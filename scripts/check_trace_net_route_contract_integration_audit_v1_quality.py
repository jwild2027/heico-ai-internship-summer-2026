from __future__ import annotations

import argparse
import json
from pathlib import Path

from tiff.trace_net_route_contract_integration_audit_v1 import AuditThresholds, build_quality, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net route contract integration audit v1 quality")
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--min-audited-processors", type=int, default=6)
    parser.add_argument("--min-audited-records", type=int, default=1)
    parser.add_argument("--max-route-contract-violation-cards", type=int, default=0)
    parser.add_argument("--max-blocked-dispatch-leak-count", type=int, default=0)
    parser.add_argument("--max-direct-answer-leak-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-leak-count", type=int, default=0)
    parser.add_argument("--max-unsafe-audit-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-route-dispatch-processor-contract-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()

    payload = json.loads(args.report_path.read_text(encoding="utf-8"))
    summary = payload.get("summary") or {}
    quality = build_quality(
        summary,
        AuditThresholds(
            min_audited_processors=args.min_audited_processors,
            min_audited_records=args.min_audited_records,
            max_route_contract_violation_cards=args.max_route_contract_violation_cards,
            max_blocked_dispatch_leak_count=args.max_blocked_dispatch_leak_count,
            max_direct_answer_leak_count=args.max_direct_answer_leak_count,
            max_source_truth_mutation_leak_count=args.max_source_truth_mutation_leak_count,
            max_unsafe_audit_cards=args.max_unsafe_audit_cards,
            max_answer_permission_count=args.max_answer_permission_count,
            max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
            require_route_dispatch_processor_contract_quality_pass=args.require_route_dispatch_processor_contract_quality_pass,
            require_no_answer_permission=args.require_no_answer_permission,
        ),
    )
    print("TRACE-Net route contract integration audit v1 quality")
    print(f" Status: {quality['status']}")
    for key in [
        "audited_processor_count",
        "audited_record_count",
        "route_contract_violation_card_count",
        "blocked_dispatch_leak_count",
        "direct_answer_leak_count",
        "source_truth_mutation_leak_count",
        "unsafe_audit_card_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    if args.write_json:
        quality_path = args.report_path.with_name("trace_net_route_contract_integration_audit_v1_quality.json")
        write_json(quality_path, quality)
        print(f" quality_path: {quality_path}")
    return 0 if quality["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
