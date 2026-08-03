"""TRACE-Net all-page table candidate scanner.

This scanner is the bridge from the full page graph to Part C table
extraction. It scans all known pages, uses cheap graph/page traits and a
lightweight image-layout probe, and writes a TRACE-Net-compatible candidate
plan. The table tile executor can consume this plan directly by pointing
``--trace-net-dir`` at the scanner output directory.

It does not call OCR, Ollama, or any table model. It only decides which pages
are plausible table candidates and gives them high/medium/review/skip routes.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import webbrowser
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:
    from PIL import Image, ImageOps
except Exception:  # pragma: no cover - missing dependency env only
    Image = None  # type: ignore[assignment]
    ImageOps = None  # type: ignore[assignment]

DEFAULT_ENTITY_TRAIT_DIR = Path("local_data/organization/entity_traits")
DEFAULT_EXPORT_DIR = Path("local_data/organization/export")
DEFAULT_IMAGE_RECOGNITION_DIR = Path("local_data/organization/image_recognition")
DEFAULT_OUTPUT_DIR = Path("local_data/organization/table_extraction/all_page_scan")

PAGE_CHARACTER_CARDS_FILE = "page_character_cards.json"
PAGE_INDEX_FILE = "page_index.json"
IMAGE_AUDIT_FILE = "page_image_recognition_audit.json"

TABLE_CANDIDATE_PLAN_FILE = "table_candidate_plan.json"
TABLE_CANDIDATE_PLAN_JSONL_FILE = "table_candidate_plan.jsonl"
TABLE_CANDIDATE_SUMMARY_FILE = "table_candidate_summary.json"
TABLE_CANDIDATE_REVIEW_MD_FILE = "table_candidate_review.md"
TABLE_CANDIDATE_REVIEW_HTML_FILE = "table_candidate_review.html"
TABLE_CANDIDATE_GRAPH_NODES_FILE = "table_candidate_graph_nodes.json"
TABLE_CANDIDATE_GRAPH_EDGES_FILE = "table_candidate_graph_edges.json"
TABLE_CANDIDATE_QUALITY_FILE = "table_candidate_quality.json"
TRACE_NET_REPAIR_PLAN_JSONL_FILE = "trace_net_repair_plan.jsonl"
TRACE_NET_REPAIR_PLAN_FILE = "trace_net_repair_plan.json"
TRACE_NET_REPAIR_SUMMARY_FILE = "trace_net_repair_summary.json"

TABLE_ROUTE_HIGH = "table_crop_tile_repair_route_high"
TABLE_ROUTE_MEDIUM = "table_crop_tile_repair_route_medium"
TABLE_ROUTE_REVIEW = "table_candidate_review_route"
ROUTE_SKIP = "skip_non_table"

_PAGE_ID_KEYS = ("page_id", "id", "page", "node_id", "entity_id")
_TIFF_KEYS = (
    "tiff_path",
    "source_tiff_path",
    "image_path",
    "image_file",
    "local_tiff_path",
    "tiff_file_path",
    "page_image_path",
)
_SOURCE_URL_KEYS = ("source_url", "url", "rescarta_url", "source_link")
_ROLE_KEYS = ("page_role", "role", "context_role", "document_role", "visual_role", "page_type")
_IMAGE_CLASS_KEYS = (
    "image_class",
    "image_classes",
    "image_classification",
    "visual_class",
    "visual_classes",
    "page_image_class",
    "page_image_classes",
    "classification",
)
_TITLE_KEYS = ("visible_title", "visible_title_header", "title", "header", "page_title")

_STRONG_TABLE_ROLES = {"table", "table_grid", "parts_table", "effective_pages_table"}
_MEDIUM_TABLE_ROLES = {"parts_list", "numerical_index", "index", "vendor_list", "list"}
_NON_TABLE_ROLES = {
    "figure",
    "diagram",
    "engineering_drawing",
    "drawing",
    "illustration",
    "blank",
    "title",
    "title_page",
    "cover",
}
_TABLE_HINTS = {"likely_table_or_grid", "table", "grid", "table_or_grid", "parts_list_table", "effective_pages"}
_FIGURE_HINTS = {"likely_figure_or_diagram", "figure", "diagram", "drawing", "engineering_drawing", "image_heavy"}
_TITLE_HINTS = {"numerical_index", "title", "cover"}


@dataclass(frozen=True)
class TableCandidateScanPaths:
    entity_trait_dir: Path = DEFAULT_ENTITY_TRAIT_DIR
    export_dir: Path = DEFAULT_EXPORT_DIR
    image_recognition_dir: Path = DEFAULT_IMAGE_RECOGNITION_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    page_cards_path: Path | None = None
    page_index_path: Path | None = None
    image_audit_path: Path | None = None
    candidate_plan_path: Path | None = None
    candidate_plan_jsonl_path: Path | None = None
    summary_path: Path | None = None
    review_md_path: Path | None = None
    review_html_path: Path | None = None
    graph_nodes_path: Path | None = None
    graph_edges_path: Path | None = None
    repair_plan_jsonl_path: Path | None = None
    repair_plan_path: Path | None = None
    repair_summary_path: Path | None = None
    quality_path: Path | None = None

    @property
    def page_cards(self) -> Path:
        return self.page_cards_path or (self.entity_trait_dir / PAGE_CHARACTER_CARDS_FILE)

    @property
    def page_index(self) -> Path:
        return self.page_index_path or (self.export_dir / PAGE_INDEX_FILE)

    @property
    def image_audit(self) -> Path:
        return self.image_audit_path or (self.image_recognition_dir / IMAGE_AUDIT_FILE)

    @property
    def candidate_plan(self) -> Path:
        return self.candidate_plan_path or (self.output_dir / TABLE_CANDIDATE_PLAN_FILE)

    @property
    def candidate_plan_jsonl(self) -> Path:
        return self.candidate_plan_jsonl_path or (self.output_dir / TABLE_CANDIDATE_PLAN_JSONL_FILE)

    @property
    def summary(self) -> Path:
        return self.summary_path or (self.output_dir / TABLE_CANDIDATE_SUMMARY_FILE)

    @property
    def review_md(self) -> Path:
        return self.review_md_path or (self.output_dir / TABLE_CANDIDATE_REVIEW_MD_FILE)

    @property
    def review_html(self) -> Path:
        return self.review_html_path or (self.output_dir / TABLE_CANDIDATE_REVIEW_HTML_FILE)

    @property
    def graph_nodes(self) -> Path:
        return self.graph_nodes_path or (self.output_dir / TABLE_CANDIDATE_GRAPH_NODES_FILE)

    @property
    def graph_edges(self) -> Path:
        return self.graph_edges_path or (self.output_dir / TABLE_CANDIDATE_GRAPH_EDGES_FILE)

    @property
    def repair_plan_jsonl(self) -> Path:
        return self.repair_plan_jsonl_path or (self.output_dir / TRACE_NET_REPAIR_PLAN_JSONL_FILE)

    @property
    def repair_plan(self) -> Path:
        return self.repair_plan_path or (self.output_dir / TRACE_NET_REPAIR_PLAN_FILE)

    @property
    def repair_summary(self) -> Path:
        return self.repair_summary_path or (self.output_dir / TRACE_NET_REPAIR_SUMMARY_FILE)

    @property
    def quality(self) -> Path:
        return self.quality_path or (self.output_dir / TABLE_CANDIDATE_QUALITY_FILE)


@dataclass
class TableCandidateScanOptions:
    expect_pages: int | None = None
    max_pages: int | None = None
    max_image_edge: int = 1200
    threshold: int = 220
    min_high_score: int = 6
    min_medium_score: int = 4
    min_layout_score: int = 3
    require_layout_for_medium: bool = True
    include_review_in_repair_plan: bool = False
    open_review: bool = False


@dataclass
class TableCandidateRecord:
    page_id: str
    status: str
    route: str
    route_priority: str
    action: str
    page_role: str = "unknown"
    image_classification: str = "unknown"
    title: str = ""
    tiff_path: str = ""
    source_url: str = ""
    graph_score: int = 0
    layout_score: int = 0
    combined_score: int = 0
    graph_reasons: list[str] = field(default_factory=list)
    layout_reasons: list[str] = field(default_factory=list)
    layout_metrics: dict[str, Any] = field(default_factory=dict)
    has_table_trait: bool = False
    has_figure_trait: bool = False
    missing_image_path: bool = False
    missing_image_file: bool = False
    error: str = ""
    trace_net_table_candidate_version: str = "trace_net_table_candidate_scan_v1"

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    def to_repair_plan_row(self) -> dict[str, Any]:
        return {
            "page_id": self.page_id,
            "primary_repair_route": self.route,
            "primary_repair_action": self.action,
            "priority": self.route_priority,
            "table_route_priority": self.route_priority,
            "review_traits": ["table_candidate_scanned"] + (["table_expected_but_not_extracted"] if self.route in {TABLE_ROUTE_HIGH, TABLE_ROUTE_MEDIUM, TABLE_ROUTE_REVIEW} else []),
            "route_metadata": {
                "page_role": self.page_role,
                "image_classification": self.image_classification,
                "title": self.title,
                "graph_score": self.graph_score,
                "layout_score": self.layout_score,
                "combined_score": self.combined_score,
                "candidate_route": self.route,
                "candidate_action": self.action,
            },
            "table_graph_gate": {
                "decision": "allow" if self.route in {TABLE_ROUTE_HIGH, TABLE_ROUTE_MEDIUM, TABLE_ROUTE_REVIEW} else "skip",
                "score": self.graph_score,
                "reasons": self.graph_reasons,
            },
            "table_layout_gate": {
                "decision": "allow" if self.layout_score >= 0 else "not_evaluated",
                "score": self.layout_score,
                "reasons": self.layout_reasons,
                "metrics": self.layout_metrics,
            },
            "tiff_path": self.tiff_path,
            "source_url": self.source_url,
            "trace_net_table_candidate_version": self.trace_net_table_candidate_version,
        }


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip() or default
    return str(value).strip() or default


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _text(value).lower()).strip("_")


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")


def _iter_nested_sources(record: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    yield record
    for key in (
        "source", "metadata", "page", "page_card", "context", "page_context", "signals",
        "roles", "image_recognition", "visual", "route_metadata",
    ):
        value = record.get(key)
        if isinstance(value, Mapping):
            yield value
            for inner_key in ("source", "metadata", "context", "signals", "image_recognition"):
                inner = value.get(inner_key)
                if isinstance(inner, Mapping):
                    yield inner


def _first_nested_text(record: Mapping[str, Any], keys: Sequence[str]) -> str:
    for source in _iter_nested_sources(record):
        for key in keys:
            value = source.get(key)
            if isinstance(value, list):
                text = " ".join(_text(v) for v in value if _text(v))
            else:
                text = _text(value)
            if text:
                return text
    return ""


def _page_id_from_record(record: Mapping[str, Any]) -> str:
    text = _first_nested_text(record, _PAGE_ID_KEYS)
    if text.startswith("page:"):
        text = text.split(":", 1)[1]
    return text


def _extract_tiff_path(record: Mapping[str, Any]) -> str:
    return _first_nested_text(record, _TIFF_KEYS)


def _extract_source_url(record: Mapping[str, Any]) -> str:
    return _first_nested_text(record, _SOURCE_URL_KEYS)


def _resolve_image_path(path_text: str, cwd: Path | None = None) -> Path:
    normalized = path_text.replace("\\", os.sep)
    path = Path(normalized)
    if path.is_absolute():
        return path
    return (cwd or Path.cwd()) / path


# ---------------------------------------------------------------------------
# Load page metadata from existing graph artifacts
# ---------------------------------------------------------------------------


def _items_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, Mapping):
        for key in ("page_cards", "cards", "records", "pages", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                payload = value
                break
        else:
            payload = list(payload.values())
    if isinstance(payload, list):
        return [dict(x) for x in payload if isinstance(x, Mapping)]
    return []


def read_page_cards(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in _items_from_payload(_read_json(path, [])):
        page_id = _page_id_from_record(item)
        if page_id:
            out[page_id] = item
    return out


def read_page_index(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in _items_from_payload(_read_json(path, [])):
        page_id = _page_id_from_record(item)
        if page_id:
            out[page_id] = item
    return out


def read_image_audit_records(path: Path) -> dict[str, dict[str, Any]]:
    data = _read_json(path, {})
    rows: list[Any] = []
    if isinstance(data, Mapping):
        for key in ("records", "pages", "items"):
            value = data.get(key)
            if isinstance(value, list):
                rows = value
                break
    elif isinstance(data, list):
        rows = data
    out: dict[str, dict[str, Any]] = {}
    for item in rows:
        if not isinstance(item, Mapping):
            continue
        page_id = _page_id_from_record(item)
        if page_id:
            out[page_id] = dict(item)
    return out


def merge_page_records(*sources: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for source in sources:
        for page_id, record in source.items():
            target = merged.setdefault(page_id, {"page_id": page_id})
            # Keep the original source nested as a fallback, but also flatten common fields.
            if source is sources[0]:
                target.setdefault("page_card", dict(record))
            elif source is sources[1]:
                target.setdefault("page_index", dict(record))
            else:
                target.setdefault("image_recognition", dict(record))
            for key in (
                "page_role", "role", "image_class", "image_classification", "classification",
                "tiff_path", "source_tiff_path", "image_path", "source_url", "ocr_path",
                "title", "page_label", "ata_code", "manual_id",
            ):
                value = record.get(key)
                if value and not target.get(key):
                    target[key] = value
            context = _as_dict(record.get("context"))
            signals = _as_dict(record.get("signals"))
            if context.get("page_role") and not target.get("page_role"):
                target["page_role"] = context.get("page_role")
            if signals.get("image_classification") and not target.get("image_classification"):
                target["image_classification"] = signals.get("image_classification")
            classification = record.get("classification") or record.get("page_classification")
            if classification and not target.get("image_classification"):
                target["image_classification"] = classification
    return merged


def _record_role(record: Mapping[str, Any]) -> str:
    return _slug(_first_nested_text(record, _ROLE_KEYS) or "unknown")


def _record_image_class(record: Mapping[str, Any]) -> str:
    return _slug(_first_nested_text(record, _IMAGE_CLASS_KEYS) or "unknown")


def _record_title(record: Mapping[str, Any]) -> str:
    return _first_nested_text(record, _TITLE_KEYS)


def _record_blob(record: Mapping[str, Any]) -> str:
    pieces: list[str] = []
    for source in _iter_nested_sources(record):
        for key in ("page_role", "role", "image_class", "image_classification", "classification", "title", "visible_title", "summary", "short_summary", "visual_summary"):
            text = _text(source.get(key))
            if text:
                pieces.append(text)
    return _slug(" ".join(pieces))


def _record_traits(record: Mapping[str, Any]) -> set[str]:
    traits: set[str] = set()
    for source in _iter_nested_sources(record):
        for key in ("traits", "direct_traits", "derived_traits", "review_traits", "blocking_traits", "nonblocking_traits", "topics", "tags"):
            for item in _as_list(source.get(key)):
                text = _slug(item)
                if text:
                    traits.add(text)
    return traits


# ---------------------------------------------------------------------------
# Scoring/gating
# ---------------------------------------------------------------------------


def graph_table_score(record: Mapping[str, Any]) -> dict[str, Any]:
    role = _record_role(record)
    image_class = _record_image_class(record)
    title = _slug(_record_title(record))
    blob = _record_blob(record)
    traits = _record_traits(record)

    score = 0
    reasons: list[str] = []
    has_table = False
    has_figure = False

    if role in _STRONG_TABLE_ROLES:
        score += 4; reasons.append(f"role_strong_table:{role}"); has_table = True
    elif role in _MEDIUM_TABLE_ROLES:
        score += 2; reasons.append(f"role_medium_table:{role}"); has_table = True
    if any(h in image_class for h in _TABLE_HINTS) or any(h in blob for h in ("table_grid", "effective_pages", "parts_list_table")):
        score += 3; reasons.append(f"image_table:{image_class or 'blob'}"); has_table = True
    if any("table" in trait or "grid" in trait for trait in traits):
        score += 1; reasons.append("trait_table_or_grid"); has_table = True
    if any(h in image_class for h in _FIGURE_HINTS) or role in {"figure", "diagram", "engineering_drawing", "drawing", "illustration"} or any("figure" in t or "drawing" in t or "diagram" in t for t in traits):
        score -= 5; reasons.append(f"figure_or_drawing_signal:{role or image_class}"); has_figure = True
    if role in {"blank", "title", "title_page", "cover"}:
        score -= 5; reasons.append(f"non_table_role:{role}")
    if title and any(h == title or h in title for h in _TITLE_HINTS) and not has_table:
        score -= 2; reasons.append(f"title_hint_without_table:{title}")
    return {
        "score": int(score),
        "role": role or "unknown",
        "image_classification": image_class or "unknown",
        "title": _record_title(record),
        "reasons": reasons,
        "has_table_trait": bool(has_table),
        "has_figure_trait": bool(has_figure),
    }


def _resize_max_edge(image: "Image.Image", max_edge: int) -> "Image.Image":
    if max_edge <= 0:
        return image
    width, height = image.size
    longest = max(width, height)
    if longest <= max_edge:
        return image
    scale = max_edge / float(longest)
    return image.resize((max(1, int(width * scale)), max(1, int(height * scale))))


def _group_count(values: Sequence[int], min_run: int = 2) -> int:
    groups = 0
    run = 0
    for value in values:
        if value:
            run += 1
        else:
            if run >= min_run:
                groups += 1
            run = 0
    if run >= min_run:
        groups += 1
    return groups


def image_layout_score(path_text: str, *, max_edge: int = 1200, threshold: int = 220) -> dict[str, Any]:
    if Image is None or ImageOps is None:
        return {"score": 0, "reasons": ["pillow_missing"], "metrics": {}, "error": "Pillow unavailable"}
    if not path_text:
        return {"score": 0, "reasons": ["missing_image_path"], "metrics": {}, "error": "missing image path"}
    path = _resolve_image_path(path_text)
    if not path.exists():
        return {"score": 0, "reasons": ["missing_image_file"], "metrics": {}, "error": f"missing image file: {path_text}"}
    try:
        with Image.open(path) as raw:
            image = raw.convert("RGB")
    except Exception as exc:
        return {"score": 0, "reasons": ["image_open_error"], "metrics": {}, "error": str(exc)}
    image = _resize_max_edge(image, max_edge)
    gray = ImageOps.grayscale(image)
    width, height = gray.size
    pix = gray.load()
    col_counts: list[int] = []
    row_counts: list[int] = []
    ink = 0
    # Sampling stride keeps this cheap on full corpus.
    x_stride = max(1, width // 600)
    y_stride = max(1, height // 800)
    sampled_w = 0
    sampled_h = 0
    for x in range(0, width, x_stride):
        count = 0
        sampled_h = 0
        for y in range(0, height, y_stride):
            sampled_h += 1
            if pix[x, y] < threshold:
                count += 1
        col_counts.append(count)
        sampled_w += 1
    for y in range(0, height, y_stride):
        count = 0
        for x in range(0, width, x_stride):
            if pix[x, y] < threshold:
                count += 1
        row_counts.append(count)
    total = max(1, len(col_counts) * max(1, sampled_h))
    ink = sum(col_counts)
    ink_ratio = ink / total
    col_threshold = max(2, int(sampled_h * 0.035))
    row_threshold = max(3, int(sampled_w * 0.08))
    dense_col_threshold = max(2, int(sampled_h * 0.12))
    dense_row_threshold = max(3, int(sampled_w * 0.20))
    column_groups = _group_count([1 if c >= col_threshold else 0 for c in col_counts], min_run=2)
    dense_column_groups = _group_count([1 if c >= dense_col_threshold else 0 for c in col_counts], min_run=1)
    row_bands = _group_count([1 if c >= row_threshold else 0 for c in row_counts], min_run=1)
    dense_row_bands = _group_count([1 if c >= dense_row_threshold else 0 for c in row_counts], min_run=1)
    # Long horizontal rules are a strong table indicator in scanned manuals.
    horizontal_rules = sum(1 for c in row_counts if c >= int(sampled_w * 0.55))
    vertical_rules = sum(1 for c in col_counts if c >= int(sampled_h * 0.55))

    score = 0
    reasons: list[str] = []
    if 0.006 <= ink_ratio <= 0.30:
        score += 1; reasons.append("ink_ratio_plausible")
    elif ink_ratio < 0.003:
        score -= 2; reasons.append("too_little_ink")
    elif ink_ratio > 0.42:
        score -= 1; reasons.append("too_much_ink")
    if column_groups >= 6:
        score += 2; reasons.append(f"column_groups:{column_groups}")
    elif column_groups >= 3:
        score += 1; reasons.append(f"some_column_groups:{column_groups}")
    if row_bands >= 12:
        score += 2; reasons.append(f"row_bands:{row_bands}")
    elif row_bands >= 6:
        score += 1; reasons.append(f"some_row_bands:{row_bands}")
    if horizontal_rules >= 2:
        score += 2; reasons.append(f"horizontal_rules:{horizontal_rules}")
    if vertical_rules >= 2:
        score += 1; reasons.append(f"vertical_rules:{vertical_rules}")
    if dense_column_groups <= 1 and row_bands < 6 and horizontal_rules < 2:
        score -= 2; reasons.append("prose_or_figure_like_layout")
    metrics = {
        "width": width,
        "height": height,
        "ink_ratio": round(ink_ratio, 6),
        "column_groups": int(column_groups),
        "dense_column_groups": int(dense_column_groups),
        "row_bands": int(row_bands),
        "dense_row_bands": int(dense_row_bands),
        "horizontal_rules": int(horizontal_rules),
        "vertical_rules": int(vertical_rules),
        "threshold": int(threshold),
    }
    return {"score": int(score), "reasons": reasons, "metrics": metrics, "error": ""}


def classify_candidate(record: Mapping[str, Any], options: TableCandidateScanOptions) -> TableCandidateRecord:
    page_id = _page_id_from_record(record)
    tiff_path = _extract_tiff_path(record)
    source_url = _extract_source_url(record)
    graph = graph_table_score(record)
    missing_image_path = not bool(tiff_path)
    missing_image_file = False
    layout = {"score": 0, "reasons": ["layout_not_evaluated"], "metrics": {}, "error": ""}
    if tiff_path:
        path = _resolve_image_path(tiff_path)
        missing_image_file = not path.exists()
        if not missing_image_file:
            layout = image_layout_score(tiff_path, max_edge=options.max_image_edge, threshold=options.threshold)
        else:
            layout = {"score": 0, "reasons": ["missing_image_file"], "metrics": {}, "error": f"missing image file: {tiff_path}"}

    graph_score = int(graph.get("score", 0) or 0)
    layout_score = int(layout.get("score", 0) or 0)
    combined = graph_score + layout_score
    route = ROUTE_SKIP
    priority = "skip"
    action = "skip_non_table_page"
    status = "skip"
    # Route only with both graph and layout support unless graph signal is extremely strong.
    if graph_score >= 5 and layout_score >= max(1, options.min_layout_score - 1):
        route, priority, action, status = TABLE_ROUTE_HIGH, "high", "send_to_table_crop_tile_route", "candidate"
    elif combined >= options.min_high_score and layout_score >= options.min_layout_score:
        route, priority, action, status = TABLE_ROUTE_HIGH, "high", "send_to_table_crop_tile_route", "candidate"
    elif combined >= options.min_medium_score and (layout_score >= options.min_layout_score or not options.require_layout_for_medium):
        route, priority, action, status = TABLE_ROUTE_MEDIUM, "medium", "send_to_table_crop_tile_route", "candidate"
    elif graph_score >= 2 or layout_score >= options.min_layout_score:
        route, priority, action, status = TABLE_ROUTE_REVIEW, "review", "review_table_candidate_before_extraction", "review"
    if missing_image_path:
        status = "missing_image_path"
        route = TABLE_ROUTE_REVIEW
        priority = "review"
        action = "review_missing_image_path"
    elif missing_image_file:
        status = "missing_image_file"
        route = TABLE_ROUTE_REVIEW
        priority = "review"
        action = "review_missing_image_file"
    return TableCandidateRecord(
        page_id=page_id,
        status=status,
        route=route,
        route_priority=priority,
        action=action,
        page_role=str(graph.get("role") or "unknown"),
        image_classification=str(graph.get("image_classification") or "unknown"),
        title=str(graph.get("title") or ""),
        tiff_path=tiff_path,
        source_url=source_url,
        graph_score=graph_score,
        layout_score=layout_score,
        combined_score=int(combined),
        graph_reasons=[_text(x) for x in _as_list(graph.get("reasons")) if _text(x)],
        layout_reasons=[_text(x) for x in _as_list(layout.get("reasons")) if _text(x)],
        layout_metrics=_as_dict(layout.get("metrics")),
        has_table_trait=bool(graph.get("has_table_trait")),
        has_figure_trait=bool(graph.get("has_figure_trait")),
        missing_image_path=missing_image_path,
        missing_image_file=missing_image_file,
        error=str(layout.get("error") or ""),
    )


# ---------------------------------------------------------------------------
# Build/write artifacts
# ---------------------------------------------------------------------------


def build_graph(records: Sequence[TableCandidateRecord]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = [{"id": "trace_net_table_candidate_scan", "type": "table_candidate_scan", "label": "TRACE-Net all-page table candidate scan"}]
    edges: list[dict[str, Any]] = []
    for record in records:
        page_node = f"page:{record.page_id}"
        candidate_node = f"table_candidate:{record.page_id}"
        nodes.append({"id": page_node, "type": "page", "page_id": record.page_id})
        nodes.append({
            "id": candidate_node,
            "type": "table_candidate",
            "page_id": record.page_id,
            "status": record.status,
            "route": record.route,
            "priority": record.route_priority,
            "graph_score": record.graph_score,
            "layout_score": record.layout_score,
            "combined_score": record.combined_score,
        })
        edges.append({"source": page_node, "target": candidate_node, "type": "HAS_TABLE_CANDIDATE_SCAN"})
        edges.append({"source": candidate_node, "target": "trace_net_table_candidate_scan", "type": "DERIVED_FROM"})
    dedup: dict[str, dict[str, Any]] = {}
    for node in nodes:
        dedup[_text(node.get("id"))] = node
    return list(dedup.values()), edges


def build_summary(records: Sequence[TableCandidateRecord], options: TableCandidateScanOptions, nodes: Sequence[Mapping[str, Any]], edges: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(r.status for r in records)
    route_counts = Counter(r.route for r in records)
    priority_counts = Counter(r.route_priority for r in records)
    high = route_counts.get(TABLE_ROUTE_HIGH, 0)
    medium = route_counts.get(TABLE_ROUTE_MEDIUM, 0)
    review = route_counts.get(TABLE_ROUTE_REVIEW, 0)
    skip = route_counts.get(ROUTE_SKIP, 0)
    missing = status_counts.get("missing_image_path", 0) + status_counts.get("missing_image_file", 0)
    candidate = high + medium
    status = "OK" if records and missing == 0 else ("PARTIAL" if records else "FAIL")
    return {
        "status": status,
        "records": len(records),
        "expected_pages": options.expect_pages,
        "candidate_records": candidate,
        "high_candidate_records": high,
        "medium_candidate_records": medium,
        "review_candidate_records": review,
        "skip_records": skip,
        "missing_image_records": missing,
        "status_counts": dict(status_counts),
        "route_counts": dict(route_counts),
        "priority_counts": dict(priority_counts),
        "layout_gate_enabled": True,
        "min_high_score": options.min_high_score,
        "min_medium_score": options.min_medium_score,
        "min_layout_score": options.min_layout_score,
        "graph_nodes": len(nodes),
        "graph_edges": len(edges),
        "trace_net_repair_plan_jsonl": TRACE_NET_REPAIR_PLAN_JSONL_FILE,
    }


def build_review_md(records: Sequence[TableCandidateRecord], summary: Mapping[str, Any]) -> str:
    lines = ["# TRACE-Net all-page table candidate scan", "", "## Summary", ""]
    for key in ("status", "records", "candidate_records", "high_candidate_records", "medium_candidate_records", "review_candidate_records", "skip_records", "missing_image_records", "route_counts"):
        lines.append(f"- **{key}**: {summary.get(key)}")
    lines.extend(["", "## Candidates", ""])
    for record in records:
        if record.route == ROUTE_SKIP:
            continue
        lines.append(f"### {record.page_id}")
        lines.append(f"- route: `{record.route}`")
        lines.append(f"- priority: `{record.route_priority}`")
        lines.append(f"- role/image: `{record.page_role}` / `{record.image_classification}`")
        lines.append(f"- scores: graph={record.graph_score}, layout={record.layout_score}, combined={record.combined_score}")
        lines.append(f"- tiff: `{record.tiff_path}`")
        lines.append(f"- graph reasons: {', '.join(record.graph_reasons) or 'none'}")
        lines.append(f"- layout reasons: {', '.join(record.layout_reasons) or 'none'}")
        lines.append("")
    return "\n".join(lines) + "\n"


def build_review_html(records: Sequence[TableCandidateRecord], summary: Mapping[str, Any]) -> str:
    cards = []
    for record in records:
        if record.route == ROUTE_SKIP:
            continue
        cards.append(f"""
