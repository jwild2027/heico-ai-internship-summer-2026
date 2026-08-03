"""TRACE-Net Fishnet Router Hardening Policy v1.

Read-only policy builder that converts fishnet route-review records into
conservative router hardening recommendations.

This module does not change the official route manifest. It does not write to
Postgres, Qdrant, OpenSearch, or source-truth files. It only emits a policy
artifact that downstream humans or route-hardening tools can review.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

MODULE_VERSION = "trace_net_fishnet_router_hardening_policy_v1"
DEFAULT_CURRENT_ROUTES = ("blank_candidate", "image_visual")
DEFAULT_TARGET_ROUTE = "normal_text"


SAFETY_CONTRACT: dict[str, Any] = {
    "artifact_authority": "router_hardening_policy_recommendation_only",
    "can_answer_directly": False,
    "can_prove_claims": False,
    "answer_permission": False,
    "source_truth_mutation_allowed": False,
    "route_change_authorized": False,
    "route_manifest_write_allowed": False,
    "postgres_write_allowed": False,
    "qdrant_write_allowed": False,
    "opensearch_write_allowed": False,
    "raw_scan_query_time_allowed": False,
    "requires_human_or_visual_review_before_route_manifest_change": True,
    "guidance_only": True,
}


@dataclass(frozen=True)
class PolicyThresholds:
    min_confidence: float = 0.85
    min_ocr_text_chars: int = 500
    min_ocr_word_boxes: int = 100
    promote_current_routes: tuple[str, ...] = DEFAULT_CURRENT_ROUTES
    target_route: str = DEFAULT_TARGET_ROUTE


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _has_unsafe_authority(record: dict[str, Any]) -> bool:
    return any(
        bool(record.get(key))
        for key in (
            "answer_permission",
            "can_answer_directly",
            "can_prove_claims",
            "source_truth_mutation_allowed",
            "route_change_authorized",
        )
    )


def _review_reasons(record: dict[str, Any]) -> list[str]:
    reasons = record.get("fishnet_review_reason_codes") or record.get("review_reasons") or []
    if isinstance(reasons, str):
        return [reasons]
    if isinstance(reasons, list):
        return [str(item) for item in reasons]
    return []


def evaluate_record(record: dict[str, Any], thresholds: PolicyThresholds) -> tuple[bool, list[str]]:
    """Return (selected, reason_codes) for a single review-packet record."""
    reasons: list[str] = []

    current_route = record.get("current_route")
    fishnet_route = record.get("fishnet_route_candidate")
    confidence = _as_float(record.get("fishnet_route_confidence"))
    text_chars = _as_int(record.get("fishnet_ocr_text_length"))
    word_boxes = _as_int(record.get("fishnet_ocr_word_box_count"))
    fishnet_review_required = bool(record.get("fishnet_review_required"))
    record_reasons = _review_reasons(record)

    if _has_unsafe_authority(record):
        reasons.append("blocked_unsafe_authority_field")
    if current_route not in thresholds.promote_current_routes:
        reasons.append("current_route_not_promotion_source")
    if fishnet_route != thresholds.target_route:
        reasons.append("fishnet_route_not_target")
    if confidence < thresholds.min_confidence:
        reasons.append("fishnet_confidence_below_threshold")
    if text_chars < thresholds.min_ocr_text_chars:
        reasons.append("ocr_text_below_threshold")
    if word_boxes < thresholds.min_ocr_word_boxes:
        reasons.append("ocr_word_boxes_below_threshold")
    if fishnet_review_required:
        reasons.append("fishnet_already_requires_review")
    if "table_text_tie" in record_reasons:
        reasons.append("table_text_tie_not_auto_promotable")
    if "low_route_margin" in record_reasons:
        reasons.append("low_route_margin_not_auto_promotable")

    selected = not reasons
    if selected:
        reasons.append("normal_text_review_promotion_candidate")
    return selected, reasons


def build_policy_record(record: dict[str, Any], reason_codes: list[str]) -> dict[str, Any]:
    current_route = record.get("current_route")
    fishnet_route = record.get("fishnet_route_candidate")
    route_pair = f"{current_route}->{fishnet_route}"
    confidence = _as_float(record.get("fishnet_route_confidence"))
    priority = "high" if confidence >= 0.90 else "medium"
    if record.get("agreement_status") == "high_confidence_disagreement":
        priority = "high"

    return {
        "policy_version": MODULE_VERSION,
        "page_id": record.get("page_id"),
        "current_route_page_id": record.get("current_route_page_id"),
        "current_route": current_route,
        "fishnet_route_candidate": fishnet_route,
        "fishnet_best_route_candidate_before_review": record.get("fishnet_best_route_candidate_before_review"),
        "recommended_target_route": "normal_text",
        "recommendation_type": "normal_text_review_promotion",
        "recommendation_status": "review_required_before_route_manifest_change",
        "review_priority": priority,
        "route_pair": route_pair,
        "agreement_status": record.get("agreement_status"),
        "selection_reason": record.get("selection_reason"),
        "policy_reason_codes": reason_codes,
        "fishnet_route_confidence": confidence,
        "fishnet_ocr_text_length": _as_int(record.get("fishnet_ocr_text_length")),
        "fishnet_ocr_word_count": _as_int(record.get("fishnet_ocr_word_count")),
        "fishnet_ocr_word_box_count": _as_int(record.get("fishnet_ocr_word_box_count")),
        "fishnet_ocr_sample_text": record.get("fishnet_ocr_sample_text") or "",
        "fishnet_route_scores": record.get("fishnet_route_scores") or {},
        "fishnet_route_adjusted_scores": record.get("fishnet_route_adjusted_scores") or {},
        "fishnet_review_reason_codes": _review_reasons(record),
        "overlay_candidates": record.get("overlay_candidates") or [],
        "route_change_authorized": False,
        "route_manifest_write_allowed": False,
        "official_route_manifest_mutation_allowed": False,
        "safety_contract": dict(SAFETY_CONTRACT),
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }


def summarize(
    *,
    source_payload: dict[str, Any],
    records: list[dict[str, Any]],
    evaluated_record_count: int,
    blocked_counts: Counter[str],
    thresholds: PolicyThresholds,
) -> dict[str, Any]:
    safety_keys = (
        "answer_permission",
        "can_answer_directly",
        "can_prove_claims",
        "source_truth_mutation_allowed",
        "route_change_authorized",
    )
    summary = {
        "source_review_packet_quality_status": source_payload.get("quality_status"),
        "source_review_record_count": len(source_payload.get("records") or []),
        "evaluated_review_record_count": evaluated_record_count,
        "policy_record_count": len(records),
        "normal_text_review_promotion_count": sum(1 for r in records if r.get("recommendation_type") == "normal_text_review_promotion"),
        "policy_record_route_pair_counts": dict(Counter(r.get("route_pair") for r in records)),
        "policy_record_current_route_counts": dict(Counter(r.get("current_route") for r in records)),
        "policy_record_target_route_counts": dict(Counter(r.get("recommended_target_route") for r in records)),
        "policy_record_review_priority_counts": dict(Counter(r.get("review_priority") for r in records)),
        "blocked_reason_counts": dict(blocked_counts),
        "min_confidence": thresholds.min_confidence,
        "min_ocr_text_chars": thresholds.min_ocr_text_chars,
        "min_ocr_word_boxes": thresholds.min_ocr_word_boxes,
        "promote_current_routes": list(thresholds.promote_current_routes),
        "target_route": thresholds.target_route,
        "unsafe_record_count": 0,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "route_change_authorized_count": 0,
        "route_manifest_write_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }
    for key in safety_keys:
        summary[f"{key}_count"] = sum(1 for record in records if record.get(key))
    summary["route_manifest_write_allowed_count"] = sum(1 for record in records if record.get("route_manifest_write_allowed"))
    return summary


def render_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    summary = payload.get("summary") or {}
    records = payload.get("records") or []
    lines.append("# TRACE-Net Fishnet Router Hardening Policy v1")
    lines.append("")
    lines.append(f"Quality status: **{payload.get('quality_status')}**")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Policy records: {summary.get('policy_record_count', 0)}")
    lines.append(f"- Normal-text review promotions: {summary.get('normal_text_review_promotion_count', 0)}")
    lines.append(f"- Route changes authorized: {summary.get('route_change_authorized_count', 0)}")
    lines.append(f"- Source-truth mutation allowed: {summary.get('source_truth_mutation_allowed_count', 0)}")
    lines.append("")
    lines.append("## Policy records")
    for record in records:
        lines.append("")
        lines.append(f"### {record.get('page_id')} — {record.get('route_pair')}")
        lines.append("")
        lines.append(f"- Recommendation: `{record.get('recommendation_type')}`")
        lines.append(f"- Status: `{record.get('recommendation_status')}`")
        lines.append(f"- Priority: `{record.get('review_priority')}`")
        lines.append(f"- Current route: `{record.get('current_route')}`")
        lines.append(f"- Recommended target route: `{record.get('recommended_target_route')}`")
        lines.append(f"- Confidence: `{record.get('fishnet_route_confidence')}`")
        lines.append(f"- OCR text length: `{record.get('fishnet_ocr_text_length')}`")
        lines.append(f"- OCR word boxes: `{record.get('fishnet_ocr_word_box_count')}`")
        lines.append(f"- Route change authorized: `{record.get('route_change_authorized')}`")
        lines.append(f"- Overlay candidates: `{record.get('overlay_candidates')}`")
        sample = (record.get("fishnet_ocr_sample_text") or "").strip()
        if sample:
            lines.append("")
            lines.append(f"> {sample[:350]}")
    lines.append("")
    return "\n".join(lines)


def build_fishnet_router_hardening_policy(
    *,
    review_packet_path: Path,
    output_dir: Path,
    thresholds: PolicyThresholds,
) -> dict[str, Any]:
    source_payload = _read_json(review_packet_path)
    source_records = source_payload.get("records") or []
    selected_records: list[dict[str, Any]] = []
    blocked_counts: Counter[str] = Counter()

    for source_record in source_records:
        selected, reasons = evaluate_record(source_record, thresholds)
        if selected:
            selected_records.append(build_policy_record(source_record, reasons))
        else:
            blocked_counts.update(reasons)

    summary = summarize(
        source_payload=source_payload,
        records=selected_records,
        evaluated_record_count=len(source_records),
        blocked_counts=blocked_counts,
        thresholds=thresholds,
    )
    quality_status = "PASS" if summary["unsafe_record_count"] == 0 and summary["route_change_authorized_count"] == 0 else "FAIL"
    payload = {
        "module": MODULE_VERSION,
        "status": "FISHNET_ROUTER_HARDENING_POLICY_BUILT",
        "quality_status": quality_status,
        "source_review_packet_path": str(review_packet_path),
        "summary": summary,
        "records": selected_records,
        "safety_contract": dict(SAFETY_CONTRACT),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_fishnet_router_hardening_policy_v1.json"
    _write_json(report_path, payload)
    _write_jsonl(output_dir / "trace_net_fishnet_router_hardening_policy_v1_records.jsonl", selected_records)
    _write_json(output_dir / "trace_net_fishnet_router_hardening_policy_v1_summary.json", summary)
    _write_json(output_dir / "trace_net_fishnet_router_hardening_policy_v1_quality.json", {"quality_status": quality_status, "summary": summary})
    (output_dir / "trace_net_fishnet_router_hardening_policy_v1.md").write_text(render_markdown(payload), encoding="utf-8")
    return payload


def check_policy_quality(
    *,
    report_path: Path,
    min_policy_records: int = 1,
    min_normal_text_review_promotions: int = 1,
    max_unsafe: int = 0,
    max_route_change_authorized: int = 0,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_route_manifest_write: bool = False,
    require_source_review_packet_quality_pass: bool = False,
) -> dict[str, Any]:
    payload = _read_json(report_path)
    summary = payload.get("summary") or {}
    failures: list[str] = []

    if _as_int(summary.get("policy_record_count")) < min_policy_records:
        failures.append("policy_record_count_below_min")
    if _as_int(summary.get("normal_text_review_promotion_count")) < min_normal_text_review_promotions:
        failures.append("normal_text_review_promotion_count_below_min")
    if _as_int(summary.get("unsafe_record_count")) > max_unsafe:
        failures.append("unsafe_record_count_above_max")
    if _as_int(summary.get("route_change_authorized_count")) > max_route_change_authorized:
        failures.append("route_change_authorized_count_above_max")
    if require_no_answer_permission and _as_int(summary.get("answer_permission_count")) != 0:
        failures.append("answer_permission_count_not_zero")
    if require_no_source_truth_mutation and _as_int(summary.get("source_truth_mutation_allowed_count")) != 0:
        failures.append("source_truth_mutation_allowed_count_not_zero")
    if require_no_route_manifest_write and _as_int(summary.get("route_manifest_write_allowed_count")) != 0:
        failures.append("route_manifest_write_allowed_count_not_zero")
    if require_source_review_packet_quality_pass and summary.get("source_review_packet_quality_status") != "PASS":
        failures.append("source_review_packet_quality_not_pass")

    quality_status = "PASS" if not failures else "FAIL"
    result = {
        "module": MODULE_VERSION,
        "status": "FISHNET_ROUTER_HARDENING_POLICY_QUALITY_CHECKED",
        "quality_status": quality_status,
        "failures": failures,
        "summary": summary,
    }
    return result


def main_build(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net fishnet router hardening policy v1.")
    parser.add_argument("--review-packet", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--min-confidence", type=float, default=0.85)
    parser.add_argument("--min-ocr-text-chars", type=int, default=500)
    parser.add_argument("--min-ocr-word-boxes", type=int, default=100)
    parser.add_argument("--promote-current-routes", default=",".join(DEFAULT_CURRENT_ROUTES))
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    promote_routes = tuple(part.strip() for part in args.promote_current_routes.split(",") if part.strip())
    thresholds = PolicyThresholds(
        min_confidence=args.min_confidence,
        min_ocr_text_chars=args.min_ocr_text_chars,
        min_ocr_word_boxes=args.min_ocr_word_boxes,
        promote_current_routes=promote_routes,
    )
    payload = build_fishnet_router_hardening_policy(
        review_packet_path=args.review_packet,
        output_dir=args.output_dir,
        thresholds=thresholds,
    )
    print("Status:", payload["status"])
    print("Quality status:", payload["quality_status"])
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["quality_status"] == "PASS" else 1


def main_check(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net fishnet router hardening policy v1 quality.")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-policy-records", type=int, default=1)
    parser.add_argument("--min-normal-text-review-promotions", type=int, default=1)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--max-route-change-authorized", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-route-manifest-write", action="store_true")
    parser.add_argument("--require-source-review-packet-quality-pass", action="store_true")
    args = parser.parse_args(argv)

    result = check_policy_quality(
        report_path=args.report_path,
        min_policy_records=args.min_policy_records,
        min_normal_text_review_promotions=args.min_normal_text_review_promotions,
        max_unsafe=args.max_unsafe,
        max_route_change_authorized=args.max_route_change_authorized,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_route_manifest_write=args.require_no_route_manifest_write,
        require_source_review_packet_quality_pass=args.require_source_review_packet_quality_pass,
    )
    print("Quality status:", result["quality_status"])
    print("Summary:", json.dumps(result["summary"], sort_keys=True))
    if result["failures"]:
        print("Failures:", json.dumps(result["failures"], sort_keys=True))
    if args.write_json:
        out = args.report_path.with_name("trace_net_fishnet_router_hardening_policy_v1_quality_check.json")
        _write_json(out, result)
        print("Wrote:", out)
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main_build())
