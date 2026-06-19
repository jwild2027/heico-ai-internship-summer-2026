"""TRACE-Net Table Paddle-Style BBox Resolver v1.

PaddleOCR-style design, adapted to TRACE-Net:
- collect many table bbox candidates,
- score them by geometry/table-structure signals,
- reject page-like/tiny/blocked candidates,
- select one bbox per table-route page/table group.

This is read-only. It does not run PaddleOCR, write databases, answer questions,
or mutate source truth.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:
    from tiff.trace_net_route_dispatch_contract_loader_v1 import load_route_dispatch_processor_contract
except Exception:  # pragma: no cover
    load_route_dispatch_processor_contract = None  # type: ignore


SCHEMA_VERSION = "trace_net_table_paddle_style_bbox_resolver_v1"
QUALITY_SCHEMA_VERSION = f"{SCHEMA_VERSION}_quality"
STATUS_BUILT = "TRACE_NET_TABLE_PADDLE_STYLE_BBOX_RESOLVER_BUILT"
STATUS_NOT_READY = "TRACE_NET_TABLE_PADDLE_STYLE_BBOX_RESOLVER_NOT_READY"

DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/table_paddle_style_bbox_resolver")
DEFAULT_REPORT_FILE = "trace_net_table_paddle_style_bbox_resolver_v1.json"
DEFAULT_QUALITY_FILE = "trace_net_table_paddle_style_bbox_resolver_v1_quality.json"

DEFAULT_TABLE_BBOX_RESOLVER = Path("local_data/organization/trace_net/table_bbox_resolver/trace_net_table_bbox_resolver_v1.json")
DEFAULT_TABLE_FULL_REGION_RECOVERY = Path("local_data/organization/trace_net/table_full_region_recovery/trace_net_table_full_region_recovery_v1.json")
DEFAULT_TABLE_CROP_COMPLETENESS_GUARD = Path("local_data/organization/trace_net/table_crop_completeness_guard/trace_net_table_crop_completeness_guard_v1.json")
DEFAULT_TABLE_LINE_GEOMETRY = Path("local_data/organization/trace_net/table_line_geometry/trace_net_table_line_geometry_v1.json")
DEFAULT_ROUTE_CONTRACT = Path("local_data/organization/trace_net/route_dispatch_processor_contract/trace_net_route_dispatch_processor_contract_v1.json")

BBOX_KEYS = {
    "bbox",
    "bounding_box",
    "boundingbox",
    "table_bbox",
    "resolved_bbox",
    "selected_bbox",
    "crop_bbox",
    "table_crop_bbox",
    "region_bbox",
    "full_region_bbox",
    "recovered_bbox",
    "line_bbox",
    "grid_bbox",
    "ocr_bbox",
    "cell_bbox",
    "page_bbox",
}

BAD_BBOX_KEY_HINTS = {
    "page_bbox",
    "image_bbox",
    "full_page_bbox",
}


@dataclass(frozen=True)
class Thresholds:
    min_resolver_cards: int = 1
    min_selected_bbox_cards: int = 1
    max_route_blocked_cards: int = 0
    max_unsafe_resolver_cards: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_route_contract_quality_pass: bool = True
    require_no_answer_permission: bool = True


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")


def safe_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return safe_text(value).lower() in {"true", "1", "yes", "y", "on", "allowed", "pass", "ready"}


def safe_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(value)
    except Exception:
        return 0


def safe_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def clip(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def quality_status(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    quality = payload.get("quality") if isinstance(payload.get("quality"), Mapping) else {}
    return safe_text(
        payload.get("quality_status")
        or quality.get("status")
        or quality.get("quality_status")
        or summary.get("quality_status")
        or payload.get("status")
        or "UNKNOWN"
    )


def page_id_from_record(record: Mapping[str, Any]) -> str:
    for key in ("page_id", "source_page_id", "group_page_id", "document_page_id"):
        value = record.get(key)
        if value:
            return safe_text(value)
    trace = record.get("traceability")
    if isinstance(trace, Mapping) and trace.get("page_id"):
        return safe_text(trace.get("page_id"))
    return ""


def table_id_from_record(record: Mapping[str, Any], page_id: str = "") -> str:
    for key in ("table_id", "normalized_table_id", "table_key", "artifact_key", "record_id"):
        value = record.get(key)
        if value:
            return safe_text(value)
    return f"table__{page_id or 'unknown'}"


def record_key(record: Mapping[str, Any]) -> tuple[str, str]:
    page_id = page_id_from_record(record)
    return (page_id, table_id_from_record(record, page_id))


def load_records(path: Path, preferred_keys: Sequence[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.exists():
        return [], {"quality_status": "MISSING", "missing_artifact": True, "path": str(path)}
    payload = read_json(path)
    if not isinstance(payload, Mapping):
        return [], {"quality_status": "UNKNOWN", "path": str(path)}
    for key in preferred_keys:
        raw = payload.get(key)
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
            return [dict(item) for item in raw if isinstance(item, Mapping)], dict(payload)
    raw = payload.get("records") or payload.get("cards") or []
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        return [dict(item) for item in raw if isinstance(item, Mapping)], dict(payload)
    return [], dict(payload)


def bbox_from_mapping(value: Mapping[str, Any]) -> list[float] | None:
    keys = set(value.keys())
    if {"x", "y", "width", "height"}.issubset(keys):
        x = safe_float(value.get("x"))
        y = safe_float(value.get("y"))
        w = safe_float(value.get("width"))
        h = safe_float(value.get("height"))
        if w > 0 and h > 0:
            return [x, y, x + w, y + h]
    if {"left", "top", "width", "height"}.issubset(keys):
        x = safe_float(value.get("left"))
        y = safe_float(value.get("top"))
        w = safe_float(value.get("width"))
        h = safe_float(value.get("height"))
        if w > 0 and h > 0:
            return [x, y, x + w, y + h]
    if {"x0", "y0", "x1", "y1"}.issubset(keys):
        return [safe_float(value.get("x0")), safe_float(value.get("y0")), safe_float(value.get("x1")), safe_float(value.get("y1"))]
    if {"left", "top", "right", "bottom"}.issubset(keys):
        return [safe_float(value.get("left")), safe_float(value.get("top")), safe_float(value.get("right")), safe_float(value.get("bottom"))]
    if {"xmin", "ymin", "xmax", "ymax"}.issubset(keys):
        return [safe_float(value.get("xmin")), safe_float(value.get("ymin")), safe_float(value.get("xmax")), safe_float(value.get("ymax"))]
    return None


def bbox_from_sequence(value: Sequence[Any]) -> list[float] | None:
    if len(value) == 4 and all(isinstance(item, (int, float, str)) for item in value):
        vals = [safe_float(item) for item in value]
        x0, y0, a, b = vals
        # Treat as x,y,w,h if a/b look like dimensions from origin.
        if a > 0 and b > 0 and (a <= x0 or b <= y0):
            return [x0, y0, x0 + a, y0 + b]
        return [x0, y0, a, b]
    if len(value) >= 4 and all(isinstance(item, Mapping) for item in value):
        xs: list[float] = []
        ys: list[float] = []
        for point in value:
            x = point.get("x") if isinstance(point, Mapping) else None
            y = point.get("y") if isinstance(point, Mapping) else None
            if x is not None and y is not None:
                xs.append(safe_float(x))
                ys.append(safe_float(y))
        if xs and ys:
            return [min(xs), min(ys), max(xs), max(ys)]
    return None


def normalize_bbox(raw: Any) -> list[float] | None:
    bbox: list[float] | None = None
    if isinstance(raw, Mapping):
        bbox = bbox_from_mapping(raw)
        if bbox is None:
            for key in ("bbox", "bounding_box", "boundingBox", "BoundingBox", "vertices", "normalizedVertices"):
                value = raw.get(key)
                if isinstance(value, Mapping):
                    bbox = bbox_from_mapping(value)
                elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                    bbox = bbox_from_sequence(value)
                if bbox:
                    break
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        bbox = bbox_from_sequence(raw)

    if bbox is None:
        return None

    x0, y0, x1, y1 = [safe_float(v) for v in bbox]
    left, right = sorted([x0, x1])
    top, bottom = sorted([y0, y1])
    if right <= left or bottom <= top:
        return None
    return [left, top, right, bottom]


def bbox_area(bbox: Sequence[float]) -> float:
    return max(0.0, safe_float(bbox[2]) - safe_float(bbox[0])) * max(0.0, safe_float(bbox[3]) - safe_float(bbox[1]))


def bbox_is_normalized(bbox: Sequence[float]) -> bool:
    return all(0.0 <= safe_float(v) <= 1.25 for v in bbox)


def bbox_shape_scores(bbox: Sequence[float]) -> dict[str, Any]:
    width = max(0.0, safe_float(bbox[2]) - safe_float(bbox[0]))
    height = max(0.0, safe_float(bbox[3]) - safe_float(bbox[1]))
    area = width * height
    normalized = bbox_is_normalized(bbox)

    tiny = False
    page_like = False
    aspect = width / height if height > 0 else 0.0

    if normalized:
        tiny = area < 0.005 or width < 0.05 or height < 0.02
        page_like = area > 0.88 or (width > 0.96 and height > 0.82)
        area_score = 1.0
        if area < 0.015:
            area_score -= 0.45
        if area > 0.78:
            area_score -= 0.35
        if page_like:
            area_score -= 0.35
        if tiny:
            area_score -= 0.50
    else:
        tiny = area < 100.0 or width < 10.0 or height < 6.0
        # Pixel-space page-like needs page size, so only mark extreme full-page-looking ratios.
        page_like = False
        area_score = 0.80 if not tiny else 0.20

    aspect_score = 1.0
    if aspect <= 0:
        aspect_score = 0.0
    elif aspect < 0.25 or aspect > 20:
        aspect_score = 0.35
    elif aspect < 0.5 or aspect > 12:
        aspect_score = 0.65

    return {
        "bbox_width": round(width, 6),
        "bbox_height": round(height, 6),
        "bbox_area": round(area, 6),
        "bbox_aspect_ratio": round(aspect, 6),
        "bbox_is_normalized": normalized,
        "bbox_tiny": tiny,
        "bbox_page_like": page_like,
        "bbox_area_score": round(clip(area_score), 6),
        "bbox_aspect_score": round(clip(aspect_score), 6),
    }


def extract_bboxes_from_obj(obj: Any, *, path: str = "", depth: int = 0, max_depth: int = 4) -> list[tuple[str, list[float]]]:
    if depth > max_depth:
        return []
    found: list[tuple[str, list[float]]] = []
    if isinstance(obj, Mapping):
        direct = normalize_bbox(obj)
        if direct and any(hint in path.lower() or hint in str(k).lower() for hint in BBOX_KEYS for k in obj.keys()):
            found.append((path or "mapping_bbox", direct))
        for key, value in obj.items():
            key_text = safe_text(key)
            next_path = f"{path}.{key_text}" if path else key_text
            key_lower = key_text.lower()
            if key_lower in BBOX_KEYS or key_lower.endswith("_bbox") or "bounding" in key_lower or "polygon" in key_lower:
                bbox = normalize_bbox(value)
                if bbox:
                    found.append((next_path, bbox))
            if isinstance(value, (Mapping, list, tuple)):
                found.extend(extract_bboxes_from_obj(value, path=next_path, depth=depth + 1, max_depth=max_depth))
    elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        # For lists of cell/word records, recurse a bounded amount.
        for idx, item in enumerate(list(obj)[:200]):
            if isinstance(item, Mapping):
                found.extend(extract_bboxes_from_obj(item, path=f"{path}[{idx}]", depth=depth + 1, max_depth=max_depth))
    return found


def union_bboxes(bboxes: Sequence[Sequence[float]]) -> list[float] | None:
    clean = [normalize_bbox(bbox) for bbox in bboxes]
    clean = [bbox for bbox in clean if bbox]
    if not clean:
        return None
    return [
        min(bbox[0] for bbox in clean),
        min(bbox[1] for bbox in clean),
        max(bbox[2] for bbox in clean),
        max(bbox[3] for bbox in clean),
    ]


def collect_nested_bboxes(record: Mapping[str, Any], keys: Sequence[str]) -> list[list[float]]:
    found: list[list[float]] = []
    for key in keys:
        value = record.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for item in value:
                bbox = normalize_bbox(item)
                if bbox:
                    found.append(bbox)
                elif isinstance(item, Mapping):
                    for _, nested in extract_bboxes_from_obj(item, max_depth=2):
                        found.append(nested)
    return found


def source_prior(source_name: str, bbox_path: str) -> float:
    source = source_name.lower()
    path = bbox_path.lower()
    score = 0.45
    if "full_region" in source:
        score += 0.16
    if "bbox_resolver" in source:
        score += 0.12
    if "crop_guard" in source:
        score += 0.10
    if "line_geometry" in source:
        score += 0.14
    if "selected" in path or "resolved" in path or "used" in path:
        score += 0.14
    if "rejected" in path or "page_bbox" in path:
        score -= 0.18
    if any(hint in path for hint in BAD_BBOX_KEY_HINTS):
        score -= 0.25
    return clip(score)


def table_signal_score(record: Mapping[str, Any]) -> float:
    horizontal = max(
        safe_int(record.get("horizontal_line_count")),
        safe_int(record.get("ink_horizontal_line_count")),
        safe_int(record.get("detected_horizontal_line_count")),
    )
    vertical = max(
        safe_int(record.get("vertical_line_count")),
        safe_int(record.get("ink_vertical_line_count")),
        safe_int(record.get("detected_vertical_line_count")),
    )
    intersections = max(
        safe_int(record.get("intersection_count")),
        safe_int(record.get("ink_intersection_count")),
        safe_int(record.get("grid_intersection_count")),
    )
    rows = max(safe_int(record.get("row_count")), safe_int(record.get("row_record_count")), safe_int(record.get("detected_row_count")))
    cols = max(safe_int(record.get("column_count")), safe_int(record.get("col_count")), safe_int(record.get("detected_column_count")))
    cells = max(safe_int(record.get("cell_count")), safe_int(record.get("cell_record_count")), safe_int(record.get("detected_cell_count")))

    score = 0.0
    score += min(0.22, horizontal * 0.012)
    score += min(0.22, vertical * 0.015)
    score += min(0.24, intersections * 0.002)
    score += min(0.14, rows * 0.01)
    score += min(0.14, cols * 0.018)
    score += min(0.18, cells * 0.004)
    return clip(score)


def guard_penalty(record: Mapping[str, Any], bbox_path: str) -> tuple[float, list[str]]:
    penalty = 0.0
    reasons: list[str] = []
    text = " ".join(str(item).lower() for item in [bbox_path] + list(record.keys()))

    if "rejected" in text:
        penalty += 0.25
        reasons.append("candidate_path_indicates_rejected")
    if safe_bool(record.get("crop_selection_blocked_by_completeness_guard")):
        penalty += 0.20
        reasons.append("source_record_crop_blocked_by_completeness_guard")
    if safe_bool(record.get("table_full_region_recovery_too_page_like")):
        penalty += 0.18
        reasons.append("source_record_too_page_like")
    if safe_bool(record.get("table_bbox_resolver_low_specificity")):
        penalty += 0.15
        reasons.append("source_record_low_specificity")
    if safe_bool(record.get("unsafe_geometry_card")):
        penalty += 0.40
        reasons.append("source_record_unsafe_geometry")
    return clip(penalty), reasons


def apply_candidate_context_penalties(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Apply page-relative penalties after all candidates for one table are known.

    The first pass can detect normalized page-like boxes. This pass detects
    pixel-space page-like boxes by comparing candidates against the largest
    candidate extent on the same page/table.
    """
    output = [dict(candidate) for candidate in candidates]
    if not output:
        return output

    max_right = max(safe_float((candidate.get("bbox") or [0, 0, 0, 0])[2]) for candidate in output)
    max_bottom = max(safe_float((candidate.get("bbox") or [0, 0, 0, 0])[3]) for candidate in output)
    max_area = max(bbox_area(candidate.get("bbox") or [0, 0, 0, 0]) for candidate in output)

    if max_right <= 0 or max_bottom <= 0 or max_area <= 0:
        return output

    for candidate in output:
        bbox = candidate.get("bbox") or [0, 0, 0, 0]
        if bbox_is_normalized(bbox):
            continue

        width = max(0.0, safe_float(bbox[2]) - safe_float(bbox[0]))
        height = max(0.0, safe_float(bbox[3]) - safe_float(bbox[1]))
        area = width * height
        width_ratio = width / max_right if max_right else 0.0
        height_ratio = height / max_bottom if max_bottom else 0.0
        area_ratio = area / max_area if max_area else 0.0
        touches_top = safe_float(bbox[1]) <= max(3.0, max_bottom * 0.015)
        touches_left = safe_float(bbox[0]) <= max(3.0, max_right * 0.015)

        page_like = (
            area_ratio >= 0.82
            or (width_ratio >= 0.90 and height_ratio >= 0.82)
            or (touches_top and touches_left and width_ratio >= 0.82 and height_ratio >= 0.70)
        )

        if page_like:
            reasons = set(candidate.get("rejection_reasons") or [])
            reasons.add("bbox_too_page_like")
            reasons.add("pixel_space_candidate_too_page_like_relative_to_page")
            candidate["rejection_reasons"] = sorted(reasons)
            candidate["bbox_page_like"] = True
            candidate["pixel_page_like_width_ratio"] = round(width_ratio, 6)
            candidate["pixel_page_like_height_ratio"] = round(height_ratio, 6)
            candidate["pixel_page_like_area_ratio"] = round(area_ratio, 6)
            candidate["score"] = round(clip(safe_float(candidate.get("score")) - 0.35), 6)

        source_name = str(candidate.get("source_name") or "")

        # Prefer actual bbox-resolver/full-region candidates over line-geometry
        # page unions when they are not rejected. Paddle-style table extraction
        # should trust table-region candidates before full-page geometry unions.
        if not candidate.get("rejection_reasons"):
            if source_name in {"table_bbox_resolver", "table_full_region_recovery", "table_crop_completeness_guard"}:
                candidate["score"] = round(clip(safe_float(candidate.get("score")) + 0.22), 6)

        if source_name == "table_line_geometry":
            if page_like:
                candidate["score"] = round(clip(safe_float(candidate.get("score")) - 0.25), 6)
            else:
                candidate["score"] = round(clip(safe_float(candidate.get("score")) - 0.08), 6)

    return output


