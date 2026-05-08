import os
import uuid
from calendar import monthrange
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.db import get_db
from backend.models import DiaryEntry, Poem, UserLog
from backend.routes.poems import poem_to_dict

router = APIRouter(prefix="/diary", tags=["diary"])

PHOTOS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "personal", "photos")


class EntryCreate(BaseModel):
    date: date
    photo_path: Optional[str] = None
    scene_description: Optional[str] = None
    poem_id: Optional[int] = None
    note: Optional[str] = None
    auto_note: bool = False


def entry_to_dict(e: DiaryEntry, poem: Optional[Poem] = None) -> dict:
    return {
        "id": e.id,
        "date": e.date.isoformat(),
        "photo_path": e.photo_path,
        "scene_description": e.scene_description,
        "poem_id": e.poem_id,
        "note": e.note,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "poem": poem_to_dict(poem) if poem else None,
    }


@router.post("/upload-photo")
async def upload_photo(photo: UploadFile = File(...)):
    import io
    from PIL import Image

    image_bytes = await photo.read()
    today = date.today().isoformat()
    filename = f"{today}_{uuid.uuid4().hex[:8]}.jpg"
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    save_path = os.path.join(PHOTOS_DIR, filename)

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.save(save_path, "JPEG", quality=85)

    return {"photo_path": f"personal/photos/{filename}"}


@router.post("/entries", status_code=201)
def create_entry(body: EntryCreate, db: Session = Depends(get_db)):
    note = body.note
    if body.auto_note and body.poem_id and body.scene_description:
        poem = db.query(Poem).filter(Poem.id == body.poem_id).first()
        if poem:
            from backend.services.llm import LLMService
            try:
                note = LLMService().generate_poem_note(poem.content, body.scene_description)
            except Exception:
                pass

    entry = DiaryEntry(
        date=body.date,
        photo_path=body.photo_path,
        scene_description=body.scene_description,
        poem_id=body.poem_id,
        note=note,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    poem = db.query(Poem).filter(Poem.id == entry.poem_id).first() if entry.poem_id else None
    return entry_to_dict(entry, poem)


@router.get("/entries")
def list_entries(
    year: Optional[int] = None,
    month: Optional[int] = None,
    db: Session = Depends(get_db),
):
    q = db.query(DiaryEntry)
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
def calendar_view(year: int, month: int, db: Session = Depends(get_db)):
    last_day = monthrange(year, month)[1]
    entries = db.query(DiaryEntry).filter(
        DiaryEntry.date >= date(year, month, 1),
        DiaryEntry.date <= date(year, month, last_day),
    ).all()
    entry_map = {}
    for e in entries:
        key = e.date.isoformat()
        if key not in entry_map:
            poem = db.query(Poem).filter(Poem.id == e.poem_id).first() if e.poem_id else None
            entry_map[key] = {
                "date": key,
                "has_entry": True,
                "poem_title": poem.title if poem else None,
            }
    return list(entry_map.values())


@router.get("/entries/{entry_id}")
def get_entry(entry_id: int, db: Session = Depends(get_db)):
    e = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="日记不存在")
    poem = db.query(Poem).filter(Poem.id == e.poem_id).first() if e.poem_id else None
    return entry_to_dict(e, poem)


@router.delete("/entries/{entry_id}", status_code=204)
def delete_entry(entry_id: int, delete_photo: bool = False, db: Session = Depends(get_db)):
    e = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="日记不存在")
    if delete_photo and e.photo_path:
        full_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", e.photo_path)
        if os.path.isfile(full_path):
            os.remove(full_path)
    db.delete(e)
    db.commit()
