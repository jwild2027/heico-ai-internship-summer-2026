#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.ollama_client import DEFAULT_OLLAMA_URL  # noqa: E402
from tiff.rag_retriever import build_rag_embeddings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build local Ollama embeddings for TIFF RAG chunks")
    parser.add_argument("--db-path", default="local_data/db/tiff_search.db")
    parser.add_argument("--model", default="bge-m3:latest")
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    summary = build_rag_embeddings(
        Path(args.db_path),
        model=args.model,
        ollama_url=args.ollama_url,
        batch_size=args.batch_size,
        reset=args.reset,
        limit=args.limit,
    )
    print("RAG embedding build complete")
    print(f"  DB: {summary.db_path}")
    print(f"  Model: {summary.model}")
    print(f"  Chunks seen: {summary.chunks_seen}")
    print(f"  Embeddings written: {summary.embeddings_written}")
    print(f"  Skipped existing: {summary.skipped_existing}")
    print(f"  Stale deleted: {summary.stale_deleted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
