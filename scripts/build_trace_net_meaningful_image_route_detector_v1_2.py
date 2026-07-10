#!/usr/bin/env python3
"""TRACE-Net meaningful image route detector v1.2.

Read-only TIFF/page-image route audit that separates true meaningful visual pages
from table/text/blank/front-matter pages before expensive vision routing.

Safety contract:
- Does not call OCR/LLM/Ollama.
- Does not write Postgres/Qdrant/OpenSearch.
- Does not mutate source TIFFs or source-truth artifacts.
- Does not grant answer permission.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import re
import statistics
import zipfile
from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "Pillow is required for TIFF/image inspection. Install with: python -m pip install Pillow"
    ) from exc


MODULE_NAME = "trace_net_meaningful_image_route_detector_v1_2"
DEFAULT_PAGE_ID_PREFIX = "t_p_120_1176"

IMAGE_EXTS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp", ".webp"}

POSITIVE_FIGURE_TERMS = {
    "figure",
    "fig.",
    "detail",
    "view",
    "section",
    "typ",
    "ref",
    "assembly",
    "exploded",
    "diagram",
    "illustration",
}

NEGATIVE_FRONT_MATTER_TERMS = {
    "table of contents",
    "list of effective pages",
    "revision record",
    "service bulletin",
    "numerical index",
    "record of revisions",
    "temporary revision",
}

TABLE_TERMS = {
    "table",
    "qty",
    "nomenclature",
    "part number",
    "item",
    "units per assy",
    "effectivity",
}


@dataclass(frozen=True)
class ImageRef:
    source_type: str
    path: str
    zip_member: str = ""

    @property
    def display_path(self) -> str:
        if self.source_type == "zip":
            return f"{self.path}!{self.zip_member}"
        return self.path


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def read_json_or_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return
    if path.suffix.lower() == ".jsonl":
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict):
                yield obj
        return

    try:
        obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return

    if isinstance(obj, dict):
        for key in ("records", "pages", "decisions", "items", "results"):
            value = obj.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        yield item
                return
        yield obj
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                yield item


def canonical_page_id_from_number(page_number: int, page_id_prefix: str = DEFAULT_PAGE_ID_PREFIX) -> str:
    return f"{page_id_prefix}_p{int(page_number):06d}"


def extract_page_number(text: str) -> Optional[int]:
    patterns = [
        r"(?:^|[_\-/\\])p(?:age)?[_-]?0*([0-9]{1,6})(?:\D|$)",
        r"(?:^|[_\-/\\])pg[_-]?0*([0-9]{1,6})(?:\D|$)",
        r"(?:^|[_\-/\\])0*([0-9]{1,6})(?:\.(?:tif|tiff|png|jpg|jpeg|bmp|webp)$)",
    ]
    lower = text.lower()
    for pat in patterns:
        m = re.search(pat, lower)
        if m:
            try:
                n = int(m.group(1))
                if n > 0:
                    return n
            except Exception:
                pass
    return None


def extract_page_id(text: str, page_id_prefix: str = DEFAULT_PAGE_ID_PREFIX) -> Optional[str]:
    m = re.search(r"(t_p_\d+_\d+_p\d{6})", text)
    if m:
        return m.group(1)

    m = re.search(r"([A-Za-z0-9]+_[A-Za-z0-9]+_[A-Za-z0-9]+_p\d{6})", text)
    if m:
        return m.group(1)

    page_number = extract_page_number(text)
    if page_number is not None:
        return canonical_page_id_from_number(page_number, page_id_prefix)

    return None


def deep_find_strings(obj: Any, limit: int = 1200) -> List[str]:
    found: List[str] = []

    def walk(x: Any) -> None:
        if len(found) >= limit:
            return
        if isinstance(x, str):
            if x.strip():
                found.append(x.strip())
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x[:200]:
                walk(v)

    walk(obj)
    return found


def first_value_by_key(obj: Any, keys: Sequence[str]) -> Optional[Any]:
    keyset = {k.lower() for k in keys}

    def walk(x: Any) -> Optional[Any]:
        if isinstance(x, dict):
            for k, v in x.items():
                if str(k).lower() in keyset:
                    return v
            for v in x.values():
                got = walk(v)
                if got is not None:
                    return got
        elif isinstance(x, list):
            for v in x[:100]:
                got = walk(v)
                if got is not None:
                    return got
        return None

    return walk(obj)


def load_route_manifest(path: Optional[Path], page_id_prefix: str) -> Dict[str, Dict[str, Any]]:
    if not path:
        return {}
    routes: Dict[str, Dict[str, Any]] = {}
    for rec in read_json_or_jsonl(path) or []:
        strings = deep_find_strings(rec, limit=60)
        page_id = None
        for key in ("page_id", "source_page_id", "canonical_page_id", "id"):
            value = first_value_by_key(rec, [key])
            if isinstance(value, str):
                page_id = extract_page_id(value, page_id_prefix) or value
                break
        if not page_id:
            for s in strings:
                page_id = extract_page_id(s, page_id_prefix)
                if page_id:
                    break
        if not page_id:
            continue

        route_value = first_value_by_key(
            rec,
            [
                "primary_route",
                "route",
                "selected_route",
                "route_decision",
                "route_name",
                "primary_route_name",
                "decision",
            ],
        )
        route_text = ""
        if isinstance(route_value, str):
            route_text = route_value
        elif route_value is not None:
            route_text = json.dumps(route_value, ensure_ascii=False)[:500]
        else:
            route_text = " ".join(strings[:20])

        lower = route_text.lower()
        old_image_candidate = "image_visual" in lower or (
            "visual" in lower and "table" not in lower
        )

        routes[page_id] = {
            "page_id": page_id,
            "old_route": route_text,
            "old_image_visual_candidate": old_image_candidate,
            "source_route_record_preview": rec if len(json.dumps(rec, default=str)) < 2500 else None,
        }
    return routes


def discover_image_refs(
    roots: Sequence[Path],
    zip_paths: Sequence[Path],
) -> List[ImageRef]:
    refs: List[ImageRef] = []

    for root in roots:
        if not root.exists():
            continue
        if root.is_file() and root.suffix.lower() in IMAGE_EXTS:
            refs.append(ImageRef("file", str(root)))
            continue
        if root.is_dir():
            for path in root.rglob("*"):
                if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
                    refs.append(ImageRef("file", str(path)))

    for zpath in zip_paths:
        if not zpath.exists():
            continue
        with zipfile.ZipFile(zpath, "r") as z:
            for name in z.namelist():
                if Path(name).suffix.lower() in IMAGE_EXTS and not name.endswith("/"):
                    refs.append(ImageRef("zip", str(zpath), name))

    return sorted(refs, key=lambda r: r.display_path.lower())


def open_image_ref(ref: ImageRef) -> Image.Image:
    if ref.source_type == "zip":
        with zipfile.ZipFile(ref.path, "r") as z:
            data = z.read(ref.zip_member)
        return Image.open(io.BytesIO(data))
    return Image.open(ref.path)


def threshold_image(gray: Image.Image) -> Tuple[Image.Image, int]:
    hist = gray.histogram()
    total = sum(hist)
    if total <= 0:
        return gray.point(lambda p: 0), 220

    # Robust scan threshold for technical black-on-white pages.
    # Use bright background expectation but adapt if scans are darker.
    cumulative = 0
    p90 = 240
    for idx, count in enumerate(hist):
        cumulative += count
        if cumulative >= total * 0.90:
            p90 = idx
            break
    threshold = int(clamp(p90 - 28, 155, 225))
    binary = gray.point(lambda p: 255 if p < threshold else 0, "L")
    return binary, threshold


def group_positions(values: Sequence[int], min_gap: int = 2) -> List[Tuple[int, int, int]]:
    if not values:
        return []
    groups: List[Tuple[int, int, int]] = []
    start = prev = values[0]
    count = 1
    for v in values[1:]:
        if v <= prev + min_gap:
            prev = v
            count += 1
        else:
            groups.append((start, prev, count))
            start = prev = v
            count = 1
    groups.append((start, prev, count))
    return groups


def spacing_regularity(positions: Sequence[int]) -> float:
    if len(positions) < 4:
        return 0.0
    gaps = [b - a for a, b in zip(positions, positions[1:]) if b > a]
    if len(gaps) < 3:
        return 0.0
    mean_gap = statistics.mean(gaps)
    if mean_gap <= 0:
        return 0.0
    try:
        std = statistics.pstdev(gaps)
    except Exception:
        return 0.0
    return clamp(1.0 - (std / max(mean_gap, 1.0)))


def connected_components(binary: Image.Image, max_dim: int = 380) -> List[Dict[str, float]]:
    img = binary.copy()
    img.thumbnail((max_dim, max_dim))
    w, h = img.size
    pix = img.load()
    total = w * h
    visited = bytearray(total)
    comps: List[Dict[str, float]] = []

    def idx(x: int, y: int) -> int:
        return y * w + x

    for y in range(h):
        for x in range(w):
            i = idx(x, y)
            if visited[i] or pix[x, y] == 0:
                visited[i] = 1
                continue

            visited[i] = 1
            q = deque([(x, y)])
            minx = maxx = x
            miny = maxy = y
            area = 0

            while q:
                cx, cy = q.popleft()
                area += 1
                if cx < minx:
                    minx = cx
                if cx > maxx:
                    maxx = cx
                if cy < miny:
                    miny = cy
                if cy > maxy:
                    maxy = cy

                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if nx < 0 or ny < 0 or nx >= w or ny >= h:
                        continue
                    ni = idx(nx, ny)
                    if visited[ni]:
                        continue
                    visited[ni] = 1
                    if pix[nx, ny] != 0:
                        q.append((nx, ny))

            if area < 3:
                continue
            bw = maxx - minx + 1
            bh = maxy - miny + 1
            bbox_area = max(1, bw * bh)
            comps.append(
                {
                    "x": minx / w,
                    "y": miny / h,
                    "w": bw / w,
                    "h": bh / h,
                    "area_ratio": area / total,
                    "bbox_area_ratio": bbox_area / total,
                    "fill_ratio": area / bbox_area,
                    "aspect_ratio": bw / max(1, bh),
                }
            )

    return comps


def projection_features(binary: Image.Image) -> Dict[str, Any]:
    w, h = binary.size
    pix = binary.load()

    row_counts = []
    for y in range(h):
        row_counts.append(sum(1 for x in range(w) if pix[x, y] != 0))
    col_counts = []
    for x in range(w):
        col_counts.append(sum(1 for y in range(h) if pix[x, y] != 0))

    row_fracs = [c / max(1, w) for c in row_counts]
    col_fracs = [c / max(1, h) for c in col_counts]

    hline_rows = [i for i, f in enumerate(row_fracs) if f >= 0.38]
    vline_cols = [i for i, f in enumerate(col_fracs) if f >= 0.30]

    hgroups = group_positions(hline_rows, min_gap=3)
    vgroups = group_positions(vline_cols, min_gap=3)

    hpos = [int((a + b) / 2) for a, b, _ in hgroups]
    vpos = [int((a + b) / 2) for a, b, _ in vgroups]

    text_like_rows = [i for i, f in enumerate(row_fracs) if 0.015 <= f <= 0.23]
    text_bands = group_positions(text_like_rows, min_gap=2)

    heavy_cols = [i for i, f in enumerate(col_fracs) if f >= 0.10]
    heavy_col_bands = group_positions(heavy_cols, min_gap=4)

    return {
        "horizontal_line_count": len(hgroups),
        "vertical_line_count": len(vgroups),
        "horizontal_line_positions": hpos[:80],
        "vertical_line_positions": vpos[:80],
        "horizontal_line_regularity": spacing_regularity(hpos),
        "vertical_line_regularity": spacing_regularity(vpos),
        "text_line_band_count": len(text_bands),
        "heavy_column_band_count": len(heavy_col_bands),
        "row_coverage_p95": sorted(row_fracs)[int(len(row_fracs) * 0.95)] if row_fracs else 0.0,
        "col_coverage_p95": sorted(col_fracs)[int(len(col_fracs) * 0.95)] if col_fracs else 0.0,
    }


def collect_ocr_text_for_page(ocr_roots: Sequence[Path], page_id: str) -> str:
    if not ocr_roots:
        return ""
    chunks: List[str] = []
    for root in ocr_roots:
        if not root.exists():
            continue
        candidates: List[Path] = []
        if root.is_file():
            candidates = [root]
        else:
            # Keep bounded; only page-specific files.
            candidates = list(root.rglob(f"*{page_id}*"))
        for path in candidates[:20]:
            if not path.is_file() or path.suffix.lower() not in {".json", ".jsonl", ".txt"}:
                continue
            try:
                if path.suffix.lower() == ".txt":
                    chunks.append(path.read_text(encoding="utf-8", errors="replace")[:5000])
                else:
                    for rec in read_json_or_jsonl(path) or []:
                        chunks.extend(deep_find_strings(rec, limit=120))
            except Exception:
                continue
    return "\n".join(chunks)[:12000]


def term_score(text: str, terms: Sequence[str]) -> float:
    if not text:
        return 0.0
    lower = text.lower()
    hits = sum(1 for t in terms if t in lower)
    return clamp(hits / max(1, min(4, len(terms))))


def analyze_image(
    ref: ImageRef,
    page_id_prefix: str,
    old_route_record: Optional[Dict[str, Any]] = None,
    ocr_text: str = "",
    max_analyze_dim: int = 900,
) -> Dict[str, Any]:
    source_text = ref.display_path
    page_number = extract_page_number(source_text)
    page_id = extract_page_id(source_text, page_id_prefix)
    if not page_id and page_number is not None:
        page_id = canonical_page_id_from_number(page_number, page_id_prefix)

    with open_image_ref(ref) as img:
        original_size = img.size
        gray = img.convert("L")
        gray.thumbnail((max_analyze_dim, max_analyze_dim))
        binary, threshold = threshold_image(gray)

    w, h = binary.size
    pixels = list(binary.getdata())
    ink_pixels = sum(1 for p in pixels if p != 0)
    ink_density = ink_pixels / max(1, len(pixels))

    proj = projection_features(binary)
    comps = connected_components(binary)

    large_components = [
        c
        for c in comps
        if c["bbox_area_ratio"] >= 0.010
        or (c["w"] >= 0.18 and c["h"] >= 0.08 and c["area_ratio"] >= 0.0015)
    ]
    irregular_large_components = [
        c
        for c in large_components
        if c["fill_ratio"] <= 0.55
        and c["aspect_ratio"] <= 16
        and c["aspect_ratio"] >= 0.08
        and not (c["h"] <= 0.025 and c["w"] >= 0.35)
    ]
    small_label_like = [
        c
        for c in comps
        if 0.00001 <= c["area_ratio"] <= 0.0018
        and c["bbox_area_ratio"] <= 0.006
        and 0.12 <= c["aspect_ratio"] <= 10.0
    ]

    hlines = int(proj["horizontal_line_count"])
    vlines = int(proj["vertical_line_count"])
    hreg = float(proj["horizontal_line_regularity"])
    vreg = float(proj["vertical_line_regularity"])
    text_bands = int(proj["text_line_band_count"])
    heavy_cols = int(proj["heavy_column_band_count"])

    table_grid_score = clamp(
        0.30 * clamp(hlines / 22)
        + 0.30 * clamp(vlines / 8)
        + 0.20 * clamp((hlines * max(vlines, 1)) / 180)
        + 0.10 * hreg
        + 0.10 * vreg
    )

    dense_text_score = clamp(
        0.45 * clamp(text_bands / 55)
        + 0.25 * clamp(ink_density / 0.105)
        + 0.15 * clamp(heavy_cols / 8)
        + 0.15 * clamp((text_bands * max(heavy_cols, 1)) / 250)
    )

    irregular_component_score = clamp(len(irregular_large_components) / 3)
    sparse_label_score = clamp(len(small_label_like) / 120)
    callout_proxy_score = clamp(
        0.45 * sparse_label_score
        + 0.35 * clamp(len(small_label_like) / max(1, len(large_components) * 20))
        + 0.20 * irregular_component_score
    )

    figure_text_score = term_score(ocr_text, sorted(POSITIVE_FIGURE_TERMS))
    front_matter_score = term_score(ocr_text, sorted(NEGATIVE_FRONT_MATTER_TERMS))
    table_text_score = term_score(ocr_text, sorted(TABLE_TERMS))

    # Diagram score intentionally requires positive image evidence and penalizes
    # table/text regularity. This is not "visual complexity"; it is meaningful visual content.
    diagram_score = clamp(
        0.34 * irregular_component_score
        + 0.24 * callout_proxy_score
        + 0.18 * sparse_label_score
        + 0.16 * figure_text_score
        + 0.08 * clamp(ink_density / 0.045)
        - 0.28 * table_grid_score
        - 0.18 * dense_text_score
        - 0.35 * front_matter_score
    )

    blank_score = 1.0 if ink_density < 0.0025 else clamp(1.0 - (ink_density / 0.018))
    table_score = clamp(
        0.62 * table_grid_score
        + 0.18 * dense_text_score
        + 0.12 * table_text_score
        + 0.08 * clamp((hlines + vlines) / 35)
        - 0.18 * irregular_component_score
    )
    text_score = clamp(
        0.62 * dense_text_score
        + 0.18 * clamp(text_bands / 65)
        + 0.12 * front_matter_score
        - 0.18 * table_grid_score
        - 0.12 * irregular_component_score
    )

    old_route = (old_route_record or {}).get("old_route", "")
    old_image_candidate = bool((old_route_record or {}).get("old_image_visual_candidate", False))

    reasons: List[str] = []
    route = "review_candidate"
    visual_subtype = "uncertain"
    confidence = 0.40

    # v1.2 calibration:
    # v1.1 over-promoted page-list/table pages to mixed_visual_table because
    # repeated table columns created many small label-like components and a few
    # irregular connected components. v1.2 requires stronger proof before a page
    # not already routed as image_visual can become an image route.
    has_grid_columns = vlines >= 6 or (vlines >= 3 and hlines >= 8)
    has_table_rows = hlines >= 8 or text_bands >= 24
    dense_page = dense_text_score >= 0.52 or ink_density >= 0.085
    small_label_noise = len(small_label_like) >= 90 and (has_grid_columns or dense_page)

    table_dominant = (
        table_grid_score >= 0.46
        or (hlines >= 9 and vlines >= 2)
        or (hlines >= 15 and hreg >= 0.55)
        or (text_bands >= 28 and heavy_cols >= 2 and ink_density >= 0.035)
        or (small_label_noise and figure_text_score == 0.0)
    )
    strong_table_dominant = (
        table_grid_score >= 0.58
        or (hlines >= 15 and vlines >= 3)
        or (vlines >= 18 and dense_text_score >= 0.45)
        or (hlines >= 22 and hreg >= 0.65)
        or (small_label_noise and table_grid_score >= 0.30)
    )

    # Strong diagram evidence is intentionally stricter than "visually complex".
    # It requires irregular visual regions with low table/text dominance, or
    # OCR/route evidence that the page is figure-like.
    strong_diagram_signal = (
        (
            len(irregular_large_components) >= 2
            and table_grid_score < 0.42
            and dense_text_score < 0.52
            and not has_grid_columns
            and ink_density > 0.004
        )
        or (diagram_score >= 0.62 and table_grid_score < 0.50 and dense_text_score < 0.58)
        or (figure_text_score >= 0.25 and len(irregular_large_components) >= 1)
    )

    weak_diagram_signal = (
        (
            len(irregular_large_components) >= 1
            and table_grid_score < 0.55
            and dense_text_score < 0.65
            and ink_density > 0.004
        )
        or diagram_score >= 0.50
        or figure_text_score >= 0.25
    )

    # Mixed visual+table needs table structure AND strong evidence that the visual
    # part is real. Otherwise it stays review/table.
    mixed_visual_table = (
        table_dominant
        and not strong_table_dominant
        and (
            figure_text_score >= 0.25
            or (
                old_image_candidate
                and len(irregular_large_components) >= 1
                and table_grid_score < 0.66
                and dense_text_score < 0.70
            )
        )
    )

    if blank_score >= 0.92:
        route = "blank_candidate"
        visual_subtype = "blank"
        confidence = blank_score
        reasons.append("very_low_ink_density")
    elif front_matter_score >= 0.45 and diagram_score < 0.55:
        route = "front_matter_or_index"
        visual_subtype = "front_matter_or_index"
        confidence = max(front_matter_score, text_score)
        reasons.append("front_matter_ocr_terms")
    elif strong_table_dominant and not mixed_visual_table:
        route = "table"
        visual_subtype = "table_dominant"
        confidence = max(table_score, table_grid_score, 0.66)
        reasons.append("strong_table_grid_or_label_noise_exclusion")
    elif mixed_visual_table:
        route = "mixed_visual_table"
        visual_subtype = "mixed_visual_table"
        confidence = max(diagram_score, table_score, table_grid_score, 0.58)
        reasons.append("confirmed_mixed_visual_and_table_layout")
    elif table_dominant and not strong_diagram_signal:
        route = "table"
        visual_subtype = "table_dominant"
        confidence = max(table_score, table_grid_score, 0.58)
        reasons.append("table_dominant_without_confirmed_diagram_signal")
    elif old_image_candidate and strong_diagram_signal:
        route = "image_visual"
        visual_subtype = "confirmed_diagram_dominant"
        confidence = max(diagram_score, 0.66)
        reasons.append("old_image_route_with_strong_diagram_signal")
    elif not old_image_candidate and strong_diagram_signal and figure_text_score >= 0.25:
        route = "image_visual"
        visual_subtype = "confirmed_new_diagram_dominant"
        confidence = max(diagram_score, 0.66)
        reasons.append("new_route_confirmed_by_figure_text_and_diagram_signal")
    elif not old_image_candidate and weak_diagram_signal:
        route = "visual_candidate_review"
        visual_subtype = "visual_candidate_review"
        confidence = max(diagram_score, 0.50)
        reasons.append("new_visual_candidate_requires_review_not_auto_image_route")
    elif old_image_candidate and weak_diagram_signal and not strong_table_dominant:
        route = "visual_candidate_review"
        visual_subtype = "borderline_old_image_visual"
        confidence = max(diagram_score, 0.50)
        reasons.append("old_image_route_but_detector_is_borderline")
    elif text_score >= 0.54 and diagram_score < 0.55 and not table_dominant:
        route = "normal_text"
        visual_subtype = "text_dominant"
        confidence = text_score
        reasons.append("dense_text_layout_without_strong_diagram_signal")
    else:
        route = "review_candidate"
        visual_subtype = "uncertain"
        confidence = max(diagram_score, table_score, text_score, 0.40)
        reasons.append("ambiguous_route_scores")

    meaningful_visual = route in {"image_visual", "mixed_visual_table"}

    if old_image_candidate and not meaningful_visual:
        reasons.append("old_image_visual_candidate_not_confirmed_by_meaningful_visual_gate")
    if not old_image_candidate and route == "visual_candidate_review":
        reasons.append("possible_missed_visual_candidate_review_only")
    if not old_image_candidate and meaningful_visual:
        reasons.append("possible_missed_visual_candidate_confirmed")
    if table_dominant:
        reasons.append("table_dominant_signal")
    if strong_table_dominant:
        reasons.append("strong_table_dominant_signal")
    if small_label_noise:
        reasons.append("small_label_noise_likely_table_or_dense_list")
    if has_grid_columns:
        reasons.append("grid_column_signal")
    if dense_page:
        reasons.append("dense_page_signal")
    if table_grid_score >= 0.65:
        reasons.append("high_table_grid_score")
    if len(irregular_large_components) >= 1:
        reasons.append("irregular_large_component_present")
    if len(small_label_like) >= 25:
        reasons.append("many_small_label_like_components")

    record = {
        "module": MODULE_NAME,
        "page_id": page_id,
        "page_number": page_number,
        "source_image": ref.display_path,
        "old_route": old_route,
        "old_image_visual_candidate": old_image_candidate,
        "new_route": route,
        "meaningful_image_visual": meaningful_visual,
        "visual_subtype": visual_subtype,
        "route_confidence": round(float(confidence), 4),
        "route_reasons": reasons,
        "scores": {
            "diagram_score": round(float(diagram_score), 4),
            "table_score": round(float(table_score), 4),
            "text_score": round(float(text_score), 4),
            "blank_score": round(float(blank_score), 4),
            "table_grid_score": round(float(table_grid_score), 4),
            "dense_text_score": round(float(dense_text_score), 4),
            "front_matter_score": round(float(front_matter_score), 4),
            "figure_text_score": round(float(figure_text_score), 4),
        },
        "features": {
            "original_size": original_size,
            "analyzed_size": [w, h],
            "threshold": threshold,
            "ink_density": round(float(ink_density), 6),
            "horizontal_line_count": hlines,
            "vertical_line_count": vlines,
            "horizontal_line_regularity": round(float(hreg), 4),
            "vertical_line_regularity": round(float(vreg), 4),
            "text_line_band_count": text_bands,
            "heavy_column_band_count": heavy_cols,
            "connected_component_count": len(comps),
            "large_component_count": len(large_components),
            "irregular_large_component_count": len(irregular_large_components),
            "small_label_like_component_count": len(small_label_like),
        },
        "safety_contract": {
            "final_answer_allowed": False,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "ollama_call_attempt": False,
            "llm_call_attempt": False,
        },
    }
    return record


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def create_contact_sheet(
    refs_by_page: Dict[str, ImageRef],
    records: Sequence[Dict[str, Any]],
    out_path: Path,
    title: str,
    limit: int = 80,
    thumb_w: int = 220,
    thumb_h: int = 300,
) -> None:
    chosen = [r for r in records if r.get("page_id") in refs_by_page][:limit]
    if not chosen:
        # Still write a tiny placeholder so automation has deterministic outputs.
        img = Image.new("RGB", (700, 120), "white")
        d = ImageDraw.Draw(img)
        d.text((12, 12), title, fill="black")
        d.text((12, 44), "No records in this category.", fill="black")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path)
        return

    cols = 4
    rows = math.ceil(len(chosen) / cols)
    pad = 18
    label_h = 74
    header_h = 44
    sheet_w = cols * (thumb_w + pad) + pad
    sheet_h = header_h + rows * (thumb_h + label_h + pad) + pad
    sheet = Image.new("RGB", (sheet_w, sheet_h), "white")
    draw = ImageDraw.Draw(sheet)
    draw.text((pad, 12), title, fill="black")

    for idx, rec in enumerate(chosen):
        row = idx // cols
        col = idx % cols
        x = pad + col * (thumb_w + pad)
        y = header_h + row * (thumb_h + label_h + pad)

        ref = refs_by_page[str(rec["page_id"])]
        try:
            with open_image_ref(ref) as src:
                thumb = src.convert("RGB")
                thumb.thumbnail((thumb_w, thumb_h))
        except Exception:
            thumb = Image.new("RGB", (thumb_w, thumb_h), "white")
            ImageDraw.Draw(thumb).text((10, 10), "open failed", fill="black")

        canvas = Image.new("RGB", (thumb_w, thumb_h), "white")
        canvas.paste(thumb, ((thumb_w - thumb.width) // 2, (thumb_h - thumb.height) // 2))
        sheet.paste(canvas, (x, y))

        label = (
            f"{rec.get('page_id')}\n"
            f"new={rec.get('new_route')} subtype={rec.get('visual_subtype')}\n"
            f"old_img={rec.get('old_image_visual_candidate')} conf={rec.get('route_confidence')}\n"
            f"d={rec.get('scores', {}).get('diagram_score')} "
            f"tbl={rec.get('scores', {}).get('table_grid_score')} "
            f"t={rec.get('scores', {}).get('table_score')}"
        )
        draw.multiline_text((x, y + thumb_h + 4), label[:220], fill="black", spacing=2)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)


def auto_tiff_roots(repo_root: Path) -> List[Path]:
    candidates = [
        repo_root / "local_data/organization/trace_net/source_tiffs",
        repo_root / "local_data/organization/trace_net/tiffs",
        repo_root / "local_data/organization/trace_net/tiff",
        repo_root / "local_data/organization/trace_net/tiff_pages",
        repo_root / "local_data/organization/trace_net/images",
        repo_root / "local_data/source_tiffs",
        repo_root / "local_data/tiffs",
        repo_root / "data/tiffs",
    ]
    return [p for p in candidates if p.exists()]


def build(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    repo_root = Path(args.repo_root).resolve()
    roots = [Path(p) for p in args.tiff_root]
    if args.auto_discover_tiffs:
        roots.extend(auto_tiff_roots(repo_root))
    zip_paths = [Path(p) for p in args.tiff_zip]

    route_manifest = Path(args.route_manifest) if args.route_manifest else None
    routes = load_route_manifest(route_manifest, args.page_id_prefix)

    refs = discover_image_refs(roots, zip_paths)
    if args.max_pages:
        refs = refs[: args.max_pages]

    refs_by_page: Dict[str, ImageRef] = {}
    for ref in refs:
        page_id = extract_page_id(ref.display_path, args.page_id_prefix)
        if page_id:
            refs_by_page[page_id] = ref

    records: List[Dict[str, Any]] = []
    for idx, ref in enumerate(refs, start=1):
        page_id = extract_page_id(ref.display_path, args.page_id_prefix)
        route_rec = routes.get(page_id or "", {})
        ocr_text = collect_ocr_text_for_page([Path(p) for p in args.ocr_root], page_id or "") if page_id else ""
        try:
            record = analyze_image(
                ref,
                page_id_prefix=args.page_id_prefix,
                old_route_record=route_rec,
                ocr_text=ocr_text,
                max_analyze_dim=args.max_analyze_dim,
            )
            record["sequence_index"] = idx
        except Exception as exc:
            record = {
                "module": MODULE_NAME,
                "page_id": page_id,
                "source_image": ref.display_path,
                "status": "image_analysis_error",
                "error": repr(exc),
                "old_route": route_rec.get("old_route", ""),
                "old_image_visual_candidate": bool(route_rec.get("old_image_visual_candidate", False)),
                "new_route": "review_candidate",
                "meaningful_image_visual": False,
                "visual_subtype": "analysis_error",
                "route_confidence": 0.0,
                "route_reasons": ["image_analysis_error"],
                "scores": {},
                "features": {},
                "safety_contract": {
                    "final_answer_allowed": False,
                    "answer_permission": False,
                    "can_answer_directly": False,
                    "can_prove_claims": False,
                    "source_truth_mutation_allowed": False,
                    "postgres_write_attempt": False,
                    "qdrant_write_attempt": False,
                    "opensearch_write_attempt": False,
                    "ollama_call_attempt": False,
                    "llm_call_attempt": False,
                },
            }
        records.append(record)

    jsonl_path = output_dir / "trace_net_meaningful_image_route_detector_v1_2.jsonl"
    jsonl_path.write_text(
        "\n".join(json.dumps(r, sort_keys=True, ensure_ascii=False) for r in records) + ("\n" if records else ""),
        encoding="utf-8",
    )

    route_counts = Counter(str(r.get("new_route")) for r in records)
    subtype_counts = Counter(str(r.get("visual_subtype")) for r in records)
    old_image_records = [r for r in records if r.get("old_image_visual_candidate")]

    diagram_dominant_records = [r for r in records if r.get("new_route") == "image_visual"]
    mixed_visual_table_records = [r for r in records if r.get("new_route") == "mixed_visual_table"]
    meaningful_visual_records = diagram_dominant_records + mixed_visual_table_records
    visual_candidate_review_records = [r for r in records if r.get("new_route") == "visual_candidate_review"]

    rejected_old_image = [r for r in old_image_records if not r.get("meaningful_image_visual")]
    old_image_rejected_as_table = [r for r in old_image_records if r.get("new_route") == "table"]
    old_image_rejected_as_text = [r for r in old_image_records if r.get("new_route") in {"normal_text", "front_matter_or_index"}]
    old_image_rejected_as_review = [r for r in old_image_records if r.get("new_route") == "review_candidate"]

    accepted_old_image_diagram = [r for r in diagram_dominant_records if r.get("old_image_visual_candidate")]
    accepted_old_image_mixed = [r for r in mixed_visual_table_records if r.get("old_image_visual_candidate")]
    possible_missed = [r for r in meaningful_visual_records if not r.get("old_image_visual_candidate")]
    uncertain = [r for r in records if r.get("new_route") == "review_candidate"]

    # Clearer disagreement buckets:
    # - old image route rejected by the new gate
    # - new meaningful visual discovered outside old image route
    disagreements = [
        r
        for r in records
        if bool(r.get("old_image_visual_candidate")) != bool(r.get("meaningful_image_visual"))
    ]

    safety_counts = {
        "final_answer_allowed_true_count": 0,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "ollama_call_attempt_count": 0,
        "llm_call_attempt_count": 0,
    }

    failures: List[str] = []
    if len(records) < args.min_processed_pages:
        failures.append(f"processed_page_count:{len(records)} < {args.min_processed_pages}")
    if len(records) < args.min_output_records:
        failures.append(f"output_record_count:{len(records)} < {args.min_output_records}")

    summary = {
        "module": MODULE_NAME,
        "status": "TRACE_NET_MEANINGFUL_IMAGE_ROUTE_DETECTOR_V1_2_BUILT",
        "quality_status": "PASS" if not failures else "FAIL",
        "quality_failures": failures,
        "inputs": {
            "repo_root": str(repo_root),
            "tiff_roots": [str(p) for p in roots],
            "tiff_zips": [str(p) for p in zip_paths],
            "route_manifest": str(route_manifest) if route_manifest else "",
            "ocr_roots": [str(p) for p in args.ocr_root],
        },
        "outputs": {
            "jsonl": str(jsonl_path),
            "summary": str(output_dir / "summary.json"),
            "accepted_diagram_dominant_contact_sheet": str(output_dir / "accepted_diagram_dominant_contact_sheet.png"),
            "accepted_mixed_visual_table_contact_sheet": str(output_dir / "accepted_mixed_visual_table_contact_sheet.png"),
            "old_image_rejected_as_table_contact_sheet": str(output_dir / "old_image_rejected_as_table_contact_sheet.png"),
            "old_image_rejected_as_review_contact_sheet": str(output_dir / "old_image_rejected_as_review_contact_sheet.png"),
            "new_visual_not_old_route_contact_sheet": str(output_dir / "new_visual_not_old_route_contact_sheet.png"),
            "visual_candidate_review_contact_sheet": str(output_dir / "visual_candidate_review_contact_sheet.png"),
            "uncertain_review_contact_sheet": str(output_dir / "uncertain_review_contact_sheet.png"),
            "route_disagreement_contact_sheet": str(output_dir / "route_disagreement_contact_sheet.png"),
        },
        "summary": {
            "processed_page_count": len(records),
            "route_manifest_page_count": len(routes),
            "old_image_visual_candidate_count": len(old_image_records),
            "new_meaningful_visual_route_count": len(meaningful_visual_records),
            "new_diagram_dominant_count": len(diagram_dominant_records),
            "new_mixed_visual_table_count": len(mixed_visual_table_records),
            "visual_candidate_review_count": len(visual_candidate_review_records),
            "old_image_visual_kept_diagram_count": len(accepted_old_image_diagram),
            "old_image_visual_kept_mixed_count": len(accepted_old_image_mixed),
            "old_image_visual_rejected_count": len(rejected_old_image),
            "old_image_rejected_as_table_count": len(old_image_rejected_as_table),
            "old_image_rejected_as_text_or_front_matter_count": len(old_image_rejected_as_text),
            "old_image_rejected_as_review_count": len(old_image_rejected_as_review),
            "uncertain_review_count": len(uncertain),
            "possible_missed_visual_candidate_count": len(possible_missed),
            "possible_missed_visual_review_only_count": sum(1 for r in visual_candidate_review_records if not r.get("old_image_visual_candidate")),
            "route_disagreement_count": len(disagreements),
            "new_route_counts": dict(sorted(route_counts.items())),
            "visual_subtype_counts": dict(sorted(subtype_counts.items())),
            **safety_counts,
        },
        "safety_contract": {
            "read_only_detector": True,
            "does_not_call_ollama": True,
            "does_not_call_llm": True,
            "does_not_write_postgres": True,
            "does_not_write_qdrant": True,
            "does_not_write_opensearch": True,
            "does_not_mutate_source_truth": True,
            "final_answer_allowed": False,
            "answer_permission": False,
        },
    }

    write_json(output_dir / "summary.json", summary)

    page_ref_map = {
        str(r.get("page_id")): refs_by_page[str(r.get("page_id"))]
        for r in records
        if str(r.get("page_id")) in refs_by_page
    }

    create_contact_sheet(
        page_ref_map,
        diagram_dominant_records,
        output_dir / "accepted_diagram_dominant_contact_sheet.png",
        "TRACE-Net v1.2 accepted diagram-dominant image_visual pages",
        limit=args.contact_sheet_limit,
    )
    create_contact_sheet(
        page_ref_map,
        mixed_visual_table_records,
        output_dir / "accepted_mixed_visual_table_contact_sheet.png",
        "TRACE-Net v1.2 accepted mixed visual+table pages",
        limit=args.contact_sheet_limit,
    )
    create_contact_sheet(
        page_ref_map,
        old_image_rejected_as_table,
        output_dir / "old_image_rejected_as_table_contact_sheet.png",
        "TRACE-Net v1.2 old image_visual rejected as table-dominant",
        limit=args.contact_sheet_limit,
    )
    create_contact_sheet(
        page_ref_map,
        old_image_rejected_as_review,
        output_dir / "old_image_rejected_as_review_contact_sheet.png",
        "TRACE-Net v1.2 old image_visual rejected to review_candidate",
        limit=args.contact_sheet_limit,
    )
    create_contact_sheet(
        page_ref_map,
        possible_missed,
        output_dir / "new_visual_not_old_route_contact_sheet.png",
        "TRACE-Net v1.2 new meaningful visual not in old image route",
        limit=args.contact_sheet_limit,
    )
    create_contact_sheet(
        page_ref_map,
        visual_candidate_review_records,
        output_dir / "visual_candidate_review_contact_sheet.png",
        "TRACE-Net v1.2 visual candidates requiring review, not auto image route",
        limit=args.contact_sheet_limit,
    )
    create_contact_sheet(
        page_ref_map,
        uncertain,
        output_dir / "uncertain_review_contact_sheet.png",
        "TRACE-Net v1.2 uncertain review candidates",
        limit=args.contact_sheet_limit,
    )
    create_contact_sheet(
        page_ref_map,
        disagreements,
        output_dir / "route_disagreement_contact_sheet.png",
        "TRACE-Net v1.2 route disagreements: old image vs new meaningful visual",
        limit=args.contact_sheet_limit,
    )

    print(f"status={summary['status']}")
    print(f"quality_status={summary['quality_status']}")
    for key, value in summary["summary"].items():
        if key != "new_route_counts":
            print(f"{key}={value}")
    print("new_route_counts=" + json.dumps(summary["summary"]["new_route_counts"], sort_keys=True))
    print("output_dir=" + str(output_dir))

    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--tiff-root", action="append", default=[], help="Directory or image file containing TIFF/page images. Can repeat.")
    ap.add_argument("--tiff-zip", action="append", default=[], help="ZIP containing TIFF/page images. Can repeat.")
    ap.add_argument("--auto-discover-tiffs", action="store_true", help="Search known local_data TIFF directories.")
    ap.add_argument("--route-manifest", default="", help="Existing route manifest JSON/JSONL to compare against.")
    ap.add_argument("--ocr-root", action="append", default=[], help="Optional OCR JSON/TXT root for page-role keyword signals.")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--page-id-prefix", default=DEFAULT_PAGE_ID_PREFIX)
    ap.add_argument("--max-pages", type=int, default=0)
    ap.add_argument("--max-analyze-dim", type=int, default=900)
    ap.add_argument("--contact-sheet-limit", type=int, default=80)
    ap.add_argument("--min-processed-pages", type=int, default=1)
    ap.add_argument("--min-output-records", type=int, default=1)
    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = build_arg_parser()
    args = ap.parse_args(argv)

    if not args.tiff_root and not args.tiff_zip and not args.auto_discover_tiffs:
        raise SystemExit(
            "No TIFF/page images supplied. Use --tiff-root, --tiff-zip, or --auto-discover-tiffs."
        )

    summary = build(args)
    return 0 if summary.get("quality_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
