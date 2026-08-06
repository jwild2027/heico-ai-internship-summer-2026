#!/usr/bin/env python3
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_engineering_engram_answer_runner_retrieval_bridge_v1 import check_answer_runner_retrieval_bridge_manifest


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check TRACE-Net H23 Engram answer-runner retrieval bridge.")
    p.add_argument("--bridge", required=True)
    p.add_argument("--min-bridge-records", type=int, default=6)
    p.add_argument("--min-task-types", type=int, default=5)
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = check_answer_runner_retrieval_bridge_manifest(**vars(args))
    s = result.get("summary", {})
    print("status=" + str(result.get("status")))
    print("quality_status=" + str(result.get("quality_status")))
    print("bridge_record_count=" + str(s.get("bridge_record_count")))
    print("task_type_count=" + str(s.get("task_type_count")))
    print("target_answer_runner_question_count=" + str(s.get("target_answer_runner_question_count")))
    print("unsafe_finding_count=" + str(s.get("unsafe_finding_count")))
    print("answer_permission_count=" + str(s.get("answer_permission_count")))
    print("write_attempt_count=" + str(s.get("write_attempt_count")))
    if result.get("quality_failures"):
        print("quality_failures=" + json.dumps(result.get("quality_failures")))
    return 0 if result.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
