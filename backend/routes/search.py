from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.db import get_db
from backend.models import Poem, UserLog
from backend.routes.auth import get_current_user_id, get_optional_user_id
from backend.routes.poems import poem_to_dict

router = APIRouter(prefix="/search", tags=["search"])

FAMOUS_POETS = {
    "李白": 1.30, "杜甫": 1.30, "苏轼": 1.25, "辛弃疾": 1.22,
    "白居易": 1.20, "李清照": 1.20, "王维": 1.18, "陶渊明": 1.18,
    "杜牧": 1.15, "孟浩然": 1.15, "柳永": 1.15, "晏殊": 1.14,
    "秦观": 1.14, "欧阳修": 1.14, "王安石": 1.12, "李商隐": 1.12,
    "温庭筠": 1.10, "周邦彦": 1.10, "姜夔": 1.10, "黄庭坚": 1.10,
    "范仲淹": 1.10, "贺铸": 1.08, "柳宗元": 1.08, "韩愈": 1.08,
    "王昌龄": 1.08, "刘禹锡": 1.08, "元稹": 1.08, "晏几道": 1.08,
    "张先": 1.06, "纳兰性德": 1.12, "曹植": 1.10,
}


def _fame_bonus(author: Optional[str]) -> float:
    """Multiplier [0.95, 1.30] based on poet fame."""
    if not author:
        return 0.95
    for poet, bonus in FAMOUS_POETS.items():
        if poet in author:
            return bonus
    return 1.0


def _title_penalty(title: Optional[str]) -> float:
    """Penalize obscure occasional poems with very long titles.
    Titles listing multiple recipients (e.g. '呈葛鲁卿席大光周举同舍诸兄') are private
    correspondence and almost never the 'right' poem for a scene."""
    if not title:
        return 1.0
    n = len(title)
    if n <= 8:
        return 1.0
    if n <= 14:
        return 0.95
    if n <= 20:
        return 0.82
    return 0.65  # 20+ chars: highly obscure occasional poem


_PUNCT = str.maketrans("", "", "，。！？、；：""''「」【】《》〈〉·—…,.!?;: \n\t")

def _content_fp(poem: dict) -> str:
    """First 40 chars stripped of whitespace and punctuation — handles version variants."""
    return (poem.get("content") or "").translate(_PUNCT)[:40]


def _merge(a: dict, b: dict) -> dict:
    """Keep the longer content and the higher score from two candidate dicts."""
    best_score = max(a["score"], b["score"])
    winner = a if len(a.get("content") or "") >= len(b.get("content") or "") else b
    return {**winner, "score": best_score}


def _dedup_candidates(candidates: list) -> list:
    """Two-pass dedup:
    1) By (title, content_fp) — catches same poem attributed to different authors.
    2) By content fingerprint alone — catches same poem with different titles/punctuation.
    """
    # Pass 1: title + content fingerprint, author intentionally excluded
    # so disputed-authorship duplicates (same poem, different author) are merged
    seen_meta: dict = {}
    for c in candidates:
        title = c.get("title") or ""
        fp = _content_fp(c)
        if title:
            key = (title, fp)
        else:
            key = (c.get("ci_pai") or "", fp)

        if key not in seen_meta:
            seen_meta[key] = c
        else:
            seen_meta[key] = _merge(seen_meta[key], c)

    # Pass 2: content fingerprint — catches same poem with title punctuation differences
    seen_content: dict = {}
    for c in seen_meta.values():
        fp = _content_fp(c)
        if fp not in seen_content:
            seen_content[fp] = c
        else:
            seen_content[fp] = _merge(seen_content[fp], c)

    result = list(seen_content.values())
    result.sort(key=lambda x: x["score"], reverse=True)

    # Pass 3: same title → keep highest score only
    # Handles disputed-authorship variants where content differs slightly
    # (e.g. "白居易" vs "唐白居易" with different punctuation versions)
    seen_title: dict = {}
    for c in result:
        title = (c.get("title") or "").strip()
        if not title:
            continue
        if title not in seen_title or c["score"] > seen_title[title]["score"]:
            seen_title[title] = c

    final: list = []
    added_titles: set = set()
    for c in result:
        title = (c.get("title") or "").strip()
        if title:
            if title not in added_titles:
                final.append(seen_title[title])
                added_titles.add(title)
        else:
            final.append(c)

    return final


class SmartInputBody(BaseModel):
    query: str


class ConfirmBody(BaseModel):
    poem_id: int


