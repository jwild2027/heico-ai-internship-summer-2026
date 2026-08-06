"""TRACE-Net table crop/tile executor v1.

This is the first concrete implementation of Part C: table extraction.
It does not call OCR, Ollama, or a table model yet. Instead it turns the
TRACE-Net repair plan's table routes into deterministic image artifacts:

- selects high/medium table-route pages from trace_net_repair_plan.jsonl;
- resolves each page's source TIFF/image path from clean visual-text records;
- crops page margins using a simple ink/content bounding box;
- writes a full preprocessed PNG plus horizontal table/row-band tiles;
- writes a manifest, graph overlay, review HTML/Markdown, and quality summary.

The purpose is to prove page routing and image handling before adding OCR or
vision extraction per tile. The resulting tiles are the future input to a
GRIT-Table/table OCR executor.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import sys
import time
import webbrowser
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:  # Pillow is required for the table tile executor.
    from PIL import Image, ImageOps
except Exception:  # pragma: no cover - exercised only in missing dependency envs
    Image = None  # type: ignore[assignment]
    ImageOps = None  # type: ignore[assignment]

DEFAULT_VISUAL_TEXT_DIR = Path("local_data/organization/visual_text")
DEFAULT_TRACE_NET_DIR = Path("local_data/organization/trace_net")
DEFAULT_ENTITY_TRAIT_DIR = Path("local_data/organization/entity_traits")
DEFAULT_OUTPUT_DIR = Path("local_data/organization/table_extraction")
DEFAULT_ENTITY_TRAIT_DIR = Path("local_data/organization/entity_traits")

TABLE_ROUTE_HIGH = "table_crop_tile_repair_route_high"
TABLE_ROUTE_MEDIUM = "table_crop_tile_repair_route_medium"
TABLE_ROUTE_LEGACY = "table_crop_tile_repair_route"
TABLE_ROUTES = {TABLE_ROUTE_HIGH, TABLE_ROUTE_MEDIUM, TABLE_ROUTE_LEGACY}
ROUTE_ALIASES = {
    "high": TABLE_ROUTE_HIGH,
    "medium": TABLE_ROUTE_MEDIUM,
    "legacy": TABLE_ROUTE_LEGACY,
    "all": "all",
}

TILE_PLAN_FILE = "table_tile_plan.json"
TILE_PLAN_JSONL_FILE = "table_tile_plan.jsonl"
TILE_SUMMARY_FILE = "table_tile_summary.json"
TILE_GRAPH_NODES_FILE = "table_tile_graph_nodes.json"
TILE_GRAPH_EDGES_FILE = "table_tile_graph_edges.json"
TILE_REVIEW_MD_FILE = "table_tile_review.md"
TILE_REVIEW_HTML_FILE = "table_tile_review.html"
TILE_QUALITY_FILE = "table_tile_quality.json"
PAGE_CHARACTER_CARDS_FILE = "page_character_cards.json"

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


@dataclass(frozen=True)
class TraceNetTableTilePaths:
    visual_text_dir: Path = DEFAULT_VISUAL_TEXT_DIR
    trace_net_dir: Path = DEFAULT_TRACE_NET_DIR
    entity_trait_dir: Path = DEFAULT_ENTITY_TRAIT_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    entity_trait_dir: Path = DEFAULT_ENTITY_TRAIT_DIR
    clean_records_path: Path | None = None
    repair_plan_path: Path | None = None
    tile_plan_path: Path | None = None
    tile_plan_jsonl_path: Path | None = None
    summary_path: Path | None = None
    graph_nodes_path: Path | None = None
    graph_edges_path: Path | None = None
    review_md_path: Path | None = None
    review_html_path: Path | None = None
    quality_path: Path | None = None
    tiles_dir_path: Path | None = None
    page_character_cards_path: Path | None = None

    @property
    def clean_records(self) -> Path:
        return self.clean_records_path or (self.visual_text_dir / "visual_text_extraction_clean.jsonl")

    @property
    def repair_plan(self) -> Path:
        return self.repair_plan_path or (self.trace_net_dir / "trace_net_repair_plan.jsonl")

    @property
    def page_cards(self) -> Path:
        return self.page_cards_path or (self.entity_trait_dir / PAGE_CHARACTER_CARDS_FILE)

    @property
    def tile_plan(self) -> Path:
        return self.tile_plan_path or (self.output_dir / TILE_PLAN_FILE)

    @property
    def tile_plan_jsonl(self) -> Path:
        return self.tile_plan_jsonl_path or (self.output_dir / TILE_PLAN_JSONL_FILE)

    @property
    def summary(self) -> Path:
        return self.summary_path or (self.output_dir / TILE_SUMMARY_FILE)

    @property
    def graph_nodes(self) -> Path:
        return self.graph_nodes_path or (self.output_dir / TILE_GRAPH_NODES_FILE)

    @property
    def graph_edges(self) -> Path:
        return self.graph_edges_path or (self.output_dir / TILE_GRAPH_EDGES_FILE)

    @property
    def review_md(self) -> Path:
        return self.review_md_path or (self.output_dir / TILE_REVIEW_MD_FILE)

    @property
    def review_html(self) -> Path:
        return self.review_html_path or (self.output_dir / TILE_REVIEW_HTML_FILE)

    @property
    def quality(self) -> Path:
        return self.quality_path or (self.output_dir / TILE_QUALITY_FILE)

    @property
    def tiles_dir(self) -> Path:
        return self.tiles_dir_path or (self.output_dir / "tiles")

    @property
    def page_character_cards(self) -> Path:
        return self.page_character_cards_path or (self.entity_trait_dir / "page_character_cards.json")


@dataclass
class TraceNetTableTileOptions:
    routes: tuple[str, ...] = (TABLE_ROUTE_HIGH,)
    include_medium: bool = False
    include_legacy: bool = False
    max_pages: int | None = None
    overwrite: bool = True
    tiles_per_page: int = 6
    tile_overlap_px: int = 48
    threshold: int = 245
    crop_padding_px: int = 24
    max_image_edge: int = 1800
    expected_pages: int | None = None
    open_review: bool = False
    table_graph_gate: bool = True
    min_table_gate_score: int = 2
    table_layout_gate: bool = True
    min_table_layout_score: int = 3
    table_layout_probe_edge: int = 1200

    def selected_routes(self) -> set[str]:
        routes = {_canonical_route(route) for route in self.routes}
        if "all" in routes:
            routes = set(TABLE_ROUTES)
        if self.include_medium:
            routes.add(TABLE_ROUTE_MEDIUM)
        if self.include_legacy:
            routes.add(TABLE_ROUTE_LEGACY)
        return {r for r in routes if r in TABLE_ROUTES}


@dataclass
class TableTileRecord:
    page_id: str
    status: str
    repair_route: str
    repair_priority: str
    repair_action: str
    tiff_path: str
    source_url: str = ""
    route_traits: list[str] = field(default_factory=list)
    reason: str = ""
    table_gate_score: int = 0
    table_gate_decision: str = "not_evaluated"
    table_gate_reasons: list[str] = field(default_factory=list)
    table_layout_gate_score: int = 0
    table_layout_gate_decision: str = "not_evaluated"
    table_layout_gate_reasons: list[str] = field(default_factory=list)
    table_layout_metrics: dict[str, Any] = field(default_factory=dict)
    image_exists: bool = False
    error: str = ""
    original_width: int = 0
    original_height: int = 0
    processed_width: int = 0
    processed_height: int = 0
    crop_box: list[int] = field(default_factory=list)
    crop_width: int = 0
    crop_height: int = 0
    crop_area_ratio: float = 0.0
    full_preprocessed_path: str = ""
    tile_count: int = 0
    tiles: list[dict[str, Any]] = field(default_factory=list)
    graph_table_gate_enabled: bool = True
    graph_table_gate_allowed: bool = True
    graph_table_gate_reason: str = ""
    graph_page_role: str = ""
    graph_image_classification: str = ""
    graph_has_table_trait: bool = False
    graph_has_figure_trait: bool = False
    trace_net_table_tile_version: str = "trace_net_table_tile_v1"

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


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


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, Mapping):
                rows.append(dict(value))
    return rows


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", _text(value)).strip().lower()


def _slug(value: Any) -> str:
    text = _norm(value)
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "unknown"


def _page_id_from_record(record: Mapping[str, Any]) -> str:
    for key in _PAGE_ID_KEYS:
        value = record.get(key)
        if value:
            text = _text(value)
            if text.startswith("page:"):
                return text.split(":", 1)[1]
            return text
    source = _as_dict(record.get("source"))
    value = source.get("page_id")
    if value:
        return _text(value)
    return ""


def _canonical_route(route: str) -> str:
    route = _text(route)
    return ROUTE_ALIASES.get(route, route)


def _safe_filename(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return text.strip("_") or "unknown"


def _rel(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except Exception:
        return path.as_posix()


def _first_nested_text(record: Mapping[str, Any], keys: Sequence[str]) -> str:
    candidates: list[Any] = []
    for key in keys:
        candidates.append(record.get(key))
    for parent_key in ("source", "metadata", "page", "page_card", "context", "image_recognition", "route_metadata"):
        parent = _as_dict(record.get(parent_key))
        for key in keys:
            candidates.append(parent.get(key))
    for value in candidates:
        text = _text(value)
        if text:
            return text
    return ""


def _extract_tiff_path(record: Mapping[str, Any]) -> str:
    return _first_nested_text(record, _TIFF_KEYS)


def _extract_source_url(record: Mapping[str, Any]) -> str:
    return _first_nested_text(record, _SOURCE_URL_KEYS)


def _clean_records_by_page(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for record in read_jsonl(path):
        page_id = _page_id_from_record(record)
        if page_id:
            records[page_id] = record
    return records


def _page_character_cards_by_page(path: Path) -> dict[str, dict[str, Any]]:
    """Read entity-trait page character cards when available.

    This is the main bridge from the table tile executor back to the graph-like
    page character layer. The file can be a list of cards or a mapping keyed by
    page_id. Only lightweight metadata is used by the table gate; the raw card is
    preserved under `page_card`.
    """
    data = _read_json(path, {})
    if isinstance(data, Mapping):
        if isinstance(data.get("page_cards"), list):
            items = data.get("page_cards")
        elif isinstance(data.get("cards"), list):
            items = data.get("cards")
        else:
            items = list(data.values())
    elif isinstance(data, list):
        items = data
    else:
        items = []
    out: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, Mapping):
            continue
        page_id = _page_id_from_record(item) or _text(item.get("page_id"))
        if not page_id:
            continue
        card = dict(item)
        # Flatten common nested fields so later generic metadata readers can use
        # the card even when its shape changes.
        context = _as_dict(card.get("context"))
        signals = _as_dict(card.get("signals"))
        if context.get("page_role") and not card.get("page_role"):
            card["page_role"] = context.get("page_role")
        if signals.get("image_classification") and not card.get("image_class"):
            card["image_class"] = signals.get("image_classification")
        out[page_id] = card
    return out


def _merge_page_card_metadata(clean_records: dict[str, dict[str, Any]], page_cards: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    merged = {pid: dict(record) for pid, record in clean_records.items()}
    for page_id, card in page_cards.items():
        rec = merged.setdefault(page_id, {"page_id": page_id})
        rec.setdefault("page_card", dict(card))
        if card.get("page_role") and not rec.get("page_role"):
            rec["page_role"] = card.get("page_role")
        if card.get("image_class") and not rec.get("image_class"):
            rec["image_class"] = card.get("image_class")
        if card.get("traits") and not rec.get("graph_traits"):
            rec["graph_traits"] = card.get("traits")
    return merged


def _page_cards_by_page(path: Path) -> dict[str, dict[str, Any]]:
    payload = _read_json(path, []) or []
    if isinstance(payload, Mapping):
        for key in ("page_cards", "records", "pages", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                payload = value
                break
    cards: dict[str, dict[str, Any]] = {}
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, Mapping):
                continue
            page_id = _text(item.get("page_id") or item.get("id") or item.get("entity_id"))
            if page_id.startswith("page:"):
                page_id = page_id.split(":", 1)[1]
            if page_id:
                cards[page_id] = dict(item)
    return cards


def _card_page_role(card: Mapping[str, Any], clean_record: Mapping[str, Any], plan: Mapping[str, Any]) -> str:
    context = _as_dict(card.get("context"))
    route_metadata = _as_dict(plan.get("route_metadata"))
    for value in (context.get("page_role"), card.get("page_role"), clean_record.get("page_role"), _as_dict(clean_record.get("context")).get("page_role"), route_metadata.get("page_role")):
        text = _slug(value)
        if text and text != "unknown":
            return text
    return _slug(route_metadata.get("role") or clean_record.get("role") or "unknown")


def _card_image_class(card: Mapping[str, Any], clean_record: Mapping[str, Any], plan: Mapping[str, Any]) -> str:
    signals = _as_dict(card.get("signals"))
    route_metadata = _as_dict(plan.get("route_metadata"))
    for value in (signals.get("image_classification"), card.get("image_classification"), clean_record.get("image_classification"), clean_record.get("image_class"), route_metadata.get("image_classification"), route_metadata.get("image_class")):
        text = _slug(value)
        if text and text != "unknown":
            return text
    return "unknown"


def _card_traits(card: Mapping[str, Any], clean_record: Mapping[str, Any], plan: Mapping[str, Any]) -> set[str]:
    traits: set[str] = set()
    for source in (card, clean_record, plan):
        for key in ("traits", "direct_traits", "derived_traits", "review_traits", "blocking_traits", "nonblocking_traits"):
            for item in _as_list(source.get(key)):
                text = _norm(item)
                if text:
                    traits.add(text)
    return traits


def _has_table_trait(role: str, image_class: str, traits: set[str]) -> bool:
    if role in {"table", "table_grid", "parts_table", "effective_pages_table"}:
        return True
    if "table" in image_class or "grid" in image_class:
        return True
    return any("table" in trait or "grid" in trait for trait in traits)


def _has_figure_trait(role: str, image_class: str, traits: set[str]) -> bool:
    if role in {"figure", "diagram", "engineering_drawing", "drawing", "illustration"}:
        return True
    if "figure" in image_class or "diagram" in image_class or "drawing" in image_class:
        return True
    return any("figure" in trait or "diagram" in trait or "drawing" in trait for trait in traits)


def table_graph_gate_decision(*, repair_route: str, card: Mapping[str, Any] | None, clean_record: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, Any]:
    card = card or {}
    role = _card_page_role(card, clean_record, plan)
    image_class = _card_image_class(card, clean_record, plan)
    traits = _card_traits(card, clean_record, plan)
    has_table = _has_table_trait(role, image_class, traits)
    has_figure = _has_figure_trait(role, image_class, traits)
    route = _text(repair_route)
    if not card:
        allowed = True
        reason = "no_page_character_card_available_allowing_repair_plan_route"
    elif role in {"blank", "title", "cover", "title_page"}:
        allowed = False
        reason = f"blocked_by_graph_role_{role}"
    elif has_figure and not has_table:
        allowed = False
        reason = "blocked_by_graph_figure_or_drawing_trait_without_table_trait"
    elif route == TABLE_ROUTE_HIGH:
        allowed = has_table and role not in {"front_matter", "procedure", "general_text", "text"}
        reason = "high_route_graph_table_supported" if allowed else "high_route_missing_strong_graph_table_support"
    elif route == TABLE_ROUTE_MEDIUM:
        allowed = has_table or role in {"parts_list", "numerical_index", "index", "vendor_list"}
        reason = "medium_route_graph_table_or_index_supported" if allowed else "medium_route_missing_graph_table_or_index_support"
    else:
        allowed = has_table
        reason = "legacy_route_graph_table_supported" if allowed else "legacy_route_missing_graph_table_support"
    return {
        "allowed": allowed,
        "reason": reason,
        "page_role": role,
        "image_classification": image_class,
        "has_table_trait": has_table,
        "has_figure_trait": has_figure,
    }


def _route_traits(plan: Mapping[str, Any]) -> list[str]:
    traits = []
    for key in ("review_traits", "blocking_traits", "nonblocking_traits"):
        for item in _as_list(plan.get(key)):
            text = _text(item)
            if text and text not in traits:
                traits.append(text)
    return traits


# ---------------------------------------------------------------------------
# Image preprocessing and tiling
# ---------------------------------------------------------------------------


def _resolve_image_path(path_text: str, cwd: Path | None = None) -> Path:
    # Git Bash/Windows records sometimes carry backslashes. Normalize without
    # breaking true Windows absolute paths when run on Windows.
    normalized = path_text.replace("\\", os.sep)
    path = Path(normalized)
    if path.is_absolute():
        return path
    return (cwd or Path.cwd()) / path


def _resize_max_edge(image: "Image.Image", max_edge: int) -> "Image.Image":
    if max_edge <= 0:
        return image
    width, height = image.size
    longest = max(width, height)
    if longest <= max_edge:
        return image
    scale = max_edge / float(longest)
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(new_size)


def _content_bbox(image: "Image.Image", threshold: int = 245, padding: int = 24) -> tuple[int, int, int, int]:
    gray = ImageOps.grayscale(image)
    # Non-white/ink pixels become 255 in mask; background becomes 0.
    mask = gray.point(lambda p: 255 if p < threshold else 0)
    bbox = mask.getbbox()
    width, height = image.size
    if not bbox:
        return (0, 0, width, height)
    left, top, right, bottom = bbox
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(width, right + padding)
    bottom = min(height, bottom + padding)
    if right <= left or bottom <= top:
        return (0, 0, width, height)
    return (left, top, right, bottom)


def _tile_bands(width: int, height: int, tile_count: int, overlap: int) -> list[tuple[int, int, int, int]]:
    count = max(1, tile_count)
    boxes: list[tuple[int, int, int, int]] = []
    for index in range(count):
        raw_top = int(math.floor(index * height / count))
        raw_bottom = int(math.ceil((index + 1) * height / count))
        top = max(0, raw_top - (overlap if index > 0 else 0))
        bottom = min(height, raw_bottom + (overlap if index < count - 1 else 0))
        if bottom > top:
            boxes.append((0, top, width, bottom))
    return boxes


def _save_png(image: "Image.Image", path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(path, format="PNG", optimize=True)


def build_tile_record(
    plan: Mapping[str, Any],
    clean_records: Mapping[str, Mapping[str, Any]],
    paths: TraceNetTableTilePaths,
    options: TraceNetTableTileOptions,
) -> TableTileRecord:
    if Image is None or ImageOps is None:
        page_id = _page_id_from_record(plan)
        return TableTileRecord(
            page_id=page_id,
            status="error",
            repair_route=_text(plan.get("primary_repair_route")),
            repair_priority=_text(plan.get("priority"), "unknown"),
            repair_action=_text(plan.get("primary_repair_action")),
            tiff_path="",
            error="Pillow is not installed; cannot process TIFF/image files.",
        )

    page_id = _page_id_from_record(plan)
    clean_record = clean_records.get(page_id, {})
    tiff_path = _extract_tiff_path(clean_record) or _extract_tiff_path(plan)
    source_url = _extract_source_url(clean_record) or _extract_source_url(plan)
    route = _text(plan.get("primary_repair_route"), "unknown")
    priority = _text(plan.get("table_route_priority") or plan.get("priority"), "unknown")
    action = _text(plan.get("primary_repair_action"), "unknown")
    traits = _route_traits(plan)
    reason = _text(plan.get("route_refinement_reason") or "; ".join(_as_list(plan.get("reasons"))))
    gate = _as_dict(plan.get("table_graph_gate"))

    record = TableTileRecord(
        page_id=page_id,
        status="pending",
        repair_route=route,
        repair_priority=priority,
        repair_action=action,
        tiff_path=tiff_path,
        source_url=source_url,
        route_traits=traits,
        reason=reason,
        table_gate_score=int(gate.get("score", 0) or 0),
        table_gate_decision=_text(gate.get("decision"), "not_evaluated"),
        table_gate_reasons=[_text(x) for x in _as_list(gate.get("reasons")) if _text(x)],
        table_layout_gate_score=int(_as_dict(plan.get("table_layout_gate")).get("score", 0) or 0),
        table_layout_gate_decision=_text(_as_dict(plan.get("table_layout_gate")).get("decision"), "not_evaluated"),
        table_layout_gate_reasons=[_text(x) for x in _as_list(_as_dict(plan.get("table_layout_gate")).get("reasons")) if _text(x)],
        table_layout_metrics=_as_dict(_as_dict(plan.get("table_layout_gate")).get("metrics")),
    )
    if not page_id:
        record.status = "error"
        record.error = "Missing page_id in repair plan record."
        return record
    if not tiff_path:
        record.status = "missing_image_path"
        record.error = "No TIFF/image path found in clean record or repair plan."
        return record

    image_path = _resolve_image_path(tiff_path)
    record.image_exists = image_path.exists()
    if not image_path.exists():
        record.status = "missing_image_file"
        record.error = f"Image file not found: {tiff_path}"
        return record

    try:
        with Image.open(image_path) as raw:
            image = raw.convert("RGB")
    except Exception as exc:
        record.status = "error"
        record.error = f"Could not open image: {exc}"
        return record

    record.original_width, record.original_height = image.size
    processed = _resize_max_edge(image, options.max_image_edge)
    record.processed_width, record.processed_height = processed.size
    bbox = _content_bbox(processed, threshold=options.threshold, padding=options.crop_padding_px)
    crop = processed.crop(bbox)
    record.crop_box = list(map(int, bbox))
    record.crop_width, record.crop_height = crop.size
    total_area = max(1, record.processed_width * record.processed_height)
    record.crop_area_ratio = round((record.crop_width * record.crop_height) / total_area, 6)

    page_dir = paths.tiles_dir / _safe_filename(page_id)
    if options.overwrite and page_dir.exists():
        # Remove stale tile PNGs but leave directory in place.
        for old in page_dir.glob("*.png"):
            try:
                old.unlink()
            except OSError:
                pass
    page_dir.mkdir(parents=True, exist_ok=True)

    full_path = page_dir / "full_preprocessed.png"
    _save_png(crop, full_path)
    record.full_preprocessed_path = full_path.as_posix()

    boxes = _tile_bands(crop.width, crop.height, options.tiles_per_page, options.tile_overlap_px)
    tiles: list[dict[str, Any]] = []
    for index, box in enumerate(boxes, start=1):
        tile = crop.crop(box)
        tile_path = page_dir / f"tile_{index:03d}.png"
        _save_png(tile, tile_path)
        tiles.append(
            {
                "tile_id": f"{page_id}_tile_{index:03d}",
                "tile_index": index,
                "path": tile_path.as_posix(),
                "relative_path": _rel(tile_path, paths.output_dir),
                "box": list(map(int, box)),
                "width": int(tile.width),
                "height": int(tile.height),
                "overlap_px": int(options.tile_overlap_px),
            }
        )
    record.tiles = tiles
    record.tile_count = len(tiles)
    record.status = "ok" if tiles else "error"
    if not tiles:
        record.error = "No tiles were generated."
    return record



# ---------------------------------------------------------------------------
# Graph-aware table routing gate
# ---------------------------------------------------------------------------

_ROLE_KEYS = (
    "page_role",
    "role",
    "context_role",
    "document_role",
    "visual_role",
    "page_type",
)
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
_TITLE_KEYS = (
    "visible_title",
    "visible_title_header",
    "title",
    "header",
)
_TABLE_ROLES_STRONG = {"table", "table_grid", "parts_table", "effective_pages_table"}
_TABLE_ROLES_MEDIUM = {"parts_list", "numerical_index", "index", "vendor_list", "list"}
_NON_TABLE_ROLES = {"figure", "diagram", "engineering_drawing", "drawing", "blank", "title", "title_page", "cover"}
_TABLE_HINTS = {"likely_table_or_grid", "table", "grid", "table_or_grid"}
_FIGURE_HINTS = {"likely_figure_or_diagram", "figure", "diagram", "drawing", "engineering_drawing", "image_heavy"}
_TITLE_ONLY_HINTS = {"numerical_index", "title", "cover"}


def _iter_metadata_sources(*records: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    for record in records:
        if isinstance(record, Mapping):
            yield record
            for key in (
                "source",
                "metadata",
                "page",
                "page_card",
                "context",
                "page_context",
                "image_recognition",
                "signals",
                "roles",
                "route_metadata",
                "visual_text_scores",
                "visual_text_scores_clean",
                "visual_text_cleanup_scores",
            ):
                value = record.get(key)
                if isinstance(value, Mapping):
                    yield value
                    for inner_key in ("context", "signals", "roles", "image_recognition", "metadata"):
                        inner = value.get(inner_key)
                        if isinstance(inner, Mapping):
                            yield inner


def _nested_slug(records: Sequence[Mapping[str, Any]], keys: Sequence[str]) -> str:
    for source in _iter_metadata_sources(*records):
        for key in keys:
            value = source.get(key)
            if isinstance(value, list):
                text = " ".join(_text(v) for v in value if _text(v))
            else:
                text = _text(value)
            if text:
                return _slug(text)
    return ""


def _nested_blob(records: Sequence[Mapping[str, Any]]) -> str:
    pieces: list[str] = []
    for source in _iter_metadata_sources(*records):
        for key in (
            "page_role",
            "role",
            "image_class",
            "image_classification",
            "visible_title",
            "title",
            "visual_summary",
            "clean_markdown",
            "visual_text",
            "text",
        ):
            text = _text(source.get(key))
            if text:
                pieces.append(text)
    return _slug(" ".join(pieces))


def _bool_nested(records: Sequence[Mapping[str, Any]], keys: Sequence[str]) -> bool:
    for source in _iter_metadata_sources(*records):
        for key in keys:
            value = source.get(key)
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)) and value:
                return True
            if isinstance(value, str) and value.strip().lower() in {"1", "true", "yes", "y"}:
                return True
    return False


def table_graph_gate_for_row(row: Mapping[str, Any], clean_record: Mapping[str, Any] | None, min_score: int = 2) -> dict[str, Any]:
    """Return graph-aware table gating information for a repair-plan row.

    The table cropper should not blindly cut every page that inherited a weak
    `table_expected_but_not_extracted` flag. This gate uses page-role, image
    classification, route metadata, and review traits to require a real table
    signal and to block obvious figure/drawing/title pages. It is intentionally
    conservative: pages that do not pass can still be handled by review or by a
    future figure/diagram route; they are just not tiled as tables.
    """
    clean = clean_record or {}
    records = [row, clean]
    route = _text(row.get("primary_repair_route"))
    traits = set(_route_traits(row))
    role = _nested_slug(records, _ROLE_KEYS)
    image_class = _nested_slug(records, _IMAGE_CLASS_KEYS)
    title = _nested_slug(records, _TITLE_KEYS)
    blob = _nested_blob(records)

    has_table_trait = (
        "table_expected_but_not_extracted" in traits
        or _bool_nested(records, ("has_table", "table_present", "contains_table", "has_table_signal"))
    )
    route_high = route == TABLE_ROUTE_HIGH
    route_medium = route == TABLE_ROUTE_MEDIUM
    route_legacy = route == TABLE_ROUTE_LEGACY
    role_table_strong = role in _TABLE_ROLES_STRONG
    role_table_medium = role in _TABLE_ROLES_MEDIUM
    image_table = any(h in image_class for h in _TABLE_HINTS) or any(h in blob for h in ("table_grid", "parts_list_table", "effective_pages"))
    figure_signal = role in _NON_TABLE_ROLES or any(h in image_class for h in _FIGURE_HINTS) or any(h in blob for h in ("engineering_drawing", "technical_drawing", "figure_diagram"))
    title_only = title in _TITLE_ONLY_HINTS and not image_table

    score = 0
    reasons: list[str] = []
    if route_high:
        score += 2; reasons.append("route_high")
    if route_medium:
        score += 1; reasons.append("route_medium")
    if route_legacy:
        score += 1; reasons.append("route_legacy")
    if role_table_strong:
        score += 3; reasons.append(f"role:{role}")
    elif role_table_medium:
        score += 1; reasons.append(f"role:{role}")
    if image_table:
        score += 2; reasons.append(f"image_table:{image_class or 'blob'}")
    if has_table_trait:
        score += 1; reasons.append("table_trait")
    if figure_signal:
        score -= 4; reasons.append(f"figure_or_drawing_signal:{role or image_class or 'blob'}")
    if title_only:
        score -= 3; reasons.append(f"title_only:{title}")

    allow = score >= int(min_score)
    decision = "allow" if allow else "skip"
    if not allow:
        reasons.append(f"score_below_threshold:{score}<{min_score}")
    return {
        "allow": allow,
        "decision": decision,
        "score": int(score),
        "min_score": int(min_score),
        "reasons": reasons,
        "page_role": role,
        "image_class": image_class,
        "title": title,
        "route": route,
        "has_table_trait": has_table_trait,
        "image_table": image_table,
        "figure_signal": figure_signal,
    }


def _run_lengths(flags: Sequence[bool], max_gap: int = 0) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    i = 0
    n = len(flags)
    while i < n:
        if flags[i]:
            start = i
            gap = 0
            i += 1
            while i < n:
                if flags[i]:
                    gap = 0
                    i += 1
                    continue
                if gap < max_gap and (i + 1 < n and flags[i + 1]):
                    gap += 1
                    i += 1
                    continue
                break
            runs.append((start, i))
        i += 1
    return runs


def _table_layout_metrics_for_image(path_text: str, *, max_edge: int = 1200, threshold: int = 220) -> dict[str, Any]:
    if Image is None:
        return {"status": "unavailable", "reason": "pillow_missing"}
    if not path_text:
        return {"status": "missing", "reason": "image_path_missing", "path": path_text}
    image_path = _resolve_image_path(path_text)
    if not image_path.exists():
        return {"status": "missing", "reason": "image_missing", "path": path_text}
    try:
        with Image.open(image_path) as raw:
            image = raw.convert("L")
    except Exception as exc:
        return {"status": "error", "reason": f"open_failed:{exc}", "path": path_text}
    width, height = image.size
    longest = max(width, height)
    if max_edge > 0 and longest > max_edge:
        scale = max_edge / float(longest)
        image = image.resize((max(1, int(width * scale)), max(1, int(height * scale))))
    width, height = image.size
    pixels = image.load()
    dark_rows = [0] * height
    dark_cols = [0] * width
    total_dark = 0
    for y in range(height):
        row_count = 0
        for x in range(width):
            if pixels[x, y] < threshold:
                row_count += 1
                dark_cols[x] += 1
        dark_rows[y] = row_count
        total_dark += row_count
    if total_dark == 0:
        return {"status": "ok", "width": width, "height": height, "ink_ratio": 0.0, "row_bands": 0, "column_groups": 0, "horizontal_rules": 0, "vertical_rules": 0}
    active_rows = [count > max(2, int(width * 0.015)) for count in dark_rows]
    row_runs = _run_lengths(active_rows, max_gap=1)
    row_bands = sum(1 for start, end in row_runs if 1 <= (end - start) <= 28)
    active_cols = [count > max(2, int(height * 0.01)) for count in dark_cols]
    col_runs = _run_lengths(active_cols, max_gap=2)
    column_groups = sum(1 for start, end in col_runs if (end - start) >= 6)
    horizontal_rules = sum(1 for count in dark_rows if count > int(width * 0.55))
    vertical_rules = sum(1 for count in dark_cols if count > int(height * 0.35))
    third_ink: list[float] = []
    for left, right in ((0, width // 3), (width // 3, (2 * width) // 3), ((2 * width) // 3, width)):
        span = max(1, right - left)
        ink = sum(dark_cols[left:right]) / float(span * height)
        third_ink.append(round(ink, 4))
    return {
        "status": "ok",
        "width": width,
        "height": height,
        "ink_ratio": round(total_dark / float(width * height), 4),
        "row_bands": int(row_bands),
        "column_groups": int(column_groups),
        "horizontal_rules": int(horizontal_rules),
        "vertical_rules": int(vertical_rules),
        "third_ink": third_ink,
    }


def table_layout_gate_for_row(row: Mapping[str, Any], clean_record: Mapping[str, Any] | None, options: TraceNetTableTileOptions) -> dict[str, Any]:
    clean = clean_record or {}
    path_text = _extract_tiff_path(clean) or _extract_tiff_path(row)
    metrics = _table_layout_metrics_for_image(path_text, max_edge=options.table_layout_probe_edge, threshold=options.threshold)
    reasons: list[str] = []
    score = 0
    if metrics.get("status") != "ok":
        reasons.append(str(metrics.get("reason") or metrics.get("status") or "layout_unavailable"))
        return {"allow": True, "decision": "allow_unverified", "score": 0, "min_score": int(options.min_table_layout_score), "reasons": reasons, "metrics": metrics}
    row_bands = int(metrics.get("row_bands", 0) or 0)
    column_groups = int(metrics.get("column_groups", 0) or 0)
    horizontal_rules = int(metrics.get("horizontal_rules", 0) or 0)
    vertical_rules = int(metrics.get("vertical_rules", 0) or 0)
    ink_ratio = float(metrics.get("ink_ratio", 0.0) or 0.0)
    if row_bands >= 38:
        score += 2; reasons.append(f"dense_rows:{row_bands}")
    elif row_bands >= 30:
        score += 1; reasons.append(f"some_rows:{row_bands}")
    else:
        reasons.append(f"few_rows:{row_bands}")
    if column_groups >= 5:
        score += 2; reasons.append(f"multi_column:{column_groups}")
    elif column_groups >= 3:
        score += 1; reasons.append(f"some_columns:{column_groups}")
    else:
        reasons.append(f"few_columns:{column_groups}")
    if horizontal_rules >= 4 and vertical_rules >= 2:
        score += 3; reasons.append(f"grid_rules:h{horizontal_rules}_v{vertical_rules}")
    if ink_ratio >= 0.10:
        score += 1; reasons.append(f"dense_ink:{ink_ratio:.3f}")
    if row_bands < 35 and column_groups < 4 and horizontal_rules < 4:
        score -= 2; reasons.append("prose_like_layout")
    allow = score >= int(options.min_table_layout_score)
    if not allow:
        reasons.append(f"layout_score_below_threshold:{score}<{options.min_table_layout_score}")
    return {"allow": bool(allow), "decision": "allow" if allow else "skip", "score": int(score), "min_score": int(options.min_table_layout_score), "reasons": reasons, "metrics": metrics}


def apply_table_graph_gate(
    rows: Sequence[Mapping[str, Any]],
    clean_records: Mapping[str, Mapping[str, Any]],
    options: TraceNetTableTileOptions,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not options.table_graph_gate:
        return [dict(row) for row in rows], []
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for row in rows:
        page_id = _page_id_from_record(row)
        gate = table_graph_gate_for_row(row, clean_records.get(page_id, {}), min_score=options.min_table_gate_score)
        row2 = dict(row)
        row2["table_graph_gate"] = gate
        if gate["allow"] and options.table_layout_gate:
            layout_gate = table_layout_gate_for_row(row2, clean_records.get(page_id, {}), options)
            row2["table_layout_gate"] = layout_gate
            if not layout_gate.get("allow"):
                skipped.append(row2)
                continue
        if gate["allow"]:
            selected.append(row2)
        else:
            skipped.append(row2)
    return selected, skipped

# ---------------------------------------------------------------------------
# Build/write outputs
# ---------------------------------------------------------------------------


def select_repair_plan_rows(
    rows: Sequence[Mapping[str, Any]],
    options: TraceNetTableTileOptions,
    clean_records: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    selected_routes = options.selected_routes()
    selected: list[dict[str, Any]] = []
    for row in rows:
        route = _text(row.get("primary_repair_route"))
        if route in selected_routes:
            selected.append(dict(row))
    if clean_records is not None:
        selected, _skipped = apply_table_graph_gate(selected, clean_records, options)
    if options.max_pages is not None and options.max_pages >= 0:
        selected = selected[: options.max_pages]
    return selected


def build_table_tile_graph(records: Sequence[TableTileRecord]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = [
        {
            "id": "trace_net_table_tile_run",
            "type": "table_tile_run",
            "label": "TRACE-Net table crop/tile run",
        }
    ]
    edges: list[dict[str, Any]] = []
    for record in records:
        page_node = f"page:{record.page_id}"
        context_node = f"table_tile_context:{record.page_id}"
        nodes.append({"id": page_node, "type": "page", "page_id": record.page_id})
        nodes.append(
            {
                "id": context_node,
                "type": "table_tile_context",
                "page_id": record.page_id,
                "status": record.status,
                "repair_route": record.repair_route,
                "tile_count": record.tile_count,
                "trust_scope": "table_extraction_prep",
            }
        )
        edges.append({"source": page_node, "target": context_node, "type": "HAS_TABLE_TILE_CONTEXT"})
        edges.append({"source": context_node, "target": "trace_net_table_tile_run", "type": "DERIVED_FROM"})
        for tile in record.tiles:
            tile_node = f"table_tile:{tile['tile_id']}"
            nodes.append(
                {
                    "id": tile_node,
                    "type": "table_tile",
                    "page_id": record.page_id,
                    "tile_index": tile.get("tile_index"),
                    "path": tile.get("path"),
                    "width": tile.get("width"),
                    "height": tile.get("height"),
                }
            )
            edges.append({"source": context_node, "target": tile_node, "type": "HAS_TABLE_TILE"})
    # Deduplicate nodes by id.
    dedup: dict[str, dict[str, Any]] = {}
    for node in nodes:
        dedup[_text(node.get("id"))] = node
    return list(dedup.values()), edges


def build_table_tile_summary(
    records: Sequence[TableTileRecord],
    selected_rows: Sequence[Mapping[str, Any]],
    all_plan_rows: Sequence[Mapping[str, Any]],
    options: TraceNetTableTileOptions,
    graph_nodes: Sequence[Mapping[str, Any]],
    graph_edges: Sequence[Mapping[str, Any]],
    skipped_rows: Sequence[Mapping[str, Any]] | None = None,
    route_selected_rows: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    status_counts = Counter(r.status for r in records)
    route_counts = Counter(r.repair_route for r in records)
    priority_counts = Counter(r.repair_priority for r in records)
    ok_records = status_counts.get("ok", 0)
    error_records = sum(count for status, count in status_counts.items() if status not in {"ok"})
    tile_images = sum(r.tile_count for r in records)
    crop_ratios = [r.crop_area_ratio for r in records if r.crop_area_ratio > 0]
    avg_crop = round(sum(crop_ratios) / len(crop_ratios), 6) if crop_ratios else 0.0
    skipped_rows = list(skipped_rows or [])
    route_selected_rows = list(route_selected_rows or selected_rows)
    skip_reason_counts = Counter()
    layout_skip_reason_counts = Counter()
    graph_skip_records = 0
    layout_skip_records = 0
    for row in skipped_rows:
        graph_gate = _as_dict(row.get("table_graph_gate"))
        layout_gate = _as_dict(row.get("table_layout_gate"))
        if graph_gate and graph_gate.get("decision") == "skip":
            graph_skip_records += 1
        if layout_gate and layout_gate.get("decision") == "skip":
            layout_skip_records += 1
        for reason in _as_list(graph_gate.get("reasons")):
            reason_text = _text(reason)
            if reason_text:
                skip_reason_counts[reason_text] += 1
        for reason in _as_list(layout_gate.get("reasons")):
            reason_text = _text(reason)
            if reason_text:
                layout_skip_reason_counts[reason_text] += 1
    if not records:
        status = "FAIL"
    elif error_records:
        status = "PARTIAL" if ok_records else "FAIL"
    else:
        status = "OK"
    return {
        "status": status,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "trace_net_table_tile_version": "trace_net_table_tile_v1",
        "repair_plan_records": len(all_plan_rows),
        "route_candidate_pages": len(route_selected_rows),
        "selected_pages": len(selected_rows),
        "records": len(records),
        "table_graph_gate_enabled": bool(options.table_graph_gate),
        "table_graph_gate_min_score": int(options.min_table_gate_score),
        "table_graph_gate_skipped_records": len(skipped_rows),
        "table_graph_gate_graph_skipped_records": graph_skip_records,
        "table_graph_gate_layout_skipped_records": layout_skip_records,
        "table_graph_gate_skip_reason_counts": dict(sorted(skip_reason_counts.items())),
        "table_layout_gate_enabled": bool(options.table_layout_gate),
        "table_layout_gate_min_score": int(options.min_table_layout_score),
        "table_layout_gate_skipped_records": layout_skip_records,
        "table_layout_gate_skip_reason_counts": dict(sorted(layout_skip_reason_counts.items())),
        "ok_records": ok_records,
        "error_records": error_records,
        "missing_image_path_records": status_counts.get("missing_image_path", 0),
        "missing_image_file_records": status_counts.get("missing_image_file", 0),
        "tile_images": tile_images,
        "full_preprocessed_images": sum(1 for r in records if r.full_preprocessed_path),
        "tiles_per_page_requested": options.tiles_per_page,
        "tile_overlap_px": options.tile_overlap_px,
        "max_image_edge": options.max_image_edge,
        "threshold": options.threshold,
        "crop_padding_px": options.crop_padding_px,
        "average_crop_area_ratio": avg_crop,
        "route_counts": dict(sorted(route_counts.items())),
        "priority_counts": dict(sorted(priority_counts.items())),
        "selected_routes": sorted(options.selected_routes()),
        "graph_nodes": len(graph_nodes),
        "graph_edges": len(graph_edges),
    }


def _record_to_md(record: TableTileRecord, paths: TraceNetTableTilePaths) -> str:
    lines = [
        f"## {record.page_id}",
        "",
        f"- status: `{record.status}`",
        f"- route: `{record.repair_route}`",
        f"- priority: `{record.repair_priority}`",
        f"- action: `{record.repair_action}`",
        f"- source_url: {record.source_url or 'none'}",
        f"- tiff_path: `{record.tiff_path or 'none'}`",
        f"- image_exists: `{record.image_exists}`",
    ]
    if record.error:
        lines.append(f"- error: `{record.error}`")
    if record.status == "ok":
        lines.extend(
            [
                f"- original_size: `{record.original_width}x{record.original_height}`",
                f"- processed_size: `{record.processed_width}x{record.processed_height}`",
                f"- crop_box: `{record.crop_box}`",
                f"- crop_size: `{record.crop_width}x{record.crop_height}`",
                f"- crop_area_ratio: `{record.crop_area_ratio}`",
                f"- tile_count: `{record.tile_count}`",
                f"- full_preprocessed: `{record.full_preprocessed_path}`",
            ]
        )
        for tile in record.tiles[:12]:
            lines.append(f"  - tile {tile['tile_index']}: `{tile['path']}` size={tile['width']}x{tile['height']}")
    lines.append("")
    return "\n".join(lines)


def build_review_md(records: Sequence[TableTileRecord], summary: Mapping[str, Any], paths: TraceNetTableTilePaths) -> str:
    lines = [
        "# TRACE-Net table crop/tile review",
        "",
        "This review shows the page crops and table/row-band tiles generated from TRACE-Net table repair routes.",
        "No OCR/model extraction has been run yet; these tiles are the next input for the table extraction route.",
        "",
        "## Summary",
        "",
    ]
    for key in (
        "status",
        "route_candidate_pages",
        "selected_pages",
        "table_graph_gate_enabled",
        "table_graph_gate_skipped_records",
        "table_layout_gate_enabled",
        "table_layout_gate_skipped_records",
        "ok_records",
        "error_records",
        "tile_images",
        "route_counts",
        "average_crop_area_ratio",
    ):
        lines.append(f"- {key}: `{summary.get(key)}`")
    lines.append("")
    for record in records:
        lines.append(_record_to_md(record, paths))
    return "\n".join(lines).rstrip() + "\n"


def build_review_html(records: Sequence[TableTileRecord], summary: Mapping[str, Any], paths: TraceNetTableTilePaths) -> str:
    def img_tag(path_text: str, label: str) -> str:
        if not path_text:
            return ""
        try:
            rel = Path(path_text).relative_to(paths.output_dir).as_posix()
        except Exception:
            rel = Path(path_text).as_posix()
        return f'<figure><img src="{html.escape(rel)}" alt="{html.escape(label)}"><figcaption>{html.escape(label)}</figcaption></figure>'

    cards = []
    for record in records:
        tile_figs = "\n".join(img_tag(_text(tile.get("path")), f"tile {tile.get('tile_index')}") for tile in record.tiles[:12])
        cards.append(
            f"""
