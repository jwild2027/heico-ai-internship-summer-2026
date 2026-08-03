#!/usr/bin/env python3
"""Summarize the Stage 0 TIFF inventory/hash database."""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def one(conn: sqlite3.Connection, sql: str, params: tuple = ()):
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def print_rows(conn: sqlite3.Connection, title: str, sql: str, params: tuple = ()) -> None:
    print(title)
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        print("  none")
        return
    for row in rows:
        print("  " + " | ".join(str(x) for x in row))


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize TIFF inventory/hash crawler DB.")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--duplicates", type=int, default=10, help="Number of duplicate groups to show.")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"[error] DB not found: {args.db}")
        return 2

    conn = sqlite3.connect(args.db)

    print(f"SQLite DB: {args.db}")
    print("Counts:")
    print(f"  crawl_runs: {one(conn, 'SELECT COUNT(*) FROM crawl_runs')}")
    print(f"  source_files: {one(conn, 'SELECT COUNT(*) FROM source_files')}")
    print(f"  tiff_pages: {one(conn, 'SELECT COUNT(*) FROM tiff_pages')}")
    print(f"  inventory_errors: {one(conn, 'SELECT COUNT(*) FROM inventory_errors')}")
    print()

    print_rows(
        conn,
        "File statuses:",
        """
        SELECT 'status=' || status, 'count=' || COUNT(*)
        FROM source_files
        GROUP BY status
        ORDER BY COUNT(*) DESC, status
        """,
    )
    print()

    print_rows(
        conn,
        "Page change statuses:",
        """
        SELECT 'change_status=' || change_status, 'count=' || COUNT(*)
        FROM tiff_pages
        GROUP BY change_status
        ORDER BY COUNT(*) DESC, change_status
        """,
    )
    print()

    print_rows(
        conn,
        "Recent crawl runs:",
        """
        SELECT 'run_id=' || id,
               'mode=' || mode,
               'files=' || files_seen,
               'pages=' || pages_seen,
               'errors=' || errors,
               'started=' || started_at,
               'finished=' || COALESCE(finished_at, '')
        FROM crawl_runs
        ORDER BY id DESC
        LIMIT 5
        """,
    )
    print()

    print_rows(
        conn,
        "Duplicate exact page-content groups:",
        """
        SELECT 'hash=' || substr(page_content_sha256, 1, 16), 'count=' || COUNT(*)
        FROM tiff_pages
        GROUP BY page_content_sha256
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC
        LIMIT ?
        """,
        (args.duplicates,),
    )
    print()

    print_rows(
        conn,
        "Recent inventory errors:",
        """
        SELECT 'path=' || COALESCE(rel_path, path), 'type=' || error_type, 'msg=' || error_message
        FROM inventory_errors
        ORDER BY id DESC
        LIMIT 10
        """,
    )
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
