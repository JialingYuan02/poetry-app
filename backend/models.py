from datetime import datetime
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, String, Text
from backend.db import Base, engine


class Poem(Base):
    __tablename__ = "poems"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=True)
    author = Column(String, nullable=True)
    dynasty = Column(String, nullable=True)
    ci_pai = Column(String, nullable=True)
    content = Column(Text, nullable=False)
    source = Column(String, nullable=False, default="personal")  # "corpus" or "personal"
    is_memorized = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class DiaryEntry(Base):
    __tablename__ = "diary_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    photo_path = Column(String, nullable=True)
    scene_description = Column(Text, nullable=True)
    poem_id = Column(Integer, ForeignKey("poems.id"), nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserLog(Base):
    __tablename__ = "user_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String, nullable=False)
    query = Column(Text, nullable=True)
    result_poem_id = Column(Integer, ForeignKey("poems.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)
