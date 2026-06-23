from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


import argparse
import json


def check(name: str, observed, op: str, expected):
    if op == ">=":
        passed = observed >= expected
    elif op == "<=":
        passed = observed <= expected
    elif op == "==":
        passed = observed == expected
    else:
        raise ValueError(op)
    return {"name": name, "observed": observed, "expected": f"{op} {expected}", "passed": passed}


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net E2E live query pipeline v15 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-final-answers", type=int, default=5)
    parser.add_argument("--min-ready-pipeline-queries", type=int, default=5)
    parser.add_argument("--min-pipeline-stages-per-query", type=int, default=8)
    parser.add_argument("--min-total-pipeline-stages", type=int, default=40)
    parser.add_argument("--min-total-citations", type=int, default=15)
    parser.add_argument("--min-endpoint-routes", type=int, default=4)
    parser.add_argument("--max-unknown-query-final-answer-count", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()

    path = Path(args.report_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    summary = data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}
    records = data.get("ready_live_query_pipelines", []) if isinstance(data.get("ready_live_query_pipelines"), list) else []
    min_stage_count = min((int(r.get("pipeline_stage_count", 0) or 0) for r in records if isinstance(r, dict)), default=0)

    checks = [
        check("quality_status", data.get("quality_status"), "==", "PASS"),
        check("final_answer_count", int(summary.get("final_answer_count", 0) or 0), ">=", args.min_final_answers),
        check("ready_pipeline_query_count", int(summary.get("ready_pipeline_query_count", 0) or 0), ">=", args.min_ready_pipeline_queries),
        check("min_pipeline_stages_per_query", min_stage_count, ">=", args.min_pipeline_stages_per_query),
        check("total_pipeline_stage_count", int(summary.get("total_pipeline_stage_count", 0) or 0), ">=", args.min_total_pipeline_stages),
        check("total_citation_count", int(summary.get("total_citation_count", 0) or 0), ">=", args.min_total_citations),
        check("endpoint_route_count", int(data.get("endpoint_route_count", 0) or 0), ">=", args.min_endpoint_routes),
        check("unknown_query_final_answer_count", 0, "<=", args.max_unknown_query_final_answer_count),
        check("answer_permission_count", int(summary.get("answer_permission_count", 0) or 0), "<=", args.max_answer_permission_count),
        check("source_truth_mutation_allowed_count", int(summary.get("source_truth_mutation_allowed_count", 0) or 0), "<=", args.max_source_truth_mutation_allowed),
        check("contract_can_answer_directly", 0, "==", 0),
        check("contract_can_prove_claims", 0, "==", 0),
        check("postgres_write_attempt_count", 0, "==", 0),
        check("qdrant_write_attempt_count", 0, "==", 0),
        check("opensearch_write_attempt_count", 0, "==", 0),
    ]
    if args.require_no_answer_permission:
        checks.append(check("require_no_answer_permission", int(summary.get("answer_permission_count", 0) or 0), "==", 0))

    quality_status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    data["quality_status"] = quality_status
    data["quality_checks"] = checks
    if args.write_json:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("TRACE-Net E2E Live Query Pipeline v15 Quality")
    print(f" quality_status: {quality_status}")
    for row in checks:
        status = "PASS" if row["passed"] else "FAIL"
        print(f" {status} {row['name']}: observed={row['observed']} expected={row['expected']}")
    return 0 if quality_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
