#!/usr/bin/env python3
"""Export local TIFF search results to CSV."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.search_index import search_db  # noqa: E402
from tiff.search_web_ui import csv_text_for_results  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export TIFF search results to a CSV file.")
    parser.add_argument("query", help="Keyword, ATA code, publication number, or part number to search.")
    parser.add_argument(
        "--db-path",
        default="local_data/db/tiff_search.db",
        help="Path to the TIFF search SQLite database.",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "part", "keyword"],
        default="auto",
        help="Search mode. Use part for exact part-number testing.",
    )
    parser.add_argument("--limit", type=int, default=50, help="Maximum number of rows to export.")
    parser.add_argument(
        "--output-csv",
        default="local_data/search_results/last_search.csv",
        help="Output CSV path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results = search_db(Path(args.db_path), args.query, limit=args.limit, mode=args.mode)
    output_csv = Path(args.output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_csv.write_text(csv_text_for_results(results), encoding="utf-8-sig")
    print("TIFF search CSV created")
    print(f"  Query: {args.query}")
    print(f"  Mode: {args.mode}")
    print(f"  Results: {len(results)}")
    print(f"  CSV: {output_csv}")
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
