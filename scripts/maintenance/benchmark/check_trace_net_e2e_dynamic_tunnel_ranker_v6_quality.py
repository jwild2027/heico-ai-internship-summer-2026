#!/usr/bin/env python3
from pathlib import Path
import argparse
import json


def main() -> int:
    p = argparse.ArgumentParser(description="Check TRACE-Net E2E dynamic tunnel ranker v6 quality.")
    p.add_argument("--report-path", required=True, type=Path)
    p.add_argument("--min-rank-plans", type=int, default=5)
    p.add_argument("--min-ready-rank-plans", type=int, default=5)
    p.add_argument("--min-total-ranked-evidence", type=int, default=10)
    p.add_argument("--min-unique-contribution-tunnels", type=int, default=4)
    p.add_argument("--min-plans-with-graph-or-summary-contribution", type=int, default=1)
    p.add_argument("--min-plans-with-table-contribution", type=int, default=5)
    p.add_argument("--max-answer-permission-count", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--write-json", action="store_true")
    args = p.parse_args()

    data = json.loads(args.report_path.read_text(encoding="utf-8"))
    s = data.get("summary", {})
    checks = [
        ("quality_status", data.get("quality_status"), "==", "PASS"),
        ("rank_plan_count", int(s.get("rank_plan_count", 0)), ">=", args.min_rank_plans),
        ("ready_rank_plan_count", int(s.get("ready_rank_plan_count", 0)), ">=", args.min_ready_rank_plans),
        ("total_ranked_evidence_count", int(s.get("total_ranked_evidence_count", 0)), ">=", args.min_total_ranked_evidence),
        ("unique_contribution_tunnel_count", int(s.get("unique_contribution_tunnel_count", 0)), ">=", args.min_unique_contribution_tunnels),
        ("plans_with_graph_or_summary_contribution_count", int(s.get("plans_with_graph_or_summary_contribution_count", 0)), ">=", args.min_plans_with_graph_or_summary_contribution),
        ("plans_with_table_contribution_count", int(s.get("plans_with_table_contribution_count", 0)), ">=", args.min_plans_with_table_contribution),
        ("answer_permission_count", int(s.get("answer_permission_count", 0)), "<=", args.max_answer_permission_count),
        ("source_truth_mutation_allowed_count", int(s.get("source_truth_mutation_allowed_count", 0)), "<=", args.max_source_truth_mutation_allowed),
    ]
    rows = []
    ok_all = True
    print("TRACE-Net E2E Dynamic Tunnel Ranker v6 Quality")
    for name, observed, op, expected in checks:
        if op == "==":
            ok = observed == expected
        elif op == ">=":
            ok = observed >= expected
        elif op == "<=":
            ok = observed <= expected
        else:
            ok = False
        ok_all = ok_all and ok
        print(f" {'PASS' if ok else 'FAIL'} {name}: observed={observed} expected={op} {expected}")
        rows.append({"name": name, "observed": observed, "expected": f"{op} {expected}", "passed": ok})
    if args.write_json:
        out = args.report_path.with_name(args.report_path.stem + "_quality.json")
        out.write_text(json.dumps({"quality_status": "PASS" if ok_all else "FAIL", "quality_checks": rows}, indent=2) + "\n", encoding="utf-8")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
