#!/usr/bin/env python3
"""Export the extracted part catalog to CSV."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.part_catalog import catalog_rows_to_csv, query_part_catalog  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export part_catalog rows to CSV.")
    parser.add_argument("--db-path", default="local_data/db/tiff_search.db")
    parser.add_argument("--output-csv", default="local_data/search_results/part_catalog.csv")
    parser.add_argument("--limit", type=int, default=100000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 2
    rows = query_part_catalog(db_path, query=None, limit=args.limit)
    output_csv = Path(args.output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_csv.write_text(catalog_rows_to_csv(rows), encoding="utf-8-sig")
    print("Part catalog CSV created")
    print(f"  Rows: {len(rows)}")
    print(f"  CSV: {output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
