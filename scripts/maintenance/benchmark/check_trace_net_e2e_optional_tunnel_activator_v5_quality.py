#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def check(name, observed, op, expected):
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
    return {"name": name, "observed": observed, "expected": f"{op} {expected}", "passed": passed}


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net optional tunnel activator v5 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-activated-tunnels", type=int, default=4)
    parser.add_argument("--min-graph-or-summary-tunnels", type=int, default=2)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()

    path = Path(args.report_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    summary = data.get("summary", {})
    contract = data.get("activation_contract", {})

    checks = [
        check("quality_status", data.get("quality_status"), "==", "PASS"),
        check("activated_optional_tunnel_count", int(summary.get("activated_optional_tunnel_count", 0)), ">=", args.min_activated_tunnels),
        check("graph_or_summary_tunnel_count", int(summary.get("graph_or_summary_tunnel_count", 0)), ">=", args.min_graph_or_summary_tunnels),
        check("answer_permission_count", int(summary.get("answer_permission_count", 0)), "<=", args.max_answer_permission_count),
        check("source_truth_mutation_allowed_count", int(summary.get("source_truth_mutation_allowed_count", 0)), "<=", args.max_source_truth_mutation_allowed),
        check("contract_reruns_ocr", bool(contract.get("reruns_ocr")), "is", False),
        check("contract_reruns_embeddings", bool(contract.get("reruns_embeddings")), "is", False),
        check("contract_reruns_graph_build", bool(contract.get("reruns_graph_build")), "is", False),
        check("contract_graph_is_not_proof_authority", bool(contract.get("graph_is_not_proof_authority")), "is", True),
    ]
    if args.require_no_answer_permission:
        checks.append(check("contract_answer_permission", bool(contract.get("answer_permission")), "is", False))
    quality = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    print("TRACE-Net E2E Optional Tunnel Activator v5 Quality")
    print(f" quality_status: {quality}")
    for c in checks:
        print(f" {'PASS' if c['passed'] else 'FAIL'} {c['name']}: observed={c['observed']} expected={c['expected']}")
    if args.write_json:
        out = path.with_name(path.stem + "_quality.json")
        out.write_text(json.dumps({"quality_status": quality, "checks": checks}, indent=2, sort_keys=True), encoding="utf-8")
    return 0 if quality == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
