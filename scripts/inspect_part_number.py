#!/usr/bin/env python3
"""Inspect one part number across clean catalog, mentions, and QA flags."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.local_config import load_local_config  # noqa: E402
from tiff.search_index import normalize_part_number  # noqa: E402


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def main() -> int:
    p = argparse.ArgumentParser(description="Inspect one part number in tiff_search.db")
    p.add_argument("part_number")
    p.add_argument("--config", default=None)
    p.add_argument("--db-path", default=None)
    args = p.parse_args()
    cfg = load_local_config(args.config)
    db_path = args.db_path or str(cfg.get("db_path") or "local_data/db/tiff_search.db")
    norm = normalize_part_number(args.part_number)
    if not norm:
        print("Could not normalize part number")
        return 2
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        print(f"Part inspection: {args.part_number} ({norm})")
        if table_exists(conn, "part_catalog_clean"):
            rows = conn.execute(
                "SELECT * FROM part_catalog_clean WHERE part_number_normalized=?",
                (norm,),
            ).fetchall()
            print("\nClean catalog:")
            if not rows:
                print("  No clean catalog row found.")
            for row in rows:
                print(f"  Part: {row['part_number_display']}")
                print(f"  Nomenclature: {row['canonical_nomenclature']}")
                print(f"  Best ATA/Page: {row['best_ata_code']} / {row['best_page_label']}")
                print(f"  TIFF: {row['source_tiff_path']}")
                print(f"  OCR: {row['source_ocr_path']}")
                if row['evidence_text']:
                    print(f"  Evidence: {row['evidence_text']}")
        if table_exists(conn, "part_catalog_mentions_clean"):
            rows = conn.execute(
                """
                SELECT clean_nomenclature, page_label, ata_code, confidence, source_tiff_path, source_ocr_path, evidence_text
                FROM part_catalog_mentions_clean
                WHERE part_number_normalized=? AND clean_nomenclature IS NOT NULL AND TRIM(clean_nomenclature) <> ''
                ORDER BY CASE confidence WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, page_sequence
                LIMIT 25
                """,
                (norm,),
            ).fetchall()
            print("\nClean catalog evidence rows:")
            if not rows:
                print("  No clean evidence rows found.")
            for row in rows:
                print(f"  - {row['ata_code']} Page {row['page_label']} [{row['confidence']}]: {row['clean_nomenclature']}")
                print(f"    TIFF: {row['source_tiff_path']}")
        if table_exists(conn, "part_mentions"):
            rows = conn.execute(
                """
                SELECT pm.part_number_display, pm.ata_code, COALESCE(p.page_label, pm.page_sequence) AS page_label,
                       p.tiff_path, p.ocr_text_path
                FROM part_mentions pm
                LEFT JOIN pages p ON p.page_id=pm.page_id
                WHERE pm.part_number_normalized=?
                ORDER BY pm.page_sequence
                LIMIT 100
                """,
                (norm,),
            ).fetchall()
            print("\nMention pages:")
            if not rows:
                print("  No part mention rows found.")
            for row in rows:
                print(f"  - {row['ata_code']} Page {row['page_label']} ({row['part_number_display']})")
                print(f"    TIFF: {row['tiff_path']}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
