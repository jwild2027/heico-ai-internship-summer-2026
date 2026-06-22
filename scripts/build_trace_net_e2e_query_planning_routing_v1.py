from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_query_planning_routing_v1 import (  # noqa: E402
    QualityThresholds,
    build_query_planning_routing,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net E2E query planning/routing v1 artifact.")
    parser.add_argument("--e2e-query-input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--summary-artifact", action="append", default=[], help="Optional graph/page/table summary JSON file or directory. May be repeated.")
    parser.add_argument("--allow-missing-summary-artifacts", action="store_true")
    parser.add_argument("--max-summary-tunnels-per-query", type=int, default=3)

    parser.add_argument("--min-source-query-records", type=int, default=1)
    parser.add_argument("--min-route-plans", type=int, default=1)
    parser.add_argument("--min-routeable-plans", type=int, default=1)
    parser.add_argument("--min-plans-with-graph-tunnels", type=int, default=1)
    parser.add_argument("--min-plans-with-summary-tunnels", type=int, default=1)
    parser.add_argument("--min-plans-with-table-tunnels", type=int, default=1)
    parser.add_argument("--min-total-tunnels", type=int, default=1)
    parser.add_argument("--min-unique-tunnel-types", type=int, default=2)
    parser.add_argument("--min-planned-retrieval-steps", type=int, default=1)
    parser.add_argument("--max-schema-missing-required-key-records", type=int, default=0)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-source-query-input-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args()

    thresholds = QualityThresholds(
        min_source_query_records=args.min_source_query_records,
        min_route_plans=args.min_route_plans,
        min_routeable_plans=args.min_routeable_plans,
        min_plans_with_graph_tunnels=args.min_plans_with_graph_tunnels,
        min_plans_with_summary_tunnels=args.min_plans_with_summary_tunnels,
        min_plans_with_table_tunnels=args.min_plans_with_table_tunnels,
        min_total_tunnels=args.min_total_tunnels,
        min_unique_tunnel_types=args.min_unique_tunnel_types,
        min_planned_retrieval_steps=args.min_planned_retrieval_steps,
        max_schema_missing_required_key_records=args.max_schema_missing_required_key_records,
        max_unsafe_records=args.max_unsafe_records,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_source_query_input_quality_pass=args.require_source_query_input_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    report = build_query_planning_routing(
        e2e_query_input_path=args.e2e_query_input,
        output_dir=args.output_dir,
        summary_artifact_paths=args.summary_artifact,
        allow_missing_summary_artifacts=args.allow_missing_summary_artifacts,
        max_summary_tunnels_per_query=args.max_summary_tunnels_per_query,
        thresholds=thresholds,
    )

    summary = report["summary"]
    print("TRACE-Net E2E Query Planning Routing v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "e2e_query_planning_routing_status",
        "source_query_input_record_count",
        "query_route_plan_count",
        "routeable_query_route_plan_count",
        "plans_with_graph_tunnel_count",
        "plans_with_summary_tunnel_count",
        "plans_with_table_tunnel_count",
        "total_query_tunnel_count",
        "unique_tunnel_type_count",
        "planned_retrieval_step_count",
        "loaded_summary_artifact_count",
        "summary_hint_count",
        "schema_missing_required_key_record_count",
        "unsafe_query_route_plan_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "opensearch_upload_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {report.get('report_path')}")
    print(f" route_plans_jsonl_path: {report.get('route_plans_jsonl_path')}")
    print(f" inspect_md_path: {report.get('inspect_md_path')}")
    return 0 if (not args.quality or report["quality_status"] == "PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
