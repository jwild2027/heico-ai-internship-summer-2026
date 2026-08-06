"""TRACE-Net Table Full Enclosure BBox Reconstructor v1.

Read-only, conservative table bbox reconstruction stage for TRACE-Net table
localization.

The prior visual-localization path proved useful as QA, but some visual bboxes
became too tight and cut off columns, header bands, or rows. The presence
verifier now marks those records with ``full_table_enclosure_recommended``.
This module consumes that recommendation and reconstructs a safer bbox that is
biased toward full table containment rather than visual tightness.

Algorithmic intent:
- If the presence verifier recommends full enclosure, do not trust a tight
  visual candidate by itself.
- Use the structure localizer input bbox as the safe containment anchor.
- When structure QA says a visual candidate cut columns/rows, reconstruct a
  larger table boundary rather than accepting the visual crop or blindly using
  the old selected bbox.
- For split-column table pages, expand toward a whole-table enclosure that is
  biased to contain both column groups and the full row extent.
- Step-0 full-page mode can intentionally set extraction-ready table bboxes to
  the whole source page while keeping review-only/image-like pages blocked from
  table extraction.
- Preserve provenance and QA flags so the result remains auditable.

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
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    from PIL import Image
except Exception:  # pragma: no cover - image resolution is optional in unit tests.
    Image = None  # type: ignore

SCHEMA_VERSION = "trace_net_table_full_enclosure_bbox_reconstructor_v1"
QUALITY_SCHEMA_VERSION = "trace_net_table_full_enclosure_bbox_reconstructor_v1_quality"
STATUS_BUILT = "TABLE_FULL_ENCLOSURE_BBOX_RECONSTRUCTOR_BUILT"
STATUS_NOT_READY = "TABLE_FULL_ENCLOSURE_BBOX_RECONSTRUCTOR_NOT_READY"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/table_full_enclosure_bbox_reconstructor")
IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".webp", ".bmp"}

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



def page_number_token(page_id: Any) -> str | None:
    text = str(page_id or "")
    match = re.search(r"p(\d{6})\b", text, flags=re.IGNORECASE)
    if match:
        return f"p{match.group(1)}"
    match = re.search(r"(\d{6})", text)
    if match:
        return f"p{match.group(1)}"
    return None


def normalize_path_value(value: Any, image_root: Path | None = None) -> Path | None:
    if not value:
        return None
    raw = str(value).strip().replace("\\", "/")
    if not raw:
        return None
    path = Path(raw)
    if path.exists():
        return path
    if image_root is not None:
        candidate = image_root / raw
        if candidate.exists():
            return candidate
        basename = Path(raw).name
        if basename:
            for match in image_root.rglob(basename):
                if match.suffix.lower() in IMAGE_EXTENSIONS:
                    return match
    return None


def build_image_index(image_root: Path | None, max_files_scanned: int = 25_000) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = {}
    if image_root is None or not image_root.exists():
        return index
    scanned = 0
    for path in image_root.rglob("*"):
        if scanned >= max_files_scanned:
            break
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        scanned += 1
        lower = path.name.lower()
        for match in re.finditer(r"p\d{6}|\d{6}", lower):
            token = match.group(0)
            if token.isdigit():
                token = f"p{token}"
            index.setdefault(token.lower(), []).append(path)
    return index


def resolve_image_path(record: Mapping[str, Any], image_root: Path | None, image_index: Mapping[str, list[Path]]) -> tuple[Path | None, str]:
    for key in ("image_path", "source_image_path", "page_image_path", "tiff_path", "source_page_image_path"):
        path = normalize_path_value(record.get(key), image_root)
        if path and path.exists():
            return path, key
    token = page_number_token(record.get("page_id"))
    if token:
        matches = image_index.get(token.lower()) or image_index.get(token)
        if matches:
            return matches[0], "image_root_page_token_scan"
    return None, "not_found"


def image_dimensions(path: Path | None) -> tuple[int | None, int | None]:
    if path is None or Image is None:
        return None, None
    try:
        with Image.open(path) as img:
            return int(img.width), int(img.height)
    except Exception:
        return None, None


def page_bbox_from_record(record: Mapping[str, Any], image_root: Path | None = None, image_index: Mapping[str, list[Path]] | None = None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Resolve the full source-page bbox for temporary step-0 extraction.

    Prefer actual page image dimensions. If a record already carries dimensions,
    use them; otherwise locate the page image by explicit image path or page-id
    token. This is deliberately advisory and never mutates source truth.
    """
    for width_key, height_key in (
        ("image_width", "image_height"),
        ("page_width", "page_height"),
        ("source_image_width", "source_image_height"),
        ("source_page_width", "source_page_height"),
    ):
        width = as_int(record.get(width_key), default=0)
        height = as_int(record.get(height_key), default=0)
        if width > 1 and height > 1:
            box = normalize_bbox({"x0": 0, "y0": 0, "x1": width, "y1": height, "coordinate_system": "pixels"})
            return box, {"full_page_bbox_resolution": f"record_{width_key}_{height_key}", "full_page_bbox_image_path": None}
    image_index = image_index or {}
    image_path, method = resolve_image_path(record, image_root, image_index)
    width, height = image_dimensions(image_path)
    if width and height:
        box = normalize_bbox({"x0": 0, "y0": 0, "x1": width, "y1": height, "coordinate_system": "pixels"})
        return box, {"full_page_bbox_resolution": method, "full_page_bbox_image_path": str(image_path) if image_path else None}
    return None, {"full_page_bbox_resolution": method, "full_page_bbox_image_path": str(image_path) if image_path else None}

