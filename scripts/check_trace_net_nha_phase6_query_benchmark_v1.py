#!/usr/bin/env python3
"""Independently check TRACE-Net NHA N6 query benchmark artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.trace_net_nha_phase6_query_benchmark_v1 import _records, _read_json, validate_phase6


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--expected-synthetic-questions", type=int, default=60)
    parser.add_argument("--expected-real-questions", type=int, default=20)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.output_dir).resolve()
    synthetic_path = root / "trace_net_nha_phase6_synthetic_results_v1.json"
    real_path = root / "trace_net_nha_phase6_real_smoke_results_v1.json"
    missing = [str(path) for path in (synthetic_path, real_path) if not path.exists()]
    if missing:
        raise FileNotFoundError("missing_nha_phase6_outputs: " + ", ".join(missing))
    result = validate_phase6(
        _records(_read_json(synthetic_path)),
        _records(_read_json(real_path)),
        expected_synthetic_questions=args.expected_synthetic_questions,
        expected_real_questions=args.expected_real_questions,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.strict and result["quality_status"] != "PASS":
        raise SystemExit("TRACE_NET_NHA_PHASE6_CHECK=FAIL")
    print("TRACE_NET_NHA_PHASE6_CHECK=PASS" if result["quality_status"] == "PASS" else "TRACE_NET_NHA_PHASE6_CHECK=WARN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
