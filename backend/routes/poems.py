from collections import defaultdict
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.db import get_db
from backend.models import Poem
from backend.routes.auth import get_current_user_id

router = APIRouter(prefix="/poems", tags=["poems"])


class PoemCreate(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    dynasty: Optional[str] = None
    ci_pai: Optional[str] = None
    content: str


class MemorizedUpdate(BaseModel):
    is_memorized: bool


def poem_to_dict(p: Poem) -> dict:
    return {
        "id": p.id,
        "title": p.title,
        "author": p.author,
        "dynasty": p.dynasty,
        "ci_pai": p.ci_pai,
        "content": p.content,
        "is_memorized": p.is_memorized,
        "source": p.source,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


@router.get("")
def list_poems(
    ci_pai: Optional[str] = None,
    author: Optional[str] = None,
    dynasty: Optional[str] = None,
    is_memorized: Optional[bool] = None,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    q = db.query(Poem).filter(Poem.source == "personal", Poem.user_id == user_id)
    if ci_pai:
        q = q.filter(Poem.ci_pai == ci_pai)
    if author:
        q = q.filter(Poem.author.contains(author))
    if dynasty:
        q = q.filter(Poem.dynasty == dynasty)
    if is_memorized is not None:
        q = q.filter(Poem.is_memorized == is_memorized)
    return [poem_to_dict(p) for p in q.order_by(Poem.created_at.desc()).all()]


@router.get("/stats")
def poem_stats(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    poems = db.query(Poem).filter(Poem.source == "personal", Poem.user_id == user_id).all()
    by_dynasty = defaultdict(int)
    by_ci_pai = defaultdict(int)
    memorized = 0
    for p in poems:
        if p.dynasty:
            by_dynasty[p.dynasty] += 1
        if p.ci_pai:
            by_ci_pai[p.ci_pai] += 1
        if p.is_memorized:
            memorized += 1
    return {
        "total": len(poems),
        "memorized": memorized,
        "by_dynasty": dict(by_dynasty),
        "by_ci_pai": dict(by_ci_pai),
    }


@router.get("/{poem_id}")
def get_poem(poem_id: int, db: Session = Depends(get_db)):
    p = db.query(Poem).filter(Poem.id == poem_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="诗词不存在")
    return poem_to_dict(p)


@router.post("", status_code=201)
def create_poem(
    body: PoemCreate,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    poem = Poem(**body.model_dump(), source="personal", user_id=user_id)
    db.add(poem)
    db.commit()
    db.refresh(poem)
    from backend.services.embedder import EmbedderService
    text = " ".join(filter(None, [poem.title, poem.content]))
    EmbedderService().add_poem_to_personal(poem.id, text, {
        "author": poem.author or "",
        "dynasty": poem.dynasty or "",
        "ci_pai": poem.ci_pai or "",
        "title": poem.title or "",
        "user_id": str(user_id),
    })
    return poem_to_dict(poem)


@router.patch("/{poem_id}/memorized")
def update_memorized(
    poem_id: int,
    body: MemorizedUpdate,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    p = db.query(Poem).filter(Poem.id == poem_id, Poem.source == "personal", Poem.user_id == user_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="诗词不存在")
    p.is_memorized = body.is_memorized
    db.commit()
    db.refresh(p)
    return poem_to_dict(p)


@router.delete("/{poem_id}", status_code=204)
def delete_poem(
    poem_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    p = db.query(Poem).filter(Poem.id == poem_id, Poem.source == "personal", Poem.user_id == user_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="诗词不存在")
    db.delete(p)
    db.commit()
    from backend.services.embedder import EmbedderService
    EmbedderService().remove_from_personal(poem_id)
