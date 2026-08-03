"""TRACE-Net Table BBox Resolver v1.

Read-only table-region bounding-box resolver for TRACE-Net table geometry.

The resolver is intentionally conservative:
* explicit OCR/table/cell/row bounding boxes are preferred when present;
* OCR bbox enrichment crop candidates are preferred over low-specificity
  aggregated/heuristic boxes when they pass conservative crop gates;
* aggregated record boxes are used when enough page/table-scoped boxes exist;
* otherwise a low-confidence page-content crop candidate is emitted so the next
  morphology pass can crop, while review flags preserve that the bbox is
  heuristic and not source truth.

Safety contract: this module never writes to Postgres, Qdrant, OpenSearch, or
source-truth artifacts. All boxes are advisory/retrieval-routing metadata only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, MutableMapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "trace_net_table_bbox_resolver_v1"
STATUS_BUILT = "TABLE_BBOX_RESOLVER_BUILT"
STATUS_NOT_READY = "TABLE_BBOX_RESOLVER_NOT_READY"
QUALITY_SCHEMA_VERSION = "trace_net_table_bbox_resolver_v1_quality"

IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".webp", ".bmp"}

OCR_ENRICHMENT_BBOX_SOURCES = {
    "ocr_part_number_token_match",
    "ocr_table_text_token_match",
    "ocr_token_match",
    "ocr_bbox_enrichment",
}

ID_KEYS = ("page_id", "source_page_id", "table_id", "normalized_table_id", "row_id", "cell_id")
TABLE_ID_KEYS = ("table_id", "normalized_table_id", "source_table_id")
PAGE_ID_KEYS = ("page_id", "source_page_id")
ROW_ID_KEYS = ("row_id", "normalized_row_id")
CELL_ID_KEYS = ("cell_id", "normalized_cell_id")

BBOX_KEYS = (
    "table_region_bbox",
    "table_bbox",
    "bbox",
    "bounding_box",
    "bounds",
    "box",
    "cell_bbox",
    "row_bbox",
    "ocr_bbox",
    "word_bbox",
    "text_bbox",
)

X0_KEYS = ("x0", "x_min", "xmin", "left")
Y0_KEYS = ("y0", "y_min", "ymin", "top")
X1_KEYS = ("x1", "x_max", "xmax", "right")
Y1_KEYS = ("y1", "y_max", "ymax", "bottom")
WIDTH_KEYS = ("width", "w")
HEIGHT_KEYS = ("height", "h")
X_KEYS = ("x", "left")
Y_KEYS = ("y", "top")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def stable_id(prefix: str, *parts: Any) -> str:
    h = hashlib.sha256("::".join(str(p) for p in parts if p is not None).encode("utf-8")).hexdigest()[:14]
    return f"{prefix}_{h}"


def as_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, str) and not value.strip():
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def first_present(mapping: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in mapping and mapping.get(key) is not None:
            return mapping.get(key)
    return None


def normalize_path(value: Any, image_root: Optional[Path] = None) -> Optional[Path]:
    if not value:
        return None
    raw = str(value).replace("\\", "/")
    path = Path(raw)
    candidates = []
    if path.is_absolute():
        candidates.append(path)
    else:
        candidates.append(Path(raw))
        if image_root is not None:
            candidates.append(image_root / raw)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1] if candidates else None


def image_dimensions(path: Optional[Path]) -> Tuple[Optional[int], Optional[int]]:
    if path is None or not path.exists() or not path.is_file():
        return None, None
    try:
        from PIL import Image  # type: ignore

        with Image.open(path) as img:
            return int(img.width), int(img.height)
    except Exception:
        return None, None


def clamp_bbox(x0: float, y0: float, x1: float, y1: float, width: Optional[int], height: Optional[int]) -> Optional[Dict[str, Any]]:
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    if width and height:
        # Normalized coordinates are common in OCR exports. If all values look
        # normalized, scale them into pixel coordinates.
        if 0 <= x0 <= 1 and 0 <= x1 <= 1 and 0 <= y0 <= 1 and 0 <= y1 <= 1:
            x0, x1 = x0 * width, x1 * width
            y0, y1 = y0 * height, y1 * height
        x0 = max(0, min(float(width), x0))
        x1 = max(0, min(float(width), x1))
        y0 = max(0, min(float(height), y0))
        y1 = max(0, min(float(height), y1))
    if x1 - x0 < 1 or y1 - y0 < 1:
        return None
    return {
        "x0": round(x0, 3),
        "y0": round(y0, 3),
        "x1": round(x1, 3),
        "y1": round(y1, 3),
        "width": round(x1 - x0, 3),
        "height": round(y1 - y0, 3),
        "coordinate_system": "pixels" if width and height else "source_units",
    }


def bbox_from_mapping(mapping: Mapping[str, Any], width: Optional[int], height: Optional[int]) -> Optional[Dict[str, Any]]:
    x0 = as_float(first_present(mapping, X0_KEYS))
    y0 = as_float(first_present(mapping, Y0_KEYS))
    x1 = as_float(first_present(mapping, X1_KEYS))
    y1 = as_float(first_present(mapping, Y1_KEYS))
    if x0 is not None and y0 is not None and x1 is not None and y1 is not None:
        return clamp_bbox(x0, y0, x1, y1, width, height)

    x = as_float(first_present(mapping, X_KEYS))
    y = as_float(first_present(mapping, Y_KEYS))
    w = as_float(first_present(mapping, WIDTH_KEYS))
    h = as_float(first_present(mapping, HEIGHT_KEYS))
    if x is not None and y is not None and w is not None and h is not None:
        return clamp_bbox(x, y, x + w, y + h, width, height)
    return None


def bbox_from_value(value: Any, width: Optional[int], height: Optional[int]) -> Optional[Dict[str, Any]]:
    if isinstance(value, Mapping):
        return bbox_from_mapping(value, width, height)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) >= 4:
        nums = [as_float(v) for v in list(value)[:4]]
        if all(v is not None for v in nums):
            return clamp_bbox(nums[0], nums[1], nums[2], nums[3], width, height)  # type: ignore[arg-type]
    return None


def merge_context(parent: Mapping[str, Any], obj: Mapping[str, Any]) -> Dict[str, Any]:
    ctx = dict(parent)
    for key in PAGE_ID_KEYS:
        if obj.get(key):
            ctx["page_id"] = obj.get(key)
            break
    for key in TABLE_ID_KEYS:
        if obj.get(key):
            ctx["table_id"] = obj.get(key)
            break
    for key in ROW_ID_KEYS:
        if obj.get(key):
            ctx["row_id"] = obj.get(key)
            break
    for key in CELL_ID_KEYS:
        if obj.get(key):
            ctx["cell_id"] = obj.get(key)
            break
    if obj.get("table_type"):
        ctx["table_type"] = obj.get("table_type")
    return ctx


def extract_bbox_records(
    obj: Any,
    *,
    width: Optional[int] = None,
    height: Optional[int] = None,
    context: Optional[Mapping[str, Any]] = None,
    limit: int = 250_000,
) -> List[Dict[str, Any]]:
    """Recursively extract page/table-scoped bbox records from a JSON object."""
    records: List[Dict[str, Any]] = []
    ctx = dict(context or {})

    def visit(value: Any, current: Mapping[str, Any], depth: int) -> None:
        if len(records) >= limit or depth > 32:
            return
        if isinstance(value, Mapping):
            local = merge_context(current, value)
            for key in BBOX_KEYS:
                if key in value:
                    box = bbox_from_value(value.get(key), width, height)
                    if box:
                        records.append({
                            "bbox": box,
                            "bbox_key": key,
                            "page_id": local.get("page_id"),
                            "table_id": local.get("table_id"),
                            "row_id": local.get("row_id"),
                            "cell_id": local.get("cell_id"),
                            "table_type": local.get("table_type"),
                            "record_kind": infer_record_kind(value, key),
                        })
            box = bbox_from_mapping(value, width, height)
            if box and any(k in value for k in X0_KEYS + X_KEYS):
                records.append({
                    "bbox": box,
                    "bbox_key": "direct_coordinate_fields",
                    "page_id": local.get("page_id"),
                    "table_id": local.get("table_id"),
                    "row_id": local.get("row_id"),
                    "cell_id": local.get("cell_id"),
                    "table_type": local.get("table_type"),
                    "record_kind": infer_record_kind(value, "direct_coordinate_fields"),
                })
            for child in value.values():
                visit(child, local, depth + 1)
        elif isinstance(value, list):
            for child in value:
                visit(child, current, depth + 1)

    visit(obj, ctx, 0)
    return records


def infer_record_kind(value: Mapping[str, Any], bbox_key: str) -> str:
    joined = " ".join(str(value.get(k, "")) for k in ("schema_version", "record_type", "document_type", "type", "table_type"))
    key_text = bbox_key.lower()
    text = f"{joined} {key_text}".lower()
    if "cell" in text or value.get("cell_id") or value.get("normalized_cell_id"):
        return "cell"
    if "row" in text or value.get("row_id") or value.get("normalized_row_id"):
        return "row"
    if "table" in text:
        return "table"
    if "word" in text or "ocr" in text:
        return "ocr_word"
    return "unknown"


def union_bboxes(boxes: Sequence[Mapping[str, Any]], pad_ratio: float = 0.025, width: Optional[int] = None, height: Optional[int] = None) -> Optional[Dict[str, Any]]:
    if not boxes:
        return None
    x0 = min(float(b["x0"]) for b in boxes)
    y0 = min(float(b["y0"]) for b in boxes)
    x1 = max(float(b["x1"]) for b in boxes)
    y1 = max(float(b["y1"]) for b in boxes)
    pad_x = max(2.0, (x1 - x0) * pad_ratio)
    pad_y = max(2.0, (y1 - y0) * pad_ratio)
    return clamp_bbox(x0 - pad_x, y0 - pad_y, x1 + pad_x, y1 + pad_y, width, height)


def page_content_heuristic_bbox(width: Optional[int], height: Optional[int], table_type: Optional[str]) -> Optional[Dict[str, Any]]:
    if not width or not height:
        return None
    t = (table_type or "").lower()
    x0_ratio, x1_ratio = 0.045, 0.955
    y0_ratio, y1_ratio = 0.105, 0.925
    if "parts" in t or "ipl" in t:
        y0_ratio, y1_ratio = 0.095, 0.93
    elif "effective" in t or "index" in t:
        y0_ratio, y1_ratio = 0.11, 0.91
    return clamp_bbox(width * x0_ratio, height * y0_ratio, width * x1_ratio, height * y1_ratio, width, height)


def bbox_area(box: Mapping[str, Any]) -> float:
    return float(box.get("width") or 0) * float(box.get("height") or 0)


def bbox_valid_for_image(box: Mapping[str, Any], width: Optional[int], height: Optional[int]) -> bool:
    if not box:
        return False
    if bbox_area(box) < 16:
        return False
    if width and height:
        page_area = float(width * height)
        if bbox_area(box) > page_area * 0.98:
            return False
    return True


def select_image_path(card: Mapping[str, Any], resolver_card: Optional[Mapping[str, Any]], image_root: Optional[Path]) -> Tuple[Optional[str], Optional[Path], Optional[float]]:
    candidates = []
    if resolver_card:
        candidates.append(resolver_card.get("resolved_image_path"))
        candidates.append(resolver_card.get("image_path"))
    for key in ("resolved_image_path", "image_path", "page_image_path", "source_image_path", "tiff_path"):
        candidates.append(card.get(key))
    for candidate in candidates:
        path = normalize_path(candidate, image_root=image_root)
        if path and path.exists():
            confidence = None
            if resolver_card and candidate == resolver_card.get("resolved_image_path"):
                confidence = as_float(resolver_card.get("image_resolution_confidence"))
            return str(path).replace("\\", "/"), path, confidence
    return None, None, None


def build_resolver_index(image_resolver_payload: Optional[Mapping[str, Any]]) -> Dict[Tuple[Optional[str], Optional[str]], Mapping[str, Any]]:
    index: Dict[Tuple[Optional[str], Optional[str]], Mapping[str, Any]] = {}
    if not image_resolver_payload:
        return index
    cards = image_resolver_payload.get("table_image_resolution_cards") or image_resolver_payload.get("resolver_cards") or []
    for card in cards:
        if not isinstance(card, Mapping):
            continue
        key = (card.get("page_id"), card.get("table_id"))
        index[key] = card
        index[(card.get("page_id"), None)] = card
    return index


def build_ocr_enrichment_index(ocr_enrichment_payload: Optional[Mapping[str, Any]]) -> Dict[Tuple[Optional[str], Optional[str]], Mapping[str, Any]]:
    index: Dict[Tuple[Optional[str], Optional[str]], Mapping[str, Any]] = {}
    if not ocr_enrichment_payload:
        return index
    cards = ocr_enrichment_payload.get("table_ocr_bbox_enrichment_cards") or ocr_enrichment_payload.get("ocr_bbox_enrichment_cards") or []
    for card in cards:
        if not isinstance(card, Mapping):
            continue
        key = (card.get("page_id"), card.get("table_id"))
        index[key] = card
        # Page-scoped fallback is useful when the table_id has shifted between
        # artifacts but the page is the same resolved TIFF page.
        index.setdefault((card.get("page_id"), None), card)
    return index


def ocr_enrichment_bbox_candidate(
    ocr_card: Optional[Mapping[str, Any]],
    *,
    width: Optional[int],
    height: Optional[int],
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Return a gated OCR-enrichment bbox candidate and gate diagnostics.

    OCR enrichment can produce broad boxes because table text often spans most
    of a page. Broad boxes are still useful crop candidates when they are not
    literally full-page crops, but they must remain advisory and review-routed.
    """
    diagnostics: Dict[str, Any] = {
        "ocr_bbox_enrichment_available": bool(ocr_card),
        "ocr_bbox_enrichment_crop_candidate_ready": False,
        "ocr_bbox_enrichment_used": False,
        "ocr_bbox_enrichment_rejected": False,
        "ocr_bbox_enrichment_rejection_reason": None,
        "ocr_bbox_enrichment_bbox_source": None,
        "ocr_bbox_enrichment_bbox_confidence": None,
        "ocr_bbox_enrichment_bbox_coverage_ratio": None,
        "ocr_bbox_enrichment_matched_ocr_bbox_count": 0,
        "ocr_bbox_enrichment_part_number_ocr_match_count": 0,
    }
    if not ocr_card:
        return None, diagnostics

    diagnostics["ocr_bbox_enrichment_crop_candidate_ready"] = bool(ocr_card.get("crop_candidate_ready"))
    diagnostics["ocr_bbox_enrichment_bbox_source"] = ocr_card.get("bbox_source")
    diagnostics["ocr_bbox_enrichment_bbox_confidence"] = as_float(ocr_card.get("bbox_confidence"))
    diagnostics["ocr_bbox_enrichment_bbox_coverage_ratio"] = as_float(ocr_card.get("bbox_coverage_ratio"))
    diagnostics["ocr_bbox_enrichment_matched_ocr_bbox_count"] = int(ocr_card.get("matched_ocr_bbox_count") or 0)
    diagnostics["ocr_bbox_enrichment_part_number_ocr_match_count"] = int(ocr_card.get("part_number_ocr_match_count") or 0)

    if not ocr_card.get("crop_candidate_ready"):
        diagnostics["ocr_bbox_enrichment_rejected"] = True
        diagnostics["ocr_bbox_enrichment_rejection_reason"] = "ocr_enrichment_crop_candidate_not_ready"
        return None, diagnostics

    raw_box = ocr_card.get("inferred_table_region_bbox") or ocr_card.get("table_region_bbox")
    box = bbox_from_value(raw_box, width, height)
    if not box:
        diagnostics["ocr_bbox_enrichment_rejected"] = True
        diagnostics["ocr_bbox_enrichment_rejection_reason"] = "ocr_enrichment_bbox_missing_or_invalid"
        return None, diagnostics

    confidence = as_float(ocr_card.get("bbox_confidence")) or 0.0
    source = str(ocr_card.get("bbox_source") or "")
    matched_count = int(ocr_card.get("matched_ocr_bbox_count") or 0)
    part_match_count = int(ocr_card.get("part_number_ocr_match_count") or 0)
    coverage = as_float(ocr_card.get("bbox_coverage_ratio"))
    if coverage is None and width and height:
        coverage = bbox_area(box) / float(width * height)
        diagnostics["ocr_bbox_enrichment_bbox_coverage_ratio"] = round(coverage, 6)

    # Conservative gates: require real OCR evidence, avoid tiny boxes, and avoid
    # crops that are effectively the whole page. Broad but non-full-page crops
    # are allowed but review-flagged downstream.
    if source not in OCR_ENRICHMENT_BBOX_SOURCES:
        diagnostics["ocr_bbox_enrichment_rejected"] = True
        diagnostics["ocr_bbox_enrichment_rejection_reason"] = "ocr_enrichment_bbox_source_not_supported"
        return None, diagnostics
    if confidence < 0.72:
        diagnostics["ocr_bbox_enrichment_rejected"] = True
        diagnostics["ocr_bbox_enrichment_rejection_reason"] = "ocr_enrichment_confidence_below_gate"
        return None, diagnostics
    if matched_count < 3 and part_match_count < 1:
        diagnostics["ocr_bbox_enrichment_rejected"] = True
        diagnostics["ocr_bbox_enrichment_rejection_reason"] = "ocr_enrichment_insufficient_matching_boxes"
        return None, diagnostics
    if float(box.get("width") or 0) < 32 or float(box.get("height") or 0) < 32:
        diagnostics["ocr_bbox_enrichment_rejected"] = True
        diagnostics["ocr_bbox_enrichment_rejection_reason"] = "ocr_enrichment_bbox_below_minimum_dimensions"
        return None, diagnostics
    if coverage is not None and coverage >= 0.96:
        diagnostics["ocr_bbox_enrichment_rejected"] = True
        diagnostics["ocr_bbox_enrichment_rejection_reason"] = "ocr_enrichment_bbox_too_close_to_full_page"
        return None, diagnostics

    diagnostics["ocr_bbox_enrichment_used"] = True
    return box, diagnostics


