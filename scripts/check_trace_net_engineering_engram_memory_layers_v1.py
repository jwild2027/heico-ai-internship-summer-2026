#!/usr/bin/env python3
from __future__ import annotations

import argparse

from tiff.trace_net_engineering_engram_memory_layers_v1 import check_memory_layer_manifest


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Engineering Engram Memory Layers v1")
    parser.add_argument("--memory-layers", required=True)
    parser.add_argument("--min-atoms", type=int, default=6)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--require-all-layers", action="store_true")
    parser.add_argument("--require-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--max-write-attempts", type=int, default=0)
    return parser


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = check_memory_layer_manifest(
        memory_layers_path=args.memory_layers,
        min_atoms=args.min_atoms,
        require_all_layers=args.require_all_layers,
        max_unsafe=args.max_unsafe,
        require_quality_pass=args.require_quality_pass,
    )
    summary = result.get("summary", {})
    if args.require_no_answer_permission and int(summary.get("answer_permission_count", 0) or 0) != 0:
        result["quality_status"] = "FAIL"
        result.setdefault("quality_errors", []).append("answer_permission_count must be zero")
    if int(summary.get("write_attempt_count", 0) or 0) > args.max_write_attempts:
        result["quality_status"] = "FAIL"
        result.setdefault("quality_errors", []).append("write_attempt_count above maximum")

    print(f"status={result.get('status')}")
    print(f"quality_status={result.get('quality_status')}")
    print(f"memory_atom_count={summary.get('memory_atom_count')}")
    print(f"layer_counts={summary.get('layer_counts')}")
    print(f"unsafe_finding_count={summary.get('unsafe_finding_count')}")
    print(f"answer_permission_count={summary.get('answer_permission_count')}")
    print(f"write_attempt_count={summary.get('write_attempt_count')}")
    return 0 if result.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
