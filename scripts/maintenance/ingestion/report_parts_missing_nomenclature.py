#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.local_config import load_local_config  # noqa: E402
from tiff.part_qa import report_parts_missing_nomenclature, write_qa_csv, write_qa_html, write_qa_json  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Report detected part numbers with no clean nomenclature")
    p.add_argument("--config", default=None)
    p.add_argument("--db-path", default=None)
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--output-dir", default="local_data/qa")
    args = p.parse_args()
    cfg = load_local_config(args.config)
    db_path = args.db_path or str(cfg.get("db_path") or "local_data/db/tiff_search.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        records = report_parts_missing_nomenclature(conn, limit=args.limit)
    finally:
        conn.close()
    out = Path(args.output_dir)
    csv_path = write_qa_csv(records, out / "parts_missing_nomenclature.csv")
    json_path = write_qa_json(records, out / "parts_missing_nomenclature.json")
    html_path = write_qa_html(records, out / "parts_missing_nomenclature.html", title="Parts Missing Nomenclature")
    print("Parts missing nomenclature report complete")
    print(f"  Rows: {len(records)}")
    print(f"  CSV: {csv_path}")
    print(f"  JSON: {json_path}")
    print(f"  HTML: {html_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
