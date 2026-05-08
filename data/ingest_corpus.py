"""
One-time script to ingest chinese-poetry JSON files into SQLite + ChromaDB.

Usage:
  python data/ingest_corpus.py
  python data/ingest_corpus.py --limit 500   # fast test run
  python data/ingest_corpus.py --reset       # clear and re-ingest everything
"""

import argparse
import json
import os
import sys

import zhconv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.orm import Session
from backend.db import SessionLocal
from backend.models import Base, Poem, UserLog  # noqa: F401 — ensure tables exist

try:
    from rich.progress import track
    from rich import print as rprint
except ImportError:
    def track(it, description=""):
        return it
    rprint = print

CORPUS_DIR = os.path.join(os.path.dirname(__file__), "corpus")
BATCH_SIZE = 500


def s(text):
    """Convert traditional Chinese to simplified."""
    return zhconv.convert(text, "zh-hans") if text else text


def parse_poems_from_file(filepath: str) -> list:
    filename = os.path.basename(filepath)
    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []

    if not isinstance(data, list):
        return []

    poems = []
    for item in data:
        paragraphs = item.get("paragraphs") or item.get("content") or []
        if not paragraphs:
            continue
        content = s("\n".join(paragraphs) if isinstance(paragraphs, list) else str(paragraphs))
        if not content.strip():
            continue

        ci_pai = s(item.get("rhythmic") or item.get("ci_pai") or None)
        if "tang" in filename.lower():
            dynasty = "唐"
        elif "song" in filename.lower() or ci_pai:
            dynasty = "宋"
        else:
            dynasty = s(item.get("dynasty")) or None

        poems.append({
            "title": s(item.get("title") or None),
            "author": s(item.get("author") or None),
            "dynasty": dynasty,
            "ci_pai": ci_pai,
            "content": content,
        })
    return poems


def ingest(limit=None, reset: bool = False):
    if not os.path.isdir(CORPUS_DIR):
        rprint(f"[red]语料库目录不存在: {CORPUS_DIR}[/red]")
        rprint("  git clone https://github.com/chinese-poetry/chinese-poetry.git data/corpus/")
        sys.exit(1)

    db: Session = SessionLocal()

    if reset:
        db.query(Poem).filter(Poem.source == "corpus").delete()
        db.commit()
        # Also reset ChromaDB corpus collection
        from backend.services.embedder import EmbedderService
        embedder = EmbedderService()
        embedder.client.delete_collection("corpus")
        embedder.corpus = embedder.client.get_or_create_collection("corpus")
        rprint("[yellow]已清空语料库（数据库 + 向量库）[/yellow]")

    existing_count = db.query(Poem).filter(Poem.source == "corpus").count()
    if existing_count > 0 and not reset:
        rprint(f"[green]语料库已有 {existing_count} 首诗词，跳过。如需重新导入请加 --reset[/green]")
        db.close()
        return

    json_files = []
    for root, _, files in os.walk(CORPUS_DIR):
        for fname in sorted(files):
            if fname.endswith(".json"):
                json_files.append(os.path.join(root, fname))

    if not json_files:
        rprint(f"[red]未找到任何 JSON 文件: {CORPUS_DIR}[/red]")
        sys.exit(1)

    rprint(f"找到 {len(json_files)} 个 JSON 文件，开始解析（繁→简转换中）...")

    all_poems = []
    for filepath in json_files:
        all_poems.extend(parse_poems_from_file(filepath))
        if limit and len(all_poems) >= limit:
            all_poems = all_poems[:limit]
            break

    rprint(f"解析完成，共 {len(all_poems)} 首，开始写入数据库...")

    inserted_poems = []
    for i in range(0, len(all_poems), BATCH_SIZE):
        batch = all_poems[i:i + BATCH_SIZE]
        orm_objs = [
            Poem(
                title=p["title"],
                author=p["author"],
                dynasty=p["dynasty"],
                ci_pai=p["ci_pai"],
                content=p["content"],
                source="corpus",
            )
            for p in batch
        ]
        db.add_all(orm_objs)
        db.flush()
        inserted_poems.extend(orm_objs)
        rprint(f"  数据库写入: {min(i + BATCH_SIZE, len(all_poems))}/{len(all_poems)}")

    db.commit()
    rprint(f"[green]数据库写入完成，共 {len(inserted_poems)} 首[/green]")

    rprint("开始向量化...")
    from backend.services.embedder import EmbedderService
    embedder = EmbedderService()

    for _, poem in track(list(enumerate(inserted_poems)), description="向量化中..."):
        text = " ".join(filter(None, [poem.title, poem.content]))
        embedder.add_poem_to_corpus(poem.id, text, {
            "author": poem.author or "",
            "dynasty": poem.dynasty or "",
            "ci_pai": poem.ci_pai or "",
            "title": poem.title or "",
        })

    db.close()
    rprint(f"[bold green]✓ 完成！共 {len(inserted_poems)} 首诗词入库并向量化。[/bold green]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="导入 chinese-poetry 语料库")
    parser.add_argument("--limit", type=int, default=None, help="限制导入数量（测试用）")
    parser.add_argument("--reset", action="store_true", help="清空已有语料重新导入")
    args = parser.parse_args()
    ingest(limit=args.limit, reset=args.reset)