def build_candidate(
    *,
    source_name: str,
    source_record: Mapping[str, Any],
    bbox_path: str,
    bbox: Sequence[float],
    page_id: str,
    table_id: str,
    candidate_index: int,
) -> dict[str, Any]:
    shape = bbox_shape_scores(bbox)
    source_score = source_prior(source_name, bbox_path)
    signal_score = table_signal_score(source_record)
    penalty, penalty_reasons = guard_penalty(source_record, bbox_path)

    score = (
        0.34 * source_score
        + 0.26 * safe_float(shape["bbox_area_score"])
        + 0.16 * safe_float(shape["bbox_aspect_score"])
        + 0.24 * signal_score
        - 0.35 * penalty
    )
    score = clip(score)

    rejection_reasons: list[str] = []
    if shape["bbox_tiny"]:
        rejection_reasons.append("bbox_too_tiny")
    if shape["bbox_page_like"]:
        rejection_reasons.append("bbox_too_page_like")
    if penalty >= 0.40:
        rejection_reasons.append("source_record_high_penalty")
    rejection_reasons.extend(penalty_reasons)

    return {
        "candidate_id": f"{page_id or 'unknown'}__{table_id or 'table'}__{source_name}__{candidate_index:04d}",
        "source_name": source_name,
        "source_bbox_path": bbox_path,
        "page_id": page_id,
        "table_id": table_id,
        "bbox": [round(safe_float(v), 6) for v in bbox],
        "score": round(score, 6),
        "source_prior_score": round(source_score, 6),
        "table_signal_score": round(signal_score, 6),
        "guard_penalty": round(penalty, 6),
        "rejection_reasons": sorted(set(rejection_reasons)),
        "candidate_selected": False,
        **shape,
    }


