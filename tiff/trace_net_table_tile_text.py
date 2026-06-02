"""TRACE-Net table tile text extractor v1.

This module is the first text-extraction executor after the TRACE-Net table
crop/tile stage. It is intentionally conservative and dependency-light:

- reads table_tile_plan.jsonl created by the table crop/tile executor;
- extracts text per tile through a provider interface;
- supports a dependency-free page_ocr baseline that maps existing page OCR onto
  table tiles, plus mock/planned providers for smoke tests;
- detects part-number-like strings and validates them against the local part tree
  when available;
- writes records, corpus, review HTML, graph overlay, and quality summaries.

It does not attempt final row/cell reconstruction yet. The next TRACE-Net step
can consume these tile text records to build row candidates and table trust
traits.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import webbrowser
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence

DEFAULT_EXPORT_DIR = Path("local_data/organization/export")
DEFAULT_TABLE_DIR = Path("local_data/organization/table_extraction")
DEFAULT_OUTPUT_DIR = DEFAULT_TABLE_DIR / "table_tile_text"

RECORDS_FILE = "table_tile_text_records.jsonl"
SUMMARY_FILE = "table_tile_text_summary.json"
CORPUS_MD_FILE = "table_tile_text_corpus.md"
GRAPH_NODES_FILE = "table_tile_text_graph_nodes.json"
GRAPH_EDGES_FILE = "table_tile_text_graph_edges.json"
REVIEW_MD_FILE = "table_tile_text_review.md"
REVIEW_HTML_FILE = "table_tile_text_review.html"
QUALITY_FILE = "table_tile_text_quality.json"

# Conservative technical-part regex. We collect these as part-like strings first,
# then remove ATA-looking codes from the canonical part_number list.
PART_LIKE_RE = re.compile(
    r"\b(?:[A-Z]{1,4}\d{2,6}[A-Z0-9.-]*|\d{2,4}[A-Z]{0,3}[-.][A-Z0-9]{2,10}(?:[-.][A-Z0-9]{1,10}){0,3}|\d{2,4}TP\d{3,8}[A-Z0-9.\-]*)\b",
    re.I,
)
ATA_RE = re.compile(r"^\d{2}-\d{2}-\d{2}$")
ONLY_NUMERIC_DASH_RE = re.compile(r"^\d+(?:-\d+)+$")

OCR_KEYS = (
    "ocr_path",
    "source_ocr_path",
    "local_ocr_path",
    "ocr_file_path",
    "ocr_text_path",
    "ocr_file",
)
TIFF_KEYS = (
    "tiff_path",
    "source_tiff_path",
    "image_path",
    "image_file",
    "local_tiff_path",
    "tiff_file_path",
)
PAGE_ID_KEYS = ("page_id", "id", "page", "node_id", "entity_id")


@dataclass(frozen=True)
class TableTileTextPaths:
    export_dir: Path = DEFAULT_EXPORT_DIR
    table_dir: Path = DEFAULT_TABLE_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    table_tile_plan_path: Path | None = None
    page_index_path: Path | None = None
    part_tree_path: Path | None = None
    records_path: Path | None = None
    summary_path: Path | None = None
    corpus_md_path: Path | None = None
    graph_nodes_path: Path | None = None
    graph_edges_path: Path | None = None
    review_md_path: Path | None = None
    review_html_path: Path | None = None
    quality_path: Path | None = None

    @property
    def table_tile_plan(self) -> Path:
        return self.table_tile_plan_path or (self.table_dir / "table_tile_plan.jsonl")

    @property
    def page_index(self) -> Path:
        return self.page_index_path or (self.export_dir / "page_index.json")

    @property
    def part_tree(self) -> Path:
        return self.part_tree_path or (self.export_dir / "part_tree.json")

    @property
    def records(self) -> Path:
        return self.records_path or (self.output_dir / RECORDS_FILE)

    @property
    def summary(self) -> Path:
        return self.summary_path or (self.output_dir / SUMMARY_FILE)

    @property
    def corpus_md(self) -> Path:
        return self.corpus_md_path or (self.output_dir / CORPUS_MD_FILE)

    @property
    def graph_nodes(self) -> Path:
        return self.graph_nodes_path or (self.output_dir / GRAPH_NODES_FILE)

    @property
    def graph_edges(self) -> Path:
        return self.graph_edges_path or (self.output_dir / GRAPH_EDGES_FILE)

    @property
    def review_md(self) -> Path:
        return self.review_md_path or (self.output_dir / REVIEW_MD_FILE)

    @property
    def review_html(self) -> Path:
        return self.review_html_path or (self.output_dir / REVIEW_HTML_FILE)

    @property
    def quality(self) -> Path:
        return self.quality_path or (self.output_dir / QUALITY_FILE)


@dataclass
class TableTileTextOptions:
    provider: str = "page_ocr"
    model: str = "page-ocr-baseline"
    max_tiles: int | None = None
    max_pages: int | None = None
    page_id: str | None = None
    include_empty: bool = True
    overwrite: bool = True
    expected_records: int | None = None
    open_review: bool = False


@dataclass
class TileTextProviderResult:
    status: str
    text: str = ""
    provider_metadata: dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass
class TableTileTextRecord:
    page_id: str
    tile_id: str
    tile_index: int
    tile_path: str
    status: str
    provider: str
    model: str
    text: str = ""
    text_chars: int = 0
    text_lines: int = 0
    part_like_strings: list[str] = field(default_factory=list)
    part_numbers: list[str] = field(default_factory=list)
    catalog_supported_part_numbers: list[str] = field(default_factory=list)
    unsupported_part_numbers: list[str] = field(default_factory=list)
    source_url: str = ""
    tiff_path: str = ""
    ocr_path: str = ""
    ocr_available: bool = False
    ocr_source: str = ""
    repair_route: str = ""
    repair_priority: str = ""
    trust_tier: str = "C"
    rag_action: str = "exclude_from_rag"
    repair_action: str = "review_tile_text"
    review_action: str = "human_review"
    provider_metadata: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    trace_net_table_tile_text_version: str = "trace_net_table_tile_text_v1"

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


class TileTextProvider(Protocol):
    provider_name: str
    model_name: str

    def extract_tile_text(self, tile: Mapping[str, Any], page_record: Mapping[str, Any], context: Mapping[str, Any]) -> TileTextProviderResult: ...


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


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _page_id_from_record(record: Mapping[str, Any]) -> str:
    for key in PAGE_ID_KEYS:
        value = record.get(key)
        if value:
            text = _text(value)
            return text.split(":", 1)[1] if text.startswith("page:") else text
    return ""


def _first_nested_text(record: Mapping[str, Any], keys: Sequence[str]) -> str:
    candidates: list[Any] = []
    for key in keys:
        candidates.append(record.get(key))
    for parent_key in ("source", "metadata", "page", "page_card", "context", "source_trace", "route_metadata"):
        parent = _as_dict(record.get(parent_key))
        for key in keys:
            candidates.append(parent.get(key))
    for value in candidates:
        text = _text(value)
        if text:
            return text
    return ""


def _extract_tiff_path(record: Mapping[str, Any]) -> str:
    return _first_nested_text(record, TIFF_KEYS)


def _extract_ocr_path(record: Mapping[str, Any]) -> str:
    return _first_nested_text(record, OCR_KEYS)


def _extract_source_url(record: Mapping[str, Any]) -> str:
    return _first_nested_text(record, ("source_url", "url", "rescarta_url", "source_link"))


def _resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.exists():
        return path
    alt = Path(path_text.replace("\\", "/"))
    if alt.exists():
        return alt
    return path


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _iter_values(value: Any) -> Iterable[Any]:
    if isinstance(value, Mapping):
        for k, v in value.items():
            yield k
            yield from _iter_values(v)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_values(item)
    else:
        yield value


def _normalize_part(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def extract_part_like_strings(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for match in PART_LIKE_RE.finditer(text or ""):
        token = match.group(0).strip(".,;:()[]{}")
        if len(token) < 4:
            continue
        key = token.upper()
        if key not in seen:
            seen.add(key)
            found.append(token)
    return found


def filter_part_numbers(part_like: Sequence[str]) -> list[str]:
    parts: list[str] = []
    seen: set[str] = set()
    for token in part_like:
        text = token.upper().strip()
        if ATA_RE.match(text):
            continue
        # Exclude short numeric page/chapter markers like 1-2 or 20-30 unless they include letters.
        if ONLY_NUMERIC_DASH_RE.match(text) and len(text) <= 8:
            continue
        if text not in seen:
            seen.add(text)
            parts.append(text)
    return parts


def _catalog_part_set(part_tree: Any) -> set[str]:
    parts: set[str] = set()
    for value in _iter_values(part_tree):
        text = _text(value)
        if not text:
            continue
        for token in extract_part_like_strings(text):
            parts.add(_normalize_part(token))
    return parts


def _load_page_index(path: Path) -> dict[str, dict[str, Any]]:
    data = _read_json(path, {})
    pages: dict[str, dict[str, Any]] = {}
    if isinstance(data, Mapping):
        if "pages" in data and isinstance(data["pages"], list):
            iterable = data["pages"]
        elif "page_index" in data and isinstance(data["page_index"], list):
            iterable = data["page_index"]
        else:
            iterable = []
            for key, value in data.items():
                if isinstance(value, Mapping):
                    row = dict(value)
                    row.setdefault("page_id", key)
                    iterable.append(row)
    elif isinstance(data, list):
        iterable = data
    else:
        iterable = []
    for item in iterable:
        if not isinstance(item, Mapping):
            continue
        row = dict(item)
        page_id = _page_id_from_record(row)
        if page_id:
            pages[page_id] = row
    return pages


def _candidate_ocr_paths(page_id: str, tile_record: Mapping[str, Any], page_index_record: Mapping[str, Any]) -> list[Path]:
    candidates: list[Path] = []
    for record in (tile_record, page_index_record):
        ocr_path = _extract_ocr_path(record)
        if ocr_path:
            candidates.append(_resolve_path(ocr_path))
    tiff_path = _extract_tiff_path(tile_record) or _extract_tiff_path(page_index_record)
    if tiff_path:
        tiff = _resolve_path(tiff_path)
        stem = tiff.stem
        candidates.append(tiff.with_suffix(".txt"))
        # Common ResCarta export shape: .../pages/000010_00000010.tif -> .../ocr/000010_00000010.txt
        parts = list(tiff.parts)
        for i, part in enumerate(parts):
            if part.lower() == "pages":
                ocr_parts = parts[:]
                ocr_parts[i] = "ocr"
                candidates.append(Path(*ocr_parts).with_suffix(".txt"))
                candidates.append(Path(*ocr_parts).with_name(stem.split("_")[0] + ".txt"))
                break
        # Limited local search in the document folder for page sequence.
        page_match = re.search(r"p(\d{6})$", page_id)
        if page_match:
            seq = page_match.group(1).lstrip("0") or "0"
            seq6 = page_match.group(1)
            root = tiff.parent.parent if tiff.parent.name.lower() == "pages" else tiff.parent
            if root.exists():
                try:
                    for pattern in (f"*{seq6}*.txt", f"*{seq.zfill(3)}*.txt", f"*{seq}*.txt"):
                        candidates.extend(list(root.rglob(pattern))[:10])
                except Exception:
                    pass
    # Deduplicate while preserving order.
    seen: set[str] = set()
    result: list[Path] = []
    for path in candidates:
        key = path.as_posix().lower()
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def _read_page_ocr(page_id: str, tile_record: Mapping[str, Any], page_index_record: Mapping[str, Any]) -> tuple[str, str, bool]:
    for path in _candidate_ocr_paths(page_id, tile_record, page_index_record):
        if path.exists():
            text = _read_text_file(path)
            return text, path.as_posix(), bool(text.strip())
    return "", "", False


def _split_text_for_tile(page_text: str, tile_index: int, total_tiles: int) -> str:
    lines = [line.rstrip() for line in (page_text or "").splitlines() if line.strip()]
    if not lines:
        return ""
    total = max(1, total_tiles)
    idx = max(1, int(tile_index or 1))
    start = int((idx - 1) * len(lines) / total)
    end = int(idx * len(lines) / total)
    # Include a small overlap to mimic image tile overlap and preserve row context.
    start = max(0, start - 2)
    end = min(len(lines), max(end + 2, start + 1))
    return "\n".join(lines[start:end]).strip()


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


class PlannedTileTextProvider:
    provider_name = "planned"
    model_name = "none"

    def extract_tile_text(self, tile: Mapping[str, Any], page_record: Mapping[str, Any], context: Mapping[str, Any]) -> TileTextProviderResult:
        return TileTextProviderResult(
            status="planned",
            text="Planned table tile OCR/text extraction record. No extraction provider was run.",
            provider_metadata={"planned": True},
        )


class MockTileTextProvider:
    provider_name = "mock"
    model_name = "mock-table-tile-text-v1"

    def extract_tile_text(self, tile: Mapping[str, Any], page_record: Mapping[str, Any], context: Mapping[str, Any]) -> TileTextProviderResult:
        page_id = _text(context.get("page_id"), "unknown")
        tile_index = int(tile.get("tile_index", 1) or 1)
        synthetic_part = f"120-{tile_index:05d}-001"
        text = (
            f"Mock table tile text for {page_id} tile {tile_index}.\n"
            "| item | part number | nomenclature | qty |\n"
            f"| {tile_index} | {synthetic_part} | MOCK TILE COMPONENT | 1 |"
        )
        return TileTextProviderResult(status="ok", text=text, provider_metadata={"synthetic": True})


class PageOcrTileTextProvider:
    provider_name = "page_ocr"
    model_name = "page-ocr-baseline"

    def extract_tile_text(self, tile: Mapping[str, Any], page_record: Mapping[str, Any], context: Mapping[str, Any]) -> TileTextProviderResult:
        page_text = _text(context.get("page_ocr_text"))
        tile_index = int(tile.get("tile_index", 1) or 1)
        total_tiles = int(context.get("total_tiles", 1) or 1)
        if not page_text.strip():
            return TileTextProviderResult(
                status="empty",
                text="",
                provider_metadata={"ocr_available": False, "method": "page_ocr_line_band"},
            )
        text = _split_text_for_tile(page_text, tile_index=tile_index, total_tiles=total_tiles)
        return TileTextProviderResult(
            status="ok" if text else "empty",
            text=text,
            provider_metadata={
                "ocr_available": True,
                "method": "page_ocr_line_band",
                "tile_index": tile_index,
                "total_tiles": total_tiles,
            },
        )


def _make_provider(options: TableTileTextOptions) -> TileTextProvider:
    provider = _norm(options.provider)
    if provider in {"planned", "plan"}:
        return PlannedTileTextProvider()
    if provider == "mock":
        return MockTileTextProvider()
    if provider in {"page_ocr", "ocr", "ocr_file", "existing_ocr"}:
        return PageOcrTileTextProvider()
    raise ValueError(f"Unsupported table tile text provider: {options.provider}")


# ---------------------------------------------------------------------------
# Record building
# ---------------------------------------------------------------------------


def _iter_tiles_from_plan(plan_rows: Sequence[Mapping[str, Any]], options: TableTileTextOptions) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    seen_pages: set[str] = set()
    for row in plan_rows:
        if _text(row.get("status")).lower() != "ok":
            continue
        page_id = _page_id_from_record(row)
        if options.page_id and page_id != options.page_id:
            continue
        if options.max_pages is not None and page_id not in seen_pages and len(seen_pages) >= options.max_pages:
            continue
        if page_id:
            seen_pages.add(page_id)
        for tile in _as_list(row.get("tiles")):
            if isinstance(tile, Mapping):
                rows.append((dict(row), dict(tile)))
                if options.max_tiles is not None and len(rows) >= options.max_tiles:
                    return rows
    return rows


def build_tile_text_record(
    page_record: Mapping[str, Any],
    tile: Mapping[str, Any],
    provider: TileTextProvider,
    page_index: Mapping[str, Mapping[str, Any]],
    catalog_parts: set[str],
) -> TableTileTextRecord:
    page_id = _page_id_from_record(page_record)
    tile_id = _text(tile.get("tile_id"), f"{page_id}_tile_{tile.get('tile_index', 'unknown')}")
    tile_index = int(tile.get("tile_index", 0) or 0)
    page_index_record = page_index.get(page_id, {})
    page_ocr_text, ocr_path, ocr_available = _read_page_ocr(page_id, page_record, page_index_record)
    context = {
        "page_id": page_id,
        "page_ocr_text": page_ocr_text,
        "ocr_path": ocr_path,
        "ocr_available": ocr_available,
        "total_tiles": max(1, int(page_record.get("tile_count", 0) or len(_as_list(page_record.get("tiles"))) or 1)),
    }
    try:
        result = provider.extract_tile_text(tile, page_record, context)
    except Exception as exc:  # pragma: no cover - defensive provider boundary
        result = TileTextProviderResult(status="error", error=str(exc), provider_metadata={})

    text = result.text or ""
    part_like = extract_part_like_strings(text)
    part_numbers = filter_part_numbers(part_like)
    supported: list[str] = []
    unsupported: list[str] = []
    for part in part_numbers:
        if _normalize_part(part) in catalog_parts:
            supported.append(part)
        else:
            unsupported.append(part)

    status = _text(result.status, "empty").lower()
    if status == "ok" and not text.strip():
        status = "empty"
    if status == "planned":
        trust = "C"
        rag = "exclude_until_table_text_exists"
        repair = "run_table_tile_ocr"
    elif status == "ok":
        trust = "B" if text.strip() else "C"
        rag = "include_as_derived_context" if text.strip() else "exclude_until_table_text_exists"
        repair = "reconstruct_table_rows" if text.strip() else "run_table_tile_ocr"
    elif status == "empty":
        trust = "C"
        rag = "exclude_until_table_text_exists"
        repair = "run_table_tile_ocr"
    else:
        trust = "D"
        rag = "exclude_from_rag"
        repair = "retry_or_review_tile_ocr"

    return TableTileTextRecord(
        page_id=page_id,
        tile_id=tile_id,
        tile_index=tile_index,
        tile_path=_text(tile.get("path")),
        status=status,
        provider=provider.provider_name,
        model=provider.model_name,
        text=text,
        text_chars=len(text),
        text_lines=len([line for line in text.splitlines() if line.strip()]),
        part_like_strings=part_like,
        part_numbers=part_numbers,
        catalog_supported_part_numbers=supported,
        unsupported_part_numbers=unsupported,
        source_url=_extract_source_url(page_record) or _extract_source_url(page_index_record),
        tiff_path=_extract_tiff_path(page_record) or _extract_tiff_path(page_index_record),
        ocr_path=ocr_path,
        ocr_available=ocr_available,
        ocr_source="page_ocr" if ocr_available else "missing_or_empty",
        repair_route=_text(page_record.get("repair_route")),
        repair_priority=_text(page_record.get("repair_priority")),
        trust_tier=trust,
        rag_action=rag,
        repair_action=repair,
        review_action="none" if trust == "B" else "human_review",
        provider_metadata=result.provider_metadata,
        error=result.error,
    )


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


def build_table_tile_text_graph(records: Sequence[TableTileTextRecord]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = [
        {"id": "trace_net_table_tile_text_run", "type": "table_tile_text_run", "label": "TRACE-Net table tile text extraction"}
    ]
    edges: list[dict[str, Any]] = []
    for record in records:
        page_node = f"page:{record.page_id}"
        context_node = f"table_tile_text_context:{record.page_id}"
        tile_text_node = f"table_tile_text:{record.tile_id}"
        nodes.append({"id": page_node, "type": "page", "page_id": record.page_id})
        nodes.append({"id": context_node, "type": "table_tile_text_context", "page_id": record.page_id})
        nodes.append(
            {
                "id": tile_text_node,
                "type": "table_tile_text",
                "page_id": record.page_id,
                "tile_id": record.tile_id,
                "status": record.status,
                "trust_tier": record.trust_tier,
                "rag_action": record.rag_action,
                "text_chars": record.text_chars,
                "part_numbers": record.part_numbers,
            }
        )
        edges.append({"source": page_node, "target": context_node, "type": "HAS_TABLE_TILE_TEXT_CONTEXT"})
        edges.append({"source": context_node, "target": tile_text_node, "type": "HAS_TABLE_TILE_TEXT"})
        edges.append({"source": tile_text_node, "target": "trace_net_table_tile_text_run", "type": "DERIVED_FROM"})
        for part in record.part_numbers[:20]:
            part_node = f"part_candidate:{_slug(part)}"
            nodes.append({"id": part_node, "type": "part_candidate", "label": part, "normalized_part": _normalize_part(part)})
            edges.append({"source": tile_text_node, "target": part_node, "type": "MENTIONS_PART_CANDIDATE"})
    dedup: dict[str, dict[str, Any]] = {}
    for node in nodes:
        node_id = _text(node.get("id"))
        if node_id:
            dedup[node_id] = node
    return list(dedup.values()), edges


def build_table_tile_text_summary(
    records: Sequence[TableTileTextRecord],
    tile_pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    options: TableTileTextOptions,
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    status_counts = Counter(r.status for r in records)
    trust_counts = Counter(r.trust_tier for r in records)
    rag_counts = Counter(r.rag_action for r in records)
    pages = {r.page_id for r in records if r.page_id}
    ok_records = status_counts.get("ok", 0)
    error_records = status_counts.get("error", 0)
    if not records:
        status = "FAIL"
    elif error_records and ok_records:
        status = "PARTIAL"
    elif error_records:
        status = "FAIL"
    else:
        status = "OK"
    part_number_records = sum(1 for r in records if r.part_numbers)
    catalog_supported_records = sum(1 for r in records if r.catalog_supported_part_numbers)
    return {
        "status": status,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "trace_net_table_tile_text_version": "trace_net_table_tile_text_v1",
        "provider": options.provider,
        "model": options.model,
        "records": len(records),
        "selected_tiles": len(tile_pairs),
        "pages": len(pages),
        "ok_records": ok_records,
        "planned_records": status_counts.get("planned", 0),
        "empty_records": status_counts.get("empty", 0),
        "error_records": error_records,
        "tile_text_char_total": sum(r.text_chars for r in records),
        "tile_text_avg_chars": round(sum(r.text_chars for r in records) / max(1, len(records)), 2),
        "tile_text_line_total": sum(r.text_lines for r in records),
        "part_number_records": part_number_records,
        "part_numbers_total": sum(len(r.part_numbers) for r in records),
        "catalog_supported_part_number_records": catalog_supported_records,
        "catalog_supported_part_numbers_total": sum(len(r.catalog_supported_part_numbers) for r in records),
        "unsupported_part_numbers_total": sum(len(r.unsupported_part_numbers) for r in records),
        "trust_tier_counts": dict(sorted(trust_counts.items())),
        "rag_action_counts": dict(sorted(rag_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "graph_nodes": len(nodes),
        "graph_edges": len(edges),
    }


def _record_md(record: TableTileTextRecord, full: bool = False) -> str:
    lines = [
        f"## {record.page_id} / tile {record.tile_index}",
        "",
        f"- status: `{record.status}`",
        f"- provider: `{record.provider}`",
        f"- trust_tier: `{record.trust_tier}`",
        f"- rag_action: `{record.rag_action}`",
        f"- tile_path: `{record.tile_path}`",
        f"- ocr_path: `{record.ocr_path or 'none'}`",
        f"- part_numbers: {', '.join(record.part_numbers) if record.part_numbers else 'none'}",
        f"- catalog_supported: {', '.join(record.catalog_supported_part_numbers) if record.catalog_supported_part_numbers else 'none'}",
        "",
        "```text",
        record.text if full else _truncate(record.text, 1200),
        "```",
        "",
    ]
    return "\n".join(lines)


def _truncate(value: str, limit: int = 500) -> str:
    text = value or ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def build_corpus_md(records: Sequence[TableTileTextRecord], summary: Mapping[str, Any]) -> str:
    lines = [
        "# TRACE-Net table tile text corpus",
        "",
        f"Provider: `{summary.get('provider')}`",
        f"Records: `{summary.get('records')}`",
        f"OK records: `{summary.get('ok_records')}`",
        "",
    ]
    for record in records:
        if record.status == "ok" and record.text.strip():
            lines.append(_record_md(record, full=True))
    return "\n".join(lines)


def build_review_md(records: Sequence[TableTileTextRecord], summary: Mapping[str, Any]) -> str:
    lines = [
        "# TRACE-Net table tile text review",
        "",
        "This review shows tile-level text extracted from the table crop/tile artifacts.",
        "",
        "## Summary",
        "",
    ]
    for key in ("status", "provider", "records", "pages", "ok_records", "empty_records", "error_records", "part_number_records", "tile_text_char_total", "trust_tier_counts", "rag_action_counts"):
        lines.append(f"- {key}: `{summary.get(key)}`")
    lines.append("")
    for record in records[:200]:
        lines.append(_record_md(record, full=False))
    return "\n".join(lines)


def build_review_html(records: Sequence[TableTileTextRecord], summary: Mapping[str, Any]) -> str:
    cards = []
    for record in records[:500]:
        text_html = html.escape(_truncate(record.text, 1400))
        part_html = html.escape(", ".join(record.part_numbers) if record.part_numbers else "none")
        supported_html = html.escape(", ".join(record.catalog_supported_part_numbers) if record.catalog_supported_part_numbers else "none")
        img = ""
        if record.tile_path:
            img = f'<img src="{html.escape(record.tile_path)}" alt="tile {record.tile_index}">'
        cards.append(
            f"""
