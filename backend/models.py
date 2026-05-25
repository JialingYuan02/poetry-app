from datetime import datetime
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, String, Text
from backend.db import Base, engine


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, nullable=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


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
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class DiaryEntry(Base):
    __tablename__ = "diary_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    photo_path = Column(String, nullable=True)
    scene_description = Column(Text, nullable=True)
    gemini_analysis = Column(Text, nullable=True)  # JSON string
    user_text = Column(String, nullable=True)
    poem_id = Column(Integer, ForeignKey("poems.id"), nullable=True)
    note = Column(Text, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserLog(Base):
    __tablename__ = "user_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String, nullable=False)
    query = Column(Text, nullable=True)
    result_poem_id = Column(Integer, ForeignKey("poems.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)
