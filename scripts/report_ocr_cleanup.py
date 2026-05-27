#!/usr/bin/env python
"""Report OCR cleanup and canonical part catalog counts."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.ocr_cleanup import cleanup_summary_counts, table_exists  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Show OCR cleanup summary counts and sample clean part names.")
    parser.add_argument("--db-path", default="local_data/db/tiff_search.db")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()

    db_path = Path(args.db_path)
    print("OCR cleanup report")
    for key, value in cleanup_summary_counts(db_path).items():
        print(f"  {key}: {value}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not table_exists(conn, "part_catalog_clean"):
            print("  No part_catalog_clean table found yet.")
            return
        rows = conn.execute(
            """
            SELECT part_number_display, canonical_nomenclature, source_count, variant_count,
                   best_page_label, best_ata_code
            FROM part_catalog_clean
            ORDER BY source_count DESC, part_number_display
            LIMIT ?
            """,
            (args.limit,),
        ).fetchall()
        print("\nTop canonical parts:")
        for row in rows:
            print(
                f"  {row['part_number_display']:<18} {row['canonical_nomenclature']:<35} "
                f"sources={row['source_count']:<3} variants={row['variant_count']:<2} "
                f"page={row['best_page_label'] or ''} ata={row['best_ata_code'] or ''}"
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