@router.post("/smart-input")
def smart_input(
    body: SmartInputBody,
    db: Session = Depends(get_db),
    user_id: Optional[int] = Depends(get_optional_user_id),
):
    query = body.query.strip()

    # 1. 词牌名精确匹配 → 按名气排序返回（词牌名是一对多）
    ci_pai_exact = db.query(Poem).filter(Poem.ci_pai == query).all()
    if ci_pai_exact:
        all_c = []
        for p in ci_pai_exact:
            d = poem_to_dict(p)
            d["score"] = round(_fame_bonus(p.author), 4)
            all_c.append(d)
        db.add(UserLog(action="search", query=query, user_id=user_id))
        db.commit()
        return {"query": query, "candidates": _dedup_candidates(all_c)[:8]}

    # 2. 标题精确匹配 → 通常1:1，取名气最高的一首
    title_exact = db.query(Poem).filter(Poem.title == query).all()
    if title_exact:
        title_exact.sort(key=lambda p: _fame_bonus(p.author), reverse=True)
        best = title_exact[0]
        d = poem_to_dict(best)
        d["score"] = 1.0
        db.add(UserLog(action="search", query=query, user_id=user_id))
        db.commit()
        return {"query": query, "candidates": [d]}

    # 3. 模糊标题 / 词牌名匹配 + 语义向量搜索
    seen_ids: set = set()
    candidates = []

    for p in db.query(Poem).filter(Poem.title.contains(query)).limit(10).all():
        if p.id not in seen_ids:
            seen_ids.add(p.id)
            d = poem_to_dict(p)
            d["score"] = round(1.0 * _fame_bonus(p.author) * _title_penalty(p.title), 4)
            candidates.append(d)

    for p in db.query(Poem).filter(Poem.ci_pai.contains(query)).limit(10).all():
        if p.id not in seen_ids:
            seen_ids.add(p.id)
            d = poem_to_dict(p)
            d["score"] = round(0.99 * _fame_bonus(p.author) * _title_penalty(p.title), 4)
            candidates.append(d)

    from backend.services.embedder import EmbedderService
    embedder = EmbedderService()
    if embedder.corpus.count() > 0:
        hits = embedder.search_both(query, n_results=12)
        for hit in hits:
            if hit["poem_id"] not in seen_ids:
                p = db.query(Poem).filter(Poem.id == hit["poem_id"]).first()
                if p:
                    base = round(1 - hit["distance"], 4)
                    d = poem_to_dict(p)
                    d["score"] = round(base * _fame_bonus(p.author) * _title_penalty(p.title), 4)
                    candidates.append(d)
                    seen_ids.add(p.id)
    elif not candidates:
        raise HTTPException(
            status_code=503,
            detail="语料库尚未初始化，请先运行 python data/ingest_corpus.py",
        )

    db.add(UserLog(action="search", query=query, user_id=user_id))
    db.commit()

    return {"query": query, "candidates": _dedup_candidates(candidates)[:8]}


@router.post("/confirm")
def confirm_poem(
    body: ConfirmBody,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    poem = db.query(Poem).filter(Poem.id == body.poem_id).first()
    if not poem:
        raise HTTPException(status_code=404, detail="诗词不存在")

    if poem.source == "personal" and poem.user_id == user_id:
        db.add(UserLog(action="confirm", query=None, result_poem_id=poem.id, user_id=user_id))
        db.commit()
        return poem_to_dict(poem)

    personal = Poem(
        title=poem.title,
        author=poem.author,
        dynasty=poem.dynasty,
        ci_pai=poem.ci_pai,
        content=poem.content,
        source="personal",
        user_id=user_id,
    )
    db.add(personal)
    db.commit()
    db.refresh(personal)

    from backend.services.embedder import EmbedderService
    text = " ".join(filter(None, [personal.title, personal.content]))
    EmbedderService().add_poem_to_personal(personal.id, text, {
        "author": personal.author or "",
        "dynasty": personal.dynasty or "",
        "ci_pai": personal.ci_pai or "",
        "title": personal.title or "",
        "user_id": str(user_id),
    })

    db.add(UserLog(action="confirm", query=None, result_poem_id=personal.id, user_id=user_id))
    db.commit()

    return poem_to_dict(personal)


@router.get("/filter")
def filter_poems(
    ci_pai: Optional[str] = None,
    author: Optional[str] = None,
    dynasty: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Poem).filter(Poem.source == "personal")
    if ci_pai:
        q = q.filter(Poem.ci_pai == ci_pai)
    if author:
        q = q.filter(Poem.author.contains(author))
    if dynasty:
        q = q.filter(Poem.dynasty == dynasty)
    return [poem_to_dict(p) for p in q.all()]
