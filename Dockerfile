FROM python:3.11-slim

WORKDIR /app

# 系统依赖（Pillow 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg-dev libpng-dev && \
    rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 确保运行时目录存在
RUN mkdir -p /app/data/personal/photos

# 复制代码
COPY backend/ backend/
COPY frontend/ frontend/
COPY data/ingest_corpus.py data/

# 预下载 BGE 模型（构建时缓存，避免启动时等待）
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')"

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
