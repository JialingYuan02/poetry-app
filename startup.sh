#!/bin/bash
set -e

echo "Starting uvicorn on PORT=${PORT:-8000}"
exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}"
