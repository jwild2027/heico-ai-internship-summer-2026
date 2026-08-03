#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.changed_page_backend import read_changed_tiffs, tiff_paths_match, update_part_catalog_for_pages


def _affected_pages_from_db(db_path: Path, changed_list: Path) -> list[str]:
    import sqlite3
    changed = read_changed_tiffs(changed_list)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT page_id, tiff_path, ocr_text_path FROM pages").fetchall()
        page_ids = []
        for row in rows:
            if any(tiff_paths_match(ch, row["tiff_path"], row["ocr_text_path"]) for ch in changed):
                page_ids.append(row["page_id"])
        return page_ids
    finally:
        conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Update clean OCR/part catalog/canonical rows for changed pages only.")
    p.add_argument("--db-path", default="local_data/db/tiff_search.db")
    p.add_argument("--changed-list", default="local_data/changed_tiffs.txt")
    p.add_argument("--page-id", action="append", default=[])
    args = p.parse_args()
    page_ids = args.page_id or _affected_pages_from_db(Path(args.db_path), Path(args.changed_list))
    s = update_part_catalog_for_pages(args.db_path, page_ids)
    print("Incremental part catalog update complete")
    print(f"  Affected pages: {len(page_ids)}")
    print(f"  Clean pages updated: {s.clean_pages_updated}")
    print(f"  Part catalog rows updated: {s.part_catalog_rows_updated}")
    print(f"  Canonical parts updated: {s.canonical_parts_updated}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
