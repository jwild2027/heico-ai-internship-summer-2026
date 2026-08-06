from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

SCHEMA_VERSION = "trace_net_route_dispatch_warning_triage_v1"
QUALITY_SCHEMA_VERSION = "trace_net_route_dispatch_warning_triage_v1_quality"
PASS = "PASS"
FAIL = "FAIL"


@dataclass(frozen=True)
class RouteDispatchWarningTriageQualityThresholds:
    min_warning_triage_cards: int = 1
    max_unsafe_triage_cards: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_route_dispatch_coverage_audit_quality_pass: bool = False
    require_no_answer_permission: bool = False


def _int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def evaluate_quality(
    report: Mapping[str, Any],
    thresholds: Optional[RouteDispatchWarningTriageQualityThresholds] = None,
) -> Dict[str, Any]:
    thresholds = thresholds or RouteDispatchWarningTriageQualityThresholds()
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else report

    warning_triage_card_count = _int(summary.get("warning_triage_card_count"))
    unsafe_triage_card_count = _int(summary.get("unsafe_triage_card_count"))
    answer_permission_count = _int(summary.get("answer_permission_count"))
    source_truth_mutation_allowed_count = _int(summary.get("source_truth_mutation_allowed_count"))
    coverage_quality_status = str(summary.get("route_dispatch_coverage_audit_quality_status") or "")

    checks: Dict[str, bool] = {
        "schema_version_ok": report.get("schema_version") == SCHEMA_VERSION,
        "min_warning_triage_cards_met": warning_triage_card_count >= thresholds.min_warning_triage_cards,
        "unsafe_triage_cards_within_limit": unsafe_triage_card_count <= thresholds.max_unsafe_triage_cards,
        "answer_permission_within_limit": answer_permission_count <= thresholds.max_answer_permission_count,
        "source_truth_mutation_allowed_within_limit": source_truth_mutation_allowed_count <= thresholds.max_source_truth_mutation_allowed,
    }
    if thresholds.require_route_dispatch_coverage_audit_quality_pass:
        checks["route_dispatch_coverage_audit_quality_pass"] = coverage_quality_status == PASS
    if thresholds.require_no_answer_permission:
        checks["no_answer_permission"] = answer_permission_count == 0

    quality_fail_reasons = [name for name, ok in checks.items() if not ok]
    quality_status = PASS if not quality_fail_reasons else FAIL

    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "source_schema_version": report.get("schema_version"),
        "quality_status": quality_status,
        "status": quality_status,
        "checks": checks,
        "quality_fail_reasons": quality_fail_reasons,
        "warning_triage_card_count": warning_triage_card_count,
        "warning_instance_count": _int(summary.get("warning_instance_count")),
        "blank_heavy_processing_triage_count": _int(summary.get("blank_heavy_processing_triage_count")),
        "ocr_text_dispatch_policy_triage_count": _int(summary.get("ocr_text_dispatch_policy_triage_count")),
        "retrieval_answer_legacy_overlap_triage_count": _int(summary.get("retrieval_answer_legacy_overlap_triage_count")),
        "unresolved_violation_triage_count": _int(summary.get("unresolved_violation_triage_count")),
        "unsafe_triage_card_count": unsafe_triage_card_count,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "route_dispatch_coverage_audit_quality_status": coverage_quality_status,
    }


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Route Dispatch Warning Triage v1 quality")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--min-warning-triage-cards", type=int, default=1)
    parser.add_argument("--max-unsafe-triage-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-route-dispatch-coverage-audit-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> Dict[str, Any]:
    args = _parse_args(argv)
    report = json.loads(args.report_path.read_text(encoding="utf-8"))
    thresholds = RouteDispatchWarningTriageQualityThresholds(
        min_warning_triage_cards=args.min_warning_triage_cards,
        max_unsafe_triage_cards=args.max_unsafe_triage_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_route_dispatch_coverage_audit_quality_pass=args.require_route_dispatch_coverage_audit_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    quality = evaluate_quality(report, thresholds)

    if args.write_json:
        quality_path = args.report_path.with_name(args.report_path.stem + "_quality.json")
        quality_path.write_text(json.dumps(quality, indent=2, sort_keys=True), encoding="utf-8")

    print("TRACE-Net Route Dispatch Warning Triage v1 quality")
    print(f" Status: {quality['quality_status']}")
    for key in [
        "warning_triage_card_count",
        "warning_instance_count",
        "blank_heavy_processing_triage_count",
        "ocr_text_dispatch_policy_triage_count",
        "retrieval_answer_legacy_overlap_triage_count",
        "unresolved_violation_triage_count",
        "unsafe_triage_card_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
        "route_dispatch_coverage_audit_quality_status",
    ]:
        print(f" {key}: {quality.get(key)}")
    return quality


if __name__ == "__main__":
    main()
