from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from tiff.trace_net_route_dispatch_coverage_audit_v1_quality import (
    PASS,
    SCHEMA_VERSION,
    RouteDispatchCoverageAuditQualityThresholds,
    evaluate_quality,
)

STATUS_BUILT = "TRACE_NET_ROUTE_DISPATCH_COVERAGE_AUDIT_BUILT"
QUALITY_SCHEMA_VERSION = "trace_net_route_dispatch_coverage_audit_v1_quality"

CATEGORY_TO_ALLOWED_FLAG = {
    "table": "table_processing_allowed",
    "image_visual": "image_visual_processing_allowed",
    "ocr_text": "normal_text_processing_allowed",
    "retrieval_answer": "normal_text_processing_allowed",
}
HEAVY_EVIDENCE_CATEGORIES = {"table", "image_visual", "ocr_text", "retrieval_answer"}


def _safe_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _page_key(card: Mapping[str, Any]) -> Optional[str]:
    for key in ("page_id", "canonical_page_id", "target_page_id"):
        value = card.get(key)
        if value:
            return str(value)
    return None


def _page_number(card: Mapping[str, Any]) -> Optional[int]:
    for key in ("page_number", "source_page_number"):
        value = card.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    return None


def _counter_from_mapping(value: Any) -> Counter:
    counter: Counter = Counter()
    if isinstance(value, Mapping):
        for k, v in value.items():
            counter[str(k)] += _safe_int(v)
    return counter


def _artifact_counts_from_page_card(card: Mapping[str, Any]) -> Counter:
    counts = _counter_from_mapping(card.get("evidence_category_counts"))
    known = {
        "table": "table_evidence_artifact_count",
        "image_visual": "image_visual_evidence_artifact_count",
        "ocr_text": "ocr_text_evidence_artifact_count",
        "human_review": "human_review_evidence_artifact_count",
    }
    for category, key in known.items():
        value = _safe_int(card.get(key))
        if value:
            counts[category] = max(counts.get(category, 0), value)
    return counts


