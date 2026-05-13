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
from backend.routes import poems, search, diary, match

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


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
        logger.info("R2 数据下载完成")


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_download_data())
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
