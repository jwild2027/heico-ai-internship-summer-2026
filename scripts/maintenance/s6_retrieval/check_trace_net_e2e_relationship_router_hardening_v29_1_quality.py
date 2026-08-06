from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
from tiff.trace_net_e2e_relationship_router_hardening_v29_1 import check_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Check TRACE-Net relationship router hardening v29.1 quality.")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--min-exact-search-documents", type=int, default=10)
    parser.add_argument("--min-endpoint-routes", type=int, default=4)
    parser.add_argument("--min-sample-queries", type=int, default=0)
    parser.add_argument("--min-sample-successes", type=int, default=0)
    parser.add_argument("--min-metadata-count-samples", type=int, default=0)
    parser.add_argument("--max-bad-broad-fallback-count", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()

    result = check_report(
        report_path=args.report_path,
        min_exact_search_documents=args.min_exact_search_documents,
        min_endpoint_routes=args.min_endpoint_routes,
        min_sample_queries=args.min_sample_queries,
        min_sample_successes=args.min_sample_successes,
        min_metadata_count_samples=args.min_metadata_count_samples,
        max_bad_broad_fallback_count=args.max_bad_broad_fallback_count,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
        write_json=args.write_json,
    )
    print("TRACE-Net E2E Relationship Router Hardening v29.1 Quality")
    print(f" quality_status: {result['quality_status']}")
    for c in result["quality_checks"]:
        status = "PASS" if c["passed"] else "FAIL"
        print(f" {status} {c['name']}: observed={c['observed']} expected={c['op']} {c['expected']}")
    if result["quality_status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