def filter_records_for_card(records: Sequence[Mapping[str, Any]], page_id: Any, table_id: Any) -> List[Mapping[str, Any]]:
    result = []
    for rec in records:
        rec_page = rec.get("page_id")
        rec_table = rec.get("table_id")
        page_match = not page_id or not rec_page or rec_page == page_id
        table_match = not table_id or not rec_table or rec_table == table_id
        if page_match and table_match:
            result.append(rec)
    return result


def build_bbox_card(
    card: Mapping[str, Any],
    *,
    bbox_records: Sequence[Mapping[str, Any]],
    resolver_card: Optional[Mapping[str, Any]],
    ocr_enrichment_card: Optional[Mapping[str, Any]],
    image_root: Optional[Path],
) -> Dict[str, Any]:
    page_id = card.get("page_id")
    table_id = card.get("table_id")
    table_type = card.get("table_type")
    image_path_str, image_path, image_conf = select_image_path(card, resolver_card, image_root)
    width, height = image_dimensions(image_path)
    if not width and resolver_card:
        width = int(resolver_card.get("image_width") or 0) or None
    if not height and resolver_card:
        height = int(resolver_card.get("image_height") or 0) or None

    scoped_records = filter_records_for_card(bbox_records, page_id, table_id)
    direct_table_boxes = [r["bbox"] for r in scoped_records if r.get("record_kind") == "table" and r.get("bbox")]
    cell_boxes = [r["bbox"] for r in scoped_records if r.get("record_kind") == "cell" and r.get("bbox")]
    row_boxes = [r["bbox"] for r in scoped_records if r.get("record_kind") == "row" and r.get("bbox")]
    ocr_boxes = [r["bbox"] for r in scoped_records if r.get("record_kind") == "ocr_word" and r.get("bbox")]
    any_boxes = [r["bbox"] for r in scoped_records if r.get("bbox")]
    ocr_enrichment_box, ocr_enrichment_diag = ocr_enrichment_bbox_candidate(ocr_enrichment_card, width=width, height=height)

    bbox_source = "unresolved"
    bbox = None
    confidence = 0.0
    if direct_table_boxes:
        bbox = union_bboxes(direct_table_boxes, pad_ratio=0.01, width=width, height=height)
        bbox_source = "explicit_table_bbox"
        confidence = 0.95
    elif cell_boxes:
        bbox = union_bboxes(cell_boxes, pad_ratio=0.035, width=width, height=height)
        bbox_source = "aggregated_cell_bboxes"
        confidence = 0.88 if len(cell_boxes) >= 10 else 0.78
    elif row_boxes:
        bbox = union_bboxes(row_boxes, pad_ratio=0.03, width=width, height=height)
        bbox_source = "aggregated_row_bboxes"
        confidence = 0.82 if len(row_boxes) >= 5 else 0.72
    elif ocr_enrichment_box:
        bbox = ocr_enrichment_box
        bbox_source = str(ocr_enrichment_diag.get("ocr_bbox_enrichment_bbox_source") or "ocr_bbox_enrichment")
        confidence = as_float(ocr_enrichment_diag.get("ocr_bbox_enrichment_bbox_confidence")) or 0.8
    elif ocr_boxes:
        bbox = union_bboxes(ocr_boxes, pad_ratio=0.05, width=width, height=height)
        bbox_source = "aggregated_ocr_bboxes"
        confidence = 0.68
    elif any_boxes:
        bbox = union_bboxes(any_boxes, pad_ratio=0.04, width=width, height=height)
        bbox_source = "aggregated_unknown_bboxes"
        confidence = 0.62
    else:
        bbox = page_content_heuristic_bbox(width, height, table_type)
        bbox_source = "page_content_heuristic_bbox"
        confidence = 0.55 if bbox else 0.0

    if bbox and not bbox_valid_for_image(bbox, width, height):
        bbox = None
        bbox_source = "invalid_bbox_rejected"
        confidence = 0.0

    crop_ready = bool(bbox and image_path_str)
    review_flags: List[str] = []
    recommended_actions: List[str] = []
    if not crop_ready:
        review_flags.append("table_region_bbox_unresolved")
        recommended_actions.append("resolve_table_region_bbox_from_ocr_or_layout_artifacts")
    elif bbox_source == "page_content_heuristic_bbox":
        review_flags.append("table_region_bbox_is_heuristic")
        recommended_actions.append("replace_heuristic_bbox_with_ocr_or_layout_bbox_when_available")
    elif bbox_source in OCR_ENRICHMENT_BBOX_SOURCES:
        coverage_hint = as_float(ocr_enrichment_diag.get("ocr_bbox_enrichment_bbox_coverage_ratio"))
        if coverage_hint is not None and coverage_hint > 0.75:
            review_flags.append("ocr_enrichment_bbox_broad_crop_candidate")
            recommended_actions.append("confirm_ocr_enrichment_bbox_against_source_page")
        if ocr_enrichment_card and ocr_enrichment_card.get("review_required"):
            review_flags.append("ocr_enrichment_source_review_required")
            recommended_actions.append("confirm_ocr_enrichment_bbox_against_source_page")
    elif bbox_source.startswith("aggregated_unknown") or bbox_source == "aggregated_ocr_bboxes":
        review_flags.append("table_region_bbox_low_specificity")
        recommended_actions.append("confirm_table_region_bbox_against_source_page")
    elif confidence < 0.8:
        review_flags.append("table_region_bbox_low_confidence")
        recommended_actions.append("confirm_table_region_bbox_against_source_page")

    if ocr_enrichment_diag.get("ocr_bbox_enrichment_rejected"):
        review_flags.append("ocr_enrichment_bbox_candidate_rejected")
        recommended_actions.append("inspect_ocr_bbox_enrichment_crop_candidate")

    if width and height and bbox:
        page_area = width * height
        coverage = round(bbox_area(bbox) / page_area, 6) if page_area else None
    else:
        coverage = None

    return {
        "bbox_card_id": stable_id("table_bbox", page_id, table_id, bbox_source, image_path_str),
        "schema_version": SCHEMA_VERSION,
        "page_id": page_id,
        "table_id": table_id,
        "table_type": table_type,
        "source_geometry_card_id": card.get("geometry_card_id"),
        "source_table_line_geometry_quality_status": card.get("quality_status"),
        "resolved_image_path": image_path_str,
        "image_width": width,
        "image_height": height,
        "image_resolution_confidence": image_conf,
        "table_region_bbox": bbox,
        "bbox_resolution_status": "RESOLVED" if crop_ready else "UNRESOLVED",
        "bbox_source": bbox_source,
        "bbox_confidence": round(confidence, 4),
        "bbox_coverage_ratio": coverage,
        "ocr_bbox_enrichment_available": ocr_enrichment_diag.get("ocr_bbox_enrichment_available"),
        "ocr_bbox_enrichment_crop_candidate_ready": ocr_enrichment_diag.get("ocr_bbox_enrichment_crop_candidate_ready"),
        "ocr_bbox_enrichment_used": ocr_enrichment_diag.get("ocr_bbox_enrichment_used"),
        "ocr_bbox_enrichment_rejected": ocr_enrichment_diag.get("ocr_bbox_enrichment_rejected"),
        "ocr_bbox_enrichment_rejection_reason": ocr_enrichment_diag.get("ocr_bbox_enrichment_rejection_reason"),
        "ocr_bbox_enrichment_bbox_source": ocr_enrichment_diag.get("ocr_bbox_enrichment_bbox_source"),
        "ocr_bbox_enrichment_bbox_confidence": ocr_enrichment_diag.get("ocr_bbox_enrichment_bbox_confidence"),
        "ocr_bbox_enrichment_bbox_coverage_ratio": ocr_enrichment_diag.get("ocr_bbox_enrichment_bbox_coverage_ratio"),
        "ocr_bbox_enrichment_matched_ocr_bbox_count": ocr_enrichment_diag.get("ocr_bbox_enrichment_matched_ocr_bbox_count"),
        "ocr_bbox_enrichment_part_number_ocr_match_count": ocr_enrichment_diag.get("ocr_bbox_enrichment_part_number_ocr_match_count"),
        "record_bbox_count": len(scoped_records),
        "table_bbox_count": len(direct_table_boxes),
        "cell_bbox_count": len(cell_boxes),
        "row_bbox_count": len(row_boxes),
        "ocr_bbox_count": len(ocr_boxes),
        "unknown_bbox_count": len(any_boxes) - len(direct_table_boxes) - len(cell_boxes) - len(row_boxes) - len(ocr_boxes),
        "crop_ready": crop_ready,
        "review_required": bool(review_flags),
        "review_flags": sorted(set(review_flags)),
        "recommended_actions": sorted(set(recommended_actions)),
        "retrieval_only": True,
        "routing_only": True,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "retrieval_only_answer_allowed": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
        "can_mutate_source_truth": False,
        "unsafe_bbox_card": False,
    }


