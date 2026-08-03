"""Lightweight page image-recognition audit for TIFF manual pages.

This module intentionally uses simple, local image features rather than a heavy
vision model. It answers first-pass questions such as:

* Is the TIFF readable?
* Does the page appear blank?
* Does the page have table/grid-like line structure?
* Does the page have visual/figure-like dark regions?
* Can the image analysis be linked back to page_id/source paths?

The output is graph-ready but does not mutate the main graph by default.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
import json
import math
import re

from PIL import Image

try:  # numpy is available in the project environment, but keep a fallback path.
    import numpy as _np
except Exception:  # pragma: no cover
    _np = None  # type: ignore[assignment]

DEFAULT_EXPORT_DIR = Path("local_data/organization/export")
DEFAULT_CONTEXT_FILE = Path("local_data/organization/context/page_contexts.json")
DEFAULT_OUTPUT = Path("local_data/organization/image_recognition/page_image_recognition_audit.json")
DEFAULT_OVERLAY_NODES = Path("local_data/organization/image_recognition/image_recognition_graph_nodes.json")
DEFAULT_OVERLAY_EDGES = Path("local_data/organization/image_recognition/image_recognition_graph_edges.json")

IMAGE_KEYS = (
    "source_image_path",
    "tiff_path",
    "tiff_file",
    "image_path",
    "local_tiff_path",
    "source_file_path",
)

OCR_KEYS = ("ocr_text_path", "ocr_path", "ocr_file", "local_ocr_path")
SOURCE_KEYS = ("source_url", "rescarta_url", "source")


@dataclass
class PageImageSource:
    page_id: str
    page_label: str = ""
    ata_code: str = ""
    document_title: str = ""
    image_path: str = ""
    ocr_path: str = ""
    source_url: str = ""
    role: str = ""
    context_summary: str = ""


@dataclass
class ImageFeatureRecord:
    page_id: str
    page_label: str = ""
    ata_code: str = ""
    document_title: str = ""
    image_path: str = ""
    source_url: str = ""
    role: str = ""
    context_summary: str = ""
    status: str = "ok"
    classification: str = "unknown"
    reason: str = ""
    width: int = 0
    height: int = 0
    sample_width: int = 0
    sample_height: int = 0
    ink_ratio: float = 0.0
    dark_pixel_count: int = 0
    horizontal_line_rows: int = 0
    vertical_line_cols: int = 0
    large_component_count: int = 0
    largest_component_pixels: int = 0
    table_grid_score: float = 0.0
    visual_score: float = 0.0
    likely_blank: bool = False
    likely_table_grid: bool = False
    likely_figure_or_diagram: bool = False
    likely_image_heavy: bool = False
    likely_text_heavy: bool = False
    warning: Optional[str] = None
    error: Optional[str] = None

    def to_json(self) -> Dict[str, Any]:
        data = asdict(self)
        # Keep JSON compact and deterministic.
        data["ink_ratio"] = round(float(data["ink_ratio"]), 6)
        data["table_grid_score"] = round(float(data["table_grid_score"]), 3)
        data["visual_score"] = round(float(data["visual_score"]), 3)
        return data


@dataclass
class PageImageRecognitionSummary:
    status: str
    export_dir: str
    context_file: str
    pages_checked: int = 0
    images_readable: int = 0
    missing_image_paths: int = 0
    missing_image_files: int = 0
    unreadable_images: int = 0
    blank_pages: int = 0
    likely_visual_pages: int = 0
    likely_table_grid_pages: int = 0
    likely_figure_or_diagram_pages: int = 0
    likely_image_heavy_pages: int = 0
    likely_text_heavy_pages: int = 0
    role_counts: Dict[str, int] = field(default_factory=dict)
    classification_counts: Dict[str, int] = field(default_factory=dict)
    average_ink_ratio: float = 0.0
    median_ink_ratio: float = 0.0
    total_large_components: int = 0
    sample_records: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    overlay_nodes_path: Optional[str] = None
    overlay_edges_path: Optional[str] = None

    def to_json(self) -> Dict[str, Any]:
        data = asdict(self)
        data["average_ink_ratio"] = round(float(data["average_ink_ratio"]), 6)
        data["median_ink_ratio"] = round(float(data["median_ink_ratio"]), 6)
        return data


def _first_nonempty(data: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = data.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return ""


def _normalize_path(path_text: str, repo_root: Path) -> Path:
    text = (path_text or "").strip()
    if text.startswith("file://"):
        text = text[7:]
        if re.match(r"^/[A-Za-z]:/", text):
            text = text[1:]
    p = Path(text)
    if not p.is_absolute():
        p = repo_root / p
    return p


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_page_dicts(page_index_data: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(page_index_data, list):
        for row in page_index_data:
            if isinstance(row, Mapping):
                yield row
        return
    if isinstance(page_index_data, Mapping):
        pages = page_index_data.get("pages")
        if isinstance(pages, list):
            for row in pages:
                if isinstance(row, Mapping):
                    yield row
        elif isinstance(pages, Mapping):
            for key, row in pages.items():
                if isinstance(row, Mapping):
                    merged = {"page_id": key, **row}
                    yield merged
        else:
            # Some exports are direct page_id -> page mapping.
            for key, row in page_index_data.items():
                if isinstance(row, Mapping) and ("page_id" in row or "source_image_path" in row):
                    merged = {"page_id": row.get("page_id", key), **row}
                    yield merged


def _load_contexts(context_file: Path) -> Dict[str, Mapping[str, Any]]:
    if not context_file.exists():
        return {}
    data = _load_json(context_file)
    contexts: Dict[str, Mapping[str, Any]] = {}
    rows: Iterable[Any]
    if isinstance(data, Mapping):
        if isinstance(data.get("contexts"), list):
            rows = data["contexts"]
        elif isinstance(data.get("page_contexts"), list):
            rows = data["page_contexts"]
        elif isinstance(data.get("contexts"), Mapping):
            rows = data["contexts"].values()
        else:
            rows = data.values()
    elif isinstance(data, list):
        rows = data
    else:
        rows = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        page_id = str(row.get("page_id") or row.get("id") or "").strip()
        if page_id:
            contexts[page_id] = row
    return contexts


def load_page_image_sources(
    export_dir: Path = DEFAULT_EXPORT_DIR,
    context_file: Path = DEFAULT_CONTEXT_FILE,
    repo_root: Optional[Path] = None,
) -> List[PageImageSource]:
    repo_root = repo_root or Path.cwd()
    page_index_path = export_dir / "page_index.json"
    if not page_index_path.exists():
        raise FileNotFoundError(f"page_index.json not found: {page_index_path}")
    contexts = _load_contexts(context_file)
    rows = list(_iter_page_dicts(_load_json(page_index_path)))
    sources: List[PageImageSource] = []
    for idx, row in enumerate(rows, start=1):
        page_id = str(row.get("page_id") or row.get("id") or f"page_{idx:06d}")
        ctx = contexts.get(page_id, {})
        role = str(
            ctx.get("role")
            or ctx.get("page_role")
            or ctx.get("classification")
            or ctx.get("primary_role")
            or row.get("role")
            or row.get("page_role")
            or row.get("classification")
            or ""
        )
        summary = str(
            ctx.get("summary")
            or ctx.get("short_summary")
            or ctx.get("context")
            or row.get("context_summary")
            or ""
        )
        sources.append(
            PageImageSource(
                page_id=page_id,
                page_label=str(row.get("page_label") or row.get("label") or row.get("page_number") or ""),
                ata_code=str(row.get("ata_code") or row.get("ata") or ""),
                document_title=str(row.get("manual_title") or row.get("document_title") or row.get("manual") or ""),
                image_path=_first_nonempty(row, IMAGE_KEYS),
                ocr_path=_first_nonempty(row, OCR_KEYS),
                source_url=_first_nonempty(row, SOURCE_KEYS),
                role=role,
                context_summary=summary,
            )
        )
    return sources


def _resize_for_analysis(image: Image.Image, max_side: int = 768) -> Image.Image:
    img = image.convert("L")
    w, h = img.size
    if max(w, h) <= max_side:
        return img
    scale = max_side / float(max(w, h))
    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    # LANCZOS is high-quality and stable for binary-ish scans.
    return img.resize(new_size, Image.Resampling.LANCZOS)


def _connected_components(mask: "_np.ndarray") -> Tuple[int, int]:
    """Return count and largest size for dark components on a downsampled mask."""
    if _np is None:  # pragma: no cover
        return 0, 0
    h, w = mask.shape
    visited = _np.zeros(mask.shape, dtype=bool)
    count = 0
    largest = 0
    # Work on components that are not too tiny to avoid counting text speckles.
    for y in range(h):
        xs = _np.where(mask[y] & ~visited[y])[0]
        for x0 in xs.tolist():
            if visited[y, x0] or not mask[y, x0]:
                continue
            stack = [(y, x0)]
            visited[y, x0] = True
            size = 0
            while stack:
                cy, cx = stack.pop()
                size += 1
                for ny in (cy - 1, cy, cy + 1):
                    if ny < 0 or ny >= h:
                        continue
                    for nx in (cx - 1, cx, cx + 1):
                        if nx < 0 or nx >= w or visited[ny, nx] or not mask[ny, nx]:
                            continue
                        visited[ny, nx] = True
                        stack.append((ny, nx))
            if size >= 80:
                count += 1
                largest = max(largest, size)
    return count, largest


def analyze_page_image(
    source: PageImageSource,
    repo_root: Optional[Path] = None,
    max_side: int = 768,
) -> ImageFeatureRecord:
    repo_root = repo_root or Path.cwd()
    rec = ImageFeatureRecord(
        page_id=source.page_id,
        page_label=source.page_label,
        ata_code=source.ata_code,
        document_title=source.document_title,
        image_path=source.image_path,
        source_url=source.source_url,
        role=source.role,
        context_summary=source.context_summary,
    )
    if not source.image_path:
        rec.status = "missing_image_path"
        rec.classification = "missing_image_path"
        rec.warning = "No local TIFF/image path available for page"
        rec.reason = rec.warning
        return rec
    image_path = _normalize_path(source.image_path, repo_root)
    if not image_path.exists():
        rec.status = "missing_image_file"
        rec.classification = "missing_image_file"
        rec.warning = f"Image file does not exist: {source.image_path}"
        rec.reason = rec.warning
        return rec
    try:
        with Image.open(image_path) as original:
            rec.width, rec.height = original.size
            sample = _resize_for_analysis(original, max_side=max_side)
            rec.sample_width, rec.sample_height = sample.size
            if _np is not None:
                arr = _np.asarray(sample, dtype=_np.uint8)
                # Treat scan ink and gray graphics as dark. 220 captures pale OCR/scan lines.
                dark = arr < 220
                total = int(dark.size)
                dark_pixels = int(dark.sum())
                rec.dark_pixel_count = dark_pixels
                rec.ink_ratio = float(dark_pixels / total) if total else 0.0
                row_density = dark.mean(axis=1) if total else _np.array([])
                col_density = dark.mean(axis=0) if total else _np.array([])
                rec.horizontal_line_rows = int((row_density > 0.42).sum())
                rec.vertical_line_cols = int((col_density > 0.32).sum())
                cc_mask = arr < 185
                rec.large_component_count, rec.largest_component_pixels = _connected_components(cc_mask)
            else:  # pragma: no cover
                pixels = list(sample.getdata())
                total = len(pixels)
                dark_pixels = sum(1 for px in pixels if px < 220)
                rec.dark_pixel_count = dark_pixels
                rec.ink_ratio = float(dark_pixels / total) if total else 0.0
    except Exception as exc:
        rec.status = "unreadable_image"
        rec.classification = "unreadable_image"
        rec.error = str(exc)
        rec.reason = f"Could not read/analyze image: {exc}"
        return rec

    role = (source.role or "").lower().strip()
    summary = (source.context_summary or "").lower()
    role_visual_hint = role in {"figure", "table"} or any(k in summary for k in ("figure", "illustration", "diagram", "drawing", "table"))
    rec.table_grid_score = float(rec.horizontal_line_rows * 0.7 + rec.vertical_line_cols * 0.9)
    rec.visual_score = float(
        (rec.ink_ratio * 20.0)
        + min(10, rec.large_component_count) * 0.8
        + min(10, rec.table_grid_score) * 0.4
        + (2.0 if role_visual_hint else 0.0)
    )
    rec.likely_blank = rec.ink_ratio < 0.004
    rec.likely_table_grid = rec.table_grid_score >= 8 or role == "table"
    rec.likely_image_heavy = rec.ink_ratio >= 0.20 or rec.largest_component_pixels >= 18000
    rec.likely_figure_or_diagram = bool(
        role == "figure"
        or (rec.large_component_count >= 2 and rec.ink_ratio >= 0.025)
        or ("figure" in summary or "illustration" in summary or "diagram" in summary)
    )
    rec.likely_text_heavy = bool(
        not rec.likely_blank
        and not rec.likely_image_heavy
        and rec.ink_ratio >= 0.015
        and rec.horizontal_line_rows < 12
        and rec.vertical_line_cols < 12
    )

    if rec.likely_blank:
        rec.classification = "likely_blank"
        rec.reason = "Very low ink ratio; image appears blank or nearly blank"
    elif rec.likely_table_grid:
        rec.classification = "likely_table_or_grid"
        rec.reason = "Image/context contains table or grid-like line structure"
    elif rec.likely_image_heavy:
        rec.classification = "likely_image_heavy"
        rec.reason = "High ink density or large dark visual regions detected"
    elif rec.likely_figure_or_diagram:
        rec.classification = "likely_figure_or_diagram"
        rec.reason = "Figure/diagram indicators detected from image features or page context"
    elif rec.likely_text_heavy:
        rec.classification = "likely_text_or_parts_list"
        rec.reason = "Readable image with text-like density and no strong table/figure signal"
    else:
        rec.classification = "unknown_visual_profile"
        rec.reason = "Image is readable but visual profile is ambiguous"
    return rec


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    mid = len(vals) // 2
    if len(vals) % 2:
        return float(vals[mid])
    return float((vals[mid - 1] + vals[mid]) / 2.0)


def run_page_image_recognition_audit(
    export_dir: Path = DEFAULT_EXPORT_DIR,
    context_file: Path = DEFAULT_CONTEXT_FILE,
    repo_root: Optional[Path] = None,
    limit: Optional[int] = None,
    sample_limit: int = 20,
    write_graph_overlay: bool = False,
    output_path: Path = DEFAULT_OUTPUT,
) -> Tuple[PageImageRecognitionSummary, List[ImageFeatureRecord]]:
    repo_root = repo_root or Path.cwd()
    sources = load_page_image_sources(export_dir=export_dir, context_file=context_file, repo_root=repo_root)
    if limit is not None:
        sources = sources[: max(0, int(limit))]
    records = [analyze_page_image(src, repo_root=repo_root) for src in sources]
    readable = [r for r in records if r.status == "ok"]
    ink_values = [r.ink_ratio for r in readable]
    role_counts: Dict[str, int] = {}
    class_counts: Dict[str, int] = {}
    for rec in records:
        role_counts[rec.role or "unknown"] = role_counts.get(rec.role or "unknown", 0) + 1
        class_counts[rec.classification] = class_counts.get(rec.classification, 0) + 1
    summary = PageImageRecognitionSummary(
        status="OK",
        export_dir=str(export_dir),
        context_file=str(context_file),
        pages_checked=len(records),
        images_readable=len(readable),
        missing_image_paths=sum(1 for r in records if r.status == "missing_image_path"),
        missing_image_files=sum(1 for r in records if r.status == "missing_image_file"),
        unreadable_images=sum(1 for r in records if r.status == "unreadable_image"),
        blank_pages=sum(1 for r in records if r.likely_blank),
        likely_visual_pages=sum(1 for r in records if r.likely_figure_or_diagram or r.likely_image_heavy or r.likely_table_grid),
        likely_table_grid_pages=sum(1 for r in records if r.likely_table_grid),
        likely_figure_or_diagram_pages=sum(1 for r in records if r.likely_figure_or_diagram),
        likely_image_heavy_pages=sum(1 for r in records if r.likely_image_heavy),
        likely_text_heavy_pages=sum(1 for r in records if r.likely_text_heavy),
        role_counts=dict(sorted(role_counts.items())),
        classification_counts=dict(sorted(class_counts.items())),
        average_ink_ratio=(sum(ink_values) / len(ink_values)) if ink_values else 0.0,
        median_ink_ratio=_median(ink_values),
        total_large_components=sum(r.large_component_count for r in records),
    )
    if summary.missing_image_paths or summary.missing_image_files or summary.unreadable_images:
        summary.status = "NEEDS ATTENTION"
        summary.warnings.append("Some pages do not have readable local TIFF/image files.")
    if summary.blank_pages:
        summary.warnings.append("Some pages appear blank or nearly blank by image analysis.")
    sample_records = sorted(
        records,
        key=lambda r: (r.status != "ok", -r.visual_score, -r.table_grid_score, r.page_id),
    )[: max(0, sample_limit)]
    summary.sample_records = [r.to_json() for r in sample_records]
    if write_graph_overlay:
        nodes, edges = build_image_recognition_graph_overlay(records)
        DEFAULT_OVERLAY_NODES.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_OVERLAY_NODES.write_text(json.dumps(nodes, indent=2), encoding="utf-8")
        DEFAULT_OVERLAY_EDGES.write_text(json.dumps(edges, indent=2), encoding="utf-8")
        summary.overlay_nodes_path = str(DEFAULT_OVERLAY_NODES)
        summary.overlay_edges_path = str(DEFAULT_OVERLAY_EDGES)
    return summary, records


def build_image_recognition_graph_overlay(records: Sequence[ImageFeatureRecord]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    visual_type_seen = set()
    for rec in records:
        analysis_id = f"image_analysis:{rec.page_id}"
        nodes.append(
            {
                "id": analysis_id,
                "type": "page_image_analysis",
                "label": f"Image analysis for {rec.page_id}",
                "page_id": rec.page_id,
                "classification": rec.classification,
                "status": rec.status,
                "visual_score": round(rec.visual_score, 3),
                "ink_ratio": round(rec.ink_ratio, 6),
                "horizontal_line_rows": rec.horizontal_line_rows,
                "vertical_line_cols": rec.vertical_line_cols,
                "large_component_count": rec.large_component_count,
                "likely_table_grid": rec.likely_table_grid,
                "likely_figure_or_diagram": rec.likely_figure_or_diagram,
                "likely_image_heavy": rec.likely_image_heavy,
                "likely_blank": rec.likely_blank,
            }
        )
        edges.append({"type": "HAS_IMAGE_ANALYSIS", "source": f"page:{rec.page_id}", "target": analysis_id})
        visual_type = f"visual_type:{rec.classification}"
        if visual_type not in visual_type_seen:
            visual_type_seen.add(visual_type)
            nodes.append({"id": visual_type, "type": "visual_type", "label": rec.classification})
        edges.append({"type": "CLASSIFIED_AS_VISUAL", "source": analysis_id, "target": visual_type})
    return nodes, edges


def write_report(path: Path, summary: PageImageRecognitionSummary, records: Sequence[ImageFeatureRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"summary": summary.to_json(), "records": [r.to_json() for r in records]}
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def print_report(summary: PageImageRecognitionSummary) -> None:
    print("Page image-recognition audit")
    print(f"  Status: {summary.status}")
    print(f"  Export dir: {summary.export_dir}")
    print(f"  Context file: {summary.context_file}")
    print("\nCounts:")
    print(f"  Pages checked: {summary.pages_checked}")
    print(f"  Readable images: {summary.images_readable}")
    print(f"  Missing image paths: {summary.missing_image_paths}")
    print(f"  Missing image files: {summary.missing_image_files}")
    print(f"  Unreadable images: {summary.unreadable_images}")
    print(f"  Blank/nearly blank pages: {summary.blank_pages}")
    print("\nImage recognition signals:")
    print(f"  Likely visual pages: {summary.likely_visual_pages}")
    print(f"  Likely figure/diagram pages: {summary.likely_figure_or_diagram_pages}")
    print(f"  Likely table/grid pages: {summary.likely_table_grid_pages}")
    print(f"  Likely image-heavy pages: {summary.likely_image_heavy_pages}")
    print(f"  Likely text/parts-list pages: {summary.likely_text_heavy_pages}")
    print(f"  Avg ink ratio: {summary.average_ink_ratio:.4f}")
    print(f"  Median ink ratio: {summary.median_ink_ratio:.4f}")
    print(f"  Total large components: {summary.total_large_components}")
    print("\nClassification counts:")
    for key, value in sorted(summary.classification_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {key}: {value}")
    print("\nPage roles:")
    for key, value in sorted(summary.role_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {key}: {value}")
    if summary.sample_records:
        print("\nSample image-recognition rows:")
        for idx, row in enumerate(summary.sample_records, start=1):
            print(
                f"  {idx}. {row['page_id']} | class={row['classification']} | role={row.get('role') or '-'} | "
                f"score={row['visual_score']:.2f} ink={row['ink_ratio']:.4f} lines={row['horizontal_line_rows']}/{row['vertical_line_cols']}"
            )
            if row.get("context_summary"):
                print(f"     context: {str(row['context_summary'])[:160]}")
            if row.get("source_url"):
                print(f"     source: {row['source_url']}")
            if row.get("reason"):
                print(f"     reason: {row['reason']}")
    if summary.overlay_nodes_path:
        print("\nGraph overlay files:")
        print(f"  nodes: {summary.overlay_nodes_path}")
        print(f"  edges: {summary.overlay_edges_path}")
    if summary.warnings:
        print("\nWarnings:")
        for warning in summary.warnings:
            print(f"  - {warning}")
