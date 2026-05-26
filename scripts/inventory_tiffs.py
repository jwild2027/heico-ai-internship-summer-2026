"""Inventory TIFF files and store metadata in SQLite.

This is the first TIFF step. It does not send data to any cloud endpoint and it
keeps the original TIFF files in place.

Usage:
    python scripts/inventory_tiffs.py --dir "C:/path/to/tiffs" --db-path rag.db
    python scripts/inventory_tiffs.py --dir "C:/path/to/tiffs" --db-path rag.db --limit 100 --no-hash
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.inventory import inventory_directory
from tiff.metadata_parser import parse_title_block_text
from tiff.sqlite_store import (
    connect,
    init_tiff_schema,
    list_tiff_files,
    upsert_drawing_metadata,
    upsert_tiff_inventory,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inventory local TIFF files into SQLite.")
    parser.add_argument("--dir", type=Path, required=True, help="Directory containing TIFF files.")
    parser.add_argument("--db-path", type=Path, default=Path("rag.db"), help="SQLite DB path.")
    parser.add_argument("--limit", type=int, default=None, help="Optional max files to process.")
    parser.add_argument("--no-recursive", action="store_true", help="Do not scan subfolders.")
    parser.add_argument("--no-hash", action="store_true", help="Skip SHA-256 hashing for faster inventory.")
    parser.add_argument(
        "--parse-filename",
        action="store_true",
        help="Try to extract drawing metadata from the filename as a first pass.",
    )
    parser.add_argument("--show", type=int, default=10, help="Show N newest rows after inventory.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.dir.resolve()
    if not root.exists():
        print(f"[error] Directory not found: {root}")
        sys.exit(1)

    print(f"TIFF inventory directory: {root}")
    print(f"DB: {args.db_path}")
    print(f"Recursive: {not args.no_recursive}")
    print(f"Hash files: {not args.no_hash}")
    print()

    started = time.perf_counter()
    records = inventory_directory(
        root,
        recursive=not args.no_recursive,
        hash_files=not args.no_hash,
        limit=args.limit,
    )

    conn = connect(args.db_path)
    init_tiff_schema(conn)

    error_count = 0
    for record in records:
        file_id = upsert_tiff_inventory(conn, record)
        if record.error:
            error_count += 1
        if args.parse_filename:
            parsed = parse_title_block_text(record.file_name)
            upsert_drawing_metadata(conn, file_id, parsed, source="filename")

    elapsed = time.perf_counter() - started
    print("=" * 72)
    print(f"Inventory complete: {len(records)} TIFF files in {elapsed:.1f}s")
    print(f"Files with metadata read errors: {error_count}")

    if args.show:
        print("\nNewest rows:")
        for row in list_tiff_files(conn, limit=args.show):
            print(
                f"- {row['file_name']} | pages={row.get('page_count')} "
                f"size={row['file_size_bytes']} sha256={(row.get('sha256') or '')[:12]} "
                f"dwg={row.get('drawing_number')} rev={row.get('revision')}"
            )
    conn.close()
    print("=" * 72)


if __name__ == "__main__":
    main()
