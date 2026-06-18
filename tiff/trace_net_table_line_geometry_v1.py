"""TRACE-Net Table Line Geometry v1.

Read-only table geometry reconstruction for OCR/table-normalizer artifacts.

This module is intentionally below the answer-authority line. It can detect
candidate table ruling lines, cluster OCR/table cells into rows and columns,
flag likely merged cells, and emit review recommendations. It cannot answer
questions, prove claims, mutate source truth, or write to Postgres/Qdrant/
OpenSearch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from tiff.trace_net_route_dispatch_contract_loader_v1 import load_route_dispatch_processor_contract
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "trace_net_table_line_geometry_v1"
QUALITY_SCHEMA_VERSION = "trace_net_table_line_geometry_v1_quality"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/table_line_geometry")

PART_NUMBER_RE = re.compile(r"\b\d{2,3}-\d{5}-\d{3}\b")
ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
REVISION_RE = re.compile(r"\b(?:REV(?:ISION)?\.?\s*\d+|REV\.\s*\d+)\b", re.IGNORECASE)
QUANTITY_RE = re.compile(r"^(?:\d+|AR|A/R|REF|NHA|ALT|OPT)$", re.IGNORECASE)

TEXT_KEYS = (
    "text",
    "cell_text",
    "row_text",
    "value",
    "normalized_text",
    "normalized_value",
    "display_text",
    "raw_text",
    "ocr_text",
    "search_text",
    "title",
)
ID_KEYS = ("cell_id", "row_id", "table_id", "page_id", "source_page_ids")
IMAGE_PATH_KEYS = (
    "image_path",
    "tiff_path",
    "source_tiff_path",
    "source_path",
    "page_image_path",
    "local_tiff_path",
)

TABLE_ID_KEYS = ("table_id", "tableId", "normalized_table_id", "normalizedTableId", "table_uid")
ROW_ID_KEYS = ("row_id", "rowId", "normalized_row_id", "normalizedRowId", "row_uid")
CELL_ID_KEYS = ("cell_id", "cellId", "normalized_cell_id", "normalizedCellId", "cell_uid")

SAFETY_CONTRACT = {
    "read_only_module": True,
    "no_postgres_writes": True,
    "no_qdrant_writes": True,
    "no_opensearch_writes": True,
    "no_source_truth_mutation": True,
    "no_answer_permission": True,
    "no_claim_proof_authority": True,
    "geometry_is_advisory": True,
    "requires_downstream_source_resolution": True,
    "requires_human_review_for_low_confidence_geometry": True,
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(p) for p in parts if p is not None)
    digest = hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:14]
    return f"{prefix}_{digest}"


def compact_text(value: Any, limit: int = 300) -> str:
    if value is None:
        return ""
    text = " ".join(str(value).replace("\n", " ").split())
    return text[:limit]


def get_text(record: Mapping[str, Any]) -> str:
    values: List[str] = []
    for key in TEXT_KEYS:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value)
    return compact_text(" ".join(values), 500)


def first_present(record: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def first_present_from_context(record: Mapping[str, Any], keys: Sequence[str], context: Optional[Mapping[str, Any]] = None) -> Any:
    value = first_present(record, keys)
    if value not in (None, "", [], {}):
        return value
    if context:
        return first_present(context, keys)
    return None


def merge_unique_strings(*values: Any) -> List[str]:
    merged: List[str] = []
    for value in values:
        for item in as_list(value):
            if isinstance(item, str) and item.strip() and item.strip() not in merged:
                merged.append(item.strip())
    return merged


def as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def normalize_page_id(record: Mapping[str, Any]) -> Optional[str]:
    page_id = record.get("page_id") or record.get("pageId") or record.get("source_page_id") or record.get("sourcePageId")
    if isinstance(page_id, str) and page_id.strip():
        return page_id.strip()
    source_pages = as_list(record.get("source_page_ids"))
    for page in source_pages:
        if isinstance(page, str) and page.strip():
            return page.strip()
    citation_ids = as_list(record.get("citation_ids"))
    for citation in citation_ids:
        if not isinstance(citation, str):
            continue
        match = re.search(r"t_p_[A-Za-z0-9_]+_p\d{6}", citation)
        if match:
            return match.group(0)
    return None


def normalize_source_page_ids(record: Mapping[str, Any], page_id: Optional[str]) -> List[str]:
    source_pages: List[str] = []
    for page in as_list(record.get("source_page_ids")):
        if isinstance(page, str) and page.strip() and page.strip() not in source_pages:
            source_pages.append(page.strip())
    if page_id and page_id not in source_pages:
        source_pages.append(page_id)
    return source_pages


def extract_bbox(record: Mapping[str, Any]) -> Optional[Dict[str, float]]:
    candidates = [
        record.get("bbox"),
        record.get("bounding_box"),
        record.get("box"),
        record.get("ocr_bbox"),
        record.get("cell_bbox"),
    ]
    for candidate in candidates:
        parsed = parse_bbox(candidate)
        if parsed:
            return parsed
    scalar_keys = ("x0", "y0", "x1", "y1")
    if all(k in record for k in scalar_keys):
        return parse_bbox({k: record.get(k) for k in scalar_keys})
    alt_scalar_keys = ("left", "top", "right", "bottom")
    if all(k in record for k in alt_scalar_keys):
        return parse_bbox({
            "x0": record.get("left"),
            "y0": record.get("top"),
            "x1": record.get("right"),
            "y1": record.get("bottom"),
        })
    wh_keys = ("x", "y", "width", "height")
    if all(k in record for k in wh_keys):
        try:
            x = float(record.get("x"))
            y = float(record.get("y"))
            w = float(record.get("width"))
            h = float(record.get("height"))
            return {"x0": x, "y0": y, "x1": x + w, "y1": y + h}
        except (TypeError, ValueError):
            return None
    return None


def parse_bbox(value: Any) -> Optional[Dict[str, float]]:
    try:
        if isinstance(value, Mapping):
            if all(k in value for k in ("x0", "y0", "x1", "y1")):
                x0, y0, x1, y1 = (float(value[k]) for k in ("x0", "y0", "x1", "y1"))
            elif all(k in value for k in ("left", "top", "right", "bottom")):
                x0, y0, x1, y1 = (float(value[k]) for k in ("left", "top", "right", "bottom"))
            elif all(k in value for k in ("x", "y", "w", "h")):
                x0 = float(value["x"]); y0 = float(value["y"])
                x1 = x0 + float(value["w"]); y1 = y0 + float(value["h"])
            elif all(k in value for k in ("x", "y", "width", "height")):
                x0 = float(value["x"]); y0 = float(value["y"])
                x1 = x0 + float(value["width"]); y1 = y0 + float(value["height"])
            else:
                return None
        elif isinstance(value, (list, tuple)) and len(value) >= 4:
            x0, y0, x1, y1 = (float(value[i]) for i in range(4))
        else:
            return None
    except (TypeError, ValueError):
        return None
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    if math.isclose(x0, x1) or math.isclose(y0, y1):
        return None
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}


def walk_dicts(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def looks_like_table_record(record: Mapping[str, Any], context: Optional[Mapping[str, Any]] = None) -> bool:
    document_type = str(record.get("document_type") or record.get("record_type") or "").lower()
    bucket = str(record.get("rag_bucket") or record.get("bucket") or "").lower()
    if document_type in {"table_cell_normalized", "table_row_normalized"}:
        return True
    if bucket in {"table_cell_normalized", "table_row_normalized"}:
        return True
    if first_present_from_context(record, CELL_ID_KEYS, context):
        return True
    if first_present_from_context(record, ROW_ID_KEYS, context) and get_text(record):
        return True
    if first_present_from_context(record, TABLE_ID_KEYS, context) and get_text(record):
        return True
    if record.get("table_type") and (record.get("page_id") or record.get("source_page_ids") or (context or {}).get("page_id")) and get_text(record):
        return True
    return False


def classify_table_record(record: Mapping[str, Any], context: Optional[Mapping[str, Any]] = None) -> str:
    document_type = str(record.get("document_type") or record.get("record_type") or "").lower()
    bucket = str(record.get("rag_bucket") or record.get("bucket") or "").lower()
    if "cell" in document_type or "cell" in bucket or first_present_from_context(record, CELL_ID_KEYS, context):
        return "cell"
    if "row" in document_type or "row" in bucket or first_present_from_context(record, ROW_ID_KEYS, context):
        return "row"
    return "table_record"


def is_table_container_key(key: str) -> bool:
    key_l = key.lower()
    return key_l in {
        "normalized_cells",
        "cells",
        "cell_records",
        "table_cells",
        "row_cells",
        "normalized_rows",
        "rows",
        "row_records",
        "table_rows",
        "tables",
        "normalized_tables",
    }


def context_from_record(record: Mapping[str, Any], parent: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    parent = parent or {}
    page_id = normalize_page_id(record) or parent.get("page_id")
    source_page_ids = merge_unique_strings(record.get("source_page_ids"), parent.get("source_page_ids"), [page_id] if page_id else [])
    table_id = first_present(record, TABLE_ID_KEYS) or parent.get("table_id")
    table_type = record.get("table_type") or record.get("table_kind") or parent.get("table_type")
    row_id = first_present(record, ROW_ID_KEYS) or parent.get("row_id")
    image_path = first_present(record, IMAGE_PATH_KEYS) or parent.get("image_path")
    citation_ids = merge_unique_strings(record.get("citation_ids"), parent.get("citation_ids"))
    return {
        "page_id": page_id,
        "source_page_ids": source_page_ids,
        "table_id": table_id,
        "table_type": table_type,
        "row_id": row_id,
        "image_path": image_path,
        "citation_ids": citation_ids,
    }


def normalize_table_record(
    item: Mapping[str, Any],
    context: Optional[Mapping[str, Any]],
    fallback_id: str,
) -> Optional[Dict[str, Any]]:
    context = context_from_record(item, context)
    page_id = context.get("page_id")
    source_page_ids = normalize_source_page_ids({"source_page_ids": context.get("source_page_ids")}, page_id)
    if not page_id and not source_page_ids:
        return None
    rec_type = classify_table_record(item, context)
    text = get_text(item)
    if not text and rec_type != "table_record":
        return None
    table_id = str(first_present(item, TABLE_ID_KEYS) or context.get("table_id") or stable_id("table", page_id or "unknown", context.get("table_type") or "unknown"))
    row_id_value = first_present(item, ROW_ID_KEYS) or context.get("row_id")
    row_id = str(row_id_value) if row_id_value not in (None, "", [], {}) else None
    cell_id_value = first_present(item, CELL_ID_KEYS)
    cell_id = str(cell_id_value) if cell_id_value not in (None, "", [], {}) else None
    record_id = str(
        item.get("record_id")
        or item.get("opensearch_document_id")
        or cell_id
        or row_id
        or stable_id("tabrec", table_id, page_id, fallback_id, text)
    )
    return {
        "record_id": record_id,
        "record_type": rec_type,
        "page_id": page_id,
        "source_page_ids": source_page_ids,
        "table_id": table_id,
        "table_type": item.get("table_type") or item.get("table_kind") or context.get("table_type") or "unknown_table",
        "row_id": row_id,
        "cell_id": cell_id,
        "row_index": item.get("row_index") if item.get("row_index") is not None else item.get("rowIndex"),
        "column_index": item.get("column_index") if item.get("column_index") is not None else item.get("columnIndex") or item.get("col_index") or item.get("colIndex"),
        "text": text,
        "bbox": extract_bbox(item),
        "citation_ids": merge_unique_strings(item.get("citation_ids"), context.get("citation_ids")),
        "source_trace_present": bool(item.get("source_trace_present") or source_page_ids),
        "image_path": first_present(item, IMAGE_PATH_KEYS) or context.get("image_path"),
        "retrieval_only": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "raw_record_keys": sorted(str(k) for k in item.keys())[:30],
    }


def scalar_cell_record(value: Any, context: Mapping[str, Any], fallback_id: str) -> Optional[Dict[str, Any]]:
    text = compact_text(value, 500)
    if not text:
        return None
    item = {
        "cell_id": stable_id("cell", context.get("table_id"), context.get("row_id"), fallback_id, text),
        "text": text,
        "document_type": "table_cell_normalized",
    }
    return normalize_table_record(item, context, fallback_id)


def extract_table_records(payload: Any) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def add(record: Optional[Dict[str, Any]]) -> None:
        if not record:
            return
        record_id = record.get("record_id")
        if not isinstance(record_id, str) or record_id in seen:
            return
        seen.add(record_id)
        records.append(record)

    def visit(value: Any, context: Optional[Mapping[str, Any]], path: str, container_hint: Optional[str] = None) -> None:
        if isinstance(value, Mapping):
            next_context = context_from_record(value, context)
            if looks_like_table_record(value, context):
                add(normalize_table_record(value, context, path))
            for key, child in value.items():
                child_hint = key if is_table_container_key(str(key)) else None
                if child_hint:
                    visit(child, next_context, f"{path}.{key}", child_hint)
                elif isinstance(child, (Mapping, list)):
                    visit(child, next_context, f"{path}.{key}", container_hint)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                child_path = f"{path}[{index}]"
                if isinstance(child, Mapping):
                    visit(child, context, child_path, container_hint)
                elif container_hint and "cell" in container_hint.lower():
                    add(scalar_cell_record(child, context or {}, child_path))
                elif container_hint and "row" in container_hint.lower():
                    add(scalar_cell_record(child, context or {}, child_path))

    visit(payload, {}, "root")
    return records


@dataclass(frozen=True)
class LineDetectionConfig:
    dark_threshold: int = 185
    # Calibration tries several thresholds because the TIFF corpus mixes dark
    # raster rules, gray anti-aliased rules, and text-heavy pages. The detector
    # keeps the threshold that gives the strongest grid-like signal.
    dark_threshold_candidates: Tuple[int, ...] = (145, 165, 185, 205, 225)
    # Fractional full-page black-pixel thresholds are intentionally low because
    # table rules in maintenance manuals often span only a table region, not the
    # full scanned page width/height. Long-run checks below are the primary
    # morphology signal; this ratio remains as a secondary guard.
    min_black_ratio: float = 0.08
    min_line_length: int = 40
    max_gap_pixels: int = 5
    max_image_width: int = 3000
    max_image_height: int = 3000
    crop_padding_pixels: int = 20
    min_crop_width: int = 80
    min_crop_height: int = 40
    # Margin-aware crop selection tests expanded table-region crops because OCR/text
    # content bands can exclude nearby ruling lines. Crops are still selected only
    # when the expanded candidate improves real grid evidence.
    crop_margin_expansion_pixels: Tuple[int, ...] = (0, 25, 50, 100, 150, 250)


def _clamp_bbox_to_image(bbox: Mapping[str, Any], width: int, height: int, padding: int = 0) -> Optional[Dict[str, int]]:
    try:
        x0 = int(max(0, math.floor(float(bbox.get("x0", 0)) - padding)))
        y0 = int(max(0, math.floor(float(bbox.get("y0", 0)) - padding)))
        x1 = int(min(width, math.ceil(float(bbox.get("x1", width)) + padding)))
        y1 = int(min(height, math.ceil(float(bbox.get("y1", height)) + padding)))
    except (TypeError, ValueError):
        return None
    if x1 <= x0 or y1 <= y0:
        return None
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}


def _scale_bbox(bbox: Mapping[str, Any], scale: float) -> Dict[str, float]:
    return {
        "x0": round(float(bbox.get("x0", 0)) * scale, 3),
        "y0": round(float(bbox.get("y0", 0)) * scale, 3),
        "x1": round(float(bbox.get("x1", 0)) * scale, 3),
        "y1": round(float(bbox.get("y1", 0)) * scale, 3),
    }


def _offset_lines(lines: Sequence[Mapping[str, Any]], x_offset: float = 0.0, y_offset: float = 0.0) -> List[Dict[str, Any]]:
    offset_lines: List[Dict[str, Any]] = []
    for line in lines:
        item = dict(line)
        for key in ("x0", "x1"):
            if key in item:
                item[key] = float(item[key]) + x_offset
        for key in ("y0", "y1"):
            if key in item:
                item[key] = float(item[key]) + y_offset
        offset_lines.append(item)
    return offset_lines


def _load_binary_mask(image_path: Path, config: LineDetectionConfig, dark_threshold: Optional[int] = None, crop_bbox: Optional[Mapping[str, Any]] = None) -> Tuple[List[List[bool]], int, int, Dict[str, Any]]:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - environment-specific
        raise RuntimeError("Pillow is required for image line detection") from exc
    with Image.open(image_path) as image:
        image = image.convert("L")
        original_width, original_height = image.size
        crop_info: Dict[str, Any] = {
            "original_image_width": original_width,
            "original_image_height": original_height,
            "crop_applied": False,
            "crop_bbox_original": None,
            "crop_bbox_scaled": None,
            "crop_x_offset_scaled": 0.0,
            "crop_y_offset_scaled": 0.0,
        }
        if crop_bbox:
            clamped = _clamp_bbox_to_image(crop_bbox, original_width, original_height, padding=0)
            if clamped and (clamped["x1"] - clamped["x0"]) >= config.min_crop_width and (clamped["y1"] - clamped["y0"]) >= config.min_crop_height:
                image = image.crop((clamped["x0"], clamped["y0"], clamped["x1"], clamped["y1"]))
                crop_info["crop_applied"] = True
                crop_info["crop_bbox_original"] = clamped
        width, height = image.size
        scale = min(config.max_image_width / max(width, 1), config.max_image_height / max(height, 1), 1.0)
        if scale < 1.0:
            image = image.resize((max(1, int(width * scale)), max(1, int(height * scale))))
            width, height = image.size
        if crop_info["crop_applied"] and crop_info.get("crop_bbox_original"):
            bbox = crop_info["crop_bbox_original"]
            crop_info["crop_bbox_scaled"] = _scale_bbox({
                "x0": bbox["x0"],
                "y0": bbox["y0"],
                "x1": bbox["x1"],
                "y1": bbox["y1"],
            }, scale)
            crop_info["crop_x_offset_scaled"] = round(float(bbox["x0"]) * scale, 3)
            crop_info["crop_y_offset_scaled"] = round(float(bbox["y0"]) * scale, 3)
        pixels = image.load()
        mask: List[List[bool]] = []
        for y in range(height):
            row: List[bool] = []
            for x in range(width):
                row.append(int(pixels[x, y]) <= (config.dark_threshold if dark_threshold is None else dark_threshold))
            mask.append(row)
        crop_info["analysis_width"] = width
        crop_info["analysis_height"] = height
        crop_info["resize_scale"] = scale
        return mask, width, height, crop_info


def _group_runs(indices: Sequence[int]) -> List[Tuple[int, int]]:
    if not indices:
        return []
    runs: List[Tuple[int, int]] = []
    start = prev = indices[0]
    for index in indices[1:]:
        if index == prev + 1:
            prev = index
            continue
        runs.append((start, prev))
        start = prev = index
    runs.append((start, prev))
    return runs

def _longest_dark_run(values: Sequence[bool], max_gap_pixels: int) -> Tuple[int, int, int]:
    """Return start, end, and dark-pixel count for the longest dark run.

    Small gaps are bridged so anti-aliased or slightly broken table rules still
    count as one morphological line candidate.
    """
    best_start = best_end = -1
    best_dark_count = 0
    start = -1
    last_dark = -1
    dark_count = 0
    gap = 0
    for index, value in enumerate(values):
        if value:
            if start < 0:
                start = index
                dark_count = 0
                gap = 0
            last_dark = index
            dark_count += 1
            gap = 0
            current_length = last_dark - start + 1
            best_length = best_end - best_start + 1 if best_start >= 0 else 0
            if current_length > best_length or (current_length == best_length and dark_count > best_dark_count):
                best_start = start
                best_end = last_dark
                best_dark_count = dark_count
        elif start >= 0:
            gap += 1
            if gap > max_gap_pixels:
                start = -1
                last_dark = -1
                dark_count = 0
                gap = 0
    return best_start, best_end, best_dark_count


def _line_centers(lines: Sequence[Mapping[str, Any]], axis: str) -> List[float]:
    if axis == "horizontal":
        return [float((line.get("y0", 0) + line.get("y1", 0)) / 2) for line in lines]
    return [float((line.get("x0", 0) + line.get("x1", 0)) / 2) for line in lines]


def _morphology_signal_strength(result: Mapping[str, Any]) -> str:
    horizontal_count = len(result.get("horizontal_lines") or [])
    vertical_count = len(result.get("vertical_lines") or [])
    intersections = int(result.get("intersection_count") or 0)
    if horizontal_count >= 2 and vertical_count >= 2 and intersections >= 4:
        return "GRID"
    if horizontal_count >= 2 and vertical_count >= 1:
        return "PARTIAL_GRID"
    if horizontal_count or vertical_count:
        return "WEAK_LINE_SIGNAL"
    return "NO_LINE_SIGNAL"


def _morphology_quality_score(result: Mapping[str, Any]) -> float:
    horizontal_count = len(result.get("horizontal_lines") or [])
    vertical_count = len(result.get("vertical_lines") or [])
    intersections = int(result.get("intersection_count") or 0)
    # Favor true grids heavily, then line balance, then raw line counts. This
    # prevents a single dark border from looking better than a sparse but real
    # ruled-table grid.
    balance = min(horizontal_count, vertical_count) * 4
    count_bonus = min(horizontal_count + vertical_count, 40)
    return float(intersections * 10 + balance + count_bonus)


def _detect_table_lines_from_mask(mask: Sequence[Sequence[bool]], width: int, height: int, config: LineDetectionConfig, dark_threshold: int) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "image_line_detection_available": False,
        "horizontal_lines": [],
        "vertical_lines": [],
        "intersection_count": 0,
        "line_detection_review_flags": [],
        "calibrated_dark_threshold": dark_threshold,
    }

    horizontal_candidates: List[Tuple[int, int, int, int]] = []
    for y, row in enumerate(mask):
        x0, x1, dark_count = _longest_dark_run(row, config.max_gap_pixels)
        length = x1 - x0 + 1 if x0 >= 0 else 0
        black_ratio = dark_count / max(width, 1)
        if length >= config.min_line_length and black_ratio >= config.min_black_ratio:
            horizontal_candidates.append((y, x0, x1, dark_count))
    horizontal_candidate_rows = [candidate[0] for candidate in horizontal_candidates]
    horizontal_lookup = {candidate[0]: candidate for candidate in horizontal_candidates}
    for y0, y1 in _group_runs(horizontal_candidate_rows):
        candidates = [horizontal_lookup[y] for y in range(y0, y1 + 1) if y in horizontal_lookup]
        if not candidates:
            continue
        x0 = min(candidate[1] for candidate in candidates)
        x1 = max(candidate[2] for candidate in candidates)
        if x1 - x0 + 1 >= config.min_line_length:
            result["horizontal_lines"].append({
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
                "length": x1 - x0 + 1,
                "thickness": y1 - y0 + 1,
                "method": "calibrated_morphological_long_run_horizontal",
            })

    vertical_candidates: List[Tuple[int, int, int, int]] = []
    for x in range(width):
        column = [mask[y][x] for y in range(height)]
        y0, y1, dark_count = _longest_dark_run(column, config.max_gap_pixels)
        length = y1 - y0 + 1 if y0 >= 0 else 0
        black_ratio = dark_count / max(height, 1)
        if length >= config.min_line_length and black_ratio >= config.min_black_ratio:
            vertical_candidates.append((x, y0, y1, dark_count))
    vertical_candidate_cols = [candidate[0] for candidate in vertical_candidates]
    vertical_lookup = {candidate[0]: candidate for candidate in vertical_candidates}
    for x0, x1 in _group_runs(vertical_candidate_cols):
        candidates = [vertical_lookup[x] for x in range(x0, x1 + 1) if x in vertical_lookup]
        if not candidates:
            continue
        y0 = min(candidate[1] for candidate in candidates)
        y1 = max(candidate[2] for candidate in candidates)
        if y1 - y0 + 1 >= config.min_line_length:
            result["vertical_lines"].append({
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
                "length": y1 - y0 + 1,
                "thickness": x1 - x0 + 1,
                "method": "calibrated_morphological_long_run_vertical",
            })

    intersections = 0
    for hline in result["horizontal_lines"]:
        hy = (hline["y0"] + hline["y1"]) / 2
        for vline in result["vertical_lines"]:
            vx = (vline["x0"] + vline["x1"]) / 2
            if hline["x0"] <= vx <= hline["x1"] and vline["y0"] <= hy <= vline["y1"]:
                intersections += 1
    horizontal_lines = result["horizontal_lines"]
    vertical_lines = result["vertical_lines"]
    result["intersection_count"] = intersections
    result["visual_row_boundary_count"] = len(horizontal_lines)
    result["visual_column_boundary_count"] = len(vertical_lines)
    result["visual_row_count_estimate"] = max(0, len(horizontal_lines) - 1)
    result["visual_column_count_estimate"] = max(0, len(vertical_lines) - 1)
    result["horizontal_line_centers"] = _line_centers(horizontal_lines, "horizontal")[:100]
    result["vertical_line_centers"] = _line_centers(vertical_lines, "vertical")[:100]
    result["image_line_detection_available"] = bool(horizontal_lines or vertical_lines)
    result["morphology_signal_strength"] = _morphology_signal_strength(result)
    result["morphology_quality_score"] = _morphology_quality_score(result)
    if not horizontal_lines:
        result["line_detection_review_flags"].append("no_horizontal_lines_detected")
    if not vertical_lines:
        result["line_detection_review_flags"].append("no_vertical_lines_detected")
    if result["morphology_signal_strength"] in {"NO_LINE_SIGNAL", "WEAK_LINE_SIGNAL", "PARTIAL_GRID"}:
        result["line_detection_review_flags"].append("weak_morphology_grid_signal")
    if horizontal_lines and vertical_lines and intersections == 0:
        result["line_detection_review_flags"].append("morphology_lines_have_no_intersections")
    return result


def detect_table_lines_from_image(image_path: Path, config: Optional[LineDetectionConfig] = None, crop_bbox: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Detect candidate horizontal/vertical table ruling lines from an image.

    The implementation is deterministic and safety-first. It uses binarization
    plus projection-style morphology, but now calibrates across several dark
    thresholds and records whether the detected line signal is a real grid, a
    partial grid, or only a weak page-line signal. Weak signals remain useful
    routing evidence but are not allowed to inflate geometry confidence.
    """
    config = config or LineDetectionConfig()
    result: Dict[str, Any] = {
        "image_path": str(image_path),
        "image_line_detection_available": False,
        "horizontal_lines": [],
        "vertical_lines": [],
        "intersection_count": 0,
        "line_detection_review_flags": [],
        "morphology_signal_strength": "NO_LINE_SIGNAL",
        "morphology_quality_score": 0.0,
    }
    if not image_path.exists():
        result["line_detection_review_flags"].append("image_path_missing")
        return result

    threshold_candidates = tuple(dict.fromkeys((*config.dark_threshold_candidates, config.dark_threshold)))
    calibrated_results: List[Dict[str, Any]] = []
    for threshold in threshold_candidates:
        try:
            mask, width, height, crop_info = _load_binary_mask(image_path, config, dark_threshold=threshold, crop_bbox=crop_bbox)
        except Exception as exc:  # pragma: no cover - defensive around image codecs
            result["line_detection_review_flags"].append(f"image_open_failed:{type(exc).__name__}")
            return result
        candidate = _detect_table_lines_from_mask(mask, width, height, config, int(threshold))
        candidate["crop_info"] = crop_info
        if crop_info.get("crop_applied"):
            candidate["table_region_crop_applied"] = True
            candidate["table_region_bbox"] = crop_info.get("crop_bbox_original")
            candidate["horizontal_lines"] = _offset_lines(candidate.get("horizontal_lines") or [], crop_info.get("crop_x_offset_scaled") or 0.0, crop_info.get("crop_y_offset_scaled") or 0.0)
            candidate["vertical_lines"] = _offset_lines(candidate.get("vertical_lines") or [], crop_info.get("crop_x_offset_scaled") or 0.0, crop_info.get("crop_y_offset_scaled") or 0.0)
            candidate["horizontal_line_centers"] = _line_centers(candidate.get("horizontal_lines") or [], "horizontal")[:100]
            candidate["vertical_line_centers"] = _line_centers(candidate.get("vertical_lines") or [], "vertical")[:100]
        else:
            candidate["table_region_crop_applied"] = False
            candidate["table_region_bbox"] = None
        calibrated_results.append(candidate)

    if not calibrated_results:
        result["line_detection_review_flags"].append("no_calibrated_morphology_results")
        return result

    best = max(calibrated_results, key=_morphology_quality_score)
    best["image_path"] = str(image_path)
    best["table_region_crop_requested"] = bool(crop_bbox)
    best["table_region_crop_applied"] = bool(best.get("table_region_crop_applied"))
    best["table_region_bbox"] = best.get("table_region_bbox")
    best["calibration_attempt_count"] = len(calibrated_results)
    best["calibration_candidates"] = [
        {
            "dark_threshold": candidate.get("calibrated_dark_threshold"),
            "horizontal_line_count": len(candidate.get("horizontal_lines") or []),
            "vertical_line_count": len(candidate.get("vertical_lines") or []),
            "intersection_count": candidate.get("intersection_count"),
            "morphology_signal_strength": candidate.get("morphology_signal_strength"),
            "morphology_quality_score": candidate.get("morphology_quality_score"),
        }
        for candidate in calibrated_results
    ]
    return best


