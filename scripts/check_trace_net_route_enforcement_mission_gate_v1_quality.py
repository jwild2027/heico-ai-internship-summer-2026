from __future__ import annotations

import argparse
import json
from pathlib import Path

from tiff.trace_net_route_enforcement_mission_gate_v1 import MissionGateThresholds, build_quality, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net route enforcement mission gate v1 quality")
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--min-required-artifacts", type=int, default=7)
    parser.add_argument("--max-failed-required-artifacts", type=int, default=0)
    parser.add_argument("--max-route-contract-violation-cards", type=int, default=0)
    parser.add_argument("--max-blocked-dispatch-leak-count", type=int, default=0)
    parser.add_argument("--max-direct-answer-leak-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-leak-count", type=int, default=0)
    parser.add_argument("--max-unsafe-audit-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()

    payload = json.loads(args.report_path.read_text(encoding="utf-8"))
    summary = payload.get("summary") or {}
    quality = build_quality(
        summary,
        MissionGateThresholds(
            min_required_artifacts=args.min_required_artifacts,
            max_failed_required_artifacts=args.max_failed_required_artifacts,
            max_route_contract_violation_cards=args.max_route_contract_violation_cards,
            max_blocked_dispatch_leak_count=args.max_blocked_dispatch_leak_count,
            max_direct_answer_leak_count=args.max_direct_answer_leak_count,
            max_source_truth_mutation_leak_count=args.max_source_truth_mutation_leak_count,
            max_unsafe_audit_cards=args.max_unsafe_audit_cards,
            max_answer_permission_count=args.max_answer_permission_count,
            max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
            require_no_answer_permission=args.require_no_answer_permission,
        ),
    )

    print("TRACE-Net route enforcement mission gate v1 quality")
    print(f" Status: {quality['status']}")
    for key in [
        "required_artifact_count",
        "passed_required_artifact_count",
        "failed_required_artifact_count",
        "route_contract_violation_card_count",
        "blocked_dispatch_leak_count",
        "direct_answer_leak_count",
        "source_truth_mutation_leak_count",
        "unsafe_audit_card_count",
    ]:
        print(f" {key}: {summary.get(key)}")

    if args.write_json:
        quality_path = args.report_path.with_name("trace_net_route_enforcement_mission_gate_v1_quality.json")
        write_json(quality_path, quality)
        print(f" quality_path: {quality_path}")

    return 0 if quality["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
