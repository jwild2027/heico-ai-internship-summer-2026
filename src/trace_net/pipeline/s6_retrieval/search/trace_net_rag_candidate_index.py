"""TRACE-Net RAG candidate indexer v1.

This module converts the TRACE-Net RAG eligibility pools into local,
searchable candidate chunks. It does not embed, call a vector database, or
answer questions. It prepares the safe evidence records for later BM25/vector/
graph retrieval while preserving source traceability metadata.

Inputs default to:
  local_data/organization/trace_net/rag_eligibility/
    rag_eligible_source_evidence.jsonl
    rag_eligible_verified_part_evidence.jsonl
    rag_eligible_derived_context.jsonl

Optional enrichment inputs:
  local_data/organization/export/page_index.json
  local_data/organization/table_extraction/table_tile_text_refined/
    table_tile_text_refined_records.jsonl

Outputs default to:
  local_data/organization/trace_net/rag_candidates/
"""
from __future__ import annotations

import argparse
import html
import json
import re
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_RAG_ELIGIBILITY_DIR = Path("local_data/organization/trace_net/rag_eligibility")
DEFAULT_EXPORT_DIR = Path("local_data/organization/export")
DEFAULT_REFINED_TABLE_DIR = Path("local_data/organization/table_extraction/table_tile_text_refined")
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/rag_candidates")

SOURCE_FILE = "rag_eligible_source_evidence.jsonl"
VERIFIED_PART_FILE = "rag_eligible_verified_part_evidence.jsonl"
DERIVED_FILE = "rag_eligible_derived_context.jsonl"
PAGE_INDEX_FILE = "page_index.json"
REFINED_TABLE_FILE = "table_tile_text_refined_records.jsonl"

ALL_CANDIDATES_FILE = "rag_candidate_chunks.jsonl"
SOURCE_CANDIDATES_FILE = "rag_candidate_source_chunks.jsonl"
SOURCE_TEXT_CANDIDATES_FILE = "rag_candidate_source_text_chunks.jsonl"
VERIFIED_PART_CANDIDATES_FILE = "rag_candidate_verified_part_chunks.jsonl"
DERIVED_CANDIDATES_FILE = "rag_candidate_derived_chunks.jsonl"
SUMMARY_FILE = "rag_candidate_summary.json"
REVIEW_MD_FILE = "rag_candidate_review.md"
REVIEW_HTML_FILE = "rag_candidate_review.html"
GRAPH_NODES_FILE = "rag_candidate_graph_nodes.json"
GRAPH_EDGES_FILE = "rag_candidate_graph_edges.json"
QUALITY_FILE = "rag_candidate_quality.json"

VERSION = "trace_net_rag_candidate_index_v1_2_source_text"
SAFE_BUCKETS = {"source_evidence", "source_text_evidence", "verified_part_evidence", "derived_context"}
TIER_ORDER = {"D": 0, "C": 1, "B": 2, "A": 3}
PART_RE = re.compile(r"\b(?:\d{3}-\d{4,6}-[A-Z0-9]{2,4}|\d{2,4}TP\d{4,8}[A-Z0-9.\-]*|[A-Z]{1,4}\d{2,6}[A-Z0-9.\-]{1,})\b", re.I)


@dataclass(frozen=True)
class RagCandidateIndexPaths:
    rag_dir: Path = DEFAULT_RAG_ELIGIBILITY_DIR
    export_dir: Path = DEFAULT_EXPORT_DIR
    refined_table_dir: Path = DEFAULT_REFINED_TABLE_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    source_evidence_path: Path | None = None
    verified_part_evidence_path: Path | None = None
    derived_context_path: Path | None = None
    page_index_path: Path | None = None
    refined_table_records_path: Path | None = None
    all_candidates_path: Path | None = None
    source_candidates_path: Path | None = None
    source_text_candidates_path: Path | None = None
    verified_part_candidates_path: Path | None = None
    derived_candidates_path: Path | None = None
    summary_path: Path | None = None
    review_md_path: Path | None = None
    review_html_path: Path | None = None
    graph_nodes_path: Path | None = None
    graph_edges_path: Path | None = None
    quality_path: Path | None = None

    @property
    def source_evidence(self) -> Path:
        return self.source_evidence_path or (self.rag_dir / SOURCE_FILE)

    @property
    def verified_part_evidence(self) -> Path:
        return self.verified_part_evidence_path or (self.rag_dir / VERIFIED_PART_FILE)

    @property
    def derived_context(self) -> Path:
        return self.derived_context_path or (self.rag_dir / DERIVED_FILE)

    @property
    def page_index(self) -> Path:
        return self.page_index_path or (self.export_dir / PAGE_INDEX_FILE)

    @property
    def refined_table_records(self) -> Path:
        return self.refined_table_records_path or (self.refined_table_dir / REFINED_TABLE_FILE)

    @property
    def all_candidates(self) -> Path:
        return self.all_candidates_path or (self.output_dir / ALL_CANDIDATES_FILE)

    @property
    def source_candidates(self) -> Path:
        return self.source_candidates_path or (self.output_dir / SOURCE_CANDIDATES_FILE)

    @property
    def source_text_candidates(self) -> Path:
        return self.source_text_candidates_path or (self.output_dir / SOURCE_TEXT_CANDIDATES_FILE)

    @property
    def verified_part_candidates(self) -> Path:
        return self.verified_part_candidates_path or (self.output_dir / VERIFIED_PART_CANDIDATES_FILE)

    @property
    def derived_candidates(self) -> Path:
        return self.derived_candidates_path or (self.output_dir / DERIVED_CANDIDATES_FILE)

    @property
    def summary(self) -> Path:
        return self.summary_path or (self.output_dir / SUMMARY_FILE)

    @property
    def review_md(self) -> Path:
        return self.review_md_path or (self.output_dir / REVIEW_MD_FILE)

    @property
    def review_html(self) -> Path:
        return self.review_html_path or (self.output_dir / REVIEW_HTML_FILE)

    @property
    def graph_nodes(self) -> Path:
        return self.graph_nodes_path or (self.output_dir / GRAPH_NODES_FILE)

    @property
    def graph_edges(self) -> Path:
        return self.graph_edges_path or (self.output_dir / GRAPH_EDGES_FILE)

    @property
    def quality(self) -> Path:
        return self.quality_path or (self.output_dir / QUALITY_FILE)


