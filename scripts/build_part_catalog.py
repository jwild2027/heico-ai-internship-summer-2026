#!/usr/bin/env python3
"""Build the part nomenclature catalog from the TIFF search database."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.part_catalog import build_part_catalog  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract likely part nomenclature from OCR text and store it in tiff_search.db."
    )
    parser.add_argument(
        "--db-path",
        default="local_data/db/tiff_search.db",
        help="SQLite search database created by build_tiff_search_index.py.",
    )
    parser.add_argument("--no-reset", action="store_true", help="Do not drop the existing part_catalog table first.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = build_part_catalog(Path(args.db_path), reset=not args.no_reset)
    print("Part catalog build complete")
    print(f"  Search DB: {summary.db_path}")
    print(f"  Catalog rows created: {summary.catalog_entries}")
    print(f"  High confidence: {summary.high_confidence}")
    print(f"  Medium confidence: {summary.medium_confidence}")
    print(f"  Low confidence: {summary.low_confidence}")
    print(f"  Skipped mentions: {summary.skipped_mentions}")
    if summary.warnings:
        print("  Warnings:")
        for warning in summary.warnings:
            print(f"    - {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