def summarize(cards: Sequence[Mapping[str, Any]], source_cards: Sequence[Mapping[str, Any]], inputs: Mapping[str, Any]) -> Dict[str, Any]:
    def count(pred) -> int:
        return sum(1 for card in cards if pred(card))
    answer_permission_count = sum(1 for c in cards if c.get("answer_permission") or c.get("can_answer_directly") or c.get("can_prove_claims"))
    source_truth_mutation_allowed_count = sum(1 for c in cards if c.get("source_truth_mutation_allowed") or c.get("can_mutate_source_truth"))
    unsafe_count = sum(1 for c in cards if c.get("unsafe_bbox_card"))
    return {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "source_table_geometry_card_count": len(source_cards),
        "bbox_card_count": len(cards),
        "resolved_bbox_card_count": count(lambda c: c.get("bbox_resolution_status") == "RESOLVED"),
        "unresolved_bbox_card_count": count(lambda c: c.get("bbox_resolution_status") != "RESOLVED"),
        "crop_ready_card_count": count(lambda c: c.get("crop_ready")),
        "heuristic_bbox_card_count": count(lambda c: c.get("bbox_source") == "page_content_heuristic_bbox"),
        "explicit_table_bbox_card_count": count(lambda c: c.get("bbox_source") == "explicit_table_bbox"),
        "aggregated_cell_bbox_card_count": count(lambda c: c.get("bbox_source") == "aggregated_cell_bboxes"),
        "aggregated_row_bbox_card_count": count(lambda c: c.get("bbox_source") == "aggregated_row_bboxes"),
        "ocr_bbox_enrichment_available_card_count": count(lambda c: c.get("ocr_bbox_enrichment_available")),
        "ocr_bbox_enrichment_crop_candidate_ready_card_count": count(lambda c: c.get("ocr_bbox_enrichment_crop_candidate_ready")),
        "ocr_bbox_enrichment_used_card_count": count(lambda c: c.get("ocr_bbox_enrichment_used")),
        "ocr_bbox_enrichment_rejected_card_count": count(lambda c: c.get("ocr_bbox_enrichment_rejected")),
        "ocr_bbox_enrichment_broad_crop_candidate_card_count": count(lambda c: "ocr_enrichment_bbox_broad_crop_candidate" in (c.get("review_flags") or [])),
        "review_required_card_count": count(lambda c: c.get("review_required")),
        "unsafe_bbox_card_count": unsafe_count,
        "answer_permission_count": answer_permission_count,
        "can_answer_directly_count": sum(1 for c in cards if c.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for c in cards if c.get("can_prove_claims")),
        "retrieval_only_answer_allowed_count": sum(1 for c in cards if c.get("retrieval_only_answer_allowed")),
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "source_truth_mutations_performed": sum(int(c.get("source_truth_mutations_performed") or 0) for c in cards),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "source_quality_statuses": dict(inputs.get("source_quality_statuses") or {}),
    }


