from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from backend.db import get_db
from backend.models import Poem, UserLog
from backend.routes.poems import poem_to_dict
from backend.routes.search import FAMOUS_POETS, _fame_bonus, _dedup_candidates

import os

router = APIRouter(prefix="/match", tags=["match"])

PHOTOS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "personal", "photos")

# 短诗（≤40字）流传度更高，给加成
def _length_bonus(content: Optional[str]) -> float:
    if not content:
        return 1.0
    n = len(content.replace("\n", "").replace(" ", "").replace("，", "").replace("。", ""))
    if n <= 40:
        return 1.10
    if n <= 100:
        return 1.0
    return 0.90


def _score_poem(base_similarity: float, poem_dict: dict) -> float:
    author = poem_dict.get("author")
    content = poem_dict.get("content")
    fame = _fame_bonus(author)
    length = _length_bonus(content)

    # 无名氏过滤：相似度不够高时不纳入
    if (not author or author == "无名氏") and base_similarity < 0.18:
        return 0.0

    return round(base_similarity * fame * length, 4)


@router.post("/photo")
async def match_photo(
    photo: UploadFile = File(...),
    user_text: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """上传照片 + 可选文字 → 推荐 2-3 首诗词。"""
    image_bytes = await photo.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片不能超过 10MB")

    # 1. Gemini 分析图片
    from backend.services.vision import VisionService
    vision = VisionService()
    analysis = vision.analyze_for_poetry(image_bytes)

    if analysis.get("error"):
        raise HTTPException(status_code=503, detail=analysis["error"])

    search_text = vision.build_search_text(analysis, user_text)

    # 2. 语义搜索
    from backend.services.embedder import EmbedderService
    embedder = EmbedderService()
    if embedder.corpus.count() == 0:
        raise HTTPException(status_code=503, detail="语料库尚未初始化")

    hits = embedder.search_corpus(search_text, n_results=20)

    # 3. 打分排序
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

    db.add(UserLog(action="match_photo", query=search_text))
    db.commit()

    return {
        "analysis": {
            "mood": analysis.get("mood", ""),
            "imagery": analysis.get("imagery", ""),
            "season": analysis.get("season", ""),
            "style": analysis.get("style", ""),
            "search_keywords": analysis.get("search_keywords", ""),
        },
        "user_text": user_text,
        "poems": top3,
    }


@router.post("/text")
async def match_text(
    user_text: str = Form(...),
    db: Session = Depends(get_db),
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

    db.add(UserLog(action="match_text", query=user_text.strip()))
    db.commit()

    return {"user_text": user_text, "poems": top3}
