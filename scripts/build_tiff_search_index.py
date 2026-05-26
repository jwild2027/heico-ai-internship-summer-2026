#!/usr/bin/env python3
"""Build a local SQLite search catalog from ResCarta staging exports."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.search_index import build_search_index  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a local TIFF search database from the OCR and metadata files "
            "inside local_data/rescarta_exports."
        )
    )
    parser.add_argument(
        "--rescarta-export-dir",
        default="local_data/rescarta_exports",
        help="Folder containing one or more ResCarta staging export folders.",
    )
    parser.add_argument(
        "--output-db",
        default="local_data/db/tiff_search.db",
        help="SQLite search database to create.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append/update instead of rebuilding the database from scratch.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = build_search_index(
        export_root=Path(args.rescarta_export_dir),
        db_path=Path(args.output_db),
        reset=not args.append,
    )

    print("TIFF search index build complete")
    print(f"  Export root: {summary.export_root}")
    print(f"  Search DB: {summary.db_path}")
    print(f"  Manuals indexed: {summary.manuals}")
    print(f"  Pages indexed: {summary.pages}")
    print(f"  Part mentions indexed: {summary.part_mentions}")

    if summary.warnings:
        print("  Warnings:")
        for warning in summary.warnings:
            print(f"    - {warning}")

    if summary.pages == 0:
        print("No pages were indexed. Check --rescarta-export-dir.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
