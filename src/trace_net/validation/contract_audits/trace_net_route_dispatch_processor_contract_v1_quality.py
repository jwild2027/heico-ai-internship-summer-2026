from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

SCHEMA_VERSION = "trace_net_route_dispatch_processor_contract_v1"
QUALITY_SCHEMA_VERSION = "trace_net_route_dispatch_processor_contract_v1_quality"


@dataclass
class RouteDispatchProcessorContractQualityThresholds:
    min_processor_contract_cards: int = 1
    min_source_page_processor_contract_cards: int = 1
    min_table_processor_pages: int = 0
    min_image_visual_processor_pages: int = 0
    max_coverage_violation_count: int = 0
    max_unsafe_contract_cards: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_route_dispatch_manifest_quality_pass: bool = False
    require_route_dispatch_coverage_audit_quality_pass: bool = False
    require_route_dispatch_warning_triage_quality_pass: bool = False
    require_no_answer_permission: bool = False


def _int(value: Any) -> int:
    try:
        if value is None or value is False:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def evaluate_route_dispatch_processor_contract_quality(
    report: Mapping[str, Any],
    thresholds: Optional[RouteDispatchProcessorContractQualityThresholds] = None,
) -> Dict[str, Any]:
    thresholds = thresholds or RouteDispatchProcessorContractQualityThresholds()
    summary = report.get("summary") or report

    processor_contract_card_count = _int(summary.get("processor_contract_card_count"))
    source_page_processor_contract_card_count = _int(summary.get("source_page_processor_contract_card_count"))
    table_processor_allowed_page_count = _int(summary.get("table_processor_allowed_page_count"))
    image_visual_processor_allowed_page_count = _int(summary.get("image_visual_processor_allowed_page_count"))
    coverage_violation_count = _int(summary.get("coverage_violation_count"))
    unsafe_contract_card_count = _int(summary.get("unsafe_contract_card_count"))
    answer_permission_count = _int(summary.get("answer_permission_count"))
    source_truth_mutation_allowed_count = _int(summary.get("source_truth_mutation_allowed_count"))

    route_dispatch_manifest_quality_status = summary.get("route_dispatch_manifest_quality_status")
    route_dispatch_coverage_audit_quality_status = summary.get("route_dispatch_coverage_audit_quality_status")
    route_dispatch_warning_triage_quality_status = summary.get("route_dispatch_warning_triage_quality_status")

    checks = {
        "schema_version_ok": (summary.get("schema_version") == SCHEMA_VERSION) or (report.get("schema_version") == SCHEMA_VERSION),
        "min_processor_contract_cards_met": processor_contract_card_count >= thresholds.min_processor_contract_cards,
        "min_source_page_processor_contract_cards_met": source_page_processor_contract_card_count >= thresholds.min_source_page_processor_contract_cards,
        "min_table_processor_pages_met": table_processor_allowed_page_count >= thresholds.min_table_processor_pages,
        "min_image_visual_processor_pages_met": image_visual_processor_allowed_page_count >= thresholds.min_image_visual_processor_pages,
        "coverage_violation_count_within_limit": coverage_violation_count <= thresholds.max_coverage_violation_count,
        "unsafe_contract_cards_within_limit": unsafe_contract_card_count <= thresholds.max_unsafe_contract_cards,
        "answer_permission_within_limit": answer_permission_count <= thresholds.max_answer_permission_count,
        "source_truth_mutation_allowed_within_limit": source_truth_mutation_allowed_count <= thresholds.max_source_truth_mutation_allowed,
        "route_dispatch_manifest_quality_pass": (route_dispatch_manifest_quality_status == "PASS") if thresholds.require_route_dispatch_manifest_quality_pass else True,
        "route_dispatch_coverage_audit_quality_pass": (route_dispatch_coverage_audit_quality_status == "PASS") if thresholds.require_route_dispatch_coverage_audit_quality_pass else True,
        "route_dispatch_warning_triage_quality_pass": (route_dispatch_warning_triage_quality_status == "PASS") if thresholds.require_route_dispatch_warning_triage_quality_pass else True,
        "no_answer_permission": answer_permission_count == 0 if thresholds.require_no_answer_permission else True,
    }
    fail_reasons = [name for name, passed in checks.items() if not passed]
    quality_status = "PASS" if not fail_reasons else "FAIL"

    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "status": quality_status,
        "quality_status": quality_status,
        "quality_fail_reasons": fail_reasons,
        "checks": checks,
        "processor_contract_card_count": processor_contract_card_count,
        "source_page_processor_contract_card_count": source_page_processor_contract_card_count,
        "table_processor_allowed_page_count": table_processor_allowed_page_count,
        "image_visual_processor_allowed_page_count": image_visual_processor_allowed_page_count,
        "coverage_violation_count": coverage_violation_count,
        "unsafe_contract_card_count": unsafe_contract_card_count,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "route_dispatch_manifest_quality_status": route_dispatch_manifest_quality_status,
        "route_dispatch_coverage_audit_quality_status": route_dispatch_coverage_audit_quality_status,
        "route_dispatch_warning_triage_quality_status": route_dispatch_warning_triage_quality_status,
    }


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Route Dispatch Processor Contract v1 quality")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--min-processor-contract-cards", type=int, default=1)
    parser.add_argument("--min-source-page-processor-contract-cards", type=int, default=1)
    parser.add_argument("--min-table-processor-pages", type=int, default=0)
    parser.add_argument("--min-image-visual-processor-pages", type=int, default=0)
    parser.add_argument("--max-coverage-violation-count", type=int, default=0)
    parser.add_argument("--max-unsafe-contract-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-route-dispatch-manifest-quality-pass", action="store_true")
    parser.add_argument("--require-route-dispatch-coverage-audit-quality-pass", action="store_true")
    parser.add_argument("--require-route-dispatch-warning-triage-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    args = _parse_args(argv)
    report = _read_json(args.report_path)
    thresholds = RouteDispatchProcessorContractQualityThresholds(
        min_processor_contract_cards=args.min_processor_contract_cards,
        min_source_page_processor_contract_cards=args.min_source_page_processor_contract_cards,
        min_table_processor_pages=args.min_table_processor_pages,
        min_image_visual_processor_pages=args.min_image_visual_processor_pages,
        max_coverage_violation_count=args.max_coverage_violation_count,
        max_unsafe_contract_cards=args.max_unsafe_contract_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_route_dispatch_manifest_quality_pass=args.require_route_dispatch_manifest_quality_pass,
        require_route_dispatch_coverage_audit_quality_pass=args.require_route_dispatch_coverage_audit_quality_pass,
        require_route_dispatch_warning_triage_quality_pass=args.require_route_dispatch_warning_triage_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    quality = evaluate_route_dispatch_processor_contract_quality(report, thresholds)
    if args.write_json:
        _write_json(args.report_path.with_name("trace_net_route_dispatch_processor_contract_v1_quality.json"), quality)

    print("TRACE-Net Route Dispatch Processor Contract v1 quality")
    print(f" Status: {quality.get('quality_status')}")
    for key in [
        "processor_contract_card_count",
        "source_page_processor_contract_card_count",
        "table_processor_allowed_page_count",
        "image_visual_processor_allowed_page_count",
        "coverage_violation_count",
        "unsafe_contract_card_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
        "route_dispatch_manifest_quality_status",
        "route_dispatch_coverage_audit_quality_status",
        "route_dispatch_warning_triage_quality_status",
    ]:
        print(f" {key}: {quality.get(key)}")
    return quality


if __name__ == "__main__":
    main()
