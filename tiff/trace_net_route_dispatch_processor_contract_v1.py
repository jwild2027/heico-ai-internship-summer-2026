from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .trace_net_route_dispatch_processor_contract_v1_quality import (
    RouteDispatchProcessorContractQualityThresholds,
    evaluate_route_dispatch_processor_contract_quality,
)

SCHEMA_VERSION = "trace_net_route_dispatch_processor_contract_v1"
QUALITY_SCHEMA_VERSION = "trace_net_route_dispatch_processor_contract_v1_quality"
STATUS_BUILT = "TRACE_NET_ROUTE_DISPATCH_PROCESSOR_CONTRACT_BUILT"

ROUTE_TABLE = "table"
ROUTE_IMAGE = "image_visual"
ROUTE_TEXT = "normal_text"
ROUTE_BLANK = "blank_candidate"
ROUTE_REVIEW = "review"
ROUTE_ORDER = [ROUTE_TABLE, ROUTE_IMAGE, ROUTE_TEXT, ROUTE_BLANK, ROUTE_REVIEW]

ALLOWLIST_FILENAMES = {
    ROUTE_TABLE: "table_allowed_pages.json",
    ROUTE_IMAGE: "image_visual_allowed_pages.json",
    ROUTE_TEXT: "normal_text_allowed_pages.json",
    ROUTE_BLANK: "blank_candidate_pages.json",
    ROUTE_REVIEW: "review_required_pages.json",
}


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _safe_int(value: Any) -> int:
    try:
        if value is None or value is False:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _quality_status(payload: Mapping[str, Any]) -> Optional[str]:
    return payload.get("quality_status") or (payload.get("summary") or {}).get("quality_status")


def _stable_id(*parts: Any) -> str:
    raw = "::".join(str(part) for part in parts if part is not None)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    return []


def _route_allowed(card: Mapping[str, Any], route: str) -> bool:
    if route == ROUTE_TABLE:
        return bool(card.get("table_processing_allowed"))
    if route == ROUTE_IMAGE:
        return bool(card.get("image_visual_processing_allowed"))
    if route == ROUTE_TEXT:
        return bool(card.get("normal_text_processing_allowed"))
    if route == ROUTE_BLANK:
        return bool(card.get("blank_candidate_processing_allowed"))
    if route == ROUTE_REVIEW:
        return bool(card.get("review_processing_required")) or route in _as_list(card.get("allowed_dispatch_routes"))
    return False


def _route_reasons(card: Mapping[str, Any], route: str) -> List[str]:
    policies = card.get("route_policies") or {}
    if isinstance(policies, Mapping):
        policy = policies.get(route) or {}
        if isinstance(policy, Mapping):
            return [str(item) for item in _as_list(policy.get("reasons"))]
    return []


def _contract_card(dispatch_card: Mapping[str, Any]) -> Dict[str, Any]:
    page_id = dispatch_card.get("page_id") or dispatch_card.get("source_page_id")
    source_page_id = dispatch_card.get("source_page_id")
    allowed_routes = [route for route in ROUTE_ORDER if _route_allowed(dispatch_card, route)]
    safe_for_routing = bool(dispatch_card.get("safe_for_routing")) and not bool(dispatch_card.get("unsafe_dispatch_card"))

    if not safe_for_routing:
        allowed_routes = []

    route_contracts = {
        route: {
            "route": route,
            "allowed": route in allowed_routes,
            "reasons": _route_reasons(dispatch_card, route),
        }
        for route in ROUTE_ORDER
    }

    card = {
        "schema_version": SCHEMA_VERSION,
        "processor_contract_card_id": f"processor_contract::{_stable_id(page_id, source_page_id, dispatch_card.get('primary_dispatch_route'))}",
        "page_id": page_id,
        "source_page_id": source_page_id,
        "page_number": dispatch_card.get("page_number"),
        "primary_dispatch_route": dispatch_card.get("primary_dispatch_route"),
        "primary_route": dispatch_card.get("primary_route"),
        "allowed_dispatch_routes": list(dispatch_card.get("allowed_dispatch_routes") or []),
        "processor_allowed_routes": allowed_routes,
        "table_processor_allowed": ROUTE_TABLE in allowed_routes,
        "image_visual_processor_allowed": ROUTE_IMAGE in allowed_routes,
        "normal_text_processor_allowed": ROUTE_TEXT in allowed_routes,
        "blank_candidate_processor_allowed": ROUTE_BLANK in allowed_routes,
        "review_processor_required": ROUTE_REVIEW in allowed_routes,
        "review_required": bool(dispatch_card.get("review_required")) or ROUTE_REVIEW in allowed_routes,
        "safe_for_routing": safe_for_routing,
        "unsafe_contract_card": not safe_for_routing,
        "route_contracts": route_contracts,
        "dispatch_reasons": list(dispatch_card.get("dispatch_reasons") or []),
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
    }
    return card


