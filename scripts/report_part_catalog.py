#!/usr/bin/env python3
"""Print a quick report of extracted part nomenclature."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.part_catalog import part_catalog_summary_counts, query_part_catalog  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report part catalog extraction results.")
    parser.add_argument("--db-path", default="local_data/db/tiff_search.db")
    parser.add_argument("--limit", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 2

    print("Part catalog summary")
    for key, value in part_catalog_summary_counts(db_path).items():
        print(f"  {key}: {value}")

    rows = query_part_catalog(db_path, query=None, limit=args.limit)
    print("\nSample rows")
    if not rows:
        print("  No rows found. Run scripts/build_part_catalog.py first.")
        return 1
    for row in rows:
        print(
            f"  {row.part_number_display:<18} {str(row.nomenclature or ''):<35} "
            f"conf={row.confidence} page={row.page_sequence} label={row.page_label}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
