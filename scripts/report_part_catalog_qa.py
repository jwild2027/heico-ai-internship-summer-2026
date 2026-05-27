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
from tiff.part_qa import run_all_part_qa_reports, write_qa_csv, write_qa_html, write_qa_json  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Run filtered part catalog QA reports")
    p.add_argument("--config", default=None)
    p.add_argument("--db-path", default=None)
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--output-dir", default="local_data/qa")
    p.add_argument(
        "--include-info-noise",
        action="store_true",
        help="Also include reference-like mentions suppressed from the main QA report",
    )
    args = p.parse_args()
    cfg = load_local_config(args.config)
    db_path = args.db_path or str(cfg.get("db_path") or "local_data/db/tiff_search.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        records = run_all_part_qa_reports(conn, limit=args.limit, include_info_noise=args.include_info_noise)
    finally:
        conn.close()
    out = Path(args.output_dir)
    csv_path = write_qa_csv(records, out / "part_catalog_qa_all.csv")
    json_path = write_qa_json(records, out / "part_catalog_qa_all.json")
    html_path = write_qa_html(records, out / "part_catalog_qa_all.html", title="Part Catalog QA - Filtered Reports")
    by_report: dict[str, int] = {}
    for record in records:
        by_report[record.report] = by_report.get(record.report, 0) + 1
    print("Part catalog QA complete")
    print(f"  Total rows: {len(records)}")
    for report, count in sorted(by_report.items()):
        print(f"  {report}: {count}")
    print(f"  CSV: {csv_path}")
    print(f"  JSON: {json_path}")
    print(f"  HTML: {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
