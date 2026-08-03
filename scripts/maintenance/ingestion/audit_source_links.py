#!/usr/bin/env python3
"""Audit TIFF/OCR/ResCarta source links from the command line."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from tiff.local_config import load_local_config  # type: ignore
except Exception:  # pragma: no cover
    def load_local_config(path=None):  # type: ignore
        return {}

from tiff.source_link_audit import (  # noqa: E402
    DEFAULT_DB_PATH,
    DEFAULT_SAMPLE_PARTS,
    audit_source_links,
    format_source_link_audit,
    write_source_link_audit_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=None, help="Optional local_config.yaml/json path")
    parser.add_argument("--db-path", default=None, help="SQLite search/RAG DB path")
    parser.add_argument(
        "--sample-part",
        action="append",
        default=None,
        help="Part/page query to resolve as a sample. May be repeated.",
    )
    parser.add_argument("--sample-limit", type=int, default=5, help="Rows to inspect per sample query")
    parser.add_argument("--print-limit", type=int, default=10, help="Sample rows to print")
    parser.add_argument("--no-check-files", action="store_true", help="Do not check whether TIFF/OCR files exist on disk")
    parser.add_argument("--write-json", action="store_true", help="Write JSON audit output")
    parser.add_argument("--json-output", default="local_data/source_links/source_link_audit.json")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit nonzero if local source review is not ready.",
    )
    parser.add_argument(
        "--require-real-rescarta",
        action="store_true",
        help="Exit nonzero if ResCarta URLs are missing or still local/placeholder URLs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = load_local_config(args.config) if args.config else {}
    db_path = args.db_path or str(cfg.get("db_path") or DEFAULT_DB_PATH)
    sample_queries = tuple(args.sample_part or DEFAULT_SAMPLE_PARTS)

    summary = audit_source_links(
        db_path,
        sample_queries=sample_queries,
        sample_limit=max(1, args.sample_limit),
        check_files=not args.no_check_files,
    )
    print(format_source_link_audit(summary, sample_limit=max(0, args.print_limit)))

    if args.write_json:
        path = write_source_link_audit_json(summary, args.json_output)
        print("")
        print(f"JSON: {path}")

    if args.require_real_rescarta and not summary.ready_for_real_rescarta_deeplinks:
        print("")
        print("Not ready for real ResCarta deep links yet.")
        return 2

    if args.strict and not summary.ready_for_local_source_review:
        print("")
        print("Local source review is not ready yet.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
