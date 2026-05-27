#!/usr/bin/env python
"""Build the ResCarta/source-link mapping table from the current search DB."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.source_links import build_source_links, format_build_summary, write_source_link_report  # noqa: E402

try:
    from tiff.local_config import load_local_config
except Exception:  # pragma: no cover
    def load_local_config(path=None):
        return {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build source_links table for TIFF/ResCarta page mappings.")
    parser.add_argument("--config", default=None, help="Optional local_config.yaml path.")
    parser.add_argument("--db-path", default=None, help="SQLite search/RAG DB path.")
    parser.add_argument(
        "--rescarta-url-template",
        default=None,
        help=(
            "Optional URL template. Available fields include {manual_id}, {object_id}, "
            "{page_id}, {page_record_id}, {page_sequence}, {page_label}."
        ),
    )
    parser.add_argument("--source-kind", default="rescarta_staging", help="Label stored on each source link row.")
    parser.add_argument("--no-reset", action="store_true", help="Do not clear existing source_links rows first.")
    parser.add_argument("--write-report", action="store_true", help="Also write CSV/JSON/HTML mapping reports.")
    parser.add_argument("--output-dir", default="local_data/source_links", help="Report output directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = load_local_config(args.config) if args.config else {}
    db_path = args.db_path or str(cfg.get("db_path") or "local_data/db/tiff_search.db")
    template = args.rescarta_url_template or cfg.get("rescarta_url_template") or cfg.get("source_url_template")

    summary = build_source_links(
        db_path,
        rescarta_url_template=str(template) if template else None,
        reset=not args.no_reset,
        source_kind=args.source_kind,
    )
    print(format_build_summary(summary))

    if args.write_report:
        report = write_source_link_report(db_path, output_dir=args.output_dir)
        print("")
        from tiff.source_links import format_report_summary
        print(format_report_summary(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