<section class="card {html.escape(record.route_priority)}">
  <h2>{html.escape(record.page_id)}</h2>
  <div class="meta">
    <span>route: <b>{html.escape(record.route)}</b></span>
    <span>priority: <b>{html.escape(record.route_priority)}</b></span>
    <span>graph: <b>{record.graph_score}</b></span>
    <span>layout: <b>{record.layout_score}</b></span>
    <span>combined: <b>{record.combined_score}</b></span>
  </div>
  <p><b>role/image:</b> {html.escape(record.page_role)} / {html.escape(record.image_classification)}</p>
  <p><b>TIFF:</b> <code>{html.escape(record.tiff_path or 'none')}</code></p>
  <p><b>Graph reasons:</b> {html.escape(', '.join(record.graph_reasons) or 'none')}</p>
  <p><b>Layout reasons:</b> {html.escape(', '.join(record.layout_reasons) or 'none')}</p>
  <details><summary>Layout metrics</summary><pre>{html.escape(json.dumps(record.layout_metrics, indent=2, sort_keys=True))}</pre></details>
</section>""")
    style = """
<style>
body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#f7f7f8;color:#1f2937;margin:24px}
header,.card{background:white;border:1px solid #ddd;border-radius:12px;padding:16px;margin:0 0 16px 0;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.meta{display:flex;gap:10px;flex-wrap:wrap;color:#4b5563}.meta span{background:#f3f4f6;border-radius:999px;padding:4px 10px}
.high{border-left:6px solid #1d4ed8}.medium{border-left:6px solid #2f855a}.review{border-left:6px solid #d97706}code{word-break:break-all}pre{white-space:pre-wrap;background:#f3f4f6;padding:12px;border-radius:8px}
</style>
"""
    summary_items = "".join(f"<li><b>{html.escape(str(k))}</b>: {html.escape(str(v))}</li>" for k, v in summary.items() if k in {"status", "records", "candidate_records", "high_candidate_records", "medium_candidate_records", "review_candidate_records", "skip_records", "route_counts"})
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>TRACE-Net table candidate scan</title>{style}</head><body>
<header><h1>TRACE-Net all-page table candidate scan</h1><ul>{summary_items}</ul></header>
{''.join(cards)}
</body></html>"""


def build_and_write_table_candidate_scan(paths: TableCandidateScanPaths, options: TableCandidateScanOptions) -> dict[str, Any]:
    page_cards = read_page_cards(paths.page_cards)
    page_index = read_page_index(paths.page_index)
    image_audit = read_image_audit_records(paths.image_audit)
    pages = merge_page_records(page_cards, page_index, image_audit)
    records: list[TableCandidateRecord] = []
    for page_id in sorted(pages):
        records.append(classify_candidate(pages[page_id], options))
        if options.max_pages is not None and len(records) >= options.max_pages:
            break
    nodes, edges = build_graph(records)
    summary = build_summary(records, options, nodes, edges)
    payload = {"status": summary["status"], "summary": summary, "records": [r.to_json() for r in records]}
    repair_rows = [r.to_repair_plan_row() for r in records if r.route in {TABLE_ROUTE_HIGH, TABLE_ROUTE_MEDIUM} or (options.include_review_in_repair_plan and r.route == TABLE_ROUTE_REVIEW)]
    repair_payload = {"status": summary["status"], "summary": summary, "records": repair_rows}
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(paths.candidate_plan, payload)
    write_jsonl(paths.candidate_plan_jsonl, [r.to_json() for r in records])
    _write_json(paths.summary, summary)
    _write_json(paths.graph_nodes, nodes)
    _write_json(paths.graph_edges, edges)
    paths.review_md.write_text(build_review_md(records, summary), encoding="utf-8")
    paths.review_html.write_text(build_review_html(records, summary), encoding="utf-8")
    write_jsonl(paths.repair_plan_jsonl, repair_rows)
    _write_json(paths.repair_plan, repair_payload)
    _write_json(paths.repair_summary, summary)
    if options.open_review:
        try:
            webbrowser.open(paths.review_html.resolve().as_uri())
        except Exception:
            pass
    return payload


# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------


def build_table_candidate_quality(paths: TableCandidateScanPaths, *, min_records: int = 1, expect_pages: int | None = None, min_candidates: int = 1, max_missing_images: int = 0) -> dict[str, Any]:
    summary = _read_json(paths.summary, {}) or {}
    records = []
    if paths.candidate_plan_jsonl.exists():
        with paths.candidate_plan_jsonl.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, Mapping):
                    records.append(value)
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, message: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "message": message})

    present = paths.summary.exists() and paths.candidate_plan_jsonl.exists()
    add("table_candidate_artifacts_present", present, f"summary={paths.summary.exists()}; plan_jsonl={paths.candidate_plan_jsonl.exists()}.")
    status = _text(summary.get("status"), "missing")
    add("table_candidate_status", status.lower() in {"ok", "partial"}, f"status={status}.")
    count = int(summary.get("records", len(records)) or 0)
    add("table_candidate_records", count >= min_records and len(records) >= min_records, f"records summary={count}, jsonl={len(records)}; minimum={min_records}.")
    if expect_pages is not None:
        add("table_candidate_expected_pages", count == int(expect_pages), f"records={count}; expected={expect_pages}.")
    candidates = int(summary.get("candidate_records", 0) or 0)
    add("table_candidate_candidates", candidates >= int(min_candidates), f"candidate_records={candidates}; minimum={min_candidates}.")
    missing = int(summary.get("missing_image_records", 0) or 0)
    add("table_candidate_missing_images", missing <= int(max_missing_images), f"missing_image_records={missing}; max={max_missing_images}.")
    overall = all(c["ok"] for c in checks)
    report_summary = {
        "table_candidate_summary_present": paths.summary.exists(),
        "table_candidate_plan_present": paths.candidate_plan_jsonl.exists(),
        "table_candidate_status": status,
        "table_candidate_records": count,
        "table_candidate_expected_pages": expect_pages,
        "table_candidate_candidates": candidates,
        "table_candidate_high_candidates": int(summary.get("high_candidate_records", 0) or 0),
        "table_candidate_medium_candidates": int(summary.get("medium_candidate_records", 0) or 0),
        "table_candidate_review_candidates": int(summary.get("review_candidate_records", 0) or 0),
        "table_candidate_skip_records": int(summary.get("skip_records", 0) or 0),
        "table_candidate_missing_image_records": missing,
        "table_candidate_route_counts": summary.get("route_counts", {}),
        "table_candidate_repair_plan_jsonl_path": str(paths.repair_plan_jsonl),
    }
    return {"status": "OK" if overall else "FAIL", "summary": report_summary, "checks": checks}


