from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

SCHEMA_VERSION = "trace_net_route_dispatch_coverage_audit_v1"
QUALITY_SCHEMA_VERSION = "trace_net_route_dispatch_coverage_audit_v1_quality"
PASS = "PASS"
FAIL = "FAIL"


@dataclass(frozen=True)
class RouteDispatchCoverageAuditQualityThresholds:
    min_dispatch_coverage_cards: int = 1
    min_audited_page_artifact_cards: int = 1
    max_unsafe_audit_cards: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_route_dispatch_manifest_quality_pass: bool = False
    require_artifact_detector_quality_pass: bool = False
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
    thresholds: Optional[RouteDispatchCoverageAuditQualityThresholds] = None,
) -> Dict[str, Any]:
    thresholds = thresholds or RouteDispatchCoverageAuditQualityThresholds()
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else report

    dispatch_coverage_card_count = _int(summary.get("dispatch_coverage_card_count"))
    audited_page_artifact_card_count = _int(summary.get("audited_page_artifact_card_count"))
    unsafe_audit_card_count = _int(summary.get("unsafe_audit_card_count"))
    answer_permission_count = _int(summary.get("answer_permission_count"))
    source_truth_mutation_allowed_count = _int(summary.get("source_truth_mutation_allowed_count"))
    route_dispatch_manifest_quality_status = str(summary.get("route_dispatch_manifest_quality_status") or "")
    artifact_detector_quality_status = str(summary.get("artifact_detector_quality_status") or "")

    checks: Dict[str, bool] = {
        "schema_version_ok": report.get("schema_version") == SCHEMA_VERSION,
        "min_dispatch_coverage_cards_met": dispatch_coverage_card_count >= thresholds.min_dispatch_coverage_cards,
        "min_audited_page_artifact_cards_met": audited_page_artifact_card_count >= thresholds.min_audited_page_artifact_cards,
        "unsafe_audit_cards_within_limit": unsafe_audit_card_count <= thresholds.max_unsafe_audit_cards,
        "answer_permission_within_limit": answer_permission_count <= thresholds.max_answer_permission_count,
        "source_truth_mutation_allowed_within_limit": source_truth_mutation_allowed_count <= thresholds.max_source_truth_mutation_allowed,
    }
    if thresholds.require_route_dispatch_manifest_quality_pass:
        checks["route_dispatch_manifest_quality_pass"] = route_dispatch_manifest_quality_status == PASS
    if thresholds.require_artifact_detector_quality_pass:
        checks["artifact_detector_quality_pass"] = artifact_detector_quality_status == PASS
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
        "dispatch_coverage_card_count": dispatch_coverage_card_count,
        "audited_page_artifact_card_count": audited_page_artifact_card_count,
        "route_dispatch_violation_card_count": _int(summary.get("route_dispatch_violation_card_count")),
        "blank_heavy_processing_warning_card_count": _int(summary.get("blank_heavy_processing_warning_card_count")),
        "review_required_audit_card_count": _int(summary.get("review_required_audit_card_count")),
        "unsafe_audit_card_count": unsafe_audit_card_count,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "route_dispatch_manifest_quality_status": route_dispatch_manifest_quality_status,
        "artifact_detector_quality_status": artifact_detector_quality_status,
    }


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Route Dispatch Coverage Audit v1 quality")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--min-dispatch-coverage-cards", type=int, default=1)
    parser.add_argument("--min-audited-page-artifact-cards", type=int, default=1)
    parser.add_argument("--max-unsafe-audit-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-route-dispatch-manifest-quality-pass", action="store_true")
    parser.add_argument("--require-artifact-detector-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> Dict[str, Any]:
    args = _parse_args(argv)
    report = json.loads(args.report_path.read_text(encoding="utf-8"))
    thresholds = RouteDispatchCoverageAuditQualityThresholds(
        min_dispatch_coverage_cards=args.min_dispatch_coverage_cards,
        min_audited_page_artifact_cards=args.min_audited_page_artifact_cards,
        max_unsafe_audit_cards=args.max_unsafe_audit_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_route_dispatch_manifest_quality_pass=args.require_route_dispatch_manifest_quality_pass,
        require_artifact_detector_quality_pass=args.require_artifact_detector_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    quality = evaluate_quality(report, thresholds)

    if args.write_json:
        quality_path = args.report_path.with_name(args.report_path.stem + "_quality.json")
        quality_path.write_text(json.dumps(quality, indent=2, sort_keys=True), encoding="utf-8")

    print("TRACE-Net Route Dispatch Coverage Audit v1 quality")
    print(f" Status: {quality['quality_status']}")
    for key in [
        "dispatch_coverage_card_count",
        "audited_page_artifact_card_count",
        "route_dispatch_violation_card_count",
        "blank_heavy_processing_warning_card_count",
        "review_required_audit_card_count",
        "unsafe_audit_card_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
        "route_dispatch_manifest_quality_status",
        "artifact_detector_quality_status",
    ]:
        print(f" {key}: {quality.get(key)}")
    return quality


if __name__ == "__main__":
    main()
