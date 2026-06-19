from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping

PASS = "PASS"
FAIL = "FAIL"
SCHEMA_VERSION = "trace_net_page_route_manifest_v1"
QUALITY_SCHEMA_VERSION = "trace_net_page_route_manifest_v1_quality"


@dataclass(frozen=True)
class PageRouteManifestQualityThresholds:
    min_page_route_cards: int = 1
    min_source_page_route_cards: int = 0
    min_table_route_cards: int = 0
    min_safe_for_routing_cards: int = 1
    max_unsafe_route_cards: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_artifact_detector_quality_pass: bool = False
    require_page_ink_route_evidence_quality_pass: bool = False
    min_page_ink_route_evidence_cards: int = 0
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
    thresholds: PageRouteManifestQualityThresholds | None = None,
) -> Dict[str, Any]:
    thresholds = thresholds or PageRouteManifestQualityThresholds()
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else report

    page_route_card_count = _int(summary.get("page_route_card_count"))
    source_page_route_card_count = _int(summary.get("source_page_route_card_count"))
    table_primary_route_count = _int(summary.get("table_primary_route_count"))
    safe_for_routing_route_card_count = _int(summary.get("safe_for_routing_route_card_count"))
    unsafe_route_card_count = _int(summary.get("unsafe_route_card_count"))
    answer_permission_count = _int(summary.get("answer_permission_count"))
    source_truth_mutation_allowed_count = _int(summary.get("source_truth_mutation_allowed_count"))
    artifact_detector_quality_status = summary.get("artifact_detector_quality_status")
    page_ink_route_evidence_quality_status = summary.get("page_ink_route_evidence_quality_status")
    page_ink_route_evidence_available_card_count = _int(summary.get("page_ink_route_evidence_available_card_count"))

    checks: Dict[str, bool] = {
        "schema_version_ok": report.get("schema_version") == SCHEMA_VERSION,
        "min_page_route_cards_met": page_route_card_count >= thresholds.min_page_route_cards,
        "min_source_page_route_cards_met": source_page_route_card_count >= thresholds.min_source_page_route_cards,
        "min_table_route_cards_met": table_primary_route_count >= thresholds.min_table_route_cards,
        "min_safe_for_routing_cards_met": safe_for_routing_route_card_count >= thresholds.min_safe_for_routing_cards,
        "min_page_ink_route_evidence_cards_met": page_ink_route_evidence_available_card_count >= thresholds.min_page_ink_route_evidence_cards,
        "unsafe_route_cards_within_limit": unsafe_route_card_count <= thresholds.max_unsafe_route_cards,
        "answer_permission_within_limit": answer_permission_count <= thresholds.max_answer_permission_count,
        "source_truth_mutation_allowed_within_limit": source_truth_mutation_allowed_count <= thresholds.max_source_truth_mutation_allowed,
    }
    if thresholds.require_artifact_detector_quality_pass:
        checks["artifact_detector_quality_pass"] = artifact_detector_quality_status == PASS
    if thresholds.require_page_ink_route_evidence_quality_pass:
        checks["page_ink_route_evidence_quality_pass"] = page_ink_route_evidence_quality_status == PASS
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
        "page_route_card_count": page_route_card_count,
        "source_page_route_card_count": source_page_route_card_count,
        "table_primary_route_count": table_primary_route_count,
        "safe_for_routing_route_card_count": safe_for_routing_route_card_count,
        "unsafe_route_card_count": unsafe_route_card_count,
        "page_ink_route_evidence_quality_status": page_ink_route_evidence_quality_status,
        "page_ink_route_evidence_available_card_count": page_ink_route_evidence_available_card_count,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "artifact_detector_quality_status": artifact_detector_quality_status,
    }
