"""TRACE-Net Table Margin Detector Parity v1.

Read-only diagnostic module that compares production Table Line Geometry
morphology detection with a lightweight margin-expansion estimator on the exact
same table crop candidates.

This module is advisory only. It never mutates source truth and never grants
answer authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "trace_net_table_margin_detector_parity_v1"
STATUS_BUILT = "TABLE_MARGIN_DETECTOR_PARITY_BUILT"
STATUS_NOT_READY = "TABLE_MARGIN_DETECTOR_PARITY_NOT_READY"
DEFAULT_MARGIN_PIXELS = (0, 25, 50, 100, 150, 250)


@dataclass(frozen=True)
class Thresholds:
    min_parity_cards: int = 1
    min_margin_candidate_evaluations: int = 1
    min_successful_image_cards: int = 1
    min_detector_disagreement_cards: int = 0
    max_unsafe_parity_cards: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_table_line_geometry_quality_pass: bool = False
    require_table_bbox_resolver_quality_pass: bool = False
    require_no_answer_permission: bool = False


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "::".join(str(part) for part in parts if part is not None)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:14]
    return f"{prefix}_{digest}"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def extract_cards(payload: Mapping[str, Any], *keys: str) -> List[Dict[str, Any]]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


def card_join_key(card: Mapping[str, Any]) -> Tuple[str, str]:
    return (str(card.get("page_id") or ""), str(card.get("table_id") or ""))


def normalize_path(path_value: Any, image_root: Path) -> Optional[Path]:
    if not path_value:
        return None
    raw = str(path_value).replace("\\", "/")
    path = Path(raw)
    if path.is_absolute():
        return path
    return image_root / path


def parse_bbox(value: Any) -> Optional[Dict[str, float]]:
    if not isinstance(value, Mapping):
        return None
    x0 = as_float(value.get("x0"), math.nan)
    y0 = as_float(value.get("y0"), math.nan)
    x1 = as_float(value.get("x1"), math.nan)
    y1 = as_float(value.get("y1"), math.nan)
    if not all(math.isfinite(v) for v in (x0, y0, x1, y1)):
        return None
    if x1 <= x0 or y1 <= y0:
        return None
    return {
        "coordinate_system": "pixels",
        "x0": round(x0, 3),
        "y0": round(y0, 3),
        "x1": round(x1, 3),
        "y1": round(y1, 3),
        "width": round(x1 - x0, 3),
        "height": round(y1 - y0, 3),
    }


def bbox_from_record(record: Mapping[str, Any]) -> Optional[Dict[str, float]]:
    return parse_bbox(record.get("table_region_bbox") or record.get("inferred_table_region_bbox"))


def clamp_bbox(bbox: Mapping[str, Any], image_width: int, image_height: int, margin_pixels: int) -> Optional[Dict[str, float]]:
    parsed = parse_bbox(bbox)
    if not parsed:
        return None
    margin = max(0.0, float(margin_pixels))
    x0 = max(0.0, parsed["x0"] - margin)
    y0 = max(0.0, parsed["y0"] - margin)
    x1 = min(float(image_width), parsed["x1"] + margin)
    y1 = min(float(image_height), parsed["y1"] + margin)
    if x1 <= x0 or y1 <= y0:
        return None
    return {
        "coordinate_system": "pixels",
        "x0": round(x0, 3),
        "y0": round(y0, 3),
        "x1": round(x1, 3),
        "y1": round(y1, 3),
        "width": round(x1 - x0, 3),
        "height": round(y1 - y0, 3),
    }


def collapse_runs(indices: Iterable[int], min_gap: int = 2) -> List[Tuple[int, int]]:
    sorted_indices = sorted(set(indices))
    if not sorted_indices:
        return []
    runs: List[Tuple[int, int]] = []
    start = prev = sorted_indices[0]
    for idx in sorted_indices[1:]:
        if idx - prev <= min_gap:
            prev = idx
            continue
        runs.append((start, prev))
        start = prev = idx
    runs.append((start, prev))
    return runs


def classify_signal(horizontal: int, vertical: int, intersections: int) -> str:
    if horizontal >= 3 and vertical >= 2 and intersections >= 4:
        return "GRID"
    if horizontal >= 1 and vertical >= 1:
        return "PARTIAL_GRID"
    if horizontal >= 1 or vertical >= 1:
        return "WEAK_LINE_SIGNAL"
    return "NO_LINE_SIGNAL"


def morphology_score(horizontal: int, vertical: int, intersections: int, signal: str) -> float:
    multiplier = {"GRID": 10.0, "PARTIAL_GRID": 4.0, "WEAK_LINE_SIGNAL": 1.0, "NO_LINE_SIGNAL": 0.0}.get(str(signal), 0.0)
    return round(horizontal * 1.0 + vertical * 2.0 + intersections * 10.0 + multiplier, 3)


def signal_rank(signal: Any) -> int:
    return {"NO_LINE_SIGNAL": 0, "WEAK_LINE_SIGNAL": 1, "PARTIAL_GRID": 2, "GRID": 3}.get(str(signal), 0)


def estimator_morphology_from_crop(image_path: Path, bbox: Mapping[str, Any], dark_threshold: int = 180) -> Dict[str, Any]:
    """Lightweight diagnostic estimator used by the margin experiment.

    This intentionally mirrors the experiment detector so we can compare it
    against production morphology on exactly the same crop boxes.
    """
    try:
        from PIL import Image  # type: ignore
    except Exception as exc:  # pragma: no cover
        return _failed_detector("ESTIMATOR_UNAVAILABLE", f"Pillow unavailable: {exc}")

    parsed = parse_bbox(bbox)
    if not parsed:
        return _failed_detector("ESTIMATOR_INVALID_BBOX", "invalid bbox")

    try:
        with Image.open(image_path) as img:
            grayscale = img.convert("L")
            width, height = grayscale.size
            x0 = max(0, min(width - 1, int(round(parsed["x0"]))))
            y0 = max(0, min(height - 1, int(round(parsed["y0"]))))
            x1 = max(x0 + 1, min(width, int(round(parsed["x1"]))))
            y1 = max(y0 + 1, min(height, int(round(parsed["y1"]))))
            crop = grayscale.crop((x0, y0, x1, y1))
            crop_width, crop_height = crop.size
            pixels = crop.load()
            row_min_dark = max(24, int(crop_width * 0.30))
            col_min_dark = max(24, int(crop_height * 0.22))

            horizontal_candidates: List[int] = []
            for y in range(crop_height):
                dark = 0
                for x in range(crop_width):
                    if pixels[x, y] <= dark_threshold:
                        dark += 1
                if dark >= row_min_dark:
                    horizontal_candidates.append(y)

            vertical_candidates: List[int] = []
            for x in range(crop_width):
                dark = 0
                for y in range(crop_height):
                    if pixels[x, y] <= dark_threshold:
                        dark += 1
                if dark >= col_min_dark:
                    vertical_candidates.append(x)

            h_runs = collapse_runs(horizontal_candidates, min_gap=2)
            v_runs = collapse_runs(vertical_candidates, min_gap=2)
            intersections = 0
            for hy0, hy1 in h_runs:
                hy = (hy0 + hy1) // 2
                for vx0, vx1 in v_runs:
                    vx = (vx0 + vx1) // 2
                    found_dark = False
                    for yy in range(max(0, hy - 2), min(crop_height, hy + 3)):
                        for xx in range(max(0, vx - 2), min(crop_width, vx + 3)):
                            if pixels[xx, yy] <= dark_threshold:
                                found_dark = True
                                break
                        if found_dark:
                            break
                    if found_dark:
                        intersections += 1
            horizontal = len(h_runs)
            vertical = len(v_runs)
            signal = classify_signal(horizontal, vertical, intersections)
            return {
                "status": "IMAGE_ANALYSIS_OK",
                "detector": "experiment_projection_estimator",
                "image_width": width,
                "image_height": height,
                "crop_width": crop_width,
                "crop_height": crop_height,
                "horizontal_line_count": horizontal,
                "vertical_line_count": vertical,
                "intersection_count": intersections,
                "morphology_signal_strength": signal,
                "morphology_quality_score": morphology_score(horizontal, vertical, intersections, signal),
            }
    except Exception as exc:
        return _failed_detector("ESTIMATOR_FAILED", str(exc))


def _failed_detector(status: str, error: str) -> Dict[str, Any]:
    return {
        "status": status,
        "error": error,
        "horizontal_line_count": 0,
        "vertical_line_count": 0,
        "intersection_count": 0,
        "morphology_signal_strength": "NO_LINE_SIGNAL",
        "morphology_quality_score": 0.0,
    }


def _count_lines(result: Mapping[str, Any], key: str) -> int:
    value = result.get(key)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return len(value)
    return as_int(value)


def summarize_detector_result(result: Mapping[str, Any], detector_name: str) -> Dict[str, Any]:
    horizontal = _count_lines(result, "horizontal_lines") or as_int(result.get("horizontal_line_count"))
    vertical = _count_lines(result, "vertical_lines") or as_int(result.get("vertical_line_count"))
    intersections = as_int(result.get("intersection_count"))
    signal = str(result.get("morphology_signal_strength") or classify_signal(horizontal, vertical, intersections))
    score = as_float(result.get("morphology_quality_score"), morphology_score(horizontal, vertical, intersections, signal))
    return {
        "detector": detector_name,
        "status": result.get("status") or "IMAGE_ANALYSIS_OK",
        "horizontal_line_count": horizontal,
        "vertical_line_count": vertical,
        "intersection_count": intersections,
        "morphology_signal_strength": signal,
        "morphology_quality_score": score,
    }


def production_morphology_from_crop(image_path: Path, bbox: Mapping[str, Any]) -> Dict[str, Any]:
    try:
        from tiff.trace_net_table_line_geometry_v1 import detect_table_lines_from_image  # type: ignore
    except Exception as exc:
        return _failed_detector("PRODUCTION_DETECTOR_IMPORT_FAILED", str(exc))
    try:
        result = detect_table_lines_from_image(image_path, crop_bbox=bbox)
        summary = summarize_detector_result(result, "production_table_line_geometry")
        summary["status"] = "IMAGE_ANALYSIS_OK"
        return summary
    except Exception as exc:
        return _failed_detector("PRODUCTION_DETECTOR_FAILED", str(exc))


def margins_from_string(value: Optional[str]) -> List[int]:
    if not value:
        return list(DEFAULT_MARGIN_PIXELS)
    margins: List[int] = []
    for raw in value.split(","):
        raw = raw.strip()
        if not raw:
            continue
        margins.append(max(0, int(float(raw))))
    return sorted(set(margins)) or list(DEFAULT_MARGIN_PIXELS)


def best_candidate(candidates: Sequence[Mapping[str, Any]], detector_prefix: str) -> Optional[Dict[str, Any]]:
    available = [dict(c) for c in candidates if c.get(f"{detector_prefix}_status") == "IMAGE_ANALYSIS_OK"]
    if not available:
        return None
    return max(
        available,
        key=lambda item: (
            signal_rank(item.get(f"{detector_prefix}_signal")),
            as_int(item.get(f"{detector_prefix}_intersection_count")),
            as_int(item.get(f"{detector_prefix}_vertical_line_count")),
            as_float(item.get(f"{detector_prefix}_score")),
            -as_int(item.get("margin_pixels")),
        ),
    )


def build_parity_card(
    *,
    line_card: Mapping[str, Any],
    bbox_card: Optional[Mapping[str, Any]],
    image_root: Path,
    margins: Sequence[int],
) -> Dict[str, Any]:
    page_id, table_id = card_join_key(line_card)
    resolved_image_path = line_card.get("resolved_image_path") or (bbox_card or {}).get("resolved_image_path")
    image_path = normalize_path(resolved_image_path, image_root)
    base_bbox = bbox_from_record(bbox_card or {}) or bbox_from_record(line_card)

    card: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "parity_card_id": stable_id("margin_detector_parity", page_id, table_id),
        "page_id": page_id,
        "table_id": table_id,
        "table_type": line_card.get("table_type"),
        "resolved_image_path": str(resolved_image_path) if resolved_image_path else None,
        "bbox_source": (bbox_card or {}).get("bbox_source") or line_card.get("table_region_bbox_source"),
        "bbox_coverage_ratio": (bbox_card or {}).get("bbox_coverage_ratio"),
        "base_table_region_bbox": base_bbox,
        "selected_morphology_scope": line_card.get("selected_morphology_scope"),
        "margin_candidate_count": 0,
        "margin_detector_candidates": [],
        "production_best_candidate": None,
        "estimator_best_candidate": None,
        "production_detector_available": False,
        "estimator_detector_available": False,
        "successful_image_analysis": False,
        "detector_disagreement": False,
        "estimator_exceeds_production": False,
        "production_exceeds_estimator": False,
        "detector_parity_findings": [],
        "recommended_actions": [],
        "review_required": True,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "retrieval_only_answer_allowed": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "unsafe_parity_card": False,
    }

    if not base_bbox:
        card["detector_parity_findings"].append("missing_table_region_bbox")
        card["recommended_actions"].append("resolve_table_region_bbox_before_detector_parity")
        return card
    if not image_path or not image_path.exists():
        card["detector_parity_findings"].append("resolved_image_missing")
        card["recommended_actions"].append("resolve_source_page_image_before_detector_parity")
        return card

    try:
        from PIL import Image  # type: ignore
        with Image.open(image_path) as img:
            image_width, image_height = img.size
    except Exception as exc:
        card["detector_parity_findings"].append("image_dimension_read_failed")
        card["image_read_error"] = str(exc)
        card["recommended_actions"].append("verify_resolved_tiff_can_be_read")
        return card

    candidates: List[Dict[str, Any]] = []
    for margin in margins:
        expanded = clamp_bbox(base_bbox, image_width, image_height, int(margin))
        if not expanded:
            continue
        prod = production_morphology_from_crop(image_path, expanded)
        est = estimator_morphology_from_crop(image_path, expanded)
        candidate = {
            "margin_pixels": int(margin),
            "expanded_bbox": expanded,
            "production_status": prod.get("status"),
            "production_horizontal_line_count": as_int(prod.get("horizontal_line_count")),
            "production_vertical_line_count": as_int(prod.get("vertical_line_count")),
            "production_intersection_count": as_int(prod.get("intersection_count")),
            "production_signal": prod.get("morphology_signal_strength"),
            "production_score": as_float(prod.get("morphology_quality_score")),
            "estimator_status": est.get("status"),
            "estimator_horizontal_line_count": as_int(est.get("horizontal_line_count")),
            "estimator_vertical_line_count": as_int(est.get("vertical_line_count")),
            "estimator_intersection_count": as_int(est.get("intersection_count")),
            "estimator_signal": est.get("morphology_signal_strength"),
            "estimator_score": as_float(est.get("morphology_quality_score")),
        }
        candidate["vertical_delta_estimator_minus_production"] = candidate["estimator_vertical_line_count"] - candidate["production_vertical_line_count"]
        candidate["intersection_delta_estimator_minus_production"] = candidate["estimator_intersection_count"] - candidate["production_intersection_count"]
        candidate["signal_rank_delta_estimator_minus_production"] = signal_rank(candidate["estimator_signal"]) - signal_rank(candidate["production_signal"])
        candidates.append(candidate)

    card["margin_detector_candidates"] = candidates
    card["margin_candidate_count"] = len(candidates)
    prod_best = best_candidate(candidates, "production")
    est_best = best_candidate(candidates, "estimator")
    card["production_best_candidate"] = prod_best
    card["estimator_best_candidate"] = est_best
    card["production_detector_available"] = bool(prod_best)
    card["estimator_detector_available"] = bool(est_best)
    card["successful_image_analysis"] = bool(prod_best and est_best)

    if not prod_best or not est_best:
        card["detector_parity_findings"].append("one_or_more_detectors_unavailable")
        card["recommended_actions"].append("verify_detector_imports_and_image_codecs")
        return card

    vertical_delta = as_int(est_best.get("estimator_vertical_line_count")) - as_int(prod_best.get("production_vertical_line_count"))
    intersection_delta = as_int(est_best.get("estimator_intersection_count")) - as_int(prod_best.get("production_intersection_count"))
    signal_delta = signal_rank(est_best.get("estimator_signal")) - signal_rank(prod_best.get("production_signal"))
    score_delta = as_float(est_best.get("estimator_score")) - as_float(prod_best.get("production_score"))
    card["best_vertical_delta_estimator_minus_production"] = vertical_delta
    card["best_intersection_delta_estimator_minus_production"] = intersection_delta
    card["best_signal_rank_delta_estimator_minus_production"] = signal_delta
    card["best_score_delta_estimator_minus_production"] = round(score_delta, 3)

    disagreement = abs(vertical_delta) >= 2 or abs(intersection_delta) >= 4 or abs(signal_delta) >= 1
    card["detector_disagreement"] = disagreement
    card["estimator_exceeds_production"] = vertical_delta > 0 or intersection_delta > 0 or signal_delta > 0
    card["production_exceeds_estimator"] = vertical_delta < 0 or intersection_delta < 0 or signal_delta < 0

    if disagreement:
        card["detector_parity_findings"].append("production_and_experiment_detectors_disagree")
        card["recommended_actions"].append("inspect_detector_line_overlays_before_selection_change")
    if card["estimator_exceeds_production"]:
        card["detector_parity_findings"].append("experiment_estimator_counts_more_grid_evidence")
        card["recommended_actions"].append("check_whether_estimator_counts_text_strokes_as_lines")
        card["recommended_actions"].append("consider_relaxing_production_line_thresholds_only_if_visual_overlay_confirms_rules")
    if card["production_exceeds_estimator"]:
        card["detector_parity_findings"].append("production_detector_counts_more_grid_evidence")
    if not card["detector_parity_findings"]:
        card["detector_parity_findings"].append("detectors_are_roughly_aligned")
        card["recommended_actions"].append("margin_selection_can_be_tuned_with_current_detector")

    return card


def quality_checks(report: Mapping[str, Any], thresholds: Thresholds) -> Dict[str, bool]:
    summary = report.get("summary") or {}
    checks = {
        "schema_version_ok": report.get("schema_version") == SCHEMA_VERSION,
        "min_parity_cards_met": as_int(summary.get("parity_card_count")) >= thresholds.min_parity_cards,
        "min_margin_candidate_evaluations_met": as_int(summary.get("margin_candidate_evaluation_count")) >= thresholds.min_margin_candidate_evaluations,
        "min_successful_image_cards_met": as_int(summary.get("successful_image_card_count")) >= thresholds.min_successful_image_cards,
        "min_detector_disagreement_cards_met": as_int(summary.get("detector_disagreement_card_count")) >= thresholds.min_detector_disagreement_cards,
        "unsafe_parity_cards_within_limit": as_int(summary.get("unsafe_parity_card_count")) <= thresholds.max_unsafe_parity_cards,
        "answer_permission_within_limit": as_int(summary.get("answer_permission_count")) <= thresholds.max_answer_permission_count,
        "source_truth_mutation_allowed_within_limit": as_int(summary.get("source_truth_mutation_allowed_count")) <= thresholds.max_source_truth_mutation_allowed,
    }
    if thresholds.require_table_line_geometry_quality_pass:
        checks["table_line_geometry_quality_pass"] = summary.get("table_line_geometry_quality_status") == "PASS"
    if thresholds.require_table_bbox_resolver_quality_pass:
        checks["table_bbox_resolver_quality_pass"] = summary.get("table_bbox_resolver_quality_status") == "PASS"
    if thresholds.require_no_answer_permission:
        checks["no_answer_permission"] = as_int(summary.get("answer_permission_count")) == 0
    return checks


def quality_fail_reasons(checks: Mapping[str, bool]) -> List[str]:
    return [key for key, ok in checks.items() if not ok]


def build_report(
    *,
    table_line_geometry_path: Path,
    table_bbox_resolver_path: Path,
    image_root: Path,
    output_dir: Path,
    margin_pixels: Sequence[int],
    thresholds: Thresholds,
) -> Dict[str, Any]:
    line_payload = load_json(table_line_geometry_path)
    bbox_payload = load_json(table_bbox_resolver_path)
    line_cards = extract_cards(line_payload, "table_geometry_cards", "records")
    bbox_cards = extract_cards(bbox_payload, "table_bbox_cards", "records")
    bbox_map = {card_join_key(card): card for card in bbox_cards}

    cards = [
        build_parity_card(
            line_card=card,
            bbox_card=bbox_map.get(card_join_key(card)),
            image_root=image_root,
            margins=margin_pixels,
        )
        for card in line_cards
    ]

    summary: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "quality_status": "PENDING",
        "table_line_geometry_quality_status": line_payload.get("quality_status"),
        "table_bbox_resolver_quality_status": bbox_payload.get("quality_status"),
        "margin_pixels": list(margin_pixels),
        "parity_card_count": len(cards),
        "margin_candidate_evaluation_count": sum(as_int(card.get("margin_candidate_count")) for card in cards),
        "successful_image_card_count": sum(1 for card in cards if card.get("successful_image_analysis")),
        "production_detector_available_card_count": sum(1 for card in cards if card.get("production_detector_available")),
        "estimator_detector_available_card_count": sum(1 for card in cards if card.get("estimator_detector_available")),
        "detector_disagreement_card_count": sum(1 for card in cards if card.get("detector_disagreement")),
        "estimator_exceeds_production_card_count": sum(1 for card in cards if card.get("estimator_exceeds_production")),
        "production_exceeds_estimator_card_count": sum(1 for card in cards if card.get("production_exceeds_estimator")),
        "unsafe_parity_card_count": sum(1 for card in cards if card.get("unsafe_parity_card")),
        "answer_permission_count": sum(1 for card in cards if card.get("answer_permission")),
        "can_answer_directly_count": sum(1 for card in cards if card.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for card in cards if card.get("can_prove_claims")),
        "source_truth_mutation_allowed_count": sum(1 for card in cards if card.get("source_truth_mutation_allowed")),
        "postgres_write_attempt_count": sum(as_int(card.get("postgres_write_attempt_count")) for card in cards),
        "qdrant_write_attempt_count": sum(as_int(card.get("qdrant_write_attempt_count")) for card in cards),
        "opensearch_write_attempt_count": sum(as_int(card.get("opensearch_write_attempt_count")) for card in cards),
    }

    report: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "status": STATUS_BUILT,
        "quality_status": "PENDING",
        "source_paths": {
            "table_line_geometry": str(table_line_geometry_path),
            "table_bbox_resolver": str(table_bbox_resolver_path),
            "image_root": str(image_root),
        },
        "summary": summary,
        "parity_cards": cards,
        "safety_contract": {
            "read_only_diagnostic": True,
            "no_postgres_writes": True,
            "no_qdrant_writes": True,
            "no_opensearch_writes": True,
            "no_source_truth_mutation": True,
            "no_answer_permission": True,
            "no_claim_proof_authority": True,
        },
    }
    checks = quality_checks(report, thresholds)
    fails = quality_fail_reasons(checks)
    status = "PASS" if not fails else "FAIL"
    summary["quality_status"] = status
    summary["quality_fail_reasons"] = fails
    summary["checks"] = checks
    report["quality_status"] = status
    report["status"] = STATUS_BUILT if status == "PASS" else STATUS_NOT_READY
    return report


def write_outputs(report: Mapping[str, Any], output_dir: Path, write_quality: bool = True) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_table_margin_detector_parity_v1.json"
    cards_path = output_dir / "trace_net_table_margin_detector_parity_v1_cards.jsonl"
    summary_path = output_dir / "trace_net_table_margin_detector_parity_v1_summary.json"
    quality_path = output_dir / "trace_net_table_margin_detector_parity_v1_quality.json"
    manifest_path = output_dir / "trace_net_table_margin_detector_parity_v1_manifest.json"
    write_json(report_path, report)
    write_jsonl(cards_path, report.get("parity_cards") or [])
    write_json(summary_path, {"summary": report.get("summary"), "generated_at": report.get("generated_at")})
    if write_quality:
        write_json(quality_path, {
            "schema_version": f"{SCHEMA_VERSION}_quality",
            "generated_at": utc_now_iso(),
            "status": report.get("quality_status"),
            "quality_status": report.get("quality_status"),
            "summary": report.get("summary"),
            "checks": (report.get("summary") or {}).get("checks"),
        })
    write_json(manifest_path, {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": utc_now_iso(),
        "artifacts": {
            "report": str(report_path),
            "cards_jsonl": str(cards_path),
            "summary": str(summary_path),
            "quality": str(quality_path),
        },
    })


def thresholds_from_args(args: argparse.Namespace) -> Thresholds:
    return Thresholds(
        min_parity_cards=args.min_parity_cards,
        min_margin_candidate_evaluations=args.min_margin_candidate_evaluations,
        min_successful_image_cards=args.min_successful_image_cards,
        min_detector_disagreement_cards=args.min_detector_disagreement_cards,
        max_unsafe_parity_cards=args.max_unsafe_parity_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_table_line_geometry_quality_pass=args.require_table_line_geometry_quality_pass,
        require_table_bbox_resolver_quality_pass=args.require_table_bbox_resolver_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net table margin detector parity diagnostics")
    parser.add_argument("--table-line-geometry", required=True, type=Path)
    parser.add_argument("--table-bbox-resolver", required=True, type=Path)
    parser.add_argument("--image-root", default=".", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--margin-pixels", default=",".join(str(x) for x in DEFAULT_MARGIN_PIXELS))
    parser.add_argument("--min-parity-cards", type=int, default=1)
    parser.add_argument("--min-margin-candidate-evaluations", type=int, default=1)
    parser.add_argument("--min-successful-image-cards", type=int, default=1)
    parser.add_argument("--min-detector-disagreement-cards", type=int, default=0)
    parser.add_argument("--max-unsafe-parity-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-line-geometry-quality-pass", action="store_true")
    parser.add_argument("--require-table-bbox-resolver-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = build_report(
        table_line_geometry_path=args.table_line_geometry,
        table_bbox_resolver_path=args.table_bbox_resolver,
        image_root=args.image_root,
        output_dir=args.output_dir,
        margin_pixels=margins_from_string(args.margin_pixels),
        thresholds=thresholds_from_args(args),
    )
    write_outputs(report, args.output_dir, write_quality=args.quality)
    summary = report.get("summary") or {}
    print("TRACE-Net Table Margin Detector Parity v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "parity_card_count",
        "margin_candidate_evaluation_count",
        "successful_image_card_count",
        "production_detector_available_card_count",
        "estimator_detector_available_card_count",
        "detector_disagreement_card_count",
        "estimator_exceeds_production_card_count",
        "production_exceeds_estimator_card_count",
        "unsafe_parity_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {args.output_dir / 'trace_net_table_margin_detector_parity_v1.json'}")
    return 0 if report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
