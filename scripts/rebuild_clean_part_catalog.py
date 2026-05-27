#!/usr/bin/env python
"""Clean OCR first, rebuild part_catalog from clean OCR, then canonicalize names."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.ocr_cleanup import rebuild_clean_part_catalog_pipeline  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the clean-OCR -> part catalog -> canonical nomenclature pipeline."
    )
    parser.add_argument("--db-path", default="local_data/db/tiff_search.db")
    parser.add_argument("--no-reset", action="store_true", help="Do not drop existing OCR cleanup tables first.")
    args = parser.parse_args()

    summary = rebuild_clean_part_catalog_pipeline(Path(args.db_path), reset=not args.no_reset)
    print("Clean part catalog rebuild complete")
    print(f"  DB: {summary.db_path}")
    print(f"  Pages cleaned: {summary.pages_cleaned}")
    print(f"  Raw chars: {summary.raw_chars}")
    print(f"  Clean chars: {summary.clean_chars}")
    print(f"  Removed decoration/noise lines: {summary.removed_lines}")
    print(f"  Catalog rows cleaned: {summary.catalog_rows_cleaned}")
    print(f"  Canonical parts: {summary.canonical_parts}")
    for warning in summary.warnings:
        print(f"  Note: {warning}")


if __name__ == "__main__":
    main()