<section class="card {html.escape(record.status)}">
  <h2>{html.escape(record.page_id)}</h2>
  <div class="meta">
    <span>status: <b>{html.escape(record.status)}</b></span>
    <span>route: <b>{html.escape(record.repair_route)}</b></span>
    <span>priority: <b>{html.escape(record.repair_priority)}</b></span>
    <span>tiles: <b>{record.tile_count}</b></span>
  </div>
  <p><b>TIFF:</b> <code>{html.escape(record.tiff_path or 'none')}</code></p>
  <p><b>Reason:</b> {html.escape(record.reason or 'none')}</p>
  <p><b>Table graph gate:</b> {html.escape(record.table_gate_decision)} score={record.table_gate_score}; {html.escape(', '.join(record.table_gate_reasons) or 'none')}</p>
  {f'<p class="error"><b>Error:</b> {html.escape(record.error)}</p>' if record.error else ''}
  <div class="images">
    {img_tag(record.full_preprocessed_path, 'full preprocessed crop')}
  </div>
  <details open><summary>Tiles</summary><div class="tile-grid">{tile_figs}</div></details>
</section>
"""
        )
    style = """
<style>
body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:24px;background:#f7f7f8;color:#1f2937}
header,.card{background:white;border:1px solid #ddd;border-radius:12px;padding:16px;margin:0 0 16px 0;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.meta{display:flex;gap:12px;flex-wrap:wrap;margin:8px 0;color:#4b5563}.meta span{background:#f3f4f6;border-radius:999px;padding:4px 10px}
.card.ok{border-left:6px solid #2f855a}.card.error,.card.missing_image_file,.card.missing_image_path{border-left:6px solid #c53030}
.images,.tile-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;align-items:start}
figure{margin:0;border:1px solid #e5e7eb;border-radius:8px;padding:8px;background:#fafafa}img{width:100%;height:auto;display:block;object-fit:contain;max-height:420px}figcaption{font-size:12px;color:#6b7280;margin-top:4px}code{word-break:break-all}.error{color:#991b1b}
</style>
"""
    summary_html = "".join(f"<li><b>{html.escape(str(k))}</b>: {html.escape(str(v))}</li>" for k, v in summary.items() if k in {"status", "route_candidate_pages", "selected_pages", "table_graph_gate_enabled", "table_graph_gate_skipped_records", "table_layout_gate_enabled", "table_layout_gate_skipped_records", "ok_records", "error_records", "tile_images", "route_counts", "average_crop_area_ratio"})
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>TRACE-Net table crop/tile review</title>{style}</head>
<body>
<header>
<h1>TRACE-Net table crop/tile review</h1>
<p>Generated table/row-band tiles for the selected TRACE-Net table repair routes. No OCR/model extraction has run yet.</p>
<ul>{summary_html}</ul>
</header>
{''.join(cards)}
</body></html>
"""


def build_and_write_table_tile_plan(
    paths: TraceNetTableTilePaths,
    options: TraceNetTableTileOptions,
) -> dict[str, Any]:
    repair_rows = read_jsonl(paths.repair_plan)
    clean_records = _clean_records_by_page(paths.clean_records)
    clean_records = _merge_page_card_metadata(clean_records, _page_character_cards_by_page(paths.page_character_cards))
    route_selected_rows = []
    for row in repair_rows:
        route = _text(row.get("primary_repair_route"))
        if route in options.selected_routes():
            route_selected_rows.append(dict(row))
    gated_rows, skipped_rows = apply_table_graph_gate(route_selected_rows, clean_records, options)
    selected_rows = gated_rows
    if options.max_pages is not None and options.max_pages >= 0:
        selected_rows = selected_rows[: options.max_pages]
    records = [build_tile_record(row, clean_records, paths, options) for row in selected_rows]
    nodes, edges = build_table_tile_graph(records)
    summary = build_table_tile_summary(records, selected_rows, repair_rows, options, nodes, edges, skipped_rows=skipped_rows, route_selected_rows=route_selected_rows)
    output = {
        "status": summary["status"],
        "summary": summary,
        "records": [r.to_json() for r in records],
        "skipped_by_table_graph_gate": skipped_rows,
    }
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(paths.tile_plan_jsonl, [r.to_json() for r in records])
    _write_json(paths.tile_plan, output)
    _write_json(paths.summary, summary)
    _write_json(paths.graph_nodes, nodes)
    _write_json(paths.graph_edges, edges)
    paths.review_md.write_text(build_review_md(records, summary, paths), encoding="utf-8")
    paths.review_html.write_text(build_review_html(records, summary, paths), encoding="utf-8")
    if options.open_review:
        try:
            webbrowser.open(paths.review_html.resolve().as_uri())
        except Exception:
            pass
    return output


# ---------------------------------------------------------------------------
# Quality gate
# ---------------------------------------------------------------------------


def build_table_tile_quality(
    paths: TraceNetTableTilePaths,
    min_records: int = 1,
    expect_pages: int | None = None,
    min_ok_records: int = 1,
    min_tile_images: int = 1,
    max_missing_image_records: int | None = 0,
    require_status_ok: bool = True,
) -> dict[str, Any]:
    summary = _read_json(paths.summary, {}) or {}
    records = read_jsonl(paths.tile_plan_jsonl)
    graph_nodes = _read_json(paths.graph_nodes, []) or []
    graph_edges = _read_json(paths.graph_edges, []) or []
    present = paths.summary.exists() and paths.tile_plan_jsonl.exists()
    status = _text(summary.get("status"), "missing").lower()
    missing = int(summary.get("missing_image_path_records", 0) or 0) + int(summary.get("missing_image_file_records", 0) or 0)
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    add("table_tile_artifacts_present", present, f"summary={paths.summary.exists()}; plan_jsonl={paths.tile_plan_jsonl.exists()}.")
    add("table_tile_status", (status == "ok") if require_status_ok else status in {"ok", "partial"}, f"status={summary.get('status')} require_status_ok={require_status_ok}.")
    add("table_tile_records", len(records) >= min_records, f"records={len(records)}; minimum={min_records}.")
    if expect_pages is not None:
        add("table_tile_expected_pages", int(summary.get("selected_pages", 0) or 0) == expect_pages, f"selected_pages={summary.get('selected_pages')}; expected={expect_pages}.")
    add("table_tile_ok_records", int(summary.get("ok_records", 0) or 0) >= min_ok_records, f"ok_records={summary.get('ok_records')}; minimum={min_ok_records}.")
    add("table_tile_images", int(summary.get("tile_images", 0) or 0) >= min_tile_images, f"tile_images={summary.get('tile_images')}; minimum={min_tile_images}.")
    if max_missing_image_records is not None:
        add("table_tile_missing_images", missing <= max_missing_image_records, f"missing_image_records={missing}; max={max_missing_image_records}.")
    add("table_tile_graph_nodes", isinstance(graph_nodes, list) and len(graph_nodes) >= max(1, int(summary.get("ok_records", 0) or 0)), f"graph_nodes={len(graph_nodes) if isinstance(graph_nodes, list) else 0}.")
    add("table_tile_graph_edges", isinstance(graph_edges, list) and len(graph_edges) >= int(summary.get("ok_records", 0) or 0), f"graph_edges={len(graph_edges) if isinstance(graph_edges, list) else 0}.")

    quality_summary = {
        "table_tile_summary_present": paths.summary.exists(),
        "table_tile_plan_present": paths.tile_plan_jsonl.exists(),
        "table_tile_status": summary.get("status"),
        "table_tile_records": len(records),
        "table_tile_selected_pages": summary.get("selected_pages", 0),
        "table_tile_ok_records": summary.get("ok_records", 0),
        "table_tile_error_records": summary.get("error_records", 0),
        "table_tile_missing_image_records": missing,
        "table_tile_images": summary.get("tile_images", 0),
        "table_tile_full_preprocessed_images": summary.get("full_preprocessed_images", 0),
        "table_tile_route_candidate_pages": summary.get("route_candidate_pages", summary.get("selected_pages", 0)),
        "table_tile_route_counts": summary.get("route_counts", {}),
        "table_tile_table_graph_gate_enabled": summary.get("table_graph_gate_enabled", False),
        "table_tile_table_graph_gate_skipped_records": summary.get("table_graph_gate_skipped_records", 0),
        "table_tile_table_graph_gate_skip_reason_counts": summary.get("table_graph_gate_skip_reason_counts", {}),
        "table_tile_table_layout_gate_enabled": summary.get("table_layout_gate_enabled", False),
        "table_tile_table_layout_gate_skipped_records": summary.get("table_layout_gate_skipped_records", 0),
        "table_tile_table_layout_gate_skip_reason_counts": summary.get("table_layout_gate_skip_reason_counts", {}),
        "table_tile_average_crop_area_ratio": summary.get("average_crop_area_ratio", 0),
        "table_tile_graph_nodes": len(graph_nodes) if isinstance(graph_nodes, list) else 0,
        "table_tile_graph_edges": len(graph_edges) if isinstance(graph_edges, list) else 0,
        "table_tile_summary_path": paths.summary.as_posix(),
        "table_tile_plan_jsonl_path": paths.tile_plan_jsonl.as_posix(),
        "table_tile_review_html_path": paths.review_html.as_posix(),
    }
    return {
        "status": "OK" if all(c["ok"] for c in checks) else "FAIL",
        "summary": quality_summary,
        "checks": checks,
    }


def write_table_tile_quality(quality: Mapping[str, Any], paths: TraceNetTableTilePaths) -> Path:
    _write_json(paths.quality, quality)
    return paths.quality


def print_table_tile_export(result: Mapping[str, Any], paths: TraceNetTableTilePaths) -> None:
    summary = _as_dict(result.get("summary"))
    print("TRACE-Net table crop/tile executor")
    print(f"  Status: {summary.get('status')}")
    print(f"  Output dir: {paths.output_dir}")
    print("  Summary:")
    for key in (
        "repair_plan_records",
        "route_candidate_pages",
        "selected_pages",
        "records",
        "table_graph_gate_enabled",
        "table_graph_gate_skipped_records",
        "table_layout_gate_enabled",
        "table_layout_gate_skipped_records",
        "ok_records",
        "error_records",
        "missing_image_path_records",
        "missing_image_file_records",
        "tile_images",
        "full_preprocessed_images",
        "route_counts",
        "average_crop_area_ratio",
        "graph_nodes",
        "graph_edges",
    ):
        print(f"    {key}: {summary.get(key)}")
    records = _as_list(result.get("records"))
    if records:
        print("  Sample tile records:")
        for rec in records[:8]:
            print(f"    {rec.get('page_id')} | {rec.get('status')} | route={rec.get('repair_route')} | tiles={rec.get('tile_count')} | tiff={rec.get('tiff_path')}")
    print("Files written:")
    print(f"  plan: {paths.tile_plan}")
    print(f"  plan_jsonl: {paths.tile_plan_jsonl}")
    print(f"  summary: {paths.summary}")
    print(f"  graph_nodes: {paths.graph_nodes}")
    print(f"  graph_edges: {paths.graph_edges}")
    print(f"  review_html: {paths.review_html}")


def print_table_tile_quality(quality: Mapping[str, Any]) -> None:
    print("TRACE-Net table crop/tile quality gate")
    print(f"  Status: {quality.get('status')}")
    print("  Summary:")
    for key, value in _as_dict(quality.get("summary")).items():
        print(f"    {key}: {value}")
    print("  Checks:")
    for check in _as_list(quality.get("checks")):
        status = "OK" if check.get("ok") else "FAIL"
        print(f"    {status} {check.get('name')}: {check.get('detail')}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_routes(value: str | None) -> tuple[str, ...]:
    if not value:
        return (TABLE_ROUTE_HIGH,)
    routes = []
    for piece in value.split(","):
        text = piece.strip()
        if text:
            routes.append(_canonical_route(text))
    return tuple(routes or [TABLE_ROUTE_HIGH])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run TRACE-Net table crop/tile executor v1.")
    parser.add_argument("--visual-text-dir", default=str(DEFAULT_VISUAL_TEXT_DIR))
    parser.add_argument("--trace-net-dir", default=str(DEFAULT_TRACE_NET_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--entity-trait-dir", default=str(DEFAULT_ENTITY_TRAIT_DIR), help="Directory containing page_character_cards.json for graph-aware table gating.")
    parser.add_argument("--routes", default="high", help="Comma-separated routes/aliases: high,medium,legacy,all or full route names. Default: high")
    parser.add_argument("--include-medium", action="store_true", help="Also include medium-priority table routes.")
    parser.add_argument("--include-legacy", action="store_true", help="Also include legacy generic table routes.")
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--expect-pages", type=int, default=None)
    parser.add_argument("--tiles-per-page", type=int, default=6)
    parser.add_argument("--tile-overlap-px", type=int, default=48)
    parser.add_argument("--threshold", type=int, default=245)
    parser.add_argument("--crop-padding-px", type=int, default=24)
    parser.add_argument("--max-image-edge", type=int, default=1800)
    parser.add_argument("--no-table-graph-gate", action="store_true", help="Disable graph-aware table gating and crop every selected table-route page.")
    parser.add_argument("--min-table-gate-score", type=int, default=2, help="Minimum graph table score needed before a selected route page is tiled. Default: 2")
    parser.add_argument("--no-table-layout-gate", action="store_true", help="Disable image-layout table gating after graph gating.")
    parser.add_argument("--min-table-layout-score", type=int, default=3, help="Minimum image-layout table score needed before tiling. Default: 3")
    parser.add_argument("--table-layout-probe-edge", type=int, default=1200, help="Max edge used for lightweight layout-gate probing. Default: 1200")
    parser.add_argument("--no-overwrite", action="store_true")
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args(argv)

    paths = TraceNetTableTilePaths(
        visual_text_dir=Path(args.visual_text_dir),
        trace_net_dir=Path(args.trace_net_dir),
        output_dir=Path(args.output_dir),
        entity_trait_dir=Path(args.entity_trait_dir),
    )
    options = TraceNetTableTileOptions(
        routes=_parse_routes(args.routes),
        include_medium=bool(args.include_medium),
        include_legacy=bool(args.include_legacy),
        max_pages=args.max_pages,
        overwrite=not bool(args.no_overwrite),
        tiles_per_page=args.tiles_per_page,
        tile_overlap_px=args.tile_overlap_px,
        threshold=args.threshold,
        crop_padding_px=args.crop_padding_px,
        max_image_edge=args.max_image_edge,
        expected_pages=args.expect_pages,
        open_review=bool(args.open),
        table_graph_gate=not bool(args.no_table_graph_gate),
        min_table_gate_score=int(args.min_table_gate_score),
        table_layout_gate=not bool(args.no_table_layout_gate),
        min_table_layout_score=int(args.min_table_layout_score),
        table_layout_probe_edge=int(args.table_layout_probe_edge),
    )
    result = build_and_write_table_tile_plan(paths, options)
    print_table_tile_export(result, paths)
    status = _as_dict(result.get("summary")).get("status")
    return 0 if status in {"OK", "PARTIAL"} else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
