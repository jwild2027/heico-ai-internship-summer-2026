#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.changed_page_backend import update_search_index_for_changed_pages


def main() -> int:
    p = argparse.ArgumentParser(description="Update search DB pages/part_mentions for changed TIFF pages only.")
    p.add_argument("--rescarta-export-dir", default="local_data/rescarta_exports")
    p.add_argument("--db-path", default="local_data/db/tiff_search.db")
    p.add_argument("--changed-list", default="local_data/changed_tiffs.txt")
    args = p.parse_args()
    s = update_search_index_for_changed_pages(
        export_root=args.rescarta_export_dir,
        db_path=args.db_path,
        changed_list_path=args.changed_list,
    )
    print("Incremental search index update complete")
    print(f"  Changed files: {s.changed_files}")
    print(f"  Affected pages: {s.affected_pages}")
    print(f"  Search pages updated: {s.search_pages_updated}")
    print(f"  Part mentions updated: {s.part_mentions_updated}")
    if s.unmatched_changed_files:
        print(f"  Unmatched changed files: {len(s.unmatched_changed_files)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
