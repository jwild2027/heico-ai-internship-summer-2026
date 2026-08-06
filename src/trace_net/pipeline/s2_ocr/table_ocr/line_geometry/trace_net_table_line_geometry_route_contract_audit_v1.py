from __future__ import annotations

import argparse
import json
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from tiff.trace_net_route_dispatch_contract_loader_v1 import load_route_dispatch_processor_contract
from tiff.trace_net_table_line_geometry_route_contract_audit_v1_quality import (
    TableLineGeometryRouteContractAuditQualityThresholds,
    evaluate_table_line_geometry_route_contract_audit_quality,
)

SCHEMA_VERSION = "trace_net_table_line_geometry_route_contract_audit_v1"
QUALITY_SCHEMA_VERSION = "trace_net_table_line_geometry_route_contract_audit_v1_quality"
STATUS_BUILT = "TRACE_NET_TABLE_LINE_GEOMETRY_ROUTE_CONTRACT_AUDIT_BUILT"
STATUS_NOT_READY = "TRACE_NET_TABLE_LINE_GEOMETRY_ROUTE_CONTRACT_AUDIT_NOT_READY"


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _safe_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _stable_id(*parts: Any) -> str:
    raw = "::".join(str(part) for part in parts if part is not None)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _page_number_from_page_id(page_id: Any) -> Optional[int]:
    if page_id is None:
        return None
    text = str(page_id)
    for token in ("_p", "metadata_page_"):
        if token in text:
            tail = text.rsplit(token, 1)[-1]
            digits = "".join(ch for ch in tail if ch.isdigit())
            if digits:
                return int(digits)
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits:
        return int(digits[-6:])
    return None