def evaluate_quality(summary: Mapping[str, Any], thresholds: Mapping[str, Any]) -> Tuple[str, List[str], Dict[str, bool]]:
    reasons: List[str] = []
    checks: Dict[str, bool] = {}

    def check(name: str, ok: bool, reason: str) -> None:
        checks[name] = bool(ok)
        if not ok:
            reasons.append(reason)

    check("min_source_cards_met", int(summary.get("source_table_geometry_card_count") or 0) >= int(thresholds.get("min_source_cards") or 0), "source_table_geometry_card_count below minimum")
    check("min_bbox_cards_met", int(summary.get("bbox_card_count") or 0) >= int(thresholds.get("min_bbox_cards") or 0), "bbox_card_count below minimum")
    check("min_crop_ready_cards_met", int(summary.get("crop_ready_card_count") or 0) >= int(thresholds.get("min_crop_ready_cards") or 0), "crop_ready_card_count below minimum")
    check("unsafe_bbox_cards_within_limit", int(summary.get("unsafe_bbox_card_count") or 0) <= int(thresholds.get("max_unsafe_bbox_cards") or 0), "unsafe_bbox_card_count above limit")
    check("answer_permission_within_limit", int(summary.get("answer_permission_count") or 0) <= int(thresholds.get("max_answer_permission_count") or 0), "answer_permission_count above limit")
    check("source_truth_mutation_allowed_within_limit", int(summary.get("source_truth_mutation_allowed_count") or 0) <= int(thresholds.get("max_source_truth_mutation_allowed") or 0), "source_truth_mutation_allowed_count above limit")
    check("write_attempts_zero", int(summary.get("postgres_write_attempt_count") or 0) == 0 and int(summary.get("qdrant_write_attempt_count") or 0) == 0 and int(summary.get("opensearch_write_attempt_count") or 0) == 0, "write attempt count is nonzero")
    if thresholds.get("require_table_line_geometry_quality_pass"):
        check("table_line_geometry_quality_pass", (summary.get("source_quality_statuses") or {}).get("table_line_geometry") == "PASS", "table_line_geometry quality is not PASS")
    check("min_ocr_bbox_enrichment_used_cards_met", int(summary.get("ocr_bbox_enrichment_used_card_count") or 0) >= int(thresholds.get("min_ocr_bbox_enrichment_used_cards") or 0), "ocr_bbox_enrichment_used_card_count below minimum")
    if thresholds.get("require_table_image_resolver_quality_pass"):
        check("table_image_resolver_quality_pass", (summary.get("source_quality_statuses") or {}).get("table_image_resolver") == "PASS", "table_image_resolver quality is not PASS")
    if thresholds.get("require_table_ocr_bbox_enrichment_quality_pass"):
        check("table_ocr_bbox_enrichment_quality_pass", (summary.get("source_quality_statuses") or {}).get("table_ocr_bbox_enrichment") == "PASS", "table_ocr_bbox_enrichment quality is not PASS")
    if thresholds.get("require_no_answer_permission"):
        check("answer_permission_zero", int(summary.get("answer_permission_count") or 0) == 0 and int(summary.get("can_answer_directly_count") or 0) == 0 and int(summary.get("can_prove_claims_count") or 0) == 0, "answer permission/proof count is nonzero")
    return ("PASS" if not reasons else "FAIL"), reasons, checks