def bbox_area(box: Mapping[str, Any] | None) -> float:
    if not box:
        return 0.0
    return max(0.0, float(box.get("width") or 0.0)) * max(0.0, float(box.get("height") or 0.0))


def union_bboxes(boxes: Iterable[Mapping[str, Any] | None], *, padding_ratio: float = 0.012) -> dict[str, Any] | None:
    clean = [normalize_bbox(b) for b in boxes if b]
    clean = [b for b in clean if b]
    if not clean:
        return None
    x0 = min(float(b["x0"]) for b in clean)
    y0 = min(float(b["y0"]) for b in clean)
    x1 = max(float(b["x1"]) for b in clean)
    y1 = max(float(b["y1"]) for b in clean)
    w = max(1.0, x1 - x0)
    h = max(1.0, y1 - y0)
    pad_x = max(8.0, w * padding_ratio)
    pad_y = max(8.0, h * padding_ratio)
    x0 = max(0.0, x0 - pad_x)
    y0 = max(0.0, y0 - pad_y)
    x1 = x1 + pad_x
    y1 = y1 + pad_y
    return normalize_bbox({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "coordinate_system": clean[0].get("coordinate_system") or "pixels"})


def overlap_1d(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))



def clamp_nonnegative_box(box: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Clamp a bbox to non-negative pixel space without needing page dimensions."""
    clean = normalize_bbox(box)
    if not clean:
        return None
    x0 = max(0.0, float(clean["x0"]))
    y0 = max(0.0, float(clean["y0"]))
    x1 = max(x0 + 1.0, float(clean["x1"]))
    y1 = max(y0 + 1.0, float(clean["y1"]))
    return normalize_bbox({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "coordinate_system": clean.get("coordinate_system") or "pixels"})


def has_any(values: Iterable[str], needles: Iterable[str]) -> bool:
    haystack = set(values)
    return any(n in haystack for n in needles)




def bounded_content_band_box(
    candidate: Mapping[str, Any] | None,
    anchor: Mapping[str, Any] | None,
    *,
    split_column: bool = False,
    cuts_columns: bool = False,
    cuts_rows: bool = False,
    header_cut: bool = False,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Cap a reconstructed table bbox to a conservative content-band envelope.

    This is intentionally similar to production table systems such as
    PP-Structure/TATR in spirit: the final region is chosen by structure
    containment constraints, not only by dark-pixel tightness or arbitrary
    expansion. We preserve full-table containment relative to the upstream
    anchor, but we do not allow weak/challenged records to balloon into almost
    full-page crops without explicit page/image evidence.
    """
    clean = normalize_bbox(candidate)
    ref = normalize_bbox(anchor)
    if not clean or not ref:
        return clean, {
            "bounded_table_content_band_applied": False,
            "boundary_content_band_capped": False,
            "boundary_cap_reason": "missing_candidate_or_anchor",
            "boundary_max_width_ratio": None,
            "boundary_max_height_ratio": None,
        }

    ref_w = max(1.0, float(ref["width"]))
    ref_h = max(1.0, float(ref["height"]))

    # Keep enough room for full containment, but avoid the v2 failure mode where
    # fallback boxes expand into page furniture. Split-column pages get a little
    # more horizontal room because the table can span two separated column groups.
    max_width_ratio = 1.08
    if split_column:
        max_width_ratio = 1.12
    if cuts_columns:
        max_width_ratio = max(max_width_ratio, 1.12)

    max_height_ratio = 1.06
    if cuts_rows or header_cut:
        max_height_ratio = 1.10

    max_extra_w = max(12.0, (max_width_ratio - 1.0) * ref_w)
    max_extra_h = max(12.0, (max_height_ratio - 1.0) * ref_h)
    # Do not hard-bias right expansion. The previous implementation expanded
    # right much more than left and could drift into non-table furniture.
    min_x0 = max(0.0, float(ref["x0"]) - max_extra_w / 2.0)
    max_x1 = float(ref["x1"]) + max_extra_w / 2.0
    min_y0 = max(0.0, float(ref["y0"]) - max_extra_h / 2.0)
    max_y1 = float(ref["y1"]) + max_extra_h / 2.0

    x0 = max(min_x0, float(clean["x0"]))
    y0 = max(min_y0, float(clean["y0"]))
    x1 = min(max_x1, float(clean["x1"]))
    y1 = min(max_y1, float(clean["y1"]))
    if x1 <= x0 + 1:
        x0, x1 = float(ref["x0"]), float(ref["x1"])
    if y1 <= y0 + 1:
        y0, y1 = float(ref["y0"]), float(ref["y1"])

    out = normalize_bbox({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "coordinate_system": clean.get("coordinate_system") or ref.get("coordinate_system") or "pixels"})
    capped = bool(
        abs(float(clean["x0"]) - x0) > 1e-6
        or abs(float(clean["x1"]) - x1) > 1e-6
        or abs(float(clean["y0"]) - y0) > 1e-6
        or abs(float(clean["y1"]) - y1) > 1e-6
    )
    return out, {
        "bounded_table_content_band_applied": True,
        "boundary_content_band_capped": capped,
        "boundary_cap_reason": "bounded_full_table_content_band",
        "boundary_max_width_ratio": round(max_width_ratio, 6),
        "boundary_max_height_ratio": round(max_height_ratio, 6),
    }

def reconstruct_full_table_boundary(
    *,
    input_box: Mapping[str, Any] | None,
    structure_selected: Mapping[str, Any] | None,
    visual_candidate: Mapping[str, Any] | None,
    structure: Mapping[str, Any],
    presence: Mapping[str, Any] | None,
    padding_ratio: float,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Create a conservative but bounded whole-table boundary.

    This v3 behavior borrows the structure-first lesson from PaddleOCR
    PP-Structure and Microsoft's Table Transformer work: avoid choosing a box
    just because it is visually dense, and avoid arbitrary full-page expansion.
    The selected box is anchored on upstream table structure, then capped to a
    table-content-band envelope. The goal is to contain the full table while
    suppressing page headers, footers, and diagram/page furniture.
    """
    flags = [f for f in as_list(structure.get("review_flags")) if isinstance(f, str)]
    flags += [f for f in as_list((presence or {}).get("review_flags")) if isinstance(f, str)]
    issues = [f for f in as_list((presence or {}).get("table_route_challenge_issues")) if isinstance(f, str)]
    signal_set = set(flags + issues)
    split_column = bool(structure.get("multi_column_vertical_merge_applied")) or "split_column_table_geometry_merged" in signal_set or "split_column_table_geometry" in signal_set
    cuts_columns = has_any(signal_set, ("visual_candidate_cuts_table_columns", "visual_candidate_low_input_x_overlap", "visual_candidate_width_under_table_extent"))
    cuts_rows = has_any(signal_set, ("visual_candidate_cuts_table_rows", "visual_candidate_low_input_y_overlap", "visual_candidate_height_under_table_extent", "visual_candidate_too_short_for_row_count"))
    header_cut = "visual_candidate_header_band_not_preserved" in signal_set
    over_tight = has_any(signal_set, ("visual_candidate_over_tightened_area", "visual_candidate_area_under_table_extent"))

    anchor = normalize_bbox(input_box) or normalize_bbox(structure_selected) or normalize_bbox(visual_candidate)
    structural_anchor = union_bboxes([input_box, structure_selected], padding_ratio=min(padding_ratio, 0.006)) or anchor
    # Visual candidates contribute only when they were already accepted. Rejected
    # candidates are evidence of failure, not a boundary source.
    accepted_visual = visual_candidate if structure.get("structure_visual_candidate_accepted") else None
    base = union_bboxes([structural_anchor, accepted_visual], padding_ratio=min(padding_ratio, 0.006)) or structural_anchor
    if not base:
        return None, {
            "boundary_reconstruction_applied": False,
            "boundary_reconstruction_reason": "no_bbox_available",
            "split_column_boundary_reconstructed": False,
            "boundary_expanded_x": False,
            "boundary_expanded_y": False,
            "bounded_table_content_band_applied": False,
            "boundary_content_band_capped": False,
        }

    x0 = float(base["x0"])
    y0 = float(base["y0"])
    x1 = float(base["x1"])
    y1 = float(base["y1"])
    w = max(1.0, float(base["width"]))
    h = max(1.0, float(base["height"]))

    expand_x = split_column or cuts_columns or over_tight
    expand_y = cuts_rows or header_cut or over_tight

    # Modest symmetric expansion only. The v2 right-heavy expansion safely
    # contained tables but often swallowed page furniture. v3 keeps enough
    # expansion to recover columns/rows, then caps it against the anchor band.
    left_pad = 0.012 * w
    right_pad = 0.012 * w
    if split_column:
        left_pad = max(left_pad, 0.025 * w)
        right_pad = max(right_pad, 0.045 * w)
    if cuts_columns:
        left_pad = max(left_pad, 0.025 * w)
        right_pad = max(right_pad, 0.055 * w)
    if over_tight:
        left_pad = max(left_pad, 0.02 * w)
        right_pad = max(right_pad, 0.035 * w)

    top_pad = 0.012 * h
    bottom_pad = 0.012 * h
    if header_cut:
        top_pad = max(top_pad, 0.035 * h)
    if cuts_rows:
        bottom_pad = max(bottom_pad, 0.055 * h)
    if over_tight:
        top_pad = max(top_pad, 0.02 * h)
        bottom_pad = max(bottom_pad, 0.035 * h)

    if expand_x:
        x0 -= left_pad
        x1 += right_pad
    if expand_y:
        y0 -= top_pad
        y1 += bottom_pad

    expanded = clamp_nonnegative_box({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "coordinate_system": base.get("coordinate_system") or "pixels"})
    out, cap_info = bounded_content_band_box(
        expanded,
        anchor,
        split_column=split_column,
        cuts_columns=cuts_columns,
        cuts_rows=cuts_rows,
        header_cut=header_cut,
    )
    return out, {
        "boundary_reconstruction_applied": bool(expand_x or expand_y or split_column or cap_info.get("boundary_content_band_capped")),
        "boundary_reconstruction_reason": "bounded_split_column_or_cut_structure" if (expand_x or expand_y or split_column) else "bounded_padded_union_only",
        "split_column_boundary_reconstructed": bool(split_column),
        "boundary_expanded_x": bool(expand_x),
        "boundary_expanded_y": bool(expand_y),
        "boundary_expansion_left_pixels": round(left_pad if expand_x else 0.0, 3),
        "boundary_expansion_right_pixels": round(right_pad if expand_x else 0.0, 3),
        "boundary_expansion_top_pixels": round(top_pad if expand_y else 0.0, 3),
        "boundary_expansion_bottom_pixels": round(bottom_pad if expand_y else 0.0, 3),
        **cap_info,
    }

def diagram_review_only(presence: Mapping[str, Any] | None, structure: Mapping[str, Any] | None = None) -> bool:
    """Return True when table bbox should be preserved only for review.

    In addition to explicit image_visual/not_table routing, catch the common
    diagram false positive seen in scanned manuals: route says table, but the
    visual candidate never refined, the bbox remains broad, and both row and
    column structure are weak. That pattern is more like a diagram/page image
    than an extractable table.
    """
    if not presence:
        return False
    recommended_route = str(presence.get("recommended_route") or "")
    action = str(presence.get("recommended_downstream_action") or "")
    label = str(presence.get("table_presence_label") or "")
    flags = [f for f in as_list(presence.get("review_flags")) if isinstance(f, str)]
    negatives = [f for f in as_list(presence.get("negative_table_signals")) if isinstance(f, str)]
    if structure:
        flags += [f for f in as_list(structure.get("review_flags")) if isinstance(f, str)]
    flag_set = set(flags + negatives)
    image_like = any("image" in f or "diagram" in f or "figure" in f for f in flag_set)
    weak_unrefined_diagram_like = (
        label in {"weak_table", "not_table"}
        and {"visual_candidate_not_refined", "visual_candidate_quality_not_pass", "visual_refinement_not_applied"}.issubset(flag_set)
        and ("weak_row_structure_flag" in flag_set or "visual_candidate_weak_row_structure" in flag_set)
        and ("weak_column_structure_flag" in flag_set or "visual_candidate_weak_column_structure" in flag_set)
    )
    broad_unrefined_diagram_like = (
        label == "weak_table"
        and "localized_bbox_still_broad" in flag_set
        and "visual_candidate_not_refined" in flag_set
        and ("weak_horizontal_table_signal" in flag_set or "weak_vertical_table_signal" in flag_set)
    )
    return (
        recommended_route in {"image_visual", "image_visual_review"}
        or "image_visual" in action
        or (label == "not_table" and image_like)
        or weak_unrefined_diagram_like
        or broad_unrefined_diagram_like
    )

def enclosure_metrics(input_box: Mapping[str, Any] | None, selected_box: Mapping[str, Any] | None) -> dict[str, Any]:
    if not input_box or not selected_box:
        return {
            "selected_to_input_width_ratio": None,
            "selected_to_input_height_ratio": None,
            "selected_to_input_area_ratio": None,
            "input_x_coverage_ratio": None,
            "input_y_coverage_ratio": None,
        }
    iw = max(1.0, float(input_box.get("width") or 1.0))
    ih = max(1.0, float(input_box.get("height") or 1.0))
    sw = max(1.0, float(selected_box.get("width") or 1.0))
    sh = max(1.0, float(selected_box.get("height") or 1.0))
    input_area = max(1.0, bbox_area(input_box))
    selected_area = max(1.0, bbox_area(selected_box))
    x_overlap = overlap_1d(float(input_box["x0"]), float(input_box["x1"]), float(selected_box["x0"]), float(selected_box["x1"]))
    y_overlap = overlap_1d(float(input_box["y0"]), float(input_box["y1"]), float(selected_box["y0"]), float(selected_box["y1"]))
    return {
        "selected_to_input_width_ratio": round(sw / iw, 6),
        "selected_to_input_height_ratio": round(sh / ih, 6),
        "selected_to_input_area_ratio": round(selected_area / input_area, 6),
        "input_x_coverage_ratio": round(x_overlap / iw, 6),
        "input_y_coverage_ratio": round(y_overlap / ih, 6),
    }


def extract_records(payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(r) for r in payload if isinstance(r, Mapping)]
    if not isinstance(payload, Mapping):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [dict(r) for r in value if isinstance(r, Mapping)]
    return []


def structure_records(payload: Any) -> list[dict[str, Any]]:
    return extract_records(payload, ("table_structure_bbox_localizer_records", "records", "structure_records"))


def presence_records(payload: Any) -> list[dict[str, Any]]:
    return extract_records(payload, ("table_presence_verifier_records", "records", "presence_records"))


def build_presence_indexes(records: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    by_table: dict[str, dict[str, Any]] = {}
    by_page: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        table_id = str(record.get("table_id") or "")
        page_id = str(record.get("page_id") or "")
        if table_id:
            by_table[table_id] = record
        if page_id:
            by_page.setdefault(page_id, []).append(record)
    return by_table, by_page


def match_presence_record(structure: Mapping[str, Any], by_table: Mapping[str, dict[str, Any]], by_page: Mapping[str, list[dict[str, Any]]]) -> tuple[dict[str, Any] | None, str]:
    table_id = str(structure.get("table_id") or "")
    page_id = str(structure.get("page_id") or "")
    if table_id and table_id in by_table:
        return by_table[table_id], "table_id"
    page_records = list(by_page.get(page_id, []))
    if len(page_records) == 1:
        return page_records[0], "page_id_single_presence_record"
    if page_records:
        return page_records[0], "page_id_first_presence_record"
    return None, "no_presence_record_match"


def severe_structure_flags(structure: Mapping[str, Any]) -> list[str]:
    flags = [f for f in as_list(structure.get("review_flags")) if isinstance(f, str)]
    return [
        f for f in flags
        if f in {
            "visual_candidate_cuts_table_columns",
            "visual_candidate_cuts_table_rows",
            "visual_candidate_over_tightened_area",
            "visual_candidate_too_short_for_row_count",
            "visual_candidate_header_band_not_preserved",
            "visual_candidate_low_input_x_overlap",
            "visual_candidate_low_input_y_overlap",
        }
    ]


def reconstruct_record(
    structure: Mapping[str, Any],
    presence: Mapping[str, Any] | None,
    match_method: str,
    *,
    padding_ratio: float,
    force_final_bbox_full_page: bool = False,
    image_root: Path | None = None,
    image_index: Mapping[str, list[Path]] | None = None,
) -> dict[str, Any]:
    page_id = str(structure.get("page_id") or "")
    table_id = str(structure.get("table_id") or "")
    input_box = normalize_bbox(structure.get("input_bbox"))
    structure_selected = normalize_bbox(structure.get("structure_selected_table_bbox"))
    visual_candidate = normalize_bbox(structure.get("visual_candidate_bbox"))
    full_recommended = bool((presence or {}).get("full_table_enclosure_recommended"))
    presence_label = str((presence or {}).get("table_presence_label") or "unknown")
    allowed = (presence or {}).get("table_localization_allowed") is not False
    challenge_issues = [f for f in as_list((presence or {}).get("table_route_challenge_issues")) if isinstance(f, str)]
    severe_flags = severe_structure_flags(structure)

    boxes_for_union: list[Mapping[str, Any] | None] = []
    if input_box:
        boxes_for_union.append(input_box)
    if structure_selected:
        boxes_for_union.append(structure_selected)
    # Include visual candidate only as an enclosure contributor, never as the sole
    # authority when full-table reconstruction was requested.
    if visual_candidate and (structure.get("structure_visual_candidate_accepted") or full_recommended):
        boxes_for_union.append(visual_candidate)

    boundary_info: dict[str, Any] = {
        "boundary_reconstruction_applied": False,
        "boundary_reconstruction_reason": "not_requested",
        "split_column_boundary_reconstructed": False,
        "boundary_expanded_x": False,
        "boundary_expanded_y": False,
    }
    review_only = diagram_review_only(presence, structure)
    if full_recommended:
        selected_box, boundary_info = reconstruct_full_table_boundary(
            input_box=input_box,
            structure_selected=structure_selected,
            visual_candidate=visual_candidate,
            structure=structure,
            presence=presence,
            padding_ratio=padding_ratio,
        )
        selected_source = "full_table_boundary_reconstructed" if boundary_info.get("boundary_reconstruction_applied") else "full_table_enclosure_reconstructed"
        selected_key = "full_table_enclosure_bbox"
        action = "use_full_table_enclosure_bbox_for_safe_row_cell_extraction"
    else:
        selected_box = structure_selected or union_bboxes(boxes_for_union, padding_ratio=padding_ratio)
        selected_source = "structure_selected_bbox_passthrough"
        selected_key = "structure_selected_table_bbox"
        action = "use_structure_selected_bbox_for_row_cell_extraction"
    full_page_box = None
    full_page_info = {"full_page_bbox_resolution": None, "full_page_bbox_image_path": None}
    full_page_applied = False
    if force_final_bbox_full_page:
        full_page_box, full_page_info = page_bbox_from_record(structure, image_root=image_root, image_index=image_index)
        if full_page_box and not review_only and allowed:
            selected_box = full_page_box
            selected_source = "full_page_table_bbox"
            selected_key = "full_page_table_bbox"
            action = "use_full_page_bbox_for_step0_table_extraction"
            full_page_applied = True
    if review_only:
        selected_source = "review_only_image_or_non_table_bbox_preserved"
        action = "review_or_route_to_image_visual_before_table_extraction"

    metrics = enclosure_metrics(input_box, selected_box)
    review_flags = list(dict.fromkeys(
        [f for f in as_list(structure.get("review_flags")) if isinstance(f, str)]
        + [f for f in as_list((presence or {}).get("review_flags")) if isinstance(f, str)]
        + (["full_table_enclosure_reconstructed"] if full_recommended else [])
        + (["full_table_boundary_reconstructed"] if boundary_info.get("boundary_reconstruction_applied") else [])
        + (["split_column_full_table_boundary_reconstructed"] if boundary_info.get("split_column_boundary_reconstructed") else [])
        + (["full_page_bbox_for_step0_table_extraction"] if full_page_applied else [])
        + (["full_page_bbox_requested_but_image_unresolved"] if force_final_bbox_full_page and not full_page_box else [])
        + (["table_bbox_review_only_image_or_non_table"] if review_only else [])
        + (["table_localization_not_allowed_but_bbox_preserved_for_review"] if not allowed else [])
    ))
    ready = selected_box is not None and bool(allowed) and not review_only
    downstream_action = action if (ready or review_only) else "review_before_table_row_cell_extraction"
    return {
        "schema_version": SCHEMA_VERSION,
        "table_full_enclosure_bbox_reconstructor_id": stable_id("tblfullbbox", page_id, table_id, selected_source),
        "page_id": page_id,
        "table_id": table_id,
        "presence_match_method": match_method,
        "table_presence_label": presence_label,
        "table_presence_confidence": (presence or {}).get("table_presence_confidence"),
        "table_localization_allowed": allowed,
        "full_table_enclosure_recommended": full_recommended,
        "table_route_challenged": bool((presence or {}).get("table_route_challenged")),
        "table_route_challenge_issues": challenge_issues,
        "structure_bbox_localizer_id": structure.get("table_structure_bbox_localizer_id"),
        "table_presence_verifier_id": (presence or {}).get("table_presence_verifier_id"),
        "input_bbox": input_box,
        "structure_selected_table_bbox": structure_selected,
        "visual_candidate_bbox": visual_candidate,
        "full_table_enclosure_bbox": selected_box,
        "final_table_bbox": selected_box,
        "final_table_bbox_key": selected_key,
        "final_table_bbox_source": selected_source,
        "full_page_table_bbox": full_page_box,
        "full_page_bbox_applied": full_page_applied,
        **full_page_info,
        "full_table_enclosure_bbox_ready": ready,
        "reconstruction_source_box_count": len([b for b in boxes_for_union if b]),
        "reconstruction_padding_ratio": padding_ratio,
        **boundary_info,
        "table_bbox_review_only": review_only,
        "severe_structure_flag_count": len(severe_flags),
        "severe_structure_flags": severe_flags,
        **metrics,
        "row_cell_extraction_scope": "full_table_enclosure_bbox_crop" if full_recommended else "structure_selected_bbox_crop",
        "recommended_downstream_bbox_key": selected_key,
        "recommended_downstream_action": downstream_action,
        "review_required": bool(review_flags),
        "review_flags": review_flags,
        "record_role": "full_table_enclosure_bbox_reconstructor",
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
        "unsafe_table_full_enclosure_bbox_record": False,
    }


def unsafe_record_count(records: list[Mapping[str, Any]]) -> int:
    count = 0
    for record in records:
        if record.get("unsafe_table_full_enclosure_bbox_record"):
            count += 1
            continue
        for key in SAFETY_FALSE_KEYS:
            if record.get(key) is True:
                count += 1
                break
    return count


def summarize(records: list[dict[str, Any]], *, structure_payload: Any = None, presence_payload: Any = None, source_structure_count: int | None = None, source_presence_count: int | None = None) -> dict[str, Any]:
    ready = [r for r in records if r.get("full_table_enclosure_bbox_ready")]
    reconstructed = [r for r in records if r.get("final_table_bbox_source") in {"full_table_enclosure_reconstructed", "full_table_boundary_reconstructed", "full_page_table_bbox"}]
    boundary_reconstructed = [r for r in records if r.get("final_table_bbox_source") == "full_table_boundary_reconstructed"]
    full_page = [r for r in records if r.get("final_table_bbox_source") == "full_page_table_bbox"]
    passthrough = [r for r in records if r.get("final_table_bbox_source") == "structure_selected_bbox_passthrough"]
    weak = [r for r in records if r.get("table_presence_label") == "weak_table"]
    confirmed = [r for r in records if r.get("table_presence_label") == "confirmed_table"]
    return {
        "schema_version": SCHEMA_VERSION,
        "source_table_structure_bbox_localizer_quality_status": payload_quality_status(structure_payload),
        "source_table_presence_verifier_quality_status": payload_quality_status(presence_payload),
        "source_structure_record_count": int(source_structure_count if source_structure_count is not None else len(records)),
        "source_presence_record_count": int(source_presence_count if source_presence_count is not None else 0),
        "full_enclosure_reconstructor_record_count": len(records),
        "page_count": len({r.get("page_id") for r in records if r.get("page_id")}),
        "final_table_bbox_ready_record_count": len(ready),
        "full_table_enclosure_recommended_record_count": sum(1 for r in records if r.get("full_table_enclosure_recommended")),
        "full_table_enclosure_reconstructed_record_count": len(reconstructed),
        "full_table_boundary_reconstructed_record_count": len(boundary_reconstructed),
        "full_page_bbox_applied_record_count": len(full_page),
        "full_page_bbox_unresolved_record_count": sum(1 for r in records if r.get("full_page_bbox_resolution") == "not_found" and r.get("full_page_bbox_applied") is not True),
        "split_column_boundary_reconstructed_record_count": sum(1 for r in records if r.get("split_column_boundary_reconstructed")),
        "boundary_expanded_x_record_count": sum(1 for r in records if r.get("boundary_expanded_x")),
        "boundary_expanded_y_record_count": sum(1 for r in records if r.get("boundary_expanded_y")),
        "bounded_table_content_band_record_count": sum(1 for r in records if r.get("bounded_table_content_band_applied")),
        "boundary_content_band_capped_record_count": sum(1 for r in records if r.get("boundary_content_band_capped")),
        "diagram_or_image_review_only_record_count": sum(1 for r in records if r.get("table_bbox_review_only")),
        "structure_selected_passthrough_record_count": len(passthrough),
        "weak_table_reconstructed_record_count": sum(1 for r in reconstructed if r.get("table_presence_label") == "weak_table"),
        "confirmed_table_passthrough_record_count": sum(1 for r in passthrough if r.get("table_presence_label") == "confirmed_table"),
        "table_route_challenged_reconstructed_count": sum(1 for r in reconstructed if r.get("table_route_challenged")),
        "presence_weak_table_count": len(weak),
        "presence_confirmed_table_count": len(confirmed),
        "missing_presence_match_count": sum(1 for r in records if r.get("presence_match_method") == "no_presence_record_match"),
        "unsafe_table_full_enclosure_bbox_record_count": unsafe_record_count(records),
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

    add("source_structure_records", summary.get("source_structure_record_count", 0) >= get("min_source_structure_records", 1), f"records={summary.get('source_structure_record_count', 0)} minimum={get('min_source_structure_records', 1)}")
    add("source_presence_records", summary.get("source_presence_record_count", 0) >= get("min_source_presence_records", 1), f"records={summary.get('source_presence_record_count', 0)} minimum={get('min_source_presence_records', 1)}")
    add("reconstructor_records", summary.get("full_enclosure_reconstructor_record_count", 0) >= get("min_reconstructor_records", 1), f"records={summary.get('full_enclosure_reconstructor_record_count', 0)} minimum={get('min_reconstructor_records', 1)}")
    add("final_bbox_ready_records", summary.get("final_table_bbox_ready_record_count", 0) >= get("min_final_bbox_ready_records", 1), f"ready={summary.get('final_table_bbox_ready_record_count', 0)} minimum={get('min_final_bbox_ready_records', 1)}")
    add("full_enclosure_reconstructed_records", summary.get("full_table_enclosure_reconstructed_record_count", 0) >= get("min_full_enclosure_reconstructed_records", 0), f"reconstructed={summary.get('full_table_enclosure_reconstructed_record_count', 0)} minimum={get('min_full_enclosure_reconstructed_records', 0)}")
    add("diagram_or_image_review_only_records", summary.get("diagram_or_image_review_only_record_count", 0) >= get("min_diagram_or_image_review_only_records", 0), f"review_only={summary.get('diagram_or_image_review_only_record_count', 0)} minimum={get('min_diagram_or_image_review_only_records', 0)}")
    add("bounded_content_band_records", summary.get("bounded_table_content_band_record_count", 0) >= get("min_bounded_content_band_records", 0), f"bounded={summary.get('bounded_table_content_band_record_count', 0)} minimum={get('min_bounded_content_band_records', 0)}")
    add("full_page_bbox_records", summary.get("full_page_bbox_applied_record_count", 0) >= get("min_full_page_bbox_records", 0), f"full_page={summary.get('full_page_bbox_applied_record_count', 0)} minimum={get('min_full_page_bbox_records', 0)}")
    add("unsafe_records", summary.get("unsafe_table_full_enclosure_bbox_record_count", 0) <= get("max_unsafe_records", 0), f"unsafe={summary.get('unsafe_table_full_enclosure_bbox_record_count', 0)} max={get('max_unsafe_records', 0)}")
    add("answer_permission", summary.get("answer_permission_count", 0) <= get("max_answer_permission_count", 0), f"count={summary.get('answer_permission_count', 0)} max={get('max_answer_permission_count', 0)}")
    add("source_truth_mutation_allowed", summary.get("source_truth_mutation_allowed_count", 0) <= get("max_source_truth_mutation_allowed", 0), f"count={summary.get('source_truth_mutation_allowed_count', 0)} max={get('max_source_truth_mutation_allowed', 0)}")
    add("postgres_writes", summary.get("postgres_write_attempt_count", 0) == 0, f"count={summary.get('postgres_write_attempt_count', 0)}")
    add("qdrant_writes", summary.get("qdrant_write_attempt_count", 0) == 0, f"count={summary.get('qdrant_write_attempt_count', 0)}")
    add("opensearch_writes", summary.get("opensearch_write_attempt_count", 0) == 0, f"count={summary.get('opensearch_write_attempt_count', 0)}")
    if get("require_table_structure_bbox_localizer_quality_pass", False):
        add("source_table_structure_bbox_localizer_quality_pass", summary.get("source_table_structure_bbox_localizer_quality_status") == "PASS", f"status={summary.get('source_table_structure_bbox_localizer_quality_status')}")
    if get("require_table_presence_verifier_quality_pass", False):
        add("source_table_presence_verifier_quality_pass", summary.get("source_table_presence_verifier_quality_status") == "PASS", f"status={summary.get('source_table_presence_verifier_quality_status')}")
    if get("require_all_final_bboxes_ready", False):
        add("all_final_bboxes_ready", summary.get("final_table_bbox_ready_record_count", 0) == summary.get("full_enclosure_reconstructor_record_count", -1), f"ready={summary.get('final_table_bbox_ready_record_count', 0)} records={summary.get('full_enclosure_reconstructor_record_count', -1)}")
    if get("require_all_recommended_reconstructed", False):
        add("all_recommended_reconstructed", summary.get("full_table_enclosure_recommended_record_count", 0) == summary.get("full_table_enclosure_reconstructed_record_count", -1), f"recommended={summary.get('full_table_enclosure_recommended_record_count', 0)} reconstructed={summary.get('full_table_enclosure_reconstructed_record_count', -1)}")
    status = "PASS" if all(c["ok"] for c in checks) else "FAIL"
    return status, checks


def build_report(
    *,
    table_structure_bbox_localizer_path: str | Path,
    table_presence_verifier_path: str | Path,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    thresholds: Mapping[str, Any] | argparse.Namespace | None = None,
    padding_ratio: float = 0.012,
    write_quality: bool = False,
    force_final_bbox_full_page: bool = False,
    image_root: str | Path | None = None,
    max_image_files_scanned: int = 25_000,
) -> dict[str, Any]:
    structure_payload = read_json(table_structure_bbox_localizer_path, default={})
    presence_payload = read_json(table_presence_verifier_path, default={})
    structures = structure_records(structure_payload)
    presences = presence_records(presence_payload)
    by_table, by_page = build_presence_indexes(presences)
    root_path = Path(image_root) if image_root else None
    image_index = build_image_index(root_path, max_files_scanned=max_image_files_scanned) if force_final_bbox_full_page else {}
    records: list[dict[str, Any]] = []
    for structure in structures:
        presence, match_method = match_presence_record(structure, by_table, by_page)
        records.append(reconstruct_record(
            structure,
            presence,
            match_method,
            padding_ratio=padding_ratio,
            force_final_bbox_full_page=force_final_bbox_full_page,
            image_root=root_path,
            image_index=image_index,
        ))
    summary = summarize(records, structure_payload=structure_payload, presence_payload=presence_payload, source_structure_count=len(structures), source_presence_count=len(presences))
    quality_status, checks = quality_checks(summary, thresholds)
    report = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "summary": summary,
        "quality": {"schema_version": QUALITY_SCHEMA_VERSION, "status": quality_status, "checks": checks},
        "table_full_enclosure_bbox_reconstructor_records": records,
    }
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "trace_net_table_full_enclosure_bbox_reconstructor_v1.json"
    records_path = out / "trace_net_table_full_enclosure_bbox_reconstructor_v1_records.jsonl"
    reconstructed_path = out / "trace_net_table_full_enclosure_bbox_reconstructor_v1_reconstructed_records.jsonl"
    summary_path = out / "trace_net_table_full_enclosure_bbox_reconstructor_v1_summary.json"
    quality_path = out / "trace_net_table_full_enclosure_bbox_reconstructor_v1_quality.json"
    manifest_path = out / "trace_net_table_full_enclosure_bbox_reconstructor_v1_manifest.json"
    write_json(report_path, report)
    write_jsonl(records_path, records)
    write_jsonl(reconstructed_path, [r for r in records if r.get("final_table_bbox_source") in {"full_table_enclosure_reconstructed", "full_table_boundary_reconstructed", "full_page_table_bbox"}])
    write_json(summary_path, summary)
    if write_quality:
        write_json(quality_path, {"schema_version": QUALITY_SCHEMA_VERSION, "status": quality_status, "summary": summary, "checks": checks})
    write_json(manifest_path, {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "report_path": str(report_path),
        "records_path": str(records_path),
        "reconstructed_records_path": str(reconstructed_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "source_paths": {
            "table_structure_bbox_localizer": str(table_structure_bbox_localizer_path),
            "table_presence_verifier": str(table_presence_verifier_path),
            "image_root": str(image_root) if image_root else None,
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
    p = argparse.ArgumentParser(description="Build TRACE-Net table full enclosure bbox reconstructor v1 artifacts.")
    p.add_argument("--table-structure-bbox-localizer", required=True)
    p.add_argument("--table-presence-verifier", required=True)
    p.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    p.add_argument("--padding-ratio", type=float, default=0.012)
    p.add_argument("--force-final-bbox-full-page", action="store_true", help="Temporary step-0 mode: use whole source page as the final table bbox for extraction-ready table records.")
    p.add_argument("--image-root", default=None, help="Root used to resolve source page images when --force-final-bbox-full-page is enabled.")
    p.add_argument("--max-image-files-scanned", type=int, default=25000)
    p.add_argument("--min-source-structure-records", type=int, default=1)
    p.add_argument("--min-source-presence-records", type=int, default=1)
    p.add_argument("--min-reconstructor-records", type=int, default=1)
    p.add_argument("--min-final-bbox-ready-records", type=int, default=1)
    p.add_argument("--min-full-enclosure-reconstructed-records", type=int, default=0)
    p.add_argument("--min-diagram-or-image-review-only-records", type=int, default=0)
    p.add_argument("--min-bounded-content-band-records", type=int, default=0)
    p.add_argument("--min-full-page-bbox-records", type=int, default=0)
    p.add_argument("--max-unsafe-records", type=int, default=0)
    p.add_argument("--max-answer-permission-count", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--require-table-structure-bbox-localizer-quality-pass", action="store_true")
    p.add_argument("--require-table-presence-verifier-quality-pass", action="store_true")
    p.add_argument("--require-all-final-bboxes-ready", action="store_true")
    p.add_argument("--require-all-recommended-reconstructed", action="store_true")
    p.add_argument("--quality", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = build_report(
        table_structure_bbox_localizer_path=args.table_structure_bbox_localizer,
        table_presence_verifier_path=args.table_presence_verifier,
        output_dir=args.output_dir,
        thresholds=args,
        padding_ratio=args.padding_ratio,
        write_quality=args.quality,
        force_final_bbox_full_page=args.force_final_bbox_full_page,
        image_root=args.image_root,
        max_image_files_scanned=args.max_image_files_scanned,
    )
    summary = report.get("summary", {})
    print("TRACE-Net Table Full Enclosure BBox Reconstructor v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in (
        "source_structure_record_count",
        "source_presence_record_count",
        "full_enclosure_reconstructor_record_count",
        "final_table_bbox_ready_record_count",
        "full_table_enclosure_recommended_record_count",
        "full_table_enclosure_reconstructed_record_count",
        "full_table_boundary_reconstructed_record_count",
        "full_page_bbox_applied_record_count",
        "full_page_bbox_unresolved_record_count",
        "split_column_boundary_reconstructed_record_count",
        "boundary_expanded_x_record_count",
        "boundary_expanded_y_record_count",
        "bounded_table_content_band_record_count",
        "boundary_content_band_capped_record_count",
        "diagram_or_image_review_only_record_count",
        "structure_selected_passthrough_record_count",
        "weak_table_reconstructed_record_count",
        "confirmed_table_passthrough_record_count",
        "table_route_challenged_reconstructed_count",
        "unsafe_table_full_enclosure_bbox_record_count",
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
