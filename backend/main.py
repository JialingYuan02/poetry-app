import os
import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import backend.models  # noqa: F401 — triggers create_all on startup
from backend.routes import poems, search, diary, match

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("预热 BGE 向量模型…")
    try:
        from backend.services.embedder import EmbedderService
        EmbedderService()
        logger.info("模型就绪")
    except Exception as e:
        logger.warning(f"模型预热失败（不影响启动）: {e}")
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


@app.get("/health")
def health():
    try:
        from backend.services.embedder import EmbedderService
        info = EmbedderService().health_check()
    except Exception:
        info = {"vectorstore_ready": False, "corpus_count": 0, "personal_count": 0}
    return {"status": "ok", **info}
