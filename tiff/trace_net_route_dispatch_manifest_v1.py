from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from tiff.trace_net_route_dispatch_manifest_v1_quality import (
    PASS,
    FAIL,
    SCHEMA_VERSION,
    RouteDispatchQualityThresholds,
    evaluate_quality,
)

ROUTE_TABLE = "table"
ROUTE_IMAGE = "image_visual"
ROUTE_TEXT = "normal_text"
ROUTE_BLANK = "blank_candidate"
ROUTE_REVIEW = "review"

ROUTE_ORDER = [ROUTE_TABLE, ROUTE_IMAGE, ROUTE_TEXT, ROUTE_BLANK, ROUTE_REVIEW]


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _stable_id(*parts: Any) -> str:
    text = "::".join(str(part) for part in parts if part is not None)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_routes(primary: str, secondary: Sequence[Any], review_required: bool) -> List[str]:
    routes: List[str] = []
    for route in [primary, *[str(item) for item in secondary if item]]:
        if route and route in ROUTE_ORDER and route not in routes:
            routes.append(route)
    if review_required and ROUTE_REVIEW not in routes:
        routes.append(ROUTE_REVIEW)
    return routes


def _dispatch_policy_for_route(route: str, card: Mapping[str, Any]) -> Dict[str, Any]:
    primary = str(card.get("primary_route") or "")
    secondary_routes = set(str(item) for item in (card.get("secondary_routes") or []) if item)
    review_required = bool(card.get("review_required"))
    route_confidence = _safe_float(card.get("route_confidence"))
    score = _safe_float(card.get(f"{route}_score"))
    if route == ROUTE_IMAGE:
        score = _safe_float(card.get("image_visual_score"))
    elif route == ROUTE_TEXT:
        score = _safe_float(card.get("text_score"))
    elif route == ROUTE_BLANK:
        score = _safe_float(card.get("blank_score"))
    elif route == ROUTE_REVIEW:
        score = _safe_float(card.get("review_score")) or (0.75 if review_required else 0.0)

    is_primary = primary == route
    is_secondary = route in secondary_routes
    reasons: List[str] = []
    status = "not_selected"
    allowed = False

    if route == ROUTE_REVIEW:
        allowed = review_required or primary == ROUTE_REVIEW
        status = "review_required" if allowed else "not_selected"
        if allowed:
            reasons.append("route_manifest_review_required")
        return {
            "route": route,
            "allowed": allowed,
            "status": status,
            "is_primary": is_primary,
            "is_secondary": is_secondary,
            "score": round(score, 6),
            "reasons": reasons,
        }

    if is_primary:
        allowed = True
        status = "primary_route_allowed"
        reasons.append(f"primary_route_{route}")
    elif is_secondary and review_required:
        allowed = True
        status = "secondary_review_candidate_allowed"
        reasons.append(f"secondary_route_{route}_with_review_required")
    elif is_secondary:
        routing_reasons = set(str(reason) for reason in (card.get("routing_reasons") or []))

        # Some primary table pages legitimately have visual evidence artifacts.
        # Allow image_visual as a secondary dispatch when the route manifest
        # already identified image/visual evidence, even if the page does not
        # require review.
        if route == ROUTE_IMAGE and "image_visual_evidence_artifact_present" in routing_reasons:
            allowed = True
            status = "secondary_route_allowed_by_visual_artifact_evidence"
            reasons.append("secondary_route_image_visual_allowed_by_visual_artifact_evidence")
        else:
            allowed = False
            status = "secondary_route_advisory_only"
            reasons.append(f"secondary_route_{route}_advisory_only")
    else:
        allowed = False
        status = "not_selected"

    # Keep blank routing conservative: blank pages should not enter heavy OCR/table/image modules.
    if route == ROUTE_BLANK and is_primary:
        reasons.append("blank_candidate_primary_route_skips_heavy_processing")

    return {
        "route": route,
        "allowed": allowed,
        "status": status,
        "is_primary": is_primary,
        "is_secondary": is_secondary,
        "score": round(score if score else route_confidence, 6),
        "reasons": reasons,
    }


