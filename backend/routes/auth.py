from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
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
from backend.services.email_service import generate_otp, is_valid_email, send_otp_email

router = APIRouter(prefix="/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)

# In-memory OTP store: email -> (otp, expires_at)
_otp_store: dict[str, tuple[str, datetime]] = {}
_OTP_TTL = timedelta(minutes=10)


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


class RequestOTPBody(BaseModel):
    email: str


class RegisterBody(BaseModel):
    email: str
    otp: str
    username: str   # display name / nickname
    password: str


class LoginBody(BaseModel):
    email: str
    password: str


@router.post("/request-otp")
def request_otp(body: RequestOTPBody):
    email = body.email.strip().lower()
    if not is_valid_email(email):
        raise HTTPException(status_code=400, detail="邮箱格式不正确")

    otp = generate_otp()
    _otp_store[email] = (otp, datetime.utcnow() + _OTP_TTL)

    try:
        send_otp_email(email, otp)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"验证码发送失败，请检查邮箱是否正确：{exc}")

    return {"message": "验证码已发送，请查收邮件"}


@router.post("/register")
def register(body: RegisterBody, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    username = body.username.strip()

    # Verify OTP
    stored = _otp_store.get(email)
    if not stored or stored[0] != body.otp.strip():
        raise HTTPException(status_code=400, detail="验证码无效")
    if datetime.utcnow() > stored[1]:
        raise HTTPException(status_code=400, detail="验证码已过期，请重新获取")
    del _otp_store[email]

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
