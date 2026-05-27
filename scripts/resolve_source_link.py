#!/usr/bin/env python
"""Resolve one page ID, page label, or part number to source-link rows."""

from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from tiff.local_config import load_local_config
except Exception:  # pragma: no cover
    def load_local_config(path=None):
        return {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve a page or part number to TIFF/OCR/ResCarta source links.")
    parser.add_argument("query", help="Page ID, page label, or part number.")
    parser.add_argument("--config", default=None, help="Optional local_config.yaml path.")
    parser.add_argument("--db-path", default=None, help="SQLite search/RAG DB path.")
    parser.add_argument("--limit", type=int, default=20)
    return parser.parse_args()


def _norm(value: str) -> str:
    return "".join(ch for ch in (value or "").upper() if ch.isalnum())


def main() -> int:
    args = parse_args()
    cfg = load_local_config(args.config) if args.config else {}
    db_path = args.db_path or str(cfg.get("db_path") or "local_data/db/tiff_search.db")
    q = args.query.strip()
    qnorm = _norm(q)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        has_source_links = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='source_links'").fetchone()
        if not has_source_links:
            print("source_links table does not exist. Run scripts/build_rescarta_mapping.py first.")
            return 1
        rows = []
        # Exact page/source lookup.
        rows.extend(conn.execute(
            """
            SELECT sl.* FROM source_links sl
            WHERE sl.page_id=? OR sl.page_label=? OR sl.rescarta_page_id=?
            ORDER BY sl.manual_id, sl.page_sequence
            LIMIT ?
            """,
            (q, q, q, args.limit),
        ).fetchall())
        if not rows and qnorm:
            # Part lookup through part_mentions / clean catalog.
            rows.extend(conn.execute(
                """
                SELECT DISTINCT sl.*
                FROM source_links sl
                JOIN part_mentions pm ON pm.page_id = sl.page_id
                WHERE pm.part_number_normalized=? OR UPPER(pm.part_number_display)=UPPER(?)
                ORDER BY sl.manual_id, sl.page_sequence
                LIMIT ?
                """,
                (qnorm, q, args.limit),
            ).fetchall())
        if not rows and qnorm:
            rows.extend(conn.execute(
                """
                SELECT DISTINCT sl.*
                FROM source_links sl
                JOIN part_catalog_clean pc ON pc.page_id = sl.page_id
                WHERE pc.part_number_normalized=? OR UPPER(pc.part_number_display)=UPPER(?)
                ORDER BY sl.manual_id, sl.page_sequence
                LIMIT ?
                """,
                (qnorm, q, args.limit),
            ).fetchall())

    if not rows:
        print(f"No source links found for: {q}")
        return 1
    print(f"Source links for: {q}")
    for idx, row in enumerate(rows, start=1):
        label_bits = [row["publication_number"] or row["manual_id"]]
        if row["ata_code"]:
            label_bits.append(f"ATA {row['ata_code']}")
        if row["page_label"]:
            label_bits.append(f"Page {row['page_label']}")
        print(f"\n{idx}. " + " - ".join(label_bits))
        if row["rescarta_object_id"] or row["rescarta_page_id"]:
            print(f"   ResCarta object/page: {row['rescarta_object_id']} / {row['rescarta_page_id']}")
        if row["rescarta_url"]:
            print(f"   ResCarta URL: {row['rescarta_url']}")
        if row["source_url"]:
            print(f"   Source URL: {row['source_url']}")
        if row["tiff_path"]:
            print(f"   TIFF: {row['tiff_path']}")
        if row["ocr_text_path"]:
            print(f"   OCR: {row['ocr_text_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
