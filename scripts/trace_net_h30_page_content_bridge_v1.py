#!/usr/bin/env python3
"""Exact-page content bridge for TRACE-Net H30.

Given a full canonical page id, this bridge assembles a typed page-content
evidence pack by (1) traversing the canonical graph from the EXACT page node to
its linked V1/V2/V3 context, OCR, table, and visual records, then (2) filling any
missing section from the corresponding page artifact using exact page_id
equality. The pack feeds the single existing Gemma writer; the router adds no
second model call and mutates no store.

Flow:
    canonical page id
      -> exact graph page (exact-equality; never a similar page)
      -> retrieve any linked graph records
      -> fill missing sections from artifacts by exact page_id
      -> typed page-content evidence pack (conflicts surfaced)

Three separate, preserved context contracts (never aliased to one another):
- v1_context            from edge HAS_CONTEXT
- v2_context            from edge HAS_CONTEXT_V2
- v3_page_intelligence  from edge HAS_V3_PAGE_INTELLIGENCE

Established graph edge-name contracts (not renamed / not invented):
- OCR:    HAS_OCR
- Tables: HAS_TABLE_ELEMENT -> HAS_TABLE_ROW -> HAS_TABLE_CELL
- Visual: HAS_VISUAL_UNDERSTANDING -> HAS_VISUAL_REGION

Source priority:
- Strongest: exact OCR text, table cells/rows, direct source fields.
- Guidance:  V1 context, V2 context, V3 intelligence, unresolved visual.
- V1/V2/V3 and visual guidance never independently prove approval, fit,
  effectivity, safety, or interchangeability (enforced by the dangerous-claim
  gate in the writer).

Enabled with TRACE_NET_H30_PAGE_CONTENT_BRIDGE_ENABLED=1 (off at module level).
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from scripts.trace_net_h30_layout_aware_ocr_v1 import (
    reconstruct_layout_aware_ocr,
    render_layout_reconstruction,
)

try:
    from tiff.trace_net_graph_query_helper_v1 import (
        collect_page_parts,
        collect_sources,
        is_page_node,
        page_id as _page_id,
        page_label as _page_label,
    )

    _HELPER_AVAILABLE = True
except Exception:  # pragma: no cover - defensive
    _HELPER_AVAILABLE = False

try:
    from scripts.trace_net_h30_graph_source_retrieval_v1 import load_graph_index
except Exception:  # pragma: no cover - defensive
    def load_graph_index():  # type: ignore
        return None

MODULE = "trace_net_h30_page_content_bridge_v1"
PATCH_ID = "trace_net_h30_phase3_page_content_bridge_v1"
BRIDGE_TUNNEL = "page_content_bridge"

# Separate, preserved context contracts.
V1_EDGES = ("HAS_CONTEXT",)
V2_EDGES = ("HAS_CONTEXT_V2",)
V3_EDGES = ("HAS_V3_PAGE_INTELLIGENCE",)
OCR_EDGES = ("HAS_OCR",)
# Established table/visual chains (multi-hop). Do not introduce HAS_TABLE or
# HAS_VISUAL / HAS_VISUAL_OBSERVATION.
TABLE_CHAIN = (("HAS_TABLE_ELEMENT",), ("HAS_TABLE_ROW",), ("HAS_TABLE_CELL",))
VISUAL_CHAIN = (("HAS_VISUAL_UNDERSTANDING",), ("HAS_VISUAL_REGION",))

# Section key -> (authority). Guidance vs supporting per the source-priority rule.
GUIDANCE = "guidance"
SUPPORTING = "supporting"

PAGE_ROUTES = {
    "document_page_navigation",
    "visual_figure_callout_lookup",
    "procedure_task_lookup",
    "warning_caution_note_lookup",
    "ocr_scan_recovery",
    "exact_table_ipl_lookup",
    # TRACE_NET_H30_PHASE5_NOTICE_COMPARISON_RUNTIME_FIX_V1_1
    "cross_source_comparison",
    "multi_question_research",
}

_PAGE_KEYS = ("page_id", "source_page_id", "document_page_id", "page")
_ARTIFACT_CACHE: Dict[Tuple[str, ...], Dict[str, Dict[str, List[Dict[str, Any]]]]] = {}
_OCR_TEXT_CACHE: Dict[str, str] = {}
_LOCK = threading.RLock()

# Multi-path artifact sections. A single section may be backed by several real
# artifacts (visual guidance in particular is produced by more than one route);
# records are merged by exact page_id across all configured paths.
_MULTI_PATH_SECTIONS = ("visuals",)
_PATH_SEP = os.pathsep  # ':' on the POSIX server; safe for the colon-free default paths.


def _ocr_full_text_limit() -> int:
    try:
        return max(200, min(int(os.environ.get("TRACE_NET_H30_PAGE_OCR_TEXT_MAX_CHARS", "4000")), 20000))
    except (TypeError, ValueError):
        return 4000


def _max_per_section() -> int:
    """Cap records kept per section so a page with hundreds of table cells does
    not bloat the single Gemma prompt."""
    try:
        return max(1, min(int(os.environ.get("TRACE_NET_H30_PAGE_CONTENT_MAX_PER_SECTION", "15")), 200))
    except (TypeError, ValueError):
        return 15


def page_content_bridge_enabled() -> bool:
    raw = os.environ.get("TRACE_NET_H30_PAGE_CONTENT_BRIDGE_ENABLED")
    if raw is None:
        return False
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _compact(value: Any, limit: int = 2000) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            text = str(value)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _as_list(value: Any) -> List[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _fields(props: Mapping[str, Any], kind: str, origin: str, authority: str, page_id: str) -> Dict[str, Any]:
    source_resolved = bool(props.get("source_resolved"))
    guidance_only = authority == GUIDANCE or (kind == "visual" and not source_resolved)
    return {
        "kind": kind,
        "origin": origin,
        "authority": authority,
        "guidance_only": guidance_only,
        "can_prove_claims": False,
        "page_id": page_id,
        "text": _compact(
            props.get("page_summary")
            or props.get("summary")
            or props.get("retrieval_summary")
            or props.get("text")
            or props.get("display_value")
            or props.get("normalized_value")
            or props.get("label"),
            2000,
        ),
        "role": _compact(props.get("role") or props.get("v2_role") or props.get("v3_role") or props.get("page_route_hint") or props.get("field_role"), 200),
        "subrole": _compact(props.get("subrole") or props.get("v2_subrole"), 200),
        "nomenclature": _as_list(props.get("nomenclature")),
        "ata": _compact(props.get("ata_code") or props.get("ata"), 100),
        "figure_refs": _as_list(props.get("figure_refs")),
        "callouts": _as_list(props.get("callouts") or props.get("labels")),
        "part_numbers": _as_list(props.get("part_numbers") or props.get("covered_part_number") or props.get("part_number")),
        "field_name": _compact(props.get("field_name"), 200),
        "ocr_engine": _compact(props.get("ocr_engine") or props.get("engine"), 100),
        "ocr_confidence": props.get("confidence") if isinstance(props.get("confidence"), (int, float)) else None,
        "source_resolved": source_resolved,
    }


def _graph_record(node: Mapping[str, Any], kind: str, authority: str, page_id: str) -> Dict[str, Any]:
    props = node.get("properties") if isinstance(node.get("properties"), Mapping) else {}
    record = _fields(props, kind, "graph", authority, page_id)
    record["node_id"] = node.get("node_id")
    if not record["text"]:
        record["text"] = _compact(node.get("label"), 2000)
    return record


def _artifact_record(raw: Mapping[str, Any], kind: str, authority: str, page_id: str) -> Dict[str, Any]:
    record = _fields(raw, kind, "artifact", authority, page_id)
    record["artifact_source"] = _compact(raw.get("_artifact_source"), 200)
    return record


def _read_ocr_full_text(raw: Mapping[str, Any], pid: str) -> str:
    """Return the full tesseract OCR text for a page, preferring the sidecar text
    file over the (truncated) sample. Read-only; cached; capped for the prompt."""
    limit = _ocr_full_text_limit()
    candidates: List[Path] = []
    rel = str(raw.get("ocr_text_path") or "").replace("\\", "/").strip()
    base = str(raw.get("_artifact_base") or "").replace("\\", "/")
    if rel:
        p = Path(rel)
        if p.is_absolute():
            candidates.append(p)
        elif "local_data/" in rel and "/local_data/" in base:
            root = base.split("/local_data/", 1)[0]
            candidates.append(Path(root) / rel)
    # Sidecar layout: <artifact_dir>/ocr_text/<page_id>.txt
    if base:
        candidates.append(Path(base).parent / "ocr_text" / f"{pid}.txt")
    for path in candidates:
        cache_key = str(path)
        with _LOCK:
            if cache_key in _OCR_TEXT_CACHE:
                cached = _OCR_TEXT_CACHE[cache_key]
                if cached:
                    return cached[:limit]
                continue
        text = ""
        try:
            if path.exists():
                text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            text = ""
        with _LOCK:
            _OCR_TEXT_CACHE[cache_key] = text
        if text.strip():
            return _compact(text, limit)
    return _compact(raw.get("ocr_sample_text"), limit)


def _ocr_artifact_record(raw: Mapping[str, Any], pid: str) -> Optional[Dict[str, Any]]:
    """Normalize a tesseract OCR scan record. Returns None for empty-OCR pages
    (e.g. image-only pages the OCR route left blank)."""
    try:
        char_count = int(raw.get("ocr_text_char_count") or 0)
    except (TypeError, ValueError):
        char_count = 0
    text = _read_ocr_full_text(raw, pid)
    if not text and char_count <= 0:
        return None
    if not text:
        return None
    conf = raw.get("route_confidence")
    record = _fields(raw, "ocr", "artifact", SUPPORTING, pid)
    record["text"] = text
    layout = reconstruct_layout_aware_ocr(
        text,
        word_boxes=(raw.get("ocr_words") or raw.get("words") or raw.get("tokens")),
        page_route=(raw.get("accepted_route") or raw.get("route") or raw.get("primary_route")),
    )
    if layout.get("reconstruction_available"):
        record["layout_reconstruction"] = layout
        record["layout_reconstruction_text"] = render_layout_reconstruction(layout)
    record["ocr_engine"] = _compact(raw.get("route_processor") or raw.get("module") or "tesseract", 100)
    record["ocr_confidence"] = conf if isinstance(conf, (int, float)) else None
    record["ocr_char_count"] = char_count
    record["source_resolved"] = True  # OCR text is the literal source text of the page.
    record["artifact_source"] = _compact(raw.get("_artifact_source"), 200)
    return record


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = _compact(value, 1600)
        if text:
            return text
    return ""


def _visual_artifact_record(raw: Mapping[str, Any], pid: str) -> Optional[Dict[str, Any]]:
    """Normalize a visual-guidance record across the several real visual artifact
    schemas (evidence pack, LLaVA observations, confirmed page summary, corrected
    context cards). Returns None when there is nothing describable."""
    cleaned = raw.get("llava_observation_cleaned") if isinstance(raw.get("llava_observation_cleaned"), Mapping) else {}
    doc = raw.get("retrieval_document") if isinstance(raw.get("retrieval_document"), Mapping) else {}

    llava_desc = ""
    if cleaned:
        subject = _compact(cleaned.get("diagram_subject_guess"), 400)
        page_type = _compact(cleaned.get("visual_page_type"), 120)
        keywords = _as_list(cleaned.get("retrieval_keywords"))
        uncertainty = _compact(cleaned.get("visual_uncertainty"), 400)
        pieces = [x for x in (
            f"{page_type}: {subject}".strip(": ").strip() if (page_type or subject) else "",
            ("keywords: " + ", ".join(keywords)) if keywords else "",
            ("uncertainty: " + uncertainty) if uncertainty else "",
        ) if x]
        llava_desc = " | ".join(pieces)

    doc_desc = _first_nonempty(doc.get("likely_diagram_subject"), doc.get("search_text"))

    figures = (
        _as_list(raw.get("figure_refs"))
        + _as_list(raw.get("figure_candidates"))
        + _as_list(raw.get("ocr_figure_candidates"))
        + _as_list(doc.get("figure_refs"))
    )
    if raw.get("figure"):
        figures.append(str(raw.get("figure")))
    figures = list(dict.fromkeys([f for f in figures if str(f).strip()]))

    callouts = (
        _as_list(raw.get("callout"))
        + _as_list(cleaned.get("visible_callouts_or_labels_cleaned"))
        + _as_list(raw.get("ocr_callout_candidates"))
    )
    callouts = list(dict.fromkeys([c for c in callouts if str(c).strip()]))

    part_numbers = (
        _as_list(raw.get("linked_part_number"))
        + _as_list(raw.get("part_numbers"))
        + _as_list(doc.get("part_numbers"))
    )
    part_numbers = list(dict.fromkeys([p for p in part_numbers if str(p).strip()]))

    text = _first_nonempty(
        raw.get("linked_description"),
        llava_desc,
        doc_desc,
        raw.get("visual_summary"),
        raw.get("visual_layout_description"),
        raw.get("likely_diagram_subject"),
    )
    if not text and isinstance(raw.get("technical_features"), list):
        text = _compact("; ".join(str(f) for f in raw["technical_features"]), 1600)

    if not text and figures:
        kind_note = _compact(raw.get("evidence_kind") or raw.get("proof_strength"), 200)
        text = f"Visual observation referencing figure {', '.join(figures)}" + (
            f" ({kind_note})" if kind_note else ""
        )
    if not text and callouts:
        text = "Visual observation with callouts: " + ", ".join(callouts)
    if not text:
        return None

    linked = bool(raw.get("linked")) or bool(raw.get("can_support_limited_visual_answer"))
    proof_strength = str(raw.get("proof_strength") or "")
    source_resolved = bool(raw.get("source_resolved")) or (linked and "not_proof" not in proof_strength)

    record = _fields(raw, "visual", "artifact", GUIDANCE, pid)
    record["text"] = text
    record["figure_refs"] = figures
    record["callouts"] = callouts
    record["part_numbers"] = part_numbers or record.get("part_numbers") or []
    record["visual_page_type"] = _compact(cleaned.get("visual_page_type") or raw.get("visual_page_type") or doc.get("visual_page_type"), 120)
    record["source_resolved"] = source_resolved
    record["guidance_only"] = True  # visual is never independent proof.
    record["artifact_source"] = _compact(raw.get("_artifact_source"), 200)
    return record


def _collect(graph: Any, page: Mapping[str, Any], edge_names: Sequence[str], kind: str, authority: str, pid: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for _edge, node in graph.out_neighbors(page["node_id"], edge_names):
        node_id = node.get("node_id")
        if node_id in seen:
            continue
        seen.add(node_id)
        out.append(_graph_record(node, kind, authority, pid))
    return out


def _collect_chain(graph: Any, page: Mapping[str, Any], edge_levels: Sequence[Sequence[str]], kind: str, authority: str, pid: str) -> List[Dict[str, Any]]:
    """Follow a multi-hop edge chain (e.g. element -> row -> cell) from the page,
    collecting every node reached at each level."""
    out: List[Dict[str, Any]] = []
    seen = set()
    frontier = [page]
    for edges in edge_levels:
        nxt = []
        for node in frontier:
            for _edge, neighbor in graph.out_neighbors(node["node_id"], edges):
                node_id = neighbor.get("node_id")
                if node_id in seen:
                    continue
                seen.add(node_id)
                out.append(_graph_record(neighbor, kind, authority, pid))
                nxt.append(neighbor)
        frontier = nxt
    return out


def _dedup_records(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop near-duplicate merged records (same normalized text), keeping the
    first (highest-priority artifact) occurrence."""
    out: List[Dict[str, Any]] = []
    seen = set()
    for record in records:
        key = re.sub(r"\s+", " ", str(record.get("text") or "").strip().lower())
        if not key:
            key = json.dumps(
                [record.get("figure_refs"), record.get("callouts")], sort_keys=True
            )
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def _detect_conflicts(records: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    conflicts: List[Dict[str, Any]] = []
    for field in ("ata", "nomenclature"):
        values: Dict[str, set] = {}
        for rec in records:
            raw = rec.get(field)
            items = raw if isinstance(raw, list) else ([raw] if raw else [])
            for item in items:
                key = re.sub(r"\s+", " ", str(item).strip()).upper()
                if key:
                    values.setdefault(key, set()).add(rec.get("kind"))
        if len(values) > 1:
            conflicts.append({
                "field": field,
                "conflicting_values": sorted(values.keys()),
                "kinds": sorted({k for kinds in values.values() for k in kinds}),
                "resolution_status": "unresolved",
                "note": "conflicting page-content values surfaced; not resolved to fact",
            })
    return conflicts


# --- artifact loading (exact page_id keyed) ----------------------------------


def _artifact_paths() -> Dict[str, List[str]]:
    """Configured artifact paths per section. Each section is a list; most have a
    single path, but visual guidance is merged across several real artifacts."""
    base = os.environ.get("TRACE_NET_REPO", ".")
    trace = f"{base}/local_data/organization/trace_net"
    default_visuals = [
        # "confirmed visual page records" — clean per-page retrieval documents.
        f"{trace}/confirmed_image_page_summary_v1_1/trace_net_confirmed_image_page_summary_v1_1.jsonl",
        # richest LLaVA layout observations (small coverage, high detail).
        f"{trace}/confirmed_image_llava_observations_v1_1_sample/trace_net_confirmed_image_llava_observations_v1_1.jsonl",
        # figure/callout candidate evidence packs.
        f"{trace}/image_visual_evidence_pack_v1/trace_net_image_visual_evidence_pack_v1_records.jsonl",
        # corrected visual context cards (broadest page coverage).
        f"{trace}/corrected_visual_context_builder_v35_4/trace_net_corrected_visual_context_cards_v35_4.jsonl",
    ]
    default = {
        "v2_context": [f"{trace}/page_context_v2/trace_net_page_context_v2.json"],
        "v3_page_intelligence": [f"{trace}/v3_page_intelligence/trace_net_v3_page_intelligence_cards_v1.json"],
        "tables": [f"{trace}/table_exact_search_adapter/trace_net_table_exact_search_documents_v1.jsonl"],
        "ocr": [f"{trace}/ocr_route_scan_pack_tesseract_full/trace_net_ocr_route_scan_pack_v1_records.jsonl"],
        "visuals": default_visuals,
    }
    env = {
        "v2_context": "TRACE_NET_H30_PAGE_V2_ARTIFACT",
        "v3_page_intelligence": "TRACE_NET_H30_PAGE_V3_ARTIFACT",
        "tables": "TRACE_NET_H30_PAGE_TABLE_ARTIFACT",
        "ocr": "TRACE_NET_H30_PAGE_OCR_ARTIFACT",
        "visuals": "TRACE_NET_H30_PAGE_VISUAL_ARTIFACT",
    }
    resolved: Dict[str, List[str]] = {}
    for name, var in env.items():
        raw = os.environ.get(var)
        if raw is None:
            resolved[name] = list(default[name])
        elif name in _MULTI_PATH_SECTIONS:
            resolved[name] = [p.strip() for p in raw.split(_PATH_SEP) if p.strip()]
        else:
            resolved[name] = [raw.strip()] if raw.strip() else []
    return resolved


def _extract_rows(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, Mapping):
        for key in ("page_context_records", "records", "cards", "items", "page_records", "page_intelligence_cards"):
            value = data.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
        if data and all(isinstance(v, Mapping) for v in data.values()):
            rows = []
            for key, value in data.items():
                row = dict(value)
                row.setdefault("page_id", key)
                rows.append(row)
            return rows
    return []


def _page_id_of(row: Mapping[str, Any]) -> str:
    """Exact page id of a raw artifact row, honoring nested retrieval documents."""
    for key in _PAGE_KEYS:
        if row.get(key):
            return str(row.get(key)).strip()
    doc = row.get("retrieval_document")
    if isinstance(doc, Mapping):
        for key in _PAGE_KEYS:
            if doc.get(key):
                return str(doc.get(key)).strip()
    return ""


def _load_artifact_index(path: str) -> Dict[str, List[Dict[str, Any]]]:
    index: Dict[str, List[Dict[str, Any]]] = {}
    if not path or not Path(path).exists():
        return index
    source = Path(path).name
    try:
        if str(path).endswith(".jsonl"):
            rows = []
            with Path(path).open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if line:
                        rows.append(json.loads(line))
        else:
            rows = _extract_rows(json.loads(Path(path).read_text(encoding="utf-8")))
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            pid = _page_id_of(row)
            if pid:
                enriched = dict(row)
                enriched.setdefault("_artifact_source", source)
                enriched.setdefault("_artifact_base", str(path))
                index.setdefault(pid, []).append(enriched)
    except Exception:
        return {}
    return index


def _merge_indexes(paths: Sequence[str]) -> Dict[str, List[Dict[str, Any]]]:
    merged: Dict[str, List[Dict[str, Any]]] = {}
    for path in paths:
        for pid, rows in _load_artifact_index(path).items():
            merged.setdefault(pid, []).extend(rows)
    return merged


def load_page_artifacts() -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    """Load and cache the exact-page-id artifact indexes for fallback. Each
    section merges every configured path by exact page id."""
    paths = _artifact_paths()
    key = tuple(
        f"{name}={_PATH_SEP.join(paths[name])}"
        for name in ("v2_context", "v3_page_intelligence", "tables", "ocr", "visuals")
    )
    with _LOCK:
        if key in _ARTIFACT_CACHE:
            return _ARTIFACT_CACHE[key]
        indexes = {name: _merge_indexes(section_paths) for name, section_paths in paths.items()}
        _ARTIFACT_CACHE[key] = indexes
        return indexes


# --- public retrieval --------------------------------------------------------

_ARTIFACT_AUTHORITY = {
    "v2_context": GUIDANCE,
    "v3_page_intelligence": GUIDANCE,
    "tables": SUPPORTING,
    "ocr": SUPPORTING,
    "visuals": GUIDANCE,
}
_ARTIFACT_KIND = {
    "v2_context": "v2_context",
    "v3_page_intelligence": "v3_page_intelligence",
    "tables": "table",
    "ocr": "ocr",
    "visuals": "visual",
}


def page_content_pack(graph: Any, page_id_query: str, *, artifacts: Optional[Mapping[str, Mapping[str, Sequence[Mapping[str, Any]]]]] = None) -> Dict[str, Any]:
    """Typed page-content pack for the EXACT canonical page id. Read-only; never
    substitutes a similar page; makes no model call."""
    query = str(page_id_query or "").strip()
    empty = {
        "available": bool(graph is not None), "found": False, "page_id": query,
        "v1_context": [], "v2_context": [], "v3_page_intelligence": [],
        "ocr": [], "tables": [], "visuals": [], "parts": [], "conflicts": [],
        "source_trace": {}, "telemetry": _telemetry([], [], [], [], [], [], exact=False),
    }
    if graph is None or not query:
        empty["available"] = False
        return empty

    pages = graph.find_page_nodes(query)  # exact-equality only
    if not pages:
        return empty

    page = pages[0]
    pid = _page_id(page)
    source_links, tiff_files = collect_sources(graph, page)

    v1 = _collect(graph, page, V1_EDGES, "v1_context", GUIDANCE, pid)
    v2 = _collect(graph, page, V2_EDGES, "v2_context", GUIDANCE, pid)
    v3 = _collect(graph, page, V3_EDGES, "v3_page_intelligence", GUIDANCE, pid)
    ocr = _collect(graph, page, OCR_EDGES, "ocr", SUPPORTING, pid)
    tables = _collect_chain(graph, page, TABLE_CHAIN, "table", SUPPORTING, pid)
    visuals = _collect_chain(graph, page, VISUAL_CHAIN, "visual", GUIDANCE, pid)
    parts = collect_page_parts(graph, page)

    # Artifact fallback: only fill a section the graph left empty, by exact pid.
    sections = {
        "v2_context": v2,
        "v3_page_intelligence": v3,
        "tables": tables,
        "ocr": ocr,
        "visuals": visuals,
    }
    if artifacts:
        for name, current in sections.items():
            if current:  # graph already populated this section; do not override it.
                continue
            index = artifacts.get(name) or {}
            for raw in index.get(pid, []) or []:
                if not isinstance(raw, Mapping):
                    continue
                if name == "ocr":
                    record = _ocr_artifact_record(raw, pid)
                elif name == "visuals":
                    record = _visual_artifact_record(raw, pid)
                else:
                    record = _artifact_record(raw, _ARTIFACT_KIND[name], _ARTIFACT_AUTHORITY[name], pid)
                if record is not None:
                    current.append(record)
            if name == "visuals":
                sections[name] = _dedup_records(current)

    v2, v3, tables, ocr, visuals = (
        sections["v2_context"], sections["v3_page_intelligence"],
        sections["tables"], sections["ocr"], sections["visuals"],
    )
    # Graph-backed OCR records may not have passed through the artifact
    # normalizer. Attach the same conservative derived layout view here.
    for record in ocr:
        if not isinstance(record, dict) or record.get("layout_reconstruction"):
            continue
        layout = reconstruct_layout_aware_ocr(record.get("text"), page_route=record.get("role"))
        if layout.get("reconstruction_available"):
            record["layout_reconstruction"] = layout
            record["layout_reconstruction_text"] = render_layout_reconstruction(layout)
    # Conflicts are detected across the full set before capping, then each
    # section is bounded so the prompt stays a reasonable size.
    conflicts = _detect_conflicts(v1 + v2 + v3 + ocr + tables + visuals)
    cap = _max_per_section()
    v1, v2, v3 = v1[:cap], v2[:cap], v3[:cap]
    ocr, tables, visuals = ocr[:cap], tables[:cap], visuals[:cap]

    return {
        "available": True,
        "found": True,
        "page_id": pid,
        "page_label": _page_label(page),
        "source_trace": {
            "page_id": pid,
            "source_links": source_links,
            "source_files": tiff_files,
            "source_resolved": bool(source_links or tiff_files),
        },
        "v1_context": v1,
        "v2_context": v2,
        "v3_page_intelligence": v3,
        "ocr": ocr,
        "tables": tables,
        "visuals": visuals,
        "parts": parts,
        "conflicts": conflicts,
        "guidance_only": True,
        "can_prove_claims": False,
        "telemetry": _telemetry(v1, v2, v3, ocr, tables, visuals, exact=True, pid=pid, paths=_artifact_paths()),
    }


def _telemetry(v1, v2, v3, ocr, tables, visuals, *, exact: bool, pid: str = "", paths: Optional[Mapping[str, List[str]]] = None) -> Dict[str, Any]:
    records = list(v1) + list(v2) + list(v3) + list(ocr) + list(tables) + list(visuals)
    graph_records = sum(1 for r in records if r.get("origin") == "graph")
    artifact_records = sum(1 for r in records if r.get("origin") == "artifact")
    cross_page = sum(
        1 for r in records
        if r.get("page_id") and pid and str(r.get("page_id")) != str(pid)
    )
    paths = paths or {}
    return {
        "v1_record_count": len(v1),
        "v2_record_count": len(v2),
        "v3_record_count": len(v3),
        "ocr_record_count": len(ocr),
        "table_record_count": len(tables),
        "visual_record_count": len(visuals),
        "graph_record_count": graph_records,
        "artifact_fallback_record_count": artifact_records,
        "exact_page_match": bool(exact),
        "cross_page_record_count": cross_page,
        "gemma_call_count_added": 0,
        "ocr_artifact_path": _PATH_SEP.join(paths.get("ocr", []) or []),
        "visual_artifact_path": _PATH_SEP.join(paths.get("visuals", []) or []),
        "ocr_exact_page_match": bool(exact and ocr),
        "visual_exact_page_match": bool(exact and visuals),
        "page_content_record_count": len(records),
        "layout_reconstruction_record_count": sum(1 for r in ocr if r.get("layout_reconstruction_text")),
        "layout_reconstruction_row_count": sum(len((r.get("layout_reconstruction") or {}).get("rows") or []) for r in ocr),
        # Assigned by the single-writer citation registry; placeholders here.
        "page_content_registry_count": 0,
        "page_content_citation_ids": [],
        "page_content_prompt_included": False,
    }


# --- router overlay ----------------------------------------------------------


def install_page_content_bridge(router: MutableMapping[str, Any]) -> None:
    marker = "_TRACE_NET_H30_PAGE_CONTENT_BRIDGE_V1_INSTALLED"
    if router.get(marker):
        return

    runtime_cls = router["CognitiveRuntime"]
    original_gather = runtime_cls.gather_initial
    original_health = runtime_cls.health

    def _declare_tunnel(plan: Any, label: str) -> None:
        tunnels = getattr(plan, "retrieval_tunnels", None)
        if isinstance(tunnels, list) and label not in tunnels:
            tunnels.append(label)

    def gather_with_page_content(self: Any, plan: Any, atoms: Any) -> Any:
        envelope = original_gather(self, plan, atoms)
        if not page_content_bridge_enabled():
            return envelope
        route = str(getattr(plan, "primary_route", "") or "")
        if route not in PAGE_ROUTES:
            return envelope
        page_ids = [
            str(p).strip()
            for p in (getattr(atoms, "page_ids", None) or [])
            if str(p).strip()
        ]
        if not page_ids:
            return envelope

        graph = load_graph_index()
        if graph is None:
            envelope.coverage["page_content"] = {"available": False}
            return envelope
        artifacts = load_page_artifacts()

        paths = _artifact_paths()
        packs = []
        totals = {
            "v1_record_count": 0, "v2_record_count": 0, "v3_record_count": 0,
            "ocr_record_count": 0, "table_record_count": 0, "visual_record_count": 0,
            "graph_record_count": 0, "artifact_fallback_record_count": 0,
            "cross_page_record_count": 0, "page_content_record_count": 0,
            "layout_reconstruction_record_count": 0, "layout_reconstruction_row_count": 0,
        }
        ocr_exact = False
        visual_exact = False
        for pid in page_ids:
            pack = page_content_pack(graph, pid, artifacts=artifacts)
            if not pack.get("found"):
                continue
            packs.append(pack)
            for key in totals:
                totals[key] += int(pack["telemetry"].get(key, 0))
            ocr_exact = ocr_exact or bool(pack["telemetry"].get("ocr_exact_page_match"))
            visual_exact = visual_exact or bool(pack["telemetry"].get("visual_exact_page_match"))
            envelope.semantic_guidance.append({
                "page_id": pack["page_id"],
                "candidate_type": "page_content",
                "summary": _page_content_summary(pack),
                "guidance_only": True,
                "source_truth": False,
                "final_answer_allowed": False,
                "page_content_bridge": True,
            })
            for conflict in pack["conflicts"]:
                envelope.contradictions.append({
                    "page_id": pack["page_id"], "page_content_conflict": True, **conflict,
                })

        if packs:
            envelope.coverage["page_content"] = {
                "available": True,
                "pages": packs,
                "page_count": len(packs),
                "guidance_only": True,
                "source_truth_confirmation_required": True,
                "telemetry": {
                    **totals,
                    "exact_page_match": True,
                    "gemma_call_count_added": 0,
                    "ocr_artifact_path": _PATH_SEP.join(paths.get("ocr", []) or []),
                    "visual_artifact_path": _PATH_SEP.join(paths.get("visuals", []) or []),
                    "ocr_exact_page_match": ocr_exact,
                    "visual_exact_page_match": visual_exact,
                    # Assigned by the single-writer citation registry.
                    "page_content_registry_count": 0,
                    "page_content_citation_ids": [],
                    # Set true by the writer when the pack is rendered into the
                    # single Gemma prompt.
                    "page_content_prompt_included": False,
                },
            }
            if BRIDGE_TUNNEL not in envelope.retrieval_tunnels_used:
                envelope.retrieval_tunnels_used.append(BRIDGE_TUNNEL)
            _declare_tunnel(plan, BRIDGE_TUNNEL)
        return envelope

    def health_with_page_content(self: Any) -> Dict[str, Any]:
        result = dict(original_health(self))
        result.update({
            "page_content_bridge_enabled": page_content_bridge_enabled(),
            "page_content_bridge_read_only": True,
            "page_content_bridge_helper_available": _HELPER_AVAILABLE,
            "page_content_bridge_v1_edge": "HAS_CONTEXT",
            "page_content_bridge_v2_edge": "HAS_CONTEXT_V2",
            "page_content_bridge_v3_edge": "HAS_V3_PAGE_INTELLIGENCE",
            "page_content_bridge_ocr_edge": "HAS_OCR",
            "page_content_bridge_table_chain": list(TABLE_CHAIN),
            "page_content_bridge_visual_chain": list(VISUAL_CHAIN),
            "page_content_bridge_artifact_fallback": True,
            "page_content_bridge_ocr_artifact_count": len(_artifact_paths().get("ocr", [])),
            "page_content_bridge_visual_artifact_count": len(_artifact_paths().get("visuals", [])),
            "page_content_bridge_adds_gemma_call": False,
            "page_content_bridge_layout_aware_ocr": True,
            "page_content_bridge_layout_is_derived_guidance": True,
            "page_content_bridge_infers_blur_from_ocr": False,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        })
        return result

    runtime_cls.gather_initial = gather_with_page_content
    runtime_cls.health = health_with_page_content
    router[marker] = True


def _page_content_summary(pack: Mapping[str, Any]) -> str:
    parts = []
    for label, key in (("v1", "v1_context"), ("v2", "v2_context"), ("v3", "v3_page_intelligence"), ("ocr", "ocr"), ("table", "tables"), ("visual", "visuals")):
        rows = pack.get(key) or []
        if rows:
            parts.append(f"{label}: " + _compact(rows[0].get("text"), 240))
    if pack.get("conflicts"):
        parts.append(f"conflicts: {len(pack['conflicts'])} unresolved")
    return " | ".join(parts) or "page-content records found"


# Page-content citation classes. OCR/table are source "supporting"; V1/V2/V3 and
# unresolved visual are "guidance" (never independent proof of approval/fit/etc.).
PAGE_CONTENT_REGISTRY = (
    ("ocr", "page_ocr_text", SUPPORTING),
    ("tables", "page_table", SUPPORTING),
    ("v1_context", "page_v1_context", GUIDANCE),
    ("v2_context", "page_v2_context", GUIDANCE),
    ("v3_page_intelligence", "page_v3_intelligence", GUIDANCE),
    ("visuals", "page_visual", GUIDANCE),
)


def _page_content_pages(result: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    envelope = result.get("evidence_envelope") if isinstance(result.get("evidence_envelope"), Mapping) else {}
    coverage = envelope.get("coverage") if isinstance(envelope.get("coverage"), Mapping) else {}
    page_content = coverage.get("page_content") if isinstance(coverage.get("page_content"), Mapping) else {}
    pages = page_content.get("pages") if isinstance(page_content.get("pages"), list) else []
    return [p for p in pages if isinstance(p, Mapping)]


def page_content_registry_rows(result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Flatten every page-content record into a citation-registry row. Each row
    references the underlying pack record dict so the registry can stamp its
    citation_id back onto it (making each record separately citable)."""
    rows: List[Dict[str, Any]] = []
    for pack in _page_content_pages(result):
        for section, cls, authority in PAGE_CONTENT_REGISTRY:
            for record in pack.get(section) or []:
                if isinstance(record, Mapping) and record.get("text"):
                    rows.append({"record": record, "class": cls, "authority": authority, "kind": record.get("kind")})
    return rows


def render_page_content_prompt(result: Mapping[str, Any]) -> str:
    """Render the full page-content pack for the single Gemma prompt (not only
    coverage metadata). Each record is labeled with its citation id (when the
    registry has been built) so every page-content sentence can cite its source.
    Returns '' when there is no page content."""
    pages = _page_content_pages(result)
    if not pages:
        return ""

    def _join(rows: Any, limit: int = 700) -> str:
        items = []
        for r in rows or []:
            if not isinstance(r, Mapping) or not r.get("text"):
                continue
            cid = r.get("citation_id")
            tag = f"[{cid}] " if cid else ""
            extra = ""
            if r.get("figure_refs"):
                extra += f" (figure {', '.join(r['figure_refs'])})"
            if r.get("callouts"):
                extra += f" (callouts {', '.join(r['callouts'])})"
            if r.get("ocr_engine"):
                extra += f" (ocr:{r['ocr_engine']})"
            if r.get("layout_reconstruction_text"):
                extra += f" (layout reconstruction: {_compact(r.get('layout_reconstruction_text'), 900)})"
            items.append(f"{tag}{_compact(r.get('text'), limit)}{extra}")
        return " || ".join(items) if items else "none"

    blocks: List[str] = []
    for pack in pages:
        trace = pack.get("source_trace") if isinstance(pack.get("source_trace"), Mapping) else {}
        parts = [str(p.get("part_number")) for p in (pack.get("parts") or []) if isinstance(p, Mapping) and p.get("part_number")]
        conflict_note = "; ".join(
            f"{c.get('field')}: {', '.join(c.get('conflicting_values') or [])}"
            for c in (pack.get("conflicts") or []) if isinstance(c, Mapping)
        )
        blocks.append(
            f"PAGE {pack.get('page_id')} (source_resolved={bool(trace.get('source_resolved'))}):\n"
            f"  OCR text (supporting — literal page text): {_join(pack.get('ocr'), 2400)}\n"
            f"  Table content (supporting): {_join(pack.get('tables'), 1400)}\n"
            f"  V1 context (guidance): {_join(pack.get('v1_context'), 700)}\n"
            f"  V2 context (guidance): {_join(pack.get('v2_context'), 900)}\n"
            f"  V3 intelligence (guidance): {_join(pack.get('v3_page_intelligence'), 1200)}\n"
            f"  Visual understanding (guidance): {_join(pack.get('visuals'), 1800)}\n"
            f"  Related parts: {', '.join(parts) if parts else 'none'}\n"
            f"  Conflicts (unresolved; never resolve to fact): {conflict_note or 'none'}"
        )
    return "\n".join(blocks)