<article class="card tier-{html.escape(record.trust_tier)}">
  <h2>{html.escape(record.page_id)} / tile {record.tile_index}</h2>
  <p><b>Status:</b> {html.escape(record.status)} | <b>Trust:</b> {html.escape(record.trust_tier)} | <b>RAG:</b> {html.escape(record.rag_action)}</p>
  <p><b>Part numbers:</b> {part_html}</p>
  <p><b>Catalog supported:</b> {supported_html}</p>
  <details><summary>Tile image</summary>{img}</details>
  <details open><summary>Extracted text</summary><pre>{text_html}</pre></details>
</article>
"""
        )
    summary_html = "".join(f"<li><b>{html.escape(str(k))}</b>: {html.escape(str(v))}</li>" for k, v in summary.items() if k in {"status", "provider", "records", "pages", "ok_records", "empty_records", "error_records", "part_number_records", "tile_text_char_total", "trust_tier_counts", "rag_action_counts"})
    style = """
<style>
body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:24px;background:#f6f7fb;color:#1f2937}
.card{background:white;border:1px solid #d1d5db;border-left:8px solid #9ca3af;border-radius:10px;padding:14px;margin:16px 0;box-shadow:0 1px 3px #0001}
.tier-A{border-left-color:#16a34a}.tier-B{border-left-color:#2563eb}.tier-C{border-left-color:#f59e0b}.tier-D{border-left-color:#dc2626}
pre{white-space:pre-wrap;background:#111827;color:#f9fafb;padding:12px;border-radius:8px;max-height:420px;overflow:auto}
img{max-width:100%;border:1px solid #d1d5db;background:white}
summary{cursor:pointer;font-weight:600}
</style>
"""
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>TRACE-Net table tile text review</title>{style}</head>
<body>
<h1>TRACE-Net table tile text review</h1>
<ul>{summary_html}</ul>
{''.join(cards)}
</body></html>
"""


def run_table_tile_text_extraction(paths: TableTileTextPaths, options: TableTileTextOptions) -> dict[str, Any]:
    provider = _make_provider(options)
    # Force the provider's actual model into the option-derived summary.
    options.model = provider.model_name
    plan_rows = read_jsonl(paths.table_tile_plan)
    page_index = _load_page_index(paths.page_index)
    part_tree = _read_json(paths.part_tree, {})
    catalog_parts = _catalog_part_set(part_tree)
    tile_pairs = _iter_tiles_from_plan(plan_rows, options)
    records = [build_tile_text_record(page, tile, provider, page_index, catalog_parts) for page, tile in tile_pairs]
    if not options.include_empty:
        records = [r for r in records if r.status != "empty"]
    nodes, edges = build_table_tile_text_graph(records)
    summary = build_table_tile_text_summary(records, tile_pairs, options, nodes, edges)
    output = {
        "summary": summary,
        "records": [r.to_json() for r in records],
    }
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(paths.summary, summary)
    write_jsonl(paths.records, [r.to_json() for r in records])
    paths.corpus_md.write_text(build_corpus_md(records, summary), encoding="utf-8")
    _write_json(paths.graph_nodes, nodes)
    _write_json(paths.graph_edges, edges)
    paths.review_md.write_text(build_review_md(records, summary), encoding="utf-8")
    paths.review_html.write_text(build_review_html(records, summary), encoding="utf-8")
    return output


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_summary(result: Mapping[str, Any], paths: TableTileTextPaths) -> None:
    summary = _as_dict(result.get("summary"))
    print("TRACE-Net table tile text extraction")
    print(f"  Status: {summary.get('status')}")
    print(f"  Provider: {summary.get('provider')}")
    print(f"  Model: {summary.get('model')}")
    print(f"  Output dir: {paths.output_dir}")
    print("  Summary:")
    for key in (
        "records",
        "pages",
        "ok_records",
        "planned_records",
        "empty_records",
        "error_records",
        "tile_text_char_total",
        "tile_text_avg_chars",
        "part_number_records",
        "part_numbers_total",
        "catalog_supported_part_number_records",
        "trust_tier_counts",
        "rag_action_counts",
        "graph_nodes",
        "graph_edges",
    ):
        print(f"    {key}: {summary.get(key)}")
    print("Files written:")
    print(f"  records: {paths.records}")
    print(f"  summary: {paths.summary}")
    print(f"  corpus_md: {paths.corpus_md}")
    print(f"  review_html: {paths.review_html}")
    print(f"  graph_nodes: {paths.graph_nodes}")
    print(f"  graph_edges: {paths.graph_edges}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run TRACE-Net table tile text extraction v1.")
    parser.add_argument("--table-dir", type=Path, default=DEFAULT_TABLE_DIR)
    parser.add_argument("--export-dir", type=Path, default=DEFAULT_EXPORT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--table-tile-plan", type=Path, default=None)
    parser.add_argument("--page-index", type=Path, default=None)
    parser.add_argument("--part-tree", type=Path, default=None)
    parser.add_argument("--provider", choices=["page_ocr", "ocr", "ocr_file", "existing_ocr", "mock", "planned"], default="page_ocr")
    parser.add_argument("--max-tiles", type=int, default=None)
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--page-id", default=None)
    parser.add_argument("--no-empty", action="store_true", help="Drop empty tile records from outputs.")
    parser.add_argument("--expect-records", type=int, default=None)
    parser.add_argument("--open", dest="open_review", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    paths = TableTileTextPaths(
        export_dir=args.export_dir,
        table_dir=args.table_dir,
        output_dir=args.output_dir,
        table_tile_plan_path=args.table_tile_plan,
        page_index_path=args.page_index,
        part_tree_path=args.part_tree,
    )
    options = TableTileTextOptions(
        provider=args.provider,
        max_tiles=args.max_tiles,
        max_pages=args.max_pages,
        page_id=args.page_id,
        include_empty=not args.no_empty,
        expected_records=args.expect_records,
        open_review=args.open_review,
    )
    result = run_table_tile_text_extraction(paths, options)
    _print_summary(result, paths)
    if args.open_review:
        try:
            webbrowser.open(paths.review_html.resolve().as_uri())
        except Exception:
            pass
    status = _as_dict(result.get("summary")).get("status")
    return 0 if status in {"OK", "PARTIAL"} else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
