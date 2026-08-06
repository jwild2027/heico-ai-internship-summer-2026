from __future__ import annotations

import argparse
from tiff.trace_net_engineering_engram_postgres_feedback_ledger_v1 import check_feedback_ledger_manifest


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check TRACE-Net Engineering Engram Postgres feedback ledger v1")
    p.add_argument("--feedback-ledger", required=True)
    p.add_argument("--min-feedback-records", type=int, default=5)
    p.add_argument("--min-candidate-records", type=int, default=5)
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = check_feedback_ledger_manifest(
        ledger=args.feedback_ledger,
        min_feedback_records=args.min_feedback_records,
        min_candidate_records=args.min_candidate_records,
        require_quality_pass=args.require_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
        max_unsafe=args.max_unsafe,
        max_write_attempts=args.max_write_attempts,
    )
    print("status=" + result["status"])
    print("quality_status=" + result["quality_status"])
    print("feedback_record_count=" + str(result["feedback_record_count"]))
    print("candidate_record_count=" + str(result["candidate_record_count"]))
    print("unsafe_finding_count=" + str(result["unsafe_finding_count"]))
    print("answer_permission_count=" + str(result["answer_permission_count"]))
    print("write_attempt_count=" + str(result["write_attempt_count"]))
    if result.get("quality_failures"):
        print("quality_failures=" + str(result["quality_failures"]))
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
