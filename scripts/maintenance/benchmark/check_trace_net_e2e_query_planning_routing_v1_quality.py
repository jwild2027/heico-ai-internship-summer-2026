from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_query_planning_routing_v1 import (  # noqa: E402
    QUALITY_PASS,
    QualityThresholds,
    evaluate_quality,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net E2E query planning/routing v1 quality.")
    parser.add_argument("--report-path", required=True)
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
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()

    report_path = Path(args.report_path)
    data = json.loads(report_path.read_text(encoding="utf-8"))
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
    status, checks = evaluate_quality(data, thresholds)
    print("TRACE-Net E2E Query Planning Routing v1 Quality")
    print(f" quality_status: {status}")
    for check in checks:
        label = "PASS" if check["passed"] else "FAIL"
        print(f" {label} {check['name']}: observed={check['observed']} expected={check['expected']}")

    if args.write_json:
        data["quality_status"] = status
        data["quality_checks"] = checks
        write_json(report_path, data)
        quality_path = report_path.with_name("trace_net_e2e_query_planning_routing_v1_quality.json")
        write_json(quality_path, {"quality_status": status, "quality_checks": checks})
    return 0 if status == QUALITY_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