@dataclass
class RagCandidateIndexOptions:
    open_report: bool = False
    max_samples: int = 40
    max_text_chars: int = 4000
    include_excluded: bool = False
    include_source_text: bool = True
    max_source_text_chars: int = 6000
    min_source_text_chars: int = 20


# ---------------------------------------------------------------------------
# IO/helpers
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(row, Mapping):
                rows.append(dict(row))
    return rows


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), sort_keys=True, ensure_ascii=False) + "\n")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    out = str(value).strip()
    return out if out else default


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _count(values: Iterable[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items()))


def _slug(value: Any) -> str:
    out = re.sub(r"[^a-z0-9]+", "_", _text(value).lower()).strip("_")
    return out or "unknown"


def _clip(text: str, max_chars: int) -> str:
    text = _text(text)
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 1)].rstrip() + "…"


def _read_text_file(path_text: str, max_chars: int = 6000) -> str:
    path_text = _text(path_text)
    if not path_text:
        return ""
    try:
        path = Path(path_text)
        if path.exists() and path.is_file():
            return _clip(path.read_text(encoding="utf-8", errors="replace"), max_chars)
    except Exception:
        return ""
    return ""


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _text(value).strip(" ,.;:()[]{}\"'")
        if not text:
            continue
        key = text.upper()
        if key not in seen:
            seen.add(key)
            result.append(text)
    return result


# ---------------------------------------------------------------------------
# Enrichment indexes
# ---------------------------------------------------------------------------


def _index_pages(page_index: Any) -> dict[str, dict[str, Any]]:
    pages: dict[str, dict[str, Any]] = {}

    def add(row: Any, fallback_id: str = "") -> None:
        if not isinstance(row, Mapping):
            return
        data = dict(row)
        page_id = _text(data.get("page_id") or data.get("id") or data.get("node_id") or fallback_id)
        if page_id:
            pages[page_id] = data

    if isinstance(page_index, list):
        for row in page_index:
            add(row)
    elif isinstance(page_index, Mapping):
        for key in ("pages", "page_cards", "records", "items"):
            value = page_index.get(key)
            if isinstance(value, list):
                for row in value:
                    add(row)
        # Also support {page_id: {...}} maps.
        for key, value in page_index.items():
            if isinstance(value, Mapping):
                add(value, fallback_id=str(key))
    return pages


def _normal_join_key(value: Any) -> str:
    """Normalize record/tile IDs so Evidence Consensus IDs can join tile records.

    Real Stage 5 derived-context IDs often look like::

        table_tile_text_refined:t_p_120_1176_p000003:tile_t_p_120_1176_p000003_tile_001

    while refined tile-text records usually use::

        t_p_120_1176_p000003_tile_001

    This helper removes graph/context prefixes and the extra ``tile_`` wrapper
    without changing the actual page/tile identity.
    """
    text = _text(value)
    if not text:
        return ""
    text = text.strip()
    if ":" in text:
        text = text.split(":")[-1]
    for prefix in (
        "table_tile_text_refined_",
        "table_tile_text_",
        "table_tile_",
    ):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    if text.startswith("tile_t_p_"):
        text = text[len("tile_") :]
    return text.strip()


