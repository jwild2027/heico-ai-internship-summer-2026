#!/usr/bin/env python3
"""List TIFF files that Stage 0 inventory says are new/changed.

This script bridges the inventory/hash crawler and the OCR/metadata scanner.
It reads the inventory SQLite DB produced by scripts/maintenance/ingestion/tiff_inventory_hash_crawler.py
and writes one TIFF path per line for files that have at least one page whose
latest change_status is `new` or `changed`.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Iterable

DEFAULT_STATUSES = ("new", "changed")


def parse_statuses(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return DEFAULT_STATUSES
    statuses = tuple(s.strip() for s in raw.split(",") if s.strip())
    if not statuses:
        raise ValueError("--statuses did not contain any valid statuses")
    return statuses


def connect_inventory_db(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(f"inventory DB not found: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    missing = {"source_files", "tiff_pages"} - tables
    if missing:
        raise RuntimeError(f"inventory DB missing expected table(s): {', '.join(sorted(missing))}")

    source_cols = {row["name"] for row in conn.execute("PRAGMA table_info(source_files)")}
    page_cols = {row["name"] for row in conn.execute("PRAGMA table_info(tiff_pages)")}
    required_source = {"id", "path", "rel_path"}
    required_pages = {"source_file_id", "page_index", "change_status"}
    if not required_source.issubset(source_cols):
        raise RuntimeError(f"source_files missing columns: {sorted(required_source - source_cols)}")
    if not required_pages.issubset(page_cols):
        raise RuntimeError(f"tiff_pages missing columns: {sorted(required_pages - page_cols)}")


def changed_tiff_rows(
    conn: sqlite3.Connection,
    statuses: Iterable[str] = DEFAULT_STATUSES,
    limit: int = 0,
) -> list[sqlite3.Row]:
    status_list = tuple(statuses)
    if not status_list:
        return []
    placeholders = ",".join("?" for _ in status_list)
    sql = f"""
        SELECT
            sf.id AS source_file_id,
            sf.path AS path,
            sf.rel_path AS rel_path,
            sf.file_sha256 AS file_sha256,
            COUNT(tp.id) AS matching_pages,
            GROUP_CONCAT(tp.page_index || ':' || tp.change_status, ',') AS page_statuses
        FROM source_files sf
        JOIN tiff_pages tp
            ON tp.source_file_id = sf.id
        WHERE tp.change_status IN ({placeholders})
          AND sf.status = 'active'
        GROUP BY sf.id, sf.path, sf.rel_path, sf.file_sha256
        ORDER BY sf.rel_path
    """
    params: list[object] = list(status_list)
    if limit and limit > 0:
        sql += " LIMIT ?"
        params.append(limit)
    return list(conn.execute(sql, params))


def write_text_list(rows: list[sqlite3.Row], output: Path, use_relative: bool) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write((row["rel_path"] if use_relative else row["path"]) + "\n")


def write_json(rows: list[sqlite3.Row], output: Path, use_relative: bool) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "count": len(rows),
        "path_mode": "relative" if use_relative else "absolute",
        "files": [
            {
                "source_file_id": row["source_file_id"],
                "path": row["rel_path"] if use_relative else row["path"],
                "absolute_path": row["path"],
                "relative_path": row["rel_path"],
                "file_sha256": row["file_sha256"],
                "matching_pages": row["matching_pages"],
                "page_statuses": row["page_statuses"].split(",") if row["page_statuses"] else [],
            }
            for row in rows
        ],
    }
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="List TIFF files that are new/changed in the Stage 0 inventory DB."
    )
    parser.add_argument("--inventory-db", type=Path, required=True, help="SQLite DB from tiff_inventory_hash_crawler.py")
    parser.add_argument("--output", type=Path, required=True, help="Output .txt or .json path")
    parser.add_argument(
        "--statuses",
        default=",".join(DEFAULT_STATUSES),
        help="Comma-separated page statuses to include. Default: new,changed",
    )
    parser.add_argument("--relative", action="store_true", help="Write relative paths instead of absolute paths")
    parser.add_argument("--json", action="store_true", help="Write JSON instead of one path per line")
    parser.add_argument("--limit", type=int, default=0, help="Optional max number of files to output")
    parser.add_argument("--print", action="store_true", help="Also print selected paths to stdout")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        statuses = parse_statuses(args.statuses)
        with connect_inventory_db(args.inventory_db) as conn:
            ensure_schema(conn)
            rows = changed_tiff_rows(conn, statuses=statuses, limit=args.limit)
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2

    if args.json or args.output.suffix.lower() == ".json":
        write_json(rows, args.output, use_relative=args.relative)
    else:
        write_text_list(rows, args.output, use_relative=args.relative)

    print(f"Inventory DB: {args.inventory_db}")
    print(f"Statuses: {', '.join(statuses)}")
    print(f"Changed/new TIFF files: {len(rows)}")
    print(f"Wrote: {args.output}")

    if args.print:
        for row in rows:
            print(row["rel_path"] if args.relative else row["path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
