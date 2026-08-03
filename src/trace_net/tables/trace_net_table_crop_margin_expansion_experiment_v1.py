"""TRACE-Net Table Crop Margin Expansion Experiment v1.

Read-only diagnostic experiment for testing whether expanded table-region crops
recover better morphology evidence than the current selected page/crop result.

This module intentionally does not mutate source-truth artifacts and does not
claim answer authority. It writes advisory diagnostic artifacts only.
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
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SCHEMA_VERSION = "trace_net_table_crop_margin_expansion_experiment_v1"
STATUS_BUILT = "TABLE_CROP_MARGIN_EXPANSION_EXPERIMENT_BUILT"
STATUS_NOT_READY = "TABLE_CROP_MARGIN_EXPANSION_EXPERIMENT_NOT_READY"

DEFAULT_MARGIN_PIXELS = (0, 25, 50, 100, 150, 250)
IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".webp"}


@dataclass(frozen=True)
class Thresholds:
    min_diagnostic_cards: int = 1
    min_margin_candidate_cards: int = 1
    min_successful_image_cards: int = 1
    max_unsafe_diagnostic_cards: int = 0
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


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, records: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def normalize_path(path_value: Any, image_root: Path) -> Optional[Path]:
    if not path_value:
        return None
    raw = str(path_value).replace("\\", "/")
    path = Path(raw)
    if path.is_absolute():
        return path
    return image_root / path


def extract_cards(payload: Dict[str, Any], *candidate_keys: str) -> List[Dict[str, Any]]:
    for key in candidate_keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [record for record in value if isinstance(record, dict)]
    return []


def card_join_key(card: Dict[str, Any]) -> Tuple[str, str]:
    return (str(card.get("page_id") or ""), str(card.get("table_id") or ""))


def bbox_from_record(record: Dict[str, Any]) -> Optional[Dict[str, float]]:
    bbox = record.get("table_region_bbox") or record.get("inferred_table_region_bbox")
    if not isinstance(bbox, dict):
        return None
    x0 = as_float(bbox.get("x0"), math.nan)
    y0 = as_float(bbox.get("y0"), math.nan)
    x1 = as_float(bbox.get("x1"), math.nan)
    y1 = as_float(bbox.get("y1"), math.nan)
    if not all(math.isfinite(v) for v in (x0, y0, x1, y1)):
        return None
    if x1 <= x0 or y1 <= y0:
        return None
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "width": x1 - x0, "height": y1 - y0, "coordinate_system": "pixels"}


def clamp_bbox(bbox: Dict[str, float], image_width: int, image_height: int, margin_pixels: int) -> Dict[str, float]:
    x0 = max(0.0, bbox["x0"] - margin_pixels)
    y0 = max(0.0, bbox["y0"] - margin_pixels)
    x1 = min(float(image_width), bbox["x1"] + margin_pixels)
    y1 = min(float(image_height), bbox["y1"] + margin_pixels)
    if x1 <= x0:
        x1 = min(float(image_width), x0 + 1.0)
    if y1 <= y0:
        y1 = min(float(image_height), y0 + 1.0)
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


def estimate_morphology_from_crop(image_path: Path, bbox: Dict[str, float], dark_threshold: int = 180) -> Dict[str, Any]:
    """Estimate table ruling evidence from a crop.

    Uses Pillow when available. The detector is intentionally lightweight and
    diagnostic: it detects dense horizontal/vertical dark runs and estimates
    intersections from line-count products. It is not answer authority.
    """
    try:
        from PIL import Image  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on environment
        return {
            "status": "IMAGE_ANALYSIS_UNAVAILABLE",
            "error": f"Pillow unavailable: {exc}",
            "horizontal_line_count": 0,
            "vertical_line_count": 0,
            "intersection_count": 0,
            "morphology_signal_strength": "NO_LINE_SIGNAL",
            "morphology_quality_score": 0.0,
        }

    try:
        with Image.open(image_path) as img:
            grayscale = img.convert("L")
            width, height = grayscale.size
            x0 = max(0, min(width - 1, int(round(bbox["x0"]))))
            y0 = max(0, min(height - 1, int(round(bbox["y0"]))))
            x1 = max(x0 + 1, min(width, int(round(bbox["x1"]))))
            y1 = max(y0 + 1, min(height, int(round(bbox["y1"]))))
            crop = grayscale.crop((x0, y0, x1, y1))
            crop_width, crop_height = crop.size
            pixels = crop.load()

            # Dense row/column thresholds. A true ruling line should occupy a
            # substantial part of the crop dimension. These thresholds avoid
            # mistaking isolated text glyphs for grid lines.
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
            horizontal_line_count = len(h_runs)
            vertical_line_count = len(v_runs)

            # Estimate intersections from centers with a small neighborhood check.
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

            signal = classify_signal(horizontal_line_count, vertical_line_count, intersections)
            score = morphology_score(horizontal_line_count, vertical_line_count, intersections, signal)
            return {
                "status": "IMAGE_ANALYSIS_OK",
                "image_width": width,
                "image_height": height,
                "crop_width": crop_width,
                "crop_height": crop_height,
                "dark_threshold": dark_threshold,
                "horizontal_line_count": horizontal_line_count,
                "vertical_line_count": vertical_line_count,
                "intersection_count": intersections,
                "morphology_signal_strength": signal,
                "morphology_quality_score": score,
            }
    except Exception as exc:
        return {
            "status": "IMAGE_ANALYSIS_FAILED",
            "error": str(exc),
            "horizontal_line_count": 0,
            "vertical_line_count": 0,
            "intersection_count": 0,
            "morphology_signal_strength": "NO_LINE_SIGNAL",
            "morphology_quality_score": 0.0,
        }


def classify_signal(horizontal: int, vertical: int, intersections: int) -> str:
    if horizontal >= 3 and vertical >= 2 and intersections >= 4:
        return "GRID"
    if horizontal >= 1 and vertical >= 1:
        return "PARTIAL_GRID"
    if horizontal >= 1 or vertical >= 1:
        return "WEAK_LINE_SIGNAL"
    return "NO_LINE_SIGNAL"


def morphology_score(horizontal: int, vertical: int, intersections: int, signal: str) -> float:
    multiplier = {"GRID": 10.0, "PARTIAL_GRID": 4.0, "WEAK_LINE_SIGNAL": 1.0, "NO_LINE_SIGNAL": 0.0}.get(signal, 0.0)
    return round(horizontal * 1.0 + vertical * 2.0 + intersections * 10.0 + multiplier, 3)


def signal_rank(signal: str) -> int:
    return {"NO_LINE_SIGNAL": 0, "WEAK_LINE_SIGNAL": 1, "PARTIAL_GRID": 2, "GRID": 3}.get(signal, 0)


def margins_from_args(value: Optional[str]) -> List[int]:
    if not value:
        return list(DEFAULT_MARGIN_PIXELS)
    margins: List[int] = []
    for raw in value.split(","):
        raw = raw.strip()
        if not raw:
            continue
        margins.append(max(0, int(float(raw))))
    return sorted(set(margins)) or list(DEFAULT_MARGIN_PIXELS)


def build_diagnostic_card(
    *,
    line_card: Dict[str, Any],
    bbox_card: Optional[Dict[str, Any]],
    image_root: Path,
    margin_pixels: Sequence[int],
) -> Dict[str, Any]:
    page_id, table_id = card_join_key(line_card)
    table_type = line_card.get("table_type")
    resolved_image_path = line_card.get("resolved_image_path") or (bbox_card or {}).get("resolved_image_path")
    image_path = normalize_path(resolved_image_path, image_root)
    base_bbox = bbox_from_record(bbox_card or {}) or bbox_from_record(line_card)

    page_horizontal = as_int(line_card.get("horizontal_line_count"))
    page_vertical = as_int(line_card.get("vertical_line_count"))
    page_intersections = as_int(line_card.get("intersection_count"))
    page_signal = str(line_card.get("morphology_signal_strength") or classify_signal(page_horizontal, page_vertical, page_intersections))
    page_score = as_float(line_card.get("morphology_quality_score"), morphology_score(page_horizontal, page_vertical, page_intersections, page_signal))

    card: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "diagnostic_card_id": stable_id("crop_margin_diag", page_id, table_id),
        "page_id": page_id,
        "table_id": table_id,
        "table_type": table_type,
        "resolved_image_path": str(resolved_image_path) if resolved_image_path else None,
        "bbox_source": (bbox_card or {}).get("bbox_source") or line_card.get("table_region_bbox_source"),
        "bbox_coverage_ratio": (bbox_card or {}).get("bbox_coverage_ratio"),
        "base_table_region_bbox": base_bbox,
        "page_morphology": {
            "horizontal_line_count": page_horizontal,
            "vertical_line_count": page_vertical,
            "intersection_count": page_intersections,
            "morphology_signal_strength": page_signal,
            "morphology_quality_score": page_score,
        },
        "margin_candidates": [],
        "best_margin_candidate": None,
        "margin_expansion_available": bool(base_bbox and image_path),
        "margin_expansion_successful": False,
        "margin_expansion_improves_grid_evidence": False,
        "margin_expansion_selected_for_recommendation": False,
        "margin_expansion_recommendation": "no_margin_experiment_available",
        "review_required": True,
        "review_flags": [],
        "recommended_actions": [],
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "retrieval_only_answer_allowed": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "unsafe_diagnostic_card": False,
    }

    if not base_bbox:
        card["review_flags"].append("missing_table_region_bbox_for_margin_experiment")
        card["recommended_actions"].append("resolve_table_region_bbox_before_margin_experiment")
        return card
    if not image_path or not image_path.exists():
        card["review_flags"].append("resolved_image_missing_for_margin_experiment")
        card["recommended_actions"].append("resolve_source_page_image_before_margin_experiment")
        return card

    try:
        from PIL import Image  # type: ignore
        with Image.open(image_path) as img:
            image_width, image_height = img.size
    except Exception as exc:
        card["review_flags"].append("image_dimension_read_failed")
        card["recommended_actions"].append("verify_resolved_tiff_can_be_read")
        card["image_read_error"] = str(exc)
        return card

    candidates: List[Dict[str, Any]] = []
    for margin in margin_pixels:
        expanded = clamp_bbox(base_bbox, image_width, image_height, margin)
        morphology = estimate_morphology_from_crop(image_path, expanded)
        candidate = {
            "margin_pixels": margin,
            "expanded_bbox": expanded,
            **morphology,
        }
        candidate["vertical_line_gain_vs_page"] = as_int(candidate.get("vertical_line_count")) - page_vertical
        candidate["intersection_gain_vs_page"] = as_int(candidate.get("intersection_count")) - page_intersections
        candidate["score_gain_vs_page"] = round(as_float(candidate.get("morphology_quality_score")) - page_score, 3)
        candidate["signal_rank_gain_vs_page"] = signal_rank(str(candidate.get("morphology_signal_strength"))) - signal_rank(page_signal)
        candidates.append(candidate)

    card["margin_candidates"] = candidates
    successful = [c for c in candidates if c.get("status") == "IMAGE_ANALYSIS_OK"]
    card["margin_expansion_successful"] = bool(successful)
    if not successful:
        card["review_flags"].append("margin_morphology_failed_for_all_candidates")
        card["recommended_actions"].append("verify_crop_margin_image_analysis")
        return card

    best = max(
        successful,
        key=lambda c: (
            signal_rank(str(c.get("morphology_signal_strength"))),
            as_int(c.get("intersection_count")),
            as_int(c.get("vertical_line_count")),
            as_float(c.get("morphology_quality_score")),
            -as_int(c.get("margin_pixels")),
        ),
    )
    card["best_margin_candidate"] = best
    improves = (
        as_int(best.get("vertical_line_gain_vs_page")) > 0
        or as_int(best.get("intersection_gain_vs_page")) > 0
        or as_int(best.get("signal_rank_gain_vs_page")) > 0
    )
    card["margin_expansion_improves_grid_evidence"] = improves
    card["margin_expansion_selected_for_recommendation"] = improves

    if improves:
        card["margin_expansion_recommendation"] = "candidate_margin_improves_grid_evidence"
        card["review_flags"].append("margin_expansion_candidate_improves_grid_evidence")
        card["recommended_actions"].append("review_margin_expansion_candidate_against_source_page")
        card["recommended_actions"].append("consider_margin_aware_crop_selection_for_this_table_type")
    else:
        card["margin_expansion_recommendation"] = "keep_page_morphology_or_improve_line_thresholds"
        card["review_flags"].append("margin_expansion_did_not_improve_grid_evidence")
        card["recommended_actions"].append("keep_page_morphology_for_current_crop")
        card["recommended_actions"].append("tune_crop_line_thresholds_or_crop_bbox_before_selection")

    return card


def build_report(
    *,
    table_line_geometry_path: Path,
    table_bbox_resolver_path: Path,
    image_root: Path,
    output_dir: Path,
    margin_pixels: Sequence[int],
    thresholds: Thresholds,
    write_quality: bool = True,
) -> Dict[str, Any]:
    line_payload = load_json(table_line_geometry_path)
    bbox_payload = load_json(table_bbox_resolver_path)

    line_cards = extract_cards(line_payload, "table_geometry_cards", "records")
    bbox_cards = extract_cards(bbox_payload, "table_bbox_cards", "records")
    bbox_by_key = {card_join_key(card): card for card in bbox_cards}

    diagnostic_cards = [
        build_diagnostic_card(
            line_card=card,
            bbox_card=bbox_by_key.get(card_join_key(card)),
            image_root=image_root,
            margin_pixels=margin_pixels,
        )
        for card in line_cards
    ]

    summary = summarize(
        diagnostic_cards=diagnostic_cards,
        line_payload=line_payload,
        bbox_payload=bbox_payload,
        margin_pixels=margin_pixels,
    )
    checks = evaluate_checks(summary, thresholds)
    quality_status = "PASS" if all(checks.values()) else "FAIL"
    summary["quality_status"] = quality_status
    summary["quality_fail_reasons"] = [name for name, ok in checks.items() if not ok]

    report = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT if quality_status == "PASS" else STATUS_NOT_READY,
        "quality_status": quality_status,
        "generated_at": utc_now_iso(),
        "input_paths": {
            "table_line_geometry": str(table_line_geometry_path),
            "table_bbox_resolver": str(table_bbox_resolver_path),
            "image_root": str(image_root),
        },
        "output_dir": str(output_dir),
        "margin_pixels": list(margin_pixels),
        "summary": summary,
        "checks": checks,
        "safety_contract": {
            "read_only_diagnostic": True,
            "no_postgres_writes": True,
            "no_qdrant_writes": True,
            "no_opensearch_writes": True,
            "no_source_truth_mutation": True,
            "no_answer_permission": True,
            "can_answer_directly": False,
            "can_prove_claims": False,
        },
        "diagnostic_cards": diagnostic_cards,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_table_crop_margin_expansion_experiment_v1.json"
    summary_path = output_dir / "trace_net_table_crop_margin_expansion_experiment_v1_summary.json"
    cards_path = output_dir / "trace_net_table_crop_margin_expansion_experiment_v1_cards.jsonl"
    manifest_path = output_dir / "trace_net_table_crop_margin_expansion_experiment_v1_manifest.json"

    write_json(report_path, report)
    write_json(summary_path, summary)
    write_jsonl(cards_path, diagnostic_cards)
    write_json(
        manifest_path,
        {
            "schema_version": f"{SCHEMA_VERSION}_manifest",
            "generated_at": report["generated_at"],
            "files": {
                "report": str(report_path),
                "summary": str(summary_path),
                "cards_jsonl": str(cards_path),
            },
            "quality_status": quality_status,
            "diagnostic_card_count": len(diagnostic_cards),
        },
    )

    if write_quality:
        quality_path = output_dir / "trace_net_table_crop_margin_expansion_experiment_v1_quality.json"
        quality_payload = {
            "schema_version": f"{SCHEMA_VERSION}_quality",
            "status": quality_status,
            "quality_status": quality_status,
            "generated_at": utc_now_iso(),
            "summary": summary,
            "checks": checks,
        }
        write_json(quality_path, quality_payload)

    return report


def summarize(*, diagnostic_cards: Sequence[Dict[str, Any]], line_payload: Dict[str, Any], bbox_payload: Dict[str, Any], margin_pixels: Sequence[int]) -> Dict[str, Any]:
    def count_if(predicate) -> int:
        return sum(1 for card in diagnostic_cards if predicate(card))

    successful_cards = [card for card in diagnostic_cards if card.get("margin_expansion_successful")]
    improvement_cards = [card for card in diagnostic_cards if card.get("margin_expansion_improves_grid_evidence")]

    return {
        "diagnostic_card_count": len(diagnostic_cards),
        "margin_pixels": list(margin_pixels),
        "margin_candidate_card_count": sum(len(card.get("margin_candidates") or []) for card in diagnostic_cards),
        "successful_image_card_count": len(successful_cards),
        "margin_improvement_card_count": len(improvement_cards),
        "margin_selected_for_recommendation_card_count": count_if(lambda c: c.get("margin_expansion_selected_for_recommendation")),
        "page_selected_source_card_count": count_if(lambda c: ((c.get("page_morphology") or {}).get("morphology_signal_strength") == "GRID")),
        "bbox_source_counts": counts(card.get("bbox_source") for card in diagnostic_cards),
        "recommendation_counts": counts(card.get("margin_expansion_recommendation") for card in diagnostic_cards),
        "review_required_card_count": count_if(lambda c: c.get("review_required")),
        "unsafe_diagnostic_card_count": count_if(lambda c: c.get("unsafe_diagnostic_card")),
        "answer_permission_count": count_if(lambda c: c.get("answer_permission")),
        "can_answer_directly_count": count_if(lambda c: c.get("can_answer_directly")),
        "can_prove_claims_count": count_if(lambda c: c.get("can_prove_claims")),
        "source_truth_mutation_allowed_count": count_if(lambda c: c.get("source_truth_mutation_allowed")),
        "source_truth_mutations_performed": sum(as_int(c.get("source_truth_mutations_performed")) for c in diagnostic_cards),
        "postgres_write_attempt_count": sum(as_int(c.get("postgres_write_attempt_count")) for c in diagnostic_cards),
        "qdrant_write_attempt_count": sum(as_int(c.get("qdrant_write_attempt_count")) for c in diagnostic_cards),
        "opensearch_write_attempt_count": sum(as_int(c.get("opensearch_write_attempt_count")) for c in diagnostic_cards),
        "source_quality_statuses": {
            "table_line_geometry": line_payload.get("quality_status"),
            "table_bbox_resolver": bbox_payload.get("quality_status"),
        },
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
    }


def counts(values: Iterable[Any]) -> Dict[str, int]:
    output: Dict[str, int] = {}
    for value in values:
        key = str(value)
        output[key] = output.get(key, 0) + 1
    return dict(sorted(output.items()))


def evaluate_checks(summary: Dict[str, Any], thresholds: Thresholds) -> Dict[str, bool]:
    checks = {
        "schema_version_ok": summary.get("schema_version") == SCHEMA_VERSION,
        "min_diagnostic_cards_met": as_int(summary.get("diagnostic_card_count")) >= thresholds.min_diagnostic_cards,
        "min_margin_candidate_cards_met": as_int(summary.get("margin_candidate_card_count")) >= thresholds.min_margin_candidate_cards,
        "min_successful_image_cards_met": as_int(summary.get("successful_image_card_count")) >= thresholds.min_successful_image_cards,
        "unsafe_diagnostic_cards_within_limit": as_int(summary.get("unsafe_diagnostic_card_count")) <= thresholds.max_unsafe_diagnostic_cards,
        "answer_permission_within_limit": as_int(summary.get("answer_permission_count")) <= thresholds.max_answer_permission_count,
        "source_truth_mutation_allowed_within_limit": as_int(summary.get("source_truth_mutation_allowed_count")) <= thresholds.max_source_truth_mutation_allowed,
        "write_attempts_zero": as_int(summary.get("postgres_write_attempt_count")) == 0 and as_int(summary.get("qdrant_write_attempt_count")) == 0 and as_int(summary.get("opensearch_write_attempt_count")) == 0,
    }
    source_statuses = summary.get("source_quality_statuses") or {}
    if thresholds.require_table_line_geometry_quality_pass:
        checks["table_line_geometry_quality_pass"] = source_statuses.get("table_line_geometry") == "PASS"
    if thresholds.require_table_bbox_resolver_quality_pass:
        checks["table_bbox_resolver_quality_pass"] = source_statuses.get("table_bbox_resolver") == "PASS"
    if thresholds.require_no_answer_permission:
        checks["answer_permission_zero"] = as_int(summary.get("answer_permission_count")) == 0
        checks["can_answer_directly_zero"] = as_int(summary.get("can_answer_directly_count")) == 0
        checks["can_prove_claims_zero"] = as_int(summary.get("can_prove_claims_count")) == 0
    return checks


def thresholds_from_args(args: argparse.Namespace) -> Thresholds:
    return Thresholds(
        min_diagnostic_cards=args.min_diagnostic_cards,
        min_margin_candidate_cards=args.min_margin_candidate_cards,
        min_successful_image_cards=args.min_successful_image_cards,
        max_unsafe_diagnostic_cards=args.max_unsafe_diagnostic_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_table_line_geometry_quality_pass=args.require_table_line_geometry_quality_pass,
        require_table_bbox_resolver_quality_pass=args.require_table_bbox_resolver_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net table crop margin expansion diagnostics.")
    parser.add_argument("--table-line-geometry", required=True, type=Path)
    parser.add_argument("--table-bbox-resolver", required=True, type=Path)
    parser.add_argument("--image-root", default=Path("."), type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--margin-pixels", default=",".join(str(m) for m in DEFAULT_MARGIN_PIXELS))
    parser.add_argument("--min-diagnostic-cards", type=int, default=1)
    parser.add_argument("--min-margin-candidate-cards", type=int, default=1)
    parser.add_argument("--min-successful-image-cards", type=int, default=1)
    parser.add_argument("--max-unsafe-diagnostic-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-line-geometry-quality-pass", action="store_true")
    parser.add_argument("--require-table-bbox-resolver-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = build_report(
        table_line_geometry_path=args.table_line_geometry,
        table_bbox_resolver_path=args.table_bbox_resolver,
        image_root=args.image_root,
        output_dir=args.output_dir,
        margin_pixels=margins_from_args(args.margin_pixels),
        thresholds=thresholds_from_args(args),
        write_quality=args.quality,
    )
    summary = report["summary"]
    print("TRACE-Net Table Crop Margin Expansion Experiment v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "diagnostic_card_count",
        "margin_candidate_card_count",
        "successful_image_card_count",
        "margin_improvement_card_count",
        "margin_selected_for_recommendation_card_count",
        "review_required_card_count",
        "unsafe_diagnostic_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {args.output_dir / 'trace_net_table_crop_margin_expansion_experiment_v1.json'}")
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
