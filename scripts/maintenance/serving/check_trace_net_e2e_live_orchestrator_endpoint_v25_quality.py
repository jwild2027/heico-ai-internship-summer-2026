import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_live_orchestrator_endpoint_v25 import evaluate_quality, read_json, write_json


def parse_args():
    p = argparse.ArgumentParser(description="Check TRACE-Net E2E Live Orchestrator Endpoint v25 quality.")
    p.add_argument("--report-path", required=True)
    p.add_argument("--min-exact-search-documents", type=int, default=10)
    p.add_argument("--min-endpoint-routes", type=int, default=4)
    p.add_argument("--min-sample-queries", type=int, default=5)
    p.add_argument("--min-sample-successes", type=int, default=5)
    p.add_argument("--max-unsupported-claim-count", type=int, default=0)
    p.add_argument("--max-llm-call-errors", type=int, default=0)
    p.add_argument("--max-answer-permission-count", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--write-json", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    state = read_json(Path(args.report_path))
    quality_status, checks = evaluate_quality(
        state,
        min_exact_search_documents=args.min_exact_search_documents,
        min_endpoint_routes=args.min_endpoint_routes,
        min_sample_queries=args.min_sample_queries,
        min_sample_successes=args.min_sample_successes,
        max_unsupported_claim_count=args.max_unsupported_claim_count,
        max_llm_call_errors=args.max_llm_call_errors,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    out = {"quality_status": quality_status, "quality_checks": checks}
    if args.write_json:
        write_json(Path(args.report_path).parent / "trace_net_e2e_live_orchestrator_endpoint_v25_quality.json", out)
    print("TRACE-Net E2E Live Orchestrator Endpoint v25 Quality")
    print(f" quality_status: {quality_status}")
    for check in checks:
        status = "PASS" if check["passed"] else "FAIL"
        print(f" {status} {check['name']}: observed={check['observed']} expected={check['op']} {check['expected']}")
    return 0 if quality_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