def cluster_values(values: Sequence[float], tolerance: float) -> List[Dict[str, Any]]:
    if not values:
        return []
    sorted_values = sorted(values)
    clusters: List[List[float]] = [[sorted_values[0]]]
    for value in sorted_values[1:]:
        center = sum(clusters[-1]) / len(clusters[-1])
        if abs(value - center) <= tolerance:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return [
        {"index": index, "center": round(sum(cluster) / len(cluster), 3), "count": len(cluster), "min": min(cluster), "max": max(cluster)}
        for index, cluster in enumerate(clusters)
    ]


def infer_geometry_from_records(records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    bboxes = [record.get("bbox") for record in records if isinstance(record.get("bbox"), Mapping)]
    centers_y = [float((bbox["y0"] + bbox["y1"]) / 2) for bbox in bboxes]
    centers_x = [float((bbox["x0"] + bbox["x1"]) / 2) for bbox in bboxes]
    if bboxes:
        heights = [float(bbox["y1"] - bbox["y0"]) for bbox in bboxes]
        widths = [float(bbox["x1"] - bbox["x0"]) for bbox in bboxes]
        row_tolerance = max(5.0, median(heights) * 0.75)
        col_tolerance = max(10.0, median(widths) * 0.6)
        row_clusters = cluster_values(centers_y, row_tolerance)
        column_clusters = cluster_values(centers_x, col_tolerance)
        method = "ocr_bbox_row_column_clustering"
    else:
        row_ids = sorted({str(record.get("row_id")) for record in records if record.get("row_id")})
        col_indices = sorted({str(record.get("column_index")) for record in records if record.get("column_index") is not None})
        row_clusters = [{"index": idx, "row_id": row_id, "count": 1} for idx, row_id in enumerate(row_ids)]
        column_clusters = [{"index": idx, "column_id": col, "count": 1} for idx, col in enumerate(col_indices)]
        if not column_clusters:
            cell_count = sum(1 for record in records if record.get("record_type") == "cell")
            estimated_cols = max(1, min(12, int(round(math.sqrt(max(cell_count, 1))))))
            column_clusters = [{"index": idx, "estimated": True, "count": 0} for idx in range(estimated_cols)]
        method = "normalizer_row_column_fallback"
    return {
        "row_clusters": row_clusters,
        "column_clusters": column_clusters,
        "row_count_estimate": len(row_clusters),
        "column_count_estimate": len(column_clusters),
        "geometry_inference_method": method,
    }


def median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    values_sorted = sorted(values)
    n = len(values_sorted)
    midpoint = n // 2
    if n % 2:
        return float(values_sorted[midpoint])
    return float((values_sorted[midpoint - 1] + values_sorted[midpoint]) / 2)


def domain_validate_records(records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    part_numbers: List[str] = []
    ata_codes: List[str] = []
    revisions: List[str] = []
    quantity_like_cells = 0
    part_number_rows = 0
    for record in records:
        text = str(record.get("text") or "")
        record_parts = PART_NUMBER_RE.findall(text)
        if record_parts:
            part_number_rows += 1 if record.get("record_type") == "row" else 0
        for part in record_parts:
            if part not in part_numbers:
                part_numbers.append(part)
        for ata in ATA_RE.findall(text):
            if ata not in ata_codes:
                ata_codes.append(ata)
        for revision in REVISION_RE.findall(text):
            revision = compact_text(revision)
            if revision and revision not in revisions:
                revisions.append(revision)
        if QUANTITY_RE.match(text.strip()):
            quantity_like_cells += 1
    return {
        "part_number_count": len(part_numbers),
        "part_numbers_sample": part_numbers[:20],
        "ata_code_count": len(ata_codes),
        "ata_codes_sample": ata_codes[:10],
        "revision_token_count": len(revisions),
        "revision_tokens_sample": revisions[:10],
        "quantity_like_cell_count": quantity_like_cells,
        "part_number_row_count": part_number_rows,
        "domain_table_type_hints": infer_domain_table_type(part_numbers, ata_codes, revisions, quantity_like_cells),
    }


def infer_domain_table_type(part_numbers: Sequence[str], ata_codes: Sequence[str], revisions: Sequence[str], quantity_like_cells: int) -> List[str]:
    hints: List[str] = []
    if part_numbers:
        hints.append("parts_list_or_ipl_table")
    if ata_codes:
        hints.append("ata_reference_table")
    if revisions:
        hints.append("revision_history_table")
    if quantity_like_cells and part_numbers:
        hints.append("parts_quantity_table")
    if not hints:
        hints.append("generic_table")
    return hints


def detect_merged_cells(records: Sequence[Mapping[str, Any]], inferred: Mapping[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    row_to_cells: Dict[str, List[Mapping[str, Any]]] = {}
    for record in records:
        if record.get("record_type") != "cell":
            continue
        row_id = str(record.get("row_id") or "unknown_row")
        row_to_cells.setdefault(row_id, []).append(record)
    row_widths = [len(cells) for cells in row_to_cells.values() if cells]
    modal_width = most_common_int(row_widths) if row_widths else int(inferred.get("column_count_estimate") or 0)
    if modal_width > 1:
        for row_id, cells in row_to_cells.items():
            if 0 < len(cells) < modal_width:
                candidates.append({
                    "candidate_id": stable_id("merged", row_id, len(cells), modal_width),
                    "row_id": row_id,
                    "reason": "row_has_fewer_cells_than_modal_width",
                    "cell_count": len(cells),
                    "modal_column_count": modal_width,
                    "candidate_type": "possible_colspan_or_missing_cell",
                })
    bbox_widths = [float(record["bbox"]["x1"] - record["bbox"]["x0"]) for record in records if isinstance(record.get("bbox"), Mapping)]
    median_width = median(bbox_widths)
    if median_width > 0:
        for record in records:
            bbox = record.get("bbox")
            if not isinstance(bbox, Mapping):
                continue
            width = float(bbox["x1"] - bbox["x0"])
            if width >= median_width * 2.2:
                candidates.append({
                    "candidate_id": stable_id("merged", record.get("record_id"), width, median_width),
                    "row_id": record.get("row_id"),
                    "cell_id": record.get("cell_id"),
                    "reason": "cell_bbox_much_wider_than_median",
                    "cell_width": round(width, 3),
                    "median_cell_width": round(median_width, 3),
                    "candidate_type": "possible_colspan",
                })
    return candidates


def most_common_int(values: Sequence[int]) -> int:
    counts: Dict[int, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    if not counts:
        return 0
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def load_table_image_resolver_cards(table_image_resolver_path: Optional[Path]) -> Tuple[Dict[Tuple[str, str], Mapping[str, Any]], str]:
    if not table_image_resolver_path:
        return {}, "NOT_PROVIDED"
    payload = read_json(table_image_resolver_path)
    quality_status = str(payload.get("quality_status") or payload.get("status") or "UNKNOWN") if isinstance(payload, Mapping) else "UNKNOWN"
    cards = payload.get("table_image_resolution_cards") if isinstance(payload, Mapping) else []
    resolver_map: Dict[Tuple[str, str], Mapping[str, Any]] = {}
    if isinstance(cards, list):
        for card in cards:
            if not isinstance(card, Mapping):
                continue
            page_id = card.get("page_id")
            table_id = card.get("table_id")
            if isinstance(page_id, str) and isinstance(table_id, str):
                resolver_map[(page_id, table_id)] = card
    return resolver_map, quality_status




def load_table_bbox_resolver_cards(table_bbox_resolver_path: Optional[Path]) -> Tuple[Dict[Tuple[str, str], Mapping[str, Any]], str]:
    if not table_bbox_resolver_path:
        return {}, "NOT_PROVIDED"
    payload = read_json(table_bbox_resolver_path)
    quality_status = str(payload.get("quality_status") or payload.get("status") or "UNKNOWN") if isinstance(payload, Mapping) else "UNKNOWN"
    cards = payload.get("table_bbox_cards") if isinstance(payload, Mapping) else []
    resolver_map: Dict[Tuple[str, str], Mapping[str, Any]] = {}
    if isinstance(cards, list):
        for card in cards:
            if not isinstance(card, Mapping):
                continue
            page_id = card.get("page_id")
            table_id = card.get("table_id")
            if isinstance(page_id, str) and isinstance(table_id, str):
                resolver_map[(page_id, table_id)] = card
    return resolver_map, quality_status


def load_table_crop_completeness_guard_cards(guard_path: Optional[Path]) -> Tuple[Dict[Tuple[str, str], Mapping[str, Any]], str]:
    """Load crop-completeness guard cards keyed by (page_id, table_id).

    The guard is advisory/read-only, but production table-line geometry treats a
    blocked guard decision as a hard stop for selecting crop or margin morphology.
    This prevents visually incomplete crops or unreviewed detector disagreement
    from becoming the selected geometry path.
    """
    if not guard_path:
        return {}, "NOT_PROVIDED"
    payload = read_json(guard_path)
    quality_status = str(payload.get("quality_status") or payload.get("status") or "UNKNOWN") if isinstance(payload, Mapping) else "UNKNOWN"
    cards = payload.get("crop_completeness_cards") if isinstance(payload, Mapping) else []
    guard_map: Dict[Tuple[str, str], Mapping[str, Any]] = {}
    if isinstance(cards, list):
        for card in cards:
            if not isinstance(card, Mapping):
                continue
            page_id = card.get("page_id")
            table_id = card.get("table_id")
            if isinstance(page_id, str) and isinstance(table_id, str):
                guard_map[(page_id, table_id)] = card
    return guard_map, quality_status




def load_table_full_region_recovery_cards(recovery_path: Optional[Path]) -> Tuple[Dict[Tuple[str, str], Mapping[str, Any]], str]:
    """Load full-table region recovery cards keyed by (page_id, table_id).

    Full-region recovery is an upstream advisory artifact that tries to fix
    incomplete crop bboxes by unioning OCR content, detector projection bboxes,
    and existing table bbox candidates. Table Line Geometry can use a ready,
    non-page-like recovered bbox as a crop candidate, but the normal crop scoring
    and completeness guard still decide whether that crop may be selected.
    """
    if not recovery_path:
        return {}, "NOT_PROVIDED"
    payload = read_json(recovery_path)
    quality_status = str(payload.get("quality_status") or payload.get("status") or "UNKNOWN") if isinstance(payload, Mapping) else "UNKNOWN"
    cards = payload.get("recovery_cards") if isinstance(payload, Mapping) else []
    recovery_map: Dict[Tuple[str, str], Mapping[str, Any]] = {}
    if isinstance(cards, list):
        for card in cards:
            if not isinstance(card, Mapping):
                continue
            page_id = card.get("page_id")
            table_id = card.get("table_id")
            if isinstance(page_id, str) and isinstance(table_id, str):
                recovery_map[(page_id, table_id)] = card
    return recovery_map, quality_status

def _bbox_width_height(bbox: Mapping[str, Any]) -> Tuple[float, float]:
    try:
        width = float(bbox.get("x1", 0)) - float(bbox.get("x0", 0))
        height = float(bbox.get("y1", 0)) - float(bbox.get("y0", 0))
        return width, height
    except (TypeError, ValueError):
        return 0.0, 0.0


def bbox_resolver_table_region_bbox(
    page_id: str,
    table_id: str,
    bbox_resolver_map: Mapping[Tuple[str, str], Mapping[str, Any]],
    config: Optional[LineDetectionConfig] = None,
    min_coverage_ratio: float = 0.002,
) -> Tuple[Optional[Dict[str, float]], Dict[str, Any]]:
    """Return a crop-safe bbox from Table BBox Resolver plus audit metadata.

    BBox Resolver output can be advisory. Some real records currently contain
    very small low-specificity boxes, so this function only enables cropping
    when dimensions and coverage are reasonable. Rejected bboxes are still
    surfaced as review metadata and never treated as source truth.
    """
    config = config or LineDetectionConfig()
    card = bbox_resolver_map.get((page_id, table_id))
    metadata: Dict[str, Any] = {
        "table_bbox_resolver_available": bool(card),
        "table_bbox_resolver_status": card.get("bbox_resolution_status") if card else None,
        "table_bbox_resolver_crop_ready": bool(card.get("crop_ready")) if card else False,
        "table_bbox_resolver_bbox_source": card.get("bbox_source") if card else None,
        "table_bbox_resolver_bbox_confidence": card.get("bbox_confidence") if card else None,
        "table_bbox_resolver_bbox_coverage_ratio": card.get("bbox_coverage_ratio") if card else None,
        "table_bbox_resolver_review_flags": list(card.get("review_flags") or []) if card else [],
        "table_bbox_resolver_used_for_crop": False,
        "table_bbox_resolver_crop_rejected": False,
        "table_bbox_resolver_rejection_reason": None,
    }
    if not card:
        return None, metadata
    if card.get("bbox_resolution_status") != "RESOLVED" or not card.get("crop_ready"):
        metadata["table_bbox_resolver_crop_rejected"] = True
        metadata["table_bbox_resolver_rejection_reason"] = "bbox_not_resolved_or_not_crop_ready"
        return None, metadata
    bbox = parse_bbox(card.get("table_region_bbox"))
    if not bbox:
        metadata["table_bbox_resolver_crop_rejected"] = True
        metadata["table_bbox_resolver_rejection_reason"] = "bbox_missing_or_unparseable"
        return None, metadata
    width, height = _bbox_width_height(bbox)
    coverage = card.get("bbox_coverage_ratio")
    try:
        coverage_float = float(coverage) if coverage is not None else None
    except (TypeError, ValueError):
        coverage_float = None
    if width < config.min_crop_width or height < config.min_crop_height:
        metadata["table_bbox_resolver_crop_rejected"] = True
        metadata["table_bbox_resolver_rejection_reason"] = "bbox_below_minimum_crop_dimensions"
        return None, metadata
    if coverage_float is not None and coverage_float < min_coverage_ratio:
        metadata["table_bbox_resolver_crop_rejected"] = True
        metadata["table_bbox_resolver_rejection_reason"] = "bbox_coverage_ratio_too_small"
        return None, metadata
    metadata["table_bbox_resolver_used_for_crop"] = True
    return bbox, metadata
def resolve_path_candidate(value: Any, image_root: Optional[Path]) -> Optional[Path]:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = Path(value)
    candidates = [raw]
    if image_root and not raw.is_absolute():
        candidates.insert(0, image_root / raw)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def resolver_image_path(
    page_id: str,
    table_id: str,
    resolver_map: Mapping[Tuple[str, str], Mapping[str, Any]],
    image_root: Optional[Path],
) -> Optional[Path]:
    card = resolver_map.get((page_id, table_id))
    if not card:
        return None
    if card.get("image_resolution_status") != "RESOLVED":
        return None
    return resolve_path_candidate(card.get("resolved_image_path"), image_root)



def infer_table_region_bbox_from_records(records: Sequence[Mapping[str, Any]], padding: int = 20) -> Optional[Dict[str, float]]:
    """Infer a table-region crop from OCR/table record bounding boxes.

    The crop is advisory and only used to focus morphology. If the current
    normalizer artifact lacks bounding boxes, callers fall back to whole-page
    morphology and keep review-routing safeguards.
    """
    bboxes = [record.get("bbox") for record in records if isinstance(record.get("bbox"), Mapping)]
    if len(bboxes) < 2:
        return None
    try:
        x0 = min(float(bbox["x0"]) for bbox in bboxes) - padding
        y0 = min(float(bbox["y0"]) for bbox in bboxes) - padding
        x1 = max(float(bbox["x1"]) for bbox in bboxes) + padding
        y1 = max(float(bbox["y1"]) for bbox in bboxes) + padding
    except (KeyError, TypeError, ValueError):
        return None
    if x1 - x0 < 80 or y1 - y0 < 40:
        return None
    return {"x0": max(0.0, x0), "y0": max(0.0, y0), "x1": x1, "y1": y1}


def _signal_rank(signal_strength: Any) -> int:
    return {"NO_LINE_SIGNAL": 0, "WEAK_LINE_SIGNAL": 1, "PARTIAL_GRID": 2, "GRID": 3}.get(str(signal_strength), 0)




def full_region_recovery_table_region_bbox(
    page_id: str,
    table_id: str,
    full_region_recovery_map: Mapping[Tuple[str, str], Mapping[str, Any]],
    config: Optional[LineDetectionConfig] = None,
    max_full_page_coverage_ratio: float = 0.95,
) -> Tuple[Optional[Dict[str, float]], Dict[str, Any]]:
    """Return a recovered full-table bbox plus audit metadata.

    A recovered bbox is used only when the recovery module marked it ready and
    the recovered area is not effectively a full-page crop. This makes recovered
    full-table regions a safer candidate crop source than the old incomplete
    bbox while still preventing broad page-like regions from replacing page
    morphology.
    """
    config = config or LineDetectionConfig()
    card = full_region_recovery_map.get((page_id, table_id))
    metadata: Dict[str, Any] = {
        "table_full_region_recovery_available": bool(card),
        "table_full_region_recovery_status": card.get("crop_recovery_status") if card else None,
        "table_full_region_recovery_ready": bool(card.get("crop_recovery_ready")) if card else False,
        "table_full_region_recovery_full_table_coverage_ratio": card.get("full_table_coverage_ratio") if card else None,
        "table_full_region_recovery_too_page_like": "recovered_bbox_too_page_like" in (card.get("review_flags") or []) if card else False,
        "table_full_region_recovery_used_for_crop": False,
        "table_full_region_recovery_crop_rejected": False,
        "table_full_region_recovery_rejection_reason": None,
        "table_full_region_recovery_review_flags": list(card.get("review_flags") or []) if card else [],
        "table_full_region_recovery_recommended_actions": list(card.get("recommended_actions") or []) if card else [],
        "table_full_region_recovery_original_crop_bbox": card.get("original_crop_bbox") if card else None,
        "table_full_region_recovery_expanded_full_table_bbox": card.get("expanded_full_table_bbox") if card else None,
    }
    if not card:
        return None, metadata
    if not card.get("crop_recovery_ready"):
        metadata["table_full_region_recovery_crop_rejected"] = True
        metadata["table_full_region_recovery_rejection_reason"] = "full_region_recovery_not_ready"
        return None, metadata
    bbox = parse_bbox(card.get("expanded_full_table_bbox"))
    if not bbox:
        metadata["table_full_region_recovery_crop_rejected"] = True
        metadata["table_full_region_recovery_rejection_reason"] = "expanded_full_table_bbox_missing_or_unparseable"
        return None, metadata
    width, height = _bbox_width_height(bbox)
    if width < config.min_crop_width or height < config.min_crop_height:
        metadata["table_full_region_recovery_crop_rejected"] = True
        metadata["table_full_region_recovery_rejection_reason"] = "expanded_full_table_bbox_below_minimum_crop_dimensions"
        return None, metadata
    try:
        coverage = float(card.get("full_table_coverage_ratio") or 0.0)
    except (TypeError, ValueError):
        coverage = 0.0
    if coverage >= max_full_page_coverage_ratio:
        metadata["table_full_region_recovery_crop_rejected"] = True
        metadata["table_full_region_recovery_rejection_reason"] = "expanded_full_table_bbox_too_page_like"
        return None, metadata
    metadata["table_full_region_recovery_used_for_crop"] = True
    return bbox, metadata

def _line_count(result: Mapping[str, Any], key: str) -> int:
    value = result.get(key)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return len(value)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _is_broad_crop_candidate(crop_metadata: Optional[Mapping[str, Any]]) -> bool:
    if not crop_metadata:
        return False
    flags = set(crop_metadata.get("table_bbox_resolver_review_flags") or [])
    if "ocr_enrichment_bbox_broad_crop_candidate" in flags:
        return True
    source = str(crop_metadata.get("table_bbox_resolver_bbox_source") or "")
    try:
        coverage = float(crop_metadata.get("table_bbox_resolver_bbox_coverage_ratio") or 0.0)
    except (TypeError, ValueError):
        coverage = 0.0
    return source.startswith("ocr_") and coverage >= 0.75


def expand_bbox_by_margin(bbox: Mapping[str, Any], margin_pixels: int) -> Optional[Dict[str, float]]:
    parsed = parse_bbox(bbox)
    if not parsed:
        return None
    margin = max(0.0, float(margin_pixels))
    return {
        "x0": max(0.0, float(parsed["x0"]) - margin),
        "y0": max(0.0, float(parsed["y0"]) - margin),
        "x1": float(parsed["x1"]) + margin,
        "y1": float(parsed["y1"]) + margin,
    }


def detect_margin_expanded_region_morphology(
    image_path: Path,
    base_crop_bbox: Optional[Mapping[str, Any]],
    config: Optional[LineDetectionConfig] = None,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """Run crop morphology over several margin-expanded bbox candidates.

    This is intentionally advisory. The caller still compares the best crop
    candidate against whole-page morphology and only selects it when it improves
    vertical lines/intersections or grid strength.
    """
    if not base_crop_bbox:
        return None, []
    config = config or LineDetectionConfig()
    candidates: List[Dict[str, Any]] = []
    for margin in config.crop_margin_expansion_pixels:
        expanded = expand_bbox_by_margin(base_crop_bbox, int(margin))
        if not expanded:
            continue
        candidate = detect_table_lines_from_image(image_path, config, crop_bbox=expanded)
        candidate["crop_margin_pixels"] = int(margin)
        candidate["margin_expansion_candidate"] = True
        candidate["margin_expanded_bbox"] = expanded
        candidate["base_table_region_bbox"] = dict(base_crop_bbox)
        candidate["horizontal_line_count"] = _line_count(candidate, "horizontal_lines")
        candidate["vertical_line_count"] = _line_count(candidate, "vertical_lines")
        candidate["margin_candidate_intersection_count"] = int(candidate.get("intersection_count") or 0)
        candidates.append(candidate)
    if not candidates:
        return None, []
    best = max(
        candidates,
        key=lambda item: (
            _signal_rank(item.get("morphology_signal_strength")),
            int(item.get("intersection_count") or 0),
            _line_count(item, "vertical_lines"),
            float(item.get("morphology_quality_score") or 0.0),
            -int(item.get("crop_margin_pixels") or 0),
        ),
    )
    best = dict(best)
    best["margin_expansion_selected_candidate"] = True
    best["margin_expansion_candidate_count"] = len(candidates)
    best["margin_expansion_candidates"] = [
        {
            "margin_pixels": int(candidate.get("crop_margin_pixels") or 0),
            "horizontal_line_count": _line_count(candidate, "horizontal_lines"),
            "vertical_line_count": _line_count(candidate, "vertical_lines"),
            "intersection_count": int(candidate.get("intersection_count") or 0),
            "morphology_signal_strength": candidate.get("morphology_signal_strength"),
            "morphology_quality_score": candidate.get("morphology_quality_score"),
            "table_region_crop_applied": bool(candidate.get("table_region_crop_applied")),
        }
        for candidate in candidates
    ]
    return best, candidates


def choose_region_or_page_morphology(
    page_result: Mapping[str, Any],
    region_result: Optional[Mapping[str, Any]],
    crop_metadata: Optional[Mapping[str, Any]] = None,
    crop_completeness_guard: Optional[Mapping[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Choose the safer morphology result and record why.

    Cropped table-region morphology is preferred only when it materially improves
    grid evidence. The crop path must improve vertical lines or intersections
    when it is only a weak signal. Broad OCR-derived bboxes are treated even
    more conservatively because they often behave like page-level crops. This
    prevents horizontal-only OCR crops from replacing a safer whole-page result.
    """
    page = dict(page_result)
    region = dict(region_result or {})
    page_horizontal = _line_count(page, "horizontal_lines")
    page_vertical = _line_count(page, "vertical_lines")
    page_intersections = int(page.get("intersection_count") or 0)
    region_horizontal = _line_count(region, "horizontal_lines") if region else 0
    region_vertical = _line_count(region, "vertical_lines") if region else 0
    region_intersections = int(region.get("intersection_count") or 0) if region else 0
    broad_crop_candidate = _is_broad_crop_candidate(crop_metadata)
    guard = dict(crop_completeness_guard or {})
    guard_available = bool(guard)
    guard_selection_allowed = (guard.get("crop_selection_allowed") is True) if guard_available else None
    raw_guard_selection_blocked = bool(guard.get("crop_selection_blocked")) if guard_available else False
    # A positive allow decision is authoritative for selection gating. Some
    # advisory guard artifacts can still carry review/blocking context for
    # unreviewed detector overlays, but once the full-region recovery gate has
    # explicitly allowed a crop, Table Line Geometry must not also mark that
    # same crop as blocked by the guard.
    guard_selection_blocked = False if guard_selection_allowed is True else raw_guard_selection_blocked
    guard_status = guard.get("crop_completeness_status") if guard_available else None
    guard_verdict = guard.get("human_review_verdict") if guard_available else None
    comparison = {
        "page_morphology_signal_strength": page.get("morphology_signal_strength"),
        "page_morphology_quality_score": page.get("morphology_quality_score"),
        "page_horizontal_line_count": page_horizontal,
        "page_vertical_line_count": page_vertical,
        "page_intersection_count": page_intersections,
        "region_morphology_signal_strength": region.get("morphology_signal_strength"),
        "region_morphology_quality_score": region.get("morphology_quality_score"),
        "region_horizontal_line_count": region_horizontal,
        "region_vertical_line_count": region_vertical,
        "region_intersection_count": region_intersections,
        "crop_vertical_line_gain": region_vertical - page_vertical,
        "crop_intersection_gain": region_intersections - page_intersections,
        "crop_horizontal_line_gain": region_horizontal - page_horizontal,
        "broad_crop_candidate": broad_crop_candidate,
        "crop_selection_requires_vertical_or_intersection_gain": True,
        "crop_selection_rejected_no_vertical_or_intersection_gain": False,
        "crop_selection_rejection_reason": None,
        "selected_morphology_scope": "page",
        "table_region_crop_available": bool(region),
        "table_region_crop_applied": bool(region.get("table_region_crop_applied")) if region else False,
        "margin_expansion_candidate_count": int(region.get("margin_expansion_candidate_count") or 0) if region else 0,
        "margin_expansion_selected_candidate": bool(region.get("margin_expansion_selected_candidate")) if region else False,
        "selected_crop_margin_pixels": region.get("crop_margin_pixels") if region else None,
        "margin_expansion_candidates": region.get("margin_expansion_candidates") if region else [],
        "crop_completeness_guard_available": guard_available,
        "crop_completeness_status": guard_status,
        "crop_completeness_human_review_verdict": guard_verdict,
        "crop_completeness_guard_selection_allowed": guard_selection_allowed,
        "crop_completeness_guard_selection_blocked": guard_selection_blocked,
        "crop_selection_blocked_by_completeness_guard": False,
        "crop_completeness_guard_review_flags": list(guard.get("review_flags") or []) if guard_available else [],
        "crop_completeness_guard_recommended_actions": list(guard.get("recommended_actions") or []) if guard_available else [],
    }
    if not region:
        page["selected_morphology_scope"] = "page"
        page["table_region_crop_available"] = False
        return page, comparison

    page_rank = _signal_rank(page.get("morphology_signal_strength"))
    region_rank = _signal_rank(region.get("morphology_signal_strength"))
    page_score = float(page.get("morphology_quality_score") or 0.0)
    region_score = float(region.get("morphology_quality_score") or 0.0)
    vertical_gain = region_vertical > page_vertical
    intersection_gain = region_intersections > page_intersections
    material_grid_gain = vertical_gain or intersection_gain
    region_has_table_grid_evidence = region_rank >= 2 or (region_vertical >= 1 and region_horizontal >= 2) or region_intersections > 0

    use_region = False
    rejection_reason: Optional[str] = None
    if guard_selection_blocked:
        rejection_reason = "crop_selection_blocked_by_completeness_guard"
    elif guard_available and guard_selection_allowed is False:
        rejection_reason = "crop_selection_not_allowed_by_completeness_guard"
    elif region_rank <= 0:
        rejection_reason = "crop_has_no_line_signal"
    elif broad_crop_candidate and not material_grid_gain:
        rejection_reason = "broad_crop_without_vertical_or_intersection_gain"
    elif page_rank >= 3 and region_rank < 3:
        rejection_reason = "page_has_stronger_full_grid"
    elif region_rank > page_rank and region_has_table_grid_evidence:
        use_region = True
    elif region_rank == page_rank and region_rank >= 2 and region_score > page_score and material_grid_gain:
        use_region = True
    elif page_rank <= 1 and region_rank >= 2 and region_has_table_grid_evidence:
        use_region = True
    elif page_rank <= 1 and region_rank <= 1 and region_score > page_score and material_grid_gain:
        use_region = True
    else:
        rejection_reason = "crop_did_not_improve_grid_evidence"

    if not use_region:
        if guard_selection_allowed is not True and (guard_selection_blocked or (guard_available and guard_selection_allowed is False)):
            comparison["crop_selection_blocked_by_completeness_guard"] = True
        if not material_grid_gain and region_rank <= 1:
            comparison["crop_selection_rejected_no_vertical_or_intersection_gain"] = True
            rejection_reason = rejection_reason or "crop_without_vertical_or_intersection_gain"
        comparison["crop_selection_rejection_reason"] = rejection_reason

    selected = dict(region if use_region else page)
    selected["selected_morphology_scope"] = "table_region_crop" if use_region else "page"
    selected["table_region_crop_available"] = True
    # Keep crop-attempt metadata even when page morphology is selected as the
    # stronger signal. This lets downstream quality distinguish "crop was tried"
    # from "crop was chosen."
    selected["table_region_crop_applied"] = bool(region.get("table_region_crop_applied"))
    if region.get("table_region_bbox") and not selected.get("table_region_bbox"):
        selected["table_region_bbox"] = region.get("table_region_bbox")
    selected["crop_margin_pixels"] = region.get("crop_margin_pixels") if use_region else None
    selected["margin_expansion_selected_for_crop_morphology"] = bool(use_region and region.get("margin_expansion_selected_candidate"))
    selected["margin_expansion_candidate_count"] = int(region.get("margin_expansion_candidate_count") or 0) if region else 0
    selected["crop_completeness_guard_available"] = guard_available
    selected["crop_completeness_status"] = guard_status
    selected["crop_completeness_human_review_verdict"] = guard_verdict
    selected["crop_completeness_guard_selection_allowed"] = guard_selection_allowed
    selected["crop_completeness_guard_selection_blocked"] = guard_selection_blocked
    selected["crop_selection_blocked_by_completeness_guard"] = bool(comparison.get("crop_selection_blocked_by_completeness_guard"))
    selected["crop_completeness_guard_review_flags"] = comparison.get("crop_completeness_guard_review_flags") or []
    selected["crop_completeness_guard_recommended_actions"] = comparison.get("crop_completeness_guard_recommended_actions") or []
    selected["table_region_crop_comparison"] = comparison | {
        "selected_morphology_scope": selected["selected_morphology_scope"],
        "selected_crop_margin_pixels": selected.get("crop_margin_pixels"),
        "margin_expansion_selected_for_crop_morphology": selected.get("margin_expansion_selected_for_crop_morphology"),
    }
    comparison["selected_morphology_scope"] = selected["selected_morphology_scope"]
    return selected, comparison

def image_alignment_summary(inferred: Mapping[str, Any], image_result: Mapping[str, Any]) -> Dict[str, Any]:
    visual_rows = int(image_result.get("visual_row_count_estimate") or 0)
    visual_cols = int(image_result.get("visual_column_count_estimate") or 0)
    inferred_rows = int(inferred.get("row_count_estimate") or 0)
    inferred_cols = int(inferred.get("column_count_estimate") or 0)
    signal_strength = str(image_result.get("morphology_signal_strength") or "NO_LINE_SIGNAL")
    has_reliable_grid = signal_strength == "GRID"
    return {
        "visual_row_count_estimate": visual_rows,
        "visual_column_count_estimate": visual_cols,
        "inferred_row_count_estimate": inferred_rows,
        "inferred_column_count_estimate": inferred_cols,
        "row_count_delta": abs(visual_rows - inferred_rows) if visual_rows and inferred_rows else None,
        "column_count_delta": abs(visual_cols - inferred_cols) if visual_cols and inferred_cols else None,
        "has_visual_grid_signal": bool(image_result.get("image_line_detection_available")),
        "morphology_signal_strength": signal_strength,
        "has_reliable_visual_grid": has_reliable_grid,
    }


def resolve_image_path(records: Sequence[Mapping[str, Any]], image_root: Optional[Path]) -> Optional[Path]:
    for record in records:
        value = record.get("image_path")
        if not isinstance(value, str) or not value.strip():
            continue
        candidate = resolve_path_candidate(value, image_root)
        if candidate:
            return candidate
    return None


def build_table_geometry_cards(
    records: Sequence[Mapping[str, Any]],
    image_root: Optional[Path] = None,
    max_image_pages: int = 50,
    line_config: Optional[LineDetectionConfig] = None,
    table_image_resolver_map: Optional[Mapping[Tuple[str, str], Mapping[str, Any]]] = None,
    table_bbox_resolver_map: Optional[Mapping[Tuple[str, str], Mapping[str, Any]]] = None,
    table_crop_completeness_guard_map: Optional[Mapping[Tuple[str, str], Mapping[str, Any]]] = None,
    table_full_region_recovery_map: Optional[Mapping[Tuple[str, str], Mapping[str, Any]]] = None,
    route_dispatch_contract: Optional[Any] = None,
    route_dispatch_stats: Optional[Dict[str, int]] = None,
) -> List[Dict[str, Any]]:
    resolver_map = table_image_resolver_map or {}
    bbox_resolver_map = table_bbox_resolver_map or {}
    crop_guard_map = table_crop_completeness_guard_map or {}
    full_region_recovery_map = table_full_region_recovery_map or {}
    stats = route_dispatch_stats if route_dispatch_stats is not None else {}
    stats["route_dispatch_contract_available"] = 1 if route_dispatch_contract is not None else 0
    stats.setdefault("table_route_allowed_input_group_count", 0)
    stats.setdefault("table_route_blocked_input_group_count", 0)
    grouped: Dict[Tuple[str, str], List[Mapping[str, Any]]] = {}
    for record in records:
        page_id = str(record.get("page_id") or (record.get("source_page_ids") or ["unknown_page"])[0])
        table_id = str(record.get("table_id") or stable_id("table", page_id))
        grouped.setdefault((page_id, table_id), []).append(record)

    cards: List[Dict[str, Any]] = []
    image_pages_used = 0
    for (page_id, table_id), group_records in sorted(grouped.items()):
        route_dispatch_contract_available = route_dispatch_contract is not None
        table_route_dispatch_allowed = True
        route_dispatch_review_required = False

        if route_dispatch_contract_available:
            table_route_dispatch_allowed = bool(route_dispatch_contract.is_table_allowed(page_id))
            route_dispatch_review_required = bool(route_dispatch_contract.is_review_required(page_id))
            if not table_route_dispatch_allowed:
                stats["table_route_blocked_input_group_count"] = int(stats.get("table_route_blocked_input_group_count") or 0) + 1
                continue
            stats["table_route_allowed_input_group_count"] = int(stats.get("table_route_allowed_input_group_count") or 0) + 1

        inferred = infer_geometry_from_records(group_records)
        domain = domain_validate_records(group_records)
        merged = detect_merged_cells(group_records, inferred)
        image_result: Dict[str, Any] = {
            "image_line_detection_available": False,
            "horizontal_lines": [],
            "vertical_lines": [],
            "intersection_count": 0,
            "line_detection_review_flags": ["image_not_available_for_geometry_card"],
        }
        resolver_card = resolver_map.get((page_id, table_id))
        image_path = resolver_image_path(page_id, table_id, resolver_map, image_root) or resolve_image_path(group_records, image_root)
        image_resolution_source = "table_image_resolver" if image_path and resolver_card else "record_embedded_image_path" if image_path else "unresolved"
        config = line_config or LineDetectionConfig()
        record_region_bbox = infer_table_region_bbox_from_records(group_records, padding=config.crop_padding_pixels)
        resolver_region_bbox, bbox_resolver_metadata = bbox_resolver_table_region_bbox(page_id, table_id, bbox_resolver_map, config)
        recovered_region_bbox, full_region_recovery_metadata = full_region_recovery_table_region_bbox(page_id, table_id, full_region_recovery_map, config)
        crop_guard_card = crop_guard_map.get((page_id, table_id))
        crop_guard_metadata: Dict[str, Any] = {
            "crop_completeness_guard_available": bool(crop_guard_card),
            "crop_completeness_status": crop_guard_card.get("crop_completeness_status") if crop_guard_card else None,
            "crop_completeness_human_review_verdict": crop_guard_card.get("human_review_verdict") if crop_guard_card else None,
            "crop_completeness_guard_selection_allowed": crop_guard_card.get("crop_selection_allowed") if crop_guard_card else None,
            "crop_completeness_guard_selection_blocked": bool(crop_guard_card.get("crop_selection_blocked")) if crop_guard_card else False,
            "crop_completeness_guard_review_flags": list(crop_guard_card.get("review_flags") or []) if crop_guard_card else [],
            "crop_completeness_guard_recommended_actions": list(crop_guard_card.get("recommended_actions") or []) if crop_guard_card else [],
        }
        table_region_bbox = recovered_region_bbox or resolver_region_bbox or record_region_bbox
        table_region_bbox_source = "table_full_region_recovery" if recovered_region_bbox else "table_bbox_resolver" if resolver_region_bbox else "record_bbox_aggregation" if record_region_bbox else None
        crop_comparison: Dict[str, Any] = {
            "selected_morphology_scope": "none",
            "table_region_crop_available": bool(table_region_bbox),
            "table_region_bbox_source": table_region_bbox_source,
            **bbox_resolver_metadata,
            **full_region_recovery_metadata,
            **crop_guard_metadata,
        }
        if image_path and image_pages_used < max_image_pages:
            image_pages_used += 1
            page_image_result = detect_table_lines_from_image(image_path, line_config)
            region_image_result, margin_candidates = detect_margin_expanded_region_morphology(image_path, table_region_bbox, config) if table_region_bbox else (None, [])
            image_result, crop_comparison = choose_region_or_page_morphology(
                page_image_result,
                region_image_result,
                bbox_resolver_metadata,
                crop_guard_metadata,
            )
            if margin_candidates:
                image_result["margin_expansion_candidate_count"] = len(margin_candidates)
                crop_comparison["margin_expansion_candidate_count"] = len(margin_candidates)
            image_result["image_resolution_source"] = image_resolution_source
            image_result["table_region_bbox_inferred_from_records"] = record_region_bbox
            image_result["table_region_bbox_source"] = table_region_bbox_source
            image_result.update(bbox_resolver_metadata)
            image_result.update(full_region_recovery_metadata)
            image_result.update(crop_guard_metadata)
        alignment = image_alignment_summary(inferred, image_result)
        review_flags: List[str] = list(image_result.get("line_detection_review_flags") or [])
        for bbox_flag in bbox_resolver_metadata.get("table_bbox_resolver_review_flags") or []:
            if bbox_flag == "table_region_bbox_low_specificity":
                review_flags.append("table_region_bbox_low_specificity")
        for recovery_flag in full_region_recovery_metadata.get("table_full_region_recovery_review_flags") or []:
            if isinstance(recovery_flag, str):
                review_flags.append(f"table_full_region_recovery::{recovery_flag}")
        if full_region_recovery_metadata.get("table_full_region_recovery_used_for_crop"):
            review_flags.append("table_full_region_recovery_used_for_crop")
        if full_region_recovery_metadata.get("table_full_region_recovery_crop_rejected"):
            review_flags.append("table_full_region_recovery_crop_rejected")
        crop_selection_comparison = image_result.get("table_region_crop_comparison") or crop_comparison or {}
        crop_guard_selection_allowed_for_card = crop_guard_metadata.get("crop_completeness_guard_selection_allowed") is True
        crop_blocked_by_guard_for_card = (
            not crop_guard_selection_allowed_for_card
            and bool(crop_selection_comparison.get("crop_selection_blocked_by_completeness_guard"))
        )
        if crop_blocked_by_guard_for_card:
            review_flags.append("crop_selection_blocked_by_completeness_guard")
        if crop_selection_comparison.get("crop_selection_rejected_no_vertical_or_intersection_gain"):
            review_flags.append("crop_selection_rejected_no_vertical_or_intersection_gain")
        for guard_flag in crop_selection_comparison.get("crop_completeness_guard_review_flags") or []:
            if isinstance(guard_flag, str):
                review_flags.append(f"crop_completeness_guard::{guard_flag}")
        if crop_selection_comparison.get("margin_expansion_selected_for_crop_morphology"):
            review_flags.append("margin_expansion_selected_for_crop_morphology")
        if crop_selection_comparison.get("broad_crop_candidate") and image_result.get("selected_morphology_scope") == "page":
            review_flags.append("broad_crop_candidate_kept_page_morphology")
        if bbox_resolver_metadata.get("table_bbox_resolver_crop_rejected"):
            review_flags.append("table_bbox_resolver_crop_rejected")
        if not image_result.get("image_line_detection_available"):
            review_flags.append("line_detection_unavailable_or_empty")
        else:
            signal_strength = str(image_result.get("morphology_signal_strength") or "NO_LINE_SIGNAL")
            row_delta = alignment.get("row_count_delta")
            col_delta = alignment.get("column_count_delta")
            if signal_strength == "GRID":
                if isinstance(row_delta, int) and row_delta > max(8, int(inferred.get("row_count_estimate") or 0) * 0.6):
                    review_flags.append("visual_row_count_mismatch_with_ocr_fallback")
                if isinstance(col_delta, int) and col_delta > max(3, int(inferred.get("column_count_estimate") or 0) * 0.75):
                    review_flags.append("visual_column_count_mismatch_with_ocr_fallback")
            elif signal_strength in {"WEAK_LINE_SIGNAL", "PARTIAL_GRID"}:
                review_flags.append("calibrated_morphology_signal_not_full_grid")
        if merged:
            review_flags.append("merged_cell_candidates_present")
        if inferred.get("row_count_estimate", 0) <= 0:
            review_flags.append("no_rows_inferred")
        if inferred.get("column_count_estimate", 0) <= 0:
            review_flags.append("no_columns_inferred")
        source_page_ids = sorted({page for record in group_records for page in as_list(record.get("source_page_ids")) if page})
        if not source_page_ids:
            review_flags.append("missing_source_page_ids")
        confidence = compute_geometry_confidence(group_records, inferred, image_result, domain, merged, review_flags)
        if confidence < 0.55:
            review_flags.append("low_geometry_confidence")
        card = {
            "geometry_card_id": stable_id("table_geom", page_id, table_id),
            "schema_version": SCHEMA_VERSION,
            "page_id": page_id,
            "source_page_ids": source_page_ids or [page_id],
            "table_id": table_id,
            "route_dispatch_processor_contract_available": route_dispatch_contract_available,
            "table_route_dispatch_allowed": table_route_dispatch_allowed,
            "route_dispatch_review_required": route_dispatch_review_required,
            "table_type": first_present(group_records[0], ["table_type"]) or "unknown_table",
            "cell_record_count": sum(1 for record in group_records if record.get("record_type") == "cell"),
            "row_record_count": sum(1 for record in group_records if record.get("record_type") == "row"),
            "table_record_count": len(group_records),
            "row_count_estimate": inferred.get("row_count_estimate"),
            "column_count_estimate": inferred.get("column_count_estimate"),
            "geometry_inference_method": "image_morphology_with_ocr_fallback" if image_result.get("image_line_detection_available") else inferred.get("geometry_inference_method"),
            "ocr_geometry_inference_method": inferred.get("geometry_inference_method"),
            "row_clusters": inferred.get("row_clusters"),
            "column_clusters": inferred.get("column_clusters"),
            "image_line_detection_available": image_result.get("image_line_detection_available", False),
            "horizontal_line_count": len(image_result.get("horizontal_lines") or []),
            "vertical_line_count": len(image_result.get("vertical_lines") or []),
            "intersection_count": image_result.get("intersection_count", 0),
            "morphology_signal_strength": image_result.get("morphology_signal_strength"),
            "morphology_quality_score": image_result.get("morphology_quality_score"),
            "calibrated_dark_threshold": image_result.get("calibrated_dark_threshold"),
            "calibration_attempt_count": image_result.get("calibration_attempt_count"),
            "calibration_candidates": image_result.get("calibration_candidates"),
            "visual_row_boundary_count": image_result.get("visual_row_boundary_count", 0),
            "visual_column_boundary_count": image_result.get("visual_column_boundary_count", 0),
            "visual_row_count_estimate": image_result.get("visual_row_count_estimate", 0),
            "visual_column_count_estimate": image_result.get("visual_column_count_estimate", 0),
            "image_geometry_alignment": alignment,
            "table_region_crop_available": bool(table_region_bbox),
            "table_region_crop_applied": bool(image_result.get("table_region_crop_applied")),
            "selected_morphology_scope": image_result.get("selected_morphology_scope"),
            "table_region_bbox": image_result.get("table_region_bbox") or table_region_bbox,
            "table_region_bbox_source": table_region_bbox_source,
            "record_inferred_table_region_bbox": record_region_bbox,
            "table_region_crop_comparison": image_result.get("table_region_crop_comparison") or crop_comparison,
            "crop_margin_pixels": image_result.get("crop_margin_pixels"),
            "margin_expansion_candidate_count": image_result.get("margin_expansion_candidate_count") or crop_selection_comparison.get("margin_expansion_candidate_count") or 0,
            "margin_expansion_selected_for_crop_morphology": bool(image_result.get("margin_expansion_selected_for_crop_morphology")),
            "crop_completeness_guard_available": crop_guard_metadata.get("crop_completeness_guard_available"),
            "crop_completeness_status": crop_guard_metadata.get("crop_completeness_status"),
            "crop_completeness_human_review_verdict": crop_guard_metadata.get("crop_completeness_human_review_verdict"),
            "crop_completeness_guard_selection_allowed": crop_guard_metadata.get("crop_completeness_guard_selection_allowed"),
            "crop_completeness_guard_selection_blocked": crop_guard_metadata.get("crop_completeness_guard_selection_blocked"),
            "crop_selection_blocked_by_completeness_guard": (
                crop_guard_metadata.get("crop_completeness_guard_selection_allowed") is not True
                and bool(crop_selection_comparison.get("crop_selection_blocked_by_completeness_guard"))
            ),
            "crop_completeness_guard_review_flags": crop_guard_metadata.get("crop_completeness_guard_review_flags"),
            "crop_completeness_guard_recommended_actions": crop_guard_metadata.get("crop_completeness_guard_recommended_actions"),
            "table_bbox_resolver_available": bbox_resolver_metadata.get("table_bbox_resolver_available"),
            "table_bbox_resolver_status": bbox_resolver_metadata.get("table_bbox_resolver_status"),
            "table_bbox_resolver_crop_ready": bbox_resolver_metadata.get("table_bbox_resolver_crop_ready"),
            "table_bbox_resolver_bbox_source": bbox_resolver_metadata.get("table_bbox_resolver_bbox_source"),
            "table_bbox_resolver_bbox_confidence": bbox_resolver_metadata.get("table_bbox_resolver_bbox_confidence"),
            "table_bbox_resolver_bbox_coverage_ratio": bbox_resolver_metadata.get("table_bbox_resolver_bbox_coverage_ratio"),
            "table_bbox_resolver_review_flags": bbox_resolver_metadata.get("table_bbox_resolver_review_flags"),
            "table_bbox_resolver_used_for_crop": bbox_resolver_metadata.get("table_bbox_resolver_used_for_crop"),
            "table_bbox_resolver_crop_rejected": bbox_resolver_metadata.get("table_bbox_resolver_crop_rejected"),
            "table_bbox_resolver_rejection_reason": bbox_resolver_metadata.get("table_bbox_resolver_rejection_reason"),
            "table_full_region_recovery_available": full_region_recovery_metadata.get("table_full_region_recovery_available"),
            "table_full_region_recovery_status": full_region_recovery_metadata.get("table_full_region_recovery_status"),
            "table_full_region_recovery_ready": full_region_recovery_metadata.get("table_full_region_recovery_ready"),
            "table_full_region_recovery_full_table_coverage_ratio": full_region_recovery_metadata.get("table_full_region_recovery_full_table_coverage_ratio"),
            "table_full_region_recovery_too_page_like": full_region_recovery_metadata.get("table_full_region_recovery_too_page_like"),
            "table_full_region_recovery_used_for_crop": full_region_recovery_metadata.get("table_full_region_recovery_used_for_crop"),
            "table_full_region_recovery_crop_rejected": full_region_recovery_metadata.get("table_full_region_recovery_crop_rejected"),
            "table_full_region_recovery_rejection_reason": full_region_recovery_metadata.get("table_full_region_recovery_rejection_reason"),
            "table_full_region_recovery_review_flags": full_region_recovery_metadata.get("table_full_region_recovery_review_flags"),
            "table_full_region_recovery_recommended_actions": full_region_recovery_metadata.get("table_full_region_recovery_recommended_actions"),
            "table_full_region_recovery_original_crop_bbox": full_region_recovery_metadata.get("table_full_region_recovery_original_crop_bbox"),
            "table_full_region_recovery_expanded_full_table_bbox": full_region_recovery_metadata.get("table_full_region_recovery_expanded_full_table_bbox"),
            "table_image_resolver_available": bool(resolver_card),
            "table_image_resolver_status": resolver_card.get("image_resolution_status") if resolver_card else None,
            "image_resolution_confidence": resolver_card.get("image_resolution_confidence") if resolver_card else None,
            "resolved_image_path": str(image_path) if image_path else None,
            "image_resolution_source": image_resolution_source,
            "line_detection": image_result,
            "merged_cell_candidate_count": len(merged),
            "merged_cell_candidates": merged[:25],
            "domain_validation": domain,
            "geometry_confidence": round(confidence, 4),
            "review_required": bool(review_flags),
            "review_flags": sorted(set(review_flags)),
            "recommended_actions": recommended_actions(review_flags, image_result, merged),
            "retrieval_only": True,
            "routing_only": True,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        }
        cards.append(card)
    return cards


def compute_geometry_confidence(
    records: Sequence[Mapping[str, Any]],
    inferred: Mapping[str, Any],
    image_result: Mapping[str, Any],
    domain: Mapping[str, Any],
    merged: Sequence[Mapping[str, Any]],
    review_flags: Sequence[str],
) -> float:
    confidence = 0.15
    if records:
        confidence += 0.15
    if inferred.get("row_count_estimate", 0) > 0:
        confidence += 0.15
    if inferred.get("column_count_estimate", 0) > 0:
        confidence += 0.15
    signal_strength = str(image_result.get("morphology_signal_strength") or "NO_LINE_SIGNAL")
    if signal_strength == "GRID":
        confidence += 0.25
    elif signal_strength == "PARTIAL_GRID":
        confidence += 0.12
    elif signal_strength == "WEAK_LINE_SIGNAL":
        confidence += 0.05
    if domain.get("part_number_count") or domain.get("ata_code_count") or domain.get("revision_token_count"):
        confidence += 0.1
    if merged:
        confidence -= 0.08
    if "missing_source_page_ids" in review_flags:
        confidence -= 0.2
    if "weak_morphology_grid_signal" in review_flags or "calibrated_morphology_signal_not_full_grid" in review_flags:
        confidence -= 0.08
    if "morphology_lines_have_no_intersections" in review_flags:
        confidence -= 0.08
    return max(0.0, min(1.0, confidence))


def recommended_actions(review_flags: Sequence[str], image_result: Mapping[str, Any], merged: Sequence[Mapping[str, Any]]) -> List[str]:
    actions: List[str] = []
    flags = set(review_flags)
    if "line_detection_unavailable_or_empty" in flags or not image_result.get("image_line_detection_available"):
        actions.append("run_or_expand_morphological_line_detection")
        actions.append("use_ocr_row_column_clustering_fallback")
    if merged:
        actions.append("route_possible_merged_cells_to_table_review")
    if "low_geometry_confidence" in flags:
        actions.append("route_low_confidence_table_to_human_review")
    if "visual_row_count_mismatch_with_ocr_fallback" in flags or "visual_column_count_mismatch_with_ocr_fallback" in flags:
        actions.append("compare_morphological_grid_against_normalized_table_records")
    if "weak_morphology_grid_signal" in flags or "calibrated_morphology_signal_not_full_grid" in flags or "morphology_lines_have_no_intersections" in flags:
        actions.append("calibrate_morphological_line_thresholds")
        actions.append("verify_table_lines_against_resolved_tiff")
    if "table_region_bbox_low_specificity" in flags:
        actions.append("confirm_table_region_bbox_against_source_page")
    if "crop_selection_rejected_no_vertical_or_intersection_gain" in flags:
        actions.append("require_crop_vertical_or_intersection_gain_before_selection")
    if "broad_crop_candidate_kept_page_morphology" in flags:
        actions.append("tighten_broad_ocr_crop_before_morphology")
    if "margin_expansion_selected_for_crop_morphology" in flags:
        actions.append("review_margin_expanded_crop_against_source_page")
        actions.append("compare_margin_crop_grid_against_normalized_table_records")
    if "crop_selection_blocked_by_completeness_guard" in flags:
        actions.append("resolve_crop_completeness_guard_before_selecting_crop_morphology")
    if "table_bbox_resolver_crop_rejected" in flags:
        actions.append("improve_table_bbox_resolution_before_crop_morphology")
    if "table_full_region_recovery_used_for_crop" in flags:
        actions.append("review_recovered_full_table_bbox_against_source_page")
    if "table_full_region_recovery_crop_rejected" in flags:
        actions.append("tighten_or_review_full_table_region_recovery_before_crop_morphology")
    if "missing_source_page_ids" in flags:
        actions.append("repair_table_source_lineage_before_index_use")
    if not actions:
        actions.append("table_geometry_ready_for_retrieval_routing")
    return sorted(set(actions))


def compute_summary(cards: Sequence[Mapping[str, Any]], records: Sequence[Mapping[str, Any]], source_status: str) -> Dict[str, Any]:
    answer_permission_count = sum(1 for card in cards if card.get("answer_permission"))
    can_answer_directly_count = sum(1 for card in cards if card.get("can_answer_directly"))
    can_prove_claims_count = sum(1 for card in cards if card.get("can_prove_claims"))
    source_truth_mutation_allowed_count = sum(1 for card in cards if card.get("source_truth_mutation_allowed"))
    unsafe_geometry_card_count = answer_permission_count + can_answer_directly_count + can_prove_claims_count + source_truth_mutation_allowed_count
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "TABLE_LINE_GEOMETRY_BUILT",
        "source_quality_status": source_status,
        "table_record_count": len(records),
        "cell_record_count": sum(1 for record in records if record.get("record_type") == "cell"),
        "row_record_count": sum(1 for record in records if record.get("record_type") == "row"),
        "table_geometry_card_count": len(cards),
        "image_line_detection_card_count": sum(1 for card in cards if card.get("image_line_detection_available")),
        "image_morphology_card_count": sum(1 for card in cards if card.get("geometry_inference_method") == "image_morphology_with_ocr_fallback"),
        "morphology_grid_card_count": sum(1 for card in cards if card.get("morphology_signal_strength") == "GRID"),
        "morphology_partial_grid_card_count": sum(1 for card in cards if card.get("morphology_signal_strength") == "PARTIAL_GRID"),
        "morphology_weak_signal_card_count": sum(1 for card in cards if card.get("morphology_signal_strength") == "WEAK_LINE_SIGNAL"),
        "morphology_no_signal_card_count": sum(1 for card in cards if card.get("morphology_signal_strength") == "NO_LINE_SIGNAL"),
        "morphology_needs_calibration_card_count": sum(1 for card in cards if "calibrated_morphology_signal_not_full_grid" in (card.get("review_flags") or []) or "weak_morphology_grid_signal" in (card.get("review_flags") or []) or "morphology_lines_have_no_intersections" in (card.get("review_flags") or [])),
        "table_region_crop_available_card_count": sum(1 for card in cards if card.get("table_region_crop_available")),
        "table_region_crop_applied_card_count": sum(1 for card in cards if card.get("table_region_crop_applied")),
        "table_region_crop_selected_card_count": sum(1 for card in cards if card.get("selected_morphology_scope") == "table_region_crop"),
        "margin_expansion_candidate_card_count": sum(1 for card in cards if int(card.get("margin_expansion_candidate_count") or 0) > 0),
        "margin_expansion_candidate_evaluation_count": sum(int(card.get("margin_expansion_candidate_count") or 0) for card in cards),
        "margin_expansion_selected_card_count": sum(1 for card in cards if card.get("margin_expansion_selected_for_crop_morphology")),
        "margin_expansion_selected_grid_card_count": sum(1 for card in cards if card.get("margin_expansion_selected_for_crop_morphology") and card.get("morphology_signal_strength") == "GRID"),
        "crop_completeness_guard_available_card_count": sum(1 for card in cards if card.get("crop_completeness_guard_available")),
        "crop_completeness_guard_selection_allowed_card_count": sum(1 for card in cards if card.get("crop_completeness_guard_selection_allowed") is True),
        "crop_completeness_guard_selection_blocked_card_count": sum(1 for card in cards if card.get("crop_completeness_guard_selection_blocked")),
        "crop_selection_blocked_by_completeness_guard_count": sum(1 for card in cards if card.get("crop_selection_blocked_by_completeness_guard")),
        "crop_completeness_guard_review_required_card_count": sum(1 for card in cards if card.get("crop_completeness_status") == "REVIEW_REQUIRED"),
        "crop_completeness_guard_pass_card_count": sum(1 for card in cards if card.get("crop_completeness_status") == "PASS"),
        "table_full_region_recovery_available_card_count": sum(1 for card in cards if card.get("table_full_region_recovery_available")),
        "table_full_region_recovery_ready_card_count": sum(1 for card in cards if card.get("table_full_region_recovery_ready")),
        "table_full_region_recovery_used_for_crop_card_count": sum(1 for card in cards if card.get("table_full_region_recovery_used_for_crop")),
        "table_full_region_recovery_crop_rejected_card_count": sum(1 for card in cards if card.get("table_full_region_recovery_crop_rejected")),
        "table_full_region_recovery_too_page_like_card_count": sum(1 for card in cards if card.get("table_full_region_recovery_too_page_like")),
        "table_bbox_resolver_available_card_count": sum(1 for card in cards if card.get("table_bbox_resolver_available")),
        "table_bbox_resolver_crop_ready_card_count": sum(1 for card in cards if card.get("table_bbox_resolver_crop_ready")),
        "table_bbox_resolver_crop_used_card_count": sum(1 for card in cards if card.get("table_bbox_resolver_used_for_crop")),
        "table_bbox_resolver_crop_rejected_card_count": sum(1 for card in cards if card.get("table_bbox_resolver_crop_rejected")),
        "table_bbox_resolver_low_specificity_card_count": sum(1 for card in cards if "table_region_bbox_low_specificity" in (card.get("review_flags") or [])),
        "page_morphology_selected_card_count": sum(1 for card in cards if card.get("selected_morphology_scope") == "page"),
        "resolved_image_input_card_count": sum(1 for card in cards if card.get("resolved_image_path")),
        "ocr_clustering_fallback_card_count": sum(1 for card in cards if card.get("ocr_geometry_inference_method") == "normalizer_row_column_fallback"),
        "bbox_clustering_card_count": sum(1 for card in cards if card.get("ocr_geometry_inference_method") == "ocr_bbox_row_column_clustering"),
        "review_required_card_count": sum(1 for card in cards if card.get("review_required")),
        "merged_cell_candidate_count": sum(int(card.get("merged_cell_candidate_count") or 0) for card in cards),
        "part_number_table_card_count": sum(1 for card in cards if card.get("domain_validation", {}).get("part_number_count", 0) > 0),
        "answer_permission_count": answer_permission_count,
        "can_answer_directly_count": can_answer_directly_count,
        "can_prove_claims_count": can_prove_claims_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "retrieval_only_answer_allowed_count": 0,
        "postgres_write_attempt_count": sum(int(card.get("postgres_write_attempt_count") or 0) for card in cards),
        "qdrant_write_attempt_count": sum(int(card.get("qdrant_write_attempt_count") or 0) for card in cards),
        "opensearch_write_attempt_count": sum(int(card.get("opensearch_write_attempt_count") or 0) for card in cards),
        "unsafe_geometry_card_count": unsafe_geometry_card_count,
        "quality_status": "UNKNOWN",
        "quality_fail_reasons": [],
    }


def evaluate_quality(summary: Mapping[str, Any], thresholds: Mapping[str, Any]) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    if summary.get("source_quality_status") not in {"PASS", "OK", "UNKNOWN"} and thresholds.get("require_source_quality_pass"):
        reasons.append("source quality status is not PASS")
    if int(summary.get("table_geometry_card_count") or 0) < int(thresholds.get("min_table_geometry_cards", 1)):
        reasons.append("table_geometry_card_count below minimum")
    if int(summary.get("cell_record_count") or 0) < int(thresholds.get("min_cell_records", 0)):
        reasons.append("cell_record_count below minimum")
    if int(summary.get("row_record_count") or 0) < int(thresholds.get("min_row_records", 0)):
        reasons.append("row_record_count below minimum")
    if thresholds.get("require_image_line_detection") and int(summary.get("image_line_detection_card_count") or 0) <= 0:
        reasons.append("image line detection required but no cards have image line detection")
    if int(summary.get("image_line_detection_card_count") or 0) < int(thresholds.get("min_image_line_detection_cards", 0)):
        reasons.append("image_line_detection_card_count below minimum")
    if thresholds.get("require_table_image_resolver_quality_pass") and summary.get("table_image_resolver_quality_status") not in {"PASS", "OK"}:
        reasons.append("table image resolver quality status is not PASS")
    if thresholds.get("require_table_bbox_resolver_quality_pass") and summary.get("table_bbox_resolver_quality_status") not in {"PASS", "OK"}:
        reasons.append("table bbox resolver quality status is not PASS")
    if thresholds.get("require_table_crop_completeness_guard_quality_pass") and summary.get("table_crop_completeness_guard_quality_status") not in {"PASS", "OK"}:
        reasons.append("table crop completeness guard quality status is not PASS")
    if thresholds.get("require_table_full_region_recovery_quality_pass") and summary.get("table_full_region_recovery_quality_status") not in {"PASS", "OK"}:
        reasons.append("table full region recovery quality status is not PASS")
    if int(summary.get("table_full_region_recovery_used_for_crop_card_count") or 0) < int(thresholds.get("min_table_full_region_recovery_used_for_crop_cards", 0)):
        reasons.append("table_full_region_recovery_used_for_crop_card_count below minimum")
    if int(summary.get("table_region_crop_available_card_count") or 0) < int(thresholds.get("min_table_region_crop_available_cards", 0)):
        reasons.append("table_region_crop_available_card_count below minimum")
    if int(summary.get("table_region_crop_applied_card_count") or 0) < int(thresholds.get("min_table_region_crop_applied_cards", 0)):
        reasons.append("table_region_crop_applied_card_count below minimum")
    if int(summary.get("unsafe_geometry_card_count") or 0) > int(thresholds.get("max_unsafe_geometry_cards", 0)):
        reasons.append("unsafe_geometry_card_count above maximum")
    if int(summary.get("answer_permission_count") or 0) > int(thresholds.get("max_answer_permission_count", 0)):
        reasons.append("answer_permission_count above maximum")
    if int(summary.get("can_answer_directly_count") or 0) > 0 and thresholds.get("require_no_answer_permission"):
        reasons.append("can_answer_directly_count nonzero")
    if int(summary.get("can_prove_claims_count") or 0) > 0 and thresholds.get("require_no_answer_permission"):
        reasons.append("can_prove_claims_count nonzero")
    if int(summary.get("source_truth_mutation_allowed_count") or 0) > int(thresholds.get("max_source_truth_mutation_allowed", 0)):
        reasons.append("source_truth_mutation_allowed_count above maximum")
    if int(summary.get("postgres_write_attempt_count") or 0) != 0:
        reasons.append("postgres_write_attempt_count nonzero")
    if int(summary.get("qdrant_write_attempt_count") or 0) != 0:
        reasons.append("qdrant_write_attempt_count nonzero")
    if int(summary.get("opensearch_write_attempt_count") or 0) != 0:
        reasons.append("opensearch_write_attempt_count nonzero")
    return ("FAIL" if reasons else "PASS"), reasons


def build_report(
    table_cell_normalizer_path: Path,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    image_root: Optional[Path] = None,
    max_image_pages: int = 50,
    thresholds: Optional[Mapping[str, Any]] = None,
    quality: bool = False,
    table_image_resolver_path: Optional[Path] = None,
    table_bbox_resolver_path: Optional[Path] = None,
    table_crop_completeness_guard_path: Optional[Path] = None,
    table_full_region_recovery_path: Optional[Path] = None,
    route_dispatch_processor_contract: Optional[Path] = None,
) -> Dict[str, Any]:
    thresholds = dict(thresholds or {})
    payload = read_json(table_cell_normalizer_path)
    source_status = str(payload.get("quality_status") or payload.get("status") or "UNKNOWN") if isinstance(payload, Mapping) else "UNKNOWN"
    records = extract_table_records(payload)
    resolver_map, resolver_status = load_table_image_resolver_cards(table_image_resolver_path)
    bbox_resolver_map, bbox_resolver_status = load_table_bbox_resolver_cards(table_bbox_resolver_path)
    crop_guard_map, crop_guard_status = load_table_crop_completeness_guard_cards(table_crop_completeness_guard_path)
    full_region_recovery_map, full_region_recovery_status = load_table_full_region_recovery_cards(table_full_region_recovery_path)
    route_dispatch_contract = None
    route_dispatch_contract_quality_status = None
    if route_dispatch_processor_contract:
        route_dispatch_payload = read_json(route_dispatch_processor_contract)
        route_dispatch_contract_quality_status = route_dispatch_payload.get("quality_status") or (route_dispatch_payload.get("summary") or {}).get("quality_status")
        route_dispatch_contract = load_route_dispatch_processor_contract(route_dispatch_processor_contract)
    route_dispatch_stats: Dict[str, int] = {}

    cards = build_table_geometry_cards(
        records,
        image_root=image_root,
        max_image_pages=max_image_pages,
        table_image_resolver_map=resolver_map,
        table_bbox_resolver_map=bbox_resolver_map,
        table_crop_completeness_guard_map=crop_guard_map,
        table_full_region_recovery_map=full_region_recovery_map,
        route_dispatch_contract=route_dispatch_contract,
        route_dispatch_stats=route_dispatch_stats,
    )
    summary = compute_summary(cards, records, source_status)
    summary["table_image_resolver_quality_status"] = resolver_status
    summary["table_image_resolver_card_count"] = len(resolver_map)
    summary["table_bbox_resolver_quality_status"] = bbox_resolver_status
    summary["table_bbox_resolver_card_count"] = len(bbox_resolver_map)
    summary["table_crop_completeness_guard_quality_status"] = crop_guard_status
    summary["table_crop_completeness_guard_card_count"] = len(crop_guard_map)
    summary["table_full_region_recovery_quality_status"] = full_region_recovery_status
    summary["table_full_region_recovery_card_count"] = len(full_region_recovery_map)
    summary["route_dispatch_processor_contract_available"] = bool(route_dispatch_processor_contract)
    summary["route_dispatch_processor_contract_path"] = str(route_dispatch_processor_contract) if route_dispatch_processor_contract else None
    summary["route_dispatch_processor_contract_quality_status"] = route_dispatch_contract_quality_status
    summary["table_route_allowed_input_group_count"] = int(route_dispatch_stats.get("table_route_allowed_input_group_count") or 0)
    summary["table_route_blocked_input_group_count"] = int(route_dispatch_stats.get("table_route_blocked_input_group_count") or 0)
    quality_status, fail_reasons = evaluate_quality(summary, thresholds)
    if quality:
        summary["quality_status"] = quality_status
        summary["quality_fail_reasons"] = fail_reasons
    else:
        summary["quality_status"] = "NOT_EVALUATED"
        summary["quality_fail_reasons"] = []
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "status": summary["status"] if summary["quality_status"] != "FAIL" else "TABLE_LINE_GEOMETRY_NOT_READY",
        "quality_status": summary["quality_status"],
        "source_artifacts": {
            "table_cell_normalizer": str(table_cell_normalizer_path),
            "table_image_resolver": str(table_image_resolver_path) if table_image_resolver_path else None,
            "table_bbox_resolver": str(table_bbox_resolver_path) if table_bbox_resolver_path else None,
            "table_crop_completeness_guard": str(table_crop_completeness_guard_path) if table_crop_completeness_guard_path else None,
            "table_full_region_recovery": str(table_full_region_recovery_path) if table_full_region_recovery_path else None,
        },
        "summary": summary,
        "safety_contract": SAFETY_CONTRACT,
        "table_geometry_cards": cards,
    }
    write_outputs(output_dir, report)
    return report


def write_outputs(output_dir: Path, report: Mapping[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_table_line_geometry_v1.json"
    write_json(report_path, report)
    cards = report.get("table_geometry_cards") or []
    write_jsonl(output_dir / "trace_net_table_line_geometry_v1_cards.jsonl", cards)  # type: ignore[arg-type]
    write_json(output_dir / "trace_net_table_line_geometry_v1_summary.json", report.get("summary") or {})
    quality_payload = {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "status": report.get("quality_status"),
        "quality_status": report.get("quality_status"),
        "summary": report.get("summary") or {},
        "checks": quality_checks(report.get("summary") or {}),
    }
    write_json(output_dir / "trace_net_table_line_geometry_v1_quality.json", quality_payload)
    manifest = {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": utc_now_iso(),
        "artifacts": {
            "report": str(report_path),
            "cards_jsonl": str(output_dir / "trace_net_table_line_geometry_v1_cards.jsonl"),
            "summary": str(output_dir / "trace_net_table_line_geometry_v1_summary.json"),
            "quality": str(output_dir / "trace_net_table_line_geometry_v1_quality.json"),
        },
        "safety_contract": SAFETY_CONTRACT,
    }
    write_json(output_dir / "trace_net_table_line_geometry_v1_manifest.json", manifest)


def quality_checks(summary: Mapping[str, Any]) -> Dict[str, bool]:
    return {
        "schema_version_ok": summary.get("schema_version") == SCHEMA_VERSION,
        "table_geometry_cards_present": int(summary.get("table_geometry_card_count") or 0) > 0,
        "unsafe_geometry_cards_zero": int(summary.get("unsafe_geometry_card_count") or 0) == 0,
        "answer_permission_zero": int(summary.get("answer_permission_count") or 0) == 0,
        "can_answer_directly_zero": int(summary.get("can_answer_directly_count") or 0) == 0,
        "can_prove_claims_zero": int(summary.get("can_prove_claims_count") or 0) == 0,
        "source_truth_mutation_allowed_zero": int(summary.get("source_truth_mutation_allowed_count") or 0) == 0,
        "table_full_region_recovery_consistent": int(summary.get("table_full_region_recovery_used_for_crop_card_count") or 0) <= int(summary.get("table_full_region_recovery_ready_card_count") or 0),
        "write_attempts_zero": int(summary.get("postgres_write_attempt_count") or 0) == 0
        and int(summary.get("qdrant_write_attempt_count") or 0) == 0
        and int(summary.get("opensearch_write_attempt_count") or 0) == 0,
    }


def thresholds_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "min_table_geometry_cards": args.min_table_geometry_cards,
        "min_cell_records": args.min_cell_records,
        "min_row_records": args.min_row_records,
        "max_unsafe_geometry_cards": args.max_unsafe_geometry_cards,
        "max_answer_permission_count": args.max_answer_permission_count,
        "max_source_truth_mutation_allowed": args.max_source_truth_mutation_allowed,
        "require_no_answer_permission": args.require_no_answer_permission,
        "require_source_quality_pass": args.require_source_quality_pass,
        "require_image_line_detection": args.require_image_line_detection,
        "min_image_line_detection_cards": args.min_image_line_detection_cards,
        "require_table_image_resolver_quality_pass": args.require_table_image_resolver_quality_pass,
        "require_table_bbox_resolver_quality_pass": args.require_table_bbox_resolver_quality_pass,
        "require_table_crop_completeness_guard_quality_pass": args.require_table_crop_completeness_guard_quality_pass,
        "require_table_full_region_recovery_quality_pass": args.require_table_full_region_recovery_quality_pass,
        "min_table_full_region_recovery_used_for_crop_cards": args.min_table_full_region_recovery_used_for_crop_cards,
        "min_table_region_crop_available_cards": args.min_table_region_crop_available_cards,
        "min_table_region_crop_applied_cards": args.min_table_region_crop_applied_cards,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Table Line Geometry v1 artifacts.")
    parser.add_argument("--table-cell-normalizer", required=True, type=Path)
    parser.add_argument("--table-image-resolver", type=Path, default=None)
    parser.add_argument("--table-bbox-resolver", type=Path, default=None)
    parser.add_argument("--table-crop-completeness-guard", type=Path, default=None)
    parser.add_argument("--table-full-region-recovery", type=Path, default=None)
    parser.add_argument("--route-dispatch-processor-contract", type=Path, default=None)
    parser.add_argument("--image-root", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-image-pages", type=int, default=50)
    parser.add_argument("--min-table-geometry-cards", type=int, default=1)
    parser.add_argument("--min-cell-records", type=int, default=0)
    parser.add_argument("--min-row-records", type=int, default=0)
    parser.add_argument("--min-image-line-detection-cards", type=int, default=0)
    parser.add_argument("--min-table-region-crop-available-cards", type=int, default=0)
    parser.add_argument("--min-table-region-crop-applied-cards", type=int, default=0)
    parser.add_argument("--min-table-full-region-recovery-used-for-crop-cards", type=int, default=0)
    parser.add_argument("--max-unsafe-geometry-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-table-image-resolver-quality-pass", action="store_true")
    parser.add_argument("--require-table-bbox-resolver-quality-pass", action="store_true")
    parser.add_argument("--require-table-crop-completeness-guard-quality-pass", action="store_true")
    parser.add_argument("--require-table-full-region-recovery-quality-pass", action="store_true")
    parser.add_argument("--require-image-line-detection", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = build_report(
        table_cell_normalizer_path=args.table_cell_normalizer,
        output_dir=args.output_dir,
        image_root=args.image_root,
        max_image_pages=args.max_image_pages,
        thresholds=thresholds_from_args(args),
        quality=args.quality,
        table_image_resolver_path=args.table_image_resolver,
        table_bbox_resolver_path=args.table_bbox_resolver,
        table_crop_completeness_guard_path=args.table_crop_completeness_guard,
        table_full_region_recovery_path=args.table_full_region_recovery,
        route_dispatch_processor_contract=args.route_dispatch_processor_contract,
    )
    summary = report.get("summary") or {}
    print("TRACE-Net Table Line Geometry v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in (
        "table_geometry_card_count",
        "cell_record_count",
        "row_record_count",
        "image_line_detection_card_count",
        "image_morphology_card_count",
        "table_region_crop_available_card_count",
        "table_region_crop_applied_card_count",
        "table_region_crop_selected_card_count",
        "margin_expansion_candidate_card_count",
        "margin_expansion_candidate_evaluation_count",
        "margin_expansion_selected_card_count",
        "margin_expansion_selected_grid_card_count",
        "crop_completeness_guard_available_card_count",
        "crop_completeness_guard_selection_allowed_card_count",
        "crop_completeness_guard_selection_blocked_card_count",
        "crop_selection_blocked_by_completeness_guard_count",
        "crop_completeness_guard_review_required_card_count",
        "crop_completeness_guard_pass_card_count",
        "table_crop_completeness_guard_quality_status",
        "table_crop_completeness_guard_card_count",
        "table_full_region_recovery_quality_status",
        "table_full_region_recovery_card_count",
        "table_full_region_recovery_available_card_count",
        "table_full_region_recovery_ready_card_count",
        "table_full_region_recovery_used_for_crop_card_count",
        "table_full_region_recovery_crop_rejected_card_count",
        "table_full_region_recovery_too_page_like_card_count",
        "table_bbox_resolver_card_count",
        "table_bbox_resolver_quality_status",
        "table_bbox_resolver_crop_ready_card_count",
        "table_bbox_resolver_crop_used_card_count",
        "table_bbox_resolver_crop_rejected_card_count",
        "table_bbox_resolver_low_specificity_card_count",
        "page_morphology_selected_card_count",
        "ocr_clustering_fallback_card_count",
        "merged_cell_candidate_count",
        "review_required_card_count",
        "unsafe_geometry_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {args.output_dir / 'trace_net_table_line_geometry_v1.json'}")
    print(f" quality_path: {args.output_dir / 'trace_net_table_line_geometry_v1_quality.json'}")
    return 1 if report.get("quality_status") == "FAIL" else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