def _table_geometry_cards(payload: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    cards = payload.get("table_geometry_cards") or payload.get("cards") or []
    return [card for card in cards if isinstance(card, Mapping)]


def _source_quality_status(payload: Mapping[str, Any]) -> str:
    return str(payload.get("quality_status") or (payload.get("summary") or {}).get("quality_status") or "UNKNOWN")


def _contract_quality_status(contract_payload: Mapping[str, Any]) -> str:
    return str(contract_payload.get("quality_status") or (contract_payload.get("summary") or {}).get("quality_status") or "UNKNOWN")


def _card_page_aliases(card: Mapping[str, Any]) -> List[Any]:
    aliases: List[Any] = []
    for key in ("page_id", "source_page_id"):
        value = card.get(key)
        if value:
            aliases.append(str(value))
    page_number = card.get("page_number") or _page_number_from_page_id(card.get("page_id"))
    if page_number:
        page_number = int(page_number)
        aliases.extend([
            page_number,
            f"metadata_page_{page_number:06d}",
            f"t_p_120_1176_p{page_number:06d}",
        ])
    return list(dict.fromkeys(aliases))


def _contract_allows_table(contract: Any, card: Mapping[str, Any]) -> bool:
    for alias in _card_page_aliases(card):
        if contract.is_table_allowed(alias):
            return True
    return False


def _contract_requires_review(contract: Any, card: Mapping[str, Any]) -> bool:
    for alias in _card_page_aliases(card):
        if contract.is_review_required(alias):
            return True
    return False


def build_table_line_geometry_route_contract_audit_report(
    table_line_geometry_path: Path,
    route_dispatch_processor_contract_path: Path,
    output_dir: Path,
    thresholds: Optional[TableLineGeometryRouteContractAuditQualityThresholds] = None,
    write_outputs: bool = True,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    table_payload = _read_json(table_line_geometry_path)
    contract_payload = _read_json(route_dispatch_processor_contract_path)
    contract = load_route_dispatch_processor_contract(route_dispatch_processor_contract_path)

    table_cards = _table_geometry_cards(table_payload)
    audit_cards: List[Dict[str, Any]] = []

    for card in table_cards:
        page_id = card.get("page_id") or card.get("source_page_id")
        table_id = card.get("table_id")
        table_allowed = _contract_allows_table(contract, card)
        review_required = _contract_requires_review(contract, card)
        safe_for_routing = bool(table_allowed)
        status = "PASS" if table_allowed else "BLOCKED_BY_ROUTE_CONTRACT"
        violations = [] if table_allowed else ["table_geometry_card_not_allowed_by_route_dispatch_contract"]
        warnings = []
        if review_required:
            warnings.append("table_geometry_page_requires_review")

        audit_cards.append({
            "schema_version": SCHEMA_VERSION,
            "audit_card_id": f"table_line_geometry_route_contract::{_stable_id(page_id, table_id)}",
            "page_id": page_id,
            "source_page_id": card.get("source_page_id"),
            "page_number": card.get("page_number") or _page_number_from_page_id(page_id),
            "table_id": table_id,
            "table_type": card.get("table_type"),
            "selected_morphology_scope": card.get("selected_morphology_scope"),
            "route_contract_table_allowed": table_allowed,
            "route_contract_review_required": review_required,
            "route_contract_status": status,
            "route_contract_violations": violations,
            "route_contract_warnings": warnings,
            "safe_for_routing": safe_for_routing,
            "unsafe_audit_card": not safe_for_routing,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "source_truth_mutations_performed": 0,
        })

    summary: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "table_line_geometry_path": str(table_line_geometry_path),
        "route_dispatch_processor_contract_path": str(route_dispatch_processor_contract_path),
        "table_line_geometry_quality_status": _source_quality_status(table_payload),
        "route_dispatch_processor_contract_quality_status": _contract_quality_status(contract_payload),
        "table_geometry_card_count": len(table_cards),
        "route_contract_audit_card_count": len(audit_cards),
        "table_route_allowed_geometry_card_count": sum(1 for card in audit_cards if card.get("route_contract_table_allowed")),
        "table_route_blocked_geometry_card_count": sum(1 for card in audit_cards if not card.get("route_contract_table_allowed")),
        "review_required_geometry_card_count": sum(1 for card in audit_cards if card.get("route_contract_review_required")),
        "unsafe_audit_card_count": sum(1 for card in audit_cards if card.get("unsafe_audit_card")),
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "source_truth_mutations_performed": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }

    thresholds = thresholds or TableLineGeometryRouteContractAuditQualityThresholds()
    quality = evaluate_table_line_geometry_route_contract_audit_quality(summary, thresholds)
    summary.update({
        "quality_status": quality["quality_status"],
        "quality_fail_reasons": quality.get("quality_fail_reasons", []),
        "checks": quality.get("checks", {}),
    })

    report: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT if summary["quality_status"] == "PASS" else STATUS_NOT_READY,
        "quality_status": summary["quality_status"],
        "summary": summary,
        "route_contract_audit_cards": audit_cards,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
    }

    if write_outputs:
        report_path = output_dir / "trace_net_table_line_geometry_route_contract_audit_v1.json"
        quality_path = output_dir / "trace_net_table_line_geometry_route_contract_audit_v1_quality.json"
        _write_json(report_path, report)
        _write_json(quality_path, quality | {"schema_version": QUALITY_SCHEMA_VERSION, "summary": summary})
        summary["report_path"] = str(report_path)
        summary["quality_path"] = str(quality_path)
        _write_json(report_path, report)
        _write_json(quality_path, quality | {"schema_version": QUALITY_SCHEMA_VERSION, "summary": summary})

    return report


def _print_report(report: Mapping[str, Any]) -> None:
    summary = report.get("summary") or {}
    print("TRACE-Net Table Line Geometry Route Contract Audit v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "table_geometry_card_count",
        "route_contract_audit_card_count",
        "table_route_allowed_geometry_card_count",
        "table_route_blocked_geometry_card_count",
        "review_required_geometry_card_count",
        "unsafe_audit_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "table_line_geometry_quality_status",
        "route_dispatch_processor_contract_quality_status",
        "report_path",
        "quality_path",
    ]:
        if key in summary:
            print(f" {key}: {summary.get(key)}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net table line geometry route contract audit v1")
    parser.add_argument("--table-line-geometry", required=True)
    parser.add_argument("--route-dispatch-processor-contract", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--min-table-geometry-cards", type=int, default=1)
    parser.add_argument("--min-route-contract-audit-cards", type=int, default=1)
    parser.add_argument("--max-table-route-blocked-geometry-cards", type=int, default=0)
    parser.add_argument("--max-unsafe-audit-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-line-geometry-quality-pass", action="store_true")
    parser.add_argument("--require-route-dispatch-processor-contract-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
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
    report = build_table_line_geometry_route_contract_audit_report(
        table_line_geometry_path=Path(args.table_line_geometry),
        route_dispatch_processor_contract_path=Path(args.route_dispatch_processor_contract),
        output_dir=Path(args.output_dir),
        thresholds=thresholds,
    )
    _print_report(report)
    return 0 if report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
