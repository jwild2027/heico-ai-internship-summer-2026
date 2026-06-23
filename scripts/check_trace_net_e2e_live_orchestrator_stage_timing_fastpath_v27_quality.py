import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27 import (
    attach_quality,
    evaluate_quality,
    read_json,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net live orchestrator stage timing + fast path v27 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-exact-search-documents", type=int, default=10)
    parser.add_argument("--min-endpoint-routes", type=int, default=4)
    parser.add_argument("--min-sample-queries", type=int, default=0)
    parser.add_argument("--min-sample-successes", type=int, default=0)
    parser.add_argument("--min-stage-timing-records", type=int, default=0)
    parser.add_argument("--min-fast-path-samples", type=int, default=0)
    parser.add_argument("--max-sample-llm-calls", type=int)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()

    path = Path(args.report_path)
    state = read_json(path)
    quality_status, checks = evaluate_quality(
        state,
        min_exact_search_documents=args.min_exact_search_documents,
        min_endpoint_routes=args.min_endpoint_routes,
        min_sample_queries=args.min_sample_queries,
        min_sample_successes=args.min_sample_successes,
        min_stage_timing_records=args.min_stage_timing_records,
        min_fast_path_samples=args.min_fast_path_samples,
        max_sample_llm_calls=args.max_sample_llm_calls,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    attach_quality(state, quality_status, checks)
    print("TRACE-Net E2E Live Orchestrator Stage Timing + Fast Path v27 Quality")
    print(f" quality_status: {quality_status}")
    for check in checks:
        status = "PASS" if check.get("passed") else "FAIL"
        print(f" {status} {check['name']}: observed={check['observed']} expected={check['op']} {check['expected']}")
    if args.write_json:
        write_json(path, state)
    return 0 if quality_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
