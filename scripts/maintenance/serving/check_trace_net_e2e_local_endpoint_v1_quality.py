#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def check(name: str, observed, op: str, expected):
    if op == ">=":
        passed = observed >= expected
    elif op == "<=":
        passed = observed <= expected
    elif op == "==":
        passed = observed == expected
    elif op == "is":
        passed = observed is expected
    else:
        raise ValueError(op)
    return {"name": name, "observed": observed, "operator": op, "expected": expected, "passed": bool(passed)}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Check TRACE-Net E2E local endpoint v1 quality")
    p.add_argument("--report-path", default="local_data/organization/trace_net/e2e_local_endpoint/trace_net_e2e_local_endpoint_v1.json")
    p.add_argument("--min-api-responses", type=int, default=5)
    p.add_argument("--min-citation-backed-responses", type=int, default=4)
    p.add_argument("--min-total-citations", type=int, default=10)
    p.add_argument("--min-endpoint-routes", type=int, default=4)
    p.add_argument("--max-unsafe-records", type=int, default=0)
    p.add_argument("--max-answer-permission-count", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--require-source-api-wrapper-quality-pass", action="store_true")
    p.add_argument("--require-openai-chat-route", action="store_true")
    p.add_argument("--require-native-ask-route", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--write-json", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    report_path = Path(args.report_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    summary = report.get("summary", {})
    contract = report.get("endpoint_contract", {})
    routes = report.get("endpoint_routes", [])
    route_paths = {r.get("path") for r in routes if isinstance(r, dict)}
    checks = [
        check("quality_status", report.get("quality_status"), "==", "PASS"),
        check("api_response_count", int(summary.get("api_response_count", 0)), ">=", args.min_api_responses),
        check("citation_backed_response_count", int(summary.get("citation_backed_response_count", 0)), ">=", args.min_citation_backed_responses),
        check("total_citation_count", int(summary.get("total_citation_count", 0)), ">=", args.min_total_citations),
        check("endpoint_route_count", int(summary.get("endpoint_route_count", 0)), ">=", args.min_endpoint_routes),
        check("ready_for_open_webui_smoke", bool(summary.get("ready_for_open_webui_smoke", False)), "is", True),
        check("unsafe_record_count", 0, "<=", args.max_unsafe_records),
        check("answer_permission_count", int(summary.get("answer_permission_count", 0)), "<=", args.max_answer_permission_count),
        check("source_truth_mutation_allowed_count", int(summary.get("source_truth_mutation_allowed_count", 0)), "<=", args.max_source_truth_mutation_allowed),
        check("can_answer_directly_count", int(summary.get("can_answer_directly_count", 0)), "==", 0),
        check("can_prove_claims_count", int(summary.get("can_prove_claims_count", 0)), "==", 0),
        check("postgres_write_attempt_count", int(summary.get("postgres_write_attempt_count", 0)), "==", 0),
        check("qdrant_write_attempt_count", int(summary.get("qdrant_write_attempt_count", 0)), "==", 0),
        check("opensearch_write_attempt_count", int(summary.get("opensearch_write_attempt_count", 0)), "==", 0),
        check("opensearch_upload_attempt_count", int(summary.get("opensearch_upload_attempt_count", 0)), "==", 0),
    ]
    if args.require_source_api_wrapper_quality_pass:
        checks.append(check("source_quality_pass", bool(report.get("source_quality_pass")), "is", True))
    if args.require_openai_chat_route:
        checks.append(check("openai_chat_route_present", "/v1/chat/completions" in route_paths, "is", True))
    if args.require_native_ask_route:
        checks.append(check("native_ask_route_present", "/api/trace-net/ask" in route_paths, "is", True))
    if args.require_no_answer_permission:
        checks.append(check("contract_can_answer_directly", bool(contract.get("can_answer_directly")), "is", False))
        checks.append(check("contract_can_prove_claims", bool(contract.get("can_prove_claims")), "is", False))
    quality_status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    print("TRACE-Net E2E Local Endpoint v1 Quality")
    print(f" quality_status: {quality_status}")
    for c in checks:
        status = "PASS" if c["passed"] else "FAIL"
        print(f" {status} {c['name']}: observed={c['observed']} expected={c['operator']} {c['expected']}")
    if args.write_json:
        out = report_path.with_name("trace_net_e2e_local_endpoint_v1_quality.json")
        out.write_text(json.dumps({"quality_status": quality_status, "quality_checks": checks}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if quality_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