def candidates_from_record(source_name: str, record: Mapping[str, Any]) -> list[dict[str, Any]]:
    page_id = page_id_from_record(record)
    table_id = table_id_from_record(record, page_id)
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[float, float, float, float, str]] = set()

    raw_bboxes = extract_bboxes_from_obj(record)
    cell_union = union_bboxes(collect_nested_bboxes(record, ["cells", "cell_records", "table_cells", "row_records", "rows", "words", "word_records", "ocr_words"]))
    if cell_union:
        raw_bboxes.append(("union_of_nested_cell_word_boxes", cell_union))

    for idx, (bbox_path, bbox) in enumerate(raw_bboxes):
        key = tuple(round(safe_float(v), 4) for v in bbox) + (bbox_path,)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            build_candidate(
                source_name=source_name,
                source_record=record,
                bbox_path=bbox_path,
                bbox=bbox,
                page_id=page_id,
                table_id=table_id,
                candidate_index=idx + 1,
            )
        )

    return candidates


class FallbackTableRouteContract:
    """Small parser for synthetic tests and simple sidecar-style contracts."""

    def __init__(self, payload: Mapping[str, Any]) -> None:
        self.table_allowed_pages: set[str] = set()
        for key in ("table_allowed_pages", "table_allowed_page_ids", "table_route_allowed_pages"):
            value = payload.get(key)
            if isinstance(value, list):
                self.table_allowed_pages.update(str(item) for item in value if item)
            elif isinstance(value, Mapping):
                self.table_allowed_pages.update(str(k) for k, v in value.items() if v)

        allowed_pages = payload.get("allowed_pages")
        if isinstance(allowed_pages, Mapping):
            pages = allowed_pages.get("table")
            if isinstance(pages, list):
                self.table_allowed_pages.update(str(item) for item in pages if item)

        for key in ("processor_contract_cards", "route_dispatch_cards", "contract_cards"):
            cards = payload.get(key)
            if not isinstance(cards, list):
                continue
            for card in cards:
                if not isinstance(card, Mapping):
                    continue
                page_id = str(card.get("page_id") or card.get("source_page_id") or "")
                if not page_id:
                    continue
                routes = set(str(item) for item in (card.get("allowed_dispatch_routes") or []) if item)
                if card.get("table_processing_allowed") or card.get("table_route_allowed") or "table" in routes:
                    self.table_allowed_pages.add(page_id)

    def is_table_allowed(self, page_id: Any) -> bool:
        return str(page_id or "") in self.table_allowed_pages


