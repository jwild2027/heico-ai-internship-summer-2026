#!/usr/bin/env python
from pathlib import Path
import argparse
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tiff.trace_net_engineering_engram_unified_runtime_gate_v1 import check_unified_runtime_gate


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--unified-runtime-gate", required=True)
    p.add_argument("--min-runtime-records", type=int, default=5)
    p.add_argument("--min-pass-or-expected", type=int, default=5)
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--require-connections", action="store_true")
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    args = p.parse_args(argv)
    result = check_unified_runtime_gate(**vars(args))
    print("status=" + str(result.get("status")))
    print("quality_status=" + str(result.get("quality_status")))
    print("runtime_record_count=" + str(result.get("runtime_record_count")))
    print("runtime_pass_or_expected_count=" + str(result.get("runtime_pass_or_expected_count")))
    print("unsafe_finding_count=" + str(result.get("unsafe_finding_count")))
    print("answer_permission_count=" + str(result.get("answer_permission_count")))
    print("write_attempt_count=" + str(result.get("write_attempt_count")))
    if result.get("quality_failures"):
        print("quality_failures=" + str(result.get("quality_failures")))
    return 0 if result.get("quality_status") == "PASS" else 1

if __name__ == '__main__':
    raise SystemExit(main())
