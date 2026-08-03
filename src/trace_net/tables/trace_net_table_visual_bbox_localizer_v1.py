"""TRACE-Net Table Visual BBox Localizer v1.

Read-only visual table-localization refinement for bbox-scoped table extraction.

This module consumes the selected/preferred table crop from
``trace_net_table_ocr_bbox_enrichment_v1`` and inspects the source page image to
produce a tighter, visually grounded table localization bbox. It is intended to
fix the gap where a bbox is valid and consumed but still page-content-scale or
header/footer contaminated.

Authority and safety contract:
- read local JSON/image artifacts only;
- write local JSON/JSONL reports only;
- no Postgres writes;
- no Qdrant writes;
- no OpenSearch writes;
- no source-truth mutation;
- no answer permission or claim-proof authority.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:  # Pillow is used elsewhere in TRACE-Net image tooling; keep import lazy-safe.
    from PIL import Image, ImageDraw
except Exception:  # pragma: no cover - exercised only on environments without Pillow.
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]

SCHEMA_VERSION = "trace_net_table_visual_bbox_localizer_v1"
QUALITY_SCHEMA_VERSION = "trace_net_table_visual_bbox_localizer_v1_quality"
STATUS_BUILT = "TABLE_VISUAL_BBOX_LOCALIZER_BUILT"
STATUS_NOT_READY = "TABLE_VISUAL_BBOX_LOCALIZER_NOT_READY"

IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".webp", ".bmp"}
BBOX_KEYS = (
    "localized_table_bbox",
    "visual_table_bbox",
    "inferred_table_region_bbox",
    "table_extraction_bbox",
    "table_region_bbox",
    "selected_table_bbox",
    "bbox",
)
IMAGE_PATH_KEYS = (
    "image_path",
    "source_image_path",
    "selected_image_path",
    "page_image_path",
    "resolved_image_path",
    "tiff_path",
    "source_tiff_path",
)
PAGE_ID_KEYS = ("page_id", "source_page_id")
TABLE_ID_KEYS = ("table_id", "normalized_table_id", "source_table_id")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "||".join("" if part is None else str(part) for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:14]
    return f"{prefix}__{digest}"


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        f = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            f = float(text)
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(f):
        return None
    return f


def first_present(mapping: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\\", "/").split())


def bbox_area(box: Mapping[str, Any] | None) -> float:
    if not box:
        return 0.0
    width = as_float(box.get("width"))
    height = as_float(box.get("height"))
    if width is None:
        x0, x1 = as_float(box.get("x0")), as_float(box.get("x1"))
        width = max(0.0, (x1 or 0.0) - (x0 or 0.0))
    if height is None:
        y0, y1 = as_float(box.get("y0")), as_float(box.get("y1"))
        height = max(0.0, (y1 or 0.0) - (y0 or 0.0))
    return max(0.0, width) * max(0.0, height)


def bbox_coverage(box: Mapping[str, Any] | None, width: int | None, height: int | None) -> float | None:
    if not box or not width or not height or width <= 0 or height <= 0:
        return None
    return round(bbox_area(box) / float(width * height), 6)


def clamp_bbox(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    width: int | None = None,
    height: int | None = None,
) -> dict[str, Any] | None:
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0

    # Scale normalized coordinates when dimensions are available.
    if width and height and 0 <= x0 <= 1 and 0 <= x1 <= 1 and 0 <= y0 <= 1 and 0 <= y1 <= 1:
        x0, x1 = x0 * width, x1 * width
        y0, y1 = y0 * height, y1 * height

    if width:
        x0 = max(0.0, min(float(width), x0))
        x1 = max(0.0, min(float(width), x1))
    if height:
        y0 = max(0.0, min(float(height), y0))
        y1 = max(0.0, min(float(height), y1))

    if x1 - x0 < 1 or y1 - y0 < 1:
        return None

    return {
        "x0": round(float(x0), 3),
        "y0": round(float(y0), 3),
        "x1": round(float(x1), 3),
        "y1": round(float(y1), 3),
        "width": round(float(x1 - x0), 3),
        "height": round(float(y1 - y0), 3),
        "coordinate_system": "pixels" if width and height else "source_units",
    }


def bbox_from_mapping(value: Mapping[str, Any], width: int | None = None, height: int | None = None) -> dict[str, Any] | None:
    x0 = first_present(value, ("x0", "left", "xmin", "min_x", "x"))
    y0 = first_present(value, ("y0", "top", "ymin", "min_y", "y"))
    x1 = first_present(value, ("x1", "right", "xmax", "max_x"))
    y1 = first_present(value, ("y1", "bottom", "ymax", "max_y"))
    w = first_present(value, ("width", "w"))
    h = first_present(value, ("height", "h"))

    fx0, fy0 = as_float(x0), as_float(y0)
    fx1, fy1 = as_float(x1), as_float(y1)
    fw, fh = as_float(w), as_float(h)

    if fx0 is not None and fy0 is not None and fx1 is not None and fy1 is not None:
        return clamp_bbox(fx0, fy0, fx1, fy1, width, height)
    if fx0 is not None and fy0 is not None and fw is not None and fh is not None:
        return clamp_bbox(fx0, fy0, fx0 + fw, fy0 + fh, width, height)
    return None


def bbox_from_value(value: Any, width: int | None = None, height: int | None = None) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        return bbox_from_mapping(value, width, height)
    if isinstance(value, (list, tuple)) and len(value) >= 4:
        coords = [as_float(item) for item in value[:4]]
        if all(coord is not None for coord in coords):
            return clamp_bbox(coords[0], coords[1], coords[2], coords[3], width, height)  # type: ignore[arg-type]
    return None


def select_input_bbox(card: Mapping[str, Any], width: int | None = None, height: int | None = None) -> tuple[dict[str, Any] | None, str | None]:
    for key in BBOX_KEYS:
        if key in card:
            box = bbox_from_value(card[key], width, height)
            if box:
                return box, key
    return None, None


def page_suffix(page_id: str | None) -> str | None:
    text = str(page_id or "")
    marker = "p"
    idx = text.rfind(marker)
    if idx >= 0:
        tail = text[idx + 1 :]
        if tail.isdigit():
            return f"p{int(tail):06d}"
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits:
        return f"p{int(digits[-6:]):06d}"
    return None


def normalize_path(value: Any, image_root: Path | None = None) -> Path | None:
    text = normalize_text(value)
    if not text:
        return None
    path = Path(text)
    candidates = [path]
    if image_root and not path.is_absolute():
        candidates.append(image_root / path)
    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_file():
                return candidate
        except OSError:
            continue
    return candidates[-1] if candidates else None


def build_image_index(image_root: Path | None, max_files_scanned: int = 25000) -> dict[str, Path]:
    if not image_root or not image_root.exists():
        return {}
    index: dict[str, Path] = {}
    scanned = 0
    for path in image_root.rglob("*"):
        if scanned >= max_files_scanned:
            break
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        scanned += 1
        stem = path.stem.lower()
        # Exact stem and common page suffix keys.
        index.setdefault(stem, path)
        suffix = page_suffix(stem)
        if suffix:
            index.setdefault(suffix.lower(), path)
    return index


def resolve_image_path(card: Mapping[str, Any], image_root: Path | None, image_index: Mapping[str, Path]) -> tuple[str | None, str]:
    for key in IMAGE_PATH_KEYS:
        candidate = normalize_path(card.get(key), image_root)
        if candidate and candidate.exists() and candidate.is_file():
            return str(candidate), f"card_{key}"
    page_id = first_present(card, PAGE_ID_KEYS)
    keys = [normalize_text(page_id).lower()]
    suffix = page_suffix(str(page_id or ""))
    if suffix:
        keys.append(suffix.lower())
    for key in keys:
        if key and key in image_index:
            return str(image_index[key]), "image_index_page_id"
    return None, "not_found"


def image_dimensions(path: Path | None) -> tuple[int | None, int | None]:
    if Image is None or path is None or not path.exists():
        return None, None
    try:
        with Image.open(path) as image:
            return image.size
    except Exception:
        return None, None


def otsu_threshold(values: Sequence[int]) -> int:
    if not values:
        return 180
    hist = [0] * 256
    for value in values:
        hist[max(0, min(255, int(value)))] += 1
    total = len(values)
    sum_total = sum(i * count for i, count in enumerate(hist))
    sum_b = 0.0
    w_b = 0
    var_max = -1.0
    threshold = 180
    for i, count in enumerate(hist):
        w_b += count
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += i * count
        m_b = sum_b / w_b
        m_f = (sum_total - sum_b) / w_f
        var_between = w_b * w_f * (m_b - m_f) ** 2
        if var_between > var_max:
            var_max = var_between
            threshold = i
    # Keep threshold conservative for scanned manuals: text/lines are dark.
    return max(70, min(210, threshold + 10))


def percentile(sorted_values: Sequence[int], pct: float) -> int:
    if not sorted_values:
        return 0
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * pct
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_values[lo]
    return int(round(sorted_values[lo] * (hi - pos) + sorted_values[hi] * (pos - lo)))


def find_runs(indices: Sequence[int], max_gap: int = 2) -> list[tuple[int, int]]:
    if not indices:
        return []
    runs: list[tuple[int, int]] = []
    start = prev = indices[0]
    for idx in indices[1:]:
        if idx <= prev + max_gap:
            prev = idx
        else:
            runs.append((start, prev))
            start = prev = idx
    runs.append((start, prev))
    return runs



def cluster_runs_by_gap(runs: Sequence[tuple[int, int]], max_gap: int) -> list[list[tuple[int, int]]]:
    if not runs:
        return []
    clusters: list[list[tuple[int, int]]] = []
    current: list[tuple[int, int]] = [runs[0]]
    for run in runs[1:]:
        if run[0] - current[-1][1] <= max_gap:
            current.append(run)
        else:
            clusters.append(current)
            current = [run]
    clusters.append(current)
    return clusters


def best_run_cluster(runs: Sequence[tuple[int, int]], max_gap: int, min_runs: int) -> list[tuple[int, int]]:
    clusters = cluster_runs_by_gap(runs, max_gap)
    if not clusters:
        return []
    eligible = [cluster for cluster in clusters if len(cluster) >= min_runs]
    if not eligible:
        return []
    # Prefer the cluster with the most repeated line/rule evidence; break ties by span.
    return max(eligible, key=lambda c: (len(c), c[-1][1] - c[0][0]))


def eligible_run_clusters(runs: Sequence[tuple[int, int]], max_gap: int, min_runs: int) -> list[list[tuple[int, int]]]:
    return [cluster for cluster in cluster_runs_by_gap(runs, max_gap) if len(cluster) >= min_runs]


def select_vertical_table_cluster(
    runs: Sequence[tuple[int, int]],
    *,
    crop_w: int,
    max_gap: int,
    min_runs: int,
) -> tuple[list[tuple[int, int]], dict[str, Any]]:
    """Select vertical rule evidence without collapsing split-column tables.

    The first localizer version picked the single densest vertical-rule cluster.
    That was safe for one contiguous table, but on IPC-style pages with two
    side-by-side column groups it could lock onto only one group.  Here we keep
    the same conservative single-cluster fallback, but merge multiple eligible
    vertical clusters when they look like one multi-column table body rather than
    unrelated page furniture.
    """
    diagnostics = {
        "vertical_cluster_count": 0,
        "eligible_vertical_cluster_count": 0,
        "multi_column_vertical_merge_applied": False,
    }
    clusters = cluster_runs_by_gap(runs, max_gap)
    eligible = [cluster for cluster in clusters if len(cluster) >= min_runs]
    diagnostics["vertical_cluster_count"] = len(clusters)
    diagnostics["eligible_vertical_cluster_count"] = len(eligible)
    if not eligible:
        return [], diagnostics

    # Standard single-cluster result remains the fallback.
    best = max(eligible, key=lambda c: (len(c), c[-1][1] - c[0][0]))
    if len(eligible) < 2 or crop_w <= 0:
        return best, diagnostics

    # Merge clusters only when the combined span is table-like: neither a tiny
    # isolated column nor almost the whole page.  This targets split-column
    # manual tables while avoiding page-header/footer artifacts.
    eligible_sorted = sorted(eligible, key=lambda c: c[0][0])
    merged = [run for cluster in eligible_sorted for run in cluster]
    combined_span = merged[-1][1] - merged[0][0]
    best_span = best[-1][1] - best[0][0]
    cluster_count = len(eligible_sorted)
    largest_gap = max(
        eligible_sorted[i + 1][0][0] - eligible_sorted[i][-1][1]
        for i in range(len(eligible_sorted) - 1)
    )

    if (
        cluster_count >= 2
        and combined_span >= max(best_span * 1.35, crop_w * 0.28)
        and combined_span <= crop_w * 0.92
        and largest_gap <= crop_w * 0.34
    ):
        diagnostics["multi_column_vertical_merge_applied"] = True
        diagnostics["multi_column_vertical_cluster_count"] = cluster_count
        diagnostics["multi_column_vertical_combined_span_ratio"] = round(combined_span / float(crop_w), 6)
        return merged, diagnostics

    return best, diagnostics


def suppress_footer_with_structural_rows(
    y0: int,
    y1: int,
    *,
    crop_h: int,
    row_counts: Sequence[int],
    table_x_span: int,
    horizontal_line_rows: Sequence[int],
) -> tuple[int, dict[str, Any]]:
    """Trim bottom page furniture when it is below the structural table body.

    Footer/page-number labels often produce dark pixels but not repeated table
    ruling.  This function only trims when there is a clear structural row near
    the table body and a meaningful low-signal tail below it.
    """
    diagnostics = {
        "footer_suppression_applied": False,
        "footer_suppression_candidate_gap": 0,
    }
    if crop_h <= 0 or y1 <= y0 or not row_counts:
        return y1, diagnostics

    row_threshold = max(8, int(max(1, table_x_span) * 0.05))
    structural_rows = sorted({
        row
        for row in range(max(0, y0), min(crop_h, y1 + 1))
        if row_counts[row] >= row_threshold
    } | {row for row in horizontal_line_rows if y0 <= row <= y1})
    if len(structural_rows) < 4:
        return y1, diagnostics

    # Ignore isolated footer rows by looking for the last row that is close to
    # prior structural evidence.  True tables have repeated row bands/rules.
    clustered_rows = []
    prev = None
    for row in structural_rows:
        if prev is None or row - prev <= max(22, int(crop_h * 0.018)):
            clustered_rows.append(row)
        else:
            # Start a new tail cluster only if it is not too far into the page.
            # This prevents a lone footer/page number from extending the body.
            if row < crop_h * 0.88:
                clustered_rows.append(row)
        prev = row

    if not clustered_rows:
        return y1, diagnostics
    last_body_row = clustered_rows[-1]
    gap = y1 - last_body_row
    diagnostics["footer_suppression_candidate_gap"] = int(gap)
    if gap >= max(36, int(crop_h * 0.045)):
        new_y1 = min(y1, last_body_row + max(8, int(crop_h * 0.01)))
        if new_y1 > y0 and new_y1 < y1:
            diagnostics["footer_suppression_applied"] = True
            diagnostics["footer_suppression_removed_pixels"] = int(y1 - new_y1)
            return new_y1, diagnostics
    return y1, diagnostics


def choose_content_extent(
    dark_x: Sequence[int],
    dark_y: Sequence[int],
    crop_w: int,
    crop_h: int,
    row_counts: Sequence[int],
    col_counts: Sequence[int],
) -> tuple[int, int, int, int, dict[str, Any]] | None:
    if len(dark_x) < 25 or crop_w < 8 or crop_h < 8:
        return None

    xs = sorted(dark_x)
    ys = sorted(dark_y)
    px0, px1 = percentile(xs, 0.015), percentile(xs, 0.985)
    py0, py1 = percentile(ys, 0.015), percentile(ys, 0.985)

    horizontal_line_rows = [i for i, count in enumerate(row_counts) if count >= max(16, int(crop_w * 0.18))]
    vertical_line_cols = [i for i, count in enumerate(col_counts) if count >= max(12, int(crop_h * 0.12))]
    h_runs = find_runs(horizontal_line_rows, max_gap=2)
    v_runs = find_runs(vertical_line_cols, max_gap=2)

    h_cluster = best_run_cluster(h_runs, max_gap=max(18, int(crop_h * 0.12)), min_runs=3)
    v_cluster, v_cluster_diag = select_vertical_table_cluster(
        v_runs,
        crop_w=crop_w,
        max_gap=max(18, int(crop_w * 0.12)),
        min_runs=2,
    )

    # Single broad header/footer lines are common in manuals.  Requiring repeated
    # line evidence keeps those outliers from stretching the table crop back to
    # page-content scale.
    if h_cluster:
        py0 = h_cluster[0][0]
        py1 = h_cluster[-1][1]
    elif h_runs:
        py0 = min(py0, h_runs[0][0])
        py1 = max(py1, h_runs[-1][1])

    if v_cluster:
        px0 = v_cluster[0][0]
        px1 = v_cluster[-1][1]
    elif v_runs:
        px0 = min(px0, v_runs[0][0])
        px1 = max(px1, v_runs[-1][1])

    pad_x = max(4, int(round(crop_w * 0.012)))
    pad_y = max(4, int(round(crop_h * 0.012)))
    x0 = max(0, px0 - pad_x)
    y0 = max(0, py0 - pad_y)
    x1 = min(crop_w - 1, px1 + pad_x)
    y1 = min(crop_h - 1, py1 + pad_y)

    y1, footer_diag = suppress_footer_with_structural_rows(
        y0,
        y1,
        crop_h=crop_h,
        row_counts=row_counts,
        table_x_span=max(1, x1 - x0),
        horizontal_line_rows=horizontal_line_rows,
    )

    if x1 - x0 < max(24, crop_w * 0.08) or y1 - y0 < max(24, crop_h * 0.08):
        return None

    row_band_rows = [i for i, count in enumerate(row_counts) if count >= max(4, int(crop_w * 0.025))]
    col_band_cols = [i for i, count in enumerate(col_counts) if count >= max(4, int(crop_h * 0.025))]

    diagnostics = {
        "dark_pixel_count": len(dark_x),
        "dark_pixel_ratio": round(len(dark_x) / float(crop_w * crop_h), 6),
        "horizontal_line_run_count": len(h_runs),
        "vertical_line_run_count": len(v_runs),
        "selected_horizontal_line_cluster_count": len(h_cluster),
        "selected_vertical_line_cluster_count": len(v_cluster),
        "row_band_run_count": len(find_runs(row_band_rows, max_gap=3)),
        "column_band_run_count": len(find_runs(col_band_cols, max_gap=3)),
        "horizontal_line_rows": len(horizontal_line_rows),
        "vertical_line_cols": len(vertical_line_cols),
    }
    diagnostics.update(v_cluster_diag)
    diagnostics.update(footer_diag)
    return x0, y0, x1, y1, diagnostics


def refine_bbox_with_visual_signal(image_path: Path, input_bbox: Mapping[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    diagnostics: dict[str, Any] = {
        "visual_refinement_attempted": True,
        "visual_refinement_applied": False,
        "visual_refinement_rejection_reason": None,
    }
    if Image is None:
        diagnostics["visual_refinement_rejection_reason"] = "pillow_unavailable"
        return None, diagnostics
    try:
        with Image.open(image_path) as image:
            gray = image.convert("L")
            page_w, page_h = gray.size
            box = bbox_from_value(input_bbox, page_w, page_h)
            if not box:
                diagnostics["visual_refinement_rejection_reason"] = "invalid_input_bbox"
                return None, diagnostics
            x0 = int(max(0, min(page_w - 1, math.floor(float(box["x0"])))))
            y0 = int(max(0, min(page_h - 1, math.floor(float(box["y0"])))))
            x1 = int(max(x0 + 1, min(page_w, math.ceil(float(box["x1"])))))
            y1 = int(max(y0 + 1, min(page_h, math.ceil(float(box["y1"])))))
            crop = gray.crop((x0, y0, x1, y1))
            crop_w, crop_h = crop.size
            if crop_w < 24 or crop_h < 24:
                diagnostics["visual_refinement_rejection_reason"] = "input_crop_too_small"
                return None, diagnostics

            pixels = list(crop.tobytes())
            threshold = otsu_threshold(pixels)
            row_counts = [0] * crop_h
            col_counts = [0] * crop_w
            dark_x: list[int] = []
            dark_y: list[int] = []
            for idx, value in enumerate(pixels):
                if value <= threshold:
                    yy, xx = divmod(idx, crop_w)
                    row_counts[yy] += 1
                    col_counts[xx] += 1
                    dark_x.append(xx)
                    dark_y.append(yy)

            diagnostics["visual_dark_threshold"] = threshold
            extent = choose_content_extent(dark_x, dark_y, crop_w, crop_h, row_counts, col_counts)
            if extent is None:
                diagnostics["visual_refinement_rejection_reason"] = "weak_or_tiny_visual_extent"
                diagnostics["dark_pixel_count"] = len(dark_x)
                diagnostics["dark_pixel_ratio"] = round(len(dark_x) / float(crop_w * crop_h), 6)
                return None, diagnostics
            rx0, ry0, rx1, ry1, extent_diag = extent
            diagnostics.update(extent_diag)
            refined = clamp_bbox(x0 + rx0, y0 + ry0, x0 + rx1, y0 + ry1, page_w, page_h)
            if not refined:
                diagnostics["visual_refinement_rejection_reason"] = "refined_bbox_invalid"
                return None, diagnostics

            input_area = bbox_area(box)
            refined_area = bbox_area(refined)
            area_ratio = refined_area / input_area if input_area > 0 else 1.0
            diagnostics["input_bbox_area"] = round(input_area, 3)
            diagnostics["refined_bbox_area"] = round(refined_area, 3)
            diagnostics["refined_to_input_area_ratio"] = round(area_ratio, 6)
            diagnostics["input_bbox_coverage_ratio"] = bbox_coverage(box, page_w, page_h)
            diagnostics["refined_bbox_coverage_ratio"] = bbox_coverage(refined, page_w, page_h)

            # Avoid destructive over-tightening. Tiny improvements are still useful as QA but not selected.
            if area_ratio < 0.08:
                diagnostics["visual_refinement_rejection_reason"] = "refined_bbox_too_aggressive"
                return None, diagnostics
            if area_ratio > 0.985:
                diagnostics["visual_refinement_rejection_reason"] = "no_meaningful_tightening"
                return None, diagnostics

            diagnostics["visual_refinement_applied"] = True
            return refined, diagnostics
    except Exception as exc:  # pragma: no cover - defensive for corrupt images.
        diagnostics["visual_refinement_rejection_reason"] = f"image_error:{type(exc).__name__}"
        return None, diagnostics


def review_flags_for_record(record: Mapping[str, Any]) -> list[str]:
    flags: list[str] = []
    input_cov = record.get("input_bbox_coverage_ratio")
    loc_cov = record.get("localized_bbox_coverage_ratio")
    if isinstance(input_cov, (int, float)) and input_cov >= 0.60:
        flags.append("input_bbox_broad_page_coverage")
    if isinstance(loc_cov, (int, float)) and loc_cov >= 0.55:
        flags.append("localized_bbox_still_broad")
    if record.get("visual_refinement_applied") is not True:
        flags.append("visual_refinement_not_applied")
    if record.get("multi_column_vertical_merge_applied"):
        flags.append("split_column_table_geometry_merged")
    if record.get("footer_suppression_applied"):
        flags.append("footer_page_furniture_suppressed")
    if (record.get("horizontal_line_run_count") or 0) < 2 and (record.get("row_band_run_count") or 0) < 4:
        flags.append("weak_horizontal_table_signal")
    if (record.get("vertical_line_run_count") or 0) < 2 and (record.get("column_band_run_count") or 0) < 2:
        flags.append("weak_vertical_table_signal")
    return flags


def source_cards(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    for key in (
        "table_ocr_bbox_enrichment_cards",
        "cards",
        "records",
        "table_bbox_scoped_cell_extraction_records",
        "scoped_table_records",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


def build_record(card: Mapping[str, Any], *, image_root: Path | None, image_index: Mapping[str, Path]) -> dict[str, Any]:
    page_id = first_present(card, PAGE_ID_KEYS)
    table_id = first_present(card, TABLE_ID_KEYS) or stable_id("table", page_id)
    image_path_text, image_confidence = resolve_image_path(card, image_root, image_index)
    image_path = Path(image_path_text) if image_path_text else None
    page_w, page_h = image_dimensions(image_path)
    input_bbox, input_key = select_input_bbox(card, page_w, page_h)

    record: dict[str, Any] = {
        "visual_bbox_localizer_id": stable_id("tblvisbbox", page_id, table_id),
        "schema_version": SCHEMA_VERSION,
        "page_id": page_id,
        "table_id": table_id,
        "source_card_id": card.get("ocr_bbox_enrichment_id") or card.get("card_id") or card.get("id"),
        "image_path": image_path_text,
        "image_resolution_confidence": image_confidence,
        "image_available": bool(image_path and image_path.exists()),
        "image_width": page_w,
        "image_height": page_h,
        "input_bbox": input_bbox,
        "input_bbox_key": input_key,
        "input_bbox_source": card.get("bbox_source") or card.get("table_extraction_bbox_source"),
        "input_bbox_coverage_ratio": bbox_coverage(input_bbox, page_w, page_h),
        "visual_refinement_attempted": False,
        "visual_refinement_applied": False,
        "localized_table_bbox": input_bbox,
        "localized_bbox_source": "input_bbox_fallback",
        "localized_bbox_coverage_ratio": bbox_coverage(input_bbox, page_w, page_h),
        "table_localization_ready": False,
        "table_localization_quality_pass": False,
        "routing_only": True,
        "retrieval_only": True,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
        "postgres_write_attempted": False,
        "qdrant_write_attempted": False,
        "opensearch_write_attempted": False,
        "unsafe_table_visual_bbox_localizer_record": False,
    }

    if image_path and image_path.exists() and input_bbox:
        refined, diag = refine_bbox_with_visual_signal(image_path, input_bbox)
        record.update(diag)
        if refined:
            record["localized_table_bbox"] = refined
            record["localized_bbox_source"] = "visual_dark_pixel_line_refined"
            record["localized_bbox_coverage_ratio"] = bbox_coverage(refined, page_w, page_h)
            record["table_localization_ready"] = True
        else:
            record["table_localization_ready"] = input_bbox is not None
    else:
        record["visual_refinement_rejection_reason"] = "missing_image_or_input_bbox"
        record["table_localization_ready"] = input_bbox is not None

    # If refinement cannot apply, input bbox can be a safe fallback, but not visual-quality PASS.
    record["review_flags"] = review_flags_for_record(record)
    record["table_localization_quality_pass"] = (
        record.get("table_localization_ready") is True
        and record.get("visual_refinement_applied") is True
        and "localized_bbox_still_broad" not in record["review_flags"]
    )
    return record


def summarize(records: Sequence[Mapping[str, Any]], source_quality: str | None) -> dict[str, Any]:
    summary = {
        "source_table_ocr_bbox_enrichment_quality_status": source_quality,
        "source_card_count": len(records),
        "localized_record_count": len(records),
        "image_available_record_count": sum(1 for r in records if r.get("image_available")),
        "input_bbox_record_count": sum(1 for r in records if r.get("input_bbox")),
        "visual_refinement_attempted_record_count": sum(1 for r in records if r.get("visual_refinement_attempted")),
        "visual_refined_bbox_record_count": sum(1 for r in records if r.get("visual_refinement_applied")),
        "input_bbox_fallback_record_count": sum(1 for r in records if r.get("localized_bbox_source") == "input_bbox_fallback"),
        "table_localization_ready_record_count": sum(1 for r in records if r.get("table_localization_ready")),
        "table_localization_quality_pass_record_count": sum(1 for r in records if r.get("table_localization_quality_pass")),
        "broad_input_bbox_record_count": sum(1 for r in records if "input_bbox_broad_page_coverage" in (r.get("review_flags") or [])),
        "localized_bbox_still_broad_record_count": sum(1 for r in records if "localized_bbox_still_broad" in (r.get("review_flags") or [])),
        "weak_visual_table_signal_record_count": sum(
            1
            for r in records
            if "weak_horizontal_table_signal" in (r.get("review_flags") or [])
            or "weak_vertical_table_signal" in (r.get("review_flags") or [])
        ),
        "split_column_geometry_merged_record_count": sum(1 for r in records if r.get("multi_column_vertical_merge_applied")),
        "footer_page_furniture_suppressed_record_count": sum(1 for r in records if r.get("footer_suppression_applied")),
        "unsafe_table_visual_bbox_localizer_record_count": sum(1 for r in records if r.get("unsafe_table_visual_bbox_localizer_record")),
        "answer_permission_count": sum(1 for r in records if r.get("answer_permission")),
        "can_answer_directly_count": sum(1 for r in records if r.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for r in records if r.get("can_prove_claims")),
        "source_truth_mutation_allowed_count": sum(1 for r in records if r.get("source_truth_mutation_allowed")),
        "postgres_write_attempt_count": sum(1 for r in records if r.get("postgres_write_attempted")),
        "qdrant_write_attempt_count": sum(1 for r in records if r.get("qdrant_write_attempted")),
        "opensearch_write_attempt_count": sum(1 for r in records if r.get("opensearch_write_attempted")),
    }
    ratios = [r.get("localized_bbox_coverage_ratio") for r in records if isinstance(r.get("localized_bbox_coverage_ratio"), (int, float))]
    if ratios:
        summary["localized_bbox_coverage_ratio_median"] = round(statistics.median(ratios), 6)
        summary["localized_bbox_coverage_ratio_max"] = round(max(ratios), 6)
    return summary


def quality_errors(summary: Mapping[str, Any], args: argparse.Namespace) -> list[str]:
    errors: list[str] = []
    def get_count(key: str) -> int:
        value = summary.get(key, 0)
        return int(value) if isinstance(value, (int, float)) else 0

    if args.require_table_ocr_bbox_enrichment_quality_pass and summary.get("source_table_ocr_bbox_enrichment_quality_status") != "PASS":
        errors.append("source_table_ocr_bbox_enrichment_quality_status_not_pass")
    if get_count("source_card_count") < args.min_source_cards:
        errors.append("source_card_count_below_min")
    if get_count("localized_record_count") < args.min_localized_records:
        errors.append("localized_record_count_below_min")
    if get_count("image_available_record_count") < args.min_image_available_records:
        errors.append("image_available_record_count_below_min")
    if get_count("visual_refined_bbox_record_count") < args.min_visual_refined_records:
        errors.append("visual_refined_bbox_record_count_below_min")
    if get_count("table_localization_ready_record_count") < args.min_localization_ready_records:
        errors.append("table_localization_ready_record_count_below_min")
    if get_count("table_localization_quality_pass_record_count") < args.min_localization_quality_pass_records:
        errors.append("table_localization_quality_pass_record_count_below_min")
    if get_count("unsafe_table_visual_bbox_localizer_record_count") > args.max_unsafe_records:
        errors.append("unsafe_table_visual_bbox_localizer_record_count_above_max")
    if get_count("answer_permission_count") > args.max_answer_permission_count:
        errors.append("answer_permission_count_above_max")
    if get_count("source_truth_mutation_allowed_count") > args.max_source_truth_mutation_allowed:
        errors.append("source_truth_mutation_allowed_count_above_max")
    if args.require_no_answer_permission and get_count("answer_permission_count") != 0:
        errors.append("answer_permission_count_not_zero")
    for key in ("postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"):
        if get_count(key) != 0:
            errors.append(f"{key}_not_zero")
    return errors


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    source_path = Path(args.table_ocr_bbox_enrichment)
    output_dir = Path(args.output_dir)
    image_root = Path(args.image_root) if args.image_root else None
    source = load_json(source_path)
    cards = source_cards(source)
    image_index = build_image_index(image_root, args.max_image_files_scanned)
    records = [build_record(card, image_root=image_root, image_index=image_index) for card in cards]
    summary = summarize(records, source.get("quality_status"))
    errors = quality_errors(summary, args)
    quality_status = "PASS" if not errors else "FAIL"
    now = utc_now()

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT if records else STATUS_NOT_READY,
        "quality_status": quality_status,
        "generated_at": now,
        "inputs": {
            "table_ocr_bbox_enrichment": str(source_path),
            "image_root": str(image_root) if image_root else None,
        },
        "summary": summary,
        "quality_errors": errors,
        "table_visual_bbox_localizer_records": records,
        "visual_localization_records": records,
    }

    report_path = output_dir / "trace_net_table_visual_bbox_localizer_v1.json"
    records_path = output_dir / "trace_net_table_visual_bbox_localizer_v1_records.jsonl"
    summary_path = output_dir / "trace_net_table_visual_bbox_localizer_v1_summary.json"
    quality_path = output_dir / "trace_net_table_visual_bbox_localizer_v1_quality.json"
    manifest_path = output_dir / "trace_net_table_visual_bbox_localizer_v1_manifest.json"

    write_json(report_path, payload)
    write_jsonl(records_path, records)
    write_json(summary_path, summary)
    quality_payload = {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "quality_status": quality_status,
        "generated_at": now,
        "report_path": str(report_path),
        "summary": summary,
        "quality_errors": errors,
    }
    write_json(quality_path, quality_payload)
    write_json(manifest_path, {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": now,
        "quality_status": quality_status,
        "report_path": str(report_path),
        "records_path": str(records_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "record_count": len(records),
    })
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net table visual bbox localizer v1")
    parser.add_argument("--table-ocr-bbox-enrichment", required=True)
    parser.add_argument("--image-root", default=".")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-image-files-scanned", type=int, default=25000)
    parser.add_argument("--min-source-cards", type=int, default=1)
    parser.add_argument("--min-localized-records", type=int, default=1)
    parser.add_argument("--min-image-available-records", type=int, default=1)
    parser.add_argument("--min-visual-refined-records", type=int, default=1)
    parser.add_argument("--min-localization-ready-records", type=int, default=1)
    parser.add_argument("--min-localization-quality-pass-records", type=int, default=0)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-ocr-bbox-enrichment-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true", help="Kept for CLI symmetry; quality is always computed.")
    parser.add_argument("--write-json", action="store_true", help="Accepted for check-script symmetry.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    payload = build_report(args)
    summary = payload["summary"]
    print("TRACE-Net Table Visual BBox Localizer v1")
    print(f" Status: {payload['status']}")
    print(f" Quality status: {payload['quality_status']}")
    for key in (
        "source_card_count",
        "localized_record_count",
        "image_available_record_count",
        "input_bbox_record_count",
        "visual_refinement_attempted_record_count",
        "visual_refined_bbox_record_count",
        "input_bbox_fallback_record_count",
        "table_localization_ready_record_count",
        "table_localization_quality_pass_record_count",
        "broad_input_bbox_record_count",
        "localized_bbox_still_broad_record_count",
        "weak_visual_table_signal_record_count",
        "split_column_geometry_merged_record_count",
        "footer_page_furniture_suppressed_record_count",
        "unsafe_table_visual_bbox_localizer_record_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {Path(args.output_dir) / 'trace_net_table_visual_bbox_localizer_v1.json'}")
    return 0 if payload["quality_status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
