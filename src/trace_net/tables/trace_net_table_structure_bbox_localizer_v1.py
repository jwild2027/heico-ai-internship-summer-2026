"""TRACE-Net Table Structure BBox Localizer v1.

Read-only, containment-aware table bbox selector inspired by PaddleOCR /
PP-Structure style pipelines: prefer structure-complete table regions, not just
small line-dense crops.

This module does not run a neural table model. It adds the missing TRACE-Net
control layer between visual bbox localization and downstream table extraction:
visual refinements are accepted only when they preserve table completeness
relative to the upstream safe input bbox and downstream row/cell/value evidence.
If the visual bbox looks partial, too narrow, too short, or too aggressive, the
module conservatively falls back to the upstream input bbox and emits audit
flags.

Safety contract:
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no direct answer permission
- no claim-proof authority
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "trace_net_table_structure_bbox_localizer_v1"
QUALITY_SCHEMA_VERSION = "trace_net_table_structure_bbox_localizer_v1_quality"
STATUS_BUILT = "TABLE_STRUCTURE_BBOX_LOCALIZER_BUILT"
STATUS_NOT_READY = "TABLE_STRUCTURE_BBOX_LOCALIZER_NOT_READY"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/table_structure_bbox_localizer")

SAFETY_FALSE_KEYS = (
    "answer_permission",
    "can_answer_directly",
    "can_prove_claims",
    "final_answer_allowed",
    "llm_freeform_answer_allowed",
    "source_truth_mutation_allowed",
    "can_mutate_source_truth",
    "postgres_write_attempted",
    "qdrant_write_attempted",
    "opensearch_write_attempted",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_id(prefix: str, *parts: Any, length: int = 14) -> str:
    data = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(data.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}__{digest}"


def read_json(path: str | Path | None, default: Any = None) -> Any:
    if not path:
        return default
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(dict(record), sort_keys=True, ensure_ascii=False) + "\n")


def as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def normalize_bbox(value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        if all(k in value for k in ("x0", "y0", "x1", "y1")):
            x0, y0, x1, y1 = (as_float(value.get(k)) for k in ("x0", "y0", "x1", "y1"))
        elif all(k in value for k in ("left", "top", "right", "bottom")):
            x0, y0, x1, y1 = (as_float(value.get(k)) for k in ("left", "top", "right", "bottom"))
        elif all(k in value for k in ("x", "y", "width", "height")):
            x = as_float(value.get("x")); y = as_float(value.get("y")); w = as_float(value.get("width")); h = as_float(value.get("height"))
            if x is None or y is None or w is None or h is None:
                return None
            x0, y0, x1, y1 = x, y, x + w, y + h
        else:
            return None
        coord = str(value.get("coordinate_system") or "pixels")
    elif isinstance(value, (list, tuple)) and len(value) >= 4:
        x0, y0, x1, y1 = (as_float(v) for v in value[:4])
        coord = "pixels"
    else:
        return None
    if None in (x0, y0, x1, y1):
        return None
    assert x0 is not None and y0 is not None and x1 is not None and y1 is not None
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    width = x1 - x0
    height = y1 - y0
    if width <= 1 or height <= 1:
        return None
    return {
        "x0": round(x0, 3),
        "y0": round(y0, 3),
        "x1": round(x1, 3),
        "y1": round(y1, 3),
        "width": round(width, 3),
        "height": round(height, 3),
        "coordinate_system": coord,
    }


def bbox_area(box: Mapping[str, Any] | None) -> float:
    if not box:
        return 0.0
    w = as_float(box.get("width"))
    h = as_float(box.get("height"))
    if w is None or h is None:
        x0 = as_float(box.get("x0")); x1 = as_float(box.get("x1")); y0 = as_float(box.get("y0")); y1 = as_float(box.get("y1"))
        if None in (x0, x1, y0, y1):
            return 0.0
        assert x0 is not None and x1 is not None and y0 is not None and y1 is not None
        w = x1 - x0
        h = y1 - y0
    return max(0.0, float(w)) * max(0.0, float(h))


def overlap_1d(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def geometry_metrics(input_box: Mapping[str, Any] | None, visual_box: Mapping[str, Any] | None) -> dict[str, Any]:
    if not input_box or not visual_box:
        return {
            "visual_to_input_width_ratio": None,
            "visual_to_input_height_ratio": None,
            "visual_to_input_area_ratio": None,
            "visual_input_x_overlap_ratio": None,
            "visual_input_y_overlap_ratio": None,
            "visual_top_band_preserved": False,
        }
    iw = max(1.0, float(input_box.get("width") or 1.0))
    ih = max(1.0, float(input_box.get("height") or 1.0))
    vw = max(1.0, float(visual_box.get("width") or 1.0))
    vh = max(1.0, float(visual_box.get("height") or 1.0))
    area_ratio = bbox_area(visual_box) / max(1.0, bbox_area(input_box))
    x_overlap = overlap_1d(float(input_box["x0"]), float(input_box["x1"]), float(visual_box["x0"]), float(visual_box["x1"])) / iw
    y_overlap = overlap_1d(float(input_box["y0"]), float(input_box["y1"]), float(visual_box["y0"]), float(visual_box["y1"])) / ih
    top_band_preserved = float(visual_box["y0"]) <= float(input_box["y0"]) + ih * 0.22
    return {
        "visual_to_input_width_ratio": round(vw / iw, 6),
        "visual_to_input_height_ratio": round(vh / ih, 6),
        "visual_to_input_area_ratio": round(area_ratio, 6),
        "visual_input_x_overlap_ratio": round(x_overlap, 6),
        "visual_input_y_overlap_ratio": round(y_overlap, 6),
        "visual_top_band_preserved": bool(top_band_preserved),
    }


def payload_quality_status(payload: Any) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    quality = payload.get("quality")
    if isinstance(quality, Mapping) and quality.get("status"):
        return str(quality.get("status"))
    if payload.get("quality_status"):
        return str(payload.get("quality_status"))
    if payload.get("status") in {"PASS", "FAIL"}:
        return str(payload.get("status"))
    return None


def visual_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(r) for r in payload if isinstance(r, Mapping)]
    if not isinstance(payload, Mapping):
        return []
    for key in ("table_visual_bbox_localizer_records", "records", "localized_records"):
        value = payload.get(key)
        if isinstance(value, list):
            return [dict(r) for r in value if isinstance(r, Mapping)]
    return []


def scoped_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(r) for r in payload if isinstance(r, Mapping)]
    if not isinstance(payload, Mapping):
        return []
    for key in ("scoped_table_records", "records", "table_bbox_scoped_cell_records"):
        value = payload.get(key)
        if isinstance(value, list):
            return [dict(r) for r in value if isinstance(r, Mapping)]
    return []


def build_scoped_indexes(records: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    by_table: dict[str, dict[str, Any]] = {}
    by_page: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        table_id = str(record.get("table_id") or "")
        page_id = str(record.get("page_id") or "")
        if table_id:
            by_table[table_id] = record
        if page_id:
            by_page[page_id].append(record)
    return by_table, by_page


def match_scoped_record(visual: Mapping[str, Any], by_table: Mapping[str, dict[str, Any]], by_page: Mapping[str, list[dict[str, Any]]]) -> tuple[dict[str, Any] | None, str]:
    table_id = str(visual.get("table_id") or "")
    page_id = str(visual.get("page_id") or "")
    if table_id and table_id in by_table:
        return by_table[table_id], "table_id"
    page_records = list(by_page.get(page_id, []))
    if len(page_records) == 1:
        return page_records[0], "page_id_single_scoped_record"
    ready = [r for r in page_records if r.get("bbox_scoped_extraction_ready") or r.get("bbox_consumed_by_row_cell_extraction")]
    if len(ready) == 1:
        return ready[0], "page_id_single_ready_scoped_record"
    if ready:
        return ready[0], "page_id_first_ready_scoped_record"
    if page_records:
        return page_records[0], "page_id_first_scoped_record"
    return None, "no_scoped_record_match"


def minimum_structure_height(row_count: int, cell_count: int) -> int:
    if row_count <= 0:
        # Dense cell-only table candidates still need non-trivial height.
        return max(260, min(900, int(cell_count / 4) * 10)) if cell_count else 260
    return max(260, min(1150, row_count * 12))


def validate_visual_candidate(visual: Mapping[str, Any], scoped: Mapping[str, Any] | None, input_box: dict[str, Any] | None, visual_box: dict[str, Any] | None) -> tuple[bool, list[str], dict[str, Any]]:
    metrics = geometry_metrics(input_box, visual_box)
    flags: list[str] = []
    row_count = as_int((scoped or {}).get("scoped_row_count") or (scoped or {}).get("source_row_count"), 0)
    cell_count = as_int((scoped or {}).get("scoped_cell_count") or (scoped or {}).get("source_cell_count"), 0)
    value_count = as_int((scoped or {}).get("scoped_value_record_count"), 0)
    min_height = minimum_structure_height(row_count, cell_count)
    multi_column = bool(visual.get("multi_column_vertical_merge_applied"))
    visual_source = visual.get("localized_bbox_source")
    visual_quality = visual.get("table_localization_quality_pass") is True
    visual_applied = visual.get("visual_refinement_applied") is True

    if scoped is None:
        flags.append("missing_bbox_scoped_cell_bridge")
    if not input_box:
        flags.append("missing_input_bbox")
    if not visual_box:
        flags.append("missing_visual_bbox")
    if visual_source == "input_bbox_fallback" or not visual_applied:
        flags.append("visual_candidate_not_refined")
    if not visual_quality:
        flags.append("visual_candidate_quality_not_pass")

    width_ratio = metrics.get("visual_to_input_width_ratio")
    height_ratio = metrics.get("visual_to_input_height_ratio")
    area_ratio = metrics.get("visual_to_input_area_ratio")
    x_overlap = metrics.get("visual_input_x_overlap_ratio")
    y_overlap = metrics.get("visual_input_y_overlap_ratio")
    if width_ratio is not None:
        required_width = 0.70 if multi_column else 0.55
        if width_ratio < required_width:
            flags.append("visual_candidate_cuts_table_columns")
    if height_ratio is not None and height_ratio < 0.32:
        flags.append("visual_candidate_cuts_table_rows")
    if area_ratio is not None and area_ratio < 0.18:
        flags.append("visual_candidate_over_tightened_area")
    if x_overlap is not None and x_overlap < 0.50:
        flags.append("visual_candidate_low_input_x_overlap")
    if y_overlap is not None and y_overlap < 0.32:
        flags.append("visual_candidate_low_input_y_overlap")
    if metrics.get("visual_top_band_preserved") is not True:
        flags.append("visual_candidate_header_band_not_preserved")
    if visual_box and float(visual_box.get("height") or 0.0) < min_height:
        flags.append("visual_candidate_too_short_for_row_count")
    if (as_int(visual.get("horizontal_line_run_count"), 0) < 2 and as_int(visual.get("row_band_run_count"), 0) < 8):
        flags.append("visual_candidate_weak_row_structure")
    if (as_int(visual.get("vertical_line_run_count"), 0) < 2 and as_int(visual.get("column_band_run_count"), 0) < 6):
        flags.append("visual_candidate_weak_column_structure")

    reject_flags = [f for f in flags if f.startswith("visual_candidate_") or f == "missing_bbox_scoped_cell_bridge"]
    accepted = bool(visual_box and input_box and not reject_flags and visual_quality and visual_applied and visual_source != "input_bbox_fallback")
    diagnostics = {
        **metrics,
        "scoped_row_count": row_count,
        "scoped_cell_count": cell_count,
        "scoped_value_record_count": value_count,
        "minimum_structure_height_required": min_height,
        "multi_column_vertical_merge_applied": multi_column,
        "multi_column_vertical_cluster_count": visual.get("multi_column_vertical_cluster_count"),
        "structure_visual_candidate_accepted": accepted,
        "structure_visual_candidate_rejected": bool(visual_box and not accepted),
    }
    return accepted, flags, diagnostics


def make_structure_record(visual: Mapping[str, Any], scoped: Mapping[str, Any] | None, match_method: str) -> dict[str, Any]:
    page_id = str(visual.get("page_id") or "")
    table_id = str((scoped or {}).get("table_id") or visual.get("table_id") or "")
    input_box = normalize_bbox(visual.get("input_bbox"))
    visual_box = normalize_bbox(visual.get("localized_table_bbox"))
    accepted, flags, diagnostics = validate_visual_candidate(visual, scoped, input_box, visual_box)
    selected_box = visual_box if accepted else input_box
    if not selected_box and visual_box:
        selected_box = visual_box
        flags.append("input_bbox_missing_selected_visual_fallback")
    selected_source = "structure_validated_visual_bbox" if accepted else "conservative_input_bbox_fallback"
    selected_key = "localized_table_bbox" if accepted else "input_bbox"
    ready = selected_box is not None
    review_flags = list(dict.fromkeys(flags + [f for f in as_list(visual.get("review_flags")) if isinstance(f, str)]))
    return {
        "schema_version": SCHEMA_VERSION,
        "table_structure_bbox_localizer_id": stable_id("tblstructbbox", page_id, table_id, selected_source),
        "page_id": page_id,
        "table_id": table_id,
        "visual_bbox_localizer_id": visual.get("visual_bbox_localizer_id"),
        "bbox_scoped_table_record_id": (scoped or {}).get("scoped_table_record_id"),
        "scoped_match_method": match_method,
        "input_bbox": input_box,
        "input_bbox_key": visual.get("input_bbox_key"),
        "input_bbox_source": visual.get("input_bbox_source"),
        "visual_candidate_bbox": visual_box,
        "visual_candidate_bbox_source": visual.get("localized_bbox_source"),
        "visual_candidate_quality_pass": visual.get("table_localization_quality_pass") is True,
        "visual_refinement_applied": visual.get("visual_refinement_applied") is True,
        "structure_selected_table_bbox": selected_box,
        "structure_selected_bbox_source": selected_source,
        "structure_selected_bbox_key": selected_key,
        "structure_selected_bbox_ready": ready,
        "structure_visual_candidate_accepted": accepted,
        "structure_visual_candidate_rejected": bool(visual_box and not accepted),
        "row_cell_extraction_scope": "structure_validated_visual_bbox_crop" if accepted else "conservative_input_bbox_crop",
        "recommended_downstream_bbox_key": "structure_selected_table_bbox",
        **diagnostics,
        "horizontal_line_run_count": visual.get("horizontal_line_run_count"),
        "vertical_line_run_count": visual.get("vertical_line_run_count"),
        "row_band_run_count": visual.get("row_band_run_count"),
        "column_band_run_count": visual.get("column_band_run_count"),
        "review_required": bool(review_flags),
        "review_flags": review_flags,
        "recommended_next_actions": [
            "use_structure_selected_table_bbox_for_row_cell_extraction" if ready else "inspect_missing_table_bbox_before_downstream_extraction"
        ],
        "record_role": "structure_first_table_bbox_selector",
        "routing_only": True,
        "retrieval_only": True,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "final_answer_allowed": False,
        "llm_freeform_answer_allowed": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
        "can_mutate_source_truth": False,
        "postgres_write_attempted": False,
        "qdrant_write_attempted": False,
        "opensearch_write_attempted": False,
        "unsafe_table_structure_bbox_localizer_record": False,
    }


def unsafe_record_count(records: list[Mapping[str, Any]]) -> int:
    count = 0
    for record in records:
        if record.get("unsafe_table_structure_bbox_localizer_record"):
            count += 1
            continue
        for key in SAFETY_FALSE_KEYS:
            if record.get(key) is True:
                count += 1
                break
    return count


def median(values: list[float]) -> float | None:
    clean = sorted(float(v) for v in values if isinstance(v, (int, float)))
    if not clean:
        return None
    mid = len(clean) // 2
    if len(clean) % 2:
        return round(clean[mid], 6)
    return round((clean[mid - 1] + clean[mid]) / 2.0, 6)


def summarize(records: list[dict[str, Any]], *, visual_payload: Any = None, scoped_payload: Any = None, source_visual_count: int | None = None, source_scoped_count: int | None = None) -> dict[str, Any]:
    selected = [r for r in records if r.get("structure_selected_bbox_ready")]
    accepted = [r for r in records if r.get("structure_visual_candidate_accepted")]
    rejected = [r for r in records if r.get("structure_visual_candidate_rejected")]
    fallback = [r for r in records if r.get("structure_selected_bbox_source") == "conservative_input_bbox_fallback"]
    ratios = [r.get("visual_to_input_area_ratio") for r in records if isinstance(r.get("visual_to_input_area_ratio"), (int, float))]
    return {
        "schema_version": SCHEMA_VERSION,
        "source_table_visual_bbox_localizer_quality_status": payload_quality_status(visual_payload),
        "source_table_bbox_scoped_cell_extraction_quality_status": payload_quality_status(scoped_payload),
        "source_visual_record_count": int(source_visual_count if source_visual_count is not None else len(records)),
        "source_scoped_table_record_count": int(source_scoped_count if source_scoped_count is not None else 0),
        "structure_record_count": len(records),
        "page_count": len({r.get("page_id") for r in records if r.get("page_id")}),
        "structure_selected_bbox_record_count": len(selected),
        "structure_visual_bbox_accepted_count": len(accepted),
        "structure_visual_bbox_rejected_count": len(rejected),
        "conservative_input_bbox_fallback_count": len(fallback),
        "missing_scoped_cell_bridge_count": sum(1 for r in records if "missing_bbox_scoped_cell_bridge" in (r.get("review_flags") or [])),
        "visual_candidate_cuts_table_columns_count": sum(1 for r in records if "visual_candidate_cuts_table_columns" in (r.get("review_flags") or [])),
        "visual_candidate_cuts_table_rows_count": sum(1 for r in records if "visual_candidate_cuts_table_rows" in (r.get("review_flags") or [])),
        "visual_candidate_over_tightened_area_count": sum(1 for r in records if "visual_candidate_over_tightened_area" in (r.get("review_flags") or [])),
        "visual_candidate_too_short_for_row_count": sum(1 for r in records if "visual_candidate_too_short_for_row_count" in (r.get("review_flags") or [])),
        "split_column_visual_candidate_count": sum(1 for r in records if r.get("multi_column_vertical_merge_applied")),
        "split_column_visual_accepted_count": sum(1 for r in accepted if r.get("multi_column_vertical_merge_applied")),
        "visual_to_input_area_ratio_median": median(ratios),
        "unsafe_table_structure_bbox_localizer_record_count": unsafe_record_count(records),
        "answer_permission_count": sum(1 for r in records if r.get("answer_permission") or r.get("final_answer_allowed") or r.get("llm_freeform_answer_allowed")),
        "can_answer_directly_count": sum(1 for r in records if r.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for r in records if r.get("can_prove_claims")),
        "source_truth_mutation_allowed_count": sum(1 for r in records if r.get("source_truth_mutation_allowed") or r.get("can_mutate_source_truth")),
        "postgres_write_attempt_count": sum(1 for r in records if r.get("postgres_write_attempted")),
        "qdrant_write_attempt_count": sum(1 for r in records if r.get("qdrant_write_attempted")),
        "opensearch_write_attempt_count": sum(1 for r in records if r.get("opensearch_write_attempted")),
    }


def quality_checks(summary: Mapping[str, Any], thresholds: Mapping[str, Any] | argparse.Namespace | None = None) -> tuple[str, list[dict[str, Any]]]:
    thresholds = thresholds or {}

    def get(name: str, default: Any) -> Any:
        if isinstance(thresholds, Mapping):
            return thresholds.get(name, default)
        return getattr(thresholds, name, default)

    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    add("source_visual_records", summary.get("source_visual_record_count", 0) >= get("min_source_visual_records", 1), f"records={summary.get('source_visual_record_count', 0)} minimum={get('min_source_visual_records', 1)}")
    add("structure_records", summary.get("structure_record_count", 0) >= get("min_structure_records", 1), f"records={summary.get('structure_record_count', 0)} minimum={get('min_structure_records', 1)}")
    add("selected_bbox_records", summary.get("structure_selected_bbox_record_count", 0) >= get("min_selected_bbox_records", 1), f"selected={summary.get('structure_selected_bbox_record_count', 0)} minimum={get('min_selected_bbox_records', 1)}")
    add("visual_bbox_rejection_guard", summary.get("structure_visual_bbox_rejected_count", 0) >= get("min_visual_bbox_rejected_records", 0), f"rejected={summary.get('structure_visual_bbox_rejected_count', 0)} minimum={get('min_visual_bbox_rejected_records', 0)}")
    add("unsafe_records", summary.get("unsafe_table_structure_bbox_localizer_record_count", 0) <= get("max_unsafe_records", 0), f"unsafe={summary.get('unsafe_table_structure_bbox_localizer_record_count', 0)} max={get('max_unsafe_records', 0)}")
    add("answer_permission", summary.get("answer_permission_count", 0) <= get("max_answer_permission_count", 0), f"count={summary.get('answer_permission_count', 0)} max={get('max_answer_permission_count', 0)}")
    add("source_truth_mutation_allowed", summary.get("source_truth_mutation_allowed_count", 0) <= get("max_source_truth_mutation_allowed", 0), f"count={summary.get('source_truth_mutation_allowed_count', 0)} max={get('max_source_truth_mutation_allowed', 0)}")
    add("postgres_writes", summary.get("postgres_write_attempt_count", 0) == 0, f"count={summary.get('postgres_write_attempt_count', 0)}")
    add("qdrant_writes", summary.get("qdrant_write_attempt_count", 0) == 0, f"count={summary.get('qdrant_write_attempt_count', 0)}")
    add("opensearch_writes", summary.get("opensearch_write_attempt_count", 0) == 0, f"count={summary.get('opensearch_write_attempt_count', 0)}")
    if get("require_table_visual_bbox_localizer_quality_pass", False):
        add("source_table_visual_bbox_localizer_quality_pass", summary.get("source_table_visual_bbox_localizer_quality_status") == "PASS", f"status={summary.get('source_table_visual_bbox_localizer_quality_status')}")
    if get("require_table_bbox_scoped_cell_extraction_quality_pass", False):
        add("source_table_bbox_scoped_cell_extraction_quality_pass", summary.get("source_table_bbox_scoped_cell_extraction_quality_status") == "PASS", f"status={summary.get('source_table_bbox_scoped_cell_extraction_quality_status')}")
    if get("require_all_records_selected_bbox_ready", False):
        add("all_records_selected_bbox_ready", summary.get("structure_selected_bbox_record_count", 0) == summary.get("structure_record_count", -1), f"selected={summary.get('structure_selected_bbox_record_count', 0)} records={summary.get('structure_record_count', -1)}")
    status = "PASS" if all(c["ok"] for c in checks) else "FAIL"
    return status, checks


def build_report(
    *,
    table_visual_bbox_localizer_path: str | Path,
    table_bbox_scoped_cell_extraction_path: str | Path,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    thresholds: Mapping[str, Any] | argparse.Namespace | None = None,
    write_quality: bool = False,
) -> dict[str, Any]:
    visual_payload = read_json(table_visual_bbox_localizer_path, default={})
    scoped_payload = read_json(table_bbox_scoped_cell_extraction_path, default={})
    visuals = visual_records(visual_payload)
    scoped = scoped_records(scoped_payload)
    by_table, by_page = build_scoped_indexes(scoped)
    records = []
    for visual in visuals:
        scoped_record, match_method = match_scoped_record(visual, by_table, by_page)
        records.append(make_structure_record(visual, scoped_record, match_method))
    summary = summarize(records, visual_payload=visual_payload, scoped_payload=scoped_payload, source_visual_count=len(visuals), source_scoped_count=len(scoped))
    quality_status, checks = quality_checks(summary, thresholds)
    report = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "summary": summary,
        "quality": {"schema_version": QUALITY_SCHEMA_VERSION, "status": quality_status, "checks": checks},
        "table_structure_bbox_localizer_records": records,
    }
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "trace_net_table_structure_bbox_localizer_v1.json"
    records_path = out / "trace_net_table_structure_bbox_localizer_v1_records.jsonl"
    summary_path = out / "trace_net_table_structure_bbox_localizer_v1_summary.json"
    quality_path = out / "trace_net_table_structure_bbox_localizer_v1_quality.json"
    manifest_path = out / "trace_net_table_structure_bbox_localizer_v1_manifest.json"
    write_json(report_path, report)
    write_jsonl(records_path, records)
    write_json(summary_path, summary)
    if write_quality:
        write_json(quality_path, {"schema_version": QUALITY_SCHEMA_VERSION, "status": quality_status, "summary": summary, "checks": checks})
    write_json(manifest_path, {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "report_path": str(report_path),
        "records_path": str(records_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "source_paths": {
            "table_visual_bbox_localizer": str(table_visual_bbox_localizer_path),
            "table_bbox_scoped_cell_extraction": str(table_bbox_scoped_cell_extraction_path),
        },
        "safety_contract": {
            "postgres_writes": False,
            "qdrant_writes": False,
            "opensearch_writes": False,
            "source_truth_mutation": False,
            "answer_permission": False,
        },
    })
    report["report_path"] = str(report_path)
    report["records_path"] = str(records_path)
    report["quality_path"] = str(quality_path)
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build TRACE-Net table structure bbox localizer v1 artifacts.")
    p.add_argument("--table-visual-bbox-localizer", required=True)
    p.add_argument("--table-bbox-scoped-cell-extraction", required=True)
    p.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    p.add_argument("--min-source-visual-records", type=int, default=1)
    p.add_argument("--min-structure-records", type=int, default=1)
    p.add_argument("--min-selected-bbox-records", type=int, default=1)
    p.add_argument("--min-visual-bbox-rejected-records", type=int, default=0)
    p.add_argument("--max-unsafe-records", type=int, default=0)
    p.add_argument("--max-answer-permission-count", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--require-table-visual-bbox-localizer-quality-pass", action="store_true")
    p.add_argument("--require-table-bbox-scoped-cell-extraction-quality-pass", action="store_true")
    p.add_argument("--require-all-records-selected-bbox-ready", action="store_true")
    p.add_argument("--quality", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = build_report(
        table_visual_bbox_localizer_path=args.table_visual_bbox_localizer,
        table_bbox_scoped_cell_extraction_path=args.table_bbox_scoped_cell_extraction,
        output_dir=args.output_dir,
        thresholds=args,
        write_quality=args.quality,
    )
    summary = report.get("summary", {})
    print("TRACE-Net Table Structure BBox Localizer v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in (
        "source_visual_record_count",
        "source_scoped_table_record_count",
        "structure_record_count",
        "structure_selected_bbox_record_count",
        "structure_visual_bbox_accepted_count",
        "structure_visual_bbox_rejected_count",
        "conservative_input_bbox_fallback_count",
        "visual_candidate_cuts_table_columns_count",
        "visual_candidate_cuts_table_rows_count",
        "visual_candidate_over_tightened_area_count",
        "visual_candidate_too_short_for_row_count",
        "split_column_visual_candidate_count",
        "split_column_visual_accepted_count",
        "unsafe_table_structure_bbox_localizer_record_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {report.get('report_path')}")
    return 0 if report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
