#!/usr/bin/env python3
"""Build complete TRACE-Net benchmark Q&A reports from an existing records.jsonl."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from scripts.trace_net_benchmark_reporting_v1 import load_records_jsonl, write_qa_reports


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records_jsonl", type=Path)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--expected-count", type=int, default=180)
    parser.add_argument(
        "--interrupted",
        action="store_true",
        help="Mark progress as interrupted rather than merely in progress.",
    )
    parser.add_argument(
        "--run-metadata",
        type=Path,
        default=None,
        help="Optional run_metadata.json to embed in progress_summary.json.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.records_jsonl.exists():
        raise SystemExit(f"records.jsonl not found: {args.records_jsonl}")
    output_dir = args.output_dir or args.records_jsonl.parent
    records, warnings = load_records_jsonl(args.records_jsonl)
    metadata = {}
    metadata_path = args.run_metadata
    if metadata_path is None:
        candidate = args.records_jsonl.parent / "run_metadata.json"
        if candidate.exists():
            metadata_path = candidate
    if metadata_path and metadata_path.exists():
        value = json.loads(metadata_path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            metadata = value

    outputs = write_qa_reports(
        records,
        output_dir=output_dir,
        expected_question_count=args.expected_count,
        interrupted=args.interrupted,
        load_warnings=warnings,
        run_metadata=metadata,
    )
    print(f"records_recovered={len(records)}")
    print(f"load_warning_count={len(warnings)}")
    for key, value in outputs.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
