#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_e2e_webui_final_answer_endpoint_v14 import write_json  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net E2E WebUI final answer endpoint v14 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-final-answers", type=int, default=5)
    parser.add_argument("--min-ready-final-answers", type=int, default=5)
    parser.add_argument("--min-total-citations", type=int, default=15)
    parser.add_argument("--min-endpoint-routes", type=int, default=4)
    parser.add_argument("--max-unsupported-claim-count", type=int, default=0)
    parser.add_argument("--max-graph-summary-proof-violations", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


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
    args = build_parser().parse_args()
    report_path = Path(args.report_path)
    data = json.loads(report_path.read_text(encoding="utf-8"))
    summary = data.get("summary", {})
    checks = [
        check("quality_status", data.get("quality_status"), "==", "PASS"),
        check("final_answer_count", summary.get("final_answer_count", 0), ">=", args.min_final_answers),
        check("ready_final_answer_count", summary.get("ready_final_answer_count", 0), ">=", args.min_ready_final_answers),
        check("total_citation_count", summary.get("total_citation_count", 0), ">=", args.min_total_citations),
        check("endpoint_route_count", data.get("endpoint_route_count", 0), ">=", args.min_endpoint_routes),
        check("unsupported_claim_count", summary.get("unsupported_claim_count", 0), "<=", args.max_unsupported_claim_count),
        check("graph_summary_proof_violation_count", summary.get("graph_summary_proof_violation_count", 0), "<=", args.max_graph_summary_proof_violations),
        check("answer_permission_count", summary.get("answer_permission_count", 0), "<=", args.max_answer_permission_count),
        check("source_truth_mutation_allowed_count", summary.get("source_truth_mutation_allowed_count", 0), "<=", args.max_source_truth_mutation_allowed),
        check("contract_can_answer_directly", 0, "==", 0),
        check("contract_can_prove_claims", 0, "==", 0),
        check("postgres_write_attempt_count", 0, "==", 0),
        check("qdrant_write_attempt_count", 0, "==", 0),
        check("opensearch_write_attempt_count", 0, "==", 0),
    ]
    if args.require_no_answer_permission:
        checks.append(check("require_no_answer_permission", summary.get("answer_permission_count", 0), "==", 0))
    quality_status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    data["webui_final_answer_endpoint_quality_check"] = {"quality_status": quality_status, "quality_checks": checks}
    if args.write_json:
        write_json(report_path, data)
    print("TRACE-Net E2E WebUI Final Answer Endpoint v14 Quality")
    print(f" quality_status: {quality_status}")
    for c in checks:
        prefix = "PASS" if c["passed"] else "FAIL"
        print(f" {prefix} {c['name']}: observed={c['observed']} expected={c['expected']}")
    return 0 if quality_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
