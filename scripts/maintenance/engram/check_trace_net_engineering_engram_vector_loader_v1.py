#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_engineering_engram_vector_loader_v1 import check_vector_loader_manifest, write_json


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check TRACE-Net Engineering Engram vector loader manifest v1")
    p.add_argument("--vector-loader", required=True)
    p.add_argument("--min-records", type=int, default=1)
    p.add_argument("--require-all-layers", action="store_true")
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    p.add_argument("--output", default="")
    return p


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = check_vector_loader_manifest(
        vector_loader=args.vector_loader,
        min_records=args.min_records,
        require_all_layers=args.require_all_layers,
        require_quality_pass=args.require_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
        max_unsafe=args.max_unsafe,
        max_write_attempts=args.max_write_attempts,
    )
    if args.output:
        write_json(args.output, result)
    summary = result.get("summary", {})
    print(f"status={result.get('status')}")
    print(f"quality_status={result.get('quality_status')}")
    print(f"qdrant_ready_record_count={summary.get('qdrant_ready_record_count')}")
    print(f"memory_layer_counts={summary.get('memory_layer_counts')}")
    print(f"unsafe_finding_count={summary.get('unsafe_finding_count')}")
    print(f"answer_permission_count={summary.get('answer_permission_count')}")
    print(f"write_attempt_count={summary.get('write_attempt_count')}")
    return 0 if result.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
