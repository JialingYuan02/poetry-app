"""
本地运行一次：把 poetry.db 和 vectorstore/ 上传到 R2。
用法：python scripts/upload_to_r2.py
"""
import os
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
from botocore.client import Config
from dotenv import load_dotenv

load_dotenv()

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


def upload_one(client, local_path: Path, key: str):
    mb = local_path.stat().st_size / 1024 / 1024
    print(f"  ↑ {key}  ({mb:.1f} MB)")
    client.upload_file(str(local_path), BUCKET, key)
    return key


def main():
    client = make_client()

    # --- poetry.db ---
    db_path = BASE_DIR / "data" / "personal" / "poetry.db"
    if db_path.exists():
        print("上传 poetry.db ...")
        upload_one(client, db_path, "backups/poetry.db")
        print("  ✓ 完成\n")
    else:
        print("poetry.db 不存在，跳过。")

    # --- vectorstore/ ---
    vs_dir = BASE_DIR / "vectorstore"
    if not vs_dir.exists():
        print("vectorstore/ 不存在，跳过。")
        return

    files = [f for f in vs_dir.rglob("*") if f.is_file()]
    print(f"上传 vectorstore/ （{len(files)} 个文件）...")

    tasks = [(client, f, f"backups/vectorstore/{f.relative_to(vs_dir)}") for f in files]

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(upload_one, *t): t[2] for t in tasks}
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as e:
                print(f"  ✗ 上传失败 {futures[fut]}: {e}", file=sys.stderr)

    print(f"\n✓ vectorstore 上传完成（{len(files)} 个文件）")


if __name__ == "__main__":
    main()
