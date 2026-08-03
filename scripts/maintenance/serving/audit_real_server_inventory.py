#!/usr/bin/env python3
"""Read-only inventory estimator for a real TIFF server path or source ZIP."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.real_server_inventory import (  # noqa: E402
    DEFAULT_OUTPUT,
    InventoryOptions,
    audit_real_server_inventory,
    format_inventory_report,
    write_inventory_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only TIFF inventory and scale estimator.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--root", type=Path, help="Root directory/server path to inventory.")
    source.add_argument("--zip", dest="zip_path", type=Path, help="Source ZIP to inventory.")
    parser.add_argument("--target-total-tb", type=float, default=None, help="Target archive size in TiB for rough scale estimates, e.g. 5.")
    parser.add_argument("--batch-size", type=int, default=5000, help="Batch size in pages for baseline planning.")
    parser.add_argument("--sample-limit", type=int, default=10, help="Number of sample file paths to print.")
    parser.add_argument("--max-files", type=int, default=None, help="Stop after this many files for a quick sample inventory.")
    parser.add_argument("--max-stem-track", type=int, default=500_000, help="Max TIFF/OCR stems to track for pairing analysis.")
    parser.add_argument("--worker-count", type=int, default=1, help="Worker count for processing-time estimates.")
    parser.add_argument("--ocr-seconds-per-page", type=float, default=1.0, help="Estimated OCR seconds/page.")
    parser.add_argument("--context-seconds-per-page", type=float, default=12.0, help="Estimated page-context LLM seconds/page.")
    parser.add_argument("--embedding-seconds-per-page", type=float, default=0.25, help="Estimated embedding seconds/page.")
    parser.add_argument("--write-json", action="store_true", help="Write JSON report.")
    parser.add_argument("--json-output", type=Path, default=DEFAULT_OUTPUT, help="JSON output path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    options = InventoryOptions(
        root=args.root,
        zip_path=args.zip_path,
        target_total_tb=args.target_total_tb,
        batch_size_pages=args.batch_size,
        sample_limit=args.sample_limit,
        max_files=args.max_files,
        max_stem_track=args.max_stem_track,
        context_seconds_per_page=args.context_seconds_per_page,
        ocr_seconds_per_page=args.ocr_seconds_per_page,
        embedding_seconds_per_page=args.embedding_seconds_per_page,
        worker_count=args.worker_count,
        write_json=args.write_json,
        json_output=args.json_output,
    )
    report = audit_real_server_inventory(options)
    print(format_inventory_report(report))
    if args.write_json:
        write_inventory_json(report, args.json_output)
        print(f"\nJSON: {args.json_output}")
    return 0 if report.get("status") == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
