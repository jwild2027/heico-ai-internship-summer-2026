"""TRACE-Net Table Full Region Recovery v1.

Read-only diagnostic/artifact builder that attempts to recover a fuller table
region from existing table bbox, OCR bbox enrichment, detector overlay audit,
and table line geometry artifacts.

This module does not write to databases, mutate source truth, grant answer
permission, or prove claims. It only emits advisory recovery cards that can be
reviewed and optionally fed into later crop-selection stages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "trace_net_table_full_region_recovery_v1"
QUALITY_SCHEMA_VERSION = "trace_net_table_full_region_recovery_v1_quality"

ZERO_AUTHORITY_FLAGS = {
    "answer_permission": False,
    "can_answer_directly": False,
    "can_prove_claims": False,
    "retrieval_only_answer_allowed": False,
    "source_truth_mutation_allowed": False,
    "source_truth_mutations_performed": 0,
    "postgres_write_attempt_count": 0,
    "qdrant_write_attempt_count": 0,
    "opensearch_write_attempt_count": 0,
}

CARD_LIST_KEYS = (
    "table_bbox_cards",
    "bbox_cards",
    "table_ocr_bbox_enrichment_cards",
    "audit_cards",
    "table_geometry_cards",
    "recovery_cards",
    "cards",
)

BBOX_KEYS = (
    "table_region_bbox",
    "inferred_table_region_bbox",
    "original_inferred_table_region_bbox",
    "content_band_bbox",
    "expanded_full_table_bbox",
    "expanded_bbox",
    "bbox",
)

MARGIN_PIXELS_DEFAULT = 35.0


@dataclass(frozen=True)
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float
    source: str = "unknown"
    confidence: Optional[float] = None

    @property
    def width(self) -> float:
        return max(0.0, self.x1 - self.x0)

    @property
    def height(self) -> float:
        return max(0.0, self.y1 - self.y0)

    @property
    def area(self) -> float:
        return self.width * self.height

    def valid(self) -> bool:
        return self.width > 1.0 and self.height > 1.0 and all(math.isfinite(v) for v in (self.x0, self.y0, self.x1, self.y1))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "coordinate_system": "pixels",
            "x0": round(self.x0, 3),
            "y0": round(self.y0, 3),
            "x1": round(self.x1, 3),
            "y1": round(self.y1, 3),
            "width": round(self.width, 3),
            "height": round(self.height, 3),
            "source": self.source,
            "confidence": self.confidence,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True) + "\n")


def get_card_list(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    for key in CARD_LIST_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            return [v for v in value if isinstance(v, dict)]
    return []


def key_for(card: Mapping[str, Any]) -> Tuple[str, str]:
    return (str(card.get("page_id") or ""), str(card.get("table_id") or card.get("target_id") or ""))


def index_cards(cards: Sequence[Mapping[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for card in cards:
        k = key_for(card)
        if k[0] or k[1]:
            out[k] = dict(card)
    return out


def find_matching(card_index: Mapping[Tuple[str, str], Dict[str, Any]], key: Tuple[str, str]) -> Optional[Dict[str, Any]]:
    if key in card_index:
        return card_index[key]
    page_id, table_id = key
    if page_id:
        page_matches = [card for (p, _), card in card_index.items() if p == page_id]
        if len(page_matches) == 1:
            return dict(page_matches[0])
    if table_id:
        table_matches = [card for (_, t), card in card_index.items() if t == table_id]
        if len(table_matches) == 1:
            return dict(table_matches[0])
    return None


def as_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def parse_bbox(value: Any, source: str, confidence: Optional[float] = None) -> Optional[BBox]:
    if not isinstance(value, Mapping):
        return None
    x0 = as_float(value.get("x0"))
    y0 = as_float(value.get("y0"))
    x1 = as_float(value.get("x1"))
    y1 = as_float(value.get("y1"))
    if x0 is None or y0 is None:
        return None
    if x1 is None:
        width = as_float(value.get("width"))
        x1 = x0 + width if width is not None else None
    if y1 is None:
        height = as_float(value.get("height"))
        y1 = y0 + height if height is not None else None
    if x1 is None or y1 is None:
        return None
    bbox = BBox(float(x0), float(y0), float(x1), float(y1), source=source, confidence=confidence)
    return bbox if bbox.valid() else None


def collect_bboxes(card: Optional[Mapping[str, Any]], prefix: str) -> List[BBox]:
    if not isinstance(card, Mapping):
        return []
    out: List[BBox] = []
    confidence = as_float(card.get("bbox_confidence") or card.get("geometry_confidence"))
    for key in BBOX_KEYS:
        bbox = parse_bbox(card.get(key), f"{prefix}.{key}", confidence=confidence)
        if bbox:
            out.append(bbox)
    # nested detector candidates in overlay/parity-style cards
    for nested_key in ("production_best_candidate", "estimator_best_candidate", "best_margin_candidate"):
        nested = card.get(nested_key)
        if isinstance(nested, Mapping):
            bbox = parse_bbox(nested.get("expanded_bbox"), f"{prefix}.{nested_key}.expanded_bbox")
            if bbox:
                out.append(bbox)
    return dedupe_bboxes(out)


def dedupe_bboxes(bboxes: Sequence[BBox]) -> List[BBox]:
    seen = set()
    out: List[BBox] = []
    for b in bboxes:
        sig = (round(b.x0, 2), round(b.y0, 2), round(b.x1, 2), round(b.y1, 2), b.source)
        if sig not in seen:
            seen.add(sig)
            out.append(b)
    return out


def union_bbox(bboxes: Sequence[BBox], source: str = "union") -> Optional[BBox]:
    valid = [b for b in bboxes if b.valid()]
    if not valid:
        return None
    return BBox(
        min(b.x0 for b in valid),
        min(b.y0 for b in valid),
        max(b.x1 for b in valid),
        max(b.y1 for b in valid),
        source=source,
    )


def expand_bbox(bbox: BBox, margin: float, page_width: Optional[float], page_height: Optional[float], source: str) -> BBox:
    x0 = bbox.x0 - margin
    y0 = bbox.y0 - margin
    x1 = bbox.x1 + margin
    y1 = bbox.y1 + margin
    if page_width and page_width > 0:
        x0 = max(0.0, x0)
        x1 = min(float(page_width), x1)
    if page_height and page_height > 0:
        y0 = max(0.0, y0)
        y1 = min(float(page_height), y1)
    return BBox(x0, y0, x1, y1, source=source)


def area_ratio(bbox: Optional[BBox], page_width: Optional[float], page_height: Optional[float]) -> Optional[float]:
    if not bbox or not page_width or not page_height or page_width <= 0 or page_height <= 0:
        return None
    return round(bbox.area / (float(page_width) * float(page_height)), 6)


def infer_page_dimensions(cards: Sequence[Optional[Mapping[str, Any]]], image_root: Optional[Path] = None) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    # Prefer explicit dimensions in any card.
    for card in cards:
        if not isinstance(card, Mapping):
            continue
        for w_key, h_key in (("image_width", "image_height"), ("page_width", "page_height"), ("width", "height")):
            w = as_float(card.get(w_key))
            h = as_float(card.get(h_key))
            if w and h and w > 100 and h > 100:
                return int(w), int(h), f"explicit:{w_key}/{h_key}"
        for key in BBOX_KEYS:
            value = card.get(key)
            if isinstance(value, Mapping):
                w = as_float(value.get("page_width") or value.get("image_width"))
                h = as_float(value.get("page_height") or value.get("image_height"))
                if w and h and w > 100 and h > 100:
                    return int(w), int(h), f"bbox:{key}"
    # Optional image probing.
    if image_root:
        try:
            from PIL import Image  # type: ignore
        except Exception:
            Image = None  # type: ignore
        if Image is not None:
            for card in cards:
                if not isinstance(card, Mapping):
                    continue
                for path_key in ("resolved_image_path", "image_path", "source_image_path", "page_image_path"):
                    raw = card.get(path_key)
                    if not raw:
                        continue
                    p = Path(str(raw))
                    if not p.is_absolute():
                        p = image_root / p
                    if p.exists():
                        try:
                            with Image.open(p) as im:
                                return int(im.width), int(im.height), f"image:{path_key}"
                        except Exception:
                            continue
    # Fallback to max bbox extent. This is less reliable but useful for diagnostics.
    bboxes: List[BBox] = []
    for card in cards:
        bboxes.extend(collect_bboxes(card, "dimension_fallback"))
    if bboxes:
        max_x = max(b.x1 for b in bboxes)
        max_y = max(b.y1 for b in bboxes)
        if max_x > 100 and max_y > 100:
            return int(math.ceil(max_x)), int(math.ceil(max_y)), "bbox_extent_fallback"
    return None, None, None


def stable_id(*parts: Any) -> str:
    raw = "::".join(str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def safe_get_counts(card: Optional[Mapping[str, Any]], *keys: str) -> int:
    if not isinstance(card, Mapping):
        return 0
    for key in keys:
        value = card.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    return 0


def build_recovery_card(
    bbox_card: Mapping[str, Any],
    ocr_card: Optional[Mapping[str, Any]],
    overlay_card: Optional[Mapping[str, Any]],
    geometry_card: Optional[Mapping[str, Any]],
    image_root: Optional[Path],
    expansion_margin_pixels: float,
    max_full_page_coverage_ratio: float,
) -> Dict[str, Any]:
    page_id = str(bbox_card.get("page_id") or "")
    table_id = str(bbox_card.get("table_id") or bbox_card.get("target_id") or "")
    table_type = str(bbox_card.get("table_type") or (ocr_card or {}).get("table_type") or (geometry_card or {}).get("table_type") or "unknown")

    page_width, page_height, page_dim_source = infer_page_dimensions([bbox_card, ocr_card, overlay_card, geometry_card], image_root=image_root)

    original_bboxes = collect_bboxes(bbox_card, "table_bbox_resolver")
    ocr_bboxes = collect_bboxes(ocr_card, "table_ocr_bbox_enrichment")
    overlay_bboxes = collect_bboxes(overlay_card, "table_detector_overlay_audit")
    geometry_bboxes = collect_bboxes(geometry_card, "table_line_geometry")

    bbox_sources: List[BBox] = []
    bbox_sources.extend(original_bboxes[:3])
    bbox_sources.extend(ocr_bboxes[:4])
    bbox_sources.extend(overlay_bboxes[:4])
    bbox_sources.extend(geometry_bboxes[:2])
    bbox_sources = dedupe_bboxes(bbox_sources)

    original_crop_bbox = original_bboxes[0] if original_bboxes else None
    ocr_content_bbox = None
    for b in ocr_bboxes:
        if "content_band_bbox" in b.source:
            ocr_content_bbox = b
            break
    if ocr_content_bbox is None and ocr_bboxes:
        ocr_content_bbox = ocr_bboxes[0]

    line_projection_bbox = overlay_bboxes[0] if overlay_bboxes else None
    base_union = union_bbox(bbox_sources, source="full_table_recovery_union")
    recovered = expand_bbox(base_union, expansion_margin_pixels, page_width, page_height, "expanded_full_table_bbox") if base_union else None

    original_ratio = area_ratio(original_crop_bbox, page_width, page_height)
    recovered_ratio = area_ratio(recovered, page_width, page_height)
    ocr_ratio = area_ratio(ocr_content_bbox, page_width, page_height)
    line_ratio = area_ratio(line_projection_bbox, page_width, page_height)

    matched_ocr_bbox_count = safe_get_counts(ocr_card, "matched_ocr_bbox_count", "ocr_bbox_record_count")
    part_number_match_count = safe_get_counts(ocr_card, "part_number_ocr_match_count", "part_number_match_count")
    detector_disagreement = bool((overlay_card or {}).get("detector_disagreement"))
    overlay_verdict = str((overlay_card or {}).get("human_review_verdict") or (overlay_card or {}).get("overlay_human_review_verdict") or "UNAVAILABLE")

    source_count = len(bbox_sources)
    has_ocr_evidence = matched_ocr_bbox_count > 0 or part_number_match_count > 0 or ocr_content_bbox is not None
    has_line_evidence = line_projection_bbox is not None or bool((overlay_card or {}).get("line_overlay_candidate_card_count"))
    not_full_page = recovered_ratio is None or recovered_ratio <= max_full_page_coverage_ratio
    expansion_non_degenerate = bool(recovered and recovered.valid() and (original_crop_bbox is None or recovered.area >= original_crop_bbox.area))

    left_right_table_coverage_ok = None
    top_bottom_table_coverage_ok = None
    if recovered and page_width and page_height:
        left_right_table_coverage_ok = recovered.width >= 0.35 * float(page_width)
        top_bottom_table_coverage_ok = recovered.height >= 0.20 * float(page_height)

    crop_recovery_ready = bool(recovered and expansion_non_degenerate and has_ocr_evidence and source_count >= 2 and not_full_page)
    if overlay_verdict in {"ESTIMATOR_LINES_TEXT_OR_NOISE", "MIXED_OR_UNCLEAR"}:
        # Recovery can still be useful, but should not be treated as trusted line geometry.
        crop_recovery_ready = False

    review_flags: List[str] = []
    recommended_actions: List[str] = []
    if not recovered:
        review_flags.append("full_table_region_recovery_missing_bbox")
        recommended_actions.append("inspect_table_bbox_resolver_and_ocr_bbox_inputs")
    if not has_ocr_evidence:
        review_flags.append("full_table_region_recovery_missing_ocr_evidence")
        recommended_actions.append("regenerate_or_inspect_ocr_bbox_sidecars")
    if detector_disagreement:
        review_flags.append("detector_disagreement_requires_overlay_review")
        recommended_actions.append("review_detector_overlay_before_trusting_line_geometry")
    if overlay_verdict in {"UNREVIEWED", "UNAVAILABLE"}:
        review_flags.append("overlay_verdict_not_reviewed")
        recommended_actions.append("label_overlay_verdict_before_crop_selection")
    if recovered_ratio is not None and recovered_ratio > max_full_page_coverage_ratio:
        review_flags.append("recovered_bbox_too_page_like")
        recommended_actions.append("tighten_full_table_recovery_bbox")
    if crop_recovery_ready:
        review_flags.append("full_table_region_recovery_ready_for_review")
        recommended_actions.append("compare_recovered_bbox_against_source_page")
    else:
        review_flags.append("full_table_region_recovery_advisory_only")

    return {
        "schema_version": SCHEMA_VERSION,
        "recovery_card_id": f"table_full_region_recovery::{stable_id(page_id, table_id)}",
        "page_id": page_id,
        "table_id": table_id,
        "table_type": table_type,
        "source_stage": "table_full_region_recovery",
        "original_crop_bbox": original_crop_bbox.to_dict() if original_crop_bbox else None,
        "ocr_content_bbox": ocr_content_bbox.to_dict() if ocr_content_bbox else None,
        "line_projection_bbox": line_projection_bbox.to_dict() if line_projection_bbox else None,
        "expanded_full_table_bbox": recovered.to_dict() if recovered else None,
        "bbox_source_count": source_count,
        "bbox_sources": [b.to_dict() for b in bbox_sources],
        "page_width": page_width,
        "page_height": page_height,
        "page_dimension_source": page_dim_source,
        "original_crop_coverage_ratio": original_ratio,
        "ocr_content_coverage_ratio": ocr_ratio,
        "line_projection_coverage_ratio": line_ratio,
        "full_table_coverage_ratio": recovered_ratio,
        "full_table_not_page_like": not_full_page,
        "left_right_table_coverage_ok": left_right_table_coverage_ok,
        "top_bottom_table_coverage_ok": top_bottom_table_coverage_ok,
        "part_number_coverage_ok": part_number_match_count > 0,
        "matched_ocr_bbox_count": matched_ocr_bbox_count,
        "part_number_ocr_match_count": part_number_match_count,
        "detector_disagreement": detector_disagreement,
        "overlay_human_review_verdict": overlay_verdict,
        "crop_recovery_status": "FULL_TABLE_REGION_RECOVERY_READY" if crop_recovery_ready else "FULL_TABLE_REGION_RECOVERY_REVIEW_REQUIRED",
        "crop_recovery_ready": crop_recovery_ready,
        "review_required": True,
        "review_flags": sorted(set(review_flags)),
        "recommended_actions": sorted(set(recommended_actions)),
        "requires_human_review": True,
        "full_table_region_recovery_advisory_only": True,
        **ZERO_AUTHORITY_FLAGS,
    }


def summarize(cards: Sequence[Mapping[str, Any]], source_quality_statuses: Mapping[str, str], output_dir: Path) -> Dict[str, Any]:
    def count_if(key: str, truthy: bool = True) -> int:
        return sum(1 for c in cards if bool(c.get(key)) is truthy)

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "TABLE_FULL_REGION_RECOVERY_BUILT",
        "quality_status": "PASS",
        "recovery_card_count": len(cards),
        "crop_recovery_ready_card_count": count_if("crop_recovery_ready"),
        "crop_recovery_review_required_card_count": count_if("review_required"),
        "expanded_full_table_bbox_card_count": count_if("expanded_full_table_bbox"),
        "ocr_content_bbox_card_count": count_if("ocr_content_bbox"),
        "line_projection_bbox_card_count": count_if("line_projection_bbox"),
        "part_number_coverage_ok_card_count": count_if("part_number_coverage_ok"),
        "detector_disagreement_card_count": count_if("detector_disagreement"),
        "overlay_unreviewed_card_count": sum(1 for c in cards if c.get("overlay_human_review_verdict") in {"UNREVIEWED", "UNAVAILABLE"}),
        "recovered_bbox_too_page_like_card_count": sum(1 for c in cards if "recovered_bbox_too_page_like" in (c.get("review_flags") or [])),
        "unsafe_recovery_card_count": sum(1 for c in cards if c.get("unsafe_recovery_card")),
        "answer_permission_count": sum(1 for c in cards if c.get("answer_permission")),
        "can_answer_directly_count": sum(1 for c in cards if c.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for c in cards if c.get("can_prove_claims")),
        "source_truth_mutation_allowed_count": sum(1 for c in cards if c.get("source_truth_mutation_allowed")),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "source_truth_mutations_performed": 0,
        "source_quality_statuses": dict(source_quality_statuses),
        "output_dir": str(output_dir),
    }


def evaluate_quality(report: Mapping[str, Any], thresholds: Mapping[str, Any]) -> Tuple[str, Dict[str, bool], List[str]]:
    summary = report.get("summary") or {}
    checks = {
        "schema_version_ok": report.get("schema_version") == SCHEMA_VERSION,
        "min_recovery_cards_met": int(summary.get("recovery_card_count") or 0) >= int(thresholds.get("min_recovery_cards") or 0),
        "min_expanded_full_table_bbox_cards_met": int(summary.get("expanded_full_table_bbox_card_count") or 0) >= int(thresholds.get("min_expanded_full_table_bbox_cards") or 0),
        "min_ocr_content_bbox_cards_met": int(summary.get("ocr_content_bbox_card_count") or 0) >= int(thresholds.get("min_ocr_content_bbox_cards") or 0),
        "unsafe_recovery_cards_within_limit": int(summary.get("unsafe_recovery_card_count") or 0) <= int(thresholds.get("max_unsafe_recovery_cards") or 0),
        "answer_permission_within_limit": int(summary.get("answer_permission_count") or 0) <= int(thresholds.get("max_answer_permission_count") or 0),
        "source_truth_mutation_allowed_within_limit": int(summary.get("source_truth_mutation_allowed_count") or 0) <= int(thresholds.get("max_source_truth_mutation_allowed") or 0),
    }
    source_statuses = summary.get("source_quality_statuses") or {}
    if thresholds.get("require_table_bbox_resolver_quality_pass"):
        checks["table_bbox_resolver_quality_pass"] = source_statuses.get("table_bbox_resolver") == "PASS"
    if thresholds.get("require_table_ocr_bbox_enrichment_quality_pass"):
        checks["table_ocr_bbox_enrichment_quality_pass"] = source_statuses.get("table_ocr_bbox_enrichment") == "PASS"
    if thresholds.get("require_no_answer_permission"):
        checks["no_answer_permission"] = int(summary.get("answer_permission_count") or 0) == 0
    fail_reasons = [k for k, ok in checks.items() if not ok]
    return ("PASS" if not fail_reasons else "FAIL", checks, fail_reasons)


def build_report(
    table_bbox_resolver_path: Path,
    table_ocr_bbox_enrichment_path: Path,
    output_dir: Path,
    table_detector_overlay_audit_path: Optional[Path] = None,
    table_line_geometry_path: Optional[Path] = None,
    image_root: Optional[Path] = None,
    expansion_margin_pixels: float = MARGIN_PIXELS_DEFAULT,
    max_full_page_coverage_ratio: float = 0.95,
    thresholds: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    thresholds = dict(thresholds or {})
    output_dir.mkdir(parents=True, exist_ok=True)

    bbox_payload = read_json(table_bbox_resolver_path)
    ocr_payload = read_json(table_ocr_bbox_enrichment_path)
    overlay_payload = read_json(table_detector_overlay_audit_path) if table_detector_overlay_audit_path and table_detector_overlay_audit_path.exists() else {}
    geometry_payload = read_json(table_line_geometry_path) if table_line_geometry_path and table_line_geometry_path.exists() else {}

    bbox_cards = get_card_list(bbox_payload)
    ocr_cards = get_card_list(ocr_payload)
    overlay_cards = get_card_list(overlay_payload)
    geometry_cards = get_card_list(geometry_payload)

    ocr_index = index_cards(ocr_cards)
    overlay_index = index_cards(overlay_cards)
    geometry_index = index_cards(geometry_cards)

    cards: List[Dict[str, Any]] = []
    for bbox_card in bbox_cards:
        key = key_for(bbox_card)
        cards.append(
            build_recovery_card(
                bbox_card=bbox_card,
                ocr_card=find_matching(ocr_index, key),
                overlay_card=find_matching(overlay_index, key),
                geometry_card=find_matching(geometry_index, key),
                image_root=image_root,
                expansion_margin_pixels=expansion_margin_pixels,
                max_full_page_coverage_ratio=max_full_page_coverage_ratio,
            )
        )

    source_quality_statuses = {
        "table_bbox_resolver": str(bbox_payload.get("quality_status") or (bbox_payload.get("summary") or {}).get("quality_status") or "UNKNOWN"),
        "table_ocr_bbox_enrichment": str(ocr_payload.get("quality_status") or (ocr_payload.get("summary") or {}).get("quality_status") or "UNKNOWN"),
    }
    if overlay_payload:
        source_quality_statuses["table_detector_overlay_audit"] = str(overlay_payload.get("quality_status") or (overlay_payload.get("summary") or {}).get("quality_status") or "UNKNOWN")
    if geometry_payload:
        source_quality_statuses["table_line_geometry"] = str(geometry_payload.get("quality_status") or (geometry_payload.get("summary") or {}).get("quality_status") or "UNKNOWN")

    summary = summarize(cards, source_quality_statuses, output_dir)
    report: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "TABLE_FULL_REGION_RECOVERY_BUILT",
        "quality_status": "PASS",
        "generated_at": utc_now(),
        "inputs": {
            "table_bbox_resolver": str(table_bbox_resolver_path),
            "table_ocr_bbox_enrichment": str(table_ocr_bbox_enrichment_path),
            "table_detector_overlay_audit": str(table_detector_overlay_audit_path) if table_detector_overlay_audit_path else None,
            "table_line_geometry": str(table_line_geometry_path) if table_line_geometry_path else None,
            "image_root": str(image_root) if image_root else None,
        },
        "settings": {
            "expansion_margin_pixels": expansion_margin_pixels,
            "max_full_page_coverage_ratio": max_full_page_coverage_ratio,
        },
        "summary": summary,
        "recovery_cards": cards,
    }
    quality_status, checks, fail_reasons = evaluate_quality(report, thresholds)
    report["quality_status"] = quality_status
    report["status"] = "TABLE_FULL_REGION_RECOVERY_BUILT" if quality_status == "PASS" else "TABLE_FULL_REGION_RECOVERY_NOT_READY"
    report["summary"]["quality_status"] = quality_status
    report["summary"]["status"] = report["status"]
    report["summary"]["checks"] = checks
    report["summary"]["quality_fail_reasons"] = fail_reasons
    report["checks"] = checks
    report["quality_fail_reasons"] = fail_reasons

    report_path = output_dir / "trace_net_table_full_region_recovery_v1.json"
    cards_path = output_dir / "trace_net_table_full_region_recovery_v1_cards.jsonl"
    summary_path = output_dir / "trace_net_table_full_region_recovery_v1_summary.json"
    quality_path = output_dir / "trace_net_table_full_region_recovery_v1_quality.json"
    manifest_path = output_dir / "trace_net_table_full_region_recovery_v1_manifest.json"

    write_json(report_path, report)
    write_jsonl(cards_path, cards)
    write_json(summary_path, report["summary"])
    quality_payload = build_quality_payload(report, thresholds)
    write_json(quality_path, quality_payload)
    write_json(manifest_path, {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": report["generated_at"],
        "files": {
            "report": str(report_path),
            "cards": str(cards_path),
            "summary": str(summary_path),
            "quality": str(quality_path),
        },
        "safety_contract": {
            "read_only": True,
            "no_answer_permission": True,
            "no_claim_proof_authority": True,
            "no_source_truth_mutation": True,
            "no_database_writes": True,
        },
    })
    return report


def build_quality_payload(report: Mapping[str, Any], thresholds: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    thresholds = dict(thresholds or {})
    quality_status, checks, fail_reasons = evaluate_quality(report, thresholds)
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "status": quality_status,
        "quality_status": quality_status,
        "generated_at": utc_now(),
        "summary": dict(report.get("summary") or {}),
        "checks": checks,
        "quality_fail_reasons": fail_reasons,
    }


def thresholds_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "min_recovery_cards": args.min_recovery_cards,
        "min_expanded_full_table_bbox_cards": args.min_expanded_full_table_bbox_cards,
        "min_ocr_content_bbox_cards": args.min_ocr_content_bbox_cards,
        "max_unsafe_recovery_cards": args.max_unsafe_recovery_cards,
        "max_answer_permission_count": args.max_answer_permission_count,
        "max_source_truth_mutation_allowed": args.max_source_truth_mutation_allowed,
        "require_table_bbox_resolver_quality_pass": args.require_table_bbox_resolver_quality_pass,
        "require_table_ocr_bbox_enrichment_quality_pass": args.require_table_ocr_bbox_enrichment_quality_pass,
        "require_no_answer_permission": args.require_no_answer_permission,
    }


def print_report(report: Mapping[str, Any]) -> None:
    summary = report.get("summary") or {}
    print("TRACE-Net Table Full Region Recovery v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in (
        "recovery_card_count",
        "crop_recovery_ready_card_count",
        "crop_recovery_review_required_card_count",
        "expanded_full_table_bbox_card_count",
        "ocr_content_bbox_card_count",
        "line_projection_bbox_card_count",
        "part_number_coverage_ok_card_count",
        "detector_disagreement_card_count",
        "overlay_unreviewed_card_count",
        "recovered_bbox_too_page_like_card_count",
        "unsafe_recovery_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Table Full Region Recovery v1 artifact.")
    parser.add_argument("--table-bbox-resolver", required=True, type=Path)
    parser.add_argument("--table-ocr-bbox-enrichment", required=True, type=Path)
    parser.add_argument("--table-detector-overlay-audit", type=Path)
    parser.add_argument("--table-line-geometry", type=Path)
    parser.add_argument("--image-root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--expansion-margin-pixels", type=float, default=MARGIN_PIXELS_DEFAULT)
    parser.add_argument("--max-full-page-coverage-ratio", type=float, default=0.95)
    parser.add_argument("--min-recovery-cards", type=int, default=1)
    parser.add_argument("--min-expanded-full-table-bbox-cards", type=int, default=1)
    parser.add_argument("--min-ocr-content-bbox-cards", type=int, default=1)
    parser.add_argument("--max-unsafe-recovery-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-bbox-resolver-quality-pass", action="store_true")
    parser.add_argument("--require-table-ocr-bbox-enrichment-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = build_report(
        table_bbox_resolver_path=args.table_bbox_resolver,
        table_ocr_bbox_enrichment_path=args.table_ocr_bbox_enrichment,
        table_detector_overlay_audit_path=args.table_detector_overlay_audit,
        table_line_geometry_path=args.table_line_geometry,
        image_root=args.image_root,
        output_dir=args.output_dir,
        expansion_margin_pixels=args.expansion_margin_pixels,
        max_full_page_coverage_ratio=args.max_full_page_coverage_ratio,
        thresholds=thresholds_from_args(args),
    )
    print_report(report)
    print(f" report_path: {args.output_dir / 'trace_net_table_full_region_recovery_v1.json'}")
    print(f" quality_path: {args.output_dir / 'trace_net_table_full_region_recovery_v1_quality.json'}")
    return 0 if report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
