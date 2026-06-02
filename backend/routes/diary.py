import json
import os
from calendar import monthrange
from datetime import date
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models import DiaryEntry, Poem, UserLog
from backend.routes.auth import get_current_user_id
from backend.routes.poems import poem_to_dict

router = APIRouter(prefix="/diary", tags=["diary"])

PHOTOS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "personal", "photos")


def entry_to_dict(e: DiaryEntry, poem: Optional[Poem] = None) -> dict:
    return {
        "id": e.id,
        "date": e.date.isoformat(),
        "photo_path": e.photo_path,
        "scene_description": e.scene_description,
        "gemini_analysis": json.loads(e.gemini_analysis) if e.gemini_analysis else None,
        "user_text": e.user_text,
        "poem_id": e.poem_id,
        "note": e.note,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "poem": poem_to_dict(poem) if poem else None,
    }


class SaveMatchBody(BaseModel):
    photo_path: str
    poem_id: int
    analysis: Optional[dict] = None
    user_text: Optional[str] = None
    note: Optional[str] = None
    entry_date: Optional[str] = None  # "YYYY-MM-DD"; omit → today


@router.post("/save", status_code=201)
def save_match(
    body: SaveMatchBody,
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """将配诗结果存入日记（选定后调用）。"""
    poem = db.query(Poem).filter(Poem.id == body.poem_id).first()
    if not poem:
        raise HTTPException(status_code=404, detail="诗词不存在")

    try:
        entry_date = date.fromisoformat(body.entry_date) if body.entry_date else date.today()
    except ValueError:
        entry_date = date.today()

    entry = DiaryEntry(
        date=entry_date,
        photo_path=body.photo_path,
        scene_description=body.analysis.get("mood", "") if body.analysis else None,
        gemini_analysis=json.dumps(body.analysis, ensure_ascii=False) if body.analysis else None,
        user_text=body.user_text,
        poem_id=body.poem_id,
        user_id=user_id,
    )
    db.add(entry)
    db.add(UserLog(action="save_match", result_poem_id=body.poem_id, user_id=user_id))
    db.commit()
    db.refresh(entry)
    from backend.main import backup_db
    bg.add_task(backup_db)
    return entry_to_dict(entry, poem)


@router.post("/entries/{entry_id}/rematch")
async def rematch_entry(
    entry_id: int,
    photo: Optional[UploadFile] = File(default=None),
    user_text: str = Form(default=""),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """重新配诗：可选替换照片，返回新的 3 首候选（不立刻覆盖，由前端选定后再调 /diary/save 或 PATCH）。"""
    e = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id, DiaryEntry.user_id == user_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="日记不存在")

    from backend.routes.match import _save_photo, _run_search
    from backend.services.vision import VisionService

    from backend.services.storage import get_photo_bytes
    if photo:
        image_bytes = await photo.read()
        if len(image_bytes) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="图片不能超过 10MB")
        new_photo_path = _save_photo(image_bytes)
        vision = VisionService()
        analysis = vision.analyze_for_poetry(image_bytes)
    else:
        image_bytes = get_photo_bytes(e.photo_path) if e.photo_path else None
        if not image_bytes:
            raise HTTPException(status_code=400, detail="原图已不存在，请重新上传照片")
        new_photo_path = e.photo_path
        vision = VisionService()
        analysis = vision.analyze_for_poetry(image_bytes)

    if analysis.get("error"):
        raise HTTPException(status_code=503, detail=analysis["error"])

    effective_user_text = user_text or (e.user_text or "")
    search_text = vision.build_search_text(analysis, effective_user_text)
    top3 = _run_search(search_text, db)

    return {
        "entry_id": entry_id,
        "photo_path": new_photo_path,
        "analysis": analysis,
        "user_text": effective_user_text,
        "poems": top3,
    }


@router.patch("/entries/{entry_id}")
def update_entry(
    entry_id: int,
    poem_id: Optional[int] = None,
    photo_path: Optional[str] = None,
    note: Optional[str] = None,
    gemini_analysis: Optional[str] = None,
    user_text: Optional[str] = None,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """更新日记条目（选定新诗 / 替换图片路径 / 修改备注）。"""
    e = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id, DiaryEntry.user_id == user_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="日记不存在")
    if poem_id is not None:
        e.poem_id = poem_id
    if photo_path is not None:
        e.photo_path = photo_path
    if note is not None:
        e.note = note
    if gemini_analysis is not None:
        e.gemini_analysis = gemini_analysis
    if user_text is not None:
        e.user_text = user_text
    db.commit()
    db.refresh(e)
    poem = db.query(Poem).filter(Poem.id == e.poem_id).first() if e.poem_id else None
    return entry_to_dict(e, poem)


@router.get("/entries")
def list_entries(
    year: Optional[int] = None,
    month: Optional[int] = None,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    q = db.query(DiaryEntry).filter(DiaryEntry.user_id == user_id)
    if year and month:
        last_day = monthrange(year, month)[1]
        q = q.filter(
            DiaryEntry.date >= date(year, month, 1),
            DiaryEntry.date <= date(year, month, last_day),
        )
    elif year:
        q = q.filter(DiaryEntry.date >= date(year, 1, 1), DiaryEntry.date <= date(year, 12, 31))
    entries = q.order_by(DiaryEntry.date.desc()).all()
    result = []
    for e in entries:
        poem = db.query(Poem).filter(Poem.id == e.poem_id).first() if e.poem_id else None
        result.append(entry_to_dict(e, poem))
    return result


@router.get("/calendar")
def calendar_view(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    last_day = monthrange(year, month)[1]
    entries = db.query(DiaryEntry).filter(
        DiaryEntry.user_id == user_id,
        DiaryEntry.date >= date(year, month, 1),
        DiaryEntry.date <= date(year, month, last_day),
    ).order_by(DiaryEntry.date, DiaryEntry.id).all()

    day_map: dict = {}
    for e in entries:
        key = e.date.isoformat()
        poem = db.query(Poem).filter(Poem.id == e.poem_id).first() if e.poem_id else None
        item = {
            "entry_id": e.id,
            "photo_path": e.photo_path,
            "poem_title": (poem.title or poem.ci_pai or "（无题）") if poem else None,
        }
        if key not in day_map:
            day_map[key] = {"date": key, "entries": []}
        day_map[key]["entries"].append(item)

    return sorted(day_map.values(), key=lambda x: x["date"])


@router.get("/entries/{entry_id}")
def get_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    e = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id, DiaryEntry.user_id == user_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="日记不存在")
    poem = db.query(Poem).filter(Poem.id == e.poem_id).first() if e.poem_id else None
    return entry_to_dict(e, poem)


@router.delete("/entries/{entry_id}", status_code=204)
def delete_entry(
    entry_id: int,
    bg: BackgroundTasks,
    delete_photo: bool = True,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    e = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id, DiaryEntry.user_id == user_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="日记不存在")
    if delete_photo and e.photo_path:
        from backend.services.storage import delete_photo as storage_delete
        storage_delete(e.photo_path)
    db.delete(e)
    db.commit()
    from backend.main import backup_db
    bg.add_task(backup_db)