def write_table_candidate_quality(report: Mapping[str, Any], paths: TableCandidateScanPaths) -> Path:
    _write_json(paths.quality, report)
    return paths.quality


def print_table_candidate_scan(result: Mapping[str, Any], paths: TableCandidateScanPaths) -> None:
    summary = _as_dict(result.get("summary"))
    print("TRACE-Net all-page table candidate scan")
    print(f"  Status: {summary.get('status')}")
    print(f"  Output dir: {paths.output_dir}")
    print("  Summary:")
    for key in ("records", "candidate_records", "high_candidate_records", "medium_candidate_records", "review_candidate_records", "skip_records", "missing_image_records", "route_counts"):
        print(f"    {key}: {summary.get(key)}")
    print("Files written:")
    print(f"  candidate_plan: {paths.candidate_plan}")
    print(f"  candidate_plan_jsonl: {paths.candidate_plan_jsonl}")
    print(f"  trace_net_repair_plan_jsonl: {paths.repair_plan_jsonl}")
    print(f"  review_html: {paths.review_html}")


def print_table_candidate_quality(report: Mapping[str, Any]) -> None:
    print("TRACE-Net all-page table candidate quality gate")
    print(f"  Status: {report.get('status')}")
    print("  Summary:")
    for key, value in _as_dict(report.get("summary")).items():
        print(f"    {key}: {value}")
    print("  Checks:")
    for check in _as_list(report.get("checks")):
        if isinstance(check, Mapping):
            print(f"    {'OK' if check.get('ok') else 'FAIL'} {check.get('name')}: {check.get('message')}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan all pages for TRACE-Net table candidates.")
    parser.add_argument("--entity-trait-dir", default=str(DEFAULT_ENTITY_TRAIT_DIR))
    parser.add_argument("--export-dir", default=str(DEFAULT_EXPORT_DIR))
    parser.add_argument("--image-recognition-dir", default=str(DEFAULT_IMAGE_RECOGNITION_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--expect-pages", type=int, default=None)
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--max-image-edge", type=int, default=1200)
    parser.add_argument("--threshold", type=int, default=220)
    parser.add_argument("--min-high-score", type=int, default=6)
    parser.add_argument("--min-medium-score", type=int, default=4)
    parser.add_argument("--min-layout-score", type=int, default=3)
    parser.add_argument("--no-require-layout-for-medium", action="store_true")
    parser.add_argument("--include-review-in-repair-plan", action="store_true")
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args(argv)
    paths = TableCandidateScanPaths(
        entity_trait_dir=Path(args.entity_trait_dir),
        export_dir=Path(args.export_dir),
        image_recognition_dir=Path(args.image_recognition_dir),
        output_dir=Path(args.output_dir),
    )
    options = TableCandidateScanOptions(
        expect_pages=args.expect_pages,
        max_pages=args.max_pages,
        max_image_edge=args.max_image_edge,
        threshold=args.threshold,
        min_high_score=args.min_high_score,
        min_medium_score=args.min_medium_score,
        min_layout_score=args.min_layout_score,
        require_layout_for_medium=not bool(args.no_require_layout_for_medium),
        include_review_in_repair_plan=bool(args.include_review_in_repair_plan),
        open_review=bool(args.open),
    )
    result = build_and_write_table_candidate_scan(paths, options)
    print_table_candidate_scan(result, paths)
    return 0 if _as_dict(result.get("summary")).get("status") in {"OK", "PARTIAL"} else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