def _tile_index_from_text(value: Any) -> int | None:
    text = _text(value)
    match = re.search(r"(?:^|[_:\-])tile[_:\-]?(\d{1,4})(?:\D|$)", text, re.I)
    if not match:
        match = re.search(r"(?:^|[_:\-])(\d{3})(?:\D|$)", text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def _candidate_tile_ids_from_text(value: Any) -> list[str]:
    text = _text(value)
    if not text:
        return []
    candidates: list[str] = []
    # Match normal tile IDs and the Stage 5 wrapped tile IDs.
    for match in re.finditer(r"(?:tile_)?(t_p_[A-Za-z0-9_]+_p\d{6}_tile_\d{3})", text):
        candidates.append(match.group(1))
    # Also match shorter generic page IDs used in unit tests.
    for match in re.finditer(r"(?:tile_)?([A-Za-z0-9]+_tile_\d{1,4})", text):
        candidates.append(match.group(1))
    normalized = _normal_join_key(text)
    if normalized:
        candidates.append(normalized)
    return _unique(candidates)


def _record_key_candidates(row: Mapping[str, Any]) -> list[str]:
    values = [
        row.get("source_record_id"),
        row.get("record_id"),
        row.get("eligibility_id"),
        row.get("candidate_id"),
        row.get("chunk_id"),
        row.get("tile_id"),
        row.get("source_tile_id"),
    ]
    out: list[str] = []
    page_id = _text(row.get("page_id"))
    tile_index = None
    for value in values:
        text = _text(value)
        if not text:
            continue
        out.append(text)
        out.append(text.split(":")[-1])
        out.extend(_candidate_tile_ids_from_text(text))
        idx = _tile_index_from_text(text)
        if idx is not None:
            tile_index = idx
    if page_id and tile_index is not None:
        out.append(f"{page_id}_tile_{tile_index:03d}")
        out.append(f"tile_{page_id}_tile_{tile_index:03d}")
        out.append(f"{page_id}#tile_index:{tile_index}")
    return _unique(_normal_join_key(item) or item for item in out if _text(item))


def _index_refined_table(records: Sequence[Mapping[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    by_key: dict[str, dict[str, Any]] = {}
    by_page: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        record = dict(row)
        page_id = _text(record.get("page_id"))
        if page_id:
            by_page.setdefault(page_id, []).append(record)
        keys = _record_key_candidates(record)
        tile_id = _text(record.get("tile_id"))
        if tile_id:
            keys.append(tile_id)
            keys.append(f"tile_{tile_id}")
            keys.append(_normal_join_key(tile_id))
        tile_index = record.get("tile_index")
        try:
            idx = int(tile_index)
        except Exception:
            idx = None
        if page_id and idx is not None:
            keys.append(f"{page_id}_tile_{idx:03d}")
            keys.append(f"tile_{page_id}_tile_{idx:03d}")
            keys.append(f"{page_id}#tile_index:{idx}")
        for key in _unique(_normal_join_key(item) or item for item in keys if _text(item)):
            if key:
                by_key[key] = record
    return by_key, by_page


def _page_meta(page_index: Mapping[str, Mapping[str, Any]], page_id: str) -> dict[str, Any]:
    return dict(page_index.get(page_id, {}))


def _source_url(page_meta: Mapping[str, Any], row: Mapping[str, Any]) -> str:
    return _text(row.get("source_url") or page_meta.get("source_url") or page_meta.get("url") or page_meta.get("source"))


def _tiff_path(page_meta: Mapping[str, Any], row: Mapping[str, Any]) -> str:
    return _text(row.get("tiff_path") or page_meta.get("tiff_path") or page_meta.get("image_path") or page_meta.get("local_tiff_path"))


def _ocr_path(page_meta: Mapping[str, Any], row: Mapping[str, Any]) -> str:
    return _text(row.get("ocr_path") or page_meta.get("ocr_path") or page_meta.get("ocr_text_path") or page_meta.get("local_ocr_path"))


def _ata_code(page_meta: Mapping[str, Any], row: Mapping[str, Any]) -> str:
    return _text(row.get("ata_code") or page_meta.get("ata_code") or page_meta.get("ata") or page_meta.get("ata_section"))


def _document_id(page_meta: Mapping[str, Any], row: Mapping[str, Any]) -> str:
    return _text(row.get("document_id") or row.get("manual_id") or page_meta.get("document_id") or page_meta.get("manual_id") or page_meta.get("document") or page_meta.get("manual"))


def _page_role(page_meta: Mapping[str, Any]) -> str:
    return _text(page_meta.get("role") or page_meta.get("page_role") or page_meta.get("type"))


def _page_context_text(page_meta: Mapping[str, Any]) -> str:
    pieces: list[str] = []
    for key in (
        "context", "summary", "page_summary", "context_summary", "ai_context",
        "title", "header", "description", "ocr_preview", "text_preview",
    ):
        value = page_meta.get(key)
        if isinstance(value, str) and value.strip():
            pieces.append(value.strip())
        elif isinstance(value, Mapping):
            for child_key in ("summary", "text", "title", "description"):
                child = value.get(child_key)
                if isinstance(child, str) and child.strip():
                    pieces.append(child.strip())
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    pieces.append(item.strip())
    return "\n".join(_unique(pieces))


def _extract_parts_from_meta(value: Any) -> list[str]:
    parts: list[str] = []

    def walk(item: Any) -> None:
        if isinstance(item, Mapping):
            for key in ("part_number", "part", "number", "id", "label"):
                text = _text(item.get(key))
                if text and PART_RE.search(text):
                    parts.extend(m.group(0) for m in PART_RE.finditer(text))
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)
        else:
            text = _text(item)
            if text:
                parts.extend(m.group(0) for m in PART_RE.finditer(text))

    walk(value)
    return _unique(parts)


# ---------------------------------------------------------------------------
# Candidate text construction
# ---------------------------------------------------------------------------


def _base_metadata(row: Mapping[str, Any], page_meta: Mapping[str, Any]) -> dict[str, Any]:
    page_id = _text(row.get("page_id"))
    return {
        "page_id": page_id,
        "document_id": _document_id(page_meta, row),
        "ata_code": _ata_code(page_meta, row),
        "page_role": _page_role(page_meta),
        "source_url": _source_url(page_meta, row),
        "tiff_path": _tiff_path(page_meta, row),
        "ocr_path": _ocr_path(page_meta, row),
    }


def _source_text(row: Mapping[str, Any], page_meta: Mapping[str, Any]) -> str:
    meta = _base_metadata(row, page_meta)
    pieces = [
        f"Source evidence for page {meta['page_id']}.",
        "This page is source-trace verified and can be used as citation evidence.",
    ]
    if meta["document_id"]:
        pieces.append(f"Document: {meta['document_id']}.")
    if meta["ata_code"]:
        pieces.append(f"ATA: {meta['ata_code']}.")
    if meta["page_role"]:
        pieces.append(f"Page role: {meta['page_role']}.")
    if meta["source_url"]:
        pieces.append(f"Source URL: {meta['source_url']}.")
    if meta["tiff_path"]:
        pieces.append(f"TIFF path: {meta['tiff_path']}.")
    if meta["ocr_path"]:
        pieces.append(f"OCR path: {meta['ocr_path']}.")
    return "\n".join(pieces)


def _source_ocr_text(row: Mapping[str, Any], page_meta: Mapping[str, Any], max_ocr_chars: int = 6000) -> str:
    meta = _base_metadata(row, page_meta)
    ocr_text = _read_text_file(meta["ocr_path"], max_chars=max_ocr_chars)
    context_text = _page_context_text(page_meta)
    pieces = [
        f"Source text evidence for page {meta['page_id']}.",
        "This chunk is source-backed OCR/page-context text and can be searched as source text evidence.",
    ]
    if meta["document_id"]:
        pieces.append(f"Document: {meta['document_id']}.")
    if meta["ata_code"]:
        pieces.append(f"ATA: {meta['ata_code']}.")
    if meta["page_role"]:
        pieces.append(f"Page role: {meta['page_role']}.")
    if meta["source_url"]:
        pieces.append(f"Source URL: {meta['source_url']}.")
    if meta["tiff_path"]:
        pieces.append(f"TIFF path: {meta['tiff_path']}.")
    if meta["ocr_path"]:
        pieces.append(f"OCR path: {meta['ocr_path']}.")
    if context_text:
        pieces.append("Page context:\n" + _clip(context_text, 1200))
    if ocr_text:
        pieces.append("OCR text:\n" + ocr_text)
    return "\n".join(pieces)


def _has_source_text(row: Mapping[str, Any], page_meta: Mapping[str, Any], min_chars: int) -> bool:
    meta = _base_metadata(row, page_meta)
    ocr_text = _read_text_file(meta["ocr_path"], max_chars=max(min_chars + 1, 500))
    context_text = _page_context_text(page_meta)
    meaningful = (ocr_text + "\n" + context_text).strip()
    return len(meaningful) >= max(1, min_chars)


def _verified_part_text(row: Mapping[str, Any], page_meta: Mapping[str, Any]) -> str:
    page_id = _text(row.get("page_id"))
    parts = _extract_parts_from_meta(page_meta)
    pieces = [
        f"Verified part evidence for page {page_id}.",
        "This record comes from the verified part evidence pool and is source-traceable.",
    ]
    meta = _base_metadata(row, page_meta)
    if meta["ata_code"]:
        pieces.append(f"ATA: {meta['ata_code']}.")
    if parts:
        pieces.append("Page/catalog part signals: " + ", ".join(parts[:80]) + ".")
    else:
        pieces.append("Verified part evidence is present for this page, but no page-index part list was available in this candidate build.")
    if meta["source_url"]:
        pieces.append(f"Source URL: {meta['source_url']}.")
    return "\n".join(pieces)


def _find_refined_record(row: Mapping[str, Any], by_key: Mapping[str, Mapping[str, Any]], by_page: Mapping[str, list[Mapping[str, Any]]]) -> dict[str, Any]:
    for key in _record_key_candidates(row):
        normalized = _normal_join_key(key)
        for candidate in (key, normalized):
            if candidate and candidate in by_key:
                return dict(by_key[candidate])

    page_id = _text(row.get("page_id"))
    page_rows = list(by_page.get(page_id, []))
    if not page_rows:
        return {}

    # If the eligibility row contains a tile index but the exact tile ID did not
    # match, use page+tile_index as the fallback. This handles Stage 5 IDs such as
    # ``tile_t_p_..._tile_001`` and other future wrapper IDs.
    tile_index: int | None = None
    for key in _record_key_candidates(row):
        tile_index = _tile_index_from_text(key)
        if tile_index is not None:
            break
    if tile_index is not None:
        for refined in page_rows:
            try:
                if int(refined.get("tile_index", -1)) == tile_index:
                    return dict(refined)
            except Exception:
                continue
            if _normal_join_key(refined.get("tile_id")) == f"{page_id}_tile_{tile_index:03d}":
                return dict(refined)

    # Final safe fallback: only auto-join a page if it has exactly one refined tile
    # record. Multiple rows would be ambiguous.
    if len(page_rows) == 1:
        return dict(page_rows[0])
    return {}


def _derived_text(row: Mapping[str, Any], page_meta: Mapping[str, Any], refined: Mapping[str, Any]) -> str:
    page_id = _text(row.get("page_id"))
    layer = _text(row.get("evidence_layer"))
    pieces = [
        f"Derived context for page {page_id}.",
        f"Evidence layer: {layer}.",
        "This context is derived evidence, not canonical source truth.",
    ]
    if refined:
        tile_id = _text(refined.get("tile_id"))
        if tile_id:
            pieces.append(f"Table tile: {tile_id}.")
        catalog_parts = _unique(_text(p) for p in _as_list(refined.get("catalog_supported_part_numbers")))
        canonical_parts = _unique(_text(p) for p in _as_list(refined.get("canonical_part_numbers")))
        unsupported = _unique(_text(p) for p in _as_list(refined.get("unsupported_part_candidates")))
        index_labels = _unique(_text(p) for p in _as_list(refined.get("index_labels")))
        if catalog_parts:
            pieces.append("Catalog-supported parts found in tile text: " + ", ".join(catalog_parts[:80]) + ".")
        elif canonical_parts:
            pieces.append("Candidate part-like strings found in tile text: " + ", ".join(canonical_parts[:80]) + ".")
        if unsupported:
            pieces.append("Unsupported part candidates requiring review: " + ", ".join(unsupported[:40]) + ".")
        if index_labels:
            pieces.append("Filtered index/section labels: " + ", ".join(index_labels[:40]) + ".")
        text = _text(refined.get("text"))
        if text:
            pieces.append("Extracted tile text:\n" + text)
    else:
        pieces.append("No refined table tile text record could be joined for this derived context candidate.")
    meta = _base_metadata(row, page_meta)
    if meta["source_url"]:
        pieces.append(f"Source URL: {meta['source_url']}.")
    return "\n".join(pieces)


def _make_candidate(row: Mapping[str, Any], bucket: str, page_meta: Mapping[str, Any], refined: Mapping[str, Any], max_text_chars: int) -> dict[str, Any]:
    source_record_id = _text(row.get("source_record_id") or row.get("eligibility_id") or row.get("record_id"))
    page_id = _text(row.get("page_id"))
    evidence_layer = _text(row.get("evidence_layer"), "unknown")
    if bucket == "source_text_evidence":
        evidence_layer = "source_text"
    if bucket == "source_evidence":
        text = _source_text(row, page_meta)
        candidate_type = "source_evidence"
    elif bucket == "source_text_evidence":
        text = _source_ocr_text(row, page_meta, max_ocr_chars=max_text_chars)
        candidate_type = "source_text_evidence"
    elif bucket == "verified_part_evidence":
        text = _verified_part_text(row, page_meta)
        candidate_type = "verified_part_evidence"
    else:
        text = _derived_text(row, page_meta, refined)
        candidate_type = "derived_context"
    meta = _base_metadata(row, page_meta)
    chunk_id = f"rag_candidate:{bucket}:{_slug(source_record_id or page_id + ':' + evidence_layer)}"
    return {
        "chunk_id": chunk_id,
        "candidate_id": chunk_id,
        "source_record_id": source_record_id,
        "page_id": page_id,
        "document_id": meta["document_id"],
        "ata_code": meta["ata_code"],
        "page_role": meta["page_role"],
        "evidence_layer": evidence_layer,
        "rag_bucket": bucket,
        "candidate_type": candidate_type,
        "text": _clip(text, max_text_chars),
        "text_chars": len(_clip(text, max_text_chars)),
        "full_text_chars": len(text),
        "source_url": meta["source_url"],
        "tiff_path": meta["tiff_path"],
        "ocr_path": meta["ocr_path"],
        "final_trust_tier": _text(row.get("final_trust_tier")),
        "final_rag_action": _text(row.get("final_rag_action")),
        "usable_confidence": round(_num(row.get("usable_confidence")), 6),
        "support_score": round(_num(row.get("support_score")), 6),
        "risk_score": round(_num(row.get("risk_score")), 6),
        "stage5_controlled": bool(row.get("stage5_controlled")),
        "source_trace_status": _text(row.get("source_trace_status")),
        "indexer_version": VERSION,
        "metadata": {
            "source_record_id": source_record_id,
            "decision_source": _text(row.get("decision_source")),
            "control_status": _text(row.get("control_status")),
            "eligibility_reasons": _as_list(row.get("eligibility_reasons")),
            "refined_tile_joined": bool(refined),
            "refined_tile_id": _text(refined.get("tile_id")) if refined else "",
            "catalog_supported_part_numbers": _as_list(refined.get("catalog_supported_part_numbers")) if refined else [],
            "canonical_part_numbers": _as_list(refined.get("canonical_part_numbers")) if refined else [],
            "source_text_ocr_joined": bool(bucket == "source_text_evidence" and _text(_read_text_file(meta["ocr_path"], max_chars=64))),
        },
    }


# ---------------------------------------------------------------------------
# Build artifacts
# ---------------------------------------------------------------------------


def build_rag_candidate_index(paths: RagCandidateIndexPaths, options: RagCandidateIndexOptions | None = None) -> dict[str, Any]:
    options = options or RagCandidateIndexOptions()
    page_index = _index_pages(_read_json(paths.page_index, {}) or {})
    refined_by_key, refined_by_page = _index_refined_table(_read_jsonl(paths.refined_table_records))

    source_rows = _read_jsonl(paths.source_evidence)
    verified_rows = _read_jsonl(paths.verified_part_evidence)
    derived_rows = _read_jsonl(paths.derived_context)

    source_candidates = [_make_candidate(row, "source_evidence", _page_meta(page_index, _text(row.get("page_id"))), {}, options.max_text_chars) for row in source_rows]
    source_text_candidates: list[dict[str, Any]] = []
    if options.include_source_text:
        for row in source_rows:
            page_meta = _page_meta(page_index, _text(row.get("page_id")))
            if _has_source_text(row, page_meta, options.min_source_text_chars):
                source_text_candidates.append(_make_candidate(row, "source_text_evidence", page_meta, {}, options.max_source_text_chars))
    verified_candidates = [_make_candidate(row, "verified_part_evidence", _page_meta(page_index, _text(row.get("page_id"))), {}, options.max_text_chars) for row in verified_rows]
    derived_candidates = []
    for row in derived_rows:
        page_meta = _page_meta(page_index, _text(row.get("page_id")))
        refined = _find_refined_record(row, refined_by_key, refined_by_page)
        derived_candidates.append(_make_candidate(row, "derived_context", page_meta, refined, options.max_text_chars))

    all_candidates = [*source_candidates, *source_text_candidates, *verified_candidates, *derived_candidates]
    unsafe = _unsafe_candidates(all_candidates)
    pages = sorted({row.get("page_id") for row in all_candidates if row.get("page_id")})
    nodes, edges = _build_graph(all_candidates)

    derived_joined = [row for row in derived_candidates if _as_dict(row.get("metadata")).get("refined_tile_joined")]
    derived_unjoined = [row for row in derived_candidates if not _as_dict(row.get("metadata")).get("refined_tile_joined")]
    derived_with_catalog_parts = [
        row for row in derived_candidates
        if _as_list(_as_dict(row.get("metadata")).get("catalog_supported_part_numbers"))
    ]
    summary = {
        "status": "OK" if not unsafe else "WARN",
        "version": VERSION,
        "created_at": _utc_now(),
        "records": len(all_candidates),
        "chunks": len(all_candidates),
        "pages": len(pages),
        "source_candidate_records": len(source_candidates),
        "source_text_candidate_records": len(source_text_candidates),
        "source_text_ocr_joined_records": len([row for row in source_text_candidates if _as_dict(row.get("metadata")).get("source_text_ocr_joined")]),
        "verified_part_candidate_records": len(verified_candidates),
        "derived_context_candidate_records": len(derived_candidates),
        "derived_context_joined_records": len(derived_joined),
        "derived_context_unjoined_records": len(derived_unjoined),
        "derived_context_catalog_supported_records": len(derived_with_catalog_parts),
        "unsafe_candidate_records": len(unsafe),
        "empty_text_records": len([row for row in all_candidates if not _text(row.get("text"))]),
        "stage5_controlled_records": len([row for row in all_candidates if row.get("stage5_controlled")]),
        "rag_bucket_counts": _count(_text(row.get("rag_bucket")) for row in all_candidates),
        "evidence_layer_counts": _count(_text(row.get("evidence_layer")) for row in all_candidates),
        "trust_tier_counts": _count(_text(row.get("final_trust_tier")) for row in all_candidates),
        "candidate_type_counts": _count(_text(row.get("candidate_type")) for row in all_candidates),
        "average_text_chars": round(sum(int(row.get("text_chars") or 0) for row in all_candidates) / len(all_candidates), 2) if all_candidates else 0.0,
        "graph_nodes": len(nodes),
        "graph_edges": len(edges),
        "paths": {
            "source_evidence": str(paths.source_evidence),
            "verified_part_evidence": str(paths.verified_part_evidence),
            "derived_context": str(paths.derived_context),
            "page_index": str(paths.page_index),
            "refined_table_records": str(paths.refined_table_records),
            "all_candidates": str(paths.all_candidates),
            "source_candidates": str(paths.source_candidates),
            "source_text_candidates": str(paths.source_text_candidates),
            "verified_part_candidates": str(paths.verified_part_candidates),
            "derived_candidates": str(paths.derived_candidates),
            "summary": str(paths.summary),
            "review_html": str(paths.review_html),
            "graph_nodes": str(paths.graph_nodes),
            "graph_edges": str(paths.graph_edges),
        },
        "samples": {
            "source_candidates": source_candidates[: options.max_samples],
            "source_text_candidates": source_text_candidates[: options.max_samples],
            "verified_part_candidates": verified_candidates[: options.max_samples],
            "derived_candidates": derived_candidates[: options.max_samples],
            "unsafe_candidates": unsafe[: options.max_samples],
        },
    }

    _write_jsonl(paths.all_candidates, all_candidates)
    _write_jsonl(paths.source_candidates, source_candidates)
    _write_jsonl(paths.source_text_candidates, source_text_candidates)
    _write_jsonl(paths.verified_part_candidates, verified_candidates)
    _write_jsonl(paths.derived_candidates, derived_candidates)
    _write_json(paths.summary, summary)
    _write_json(paths.graph_nodes, nodes)
    _write_json(paths.graph_edges, edges)
    _write_text(paths.review_md, _render_markdown(summary))
    _write_text(paths.review_html, _render_html(summary))

    if options.open_report:
        try:
            webbrowser.open(paths.review_html.resolve().as_uri())
        except Exception:
            pass
    return summary


def _unsafe_candidates(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unsafe: list[dict[str, Any]] = []
    for row in candidates:
        reasons: list[str] = []
        bucket = _text(row.get("rag_bucket"))
        layer = _text(row.get("evidence_layer"))
        tier = _text(row.get("final_trust_tier"))
        text = _text(row.get("text"))
        if bucket not in SAFE_BUCKETS:
            reasons.append("unsafe_bucket")
        if layer in {"table_candidate", "table_tiles"}:
            reasons.append("routing_or_preprocessing_artifact_indexed")
        if tier == "D":
            reasons.append("D_tier_indexed")
        if not text:
            reasons.append("empty_text")
        if reasons:
            item = dict(row)
            item["unsafe_index_reasons"] = sorted(set(reasons))
            unsafe.append(item)
    return unsafe


def _build_graph(candidates: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def add_node(node_id: str, kind: str, **props: Any) -> None:
        if not node_id:
            return
        node = nodes.setdefault(node_id, {"id": node_id, "kind": kind})
        node.update({k: v for k, v in props.items() if v is not None})

    def add_edge(src: str, dst: str, kind: str, **props: Any) -> None:
        if not src or not dst:
            return
        edges.append({"source": src, "target": dst, "kind": kind, **{k: v for k, v in props.items() if v is not None}})

    root = "rag_candidate_index:root"
    add_node(root, "rag_candidate_index_root", version=VERSION)
    for bucket in SAFE_BUCKETS:
        bucket_id = f"rag_candidate_bucket:{bucket}"
        add_node(bucket_id, "rag_candidate_bucket", value=bucket)
        add_edge(root, bucket_id, "HAS_CANDIDATE_BUCKET")

    for row in candidates:
        cid = _text(row.get("chunk_id"))
        page_id = _text(row.get("page_id"))
        bucket = _text(row.get("rag_bucket"))
        layer = _text(row.get("evidence_layer"))
        tier = _text(row.get("final_trust_tier"))
        add_node(cid, "rag_candidate_chunk", page_id=page_id, rag_bucket=bucket, evidence_layer=layer, final_trust_tier=tier, usable_confidence=row.get("usable_confidence"))
        add_edge(root, cid, "HAS_RAG_CANDIDATE")
        add_node(f"rag_candidate_bucket:{bucket}", "rag_candidate_bucket", value=bucket)
        add_edge(cid, f"rag_candidate_bucket:{bucket}", "IN_RAG_CANDIDATE_BUCKET")
        add_node(f"trait:evidence_layer:{layer}", "trait", namespace="evidence_layer", value=layer)
        add_edge(cid, f"trait:evidence_layer:{layer}", "HAS_EVIDENCE_LAYER")
        add_node(f"trait:trust:{layer}:{tier}", "trait", namespace="trust", evidence_layer=layer, value=tier)
        add_edge(cid, f"trait:trust:{layer}:{tier}", "HAS_TRUST_TIER")
        if page_id:
            add_node(f"page:{page_id}", "page", page_id=page_id)
            add_edge(f"page:{page_id}", cid, "HAS_RAG_CANDIDATE")
    return list(nodes.values()), edges


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(v).replace("\n", "<br>") for v in row) + " |")
    return "\n".join(out)


def _sample_table(rows: Sequence[Mapping[str, Any]], limit: int = 20) -> str:
    table_rows = []
    for row in rows[:limit]:
        table_rows.append([
            row.get("page_id", ""),
            row.get("evidence_layer", ""),
            row.get("rag_bucket", ""),
            row.get("final_trust_tier", ""),
            row.get("usable_confidence", ""),
            _clip(_text(row.get("text")), 220),
        ])
    return _md_table(["Page", "Layer", "Bucket", "Trust", "Confidence", "Text preview"], table_rows) if table_rows else "None."


def _render_markdown(summary: Mapping[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# TRACE-Net RAG Candidate Index v1")
    lines.append("")
    lines.append(f"Status: **{summary.get('status')}**")
    lines.append(f"Version: `{summary.get('version')}`")
    lines.append("")
    lines.append("## Summary")
    for key in (
        "records", "pages", "source_candidate_records", "source_text_candidate_records", "source_text_ocr_joined_records", "verified_part_candidate_records", "derived_context_candidate_records",
        "derived_context_joined_records", "derived_context_unjoined_records", "derived_context_catalog_supported_records",
        "unsafe_candidate_records", "empty_text_records", "stage5_controlled_records", "average_text_chars", "graph_nodes", "graph_edges",
    ):
        lines.append(f"- **{key}**: {summary.get(key)}")
    lines.append("")
    lines.append("## Counts")
    for key in ("rag_bucket_counts", "evidence_layer_counts", "trust_tier_counts", "candidate_type_counts"):
        lines.append(f"- **{key}**: `{summary.get(key, {})}`")
    lines.append("")
    for title, rows in (
        ("Source candidates", summary.get("samples", {}).get("source_candidates", [])),
        ("Source text candidates", summary.get("samples", {}).get("source_text_candidates", [])),
        ("Verified part candidates", summary.get("samples", {}).get("verified_part_candidates", [])),
        ("Derived context candidates", summary.get("samples", {}).get("derived_candidates", [])),
        ("Unsafe candidates", summary.get("samples", {}).get("unsafe_candidates", [])),
    ):
        lines.append(f"## {title}")
        lines.append(_sample_table(rows))
        lines.append("")
    return "\n".join(lines) + "\n"


def _render_html(summary: Mapping[str, Any]) -> str:
    def esc(value: Any) -> str:
        return html.escape(str(value))

    sections = ["<h1>TRACE-Net RAG Candidate Index v1</h1>"]
    sections.append(f"<p><b>Status:</b> {esc(summary.get('status'))} &nbsp; <b>Version:</b> <code>{esc(summary.get('version'))}</code></p>")
    sections.append("<h2>Summary</h2><table><tbody>")
    for key in (
        "records", "pages", "source_candidate_records", "source_text_candidate_records", "source_text_ocr_joined_records", "verified_part_candidate_records", "derived_context_candidate_records",
        "derived_context_joined_records", "derived_context_unjoined_records", "derived_context_catalog_supported_records",
        "unsafe_candidate_records", "empty_text_records", "stage5_controlled_records", "average_text_chars", "graph_nodes", "graph_edges",
    ):
        sections.append(f"<tr><th>{esc(key)}</th><td>{esc(summary.get(key))}</td></tr>")
    sections.append("</tbody></table>")
    sections.append("<h2>Counts</h2>")
    for key in ("rag_bucket_counts", "evidence_layer_counts", "trust_tier_counts", "candidate_type_counts"):
        sections.append(f"<h3>{esc(key)}</h3><pre>{esc(json.dumps(summary.get(key, {}), indent=2, sort_keys=True))}</pre>")
    for title, rows in (
        ("Source candidates", summary.get("samples", {}).get("source_candidates", [])),
        ("Source text candidates", summary.get("samples", {}).get("source_text_candidates", [])),
        ("Verified part candidates", summary.get("samples", {}).get("verified_part_candidates", [])),
        ("Derived context candidates", summary.get("samples", {}).get("derived_candidates", [])),
        ("Unsafe candidates", summary.get("samples", {}).get("unsafe_candidates", [])),
    ):
        sections.append(f"<h2>{esc(title)}</h2>")
        sections.append("<table><thead><tr><th>Page</th><th>Layer</th><th>Bucket</th><th>Trust</th><th>Confidence</th><th>Text preview</th></tr></thead><tbody>")
        for row in rows[:40]:
            sections.append(
                "<tr>"
                f"<td>{esc(row.get('page_id',''))}</td>"
                f"<td>{esc(row.get('evidence_layer',''))}</td>"
                f"<td>{esc(row.get('rag_bucket',''))}</td>"
                f"<td>{esc(row.get('final_trust_tier',''))}</td>"
                f"<td>{esc(row.get('usable_confidence',''))}</td>"
                f"<td><pre>{esc(_clip(_text(row.get('text')), 700))}</pre></td>"
                "</tr>"
            )
        sections.append("</tbody></table>")
    css = "body{font-family:Arial,sans-serif;margin:24px;line-height:1.35}table{border-collapse:collapse;width:100%;margin:12px 0}th,td{border:1px solid #ddd;padding:6px;vertical-align:top}th{background:#f6f6f6;text-align:left}pre{white-space:pre-wrap;background:#f6f6f6;padding:8px;max-height:240px;overflow:auto}code{background:#f6f6f6;padding:1px 3px}"
    return "<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net RAG Candidate Index</title><style>" + css + "</style></head><body>" + "\n".join(sections) + "</body></html>\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net RAG candidate chunks from RAG eligibility pools.")
    parser.add_argument("--rag-dir", type=Path, default=DEFAULT_RAG_ELIGIBILITY_DIR)
    parser.add_argument("--export-dir", type=Path, default=DEFAULT_EXPORT_DIR)
    parser.add_argument("--refined-table-dir", type=Path, default=DEFAULT_REFINED_TABLE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-text-chars", type=int, default=4000)
    parser.add_argument("--no-source-text", action="store_true", help="Do not create source_text_evidence chunks from OCR/page context.")
    parser.add_argument("--max-source-text-chars", type=int, default=6000)
    parser.add_argument("--min-source-text-chars", type=int, default=20)
    parser.add_argument("--samples", type=int, default=40)
    parser.add_argument("--open", action="store_true", dest="open_report")
    args = parser.parse_args(argv)

    paths = RagCandidateIndexPaths(
        rag_dir=args.rag_dir,
        export_dir=args.export_dir,
        refined_table_dir=args.refined_table_dir,
        output_dir=args.output_dir,
    )
    result = build_rag_candidate_index(
        paths,
        RagCandidateIndexOptions(
            open_report=args.open_report,
            max_samples=args.samples,
            max_text_chars=args.max_text_chars,
            include_source_text=not args.no_source_text,
            max_source_text_chars=args.max_source_text_chars,
            min_source_text_chars=args.min_source_text_chars,
        ),
    )
    print("TRACE-Net RAG candidate indexer")
    print(f"  Status: {result['status']}")
    print(f"  Output dir: {args.output_dir}")
    print("  Summary:")
    for key in (
        "records", "pages", "source_candidate_records", "source_text_candidate_records", "source_text_ocr_joined_records", "verified_part_candidate_records", "derived_context_candidate_records",
        "derived_context_joined_records", "derived_context_unjoined_records", "derived_context_catalog_supported_records",
        "unsafe_candidate_records", "empty_text_records", "stage5_controlled_records", "graph_nodes", "graph_edges",
    ):
        print(f"    {key}: {result.get(key)}")
    print("  Buckets:", result.get("rag_bucket_counts"))
    print("Files written:")
    for key, value in result.get("paths", {}).items():
        if key in {"all_candidates", "source_candidates", "verified_part_candidates", "derived_candidates", "summary", "review_html", "graph_nodes", "graph_edges"}:
            print(f"  {key}: {value}")
    return 0 if result.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
