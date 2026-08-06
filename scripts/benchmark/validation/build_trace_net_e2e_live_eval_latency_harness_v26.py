from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_live_eval_latency_harness_v26 import (
    build_report,
    load_eval_queries_from_jsonl,
    standard_eval_queries,
)


def main() -> int:
    p = argparse.ArgumentParser(description="Build TRACE-Net live eval + latency harness v26")
    p.add_argument("--endpoint-base-url", default="http://127.0.0.1:8021/v1")
    p.add_argument("--model", default="trace-net-e2e-live-orchestrator-gemma-v25")
    p.add_argument("--api-key", default="trace-net-local")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--request-timeout", type=float, default=300.0)
    p.add_argument("--include-standard-eval-queries", action="store_true")
    p.add_argument("--eval-query-jsonl")
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
    p.add_argument("--quality", action="store_true")
    args = p.parse_args()

    queries = []
    if args.include_standard_eval_queries or not args.eval_query_jsonl:
        queries.extend(standard_eval_queries())
    if args.eval_query_jsonl:
        queries.extend(load_eval_queries_from_jsonl(Path(args.eval_query_jsonl)))

    report = build_report(
        endpoint_base_url=args.endpoint_base_url,
        model=args.model,
        output_dir=Path(args.output_dir),
        queries=queries,
        request_timeout=args.request_timeout,
        api_key=args.api_key,
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
    print("TRACE-Net E2E Live Eval + Latency Harness v26")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for k in [
        "eval_query_count",
        "success_count",
        "false_positive_count",
        "false_negative_count",
        "unsupported_claim_count",
        "llm_call_error_count",
        "audit_only_count",
        "final_answer_count",
        "avg_latency_ms",
        "max_latency_ms",
        "total_latency_ms",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {k}: {report.get(k)}")
    print(f" report_path: {report['report_path']}")
    print(f" records_jsonl_path: {report['records_jsonl_path']}")
    print(f" inspect_md_path: {report['inspect_md_path']}")
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
