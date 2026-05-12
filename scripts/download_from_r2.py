"""
容器启动时自动运行：从 R2 下载 poetry.db 和 vectorstore/（如果本地不存在）。
"""
import os
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
from botocore.client import Config

BASE_DIR = Path(__file__).parent.parent
BUCKET = os.environ["R2_BUCKET"]


def make_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def list_prefix(client, prefix: str) -> list[dict]:
    paginator = client.get_paginator("list_objects_v2")
    objects = []
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        objects.extend(page.get("Contents", []))
    return objects


def download_one(client, key: str, local_path: Path):
    local_path.parent.mkdir(parents=True, exist_ok=True)
    mb = 0
    try:
        head = client.head_object(Bucket=BUCKET, Key=key)
        mb = head["ContentLength"] / 1024 / 1024
    except Exception:
        pass
    print(f"  ↓ {key}  ({mb:.1f} MB)")
    client.download_file(BUCKET, key, str(local_path))
    return key


def main():
    client = make_client()

    # --- poetry.db ---
    db_path = BASE_DIR / "data" / "personal" / "poetry.db"
    if db_path.exists():
        print("poetry.db 已存在，跳过下载。")
    else:
        print("下载 poetry.db ...")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        client.download_file(BUCKET, "backups/poetry.db", str(db_path))
        mb = db_path.stat().st_size / 1024 / 1024
        print(f"  ✓ 完成（{mb:.0f} MB）\n")

    # --- vectorstore/ ---
    vs_marker = BASE_DIR / "vectorstore" / "chroma.sqlite3"
    if vs_marker.exists():
        print("vectorstore/ 已存在，跳过下载。")
        return

    print("下载 vectorstore/ ...")
    objects = list_prefix(client, "backups/vectorstore/")
    if not objects:
        print("  ✗ R2 中没有 vectorstore 数据，请先运行 upload_to_r2.py", file=sys.stderr)
        sys.exit(1)

    vs_dir = BASE_DIR / "vectorstore"

    def _dl(obj):
        key = obj["Key"]
        rel = key[len("backups/vectorstore/"):]
        return download_one(client, key, vs_dir / rel)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_dl, obj): obj["Key"] for obj in objects}
        failed = []
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as e:
                failed.append(f"{futures[fut]}: {e}")

    if failed:
        for f in failed:
            print(f"  ✗ {f}", file=sys.stderr)
        sys.exit(1)

    print(f"\n✓ vectorstore 下载完成（{len(objects)} 个文件）")


if __name__ == "__main__":
    main()
