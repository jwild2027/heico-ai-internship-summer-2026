#!/usr/bin/env python3
"""Audit OCR file coverage for source-linked TIFF pages."""

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

from tiff.pipeline_manifest import refresh_manifest_ocr_coverage_summary  # noqa: E402
from tiff.ocr_coverage_audit import (  # noqa: E402
    DEFAULT_DB_PATH,
    DEFAULT_MIN_CHARS,
    audit_ocr_coverage,
    format_ocr_coverage_audit,
    write_ocr_coverage_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=None, help="Optional local_config.yaml/json path")
    parser.add_argument("--db-path", default=None, help="SQLite search/RAG DB path")
    parser.add_argument("--min-chars", type=int, default=DEFAULT_MIN_CHARS, help="Flag non-empty OCR files below this visible-character count")
    parser.add_argument("--sample-limit", type=int, default=20, help="Sample rows to print")
    parser.add_argument("--write-json", action="store_true", help="Write JSON audit output")
    parser.add_argument("--json-output", default="local_data/ocr/ocr_coverage_audit.json")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero if OCR paths/files are missing or unreadable")
    parser.add_argument("--no-refresh-manifest", action="store_true", help="Do not refresh latest pipeline manifest after writing JSON")
    parser.add_argument("--fail-on-empty-ocr", action="store_true", help="Also exit nonzero if any OCR files are empty or suspiciously short")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = load_local_config(args.config) if args.config else {}
    db_path = args.db_path or str(cfg.get("db_path") or DEFAULT_DB_PATH)

    summary = audit_ocr_coverage(db_path, min_chars=args.min_chars, sample_limit=max(1, args.sample_limit))
    print(format_ocr_coverage_audit(summary, sample_limit=max(0, args.sample_limit)))

    if args.write_json:
        path = write_ocr_coverage_json(summary, args.json_output)
        print("")
        print(f"JSON: {path}")
        if not args.no_refresh_manifest:
            written = refresh_manifest_ocr_coverage_summary(ocr_coverage_json=path)
            if written:
                print("Refreshed pipeline manifest OCR coverage summary:")
                for item in written:
                    print(f"  {item}")

    if args.strict and not summary.local_ocr_paths_ready:
        print("")
        print("Local OCR path/file coverage is not ready.")
        return 1
    if args.fail_on_empty_ocr and summary.has_empty_or_short_ocr:
        print("")
        print("Empty or short OCR files require review.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
