from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from tiff.trace_net_table_line_geometry_route_contract_audit_v1_quality import (
    TableLineGeometryRouteContractAuditQualityThresholds,
    evaluate_table_line_geometry_route_contract_audit_quality,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net table line geometry route contract audit v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-table-geometry-cards", type=int, default=1)
    parser.add_argument("--min-route-contract-audit-cards", type=int, default=1)
    parser.add_argument("--max-table-route-blocked-geometry-cards", type=int, default=0)
    parser.add_argument("--max-unsafe-audit-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-line-geometry-quality-pass", action="store_true")
    parser.add_argument("--require-route-dispatch-processor-contract-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report_path = Path(args.report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    summary = payload.get("summary") or {}
    thresholds = TableLineGeometryRouteContractAuditQualityThresholds(
        min_table_geometry_cards=args.min_table_geometry_cards,
        min_route_contract_audit_cards=args.min_route_contract_audit_cards,
        max_table_route_blocked_geometry_cards=args.max_table_route_blocked_geometry_cards,
        max_unsafe_audit_cards=args.max_unsafe_audit_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_table_line_geometry_quality_pass=args.require_table_line_geometry_quality_pass,
        require_route_dispatch_processor_contract_quality_pass=args.require_route_dispatch_processor_contract_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    quality = evaluate_table_line_geometry_route_contract_audit_quality(summary, thresholds)
    if args.write_json:
        quality_path = report_path.with_name("trace_net_table_line_geometry_route_contract_audit_v1_quality.json")
        quality_path.write_text(json.dumps(quality | {"summary": summary}, indent=2, sort_keys=True), encoding="utf-8")
    print("TRACE-Net Table Line Geometry Route Contract Audit v1 quality")
    print(f" Status: {quality.get('quality_status')}")
    for key in [
        "table_geometry_card_count",
        "route_contract_audit_card_count",
        "table_route_allowed_geometry_card_count",
        "table_route_blocked_geometry_card_count",
        "review_required_geometry_card_count",
        "unsafe_audit_card_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
        "table_line_geometry_quality_status",
        "route_dispatch_processor_contract_quality_status",
    ]:
        print(f" {key}: {quality.get(key)}")
    return 0 if quality.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
