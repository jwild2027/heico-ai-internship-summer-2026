#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.rag_chunks import build_rag_chunks  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build local RAG chunks from tiff_search.db")
    parser.add_argument("--db-path", default="local_data/db/tiff_search.db")
    parser.add_argument("--max-chars", type=int, default=1400)
    parser.add_argument("--overlap-chars", type=int, default=180)
    parser.add_argument("--no-reset", action="store_true", help="Append/update instead of rebuilding RAG chunk tables")
    args = parser.parse_args()

    summary = build_rag_chunks(
        Path(args.db_path),
        reset=not args.no_reset,
        max_chars=args.max_chars,
        overlap_chars=args.overlap_chars,
    )
    print("RAG chunk build complete")
    print(f"  DB: {summary.db_path}")

    # Current RagChunkBuildSummary fields.
    if hasattr(summary, "pages_seen"):
        print(f"  Pages seen: {summary.pages_seen}")
    if hasattr(summary, "chunks_created"):
        print(f"  Chunks created: {summary.chunks_created}")

    # Compatibility with the alternate summary shape, if present in a local branch.
    if hasattr(summary, "page_chunks"):
        print(f"  Page OCR chunks: {summary.page_chunks}")
    if hasattr(summary, "part_chunks"):
        print(f"  Part catalog chunks: {summary.part_chunks}")
    if hasattr(summary, "total_chunks"):
        print(f"  Total chunks: {summary.total_chunks}")
    if hasattr(summary, "skipped_blank_pages"):
        print(f"  Skipped blank pages: {summary.skipped_blank_pages}")

    for warning in getattr(summary, "warnings", ()):
        print(f"  Warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
