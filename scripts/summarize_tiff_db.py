#!/usr/bin/env python3
"""Summarize the local TIFF SQLite database.

This is a quick inspection tool after running scripts/batch_scan_tiffs_to_json.py.
It prints document-type counts and a small table of recent records.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.sqlite_store import connect, list_tiff_files


def _fetch_count(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> int:
    row = conn.execute(query, params).fetchone()
    return int(row[0] if row else 0)


def summarize_db(db_path: str | Path, *, limit: int = 25) -> dict[str, Any]:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"SQLite DB does not exist: {path}")

    with connect(path) as conn:
        total_files = _fetch_count(conn, "SELECT COUNT(*) FROM tiff_files")
        total_ocr_rows = _fetch_count(conn, "SELECT COUNT(*) FROM tiff_ocr_texts")
        total_reports = _fetch_count(conn, "SELECT COUNT(*) FROM tiff_scan_reports")

        doc_type_rows = conn.execute(
            """
            SELECT detected_type, COUNT(*) AS count
            FROM tiff_document_classification
            GROUP BY detected_type
            ORDER BY count DESC, detected_type ASC
            """
        ).fetchall()

        manual_code_rows = conn.execute(
            """
            SELECT document_code, COUNT(*) AS count
            FROM tiff_manual_metadata
            WHERE document_code IS NOT NULL AND document_code != ''
            GROUP BY document_code
            ORDER BY count DESC, document_code ASC
            LIMIT 20
            """
        ).fetchall()

        section_rows = conn.execute(
            """
            SELECT section_title, COUNT(*) AS count
            FROM tiff_manual_metadata
            WHERE section_title IS NOT NULL AND section_title != ''
            GROUP BY section_title
            ORDER BY count DESC, section_title ASC
            LIMIT 20
            """
        ).fetchall()

        ata_rows = conn.execute(
            """
            SELECT ata_code, COUNT(*) AS count
            FROM tiff_manual_metadata
            WHERE ata_code IS NOT NULL AND ata_code != ''
            GROUP BY ata_code
            ORDER BY count DESC, ata_code ASC
            LIMIT 20
            """
        ).fetchall()

        recent = list_tiff_files(conn, limit=limit)

    return {
        "db_path": str(path),
        "counts": {
            "files": total_files,
            "scan_reports": total_reports,
            "ocr_rows": total_ocr_rows,
        },
        "document_types": [dict(row) for row in doc_type_rows],
        "manual_document_codes": [dict(row) for row in manual_code_rows],
        "manual_sections": [dict(row) for row in section_rows],
        "ata_codes": [dict(row) for row in ata_rows],
        "recent_records": recent,
    }


def _print_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("  none")
        return
    for row in rows:
        print("  " + " | ".join(f"{key}={value}" for key, value in row.items()))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize local TIFF scan SQLite database.")
    parser.add_argument("--db-path", default="local_data/db/tiff_scans.db")
    parser.add_argument("--limit", type=int, default=25, help="Recent record limit. Default: 25")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = summarize_db(args.db_path, limit=args.limit)
    if args.json:
        print(json.dumps(summary, indent=2))
        return 0

    print(f"SQLite DB: {summary['db_path']}")
    print("Counts:")
    for key, value in summary["counts"].items():
        print(f"  {key}: {value}")

    print("\nDocument types:")
    _print_table(summary["document_types"])

    print("\nManual document codes:")
    _print_table(summary["manual_document_codes"])

    print("\nATA codes:")
    _print_table(summary["ata_codes"])

    print("\nRecent records:")
    for row in summary["recent_records"]:
        print(
            "  "
            f"file={row.get('file_name')} | "
            f"type={row.get('detected_type')} | "
            f"doc_code={row.get('document_code')} | "
            f"section={row.get('section_title')} | "
            f"page={row.get('page_label') or row.get('page_number')} | "
            f"ata={row.get('ata_code')} | "
            f"drawing={row.get('drawing_number')}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