def build_report(
    *,
    table_line_geometry_path: Path,
    table_cell_normalizer_path: Optional[Path],
    table_image_resolver_path: Optional[Path],
    table_ocr_bbox_enrichment_path: Optional[Path],
    image_root: Optional[Path],
    output_dir: Path,
    thresholds: Mapping[str, Any],
) -> Dict[str, Any]:
    tlg = load_json(table_line_geometry_path)
    tcn = load_json(table_cell_normalizer_path) if table_cell_normalizer_path and table_cell_normalizer_path.exists() else {}
    tir = load_json(table_image_resolver_path) if table_image_resolver_path and table_image_resolver_path.exists() else {}
    ocr_enrich = load_json(table_ocr_bbox_enrichment_path) if table_ocr_bbox_enrichment_path and table_ocr_bbox_enrichment_path.exists() else {}

    source_cards = tlg.get("table_geometry_cards") or []
    source_quality_statuses = {
        "table_line_geometry": tlg.get("quality_status"),
        "table_cell_normalizer": tcn.get("quality_status") if tcn else None,
        "table_image_resolver": tir.get("quality_status") if tir else None,
        "table_ocr_bbox_enrichment": ocr_enrich.get("quality_status") if ocr_enrich else None,
    }
    resolver_index = build_resolver_index(tir)
    ocr_enrichment_index = build_ocr_enrichment_index(ocr_enrich)

    # Extract all available bboxes from the normalizer and table geometry. Image
    # dimensions differ by page, so boxes will be clamped/scaled later by the
    # selected page image where possible. Use source units for the global pass.
    bbox_records = []
    bbox_records.extend(extract_bbox_records(tcn))
    bbox_records.extend(extract_bbox_records(tlg))

    cards = []
    for source_card in source_cards:
        if not isinstance(source_card, Mapping):
            continue
        resolver_card = resolver_index.get((source_card.get("page_id"), source_card.get("table_id"))) or resolver_index.get((source_card.get("page_id"), None))
        ocr_enrichment_card = ocr_enrichment_index.get((source_card.get("page_id"), source_card.get("table_id"))) or ocr_enrichment_index.get((source_card.get("page_id"), None))
        cards.append(build_bbox_card(source_card, bbox_records=bbox_records, resolver_card=resolver_card, ocr_enrichment_card=ocr_enrichment_card, image_root=image_root))

    inputs = {"source_quality_statuses": source_quality_statuses}
    summary = summarize(cards, source_cards, inputs)
    quality_status, quality_fail_reasons, checks = evaluate_quality(summary, thresholds)
    summary["quality_status"] = quality_status
    summary["quality_fail_reasons"] = quality_fail_reasons
    status = STATUS_BUILT if quality_status == "PASS" else STATUS_NOT_READY
    summary["status"] = status

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "status": status,
        "quality_status": quality_status,
        "quality_fail_reasons": quality_fail_reasons,
        "checks": checks,
        "summary": summary,
        "input_paths": {
            "table_line_geometry": str(table_line_geometry_path),
            "table_cell_normalizer": str(table_cell_normalizer_path) if table_cell_normalizer_path else None,
            "table_image_resolver": str(table_image_resolver_path) if table_image_resolver_path else None,
            "table_ocr_bbox_enrichment": str(table_ocr_bbox_enrichment_path) if table_ocr_bbox_enrichment_path else None,
            "image_root": str(image_root) if image_root else None,
        },
        "safety_contract": {
            "read_only_bbox_resolver": True,
            "no_postgres_writes": True,
            "no_qdrant_writes": True,
            "no_opensearch_writes": True,
            "no_source_truth_mutation": True,
            "no_answer_permission": True,
            "bbox_metadata_is_advisory_only": True,
        },
        "table_bbox_cards": cards,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_table_bbox_resolver_v1.json"
    quality_path = output_dir / "trace_net_table_bbox_resolver_v1_quality.json"
    summary_path = output_dir / "trace_net_table_bbox_resolver_v1_summary.json"
    manifest_path = output_dir / "trace_net_table_bbox_resolver_v1_manifest.json"
    cards_path = output_dir / "trace_net_table_bbox_resolver_v1_cards.jsonl"

    write_json(report_path, report)
    write_json(summary_path, summary)
    write_jsonl(cards_path, cards)
    quality_payload = build_quality_payload(report)
    write_json(quality_path, quality_payload)
    write_json(manifest_path, {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": report["generated_at"],
        "files": {
            "report": str(report_path),
            "quality": str(quality_path),
            "summary": str(summary_path),
            "cards_jsonl": str(cards_path),
        },
        "quality_status": quality_status,
    })
    return report