def _allowlist_page_record(card: Mapping[str, Any], route: str) -> Dict[str, Any]:
    return {
        "page_id": card.get("page_id"),
        "source_page_id": card.get("source_page_id"),
        "page_number": card.get("page_number"),
        "primary_dispatch_route": card.get("primary_dispatch_route"),
        "route": route,
        "review_required": bool(card.get("review_required")),
        "safe_for_routing": bool(card.get("safe_for_routing")),
        "reasons": (card.get("route_contracts") or {}).get(route, {}).get("reasons", []),
    }


def _build_allowlist(route: str, cards: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    route_key = {
        ROUTE_TABLE: "table_processor_allowed",
        ROUTE_IMAGE: "image_visual_processor_allowed",
        ROUTE_TEXT: "normal_text_processor_allowed",
        ROUTE_BLANK: "blank_candidate_processor_allowed",
        ROUTE_REVIEW: "review_processor_required",
    }[route]
    pages = [_allowlist_page_record(card, route) for card in cards if card.get(route_key)]
    return {
        "schema_version": SCHEMA_VERSION,
        "route": route,
        "page_count": len(pages),
        "pages": pages,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
    }


def build_route_dispatch_processor_contract_report(
    route_dispatch_manifest_path: Path,
    route_dispatch_coverage_audit_path: Path,
    route_dispatch_warning_triage_path: Path,
    output_dir: Path,
    thresholds: Optional[RouteDispatchProcessorContractQualityThresholds] = None,
    write_outputs: bool = True,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    route_dispatch_manifest = _read_json(route_dispatch_manifest_path)
    coverage_audit = _read_json(route_dispatch_coverage_audit_path)
    warning_triage = _read_json(route_dispatch_warning_triage_path)

    dispatch_cards = [card for card in route_dispatch_manifest.get("route_dispatch_cards") or [] if isinstance(card, Mapping)]
    contract_cards = [_contract_card(card) for card in dispatch_cards]

    allowlists = {route: _build_allowlist(route, contract_cards) for route in ROUTE_ORDER}
    allowlist_paths: Dict[str, str] = {}
    if write_outputs:
        for route, payload in allowlists.items():
            path = output_dir / ALLOWLIST_FILENAMES[route]
            _write_json(path, payload)
            allowlist_paths[route] = str(path)

    table_count = sum(1 for card in contract_cards if card.get("table_processor_allowed"))
    image_count = sum(1 for card in contract_cards if card.get("image_visual_processor_allowed"))
    text_count = sum(1 for card in contract_cards if card.get("normal_text_processor_allowed"))
    blank_count = sum(1 for card in contract_cards if card.get("blank_candidate_processor_allowed"))
    review_count = sum(1 for card in contract_cards if card.get("review_processor_required"))
    unsafe_count = sum(1 for card in contract_cards if card.get("unsafe_contract_card"))
    multi_route_count = sum(1 for card in contract_cards if len(card.get("processor_allowed_routes") or []) > 1)

    coverage_summary = coverage_audit.get("summary") or {}
    triage_summary = warning_triage.get("summary") or {}
    dispatch_summary = route_dispatch_manifest.get("summary") or {}

    summary: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "route_dispatch_manifest_path": str(route_dispatch_manifest_path),
        "route_dispatch_coverage_audit_path": str(route_dispatch_coverage_audit_path),
        "route_dispatch_warning_triage_path": str(route_dispatch_warning_triage_path),
        "route_dispatch_manifest_quality_status": _quality_status(route_dispatch_manifest),
        "route_dispatch_coverage_audit_quality_status": _quality_status(coverage_audit),
        "route_dispatch_warning_triage_quality_status": _quality_status(warning_triage),
        "route_dispatch_card_count": len(dispatch_cards),
        "processor_contract_card_count": len(contract_cards),
        "source_page_processor_contract_card_count": sum(1 for card in contract_cards if card.get("source_page_id")),
        "table_processor_allowed_page_count": table_count,
        "image_visual_processor_allowed_page_count": image_count,
        "normal_text_processor_allowed_page_count": text_count,
        "blank_candidate_processor_allowed_page_count": blank_count,
        "review_required_page_count": review_count,
        "multi_route_processor_contract_card_count": multi_route_count,
        "coverage_violation_count": _safe_int(coverage_summary.get("route_dispatch_violation_card_count")),
        "coverage_warning_count": _safe_int(coverage_summary.get("route_dispatch_warning_card_count")),
        "warning_triage_card_count": _safe_int(triage_summary.get("warning_triage_card_count")),
        "unresolved_violation_triage_count": _safe_int(triage_summary.get("unresolved_violation_triage_count")),
        "unsafe_contract_card_count": unsafe_count,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "source_truth_mutations_performed": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "allowlist_paths": allowlist_paths,
        "allowed_processor_route_counts": {
            ROUTE_TABLE: table_count,
            ROUTE_IMAGE: image_count,
            ROUTE_TEXT: text_count,
            ROUTE_BLANK: blank_count,
            ROUTE_REVIEW: review_count,
        },
    }

    thresholds = thresholds or RouteDispatchProcessorContractQualityThresholds()
    quality = evaluate_route_dispatch_processor_contract_quality({"summary": summary, "processor_contract_cards": contract_cards}, thresholds)
    summary.update({
        "quality_status": quality["quality_status"],
        "quality_fail_reasons": quality.get("quality_fail_reasons", []),
        "checks": quality.get("checks", {}),
    })

    report = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "quality_status": summary["quality_status"],
        "summary": summary,
        "processor_contract_cards": contract_cards,
        "allowlists": allowlists,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
    }

    if write_outputs:
        report_path = output_dir / "trace_net_route_dispatch_processor_contract_v1.json"
        quality_path = output_dir / "trace_net_route_dispatch_processor_contract_v1_quality.json"
        summary_path = output_dir / "trace_net_route_dispatch_processor_contract_v1_summary.json"
        _write_json(report_path, report)
        _write_json(quality_path, quality)
        _write_json(summary_path, summary)

    return report


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Route Dispatch Processor Contract v1")
    parser.add_argument("--route-dispatch-manifest", required=True, type=Path)
    parser.add_argument("--route-dispatch-coverage-audit", required=True, type=Path)
    parser.add_argument("--route-dispatch-warning-triage", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
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
    parser.add_argument("--quality", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    args = _parse_args(argv)
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
    report = build_route_dispatch_processor_contract_report(
        route_dispatch_manifest_path=args.route_dispatch_manifest,
        route_dispatch_coverage_audit_path=args.route_dispatch_coverage_audit,
        route_dispatch_warning_triage_path=args.route_dispatch_warning_triage,
        output_dir=args.output_dir,
        thresholds=thresholds,
    )

    summary = report.get("summary", {})
    print("TRACE-Net Route Dispatch Processor Contract v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "processor_contract_card_count",
        "source_page_processor_contract_card_count",
        "table_processor_allowed_page_count",
        "image_visual_processor_allowed_page_count",
        "normal_text_processor_allowed_page_count",
        "blank_candidate_processor_allowed_page_count",
        "review_required_page_count",
        "coverage_violation_count",
        "warning_triage_card_count",
        "unsafe_contract_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {args.output_dir / 'trace_net_route_dispatch_processor_contract_v1.json'}")
    print(f" quality_path: {args.output_dir / 'trace_net_route_dispatch_processor_contract_v1_quality.json'}")
    return report


if __name__ == "__main__":
    main()
