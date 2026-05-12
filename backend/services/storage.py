"""
Photo storage — local filesystem (dev) or Cloudflare R2 (prod).
Set R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_BUCKET
to switch to R2; omit them to use the local data/ directory.
"""
import os
from typing import Optional

_DATA_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data")
)
_r2_client = None


def _use_r2() -> bool:
    return bool(os.environ.get("R2_ACCOUNT_ID"))


def _r2():
    global _r2_client
    if _r2_client is None:
        import boto3
        from botocore.client import Config
        _r2_client = boto3.client(
            "s3",
            endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
            aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
    return _r2_client


def _bucket() -> str:
    return os.environ.get("R2_BUCKET", "poetry-app-photos")


def save_photo(jpeg_bytes: bytes, relative_path: str) -> str:
    """Save JPEG bytes; returns the same relative_path."""
    if _use_r2():
        _r2().put_object(
            Bucket=_bucket(),
            Key=relative_path,
            Body=jpeg_bytes,
            ContentType="image/jpeg",
        )
    else:
        full = os.path.join(_DATA_DIR, relative_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(jpeg_bytes)
    return relative_path


def get_photo_bytes(relative_path: str) -> Optional[bytes]:
    """Return raw bytes for a photo, or None if not found."""
    if _use_r2():
        try:
            resp = _r2().get_object(Bucket=_bucket(), Key=relative_path)
            return resp["Body"].read()
        except Exception:
            return None
    else:
        full = os.path.join(_DATA_DIR, relative_path)
        if os.path.isfile(full):
            with open(full, "rb") as f:
                return f.read()
        return None


def delete_photo(relative_path: str) -> None:
    if _use_r2():
        try:
            _r2().delete_object(Bucket=_bucket(), Key=relative_path)
        except Exception:
            pass
    else:
        full = os.path.join(_DATA_DIR, relative_path)
        if os.path.isfile(full):
            os.remove(full)