def build_quality_payload(report: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "generated_at": utc_now(),
        "status": report.get("quality_status"),
        "quality_status": report.get("quality_status"),
        "summary": report.get("summary") or {},
        "quality_errors": report.get("quality_fail_reasons") or [],
        "checks": report.get("checks") or {},
    }


def thresholds_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "min_source_cards": args.min_source_cards,
        "min_bbox_cards": args.min_bbox_cards,
        "min_crop_ready_cards": args.min_crop_ready_cards,
        "min_ocr_bbox_enrichment_used_cards": args.min_ocr_bbox_enrichment_used_cards,
        "max_unsafe_bbox_cards": args.max_unsafe_bbox_cards,
        "max_answer_permission_count": args.max_answer_permission_count,
        "max_source_truth_mutation_allowed": args.max_source_truth_mutation_allowed,
        "require_table_line_geometry_quality_pass": args.require_table_line_geometry_quality_pass,
        "require_table_image_resolver_quality_pass": args.require_table_image_resolver_quality_pass,
        "require_table_ocr_bbox_enrichment_quality_pass": args.require_table_ocr_bbox_enrichment_quality_pass,
        "require_no_answer_permission": args.require_no_answer_permission,
    }


def add_common_threshold_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-source-cards", type=int, default=1)
    parser.add_argument("--min-bbox-cards", type=int, default=1)
    parser.add_argument("--min-crop-ready-cards", type=int, default=1)
    parser.add_argument("--min-ocr-bbox-enrichment-used-cards", type=int, default=0)
    parser.add_argument("--max-unsafe-bbox-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-line-geometry-quality-pass", action="store_true")
    parser.add_argument("--require-table-image-resolver-quality-pass", action="store_true")
    parser.add_argument("--require-table-ocr-bbox-enrichment-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Table BBox Resolver v1")
    parser.add_argument("--table-line-geometry", required=True, type=Path)
    parser.add_argument("--table-cell-normalizer", type=Path)
    parser.add_argument("--table-image-resolver", type=Path)
    parser.add_argument("--table-ocr-bbox-enrichment", type=Path)
    parser.add_argument("--image-root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--quality", action="store_true")
    add_common_threshold_args(parser)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = build_report(
        table_line_geometry_path=args.table_line_geometry,
        table_cell_normalizer_path=args.table_cell_normalizer,
        table_image_resolver_path=args.table_image_resolver,
        table_ocr_bbox_enrichment_path=args.table_ocr_bbox_enrichment,
        image_root=args.image_root,
        output_dir=args.output_dir,
        thresholds=thresholds_from_args(args),
    )
    summary = report.get("summary") or {}
    print("TRACE-Net Table BBox Resolver v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in (
        "source_table_geometry_card_count",
        "bbox_card_count",
        "resolved_bbox_card_count",
        "unresolved_bbox_card_count",
        "crop_ready_card_count",
        "heuristic_bbox_card_count",
        "aggregated_cell_bbox_card_count",
        "ocr_bbox_enrichment_available_card_count",
        "ocr_bbox_enrichment_crop_candidate_ready_card_count",
        "ocr_bbox_enrichment_used_card_count",
        "ocr_bbox_enrichment_rejected_card_count",
        "ocr_bbox_enrichment_broad_crop_candidate_card_count",
        "review_required_card_count",
        "unsafe_bbox_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {args.output_dir / 'trace_net_table_bbox_resolver_v1.json'}")
    print(f" quality_path: {args.output_dir / 'trace_net_table_bbox_resolver_v1_quality.json'}")
    return 0 if report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
