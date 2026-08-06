from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_live_eval_latency_harness_v26 import quality_checks, quality_status, write_json


def main() -> int:
    p = argparse.ArgumentParser(description="Check TRACE-Net live eval + latency harness v26 quality")
    p.add_argument("--report-path", required=True)
    p.add_argument("--min-eval-queries", type=int, default=1)
    p.add_argument("--min-success-count", type=int, default=1)
    p.add_argument("--min-latency-records", type=int, default=1)
    p.add_argument("--max-false-positive-count", type=int, default=0)
    p.add_argument("--max-false-negative-count", type=int, default=0)
    p.add_argument("--max-unsupported-claim-count", type=int, default=0)
    p.add_argument("--max-llm-call-errors", type=int, default=0)
    p.add_argument("--max-answer-permission-count", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--write-json", action="store_true")
    args = p.parse_args()

    path = Path(args.report_path)
    report = json.loads(path.read_text(encoding="utf-8"))
    checks = quality_checks(
        report,
        min_eval_queries=args.min_eval_queries,
        min_success_count=args.min_success_count,
        min_latency_records=args.min_latency_records,
        max_false_positive_count=args.max_false_positive_count,
        max_false_negative_count=args.max_false_negative_count,
        max_unsupported_claim_count=args.max_unsupported_claim_count,
        max_llm_call_errors=args.max_llm_call_errors,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    status = quality_status(checks)
    report["quality_checks"] = checks
    report["quality_status"] = status
    if args.write_json:
        write_json(path, report)

    print("TRACE-Net E2E Live Eval + Latency Harness v26 Quality")
    print(f" quality_status: {status}")
    for c in checks:
        prefix = "PASS" if c["passed"] else "FAIL"
        print(f" {prefix} {c['name']}: observed={c['observed']} expected={c['op']} {c['expected']}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
