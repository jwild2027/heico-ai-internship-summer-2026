#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.changed_page_backend import read_changed_tiffs, tiff_paths_match, update_rag_chunks_for_pages


def _affected_pages_from_db(db_path: Path, changed_list: Path) -> list[str]:
    import sqlite3
    changed = read_changed_tiffs(changed_list)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT page_id, tiff_path, ocr_text_path FROM pages").fetchall()
        return [row["page_id"] for row in rows if any(tiff_paths_match(ch, row["tiff_path"], row["ocr_text_path"]) for ch in changed)]
    finally:
        conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Update RAG chunks for changed pages only.")
    p.add_argument("--db-path", default="local_data/db/tiff_search.db")
    p.add_argument("--changed-list", default="local_data/changed_tiffs.txt")
    p.add_argument("--page-id", action="append", default=[])
    p.add_argument("--max-chars", type=int, default=1400)
    p.add_argument("--overlap-chars", type=int, default=180)
    args = p.parse_args()
    page_ids = args.page_id or _affected_pages_from_db(Path(args.db_path), Path(args.changed_list))
    s = update_rag_chunks_for_pages(args.db_path, page_ids, max_chars=args.max_chars, overlap_chars=args.overlap_chars)
    print("Incremental RAG chunk update complete")
    print(f"  Affected pages: {len(page_ids)}")
    print(f"  RAG chunks updated: {s.rag_chunks_updated}")
    print(f"  Stale embeddings deleted: {s.stale_embeddings_deleted}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
