from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse

from tiff.trace_net_e2e_live_dynamic_fallback_v16 import check_quality_report, read_json, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net E2E live dynamic fallback v16 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-existing-pipeline-queries", type=int, default=5)
    parser.add_argument("--min-exact-search-documents", type=int, default=10)
    parser.add_argument("--min-dynamic-fallback-probes", type=int, default=3)
    parser.add_argument("--min-ready-dynamic-fallback-probes", type=int, default=3)
    parser.add_argument("--min-total-citations", type=int, default=15)
    parser.add_argument("--min-endpoint-routes", type=int, default=4)
    parser.add_argument("--max-unsupported-claim-count", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()

    report = read_json(args.report_path)
    quality = check_quality_report(
        report,
        min_existing_pipeline_queries=args.min_existing_pipeline_queries,
        min_exact_search_documents=args.min_exact_search_documents,
        min_dynamic_fallback_probes=args.min_dynamic_fallback_probes,
        min_ready_dynamic_fallback_probes=args.min_ready_dynamic_fallback_probes,
        min_total_citations=args.min_total_citations,
        min_endpoint_routes=args.min_endpoint_routes,
        max_unsupported_claim_count=args.max_unsupported_claim_count,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    if args.write_json:
        out = Path(args.report_path).with_name(Path(args.report_path).stem + "_quality.json")
        write_json(out, quality)
    print("TRACE-Net E2E Live Dynamic Fallback v16 Quality")
    print(f" quality_status: {quality.get('quality_status')}")
    for check in quality.get("quality_checks", []):
        status = "PASS" if check.get("passed") else "FAIL"
        print(f" {status} {check.get('name')}: observed={check.get('observed')} expected={check.get('expected')}")
    return 0 if quality.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
