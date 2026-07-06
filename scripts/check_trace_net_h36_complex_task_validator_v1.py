#!/usr/bin/env python3
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_h36_complex_task_validator_v1 import check_complex_task_validator


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--validator", required=True)
    p.add_argument("--min-records", type=int, default=5)
    p.add_argument("--min-contract-pass", type=int, default=4)
    p.add_argument("--max-bad", type=int, default=0)
    p.add_argument("--max-fallback-used", type=int, default=0)
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    args = p.parse_args()
    result = check_complex_task_validator(**vars(args))
    print("status=TRACE_NET_H36_COMPLEX_TASK_VALIDATOR_CHECKED")
    for k in ["quality_status", "record_count", "contract_pass_count", "review_count", "bad_count", "fallback_used_count", "unsafe_finding_count", "answer_permission_count", "write_attempt_count"]:
        print(f"{k}={result[k]}")
    if result["quality_failures"]:
        print("quality_failures=" + ",".join(result["quality_failures"]))
    return 0 if result["quality_status"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
