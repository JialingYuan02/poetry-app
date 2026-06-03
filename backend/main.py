import os
import time
import asyncio
import logging
import tempfile
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import backend.models  # noqa: F401 — triggers create_all on startup
from backend.routes import poems, search, diary, match, auth

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _is_postgres() -> bool:
    from backend.db import DATABASE_URL
    return DATABASE_URL.startswith("postgresql")


def _apply_migrations():
    """Add new columns/tables to existing DB without breaking old data."""
    import sqlalchemy
    from backend.db import engine
    from backend.models import Base
    try:
        Base.metadata.create_all(bind=engine)

        if _is_postgres():
            return  # PostgreSQL: create_all handles everything, no ALTER TABLE needed

        # SQLite-only: add columns that may be missing in older DB files
        with engine.connect() as conn:
            def has_column(table, col):
                rows = conn.execute(sqlalchemy.text(f"PRAGMA table_info({table})")).fetchall()
                return any(r[1] == col for r in rows)

            if not has_column("users", "email"):
                conn.execute(sqlalchemy.text("ALTER TABLE users ADD COLUMN email TEXT"))
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
    """Upload poetry.db to R2. No-op when using PostgreSQL (data is already persistent)."""
    if _is_postgres():
        return

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


def _import_poems_from_sqlite(sqlite_path: str) -> int:
    """Bulk-insert corpus poems from a SQLite file into PostgreSQL. Returns row count."""
    import sqlite3
    import sqlalchemy
    from backend.db import engine
    from backend.models import Poem

    with sqlite3.connect(sqlite_path) as src:
        src.row_factory = sqlite3.Row
        rows = src.execute(
            "SELECT id, title, author, dynasty, ci_pai, content, source, is_memorized, created_at "
            "FROM poems WHERE source = 'corpus'"
        ).fetchall()

    if not rows:
        logger.warning("SQLite backup has no corpus poems")
        return 0

    batch_size = 500
    total = 0
    with engine.begin() as conn:
        for i in range(0, len(rows), batch_size):
            batch = [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "author": r["author"],
                    "dynasty": r["dynasty"],
                    "ci_pai": r["ci_pai"],
                    "content": r["content"],
                    "source": r["source"] or "corpus",
                    "is_memorized": bool(r["is_memorized"]),
                    "user_id": None,
                    "created_at": r["created_at"],
                }
                for r in rows[i : i + batch_size]
            ]
            conn.execute(Poem.__table__.insert(), batch)
            total += len(batch)
            if total % 50000 == 0:
                logger.info("Imported %d / %d poems…", total, len(rows))

        # Reset PostgreSQL sequence to max imported ID
        conn.execute(sqlalchemy.text(
            "SELECT setval(pg_get_serial_sequence('poems', 'id'), MAX(id)) FROM poems"
        ))

    return total


async def _import_poems_to_postgres_if_needed():
    """One-time: if PostgreSQL poems table is empty, download SQLite from R2 and import."""
    if not _is_postgres():
        return

    import sqlalchemy
    from backend.db import engine
    with engine.connect() as conn:
        count = conn.execute(sqlalchemy.text("SELECT COUNT(*) FROM poems")).scalar()
    if count > 0:
        logger.info("PostgreSQL already has %d poems, skipping import", count)
        return

    if not os.environ.get("R2_ACCOUNT_ID"):
        logger.error("PostgreSQL poems empty but R2 not configured — cannot import")
        return

    logger.info("PostgreSQL poems table empty — downloading SQLite backup from R2 to import…")
    import boto3
    from botocore.client import Config

    client = boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp_path = f.name
    try:
        client.download_file(os.environ["R2_BUCKET"], "backups/poetry.db", tmp_path)
        logger.info("Downloaded SQLite backup (%d MB), importing poems…",
                    os.path.getsize(tmp_path) // (1024 * 1024))
        total = await asyncio.to_thread(_import_poems_from_sqlite, tmp_path)
        logger.info("Poem import complete: %d poems imported into PostgreSQL", total)
    except Exception:
        logger.exception("Failed to import poems from SQLite backup")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


async def _download_vectorstore():
    """Download only the vectorstore from R2 (used in both SQLite and PostgreSQL modes)."""
    if not os.environ.get("R2_ACCOUNT_ID"):
        return
    logger.info("Downloading vectorstore from R2…")
    proc = await asyncio.create_subprocess_exec(
        "python", "scripts/download_from_r2.py",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    if out:
        logger.info(out.decode(errors="replace"))
    if proc.returncode != 0:
        logger.error("R2 download failed, returncode=%d", proc.returncode)


async def _download_data():
    if not os.environ.get("R2_ACCOUNT_ID"):
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
    try:
        from backend.services.embedder import EmbedderService
        svc = EmbedderService()
        logger.info("EmbedderService 预热完成，corpus=%d 首", svc.corpus.count())
    except Exception:
        logger.exception("EmbedderService 预热失败（非致命）")


async def _download_and_prewarm():
    if _is_postgres():
        # PostgreSQL: download only vectorstore, then import poems if needed
        await _download_vectorstore()
        await _import_poems_to_postgres_if_needed()
    else:
        # SQLite: download full DB + vectorstore from R2
        await _download_data()

    try:
        from backend.services.embedder import EmbedderService
        EmbedderService._instance = None
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

    # PostgreSQL poem count (separate from vectorstore)
    pg_poem_count = None
    if _is_postgres():
        try:
            import sqlalchemy
            from backend.db import engine
            with engine.connect() as conn:
                pg_poem_count = conn.execute(sqlalchemy.text("SELECT COUNT(*) FROM poems")).scalar()
        except Exception:
            pass

    return {"status": "ok", "pg_poem_count": pg_poem_count, **info}
