#!/usr/bin/env python3
"""Scan one TIFF file and write a JSON metadata report.

Examples:
    python scripts/scan_tiff_to_json.py --input sample.tif --output local_data/json_scans/sample.json
    python scripts/scan_tiff_to_json.py --input sample.tif --output sample.json --no-hash
    python scripts/scan_tiff_to_json.py --input sample.tif --output sample.json --ocr
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from the repo root without installing the package.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.json_report import scan_tiff_to_dict, write_scan_json
from tiff.sqlite_store import connect, upsert_scan_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan a TIFF and write a JSON report.")
    parser.add_argument("--input", required=True, help="Path to one .tif/.tiff file")
    parser.add_argument("--output", required=True, help="Where to write the JSON report")
    parser.add_argument(
        "--source-root",
        default=None,
        help="Optional root path used to calculate relative_path in the report",
    )
    parser.add_argument(
        "--no-hash",
        action="store_true",
        help="Skip SHA-256 hashing for faster scans of very large TIFFs",
    )
    parser.add_argument(
        "--no-filename-parse",
        action="store_true",
        help="Do not try to parse drawing metadata from the filename",
    )
    parser.add_argument(
        "--ocr",
        action="store_true",
        help="Run local Tesseract OCR on likely title-block/header regions",
    )
    parser.add_argument(
        "--ocr-page-index",
        type=int,
        default=0,
        help="Zero-based TIFF page index to OCR. Default: 0",
    )
    parser.add_argument(
        "--ocr-lang",
        default="eng",
        help="Tesseract language code. Default: eng",
    )
    parser.add_argument(
        "--tesseract-cmd",
        default=None,
        help="Optional explicit path to tesseract.exe",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Optional SQLite DB path. When set, the scan report is also saved to TIFF metadata tables.",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="Also print the JSON report to stdout",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = scan_tiff_to_dict(
        args.input,
        source_root=args.source_root,
        hash_file=not args.no_hash,
        parse_filename=not args.no_filename_parse,
        run_ocr=args.ocr,
        ocr_page_index=args.ocr_page_index,
        ocr_lang=args.ocr_lang,
        tesseract_cmd=args.tesseract_cmd,
    )
    output_path = write_scan_json(report, args.output)

    if args.db_path:
        with connect(args.db_path) as conn:
            file_id = upsert_scan_report(conn, report)
        print(f"Saved TIFF scan to SQLite: {args.db_path} file_id={file_id}")

    if args.print:
        print(json.dumps(report, indent=2))
    else:
        print(f"Wrote TIFF scan JSON: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
