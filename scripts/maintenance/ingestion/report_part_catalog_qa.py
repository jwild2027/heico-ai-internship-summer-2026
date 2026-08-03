#!/usr/bin/env python3
"""Run filtered part catalog QA reports from the command line.

Default behavior is command-line first: write CSV/JSON artifacts and print a
summary. HTML is opt-in with --write-html.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.local_config import load_local_config  # noqa: E402
from tiff.part_qa import (  # noqa: E402
    QARecord,
    run_all_part_qa_reports,
    write_qa_csv,
    write_qa_html,
    write_qa_json,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run filtered part catalog QA reports")
    parser.add_argument("--config", default=None)
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output-dir", default="local_data/qa")
    parser.add_argument(
        "--include-info-noise",
        action="store_true",
        help="Also include reference-like mentions suppressed from the main QA report",
    )
    parser.add_argument(
        "--write-html",
        action="store_true",
        help="Also write part_catalog_qa_all.html. Default is CSV/JSON plus terminal output only.",
    )
    return parser


def summarize_by_report(records: Iterable[QARecord]) -> dict[str, int]:
    by_report: dict[str, int] = {}
    for record in records:
        by_report[record.report] = by_report.get(record.report, 0) + 1
    return by_report


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    cfg = load_local_config(args.config) if args.config else {}
    db_path = args.db_path or str(cfg.get("db_path") or "local_data/db/tiff_search.db")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        records = run_all_part_qa_reports(
            conn,
            limit=args.limit,
            include_info_noise=args.include_info_noise,
        )
    finally:
        conn.close()

    out = Path(args.output_dir)
    csv_path = write_qa_csv(records, out / "part_catalog_qa_all.csv")
    json_path = write_qa_json(records, out / "part_catalog_qa_all.json")
    html_path = None
    if args.write_html:
        html_path = write_qa_html(
            records,
            out / "part_catalog_qa_all.html",
            title="Part Catalog QA - Filtered Reports",
        )

    print("Part catalog QA complete")
    print(f"  Total rows: {len(records)}")
    for report, count in sorted(summarize_by_report(records).items()):
        print(f"  {report}: {count}")
    print(f"  CSV: {csv_path}")
    print(f"  JSON: {json_path}")
    if html_path is not None:
        print(f"  HTML: {html_path}")
    else:
        print("  HTML: not written (use --write-html to create it)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