class MergedTableRouteContract:
    """Accepts either production contract loader output or fallback simple keys."""

    def __init__(self, primary: Any | None, fallback: FallbackTableRouteContract) -> None:
        self.primary = primary
        self.fallback = fallback

    def is_table_allowed(self, page_id: Any) -> bool:
        for contract in (self.primary, self.fallback):
            if contract is None:
                continue
            method = getattr(contract, "is_table_allowed", None)
            if method is None:
                continue
            try:
                if bool(method(page_id)):
                    return True
            except Exception:
                continue
        return False


def load_contract(path: Path | None) -> tuple[Any | None, str | None]:
    if not path:
        return None, None
    payload = read_json(path)
    status = quality_status(payload) if isinstance(payload, Mapping) else "UNKNOWN"
    fallback = FallbackTableRouteContract(payload if isinstance(payload, Mapping) else {})
    primary = None
    if load_route_dispatch_processor_contract is not None:
        try:
            primary = load_route_dispatch_processor_contract(path)
        except Exception:
            primary = None
    return MergedTableRouteContract(primary, fallback), status


def route_table_allowed(contract: Any | None, page_id: str) -> bool:
    if contract is None:
        return True
    method = getattr(contract, "is_table_allowed", None)
    if method is None:
        return True
    try:
        return bool(method(page_id))
    except Exception:
        return False