def build_dispatch_card(route_card: Mapping[str, Any]) -> Dict[str, Any]:
    page_id = route_card.get("page_id") or route_card.get("source_page_id")
    source_page_id = route_card.get("source_page_id")
    primary_route = str(route_card.get("primary_route") or ROUTE_REVIEW)
    secondary_routes = list(route_card.get("secondary_routes") or [])
    review_required = bool(route_card.get("review_required"))
    safe_for_routing = bool(route_card.get("safe_for_routing"))
    dispatch_routes = _normalize_routes(primary_route, secondary_routes, review_required)

    route_policies = {route: _dispatch_policy_for_route(route, route_card) for route in ROUTE_ORDER}
    allowed_routes = [route for route, policy in route_policies.items() if policy.get("allowed")]

    # Unsafe route cards remain visible but cannot dispatch downstream.
    unsafe_dispatch_card = not safe_for_routing
    if unsafe_dispatch_card:
        allowed_routes = []
        for policy in route_policies.values():
            policy["allowed"] = False
            policy["status"] = "blocked_unsafe_route_card"
            policy.setdefault("reasons", []).append("safe_for_routing_false")

    primary_dispatch_route = primary_route if primary_route in ROUTE_ORDER else ROUTE_REVIEW
    if unsafe_dispatch_card:
        primary_dispatch_route = ROUTE_REVIEW

    dispatch_reasons: List[str] = []
    for route in allowed_routes:
        dispatch_reasons.extend(route_policies[route].get("reasons") or [])
    if not dispatch_reasons and not unsafe_dispatch_card:
        dispatch_reasons.append("route_manifest_advisory_only")

    return {
        "schema_version": SCHEMA_VERSION,
        "route_dispatch_card_id": f"route_dispatch::{_stable_id(page_id, source_page_id, primary_route)}",
        "page_id": page_id,
        "source_page_id": source_page_id,
        "page_number": route_card.get("page_number"),
        "primary_route": primary_route,
        "secondary_routes": secondary_routes,
        "primary_dispatch_route": primary_dispatch_route,
        "dispatch_routes": dispatch_routes,
        "allowed_dispatch_routes": allowed_routes,
        "route_policies": route_policies,
        "table_processing_allowed": ROUTE_TABLE in allowed_routes,
        "image_visual_processing_allowed": ROUTE_IMAGE in allowed_routes,
        "normal_text_processing_allowed": ROUTE_TEXT in allowed_routes,
        "blank_candidate_processing_allowed": ROUTE_BLANK in allowed_routes,
        "review_processing_required": ROUTE_REVIEW in allowed_routes or review_required,
        "review_required": review_required,
        "safe_for_routing": safe_for_routing,
        "unsafe_dispatch_card": unsafe_dispatch_card,
        "route_confidence": route_card.get("route_confidence"),
        "blank_score": route_card.get("blank_score"),
        "text_score": route_card.get("text_score"),
        "table_score": route_card.get("table_score"),
        "image_visual_score": route_card.get("image_visual_score"),
        "review_score": route_card.get("review_score"),
        "page_ink_route_evidence_available": route_card.get("page_ink_route_evidence_available"),
        "ink_primary_route": route_card.get("ink_primary_route"),
        "ink_route_disagreement_review_reasons": route_card.get("ink_route_disagreement_review_reasons") or [],
        "routing_reasons": route_card.get("routing_reasons") or [],
        "dispatch_reasons": sorted(set(dispatch_reasons)),
        "evidence_summary": route_card.get("evidence_summary") or {},
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }


