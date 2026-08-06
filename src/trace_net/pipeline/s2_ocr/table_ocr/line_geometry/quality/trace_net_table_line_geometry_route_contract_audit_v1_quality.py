from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping

SCHEMA_VERSION = "trace_net_table_line_geometry_route_contract_audit_v1_quality"


@dataclass
class TableLineGeometryRouteContractAuditQualityThresholds:
    min_table_geometry_cards: int = 1
    min_route_contract_audit_cards: int = 1
    max_table_route_blocked_geometry_cards: int = 0
    max_unsafe_audit_cards: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_table_line_geometry_quality_pass: bool = False
    require_route_dispatch_processor_contract_quality_pass: bool = False
    require_no_answer_permission: bool = False


def _int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _status(value: Any) -> str:
    return str(value or "UNKNOWN")


def evaluate_table_line_geometry_route_contract_audit_quality(
    summary: Mapping[str, Any],
    thresholds: TableLineGeometryRouteContractAuditQualityThresholds | None = None,
) -> Dict[str, Any]:
    thresholds = thresholds or TableLineGeometryRouteContractAuditQualityThresholds()
    checks = {
        "schema_version_ok": summary.get("schema_version") == "trace_net_table_line_geometry_route_contract_audit_v1",
        "min_table_geometry_cards_met": _int(summary.get("table_geometry_card_count")) >= thresholds.min_table_geometry_cards,
        "min_route_contract_audit_cards_met": _int(summary.get("route_contract_audit_card_count")) >= thresholds.min_route_contract_audit_cards,
        "table_route_blocked_geometry_cards_within_limit": _int(summary.get("table_route_blocked_geometry_card_count")) <= thresholds.max_table_route_blocked_geometry_cards,
        "unsafe_audit_cards_within_limit": _int(summary.get("unsafe_audit_card_count")) <= thresholds.max_unsafe_audit_cards,
        "answer_permission_within_limit": _int(summary.get("answer_permission_count")) <= thresholds.max_answer_permission_count,
        "source_truth_mutation_allowed_within_limit": _int(summary.get("source_truth_mutation_allowed_count")) <= thresholds.max_source_truth_mutation_allowed,
    }
    if thresholds.require_table_line_geometry_quality_pass:
        checks["table_line_geometry_quality_pass"] = _status(summary.get("table_line_geometry_quality_status")) == "PASS"
    if thresholds.require_route_dispatch_processor_contract_quality_pass:
        checks["route_dispatch_processor_contract_quality_pass"] = _status(summary.get("route_dispatch_processor_contract_quality_status")) == "PASS"
    if thresholds.require_no_answer_permission:
        checks["no_answer_permission"] = _int(summary.get("answer_permission_count")) == 0

    fail_reasons = [name for name, ok in checks.items() if not ok]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS" if not fail_reasons else "FAIL",
        "quality_status": "PASS" if not fail_reasons else "FAIL",
        "quality_fail_reasons": fail_reasons,
        "checks": checks,
        "table_geometry_card_count": _int(summary.get("table_geometry_card_count")),
        "route_contract_audit_card_count": _int(summary.get("route_contract_audit_card_count")),
        "table_route_allowed_geometry_card_count": _int(summary.get("table_route_allowed_geometry_card_count")),
        "table_route_blocked_geometry_card_count": _int(summary.get("table_route_blocked_geometry_card_count")),
        "review_required_geometry_card_count": _int(summary.get("review_required_geometry_card_count")),
        "unsafe_audit_card_count": _int(summary.get("unsafe_audit_card_count")),
        "answer_permission_count": _int(summary.get("answer_permission_count")),
        "source_truth_mutation_allowed_count": _int(summary.get("source_truth_mutation_allowed_count")),
        "table_line_geometry_quality_status": summary.get("table_line_geometry_quality_status"),
        "route_dispatch_processor_contract_quality_status": summary.get("route_dispatch_processor_contract_quality_status"),
    }
