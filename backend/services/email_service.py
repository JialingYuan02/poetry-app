import os
import re
import secrets
import smtplib
from email.mime.text import MIMEText

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email))


def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def send_otp_email(to_email: str, otp: str) -> None:
    body = (
        f"您好，\n\n"
        f"您的拾句验证码是：{otp}\n\n"
        f"验证码 10 分钟内有效，请勿转发给他人。\n\n"
        f"——拾句"
    )
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = "【拾句】邮箱验证码"
    msg["From"] = f"拾句 <{SMTP_USER}>"
    msg["To"] = to_email

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(SMTP_USER, SMTP_PASSWORD)
        smtp.send_message(msg)
