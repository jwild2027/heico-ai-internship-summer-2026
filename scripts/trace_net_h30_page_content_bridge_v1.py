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
    "multi_question_research",
}

_PAGE_KEYS = ("page_id", "source_page_id", "document_page_id", "page")
_ARTIFACT_CACHE: Dict[Tuple[str, ...], Dict[str, Dict[str, List[Dict[str, Any]]]]] = {}
_LOCK = threading.RLock()


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
    return _fields(raw, kind, "artifact", authority, page_id)


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


def _artifact_paths() -> Dict[str, str]:
    base = os.environ.get("TRACE_NET_REPO", ".")
    default = {
        "v2_context": f"{base}/local_data/organization/trace_net/page_context_v2/trace_net_page_context_v2.json",
        "v3_page_intelligence": f"{base}/local_data/organization/trace_net/v3_page_intelligence/trace_net_v3_page_intelligence_cards_v1.json",
        "tables": f"{base}/local_data/organization/trace_net/table_exact_search_adapter/trace_net_table_exact_search_documents_v1.jsonl",
        "ocr": "",       # configure via env when a per-page OCR artifact is available
        "visuals": "",   # configure via env when a per-page visual artifact is available
    }
    return {
        "v2_context": os.environ.get("TRACE_NET_H30_PAGE_V2_ARTIFACT", default["v2_context"]),
        "v3_page_intelligence": os.environ.get("TRACE_NET_H30_PAGE_V3_ARTIFACT", default["v3_page_intelligence"]),
        "tables": os.environ.get("TRACE_NET_H30_PAGE_TABLE_ARTIFACT", default["tables"]),
        "ocr": os.environ.get("TRACE_NET_H30_PAGE_OCR_ARTIFACT", default["ocr"]),
        "visuals": os.environ.get("TRACE_NET_H30_PAGE_VISUAL_ARTIFACT", default["visuals"]),
    }


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


def _load_artifact_index(path: str) -> Dict[str, List[Dict[str, Any]]]:
    index: Dict[str, List[Dict[str, Any]]] = {}
    if not path or not Path(path).exists():
        return index
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
            pid = ""
            for key in _PAGE_KEYS:
                if row.get(key):
                    pid = str(row.get(key)).strip()
                    break
            if pid:
                index.setdefault(pid, []).append(dict(row))
    except Exception:
        return {}
    return index


def load_page_artifacts() -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    """Load and cache the exact-page-id artifact indexes for fallback."""
    paths = _artifact_paths()
    key = tuple(paths[name] for name in ("v2_context", "v3_page_intelligence", "tables", "ocr", "visuals"))
    with _LOCK:
        if key in _ARTIFACT_CACHE:
            return _ARTIFACT_CACHE[key]
        indexes = {name: _load_artifact_index(path) for name, path in paths.items()}
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
            if current:
                continue
            index = artifacts.get(name) or {}
            for raw in index.get(pid, []) or []:
                if isinstance(raw, Mapping):
                    current.append(_artifact_record(raw, _ARTIFACT_KIND[name], _ARTIFACT_AUTHORITY[name], pid))

    v2, v3, tables, ocr, visuals = (
        sections["v2_context"], sections["v3_page_intelligence"],
        sections["tables"], sections["ocr"], sections["visuals"],
    )
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
        "telemetry": _telemetry(v1, v2, v3, ocr, tables, visuals, exact=True, pid=pid),
    }


def _telemetry(v1, v2, v3, ocr, tables, visuals, *, exact: bool, pid: str = "") -> Dict[str, Any]:
    records = list(v1) + list(v2) + list(v3) + list(ocr) + list(tables) + list(visuals)
    graph_records = sum(1 for r in records if r.get("origin") == "graph")
    artifact_records = sum(1 for r in records if r.get("origin") == "artifact")
    cross_page = sum(
        1 for r in records
        if r.get("page_id") and pid and str(r.get("page_id")) != str(pid)
    )
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

        packs = []
        totals = {
            "v1_record_count": 0, "v2_record_count": 0, "v3_record_count": 0,
            "ocr_record_count": 0, "table_record_count": 0, "visual_record_count": 0,
            "graph_record_count": 0, "artifact_fallback_record_count": 0,
            "cross_page_record_count": 0,
        }
        for pid in page_ids:
            pack = page_content_pack(graph, pid, artifacts=artifacts)
            if not pack.get("found"):
                continue
            packs.append(pack)
            for key in totals:
                totals[key] += int(pack["telemetry"].get(key, 0))
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
            "page_content_bridge_table_chain": list(TABLE_CHAIN),
            "page_content_bridge_visual_chain": list(VISUAL_CHAIN),
            "page_content_bridge_artifact_fallback": True,
            "page_content_bridge_adds_gemma_call": False,
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


def render_page_content_prompt(result: Mapping[str, Any]) -> str:
    """Render the full page-content pack for the single Gemma prompt (not only
    coverage metadata). Returns '' when there is no page content."""
    envelope = result.get("evidence_envelope") if isinstance(result.get("evidence_envelope"), Mapping) else {}
    coverage = envelope.get("coverage") if isinstance(envelope.get("coverage"), Mapping) else {}
    page_content = coverage.get("page_content") if isinstance(coverage.get("page_content"), Mapping) else {}
    pages = page_content.get("pages") if isinstance(page_content.get("pages"), list) else []
    if not pages:
        return ""

    blocks: List[str] = []
    for pack in pages:
        if not isinstance(pack, Mapping):
            continue
        trace = pack.get("source_trace") if isinstance(pack.get("source_trace"), Mapping) else {}

        def _join(key: str, limit: int = 600) -> str:
            rows = pack.get(key) or []
            texts = [_compact(r.get("text"), limit) for r in rows if isinstance(r, Mapping) and r.get("text")]
            return " || ".join(texts) if texts else "none"

        parts = [str(p.get("part_number")) for p in (pack.get("parts") or []) if isinstance(p, Mapping) and p.get("part_number")]
        conflict_note = "; ".join(
            f"{c.get('field')}: {', '.join(c.get('conflicting_values') or [])}"
            for c in (pack.get("conflicts") or []) if isinstance(c, Mapping)
        )
        blocks.append(
            f"PAGE {pack.get('page_id')} (source_resolved={bool(trace.get('source_resolved'))}):\n"
            f"  V1 context (guidance): {_join('v1_context')}\n"
            f"  V2 context (guidance): {_join('v2_context')}\n"
            f"  V3 intelligence (guidance): {_join('v3_page_intelligence')}\n"
            f"  OCR text (supporting): {_join('ocr')}\n"
            f"  Table content (supporting): {_join('tables')}\n"
            f"  Visual understanding (guidance): {_join('visuals')}\n"
            f"  Related parts: {', '.join(parts) if parts else 'none'}\n"
            f"  Conflicts (unresolved; never resolve to fact): {conflict_note or 'none'}"
        )
    return "\n".join(blocks)
