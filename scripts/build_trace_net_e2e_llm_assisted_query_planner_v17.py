from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_llm_assisted_query_planner_v17 import build_report, load_json, write_report_files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build TRACE-Net E2E LLM-assisted query planner v17 artifact.")
    parser.add_argument("--live-dynamic-fallback", required=True)
    parser.add_argument("--page-context-v2", required=True)
    parser.add_argument("--leiden-communities", required=True)
    parser.add_argument("--community-navigation-metadata-bridge", required=True)
    parser.add_argument("--route-dispatch-manifest", required=True)
    parser.add_argument("--table-exact-search-adapter", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--min-query-plans", type=int, default=5)
    parser.add_argument("--min-validated-query-plans", type=int, default=5)
    parser.add_argument("--min-plans-with-v2-summary-guidance", type=int, default=5)
    parser.add_argument("--min-plans-with-leiden-guidance", type=int, default=5)
    parser.add_argument("--min-plans-with-source-truth-fields", type=int, default=5)
    parser.add_argument("--min-allowed-tunnel-validations", type=int, default=20)
    parser.add_argument("--max-invalid-tunnel-count", type=int, default=0)
    parser.add_argument("--max-proof-authority-violations", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        live_dynamic_fallback=load_json(args.live_dynamic_fallback, {}),
        page_context_v2=load_json(args.page_context_v2, {}),
        leiden_communities=load_json(args.leiden_communities, {}),
        community_navigation_metadata_bridge=load_json(args.community_navigation_metadata_bridge, {}),
        route_dispatch_manifest=load_json(args.route_dispatch_manifest, {}),
        table_exact_search_adapter=load_json(args.table_exact_search_adapter, {}),
        min_query_plans=args.min_query_plans,
    )

    # Re-evaluate against CLI thresholds by importing threshold helpers lazily.
    from tiff.trace_net_e2e_llm_assisted_query_planner_v17 import QualityThresholds, DEFAULT_STATUS_READY, DEFAULT_STATUS_NEEDS_REPAIR, evaluate_quality

    thresholds = QualityThresholds(
        min_query_plans=args.min_query_plans,
        min_validated_query_plans=args.min_validated_query_plans,
        min_plans_with_v2_summary_guidance=args.min_plans_with_v2_summary_guidance,
        min_plans_with_leiden_guidance=args.min_plans_with_leiden_guidance,
        min_plans_with_source_truth_fields=args.min_plans_with_source_truth_fields,
        min_allowed_tunnel_validations=args.min_allowed_tunnel_validations,
        max_invalid_tunnel_count=args.max_invalid_tunnel_count,
        max_proof_authority_violations=args.max_proof_authority_violations,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    quality = evaluate_quality(report, thresholds)
    report["quality_status"] = quality["quality_status"]
    report["quality_checks"] = quality["quality_checks"]
    report["status"] = DEFAULT_STATUS_READY if quality["quality_status"] == "PASS" else DEFAULT_STATUS_NEEDS_REPAIR

    paths = write_report_files(report, args.output_dir)
    print("TRACE-Net E2E LLM-Assisted Query Planner v17")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in (
        "query_plan_count",
        "validated_query_plan_count",
        "plans_with_v2_summary_guidance_count",
        "plans_with_leiden_guidance_count",
        "plans_with_source_truth_fields_count",
        "allowed_tunnel_validation_count",
        "invalid_tunnel_count",
        "proof_authority_violation_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ):
        print(f" {key}: {report.get(key, 0)}")
    for key, value in paths.items():
        print(f" {key}: {value}")
    if args.quality and report["quality_status"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
