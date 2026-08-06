#!/usr/bin/env python3
"""Run TRACE-Net NHA N6 deterministic real/synthetic query benchmarks."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trace_net.graph.trace_net_nha_phase6_query_benchmark_v1 import build_phase6


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase4-dir", required=True)
    parser.add_argument("--phase5-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--enable-synthetic-benchmark", action="store_true")
    parser.add_argument("--expected-synthetic-questions", type=int, default=60)
    parser.add_argument("--expected-real-questions", type=int, default=20)
    parser.add_argument("--max-depth", type=int, default=8)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = build_phase6(
        phase4_dir=args.phase4_dir,
        phase5_dir=args.phase5_dir,
        output_dir=args.output_dir,
        enable_synthetic_benchmark=args.enable_synthetic_benchmark,
        expected_synthetic_questions=args.expected_synthetic_questions,
        expected_real_questions=args.expected_real_questions,
        max_depth=args.max_depth,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"quality_status={summary['quality_status']}")
    print(f"summary={Path(args.output_dir).resolve() / 'trace_net_nha_phase6_summary_v1.json'}")
    if args.strict and summary["quality_status"] != "PASS":
        raise SystemExit("TRACE_NET_NHA_PHASE6=FAIL")
    print("TRACE_NET_NHA_PHASE6=PASS" if summary["quality_status"] == "PASS" else "TRACE_NET_NHA_PHASE6=WARN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
