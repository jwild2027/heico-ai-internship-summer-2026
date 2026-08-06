#!/usr/bin/env python3
"""Search the local TIFF search catalog."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.search_index import (  # noqa: E402
    format_result,
    open_source_path,
    result_to_dict,
    search_db,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search the local TIFF catalog by part number, ATA code, manual code, or OCR keyword."
    )
    parser.add_argument("query", help="Search text, part number, ATA code, or keyword phrase.")
    parser.add_argument(
        "--db-path",
        default="local_data/db/tiff_search.db",
        help="SQLite search database created by build_tiff_search_index.py.",
    )
    parser.add_argument("--limit", type=int, default=20, help="Maximum number of results to show.")
    parser.add_argument(
        "--mode",
        choices=["auto", "part", "keyword"],
        default="auto",
        help="Search mode. auto tries exact part-number search first, then keyword search.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON results instead of readable text.")
    parser.add_argument(
        "--open-first",
        action="store_true",
        help="Open the TIFF path from the first result using the operating system default viewer.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results = search_db(Path(args.db_path), args.query, limit=args.limit, mode=args.mode)

    if args.json:
        print(json.dumps([result_to_dict(r) for r in results], ensure_ascii=True, indent=2))
    else:
        print(f"Search: {args.query}")
        print(f"Results: {len(results)}")
        print("")
        if not results:
            print("No matches found.")
            return 1
        for i, result in enumerate(results, start=1):
            print(format_result(result, i))
            print("")

    if args.open_first and results:
        open_source_path(results[0].tiff_path)

    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
