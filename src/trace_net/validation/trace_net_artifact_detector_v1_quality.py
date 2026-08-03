from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, MutableMapping

SCHEMA_VERSION = "trace_net_artifact_detector_v1"
QUALITY_SCHEMA_VERSION = "trace_net_artifact_detector_v1_quality"
PASS = "PASS"
FAIL = "FAIL"


@dataclass(frozen=True)
class ArtifactDetectorQualityThresholds:
    min_artifact_cards: int = 1
    min_page_artifact_cards: int = 1
    min_source_page_cards: int = 0
    max_unsafe_artifact_cards: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_metadata_pages: bool = False
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
    thresholds: ArtifactDetectorQualityThresholds | None = None,
) -> Dict[str, Any]:
    thresholds = thresholds or ArtifactDetectorQualityThresholds()
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else report

    artifact_card_count = _int(summary.get("artifact_card_count"))
    page_artifact_card_count = _int(summary.get("page_artifact_card_count"))
    source_page_card_count = _int(summary.get("source_page_card_count"))
    unsafe_artifact_card_count = _int(summary.get("unsafe_artifact_card_count"))
    unsafe_safe_for_routing_artifact_card_count = _int(summary.get("unsafe_safe_for_routing_artifact_card_count"))
    safe_for_routing_answer_permission_count = _int(summary.get("safe_for_routing_answer_permission_count"))
    safe_for_routing_source_truth_mutation_allowed_count = _int(summary.get("safe_for_routing_source_truth_mutation_allowed_count"))
    answer_permission_count = _int(summary.get("answer_permission_count"))
    source_truth_mutation_allowed_count = _int(summary.get("source_truth_mutation_allowed_count"))

    checks: Dict[str, bool] = {
        "schema_version_ok": report.get("schema_version") == SCHEMA_VERSION,
        "min_artifact_cards_met": artifact_card_count >= thresholds.min_artifact_cards,
        "min_page_artifact_cards_met": page_artifact_card_count >= thresholds.min_page_artifact_cards,
        "min_source_page_cards_met": source_page_card_count >= thresholds.min_source_page_cards,
        "unsafe_artifact_cards_within_limit": unsafe_safe_for_routing_artifact_card_count <= thresholds.max_unsafe_artifact_cards,
        "answer_permission_within_limit": safe_for_routing_answer_permission_count <= thresholds.max_answer_permission_count,
        "source_truth_mutation_allowed_within_limit": safe_for_routing_source_truth_mutation_allowed_count <= thresholds.max_source_truth_mutation_allowed,
    }
    if thresholds.require_metadata_pages:
        checks["metadata_pages_present"] = source_page_card_count > 0
    if thresholds.require_no_answer_permission:
        checks["no_answer_permission"] = safe_for_routing_answer_permission_count == 0

    quality_fail_reasons = [name for name, ok in checks.items() if not ok]
    quality_status = PASS if not quality_fail_reasons else FAIL

    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "source_schema_version": report.get("schema_version"),
        "quality_status": quality_status,
        "status": quality_status,
        "checks": checks,
        "quality_fail_reasons": quality_fail_reasons,
        "artifact_card_count": artifact_card_count,
        "page_artifact_card_count": page_artifact_card_count,
        "source_page_card_count": source_page_card_count,
        "unsafe_artifact_card_count": unsafe_artifact_card_count,
        "unsafe_safe_for_routing_artifact_card_count": unsafe_safe_for_routing_artifact_card_count,
        "safe_for_routing_answer_permission_count": safe_for_routing_answer_permission_count,
        "safe_for_routing_source_truth_mutation_allowed_count": safe_for_routing_source_truth_mutation_allowed_count,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
    }
