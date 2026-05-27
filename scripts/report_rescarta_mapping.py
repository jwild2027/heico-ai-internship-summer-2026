#!/usr/bin/env python
"""Write and display the current ResCarta/source-link mapping report."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.source_links import format_report_summary, summarize_source_links, write_source_link_report  # noqa: E402

try:
    from tiff.local_config import load_local_config
except Exception:  # pragma: no cover
    def load_local_config(path=None):
        return {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report ResCarta/source-link mapping coverage.")
    parser.add_argument("--config", default=None, help="Optional local_config.yaml path.")
    parser.add_argument("--db-path", default=None, help="SQLite search/RAG DB path.")
    parser.add_argument("--output-dir", default="local_data/source_links", help="Report output directory.")
    parser.add_argument("--limit", type=int, default=None, help="Limit rows written to report files.")
    parser.add_argument("--summary-only", action="store_true", help="Print summary without writing report files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = load_local_config(args.config) if args.config else {}
    db_path = args.db_path or str(cfg.get("db_path") or "local_data/db/tiff_search.db")
    if args.summary_only:
        summary = summarize_source_links(db_path)
    else:
        summary = write_source_link_report(db_path, output_dir=args.output_dir, limit=args.limit)
    print(format_report_summary(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
