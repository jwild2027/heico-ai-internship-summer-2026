#!/usr/bin/env python
"""Clean OCR text derivatives in tiff_search.db without touching raw OCR."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.ocr_cleanup import run_ocr_cleanup  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create cleaned OCR derivative tables in tiff_search.db. Raw OCR is preserved."
    )
    parser.add_argument("--db-path", default="local_data/db/tiff_search.db")
    parser.add_argument("--no-reset", action="store_true", help="Do not drop existing cleanup tables first.")
    parser.add_argument("--pages-only", action="store_true", help="Only build ocr_clean_pages, not clean part catalog tables.")
    args = parser.parse_args()

    summary = run_ocr_cleanup(Path(args.db_path), reset=not args.no_reset, include_catalog=not args.pages_only)
    print("OCR cleanup complete")
    print(f"  DB: {summary.db_path}")
    print(f"  Pages cleaned: {summary.pages_cleaned}")
    print(f"  Raw chars: {summary.raw_chars}")
    print(f"  Clean chars: {summary.clean_chars}")
    print(f"  Removed decoration/noise lines: {summary.removed_lines}")
    print(f"  Catalog rows seen: {summary.catalog_rows_seen}")
    print(f"  Catalog rows cleaned: {summary.catalog_rows_cleaned}")
    print(f"  Canonical parts: {summary.canonical_parts}")
    for warning in summary.warnings:
        print(f"  Warning: {warning}")


if __name__ == "__main__":
    main()