def group_records_by_key(records_by_source: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[tuple[str, str], dict[str, list[Mapping[str, Any]]]]:
    grouped: dict[tuple[str, str], dict[str, list[Mapping[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for source_name, records in records_by_source.items():
        for record in records:
            page_id = page_id_from_record(record)
            table_id = table_id_from_record(record, page_id)
            if not page_id:
                continue
            grouped[(page_id, table_id)][source_name].append(record)
    return grouped


def build_resolver_card(
    *,
    page_id: str,
    table_id: str,
    grouped_records: Mapping[str, Sequence[Mapping[str, Any]]],
    contract: Any | None,
) -> dict[str, Any]:
    table_route_allowed = route_table_allowed(contract, page_id)

    candidates: list[dict[str, Any]] = []
    for source_name, records in grouped_records.items():
        for record in records:
            candidates.extend(candidates_from_record(source_name, record))

    candidates = apply_candidate_context_penalties(candidates)
    candidates = sorted(candidates, key=lambda item: (-safe_float(item.get("score")), safe_text(item.get("source_name")), safe_text(item.get("source_bbox_path"))))

    selected = None

    # First choice: clean, non-line-geometry table-region candidate.
    for candidate in candidates:
        if candidate.get("rejection_reasons"):
            continue
        if str(candidate.get("source_name") or "") == "table_line_geometry":
            continue
        selected = dict(candidate)
        break

    # Second choice: any clean candidate.
    if selected is None:
        for candidate in candidates:
            if candidate.get("rejection_reasons"):
                continue
            selected = dict(candidate)
            break

    # Third choice: non-page-like bbox resolver/full-region candidate even if it
    # has advisory warnings.
    if selected is None:
        for candidate in candidates:
            reasons = set(candidate.get("rejection_reasons") or [])
            if "bbox_too_page_like" in reasons or "pixel_space_candidate_too_page_like_relative_to_page" in reasons:
                continue
            if str(candidate.get("source_name") or "") in {"table_bbox_resolver", "table_full_region_recovery", "table_crop_completeness_guard"}:
                selected = dict(candidate)
                break

    if selected is None and candidates:
        # Final fallback: use best candidate but keep review required.
        selected = dict(candidates[0])

    selected_bbox = selected.get("bbox") if selected else None
    selected_candidate_id = selected.get("candidate_id") if selected else ""

    final_candidates = []
    for candidate in candidates:
        item = dict(candidate)
        item["candidate_selected"] = bool(item.get("candidate_id") == selected_candidate_id)
        final_candidates.append(item)

    candidate_reasons = Counter(reason for candidate in final_candidates for reason in candidate.get("rejection_reasons") or [])
    review_reasons: list[str] = []
    if not table_route_allowed:
        review_reasons.append("table_route_not_allowed")
    if not final_candidates:
        review_reasons.append("no_bbox_candidates_found")
    if selected and selected.get("rejection_reasons"):
        review_reasons.append("selected_best_candidate_has_rejection_reasons")
    if selected and safe_float(selected.get("score")) < 0.45:
        review_reasons.append("selected_bbox_low_score")
    selected_reasons = set(selected.get("rejection_reasons") or []) if selected else set()
    if "bbox_too_page_like" in selected_reasons or "pixel_space_candidate_too_page_like_relative_to_page" in selected_reasons:
        review_reasons.append("selected_bbox_page_like")
    if "bbox_too_tiny" in selected_reasons:
        review_reasons.append("selected_bbox_too_tiny")

    unsafe = (not table_route_allowed) or (selected is None)

    return {
        "schema_version": SCHEMA_VERSION,
        "page_id": page_id,
        "table_id": table_id,
        "table_route_dispatch_allowed": table_route_allowed,
        "candidate_count": len(final_candidates),
        "selected_candidate_id": selected_candidate_id,
        "selected_bbox": selected_bbox,
        "selected_score": round(safe_float(selected.get("score")) if selected else 0.0, 6),
        "selected_source_name": selected.get("source_name") if selected else "",
        "selected_source_bbox_path": selected.get("source_bbox_path") if selected else "",
        "review_required": bool(review_reasons),
        "review_reasons": sorted(set(review_reasons)),
        "candidate_rejection_reason_counts": dict(sorted(candidate_reasons.items())),
        "bbox_candidates": final_candidates[:80],
        "paddle_style_design_notes": [
            "multi_candidate_table_region_selection",
            "table_structure_signal_scoring",
            "bbox_shape_rejection_for_page_like_or_tiny_regions",
            "selected_bbox_ready_for_cell_coordinate_and_text_assignment",
        ],
        "unsafe_resolver_card": unsafe,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
    }


def build_quality(summary: Mapping[str, Any], thresholds: Thresholds) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(name: str, actual: Any, op: str, expected: Any, passed: bool) -> None:
        checks.append({"name": name, "actual": actual, "op": op, "expected": expected, "passed": bool(passed)})

    check("resolver_card_count", summary.get("resolver_card_count"), ">=", thresholds.min_resolver_cards, safe_int(summary.get("resolver_card_count")) >= thresholds.min_resolver_cards)
    check("selected_bbox_card_count", summary.get("selected_bbox_card_count"), ">=", thresholds.min_selected_bbox_cards, safe_int(summary.get("selected_bbox_card_count")) >= thresholds.min_selected_bbox_cards)
    check("route_blocked_card_count", summary.get("route_blocked_card_count"), "<=", thresholds.max_route_blocked_cards, safe_int(summary.get("route_blocked_card_count")) <= thresholds.max_route_blocked_cards)
    check("unsafe_resolver_card_count", summary.get("unsafe_resolver_card_count"), "<=", thresholds.max_unsafe_resolver_cards, safe_int(summary.get("unsafe_resolver_card_count")) <= thresholds.max_unsafe_resolver_cards)
    check("answer_permission_count", summary.get("answer_permission_count"), "<=", thresholds.max_answer_permission_count, safe_int(summary.get("answer_permission_count")) <= thresholds.max_answer_permission_count)
    check("source_truth_mutation_allowed_count", summary.get("source_truth_mutation_allowed_count"), "<=", thresholds.max_source_truth_mutation_allowed, safe_int(summary.get("source_truth_mutation_allowed_count")) <= thresholds.max_source_truth_mutation_allowed)

    if thresholds.require_route_contract_quality_pass:
        check("route_dispatch_processor_contract_quality_status", summary.get("route_dispatch_processor_contract_quality_status"), "==", "PASS", safe_text(summary.get("route_dispatch_processor_contract_quality_status")) == "PASS")
    if thresholds.require_no_answer_permission:
        check("no_answer_permission", summary.get("answer_permission_count"), "==", 0, safe_int(summary.get("answer_permission_count")) == 0)
        check("no_can_answer_directly", summary.get("can_answer_directly_count"), "==", 0, safe_int(summary.get("can_answer_directly_count")) == 0)
        check("no_can_prove_claims", summary.get("can_prove_claims_count"), "==", 0, safe_int(summary.get("can_prove_claims_count")) == 0)

    status = "PASS" if all(item["passed"] for item in checks) else "FAIL"
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "status": status,
        "quality_status": status,
        "checks": checks,
        "summary": dict(summary),
    }


def build_table_paddle_style_bbox_resolver_report(
    *,
    table_bbox_resolver: Path = DEFAULT_TABLE_BBOX_RESOLVER,
    table_full_region_recovery: Path = DEFAULT_TABLE_FULL_REGION_RECOVERY,
    table_crop_completeness_guard: Path = DEFAULT_TABLE_CROP_COMPLETENESS_GUARD,
    table_line_geometry: Path = DEFAULT_TABLE_LINE_GEOMETRY,
    route_dispatch_processor_contract: Path | None = DEFAULT_ROUTE_CONTRACT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    thresholds: Thresholds | None = None,
    write_outputs: bool = True,
) -> dict[str, Any]:
    thresholds = thresholds or Thresholds()

    bbox_records, bbox_payload = load_records(table_bbox_resolver, [
        "table_bbox_cards",
        "table_bbox_resolver_cards",
        "bbox_resolver_cards",
        "records",
    ])
    full_records, full_payload = load_records(table_full_region_recovery, [
        "recovery_cards",
        "table_full_region_recovery_cards",
        "full_region_recovery_cards",
        "records",
    ])
    guard_records, guard_payload = load_records(table_crop_completeness_guard, [
        "crop_completeness_cards",
        "table_crop_completeness_guard_cards",
        "crop_completeness_guard_cards",
        "records",
    ])
    geometry_records, geometry_payload = load_records(table_line_geometry, ["table_geometry_cards", "records"])

    contract, contract_status = load_contract(route_dispatch_processor_contract)

    records_by_source = {
        "table_bbox_resolver": bbox_records,
        "table_full_region_recovery": full_records,
        "table_crop_completeness_guard": guard_records,
        "table_line_geometry": geometry_records,
    }

    grouped = group_records_by_key(records_by_source)
    cards = [
        build_resolver_card(
            page_id=page_id,
            table_id=table_id,
            grouped_records=source_records,
            contract=contract,
        )
        for (page_id, table_id), source_records in sorted(grouped.items())
    ]

    candidate_count = sum(safe_int(card.get("candidate_count")) for card in cards)
    source_counts = Counter(
        candidate.get("source_name")
        for card in cards
        for candidate in card.get("bbox_candidates") or []
        if isinstance(candidate, Mapping)
    )

    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "table_bbox_resolver_path": str(table_bbox_resolver),
        "table_full_region_recovery_path": str(table_full_region_recovery),
        "table_crop_completeness_guard_path": str(table_crop_completeness_guard),
        "table_line_geometry_path": str(table_line_geometry),
        "route_dispatch_processor_contract_path": str(route_dispatch_processor_contract or ""),
        "table_bbox_resolver_quality_status": quality_status(bbox_payload),
        "table_full_region_recovery_quality_status": quality_status(full_payload),
        "table_crop_completeness_guard_quality_status": quality_status(guard_payload),
        "table_line_geometry_quality_status": quality_status(geometry_payload),
        "route_dispatch_processor_contract_quality_status": contract_status,
        "resolver_card_count": len(cards),
        "selected_bbox_card_count": sum(1 for card in cards if card.get("selected_bbox")),
        "candidate_bbox_count": candidate_count,
        "route_blocked_card_count": sum(1 for card in cards if not card.get("table_route_dispatch_allowed")),
        "review_required_card_count": sum(1 for card in cards if card.get("review_required")),
        "unsafe_resolver_card_count": sum(1 for card in cards if card.get("unsafe_resolver_card")),
        "page_like_candidate_card_count": sum(1 for card in cards if "page_like_bbox_candidates_present" in (card.get("review_reasons") or [])),
        "tiny_candidate_card_count": sum(1 for card in cards if "tiny_bbox_candidates_present" in (card.get("review_reasons") or [])),
        "low_score_selected_card_count": sum(1 for card in cards if "selected_bbox_low_score" in (card.get("review_reasons") or [])),
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "source_truth_mutations_performed": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "candidate_count_by_source": dict(sorted(source_counts.items())),
    }

    quality = build_quality(summary, thresholds)
    summary["quality_status"] = quality["status"]

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "status": STATUS_BUILT if quality["status"] == "PASS" else STATUS_NOT_READY,
        "quality_status": quality["status"],
        "summary": summary,
        "table_paddle_style_bbox_resolver_cards": cards,
        "quality": quality,
    }

    if write_outputs:
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / DEFAULT_REPORT_FILE
        quality_path = output_dir / DEFAULT_QUALITY_FILE
        write_json(report_path, report)
        write_json(quality_path, quality)
        report["report_path"] = str(report_path)
        report["quality_path"] = str(quality_path)

    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Paddle-style table bbox resolver v1")
    parser.add_argument("--table-bbox-resolver", type=Path, default=DEFAULT_TABLE_BBOX_RESOLVER)
    parser.add_argument("--table-full-region-recovery", type=Path, default=DEFAULT_TABLE_FULL_REGION_RECOVERY)
    parser.add_argument("--table-crop-completeness-guard", type=Path, default=DEFAULT_TABLE_CROP_COMPLETENESS_GUARD)
    parser.add_argument("--table-line-geometry", type=Path, default=DEFAULT_TABLE_LINE_GEOMETRY)
    parser.add_argument("--route-dispatch-processor-contract", type=Path, default=DEFAULT_ROUTE_CONTRACT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--min-resolver-cards", type=int, default=1)
    parser.add_argument("--min-selected-bbox-cards", type=int, default=1)
    parser.add_argument("--max-route-blocked-cards", type=int, default=0)
    parser.add_argument("--max-unsafe-resolver-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-route-contract-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    thresholds = Thresholds(
        min_resolver_cards=args.min_resolver_cards,
        min_selected_bbox_cards=args.min_selected_bbox_cards,
        max_route_blocked_cards=args.max_route_blocked_cards,
        max_unsafe_resolver_cards=args.max_unsafe_resolver_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_route_contract_quality_pass=args.require_route_contract_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    report = build_table_paddle_style_bbox_resolver_report(
        table_bbox_resolver=args.table_bbox_resolver,
        table_full_region_recovery=args.table_full_region_recovery,
        table_crop_completeness_guard=args.table_crop_completeness_guard,
        table_line_geometry=args.table_line_geometry,
        route_dispatch_processor_contract=args.route_dispatch_processor_contract,
        output_dir=args.output_dir,
        thresholds=thresholds,
    )
    summary = report["summary"]
    print("TRACE-Net Table Paddle-Style BBox Resolver v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "resolver_card_count",
        "selected_bbox_card_count",
        "candidate_bbox_count",
        "route_blocked_card_count",
        "review_required_card_count",
        "unsafe_resolver_card_count",
        "page_like_candidate_card_count",
        "tiny_candidate_card_count",
        "low_score_selected_card_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
        "route_dispatch_processor_contract_quality_status",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {report.get('report_path')}")
    print(f" quality_path: {report.get('quality_path')}")
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
