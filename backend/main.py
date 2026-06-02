import os
import time
import asyncio
import logging
import subprocess
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import backend.models  # noqa: F401 — triggers create_all on startup
from backend.routes import poems, search, diary, match, auth

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _apply_migrations():
    """Add new columns/tables to existing DB without breaking old data."""
    import sqlalchemy
    from backend.db import engine
    from backend.models import Base
    try:
        # Ensure all tables exist first (idempotent; safe to call after R2 restore)
        Base.metadata.create_all(bind=engine)

        with engine.connect() as conn:
            def has_column(table, col):
                rows = conn.execute(sqlalchemy.text(f"PRAGMA table_info({table})")).fetchall()
                return any(r[1] == col for r in rows)

            # users table: email column (new in email-based auth)
            if not has_column("users", "email"):
                conn.execute(sqlalchemy.text(
                    "ALTER TABLE users ADD COLUMN email TEXT"
                ))
                conn.execute(sqlalchemy.text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users(email)"
                ))

            for table in ("poems", "diary_entries", "user_logs"):
                if not has_column(table, "user_id"):
                    conn.execute(sqlalchemy.text(
                        f"ALTER TABLE {table} ADD COLUMN user_id INTEGER REFERENCES users(id)"
                    ))
            conn.commit()
    except Exception:
        logger.exception("Migration failed (non-fatal)")


def backup_db() -> None:
    """Upload poetry.db to R2. Call after any user-data write (register, save entry, delete)."""
    if not (os.environ.get("R2_ACCOUNT_ID") and os.environ.get("R2_ACCESS_KEY_ID")):
        logger.warning("backup_db: R2 env vars not set, skipping")
        return
    import sqlite3
    import boto3
    from botocore.client import Config
    from pathlib import Path

    db_path = Path(__file__).parent.parent / "data" / "personal" / "poetry.db"
    logger.info("backup_db: path=%s exists=%s", db_path, db_path.exists())
    if not db_path.exists():
        logger.error("backup_db: DB file not found at %s", db_path)
        return

    # Checkpoint WAL so main DB file contains all committed data before upload
    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception:
        logger.warning("backup_db: WAL checkpoint failed (continuing anyway)")

    try:
        client = boto3.client(
            "s3",
            endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
            aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
        size_kb = db_path.stat().st_size // 1024
        client.upload_file(str(db_path), os.environ["R2_BUCKET"], "backups/poetry.db")
        logger.info("backup_db: SUCCESS — uploaded %d KB to R2", size_kb)
    except Exception:
        logger.exception("backup_db: FAILED to upload to R2")


async def _download_data():
    if not (os.environ.get("R2_ACCOUNT_ID") and os.environ.get("R2_ACCESS_KEY_ID")):
        return
    logger.info("后台开始从 R2 下载数据…")
    proc = await asyncio.create_subprocess_exec(
        "python", "scripts/download_from_r2.py",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    if out:
        logger.info(out.decode(errors="replace"))
    if proc.returncode != 0:
        logger.error("R2 数据下载失败，returncode=%d", proc.returncode)
    else:
        logger.info("R2 数据下载完成，重置数据库连接池")
        from backend.db import engine
        engine.dispose()
        _apply_migrations()


def _prewarm_embedder():
    """加载 BGE 模型和 ChromaDB，避免第一次请求时的冷启动延迟。"""
    try:
        from backend.services.embedder import EmbedderService
        svc = EmbedderService()
        logger.info("EmbedderService 预热完成，corpus=%d 首", svc.corpus.count())
    except Exception:
        logger.exception("EmbedderService 预热失败（非致命）")


async def _download_and_prewarm():
    """先下载数据，再重置单例并预热——避免预热跑在下载之前拿到空库。"""
    await _download_data()
    # 下载完后重置单例，确保 EmbedderService 从完整数据重新初始化
    try:
        from backend.services.embedder import EmbedderService
        EmbedderService._instance = None
        logger.info("EmbedderService 单例已重置，开始预热…")
    except Exception:
        pass
    await asyncio.to_thread(_prewarm_embedder)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _apply_migrations()
    asyncio.create_task(_download_and_prewarm())
    yield


app = FastAPI(title="拾句", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    ms = round((time.time() - start) * 1000)
    logger.info(f"{request.method} {request.url.path} {response.status_code} {ms}ms")
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, _exc: Exception):
    logger.exception(f"Unhandled error on {request.url.path}")
    return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})


app.include_router(auth.router)
app.include_router(poems.router)
app.include_router(search.router)
app.include_router(diary.router)
app.include_router(match.router)

data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
if os.path.isdir(data_dir):
    app.mount("/data", StaticFiles(directory=data_dir), name="data")

from fastapi.responses import FileResponse

frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/static", StaticFiles(directory=os.path.join(frontend_dir, "static")), name="static")


@app.get("/", include_in_schema=False)
def root():
    return FileResponse(os.path.join(frontend_dir, "index.html"))


@app.get("/photo/{path:path}", include_in_schema=False)
def serve_photo(path: str):
    from backend.services.storage import get_photo_bytes
    from fastapi.responses import Response
    data = get_photo_bytes(path)
    if not data:
        raise HTTPException(status_code=404, detail="图片不存在")
    return Response(content=data, media_type="image/jpeg")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/full")
def health_full():
    try:
        from backend.services.embedder import EmbedderService
        info = EmbedderService().health_check()
    except Exception:
        info = {"vectorstore_ready": False, "corpus_count": 0, "personal_count": 0}
    return {"status": "ok", **info}
