import os
import re
import secrets

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
FROM_ADDRESS = "拾句 <noreply@shiju.app>"


def is_valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email))


def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def send_otp_email(to_email: str, otp: str) -> None:
    import resend
    resend.api_key = RESEND_API_KEY

    body = (
        f"您好，\n\n"
        f"您的拾句验证码是：{otp}\n\n"
        f"验证码 10 分钟内有效，请勿转发给他人。\n\n"
        f"——拾句"
    )
    resend.Emails.send({
        "from": FROM_ADDRESS,
        "to": [to_email],
        "subject": "【拾句】邮箱验证码",
        "text": body,
    })