def _index_dispatch_cards(route_dispatch_manifest: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    cards = route_dispatch_manifest.get("route_dispatch_cards") or []
    by_page: Dict[str, Mapping[str, Any]] = {}
    for card in cards:
        if not isinstance(card, Mapping):
            continue
        page_id = _page_key(card)
        if page_id:
            by_page[page_id] = card
    return by_page


def _dispatch_aliases(card: Mapping[str, Any]) -> List[str]:
    aliases: List[str] = []
    for key in ("page_id", "source_page_id"):
        value = card.get(key)
        if value:
            aliases.append(str(value))

    page_number = _page_number(card)
    if page_number is not None:
        aliases.append(f"metadata_page_{page_number:06d}")
        aliases.append(f"t_p_120_1176_p{page_number:06d}")

    return list(dict.fromkeys(alias for alias in aliases if alias))


def _index_dispatch_cards_by_alias(route_dispatch_manifest: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    lookup: Dict[str, Mapping[str, Any]] = {}
    for card in route_dispatch_manifest.get("route_dispatch_cards") or []:
        if not isinstance(card, Mapping):
            continue
        for alias in _dispatch_aliases(card):
            lookup.setdefault(alias, card)
    return lookup


def _index_page_artifact_cards(artifact_detector: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    cards = artifact_detector.get("page_artifact_cards") or []
    by_page: Dict[str, Mapping[str, Any]] = {}
    for card in cards:
        if not isinstance(card, Mapping):
            continue
        page_id = _page_key(card)
        if page_id:
            by_page[page_id] = card
    return by_page


def _artifact_category_index(artifact_detector: Mapping[str, Any]) -> Dict[str, Counter]:
    # Optional artifact-level evidence index. Some artifact detector builds only
    # provide page-level category counts, but when artifact cards carry page_ids
    # this gives us a second lens for audit debugging.
    page_to_categories: Dict[str, Counter] = defaultdict(Counter)
    for card in artifact_detector.get("artifact_cards") or []:
        if not isinstance(card, Mapping):
            continue
        if not card.get("safe_for_routing"):
            continue
        category = str(card.get("evidence_category") or "general")
        page_ids = card.get("page_ids") or card.get("artifact_page_ids") or []
        if not isinstance(page_ids, list):
            continue
        for page_id in page_ids:
            if page_id:
                page_to_categories[str(page_id)][category] += 1
    return page_to_categories


def _build_coverage_card(
    page_id: str,
    dispatch_card: Optional[Mapping[str, Any]],
    page_artifact_card: Optional[Mapping[str, Any]],
    artifact_category_counts: Optional[Counter] = None,
) -> Dict[str, Any]:
    dispatch_card = dispatch_card or {}
    page_artifact_card = page_artifact_card or {}
    counts = _artifact_counts_from_page_card(page_artifact_card)
    if artifact_category_counts:
        for category, value in artifact_category_counts.items():
            counts[category] = max(counts.get(category, 0), value)

    violations: List[str] = []
    warnings: List[str] = []
    advisory: List[str] = []

    safe_dispatch = bool(dispatch_card.get("safe_for_routing")) if dispatch_card else False
    unsafe_audit_card = not safe_dispatch
    if not dispatch_card:
        violations.append("missing_route_dispatch_card")
    if not safe_dispatch:
        violations.append("route_dispatch_not_safe_for_routing")

    for category, allowed_flag in CATEGORY_TO_ALLOWED_FLAG.items():
        evidence_count = _safe_int(counts.get(category))
        if evidence_count <= 0:
            continue
        allowed = bool(dispatch_card.get(allowed_flag))
        if not allowed:
            # OCR/retrieval text evidence is often embedded inside table/visual
            # work. Treat it as advisory unless the page is blank-only.
            if category in {"ocr_text", "retrieval_answer"}:
                warnings.append(f"{category}_artifact_without_explicit_text_dispatch")
            else:
                violations.append(f"{category}_artifact_without_allowed_dispatch")

    heavy_count = sum(_safe_int(counts.get(category)) for category in HEAVY_EVIDENCE_CATEGORIES)
    if bool(dispatch_card.get("blank_candidate_processing_allowed")) and heavy_count > 0:
        warnings.append("blank_candidate_has_heavy_processing_evidence")

    if bool(dispatch_card.get("review_processing_required")):
        advisory.append("route_dispatch_requires_review")
    if dispatch_card.get("allowed_dispatch_routes") and len(dispatch_card.get("allowed_dispatch_routes") or []) > 1:
        advisory.append("multi_route_dispatch")

    compliance_status = "PASS"
    if violations:
        compliance_status = "VIOLATION"
    elif warnings:
        compliance_status = "WARNING"
    elif advisory:
        compliance_status = "REVIEW"

    return {
        "schema_version": SCHEMA_VERSION,
        "page_id": page_id,
        "page_number": _page_number(dispatch_card) or _page_number(page_artifact_card),
        "primary_route": dispatch_card.get("primary_route"),
        "primary_dispatch_route": dispatch_card.get("primary_dispatch_route"),
        "allowed_dispatch_routes": list(dispatch_card.get("allowed_dispatch_routes") or []),
        "table_processing_allowed": bool(dispatch_card.get("table_processing_allowed")),
        "image_visual_processing_allowed": bool(dispatch_card.get("image_visual_processing_allowed")),
        "normal_text_processing_allowed": bool(dispatch_card.get("normal_text_processing_allowed")),
        "blank_candidate_processing_allowed": bool(dispatch_card.get("blank_candidate_processing_allowed")),
        "review_processing_required": bool(dispatch_card.get("review_processing_required")),
        "safe_for_routing": safe_dispatch,
        "unsafe_audit_card": unsafe_audit_card,
        "route_dispatch_coverage_status": compliance_status,
        "route_dispatch_violations": violations,
        "route_dispatch_warnings": warnings,
        "route_dispatch_advisory_flags": advisory,
        "artifact_evidence_category_counts": dict(sorted(counts.items())),
        "table_evidence_artifact_count": _safe_int(counts.get("table")),
        "image_visual_evidence_artifact_count": _safe_int(counts.get("image_visual")),
        "ocr_text_evidence_artifact_count": _safe_int(counts.get("ocr_text")),
        "retrieval_answer_evidence_artifact_count": _safe_int(counts.get("retrieval_answer")),
        "human_review_evidence_artifact_count": _safe_int(counts.get("human_review")),
        "artifact_key_count": len(page_artifact_card.get("artifact_keys") or []) if isinstance(page_artifact_card.get("artifact_keys"), list) else _safe_int(page_artifact_card.get("artifact_count")),
        "dispatch_reasons": list(dispatch_card.get("dispatch_reasons") or []),
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
    }


def build_route_dispatch_coverage_audit_report(
    route_dispatch_manifest_path: Path,
    artifact_detector_path: Path,
    output_dir: Path,
    thresholds: Optional[RouteDispatchCoverageAuditQualityThresholds] = None,
    write_outputs: bool = True,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    route_dispatch_manifest = _read_json(route_dispatch_manifest_path)
    artifact_detector = _read_json(artifact_detector_path)

    dispatch_by_page = _index_dispatch_cards(route_dispatch_manifest)
    dispatch_by_alias = _index_dispatch_cards_by_alias(route_dispatch_manifest)
    page_artifacts_by_page = _index_page_artifact_cards(artifact_detector)
    artifact_category_by_page = _artifact_category_index(artifact_detector)

    all_page_ids = sorted(set(dispatch_by_page) | set(page_artifacts_by_page) | set(artifact_category_by_page))
    coverage_cards = [
        _build_coverage_card(
            page_id,
            dispatch_by_alias.get(page_id) or dispatch_by_page.get(page_id),
            page_artifacts_by_page.get(page_id),
            artifact_category_by_page.get(page_id),
        )
        for page_id in all_page_ids
    ]

    status_counts = Counter(str(card.get("route_dispatch_coverage_status")) for card in coverage_cards)
    route_counts = Counter(route for card in coverage_cards for route in (card.get("allowed_dispatch_routes") or []))
    violation_counts = Counter(v for card in coverage_cards for v in (card.get("route_dispatch_violations") or []))
    warning_counts = Counter(w for card in coverage_cards for w in (card.get("route_dispatch_warnings") or []))
    advisory_counts = Counter(a for card in coverage_cards for a in (card.get("route_dispatch_advisory_flags") or []))

    summary: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "route_dispatch_manifest_path": str(route_dispatch_manifest_path),
        "artifact_detector_path": str(artifact_detector_path),
        "route_dispatch_manifest_quality_status": route_dispatch_manifest.get("quality_status"),
        "artifact_detector_quality_status": artifact_detector.get("quality_status"),
        "dispatch_coverage_card_count": len(coverage_cards),
        "route_dispatch_card_count": len(route_dispatch_manifest.get("route_dispatch_cards") or []),
        "audited_page_artifact_card_count": len(page_artifacts_by_page),
        "page_with_dispatch_card_count": len(dispatch_by_page),
        "page_with_artifact_evidence_count": len(page_artifacts_by_page),
        "route_dispatch_violation_card_count": sum(1 for card in coverage_cards if card.get("route_dispatch_violations")),
        "route_dispatch_warning_card_count": sum(1 for card in coverage_cards if card.get("route_dispatch_warnings")),
        "blank_heavy_processing_warning_card_count": sum(1 for card in coverage_cards if "blank_candidate_has_heavy_processing_evidence" in (card.get("route_dispatch_warnings") or [])),
        "review_required_audit_card_count": sum(1 for card in coverage_cards if card.get("review_processing_required")),
        "multi_route_audit_card_count": sum(1 for card in coverage_cards if len(card.get("allowed_dispatch_routes") or []) > 1),
        "unsafe_audit_card_count": sum(1 for card in coverage_cards if card.get("unsafe_audit_card")),
        "table_artifact_without_dispatch_allowed_count": violation_counts.get("table_artifact_without_allowed_dispatch", 0),
        "image_visual_artifact_without_dispatch_allowed_count": violation_counts.get("image_visual_artifact_without_allowed_dispatch", 0),
        "ocr_text_artifact_without_explicit_text_dispatch_warning_count": warning_counts.get("ocr_text_artifact_without_explicit_text_dispatch", 0),
        "allowed_dispatch_route_counts": dict(sorted(route_counts.items())),
        "coverage_status_counts": dict(sorted(status_counts.items())),
        "violation_reason_counts": dict(sorted(violation_counts.items())),
        "warning_reason_counts": dict(sorted(warning_counts.items())),
        "advisory_reason_counts": dict(sorted(advisory_counts.items())),
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "source_truth_mutations_performed": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }

    report: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "quality_status": PASS,
        "summary": summary,
        "route_dispatch_coverage_cards": coverage_cards,
    }

    quality = evaluate_quality(report, thresholds)
    report["quality_status"] = quality["quality_status"]
    report["summary"]["quality_status"] = quality["quality_status"]
    report["summary"]["quality_fail_reasons"] = quality.get("quality_fail_reasons", [])
    report["summary"]["checks"] = quality.get("checks", {})

    if write_outputs:
        report_path = output_dir / "trace_net_route_dispatch_coverage_audit_v1.json"
        quality_path = output_dir / "trace_net_route_dispatch_coverage_audit_v1_quality.json"
        summary_path = output_dir / "trace_net_route_dispatch_coverage_audit_v1_summary.json"
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        quality_path.write_text(json.dumps(quality, indent=2, sort_keys=True), encoding="utf-8")
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    return report


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Route Dispatch Coverage Audit v1")
    parser.add_argument("--route-dispatch-manifest", required=True, type=Path)
    parser.add_argument("--artifact-detector", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--min-dispatch-coverage-cards", type=int, default=1)
    parser.add_argument("--min-audited-page-artifact-cards", type=int, default=1)
    parser.add_argument("--max-unsafe-audit-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-route-dispatch-manifest-quality-pass", action="store_true")
    parser.add_argument("--require-artifact-detector-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> Dict[str, Any]:
    args = _parse_args(argv)
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
    report = build_route_dispatch_coverage_audit_report(
        route_dispatch_manifest_path=args.route_dispatch_manifest,
        artifact_detector_path=args.artifact_detector,
        output_dir=args.output_dir,
        thresholds=thresholds,
    )
    summary = report.get("summary", {})

    print("TRACE-Net Route Dispatch Coverage Audit v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "dispatch_coverage_card_count",
        "route_dispatch_card_count",
        "audited_page_artifact_card_count",
        "route_dispatch_violation_card_count",
        "route_dispatch_warning_card_count",
        "blank_heavy_processing_warning_card_count",
        "review_required_audit_card_count",
        "multi_route_audit_card_count",
        "table_artifact_without_dispatch_allowed_count",
        "image_visual_artifact_without_dispatch_allowed_count",
        "ocr_text_artifact_without_explicit_text_dispatch_warning_count",
        "unsafe_audit_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {args.output_dir / 'trace_net_route_dispatch_coverage_audit_v1.json'}")
    print(f" quality_path: {args.output_dir / 'trace_net_route_dispatch_coverage_audit_v1_quality.json'}")
    return report


if __name__ == "__main__":
    main()
