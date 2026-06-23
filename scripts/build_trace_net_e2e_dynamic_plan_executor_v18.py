from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse

from tiff.trace_net_e2e_dynamic_plan_executor_v18 import build_report, quality_check_report, write_report_files


def main() -> int:
    ap = argparse.ArgumentParser(description="Build TRACE-Net E2E Dynamic Plan Executor v18")
    ap.add_argument("--query-planner", required=True)
    ap.add_argument("--table-exact-search-adapter", required=True)
    ap.add_argument("--page-context-v2")
    ap.add_argument("--leiden-communities")
    ap.add_argument("--community-navigation-metadata-bridge")
    ap.add_argument("--route-dispatch-manifest")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--high-degree-threshold", type=int, default=25)
    ap.add_argument("--max-pages-per-community", type=int, default=25)
    ap.add_argument("--min-query-plans", type=int, default=1)
    ap.add_argument("--min-ready-executions", type=int, default=1)
    ap.add_argument("--min-source-truth-evidence", type=int, default=1)
    ap.add_argument("--min-graph-guidance-records", type=int, default=0)
    ap.add_argument("--min-capped-result-disclosures", type=int, default=0)
    ap.add_argument("--max-graph-proof-authority-violations", type=int, default=0)
    ap.add_argument("--max-summary-proof-authority-violations", type=int, default=0)
    ap.add_argument("--max-answer-permission-count", type=int, default=0)
    ap.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    ap.add_argument("--require-no-answer-permission", action="store_true")
    ap.add_argument("--quality", action="store_true")
    args = ap.parse_args()

    report = build_report(
        query_planner=args.query_planner,
        table_exact_search_adapter=args.table_exact_search_adapter,
        page_context_v2=args.page_context_v2,
        leiden_communities=args.leiden_communities,
        community_navigation_metadata_bridge=args.community_navigation_metadata_bridge,
        route_dispatch_manifest=args.route_dispatch_manifest,
        top_k=args.top_k,
        high_degree_threshold=args.high_degree_threshold,
        max_pages_per_community=args.max_pages_per_community,
    )
    if args.quality:
        status, checks = quality_check_report(
            report,
            min_query_plans=args.min_query_plans,
            min_ready_executions=args.min_ready_executions,
            min_source_truth_evidence=args.min_source_truth_evidence,
            min_graph_guidance_records=args.min_graph_guidance_records,
            min_capped_result_disclosures=args.min_capped_result_disclosures,
            max_graph_proof_authority_violations=args.max_graph_proof_authority_violations,
            max_summary_proof_authority_violations=args.max_summary_proof_authority_violations,
            max_answer_permission_count=args.max_answer_permission_count,
            max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
            require_no_answer_permission=args.require_no_answer_permission,
        )
        report["quality_status"] = status
        report["quality_checks"] = checks
        if status != "PASS":
            report["status"] = "E2E_DYNAMIC_PLAN_EXECUTOR_NEEDS_REPAIR"
    paths = write_report_files(report, args.output_dir)
    print("TRACE-Net E2E Dynamic Plan Executor v18")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in ["query_plan_count", "execution_count", "ready_execution_count", "source_truth_evidence_count", "graph_guidance_count", "summary_guidance_count", "capped_result_count", "high_degree_node_execution_count", "graph_proof_authority_violation_count", "summary_proof_authority_violation_count", "answer_permission_count", "source_truth_mutation_allowed_count"]:
        print(f" {key}: {report.get(key)}")
    for k, v in paths.items():
        print(f" {k}: {v}")
    return 0 if report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
