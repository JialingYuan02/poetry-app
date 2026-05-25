from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from backend.db import get_db
from backend.models import Poem, UserLog
from backend.routes.auth import get_optional_user_id
from backend.routes.poems import poem_to_dict
from backend.routes.search import FAMOUS_POETS, _fame_bonus, _title_penalty, _dedup_candidates

import io
import json
import os
import uuid
from datetime import date

from PIL import Image

router = APIRouter(prefix="/match", tags=["match"])

# 短诗（≤40字）流传度更高，给加成
def _length_bonus(content: Optional[str]) -> float:
    if not content:
        return 1.0
    n = len(content.replace("\n", "").replace(" ", "").replace("，", "").replace("。", ""))
    # 短诗（绝句/律诗）略有加成；长词不再惩罚，避免诗/词权重不均
    return 1.06 if n <= 40 else 1.0


def _score_poem(base_similarity: float, poem_dict: dict) -> float:
    author = poem_dict.get("author")
    content = poem_dict.get("content")
    title = poem_dict.get("title")
    fame = _fame_bonus(author)
    length = _length_bonus(content)
    title_pen = _title_penalty(title)

    # 按名气分层设相似度下限，名气越低门槛越高
    if not author or author == "无名氏":
        if base_similarity < 0.30:
            return 0.0
    elif fame >= 1.20:       # 顶级名家：李白/杜甫/苏轼等，放宽门槛
        if base_similarity < 0.10:
            return 0.0
    elif fame >= 1.08:       # 次级名家：杜牧/孟浩然等
        if base_similarity < 0.18:
            return 0.0
    else:                    # 普通作者
        if base_similarity < 0.25:
            return 0.0

    return round(base_similarity * fame * length * title_pen, 4)


def _save_photo(image_bytes: bytes) -> str:
    """压缩图片并保存（本地或 R2），返回相对路径。"""
    from backend.services.storage import save_photo
    filename = f"{date.today().isoformat()}_{uuid.uuid4().hex[:8]}.jpg"
    relative_path = f"personal/photos/{filename}"
    buf = io.BytesIO()
    Image.open(io.BytesIO(image_bytes)).convert("RGB").save(buf, "JPEG", quality=85)
    save_photo(buf.getvalue(), relative_path)
    return relative_path


def _run_search(search_text: str, db: Session) -> list:
    """向量搜索 → 打分 → 去重 → 返回 top3。"""
    from backend.services.embedder import EmbedderService
    embedder = EmbedderService()
    if embedder.corpus.count() == 0:
        raise HTTPException(status_code=503, detail="语料库尚未初始化")

    hits = embedder.search_corpus(search_text, n_results=60)
    candidates = []
    seen_ids: set = set()
    for hit in hits:
        if hit["poem_id"] in seen_ids:
            continue
        p = db.query(Poem).filter(Poem.id == hit["poem_id"]).first()
        if not p:
            continue
        seen_ids.add(p.id)
        base = round(1 - hit["distance"], 4)
        d = poem_to_dict(p)
        score = _score_poem(base, d)
        if score <= 0:
            continue
        d["score"] = score
        candidates.append(d)
    return _dedup_candidates(candidates)[:3]


@router.post("/photo")
async def match_photo(
    photo: UploadFile = File(...),
    user_text: str = Form(default=""),
    db: Session = Depends(get_db),
    user_id: Optional[int] = Depends(get_optional_user_id),
):
    """上传照片 + 可选文字 → 保存图片 → 推荐 2-3 首诗词。"""
    image_bytes = await photo.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片不能超过 10MB")

    photo_path = _save_photo(image_bytes)

    from backend.services.vision import VisionService
    vision = VisionService()
    analysis = vision.analyze_for_poetry(image_bytes)

    gemini_error = analysis.get("error")
    if gemini_error and not user_text.strip():
        raise HTTPException(status_code=503, detail=analysis["error"])

    search_text = vision.build_search_text(analysis, user_text) if not gemini_error else user_text.strip()
    top3 = _run_search(search_text, db)

    db.add(UserLog(action="match_photo", query=search_text, user_id=user_id))
    db.commit()

    return {
        "photo_path": photo_path,
        "analysis": {
            "mood": analysis.get("mood", ""),
            "imagery": analysis.get("imagery", ""),
            "season": analysis.get("season", ""),
            "style": analysis.get("style", ""),
            "search_keywords": analysis.get("search_keywords", ""),
        },
        "user_text": user_text,
        "poems": top3,
        "warning": gemini_error or None,
    }


@router.post("/text")
async def match_text(
    user_text: str = Form(...),
    db: Session = Depends(get_db),
    user_id: Optional[int] = Depends(get_optional_user_id),
):
    """只输入文字（不上传照片）→ 推荐 2-3 首诗词。"""
    if not user_text.strip():
        raise HTTPException(status_code=400, detail="请输入文字描述")

    from backend.services.embedder import EmbedderService
    embedder = EmbedderService()
    if embedder.corpus.count() == 0:
        raise HTTPException(status_code=503, detail="语料库尚未初始化")

    hits = embedder.search_corpus(user_text.strip(), n_results=20)

    candidates = []
    seen_ids: set = set()
    for hit in hits:
        if hit["poem_id"] in seen_ids:
            continue
        p = db.query(Poem).filter(Poem.id == hit["poem_id"]).first()
        if not p:
            continue
        seen_ids.add(p.id)
        base = round(1 - hit["distance"], 4)
        d = poem_to_dict(p)
        score = _score_poem(base, d)
        if score <= 0:
            continue
        d["score"] = score
        candidates.append(d)

    deduped = _dedup_candidates(candidates)
    top3 = deduped[:3]

    db.add(UserLog(action="match_text", query=user_text.strip(), user_id=user_id))
    db.commit()

    return {"user_text": user_text, "poems": top3}
