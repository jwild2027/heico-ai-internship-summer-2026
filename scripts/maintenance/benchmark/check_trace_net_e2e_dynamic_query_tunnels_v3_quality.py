#!/usr/bin/env python3
"""Quality check for TRACE-Net E2E dynamic query tunnels v3."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-query-tunnel-plans", type=int, default=5)
    parser.add_argument("--min-ready-query-tunnel-plans", type=int, default=5)
    parser.add_argument("--min-total-tunnels", type=int, default=20)
    parser.add_argument("--min-unique-tunnel-types", type=int, default=3)
    parser.add_argument("--min-plans-with-table-tunnels", type=int, default=5)
    parser.add_argument("--min-plans-with-graph-or-summary-tunnels", type=int, default=1)
    parser.add_argument("--min-available-artifacts", type=int, default=3)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = Path(args.report_path)
    data = json.loads(report_path.read_text(encoding="utf-8"))
    summary = data.get("summary", {})

    checks = []

    def add(name: str, observed, expected: str, passed: bool) -> None:
        checks.append({"name": name, "observed": observed, "expected": expected, "passed": bool(passed)})

    checks_to_run = [
        ("quality_status", data.get("quality_status"), "== PASS", data.get("quality_status") == "PASS"),
        ("query_tunnel_plan_count", summary.get("query_tunnel_plan_count", 0), f">= {args.min_query_tunnel_plans}", int(summary.get("query_tunnel_plan_count", 0)) >= args.min_query_tunnel_plans),
        ("ready_query_tunnel_plan_count", summary.get("ready_query_tunnel_plan_count", 0), f">= {args.min_ready_query_tunnel_plans}", int(summary.get("ready_query_tunnel_plan_count", 0)) >= args.min_ready_query_tunnel_plans),
        ("total_tunnel_count", summary.get("total_tunnel_count", 0), f">= {args.min_total_tunnels}", int(summary.get("total_tunnel_count", 0)) >= args.min_total_tunnels),
        ("unique_tunnel_type_count", summary.get("unique_tunnel_type_count", 0), f">= {args.min_unique_tunnel_types}", int(summary.get("unique_tunnel_type_count", 0)) >= args.min_unique_tunnel_types),
        ("plans_with_table_tunnel_count", summary.get("plans_with_table_tunnel_count", 0), f">= {args.min_plans_with_table_tunnels}", int(summary.get("plans_with_table_tunnel_count", 0)) >= args.min_plans_with_table_tunnels),
        ("plans_with_graph_or_summary_tunnel_count", summary.get("plans_with_graph_or_summary_tunnel_count", 0), f">= {args.min_plans_with_graph_or_summary_tunnels}", int(summary.get("plans_with_graph_or_summary_tunnel_count", 0)) >= args.min_plans_with_graph_or_summary_tunnels),
        ("available_artifact_count", summary.get("available_artifact_count", 0), f">= {args.min_available_artifacts}", int(summary.get("available_artifact_count", 0)) >= args.min_available_artifacts),
        ("unsafe_record_count", summary.get("unsafe_record_count", 0), f"<= {args.max_unsafe_records}", int(summary.get("unsafe_record_count", 0)) <= args.max_unsafe_records),
        ("answer_permission_count", summary.get("answer_permission_count", 0), f"<= {args.max_answer_permission_count}", int(summary.get("answer_permission_count", 0)) <= args.max_answer_permission_count),
        ("source_truth_mutation_allowed_count", summary.get("source_truth_mutation_allowed_count", 0), f"<= {args.max_source_truth_mutation_allowed}", int(summary.get("source_truth_mutation_allowed_count", 0)) <= args.max_source_truth_mutation_allowed),
    ]
    for row in checks_to_run:
        add(*row)

    if args.require_no_answer_permission:
        add("contract_answer_permission", summary.get("answer_permission_count", 0), "== 0", int(summary.get("answer_permission_count", 0)) == 0)
        add("contract_can_answer_directly", summary.get("can_answer_directly_count", 0), "== 0", int(summary.get("can_answer_directly_count", 0)) == 0)
        add("contract_can_prove_claims", summary.get("can_prove_claims_count", 0), "== 0", int(summary.get("can_prove_claims_count", 0)) == 0)

    quality = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    print("TRACE-Net E2E Dynamic Query Tunnels v3 Quality")
    print(f" quality_status: {quality}")
    for check in checks:
        mark = "PASS" if check["passed"] else "FAIL"
        print(f" {mark} {check['name']}: observed={check['observed']} expected={check['expected']}")

    if args.write_json:
        out = report_path.with_name("trace_net_e2e_dynamic_query_tunnels_v3_quality.json")
        out.write_text(json.dumps({"quality_status": quality, "checks": checks}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if quality == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
