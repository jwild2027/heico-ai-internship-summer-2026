"""TRACE-Net Table Crop Completeness Guard v1.

Read-only advisory guard for table crop completeness.  It checks whether crop
candidates used by table geometry are safe to trust as full-table crops before
production morphology selection is relaxed.  It never grants answer authority
and never mutates source truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_table_crop_completeness_guard_v1"
QUALITY_SCHEMA_VERSION = "trace_net_table_crop_completeness_guard_v1_quality"

SAFETY_CONTRACT = {
    "read_only_guard": True,
    "no_postgres_writes": True,
    "no_qdrant_writes": True,
    "no_opensearch_writes": True,
    "no_source_truth_mutation": True,
    "no_answer_permission": True,
    "can_answer_directly": False,
    "can_prove_claims": False,
}

SAFE_VERDICTS = {"ESTIMATOR_LINES_REAL_TABLE_RULES"}
UNSAFE_OR_UNKNOWN_VERDICTS = {
    "UNREVIEWED",
    "ESTIMATOR_LINES_TEXT_OR_NOISE",
    "MIXED_OR_UNCLEAR",
    None,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True))
            f.write("\n")


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def stable_id(*parts: Any) -> str:
    text = "::".join(str(p) for p in parts if p is not None)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def card_key(card: dict[str, Any]) -> tuple[str | None, str | None]:
    return card.get("page_id"), card.get("table_id")


def index_cards(payload: dict[str, Any], names: list[str]) -> dict[tuple[str | None, str | None], dict[str, Any]]:
    records: list[Any] = []
    for name in names:
        records = as_list(payload.get(name))
        if records:
            break
    out: dict[tuple[str | None, str | None], dict[str, Any]] = {}
    for record in records:
        if isinstance(record, dict):
            out[card_key(record)] = record
    return out


def first_bbox(card: dict[str, Any]) -> dict[str, Any] | None:
    for key in (
        "table_region_bbox",
        "resolved_table_region_bbox",
        "crop_bbox",
        "bbox",
        "inferred_table_region_bbox",
    ):
        value = card.get(key)
        if isinstance(value, dict):
            return value
    return None




def full_region_is_too_page_like(card: dict[str, Any] | None, max_ratio: float) -> bool:
    if not isinstance(card, dict):
        return False
    if bool(card.get("recovered_bbox_too_page_like")):
        return True
    coverage = safe_float(card.get("full_table_coverage_ratio"), -1.0)
    return coverage >= 0 and coverage > max_ratio


def nested_crop_comparison(geometry_card: dict[str, Any]) -> dict[str, Any]:
    value = geometry_card.get("table_region_crop_comparison")
    return value if isinstance(value, dict) else {}


def full_region_meets_selection_gate(
    *,
    geometry_card: dict[str, Any],
    full_region_card: dict[str, Any] | None,
    review_verdict: str | None,
    thresholds: dict[str, Any],
) -> tuple[bool, list[str], list[str]]:
    """Return whether recovered full-table region can unblock crop selection.

    This is intentionally conservative. It only allows a recovered crop candidate
    when full-region recovery says the bbox is ready, it is not page-like, and
    the morphology observed on that recovered crop shows real grid evidence.
    It still never grants answer or proof authority.
    """
    reasons: list[str] = []
    actions: list[str] = []
    if not thresholds.get("allow_full_region_recovery_ready_selection"):
        reasons.append("full_region_recovery_ready_selection_not_enabled")
        actions.append("enable_full_region_recovery_ready_selection_only_after_preview_review")
        return False, reasons, actions
    if not isinstance(full_region_card, dict):
        reasons.append("full_region_recovery_card_missing")
        actions.append("build_table_full_region_recovery_before_unblocking_crop_selection")
        return False, reasons, actions
    if not full_region_card.get("crop_recovery_ready"):
        reasons.append("full_region_recovery_not_ready")
        actions.append("tighten_or_review_full_table_region_recovery_before_crop_selection")
        return False, reasons, actions
    max_ratio = safe_float(thresholds.get("max_full_region_coverage_ratio"), 0.95)
    if full_region_is_too_page_like(full_region_card, max_ratio):
        reasons.append("full_region_recovery_too_page_like")
        actions.append("tighten_full_table_recovery_bbox_before_crop_selection")
        return False, reasons, actions
    if review_verdict == "ESTIMATOR_LINES_TEXT_OR_NOISE":
        reasons.append("human_review_labeled_estimator_lines_as_noise")
        actions.append("keep_production_morphology_conservative_for_noise_labeled_crop")
        return False, reasons, actions

    signal = geometry_card.get("morphology_signal_strength")
    vertical = safe_int(geometry_card.get("vertical_line_count"))
    intersections = safe_int(geometry_card.get("intersection_count"))
    comp = nested_crop_comparison(geometry_card)
    vertical_gain = safe_int(comp.get("crop_vertical_line_gain"))
    intersection_gain = safe_int(comp.get("crop_intersection_gain"))
    used_for_crop = bool(geometry_card.get("table_full_region_recovery_used_for_crop"))

    if not used_for_crop:
        reasons.append("full_region_recovery_not_used_for_crop_test")
        actions.append("rebuild_table_line_geometry_with_full_region_recovery")
    if signal_rank(signal) < 3:
        reasons.append("full_region_crop_did_not_produce_grid_signal")
        actions.append("keep_page_morphology_selected_until_recovered_crop_has_grid_signal")
    if vertical <= 0:
        reasons.append("full_region_crop_has_no_vertical_lines")
        actions.append("do_not_use_full_region_crop_as_column_boundary_authority")
    if intersections <= 0:
        reasons.append("full_region_crop_has_no_intersections")
        actions.append("do_not_use_full_region_crop_as_cell_boundary_authority")
    if vertical_gain <= 0 and intersection_gain <= 0:
        reasons.append("full_region_crop_has_no_vertical_or_intersection_gain")
        actions.append("require_recovered_crop_grid_gain_before_selection")

    return not reasons, reasons, actions


def bbox_metrics(bbox: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(bbox, dict):
        return {
            "bbox_present": False,
            "bbox_width": None,
            "bbox_height": None,
            "bbox_area": None,
            "bbox_page_coverage_ratio": None,
            "bbox_width_coverage_ratio": None,
            "bbox_height_coverage_ratio": None,
            "bbox_touches_top": None,
            "bbox_touches_bottom": None,
            "bbox_touches_left": None,
            "bbox_touches_right": None,
        }

    x0 = safe_float(bbox.get("x0"))
    y0 = safe_float(bbox.get("y0"))
    x1 = safe_float(bbox.get("x1"))
    y1 = safe_float(bbox.get("y1"))
    page_w = safe_float(bbox.get("image_width") or bbox.get("page_width") or bbox.get("width"))
    page_h = safe_float(bbox.get("image_height") or bbox.get("page_height") or bbox.get("height"))
    # Some existing artifacts store bbox.width/bbox.height as page dimensions.
    # If x1/y1 are smaller than width/height, treat width/height as page dims.
    bbox_w = max(0.0, x1 - x0)
    bbox_h = max(0.0, y1 - y0)
    area = bbox_w * bbox_h
    coverage = None
    width_cov = None
    height_cov = None
    if page_w > 0 and page_h > 0:
        coverage = area / (page_w * page_h) if page_w * page_h else None
        width_cov = bbox_w / page_w if page_w else None
        height_cov = bbox_h / page_h if page_h else None
    return {
        "bbox_present": True,
        "bbox_width": round(bbox_w, 6),
        "bbox_height": round(bbox_h, 6),
        "bbox_area": round(area, 6),
        "bbox_page_width": page_w or None,
        "bbox_page_height": page_h or None,
        "bbox_page_coverage_ratio": round(coverage, 6) if coverage is not None else None,
        "bbox_width_coverage_ratio": round(width_cov, 6) if width_cov is not None else None,
        "bbox_height_coverage_ratio": round(height_cov, 6) if height_cov is not None else None,
        "bbox_touches_top": (y0 <= 0.03 * page_h) if page_h else None,
        "bbox_touches_bottom": (y1 >= 0.97 * page_h) if page_h else None,
        "bbox_touches_left": (x0 <= 0.03 * page_w) if page_w else None,
        "bbox_touches_right": (x1 >= 0.97 * page_w) if page_w else None,
    }


def signal_rank(signal: str | None) -> int:
    return {
        "NO_LINE_SIGNAL": 0,
        "WEAK_LINE_SIGNAL": 1,
        "PARTIAL_GRID": 2,
        "GRID": 3,
    }.get(str(signal or ""), 0)


def table_type_requires_full_table_crop(table_type: str | None) -> bool:
    value = str(table_type or "").lower()
    return any(token in value for token in ("parts", "effective", "index", "table"))


def build_completeness_card(
    geometry_card: dict[str, Any],
    bbox_card: dict[str, Any] | None,
    review_card: dict[str, Any] | None,
    full_region_card: dict[str, Any] | None,
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    page_id, table_id = card_key(geometry_card)
    bbox_card = bbox_card or {}
    review_card = review_card or {}
    full_region_card = full_region_card or {}
    table_type = (
        geometry_card.get("table_type")
        or bbox_card.get("table_type")
        or review_card.get("table_type")
        or full_region_card.get("table_type")
    )
    bbox = first_bbox(bbox_card) or first_bbox(geometry_card)
    metrics = bbox_metrics(bbox)
    bbox_coverage = bbox_card.get("bbox_coverage_ratio")
    if bbox_coverage is None:
        bbox_coverage = metrics.get("bbox_page_coverage_ratio")
    bbox_coverage_float = safe_float(bbox_coverage, -1.0)

    selected_scope = geometry_card.get("selected_morphology_scope")
    crop_selected = selected_scope == "table_region_crop"
    crop_available = bool(geometry_card.get("table_region_crop_available"))
    crop_applied = bool(geometry_card.get("table_region_crop_applied"))
    margin_selected = bool(geometry_card.get("margin_expansion_selected_for_crop_morphology"))
    review_verdict = review_card.get("human_review_verdict")
    detector_disagreement = bool(review_card.get("detector_disagreement"))
    estimator_exceeds = bool(review_card.get("estimator_exceeds_production"))
    full_region_available = bool(full_region_card)
    full_region_status = full_region_card.get("crop_recovery_status")
    full_region_ready = bool(full_region_card.get("crop_recovery_ready"))
    full_region_coverage = safe_float(full_region_card.get("full_table_coverage_ratio"), -1.0)
    full_region_too_page_like = full_region_is_too_page_like(
        full_region_card,
        safe_float(thresholds.get("max_full_region_coverage_ratio"), 0.95),
    )
    full_region_used_for_crop = bool(geometry_card.get("table_full_region_recovery_used_for_crop"))

    horizontal = safe_int(geometry_card.get("horizontal_line_count"))
    vertical = safe_int(geometry_card.get("vertical_line_count"))
    intersections = safe_int(geometry_card.get("intersection_count"))
    signal = geometry_card.get("morphology_signal_strength")
    row_count = safe_int(geometry_card.get("row_record_count"))
    cell_count = safe_int(geometry_card.get("cell_record_count"))

    concerns: list[str] = []
    recommended_actions: list[str] = []

    if not metrics["bbox_present"]:
        concerns.append("missing_table_crop_bbox")
        recommended_actions.append("resolve_full_table_bbox_before_crop_selection")

    if detector_disagreement and review_verdict in UNSAFE_OR_UNKNOWN_VERDICTS:
        concerns.append("detector_disagreement_without_human_verdict")
        recommended_actions.append("label_detector_overlay_before_relaxing_crop_selection")

    if estimator_exceeds and review_verdict == "UNREVIEWED":
        concerns.append("estimator_grid_evidence_unreviewed")
        recommended_actions.append("verify_estimator_lines_are_table_rules_not_text_strokes")

    min_full_coverage = safe_float(thresholds.get("min_full_table_coverage_ratio"), 0.45)
    if table_type_requires_full_table_crop(table_type) and 0 <= bbox_coverage_float < min_full_coverage:
        concerns.append("crop_coverage_may_be_too_small_for_full_table")
        recommended_actions.append("expand_or_recompute_bbox_to_cover_header_and_body_rows")

    if signal_rank(signal) < 3 and table_type_requires_full_table_crop(table_type):
        concerns.append("selected_or_page_morphology_not_full_grid")
        recommended_actions.append("keep_table_geometry_review_routing_until_full_grid_validated")

    if vertical == 0 and table_type_requires_full_table_crop(table_type):
        concerns.append("no_vertical_table_rules_confirmed")
        recommended_actions.append("do_not_use_crop_as_column_boundary_authority")

    if intersections == 0 and table_type_requires_full_table_crop(table_type):
        concerns.append("no_table_rule_intersections_confirmed")
        recommended_actions.append("do_not_use_crop_as_cell_boundary_authority")

    if crop_selected and review_verdict not in SAFE_VERDICTS:
        concerns.append("crop_selected_without_safe_overlay_verdict")
        recommended_actions.append("block_crop_selection_until_overlay_verdict_is_safe")

    if margin_selected and review_verdict not in SAFE_VERDICTS:
        concerns.append("margin_crop_selected_without_safe_overlay_verdict")
        recommended_actions.append("block_margin_crop_selection_until_overlay_verdict_is_safe")

    if review_verdict == "ESTIMATOR_LINES_TEXT_OR_NOISE":
        concerns.append("human_review_labeled_estimator_lines_as_noise")
        recommended_actions.append("tighten_estimator_or_keep_production_morphology_conservative")
    elif review_verdict == "MIXED_OR_UNCLEAR":
        concerns.append("human_review_labeled_estimator_lines_mixed_or_unclear")
        recommended_actions.append("require_additional_line_overlay_review_before_selection_change")

    full_region_gate_allowed, full_region_gate_reasons, full_region_gate_actions = full_region_meets_selection_gate(
        geometry_card=geometry_card,
        full_region_card=full_region_card,
        review_verdict=review_verdict,
        thresholds=thresholds,
    )

    if not concerns:
        completeness_status = "PASS"
        crop_selection_allowed = True
        recommended_actions.append("crop_candidate_completeness_guard_passed")
    elif full_region_gate_allowed:
        # Full-region recovery is allowed to override unresolved detector-review
        # concerns only when it is explicitly enabled and the recovered crop already
        # produced grid evidence in Table Line Geometry.  This unblocks crop
        # morphology candidates for testing, not answer/proof authority.
        completeness_status = "PASS_FULL_REGION_RECOVERY_READY"
        crop_selection_allowed = True
        recommended_actions.append("full_region_recovery_ready_crop_candidate_allowed")
    elif crop_selected or margin_selected:
        completeness_status = "FAIL_BLOCK_SELECTION"
        crop_selection_allowed = False
        concerns.extend(full_region_gate_reasons)
        recommended_actions.extend(full_region_gate_actions)
    else:
        completeness_status = "REVIEW_REQUIRED"
        crop_selection_allowed = False
        concerns.extend(full_region_gate_reasons)
        recommended_actions.extend(full_region_gate_actions)

    recommended_actions = list(dict.fromkeys(recommended_actions))
    concerns = list(dict.fromkeys(concerns))

    return {
        "schema_version": SCHEMA_VERSION,
        "crop_completeness_card_id": f"crop_complete::{stable_id(page_id, table_id)}",
        "page_id": page_id,
        "table_id": table_id,
        "table_type": table_type,
        "target_type": "table_crop_completeness_guard",
        "selected_morphology_scope": selected_scope,
        "table_region_crop_available": crop_available,
        "table_region_crop_applied": crop_applied,
        "table_region_crop_selected": crop_selected,
        "margin_expansion_selected_for_crop_morphology": margin_selected,
        "crop_margin_pixels": geometry_card.get("crop_margin_pixels"),
        "bbox_source": bbox_card.get("bbox_source") or geometry_card.get("table_region_bbox_source"),
        "bbox_coverage_ratio": bbox_coverage_float if bbox_coverage_float >= 0 else None,
        "bbox_metrics": metrics,
        "row_record_count": row_count,
        "cell_record_count": cell_count,
        "horizontal_line_count": horizontal,
        "vertical_line_count": vertical,
        "intersection_count": intersections,
        "morphology_signal_strength": signal,
        "morphology_quality_score": safe_float(geometry_card.get("morphology_quality_score")),
        "overlay_review_available": bool(review_card),
        "human_review_verdict": review_verdict or "MISSING_REVIEW_CARD",
        "detector_disagreement": detector_disagreement,
        "estimator_exceeds_production": estimator_exceeds,
        "production_exceeds_estimator": bool(review_card.get("production_exceeds_estimator")),
        "overlay_path": review_card.get("overlay_path"),
        "table_full_region_recovery_available": full_region_available,
        "table_full_region_recovery_status": full_region_status,
        "table_full_region_recovery_ready": full_region_ready,
        "table_full_region_recovery_used_for_crop": full_region_used_for_crop,
        "table_full_region_recovery_full_table_coverage_ratio": full_region_coverage if full_region_coverage >= 0 else None,
        "table_full_region_recovery_too_page_like": full_region_too_page_like,
        "full_region_recovery_gate_allowed": full_region_gate_allowed,
        "full_region_recovery_gate_reasons": full_region_gate_reasons,
        "crop_completeness_status": completeness_status,
        "crop_selection_allowed": crop_selection_allowed,
        "crop_selection_blocked": not crop_selection_allowed,
        "requires_human_review": completeness_status != "PASS",
        "review_flags": concerns,
        "recommended_actions": recommended_actions,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "retrieval_only_answer_allowed": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "unsafe_crop_completeness_card": False,
    }


def build_report(
    *,
    table_line_geometry_path: Path,
    table_bbox_resolver_path: Path,
    overlay_review_pack_path: Path,
    output_dir: Path,
    table_full_region_recovery_path: Path | None = None,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or {}
    geometry_payload = read_json(table_line_geometry_path)
    bbox_payload = read_json(table_bbox_resolver_path)
    review_payload = read_json(overlay_review_pack_path)
    full_region_payload = read_json(table_full_region_recovery_path) if table_full_region_recovery_path else {}

    bbox_index = index_cards(bbox_payload, ["table_bbox_cards", "bbox_cards"])
    review_index = index_cards(review_payload, ["review_cards", "audit_cards"])
    full_region_index = index_cards(full_region_payload, ["recovery_cards", "table_full_region_recovery_cards"])

    geometry_cards = [c for c in as_list(geometry_payload.get("table_geometry_cards")) if isinstance(c, dict)]
    completeness_cards = [
        build_completeness_card(
            geometry_card=card,
            bbox_card=bbox_index.get(card_key(card)),
            review_card=review_index.get(card_key(card)),
            full_region_card=full_region_index.get(card_key(card)),
            thresholds=thresholds,
        )
        for card in geometry_cards
    ]

    summary = summarize_cards(
        completeness_cards,
        geometry_payload=geometry_payload,
        bbox_payload=bbox_payload,
        review_payload=review_payload,
        full_region_payload=full_region_payload,
        thresholds=thresholds,
    )

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "status": "TABLE_CROP_COMPLETENESS_GUARD_BUILT",
        "quality_status": "PASS" if not summary["quality_fail_reasons"] else "FAIL",
        "table_line_geometry_path": str(table_line_geometry_path),
        "table_bbox_resolver_path": str(table_bbox_resolver_path),
        "overlay_review_pack_path": str(overlay_review_pack_path),
        "table_full_region_recovery_path": str(table_full_region_recovery_path) if table_full_region_recovery_path else None,
        "thresholds": thresholds,
        "safety_contract": SAFETY_CONTRACT,
        "summary": summary,
        "crop_completeness_cards": completeness_cards,
    }
    report["quality_status"] = summary["quality_status"]

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_table_crop_completeness_guard_v1.json"
    cards_path = output_dir / "trace_net_table_crop_completeness_guard_v1_cards.jsonl"
    summary_path = output_dir / "trace_net_table_crop_completeness_guard_v1_summary.json"
    manifest_path = output_dir / "trace_net_table_crop_completeness_guard_v1_manifest.json"
    quality_path = output_dir / "trace_net_table_crop_completeness_guard_v1_quality.json"

    write_json(report_path, report)
    write_jsonl(cards_path, completeness_cards)
    write_json(summary_path, summary)
    write_json(manifest_path, {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": report["generated_at"],
        "files": {
            "report": str(report_path),
            "cards_jsonl": str(cards_path),
            "summary": str(summary_path),
            "quality": str(quality_path),
        },
    })

    from tiff.trace_net_table_crop_completeness_guard_v1_quality import build_quality_report

    quality = build_quality_report(report, thresholds=thresholds)
    write_json(quality_path, quality)
    return report


def summarize_cards(
    cards: list[dict[str, Any]],
    *,
    geometry_payload: dict[str, Any],
    bbox_payload: dict[str, Any],
    review_payload: dict[str, Any],
    full_region_payload: dict[str, Any],
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    from collections import Counter

    status_counts = Counter(card.get("crop_completeness_status") for card in cards)
    flag_counts = Counter(flag for card in cards for flag in as_list(card.get("review_flags")))
    action_counts = Counter(action for card in cards for action in as_list(card.get("recommended_actions")))

    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "quality_status": "PASS",
        "quality_fail_reasons": [],
        "crop_completeness_card_count": len(cards),
        "crop_completeness_pass_card_count": status_counts.get("PASS", 0) + status_counts.get("PASS_FULL_REGION_RECOVERY_READY", 0),
        "crop_completeness_standard_pass_card_count": status_counts.get("PASS", 0),
        "crop_completeness_full_region_recovery_pass_card_count": status_counts.get("PASS_FULL_REGION_RECOVERY_READY", 0),
        "crop_completeness_review_required_card_count": status_counts.get("REVIEW_REQUIRED", 0),
        "crop_completeness_fail_block_selection_card_count": status_counts.get("FAIL_BLOCK_SELECTION", 0),
        "crop_selection_allowed_card_count": sum(1 for c in cards if c.get("crop_selection_allowed")),
        "crop_selection_blocked_card_count": sum(1 for c in cards if c.get("crop_selection_blocked")),
        "overlay_review_available_card_count": sum(1 for c in cards if c.get("overlay_review_available")),
        "overlay_unreviewed_card_count": sum(1 for c in cards if c.get("human_review_verdict") == "UNREVIEWED"),
        "detector_disagreement_card_count": sum(1 for c in cards if c.get("detector_disagreement")),
        "detector_disagreement_without_safe_verdict_card_count": sum(
            1
            for c in cards
            if c.get("detector_disagreement") and c.get("human_review_verdict") not in SAFE_VERDICTS
        ),
        "table_full_region_recovery_available_card_count": sum(1 for c in cards if c.get("table_full_region_recovery_available")),
        "table_full_region_recovery_ready_card_count": sum(1 for c in cards if c.get("table_full_region_recovery_ready")),
        "table_full_region_recovery_used_for_crop_card_count": sum(1 for c in cards if c.get("table_full_region_recovery_used_for_crop")),
        "table_full_region_recovery_too_page_like_card_count": sum(1 for c in cards if c.get("table_full_region_recovery_too_page_like")),
        "full_region_recovery_gate_allowed_card_count": sum(1 for c in cards if c.get("full_region_recovery_gate_allowed")),
        "table_region_crop_selected_card_count": sum(1 for c in cards if c.get("table_region_crop_selected")),
        "margin_expansion_selected_card_count": sum(1 for c in cards if c.get("margin_expansion_selected_for_crop_morphology")),
        "unsafe_crop_completeness_card_count": sum(1 for c in cards if c.get("unsafe_crop_completeness_card")),
        "answer_permission_count": sum(1 for c in cards if c.get("answer_permission")),
        "can_answer_directly_count": sum(1 for c in cards if c.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for c in cards if c.get("can_prove_claims")),
        "source_truth_mutation_allowed_count": sum(1 for c in cards if c.get("source_truth_mutation_allowed")),
        "source_truth_mutations_performed": sum(safe_int(c.get("source_truth_mutations_performed")) for c in cards),
        "postgres_write_attempt_count": sum(safe_int(c.get("postgres_write_attempt_count")) for c in cards),
        "qdrant_write_attempt_count": sum(safe_int(c.get("qdrant_write_attempt_count")) for c in cards),
        "opensearch_write_attempt_count": sum(safe_int(c.get("opensearch_write_attempt_count")) for c in cards),
        "review_flag_counts": dict(flag_counts),
        "recommended_action_counts": dict(action_counts),
        "source_quality_statuses": {
            "table_line_geometry": geometry_payload.get("quality_status"),
            "table_bbox_resolver": bbox_payload.get("quality_status"),
            "overlay_review_pack": review_payload.get("quality_status"),
            "table_full_region_recovery": full_region_payload.get("quality_status"),
        },
        "thresholds": thresholds,
    }

    if geometry_payload.get("quality_status") != "PASS" and thresholds.get("require_table_line_geometry_quality_pass"):
        summary["quality_fail_reasons"].append("table_line_geometry_quality_not_pass")
    if bbox_payload.get("quality_status") != "PASS" and thresholds.get("require_table_bbox_resolver_quality_pass"):
        summary["quality_fail_reasons"].append("table_bbox_resolver_quality_not_pass")
    if review_payload.get("quality_status") != "PASS" and thresholds.get("require_overlay_review_pack_quality_pass"):
        summary["quality_fail_reasons"].append("overlay_review_pack_quality_not_pass")
    if full_region_payload.get("quality_status") != "PASS" and thresholds.get("require_table_full_region_recovery_quality_pass"):
        summary["quality_fail_reasons"].append("table_full_region_recovery_quality_not_pass")
    if summary.get("full_region_recovery_gate_allowed_card_count", 0) < safe_int(thresholds.get("min_full_region_recovery_gate_allowed_cards"), 0):
        summary["quality_fail_reasons"].append("min_full_region_recovery_gate_allowed_cards_not_met")
    if len(cards) < safe_int(thresholds.get("min_completeness_cards"), 0):
        summary["quality_fail_reasons"].append("min_completeness_cards_not_met")
    if summary["unsafe_crop_completeness_card_count"] > safe_int(thresholds.get("max_unsafe_completeness_cards"), 0):
        summary["quality_fail_reasons"].append("unsafe_completeness_card_limit_exceeded")
    if summary["answer_permission_count"] > safe_int(thresholds.get("max_answer_permission_count"), 0):
        summary["quality_fail_reasons"].append("answer_permission_limit_exceeded")
    if summary["source_truth_mutation_allowed_count"] > safe_int(thresholds.get("max_source_truth_mutation_allowed"), 0):
        summary["quality_fail_reasons"].append("source_truth_mutation_allowed_limit_exceeded")
    if thresholds.get("require_no_answer_permission") and summary["answer_permission_count"] != 0:
        summary["quality_fail_reasons"].append("answer_permission_present")

    if summary["quality_fail_reasons"]:
        summary["quality_status"] = "FAIL"
        summary["status"] = "FAIL"
    return summary


def thresholds_from_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "min_completeness_cards": args.min_completeness_cards,
        "min_full_table_coverage_ratio": args.min_full_table_coverage_ratio,
        "max_unsafe_completeness_cards": args.max_unsafe_completeness_cards,
        "max_answer_permission_count": args.max_answer_permission_count,
        "max_source_truth_mutation_allowed": args.max_source_truth_mutation_allowed,
        "require_table_line_geometry_quality_pass": args.require_table_line_geometry_quality_pass,
        "require_table_bbox_resolver_quality_pass": args.require_table_bbox_resolver_quality_pass,
        "require_overlay_review_pack_quality_pass": args.require_overlay_review_pack_quality_pass,
        "require_table_full_region_recovery_quality_pass": args.require_table_full_region_recovery_quality_pass,
        "allow_full_region_recovery_ready_selection": args.allow_full_region_recovery_ready_selection,
        "max_full_region_coverage_ratio": args.max_full_region_coverage_ratio,
        "min_full_region_recovery_gate_allowed_cards": args.min_full_region_recovery_gate_allowed_cards,
        "require_no_answer_permission": args.require_no_answer_permission,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net table crop completeness guard v1")
    parser.add_argument("--table-line-geometry", required=True, type=Path)
    parser.add_argument("--table-bbox-resolver", required=True, type=Path)
    parser.add_argument("--overlay-review-pack", required=True, type=Path)
    parser.add_argument("--table-full-region-recovery", type=Path, default=None)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--min-completeness-cards", type=int, default=1)
    parser.add_argument("--min-full-table-coverage-ratio", type=float, default=0.45)
    parser.add_argument("--max-unsafe-completeness-cards", type=int, default=0)
    parser.add_argument("--max-full-region-coverage-ratio", type=float, default=0.95)
    parser.add_argument("--min-full-region-recovery-gate-allowed-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-line-geometry-quality-pass", action="store_true")
    parser.add_argument("--require-table-bbox-resolver-quality-pass", action="store_true")
    parser.add_argument("--require-overlay-review-pack-quality-pass", action="store_true")
    parser.add_argument("--require-table-full-region-recovery-quality-pass", action="store_true")
    parser.add_argument("--allow-full-region-recovery-ready-selection", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def print_report(report: dict[str, Any]) -> None:
    summary = report.get("summary", {})
    print("TRACE-Net Table Crop Completeness Guard v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in (
        "crop_completeness_card_count",
        "crop_completeness_pass_card_count",
        "crop_completeness_review_required_card_count",
        "crop_completeness_fail_block_selection_card_count",
        "crop_selection_allowed_card_count",
        "crop_selection_blocked_card_count",
        "overlay_review_available_card_count",
        "overlay_unreviewed_card_count",
        "detector_disagreement_card_count",
        "detector_disagreement_without_safe_verdict_card_count",
        "table_full_region_recovery_available_card_count",
        "table_full_region_recovery_ready_card_count",
        "table_full_region_recovery_used_for_crop_card_count",
        "table_full_region_recovery_too_page_like_card_count",
        "full_region_recovery_gate_allowed_card_count",
        "crop_completeness_full_region_recovery_pass_card_count",
        "table_region_crop_selected_card_count",
        "margin_expansion_selected_card_count",
        "unsafe_crop_completeness_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    thresholds = thresholds_from_args(args)
    report = build_report(
        table_line_geometry_path=args.table_line_geometry,
        table_bbox_resolver_path=args.table_bbox_resolver,
        overlay_review_pack_path=args.overlay_review_pack,
        output_dir=args.output_dir,
        table_full_region_recovery_path=args.table_full_region_recovery,
        thresholds=thresholds,
    )
    print_report(report)
    return 0 if report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