def build_route_dispatch_manifest(
    page_route_manifest_path: Path,
    output_dir: Path,
    thresholds: Optional[RouteDispatchQualityThresholds] = None,
    write_outputs: bool = True,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    page_route_manifest = _load_json(page_route_manifest_path)
    page_route_cards = page_route_manifest.get("page_route_cards") or []
    dispatch_cards = [build_dispatch_card(card) for card in page_route_cards]

    primary_counts = Counter(str(card.get("primary_dispatch_route") or "UNKNOWN") for card in dispatch_cards)
    allowed_counts = Counter(route for card in dispatch_cards for route in (card.get("allowed_dispatch_routes") or []))
    policy_status_counts = Counter(
        policy.get("status")
        for card in dispatch_cards
        for policy in (card.get("route_policies") or {}).values()
    )

    unsafe_dispatch_card_count = sum(1 for card in dispatch_cards if card.get("unsafe_dispatch_card"))
    answer_permission_count = sum(1 for card in dispatch_cards if card.get("answer_permission") or card.get("can_answer_directly"))
    can_answer_directly_count = sum(1 for card in dispatch_cards if card.get("can_answer_directly"))
    can_prove_claims_count = sum(1 for card in dispatch_cards if card.get("can_prove_claims"))
    source_truth_mutation_allowed_count = sum(1 for card in dispatch_cards if card.get("source_truth_mutation_allowed"))

    page_route_summary = page_route_manifest.get("summary") if isinstance(page_route_manifest.get("summary"), Mapping) else {}
    page_route_quality = page_route_manifest.get("quality_status") or page_route_summary.get("quality_status")

    summary: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "TRACE_NET_ROUTE_DISPATCH_MANIFEST_BUILT",
        "quality_status": None,
        "page_route_manifest_path": str(page_route_manifest_path),
        "page_route_manifest_quality_status": page_route_quality,
        "page_route_card_count": len(page_route_cards),
        "route_dispatch_card_count": len(dispatch_cards),
        "source_page_dispatch_card_count": sum(1 for card in dispatch_cards if card.get("source_page_id")),
        "primary_route_dispatch_card_count": sum(1 for card in dispatch_cards if card.get("primary_dispatch_route")),
        "primary_dispatch_route_counts": dict(sorted(primary_counts.items())),
        "allowed_dispatch_route_counts": dict(sorted(allowed_counts.items())),
        "route_policy_status_counts": dict(sorted((str(k), v) for k, v in policy_status_counts.items())),
        "table_dispatch_card_count": allowed_counts.get(ROUTE_TABLE, 0),
        "image_visual_dispatch_card_count": allowed_counts.get(ROUTE_IMAGE, 0),
        "normal_text_dispatch_card_count": allowed_counts.get(ROUTE_TEXT, 0),
        "blank_candidate_dispatch_card_count": allowed_counts.get(ROUTE_BLANK, 0),
        "review_dispatch_card_count": allowed_counts.get(ROUTE_REVIEW, 0),
        "table_primary_dispatch_card_count": primary_counts.get(ROUTE_TABLE, 0),
        "image_visual_primary_dispatch_card_count": primary_counts.get(ROUTE_IMAGE, 0),
        "normal_text_primary_dispatch_card_count": primary_counts.get(ROUTE_TEXT, 0),
        "blank_candidate_primary_dispatch_card_count": primary_counts.get(ROUTE_BLANK, 0),
        "review_primary_dispatch_card_count": primary_counts.get(ROUTE_REVIEW, 0),
        "multi_route_dispatch_card_count": sum(1 for card in dispatch_cards if len(card.get("allowed_dispatch_routes") or []) > 1),
        "review_required_dispatch_card_count": sum(1 for card in dispatch_cards if card.get("review_processing_required")),
        "ink_disagreement_dispatch_card_count": sum(1 for card in dispatch_cards if card.get("ink_route_disagreement_review_reasons")),
        "unsafe_dispatch_card_count": unsafe_dispatch_card_count,
        "answer_permission_count": answer_permission_count,
        "can_answer_directly_count": can_answer_directly_count,
        "can_prove_claims_count": can_prove_claims_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "source_truth_mutations_performed": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }

    report: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "TRACE_NET_ROUTE_DISPATCH_MANIFEST_BUILT",
        "quality_status": None,
        "summary": summary,
        "route_dispatch_cards": dispatch_cards,
    }

    quality = evaluate_quality(report, thresholds or RouteDispatchQualityThresholds())
    report["quality_status"] = quality["quality_status"]
    summary["quality_status"] = quality["quality_status"]
    summary["quality_fail_reasons"] = quality["quality_fail_reasons"]
    summary["checks"] = quality["checks"]

    if write_outputs:
        report_path = output_dir / "trace_net_route_dispatch_manifest_v1.json"
        quality_path = output_dir / "trace_net_route_dispatch_manifest_v1_quality.json"
        summary_path = output_dir / "trace_net_route_dispatch_manifest_v1_summary.json"
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        quality_path.write_text(json.dumps(quality, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report["report_path"] = str(report_path)
        report["quality_path"] = str(quality_path)

    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Route Dispatch Manifest v1")
    parser.add_argument("--page-route-manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--min-dispatch-cards", type=int, default=1)
    parser.add_argument("--min-source-page-dispatch-cards", type=int, default=0)
    parser.add_argument("--min-primary-route-cards", type=int, default=1)
    parser.add_argument("--max-unsafe-dispatch-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-page-route-manifest-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser.parse_args(argv)


def _thresholds_from_args(args: argparse.Namespace) -> RouteDispatchQualityThresholds:
    return RouteDispatchQualityThresholds(
        min_dispatch_cards=args.min_dispatch_cards,
        min_source_page_dispatch_cards=args.min_source_page_dispatch_cards,
        min_primary_route_cards=args.min_primary_route_cards,
        max_unsafe_dispatch_cards=args.max_unsafe_dispatch_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_page_route_manifest_quality_pass=args.require_page_route_manifest_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )


def main(argv: list[str] | None = None) -> Dict[str, Any]:
    args = parse_args(argv)
    report = build_route_dispatch_manifest(
        page_route_manifest_path=Path(args.page_route_manifest),
        output_dir=Path(args.output_dir),
        thresholds=_thresholds_from_args(args),
    )
    summary = report.get("summary", {})
    print("TRACE-Net Route Dispatch Manifest v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "route_dispatch_card_count",
        "source_page_dispatch_card_count",
        "primary_route_dispatch_card_count",
        "table_dispatch_card_count",
        "image_visual_dispatch_card_count",
        "normal_text_dispatch_card_count",
        "blank_candidate_dispatch_card_count",
        "review_dispatch_card_count",
        "multi_route_dispatch_card_count",
        "review_required_dispatch_card_count",
        "unsafe_dispatch_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    if report.get("report_path"):
        print(f" report_path: {report.get('report_path')}")
        print(f" quality_path: {report.get('quality_path')}")
    return report


if __name__ == "__main__":
    main()
