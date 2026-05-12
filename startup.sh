#!/bin/bash
set -e

# 如果配置了 R2，先从 R2 拉取数据（poetry.db + vectorstore）
if [ -n "$R2_ACCOUNT_ID" ] && [ -n "$R2_ACCESS_KEY_ID" ]; then
    echo "=== 从 R2 恢复数据 ==="
    python scripts/download_from_r2.py
    echo "=== 数据就绪 ==="
else
    echo "未检测到 R2 配置，跳过数据下载（本地开发模式）。"
fi

exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
