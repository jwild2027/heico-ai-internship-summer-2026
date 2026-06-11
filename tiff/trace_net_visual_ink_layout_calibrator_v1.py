"""TRACE-Net Visual Ink / Layout Calibrator v1.

This module is a read-only front-start TRACE-Net layer. It takes the broad
image-recognition/figure understanding signals and recalibrates them with simple,
auditable layout math before any heavier vision model is used.

Important safety boundary:
- ink/layout records are routing/review helpers only;
- they cannot answer directly;
- they cannot prove claims;
- they cannot mutate source truth;
- final answer use still requires OCR/catalog/graph/citation/trust gates.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_visual_ink_layout_calibrator_v1"
ALGORITHM_NAME = "trace_net_ink_layout_math_calibrator_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/visual_ink_layout_calibrator")

VISUAL_ROUTE_AUTHORITY = "visual_layout_route_only"

FORBIDDEN_USER_VISIBLE_MARKERS = (
    "local_data\\",
    "local_data/",
    "rescarta_exports",
    "C:\\Users\\",
    "TIFF path:",
    "OCR path:",
    "Source URL:",
    "OCR text: [b",
    "prompt_preview",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_id(prefix: str, *parts: Any, length: int = 16) -> str:
    text = "::".join(str(p) for p in parts if p is not None)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}__{digest}"


def read_json(path: str | Path | None, default: Any = None) -> Any:
    if not path:
        return default
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON file: {p}: {exc}") from exc


def write_json(path: str | Path, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: str | Path, records: Iterable[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_records(path: str | Path | None, keys: tuple[str, ...] = ("records",)) -> list[dict[str, Any]]:
    payload = read_json(path, {})
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
    return []


def load_summary(path: str | Path | None) -> dict[str, Any]:
    payload = read_json(path, {})
    if isinstance(payload, dict):
        summary = payload.get("summary")
        if isinstance(summary, dict):
            return summary
        # Quality files often put summary fields at top level.
        return {k: v for k, v in payload.items() if k != "records"}
    return {}


def index_by_page(records: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        page_id = record.get("page_id")
        if isinstance(page_id, str) and page_id:
            out[page_id].append(record)
    return out


def first_record(index: dict[str, list[dict[str, Any]]], page_id: str) -> dict[str, Any]:
    values = index.get(page_id) or []
    return values[0] if values else {}


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "ok", "pass"}
    return False


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


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def round4(value: float) -> float:
    return round(float(value), 4)


def page_number_from_page_id(page_id: str) -> int | None:
    match = re.search(r"p(\d{6})$", page_id or "")
    if not match:
        return None
    return int(match.group(1))


def text_blob(*values: Any) -> str:
    parts: list[str] = []
    for value in values:
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(v) for v in value if v is not None)
        elif isinstance(value, dict):
            parts.extend(str(v) for v in value.values() if isinstance(v, (str, int, float)))
    return " ".join(parts).lower()


def safe_public_text(value: Any, max_chars: int = 320) -> str:
    text = str(value or "")
    for marker in FORBIDDEN_USER_VISIBLE_MARKERS:
        text = text.replace(marker, "")
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\b[a-zA-Z]:\\[^\s]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def collect_candidate_bucket_counts(record: dict[str, Any]) -> dict[str, int]:
    counts = record.get("candidate_bucket_counts") or record.get("safe_candidate_bucket_counts") or {}
    if isinstance(counts, dict):
        return {str(k): as_int(v) for k, v in counts.items()}
    return {}


def table_normalizer_page_stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    row_count = 0
    cell_count = 0
    answer_support_rows = 0
    repair_count = 0
    table_types = Counter()
    for record in records:
        row_count += as_int(record.get("normalized_row_count") or record.get("row_count"))
        cell_count += as_int(record.get("normalized_cell_count") or record.get("cell_count"))
        answer_support_rows += as_int(record.get("answer_support_row_count"))
        repair_count += as_int(record.get("repair_count") or record.get("normalized_repair_count"))
        if record.get("table_type"):
            table_types[str(record.get("table_type"))] += 1
    return {
        "normalized_row_count": row_count,
        "normalized_cell_count": cell_count,
        "answer_support_row_count": answer_support_rows,
        "table_repair_count": repair_count,
        "table_types": dict(table_types),
    }


def compute_layout_scores(
    page_record: dict[str, Any],
    audit_record: dict[str, Any],
    figure_record: dict[str, Any],
    table_stats: dict[str, Any],
) -> dict[str, float]:
    """Compute auditable ink/layout scores in [0, 1].

    The math intentionally uses simple ratios instead of a learned image model:
    - ink_ratio: dark pixels / sampled pixels;
    - line_density: horizontal/vertical line counts normalized by expected grid counts;
    - component_density: log-scaled connected component count;
    - largest_component_ratio: largest dark blob / dark pixel count;
    - table_score: grid score + line density + known table rows;
    - diagram_score: visual score + components + parts-list/figure context;
    - chart_score: non-table visual score, penalized for front matter/blank/pages with no chart context;
    - text_score: OCR/text/front-matter/procedure signals.
    """

    role = str(audit_record.get("role") or page_record.get("page_role") or page_record.get("role") or "").lower()
    context = text_blob(audit_record.get("context_summary"), page_record.get("page_traits"), page_record.get("detected_elements"))
    buckets = collect_candidate_bucket_counts(page_record)

    ink_ratio = as_float(audit_record.get("ink_ratio"))
    dark_pixels = as_float(audit_record.get("dark_pixel_count"))
    h_lines = as_float(audit_record.get("horizontal_line_rows"))
    v_lines = as_float(audit_record.get("vertical_line_cols"))
    large_components = as_float(audit_record.get("large_component_count"))
    largest_component_pixels = as_float(audit_record.get("largest_component_pixels"))
    table_grid_score_raw = as_float(audit_record.get("table_grid_score"))
    visual_score_raw = as_float(audit_record.get("visual_score"))

    ink_score = clamp(ink_ratio / 0.12)
    line_density_score = clamp((h_lines * 1.25 + v_lines) / 70.0)
    component_density_score = clamp(math.log1p(max(0.0, large_components)) / math.log1p(120.0))
    largest_component_ratio = clamp(largest_component_pixels / max(1.0, dark_pixels))
    table_grid_score = clamp(table_grid_score_raw / 60.0)
    visual_score = clamp(visual_score_raw / 18.0)

    has_ocr = boolish(page_record.get("ocr_present")) or "ocr_text_present" in page_record.get("page_traits", [])
    has_source_text = buckets.get("source_text_evidence", 0) > 0
    has_verified_parts = buckets.get("verified_part_evidence", 0) > 0 or table_stats.get("answer_support_row_count", 0) > 0
    table_rows = as_float(table_stats.get("normalized_row_count"))
    table_cells = as_float(table_stats.get("normalized_cell_count"))

    # Ink/layout is a routing signal, not source truth.  A low-ink page may
    # still contain a small but important revision note, title block, or part
    # reference.  Therefore we separate an ink-based blank *candidate* from a
    # confirmed blank.  A page is confirmed blank only when low ink also lacks
    # OCR/source text, verified part/table support, and query-relevant context.
    likely_blank = boolish(audit_record.get("likely_blank")) or role == "blank"
    ink_blank_candidate_score = 1.0 if likely_blank or ink_ratio <= 0.004 else clamp(1.0 - (ink_ratio / 0.018)) * 0.75

    role_table = 1.0 if role == "table" else 0.0
    role_parts = 1.0 if role == "parts_list" else 0.0
    role_figure = 1.0 if role == "figure" else 0.0
    role_text = 1.0 if role in {"front_matter", "procedure"} else 0.0
    has_table_structure = 1.0 if table_rows > 0 and table_cells > 0 else 0.0
    has_part_context = 1.0 if has_verified_parts or "part" in context or "figure" in context else 0.0
    has_chart_words = 1.0 if any(word in context for word in ("chart", "plot", "axis", "graph", "curve")) else 0.0
    has_revision_words = 1.0 if any(word in context for word in ("revision", "effective pages", "record of revisions")) else 0.0

    meaningful_content_score = clamp(
        0.30 * (1.0 if has_ocr else 0.0)
        + 0.30 * (1.0 if has_source_text else 0.0)
        + 0.20 * (1.0 if has_verified_parts else 0.0)
        + 0.15 * (1.0 if table_rows > 0 or table_cells > 0 else 0.0)
        + 0.15 * has_revision_words
    )
    confirmed_blank_score = round4(ink_blank_candidate_score * (1.0 - meaningful_content_score))
    blank_score = confirmed_blank_score

    table_score = clamp(
        0.38 * table_grid_score
        + 0.24 * line_density_score
        + 0.20 * has_table_structure
        + 0.10 * role_table
        + 0.08 * role_parts
    )

    parts_list_score = clamp(
        0.40 * role_parts
        + 0.25 * has_part_context
        + 0.15 * has_verified_parts
        + 0.10 * table_score
        + 0.10 * visual_score
    )

    diagram_score = clamp(
        0.28 * visual_score
        + 0.22 * component_density_score
        + 0.18 * largest_component_ratio
        + 0.14 * role_figure
        + 0.10 * role_parts
        + 0.08 * has_part_context
        - 0.10 * table_grid_score
    )

    chart_score = clamp(
        0.40 * visual_score
        + 0.20 * component_density_score
        + 0.25 * has_chart_words
        + 0.10 * role_figure
        - 0.25 * table_score
        - 0.25 * role_parts
        - 0.20 * role_text
        - 0.20 * blank_score
        - 0.10 * has_revision_words
    )

    text_score = clamp(
        0.22 * (1.0 if has_ocr else 0.0)
        + 0.22 * (1.0 if has_source_text else 0.0)
        + 0.18 * role_text
        + 0.14 * boolish(audit_record.get("likely_text_heavy"))
        + 0.12 * has_revision_words
        + 0.12 * (1.0 - min(table_score, 0.8))
    )

    mixed_score = clamp(min(table_score, max(diagram_score, parts_list_score)))

    return {
        "ink_score": round4(ink_score),
        "blank_score": round4(blank_score),
        "ink_blank_candidate_score": round4(ink_blank_candidate_score),
        "meaningful_content_score": round4(meaningful_content_score),
        "confirmed_blank_score": round4(confirmed_blank_score),
        "line_density_score": round4(line_density_score),
        "component_density_score": round4(component_density_score),
        "largest_component_ratio": round4(largest_component_ratio),
        "table_grid_score_normalized": round4(table_grid_score),
        "visual_score_normalized": round4(visual_score),
        "table_score": round4(table_score),
        "parts_list_score": round4(parts_list_score),
        "diagram_score": round4(diagram_score),
        "chart_score": round4(chart_score),
        "text_score": round4(text_score),
        "mixed_layout_score": round4(mixed_score),
    }


def choose_layout_class(scores: dict[str, float], audit_record: dict[str, Any], table_stats: dict[str, Any]) -> str:
    role = str(audit_record.get("role") or "").lower()
    if scores.get("confirmed_blank_score", scores.get("blank_score", 0)) >= 0.90:
        return "blank"
    if scores.get("ink_blank_candidate_score", 0) >= 0.90 and scores.get("meaningful_content_score", 0) > 0:
        return "sparse_ink_text_or_source_trace"
    if scores["table_score"] >= 0.62 and table_stats.get("normalized_row_count", 0) > 0:
        if scores["parts_list_score"] >= 0.62:
            return "parts_list_table"
        return "table_or_grid"
    if scores["mixed_layout_score"] >= 0.52 and role in {"parts_list", "figure"}:
        return "mixed_table_and_diagram"
    if scores["parts_list_score"] >= 0.62:
        return "parts_list_or_illustrated_parts"
    if scores["chart_score"] >= 0.62:
        return "chart_or_plot"
    if scores["diagram_score"] >= 0.58:
        return "figure_or_diagram"
    if scores["text_score"] >= 0.48:
        return "text_heavy"
    return "unknown_visual_layout"


def recommended_routes_for_class(layout_class: str, scores: dict[str, float]) -> list[str]:
    routes = ["source_trace_route", "graph_source_compare_route"]
    if layout_class == "blank":
        return routes + ["blank_page_review_route"]
    if layout_class in {"text_heavy", "unknown_visual_layout", "sparse_ink_text_or_source_trace"}:
        routes.append("ocr_text_route")
    if layout_class == "sparse_ink_text_or_source_trace":
        routes.extend(["sparse_ink_source_validation_route", "region_ocr_retry_route"])
    if layout_class in {"table_or_grid", "parts_list_table", "mixed_table_and_diagram"}:
        routes.extend(["table_structure_route", "table_cell_normalizer_route"])
    if layout_class in {"parts_list_table", "parts_list_or_illustrated_parts", "mixed_table_and_diagram"}:
        routes.extend(["part_catalog_compare_route", "callout_candidate_route"])
    if layout_class in {"figure_or_diagram", "parts_list_or_illustrated_parts", "mixed_table_and_diagram"}:
        routes.extend(["visual_region_route", "catalog_graph_visual_compare_route"])
    if layout_class == "chart_or_plot":
        routes.extend(["chart_region_route", "chart_axis_label_ocr_route"])
    if scores.get("blank_score", 0) < 0.9:
        routes.append("fishnet_retry_planner_route")
    # Stable order without duplicates.
    return list(dict.fromkeys(routes))


def fishnet_plan_for_record(layout_class: str, scores: dict[str, float]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    layer = 0
    plan.append({"fishnet_layer": layer, "layer_name": "normal_extraction", "retry_route": "use_existing_extractor_outputs"})
    layer += 1
    if layout_class == "sparse_ink_text_or_source_trace":
        plan.append({"fishnet_layer": layer, "layer_name": "sparse_ink_validation", "retry_route": "source_trace_plus_region_ocr_validation"})
        layer += 1
    if layout_class != "blank" and scores.get("text_score", 0) < 0.45:
        plan.append({"fishnet_layer": layer, "layer_name": "ocr_cleanup_retry", "retry_route": "ocr_cleanup_or_region_ocr"})
        layer += 1
    if layout_class in {"table_or_grid", "parts_list_table", "mixed_table_and_diagram"}:
        plan.append({"fishnet_layer": layer, "layer_name": "table_region_retry", "retry_route": "table_crop_tile_and_cell_normalize"})
        layer += 1
    if layout_class in {"figure_or_diagram", "parts_list_or_illustrated_parts", "mixed_table_and_diagram", "chart_or_plot"}:
        plan.append({"fishnet_layer": layer, "layer_name": "visual_region_retry", "retry_route": "crop_visual_regions_then_ocr_labels"})
        layer += 1
    plan.append({"fishnet_layer": layer, "layer_name": "compare_outputs", "retry_route": "ocr_catalog_graph_source_compare"})
    layer += 1
    plan.append({"fishnet_layer": layer, "layer_name": "review_or_trust_downgrade", "retry_route": "human_review_if_still_unverified"})
    return plan


def build_calibrated_record(
    page_record: dict[str, Any],
    audit_record: dict[str, Any],
    figure_record: dict[str, Any],
    table_records: list[dict[str, Any]],
) -> dict[str, Any]:
    page_id = page_record.get("page_id") or audit_record.get("page_id")
    if not page_id:
        raise ValueError("Page record is missing page_id")
    table_stats = table_normalizer_page_stats(table_records)
    scores = compute_layout_scores(page_record, audit_record, figure_record, table_stats)
    layout_class = choose_layout_class(scores, audit_record, table_stats)

    previous_class = audit_record.get("classification") or "unknown"
    previous_visual_type = figure_record.get("visual_type") or ""
    reclassified = False
    reclassification_reason = ""
    if previous_visual_type == "chart_or_plot_candidate" and layout_class != "chart_or_plot":
        reclassified = True
        reclassification_reason = "chart_candidate_demoted_by_ink_layout_math"
    elif str(previous_class) == "likely_figure_or_diagram" and layout_class in {"text_heavy", "blank", "table_or_grid", "parts_list_table"}:
        reclassified = True
        reclassification_reason = "broad_figure_signal_recalibrated_by_layout"
    elif str(previous_class) == "likely_table_or_grid" and layout_class not in {"table_or_grid", "parts_list_table", "mixed_table_and_diagram"}:
        reclassified = True
        reclassification_reason = "table_grid_signal_recalibrated_by_layout"

    source_page_role = audit_record.get("role") or page_record.get("page_role") or page_record.get("role") or "unknown"
    comparison_targets = [
        "ocr_depth",
        "source_trace",
        "page_context",
        "page_element_registry",
        "table_cell_normalizer",
        "figure_chart_understanding",
        "catalog_part_graph",
        "source_citation",
        "trust_authority",
    ]
    if layout_class == "blank":
        comparison_targets = ["source_trace", "page_context", "blank_page_review"]
    elif layout_class == "sparse_ink_text_or_source_trace":
        comparison_targets = ["ocr_depth", "source_trace", "page_context", "source_citation", "region_ocr_retry", "trust_authority"]

    calibrated_visual_type = {
        "blank": "blank_page",
        "sparse_ink_text_or_source_trace": "sparse_ink_text_or_source_trace_layout",
        "text_heavy": "text_layout",
        "table_or_grid": "table_or_grid_layout",
        "parts_list_table": "parts_list_table_layout",
        "parts_list_or_illustrated_parts": "parts_list_or_illustrated_parts_layout",
        "figure_or_diagram": "figure_or_diagram_layout",
        "mixed_table_and_diagram": "mixed_table_and_diagram_layout",
        "chart_or_plot": "chart_or_plot_layout",
        "unknown_visual_layout": "unknown_visual_layout",
    }[layout_class]

    needs_vision_model = layout_class in {"figure_or_diagram", "mixed_table_and_diagram", "parts_list_or_illustrated_parts", "chart_or_plot"}
    requires_catalog_compare = layout_class in {"parts_list_table", "parts_list_or_illustrated_parts", "mixed_table_and_diagram", "figure_or_diagram"}
    needs_human_review = needs_vision_model or scores.get("text_score", 0) < 0.3 or layout_class in {"unknown_visual_layout", "sparse_ink_text_or_source_trace"}
    if layout_class in {"blank", "text_heavy", "table_or_grid"}:
        needs_human_review = False

    return {
        "calibration_id": stable_id("ink_layout", page_id),
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM_NAME,
        "page_id": page_id,
        "page_number": page_number_from_page_id(page_id),
        "page_label": audit_record.get("page_label") or page_record.get("page_label"),
        "source_page_role": source_page_role,
        "previous_image_classification": previous_class,
        "previous_visual_type": previous_visual_type,
        "calibrated_layout_class": layout_class,
        "calibrated_visual_type": calibrated_visual_type,
        "ink_blank_candidate": scores.get("ink_blank_candidate_score", 0) >= 0.90,
        "source_confirmed_blank": layout_class == "blank",
        "blank_status": "confirmed_blank" if layout_class == "blank" else ("sparse_ink_not_source_truth" if scores.get("ink_blank_candidate_score", 0) >= 0.90 else "not_blank_candidate"),
        "blank_confirmation_policy": "low_ink_requires_no_ocr_no_source_text_no_part_or_table_support_no_context_before_blank",
        "reclassified": reclassified,
        "reclassification_reason": reclassification_reason,
        "ink_layout_metrics": {
            "ink_ratio": round4(as_float(audit_record.get("ink_ratio"))),
            "dark_pixel_count": as_int(audit_record.get("dark_pixel_count")),
            "horizontal_line_rows": as_int(audit_record.get("horizontal_line_rows")),
            "vertical_line_cols": as_int(audit_record.get("vertical_line_cols")),
            "large_component_count": as_int(audit_record.get("large_component_count")),
            "largest_component_pixels": as_int(audit_record.get("largest_component_pixels")),
            "table_grid_score_raw": round4(as_float(audit_record.get("table_grid_score"))),
            "visual_score_raw": round4(as_float(audit_record.get("visual_score"))),
            "sample_width": as_int(audit_record.get("sample_width")),
            "sample_height": as_int(audit_record.get("sample_height")),
        },
        "calibrated_scores": scores,
        "table_context": table_stats,
        "page_traits": page_record.get("page_traits") or [],
        "detected_elements": page_record.get("detected_elements") or [],
        "recommended_extraction_routes": recommended_routes_for_class(layout_class, scores),
        "fishnet_retry_plan": fishnet_plan_for_record(layout_class, scores),
        "comparison_targets": comparison_targets,
        "requires_catalog_compare": requires_catalog_compare,
        "needs_vision_model": needs_vision_model,
        "needs_human_review": needs_human_review,
        "authority": VISUAL_ROUTE_AUTHORITY,
        "rag_bucket": "visual_ink_layout_retrieval_helper",
        "trust_tier": "C" if needs_vision_model or layout_class == "unknown_visual_layout" else "B",
        "answer_use_policy": "route_only_then_require_source_catalog_graph_verification",
        "can_embed": True,
        "can_retrieve": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "visual_answer_allowed": False,
        "unverified_visual_claim": False,
        "source_truth_mutations_performed": 0,
        "public_summary": safe_public_text(
            f"Page {page_number_from_page_id(page_id) or page_id} calibrated as {layout_class}; "
            f"ink={scores['ink_score']}, table={scores['table_score']}, diagram={scores['diagram_score']}, "
            f"chart={scores['chart_score']}, text={scores['text_score']}."
        ),
    }


def compute_summary(records: list[dict[str, Any]], source_summaries: dict[str, Any]) -> dict[str, Any]:
    layout_counts = Counter(r.get("calibrated_layout_class") for r in records)
    visual_counts = Counter(r.get("calibrated_visual_type") for r in records)
    previous_counts = Counter(r.get("previous_visual_type") or r.get("previous_image_classification") for r in records)
    role_counts = Counter(r.get("source_page_role") for r in records)
    route_counts = Counter(route for r in records for route in r.get("recommended_extraction_routes", []))

    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM_NAME,
        "answer_status": "VISUAL_INK_LAYOUT_CALIBRATION_ONLY",
        "final_answer_allowed": False,
        "calibrated_page_count": len(records),
        "ink_metric_page_count": sum(1 for r in records if r.get("ink_layout_metrics")),
        "blank_page_count": layout_counts.get("blank", 0),
        "confirmed_blank_page_count": layout_counts.get("blank", 0),
        "ink_blank_candidate_count": sum(1 for r in records if r.get("ink_blank_candidate")),
        "sparse_ink_page_count": layout_counts.get("sparse_ink_text_or_source_trace", 0),
        "text_heavy_page_count": layout_counts.get("text_heavy", 0),
        "table_or_grid_page_count": layout_counts.get("table_or_grid", 0) + layout_counts.get("parts_list_table", 0),
        "parts_list_or_diagram_page_count": layout_counts.get("parts_list_or_illustrated_parts", 0)
        + layout_counts.get("parts_list_table", 0)
        + layout_counts.get("mixed_table_and_diagram", 0),
        "figure_or_diagram_page_count": layout_counts.get("figure_or_diagram", 0)
        + layout_counts.get("mixed_table_and_diagram", 0)
        + layout_counts.get("parts_list_or_illustrated_parts", 0),
        "chart_or_plot_page_count": layout_counts.get("chart_or_plot", 0),
        "unknown_visual_layout_count": layout_counts.get("unknown_visual_layout", 0),
        "low_ink_content_preserved_count": layout_counts.get("sparse_ink_text_or_source_trace", 0),
        "reclassified_page_count": sum(1 for r in records if r.get("reclassified")),
        "chart_candidate_demoted_count": sum(
            1 for r in records if r.get("reclassification_reason") == "chart_candidate_demoted_by_ink_layout_math"
        ),
        "needs_vision_model_count": sum(1 for r in records if r.get("needs_vision_model")),
        "needs_human_review_count": sum(1 for r in records if r.get("needs_human_review")),
        "requires_catalog_compare_count": sum(1 for r in records if r.get("requires_catalog_compare")),
        "pages_with_recommended_routes_count": sum(1 for r in records if r.get("recommended_extraction_routes")),
        "pages_with_fishnet_plan_count": sum(1 for r in records if r.get("fishnet_retry_plan")),
        "visual_answer_allowed_count": sum(1 for r in records if boolish(r.get("visual_answer_allowed")) or boolish(r.get("can_answer_directly"))),
        "unverified_visual_claim_count": sum(1 for r in records if boolish(r.get("unverified_visual_claim")) or boolish(r.get("can_prove_claims"))),
        "source_truth_mutation_allowed_count": sum(1 for r in records if boolish(r.get("can_mutate_source_truth"))),
        "unsafe_visual_layout_record_count": sum(1 for r in records if is_unsafe_record(r)),
        "layout_class_counts": dict(layout_counts),
        "calibrated_visual_type_counts": dict(visual_counts),
        "previous_visual_or_image_counts": dict(previous_counts),
        "source_page_role_counts": dict(role_counts),
        "route_counts": dict(route_counts),
        "image_recognition_summary": source_summaries.get("image_recognition_summary") or {},
        "figure_chart_summary": source_summaries.get("figure_chart_summary") or {},
    }


def is_unsafe_record(record: dict[str, Any]) -> bool:
    if boolish(record.get("can_answer_directly")) or boolish(record.get("can_prove_claims")):
        return True
    if boolish(record.get("can_mutate_source_truth")) or as_int(record.get("source_truth_mutations_performed")):
        return True
    # Check only fields intended to be public; internal source artifacts are allowed elsewhere.
    public_text = text_blob(record.get("public_summary"), record.get("calibrated_layout_class"), record.get("calibrated_visual_type"))
    return any(marker.lower() in public_text for marker in (m.lower() for m in FORBIDDEN_USER_VISIBLE_MARKERS))


def build_quality(
    payload: dict[str, Any],
    *,
    require_page_count: int | None = None,
    min_calibrated_pages: int = 1,
    min_ink_metric_pages: int = 1,
    min_blank_pages: int = 0,
    min_reclassified_pages: int = 0,
    max_chart_pages: int | None = None,
) -> dict[str, Any]:
    summary = payload.get("summary") or {}
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, actual: Any, expected: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "actual": actual, "expected": expected})

    count = as_int(summary.get("calibrated_page_count"))
    add("min_calibrated_pages", count >= min_calibrated_pages, count, f">= {min_calibrated_pages}")
    if require_page_count is not None:
        add("require_page_count", count == require_page_count, count, require_page_count)
    add(
        "min_ink_metric_pages",
        as_int(summary.get("ink_metric_page_count")) >= min_ink_metric_pages,
        summary.get("ink_metric_page_count"),
        f">= {min_ink_metric_pages}",
    )
    add("min_blank_pages", as_int(summary.get("blank_page_count")) >= min_blank_pages, summary.get("blank_page_count"), f">= {min_blank_pages}")
    add(
        "min_reclassified_pages",
        as_int(summary.get("reclassified_page_count")) >= min_reclassified_pages,
        summary.get("reclassified_page_count"),
        f">= {min_reclassified_pages}",
    )
    if max_chart_pages is not None:
        add(
            "max_chart_pages",
            as_int(summary.get("chart_or_plot_page_count")) <= max_chart_pages,
            summary.get("chart_or_plot_page_count"),
            f"<= {max_chart_pages}",
        )
    add("visual_answer_allowed_zero", as_int(summary.get("visual_answer_allowed_count")) == 0, summary.get("visual_answer_allowed_count"), 0)
    add("unverified_visual_claim_zero", as_int(summary.get("unverified_visual_claim_count")) == 0, summary.get("unverified_visual_claim_count"), 0)
    add("source_truth_mutation_zero", as_int(summary.get("source_truth_mutation_allowed_count")) == 0, summary.get("source_truth_mutation_allowed_count"), 0)
    add("unsafe_visual_layout_zero", as_int(summary.get("unsafe_visual_layout_record_count")) == 0, summary.get("unsafe_visual_layout_record_count"), 0)
    add(
        "routes_present",
        as_int(summary.get("pages_with_recommended_routes_count")) >= min_calibrated_pages,
        summary.get("pages_with_recommended_routes_count"),
        f">= {min_calibrated_pages}",
    )
    add(
        "fishnet_present",
        as_int(summary.get("pages_with_fishnet_plan_count")) >= min_calibrated_pages,
        summary.get("pages_with_fishnet_plan_count"),
        f">= {min_calibrated_pages}",
    )

    status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    return {
        "schema_version": SCHEMA_VERSION,
        "quality_status": status,
        "status": status,
        "checked_at": utc_now(),
        "checks": checks,
        "summary": summary,
    }


def build_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    lines = [
        "# TRACE-Net Visual Ink / Layout Calibrator v1",
        "",
        f"**Status:** {payload.get('status')}",
        f"**Quality:** {payload.get('quality_status')}",
        "",
        "## What this does",
        "",
        "This is a math-based visual routing layer. It uses ink ratio, line counts, connected components, grid score, and existing page roles to calibrate visual/table/chart/figure routing before any vision model is used.",
        "",
        "It is route-only: it cannot answer directly, prove claims, or mutate source truth.",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "calibrated_page_count",
        "ink_metric_page_count",
        "blank_page_count",
        "confirmed_blank_page_count",
        "ink_blank_candidate_count",
        "sparse_ink_page_count",
        "text_heavy_page_count",
        "table_or_grid_page_count",
        "parts_list_or_diagram_page_count",
        "figure_or_diagram_page_count",
        "chart_or_plot_page_count",
        "reclassified_page_count",
        "chart_candidate_demoted_count",
        "needs_vision_model_count",
        "needs_human_review_count",
        "visual_answer_allowed_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend(["", "## Layout classes", ""])
    for key, value in sorted((summary.get("layout_class_counts") or {}).items()):
        lines.append(f"- {key}: {value}")
    return "\n".join(lines) + "\n"


def build_html(markdown_text: str) -> str:
    escaped = html.escape(markdown_text)
    return f"<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Visual Ink Layout Calibrator v1</title></head><body><pre>{escaped}</pre></body></html>"


def build_visual_ink_layout_calibrator(
    *,
    page_registry_path: str | Path,
    image_recognition_audit_path: str | Path,
    figure_chart_understanding_path: str | Path | None = None,
    table_cell_normalizer_path: str | Path | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    require_page_count: int | None = None,
    min_calibrated_pages: int = 1,
    min_ink_metric_pages: int = 1,
    min_blank_pages: int = 0,
    min_reclassified_pages: int = 0,
    max_chart_pages: int | None = None,
    write_quality: bool = False,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    page_records = load_records(page_registry_path)
    audit_payload = read_json(image_recognition_audit_path, {})
    audit_records = audit_payload.get("records", []) if isinstance(audit_payload, dict) else []
    if not isinstance(audit_records, list):
        audit_records = []
    audit_summary = audit_payload.get("summary", {}) if isinstance(audit_payload, dict) and isinstance(audit_payload.get("summary"), dict) else {}

    figure_payload = read_json(figure_chart_understanding_path, {})
    figure_records = figure_payload.get("records", []) if isinstance(figure_payload, dict) else []
    if not isinstance(figure_records, list):
        figure_records = []
    figure_summary = figure_payload.get("summary", {}) if isinstance(figure_payload, dict) and isinstance(figure_payload.get("summary"), dict) else {}

    table_payload = read_json(table_cell_normalizer_path, {})
    table_records = table_payload.get("records", []) if isinstance(table_payload, dict) else []
    if not isinstance(table_records, list):
        table_records = []

    audit_index = {r.get("page_id"): r for r in audit_records if isinstance(r, dict) and r.get("page_id")}
    figure_index = {r.get("page_id"): r for r in figure_records if isinstance(r, dict) and r.get("page_id")}
    table_index = index_by_page(table_records)

    records: list[dict[str, Any]] = []
    for page_record in sorted(page_records, key=lambda r: str(r.get("page_id", ""))):
        page_id = page_record.get("page_id")
        if not isinstance(page_id, str) or not page_id:
            continue
        audit_record = audit_index.get(page_id, {})
        figure_record = figure_index.get(page_id, {})
        records.append(build_calibrated_record(page_record, audit_record, figure_record, table_index.get(page_id, [])))

    source_summaries = {
        "image_recognition_summary": audit_summary,
        "figure_chart_summary": figure_summary,
    }
    summary = compute_summary(records, source_summaries)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM_NAME,
        "status": "VISUAL_INK_LAYOUT_CALIBRATION_BUILT",
        "quality_status": "UNKNOWN",
        "created_at": utc_now(),
        "source_paths": {
            "page_registry": str(page_registry_path),
            "image_recognition_audit": str(image_recognition_audit_path),
            "figure_chart_understanding": str(figure_chart_understanding_path) if figure_chart_understanding_path else None,
            "table_cell_normalizer": str(table_cell_normalizer_path) if table_cell_normalizer_path else None,
        },
        "summary": summary,
        "records": records,
    }

    quality = build_quality(
        payload,
        require_page_count=require_page_count,
        min_calibrated_pages=min_calibrated_pages,
        min_ink_metric_pages=min_ink_metric_pages,
        min_blank_pages=min_blank_pages,
        min_reclassified_pages=min_reclassified_pages,
        max_chart_pages=max_chart_pages,
    )
    payload["quality"] = quality
    payload["quality_status"] = quality["quality_status"]

    report_path = output / "trace_net_visual_ink_layout_calibrator_v1.json"
    records_path = output / "trace_net_visual_ink_layout_calibrator_v1_records.jsonl"
    routes_path = output / "trace_net_visual_ink_layout_calibrator_v1_routes.jsonl"
    summary_path = output / "trace_net_visual_ink_layout_calibrator_v1_summary.json"
    manifest_path = output / "trace_net_visual_ink_layout_calibrator_v1_manifest.json"
    quality_path = output / "trace_net_visual_ink_layout_calibrator_v1_quality.json"
    md_path = output / "trace_net_visual_ink_layout_calibrator_v1.md"
    html_path = output / "trace_net_visual_ink_layout_calibrator_v1.html"

    write_json(report_path, payload)
    write_jsonl(records_path, records)
    write_jsonl(
        routes_path,
        (
            {
                "page_id": r["page_id"],
                "calibrated_layout_class": r["calibrated_layout_class"],
                "recommended_extraction_routes": r["recommended_extraction_routes"],
                "fishnet_retry_plan": r["fishnet_retry_plan"],
            }
            for r in records
        ),
    )
    write_json(summary_path, summary)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "report_path": str(report_path),
        "records_path": str(records_path),
        "routes_path": str(routes_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "record_count": len(records),
        "quality_status": payload["quality_status"],
    }
    write_json(manifest_path, manifest)
    if write_quality:
        write_json(quality_path, quality)
    markdown_text = build_markdown(payload)
    md_path.write_text(markdown_text, encoding="utf-8")
    html_path.write_text(build_html(markdown_text), encoding="utf-8")

    payload["report_path"] = str(report_path)
    payload["records_path"] = str(records_path)
    payload["routes_path"] = str(routes_path)
    payload["summary_path"] = str(summary_path)
    payload["manifest_path"] = str(manifest_path)
    payload["quality_path"] = str(quality_path)
    payload["markdown_path"] = str(md_path)
    payload["html_path"] = str(html_path)
    # Re-write with output paths included.
    write_json(report_path, payload)
    return payload


def print_build_summary(payload: dict[str, Any]) -> None:
    summary = payload.get("summary") or {}
    print("TRACE-Net visual ink / layout calibrator v1")
    print(f" Status: {payload.get('status')}")
    print(f" Quality status: {payload.get('quality_status')}")
    for key in [
        "calibrated_page_count",
        "ink_metric_page_count",
        "blank_page_count",
        "confirmed_blank_page_count",
        "ink_blank_candidate_count",
        "sparse_ink_page_count",
        "text_heavy_page_count",
        "table_or_grid_page_count",
        "parts_list_or_diagram_page_count",
        "figure_or_diagram_page_count",
        "chart_or_plot_page_count",
        "reclassified_page_count",
        "chart_candidate_demoted_count",
        "needs_vision_model_count",
        "needs_human_review_count",
        "visual_answer_allowed_count",
        "unverified_visual_claim_count",
        "unsafe_visual_layout_record_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    for key in ["report_path", "quality_path"]:
        if payload.get(key):
            print(f" {key}: {payload.get(key)}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net visual ink/layout calibration records v1.")
    parser.add_argument("--page-registry", required=True)
    parser.add_argument("--image-recognition-audit", required=True)
    parser.add_argument("--figure-chart-understanding")
    parser.add_argument("--table-cell-normalizer")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--min-calibrated-pages", type=int, default=1)
    parser.add_argument("--min-ink-metric-pages", type=int, default=1)
    parser.add_argument("--min-blank-pages", type=int, default=0)
    parser.add_argument("--min-reclassified-pages", type=int, default=0)
    parser.add_argument("--max-chart-pages", type=int)
    parser.add_argument("--quality", action="store_true", help="Write quality JSON and return nonzero on quality failure.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        payload = build_visual_ink_layout_calibrator(
            page_registry_path=args.page_registry,
            image_recognition_audit_path=args.image_recognition_audit,
            figure_chart_understanding_path=args.figure_chart_understanding,
            table_cell_normalizer_path=args.table_cell_normalizer,
            output_dir=args.output_dir,
            require_page_count=args.require_page_count,
            min_calibrated_pages=args.min_calibrated_pages,
            min_ink_metric_pages=args.min_ink_metric_pages,
            min_blank_pages=args.min_blank_pages,
            min_reclassified_pages=args.min_reclassified_pages,
            max_chart_pages=args.max_chart_pages,
            write_quality=args.quality,
        )
        print_build_summary(payload)
        if args.quality and payload.get("quality_status") != "PASS":
            return 1
        return 0
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"TRACE-Net visual ink/layout calibrator failed: {exc}")
        return 1


def check_quality_from_report(
    *,
    report_path: str | Path,
    require_page_count: int | None = None,
    min_calibrated_pages: int = 1,
    min_ink_metric_pages: int = 1,
    min_blank_pages: int = 0,
    min_reclassified_pages: int = 0,
    max_chart_pages: int | None = None,
    write_json_quality: bool = False,
) -> dict[str, Any]:
    payload = read_json(report_path, {})
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid report: {report_path}")
    quality = build_quality(
        payload,
        require_page_count=require_page_count,
        min_calibrated_pages=min_calibrated_pages,
        min_ink_metric_pages=min_ink_metric_pages,
        min_blank_pages=min_blank_pages,
        min_reclassified_pages=min_reclassified_pages,
        max_chart_pages=max_chart_pages,
    )
    if write_json_quality:
        out = Path(report_path).with_name("trace_net_visual_ink_layout_calibrator_v1_quality.json")
        write_json(out, quality)
        quality["quality_path"] = str(out)
    return quality


def quality_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net visual ink/layout calibrator v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--require-page-count", type=int)
    parser.add_argument("--min-calibrated-pages", type=int, default=1)
    parser.add_argument("--min-ink-metric-pages", type=int, default=1)
    parser.add_argument("--min-blank-pages", type=int, default=0)
    parser.add_argument("--min-reclassified-pages", type=int, default=0)
    parser.add_argument("--max-chart-pages", type=int)
    parser.add_argument("--write-json", action="store_true")
    return parser


def print_quality_summary(quality: dict[str, Any]) -> None:
    summary = quality.get("summary") or {}
    print("TRACE-Net visual ink/layout calibrator v1 quality")
    print(f" Status: {quality.get('quality_status')}")
    for key in [
        "calibrated_page_count",
        "ink_metric_page_count",
        "blank_page_count",
        "confirmed_blank_page_count",
        "ink_blank_candidate_count",
        "sparse_ink_page_count",
        "text_heavy_page_count",
        "table_or_grid_page_count",
        "parts_list_or_diagram_page_count",
        "figure_or_diagram_page_count",
        "chart_or_plot_page_count",
        "reclassified_page_count",
        "chart_candidate_demoted_count",
        "visual_answer_allowed_count",
        "unverified_visual_claim_count",
        "unsafe_visual_layout_record_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    if quality.get("quality_path"):
        print(f" quality_path: {quality.get('quality_path')}")


def quality_main(argv: list[str] | None = None) -> int:
    args = quality_arg_parser().parse_args(argv)
    try:
        quality = check_quality_from_report(
            report_path=args.report_path,
            require_page_count=args.require_page_count,
            min_calibrated_pages=args.min_calibrated_pages,
            min_ink_metric_pages=args.min_ink_metric_pages,
            min_blank_pages=args.min_blank_pages,
            min_reclassified_pages=args.min_reclassified_pages,
            max_chart_pages=args.max_chart_pages,
            write_json_quality=args.write_json,
        )
        print_quality_summary(quality)
        return 0 if quality.get("quality_status") == "PASS" else 1
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"TRACE-Net visual ink/layout quality check failed: {exc}")
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
