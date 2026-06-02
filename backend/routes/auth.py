import re
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models import User
from backend.services.auth_service import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> int:
    if not credentials:
        raise HTTPException(status_code=401, detail="请先登录")
    user_id = decode_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    return user_id


def get_optional_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[int]:
    if not credentials:
        return None
    return decode_token(credentials.credentials)


class RegisterBody(BaseModel):
    email: str
    username: str
    password: str


class LoginBody(BaseModel):
    email: str
    password: str


@router.post("/register")
def register(body: RegisterBody, bg: BackgroundTasks, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    username = body.username.strip()

    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    if len(username) < 2:
        raise HTTPException(status_code=400, detail="昵称至少 2 个字符")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="该邮箱已注册，请直接登录")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=409, detail="该昵称已被占用，请换一个")

    user = User(email=email, username=username, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    from backend.main import backup_db
    bg.add_task(backup_db)
    return {"token": create_access_token(user.id), "username": user.username, "email": user.email}


@router.post("/login")
def login(body: LoginBody, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    return {"token": create_access_token(user.id), "username": user.username, "email": user.email}


@router.get("/me")
def me(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return {"id": user.id, "username": user.username, "email": user.email}
