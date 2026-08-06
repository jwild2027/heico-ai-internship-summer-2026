#!/usr/bin/env python3
"""Build TRACE-Net NHA phase N5 deterministic synthetic benchmark artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trace_net.graph.trace_net_nha_phase5_synthetic_benchmark_v1 import (
    DEFAULT_SEED,
    EXPECTED_QUESTION_COUNT,
    EXPECTED_SCENARIO_COUNT,
    build_phase5,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase0-3-dir", required=True)
    parser.add_argument("--phase4-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--seed", default=DEFAULT_SEED)
    parser.add_argument("--expected-scenario-count", type=int, default=EXPECTED_SCENARIO_COUNT)
    parser.add_argument("--expected-question-count", type=int, default=EXPECTED_QUESTION_COUNT)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = build_phase5(
        phase0_3_dir=args.phase0_3_dir,
        phase4_dir=args.phase4_dir,
        output_dir=args.output_dir,
        seed=args.seed,
        expected_scenario_count=args.expected_scenario_count,
        expected_question_count=args.expected_question_count,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"quality_status={summary['quality_status']}")
    print(f"summary={Path(args.output_dir).resolve() / 'trace_net_nha_phase5_summary_v1.json'}")
    if args.strict and summary["quality_status"] != "PASS":
        raise SystemExit("TRACE_NET_NHA_PHASE5=FAIL")
    print("TRACE_NET_NHA_PHASE5=PASS" if summary["quality_status"] == "PASS" else "TRACE_NET_NHA_PHASE5=WARN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
