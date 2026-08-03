#!/usr/bin/env python3
"""Search the extracted part catalog directly."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.part_catalog import format_catalog_row, query_part_catalog  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search part numbers and extracted nomenclature.")
    parser.add_argument("query", help="Part number or nomenclature text, e.g. 120-37313-001 or MAGAZINE HOLDER.")
    parser.add_argument("--db-path", default="local_data/db/tiff_search.db")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = query_part_catalog(Path(args.db_path), args.query, limit=args.limit)
    if args.json:
        print(json.dumps([asdict(row) for row in rows], ensure_ascii=True, indent=2))
        return 0 if rows else 1

    print(f"Part catalog search: {args.query}")
    print(f"Results: {len(rows)}\n")
    for i, row in enumerate(rows, start=1):
        print(format_catalog_row(row, i))
        print("")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
