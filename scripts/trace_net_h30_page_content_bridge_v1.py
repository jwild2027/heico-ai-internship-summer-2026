#!/usr/bin/env python3
"""Exact-page content bridge for TRACE-Net H30.

Given a full canonical page id, this bridge assembles a typed page-content
evidence pack by traversing the canonical graph from the EXACT page node to its
linked V2 page-context, V3 page-intelligence, OCR/page-text, table, and visual
records, plus part mentions and source trace. The pack feeds the single Gemma
answer; it never adds a second model call and never mutates any store.

Flow:
    canonical page id
      -> exact graph page (exact-equality; never a similar page)
      -> exact V2 page-context record (edge HAS_CONTEXT_V2, alias HAS_CONTEXT)
      -> exact V3 page-intelligence record (edge HAS_V3_PAGE_INTELLIGENCE)
      -> exact OCR/page text (edge HAS_OCR)
      -> exact table records, when present (edge HAS_TABLE)
      -> exact visual observation, when present (edge HAS_VISUAL)
      -> typed page-content evidence pack (with conflicts surfaced)

Evidence rules:
- OCR, tables, and direct source fields are stronger than generated summaries.
- V2 and V3 are guidance/context; they never independently prove a claim.
- Visual observations remain guidance unless source-resolved.
- Disagreements across V2/V3/OCR/table/visual are surfaced as conflicts and never
  silently resolved to fact.
- V2/V3 guidance cannot prove approval, fit, effectivity, safety, or
  interchangeability (enforced downstream by the dangerous-claim gate).

The mandated graph edge-name contracts HAS_CONTEXT_V2 and HAS_V3_PAGE_INTELLIGENCE
are preserved (traversed by exactly those names; HAS_CONTEXT is accepted as a V2
alias for the current graph build). Enabled with
TRACE_NET_H30_PAGE_CONTENT_BRIDGE_ENABLED=1 (off at the module level).
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence

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

# Mandated edge-name contracts (do not rename). HAS_CONTEXT is accepted as the
# current graph build's V2 alias.
V2_EDGES = ("HAS_CONTEXT_V2", "HAS_CONTEXT")
V3_EDGES = ("HAS_V3_PAGE_INTELLIGENCE",)
OCR_EDGES = ("HAS_OCR", "HAS_OCR_TEXT")
TABLE_EDGES = ("HAS_TABLE", "HAS_TABLE_ROW")
VISUAL_EDGES = ("HAS_VISUAL", "HAS_VISUAL_OBSERVATION")

# Routes for which explaining an exact page adds value.
PAGE_ROUTES = {
    "document_page_navigation",
    "visual_figure_callout_lookup",
    "procedure_task_lookup",
    "warning_caution_note_lookup",
    "ocr_scan_recovery",
    "exact_table_ipl_lookup",
    "multi_question_research",
}


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
            import json

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


def _record(node: Mapping[str, Any], kind: str, authority: str) -> Dict[str, Any]:
    props = node.get("properties") if isinstance(node.get("properties"), Mapping) else {}
    source_resolved = bool(props.get("source_resolved"))
    # Visual is guidance unless source-resolved; V2/V3 are always guidance;
    # OCR/table are stronger than summaries (supporting).
    guidance_only = authority == "guidance" or (kind == "visual" and not source_resolved)
    return {
        "kind": kind,
        "node_id": node.get("node_id"),
        "authority": authority,
        "guidance_only": guidance_only,
        "can_prove_claims": False,
        "text": _compact(
            props.get("summary")
            or props.get("text")
            or props.get("retrieval_summary")
            or props.get("v2_summary")
            or node.get("label"),
            2000,
        ),
        "role": _compact(props.get("role") or props.get("v2_role") or props.get("v3_role"), 200),
        "subrole": _compact(props.get("subrole") or props.get("v2_subrole"), 200),
        "nomenclature": _as_list(props.get("nomenclature")),
        "ata": _compact(props.get("ata_code") or props.get("ata"), 100),
        "figure_refs": _as_list(props.get("figure_refs")),
        "callouts": _as_list(props.get("callouts") or props.get("labels")),
        "part_numbers": _as_list(props.get("part_numbers")),
        "ocr_engine": _compact(props.get("ocr_engine") or props.get("engine"), 100),
        "ocr_confidence": props.get("confidence") if isinstance(props.get("confidence"), (int, float)) else None,
        "source_resolved": source_resolved,
    }


def _collect(graph: Any, page: Mapping[str, Any], edge_names: Sequence[str], kind: str, authority: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for _edge, node in graph.out_neighbors(page["node_id"], edge_names):
        node_id = node.get("node_id")
        if node_id in seen:
            continue
        seen.add(node_id)
        out.append(_record(node, kind, authority))
    return out


def _detect_conflicts(records: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Surface disagreement across page-content records; never resolve to fact."""
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


def page_content_pack(graph: Any, page_id_query: str) -> Dict[str, Any]:
    """Typed page-content evidence pack for the EXACT canonical page id.

    Returns found=False (no page-content evidence) for a nonexistent page and
    never substitutes a similar page. Pure/read-only: it does not mutate the
    graph or any store, and it never calls a model."""
    query = str(page_id_query or "").strip()
    if graph is None or not query:
        return {"available": False, "found": False, "page_id": query,
                "v2": [], "v3": [], "ocr": [], "tables": [], "visuals": [],
                "parts": [], "conflicts": [], "source_trace": {}}

    pages = graph.find_page_nodes(query)  # exact-equality only
    if not pages:
        return {"available": True, "found": False, "page_id": query,
                "v2": [], "v3": [], "ocr": [], "tables": [], "visuals": [],
                "parts": [], "conflicts": [], "source_trace": {}}

    page = pages[0]
    pid = _page_id(page)
    source_links, tiff_files = collect_sources(graph, page)
    v2 = _collect(graph, page, V2_EDGES, "v2_context", "guidance")
    v3 = _collect(graph, page, V3_EDGES, "v3_page_intelligence", "guidance")
    ocr = _collect(graph, page, OCR_EDGES, "ocr", "supporting")
    tables = _collect(graph, page, TABLE_EDGES, "table", "supporting")
    visuals = _collect(graph, page, VISUAL_EDGES, "visual", "guidance")
    parts = collect_page_parts(graph, page)
    conflicts = _detect_conflicts(v2 + v3 + ocr + tables + visuals)

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
        "v2": v2,
        "v3": v3,
        "ocr": ocr,
        "tables": tables,
        "visuals": visuals,
        "parts": parts,
        "conflicts": conflicts,
        # Bridge output is guidance/context; only linked direct/OCR/table records
        # (source-resolved) may support a claim, enforced downstream.
        "guidance_only": True,
        "can_prove_claims": False,
    }


def _page_content_summary(pack: Mapping[str, Any]) -> str:
    parts = []
    if pack.get("v2"):
        parts.append("v2: " + _compact(pack["v2"][0].get("text"), 300))
    if pack.get("v3"):
        parts.append("v3: " + _compact(pack["v3"][0].get("text"), 300))
    if pack.get("ocr"):
        parts.append("ocr: " + _compact(pack["ocr"][0].get("text"), 300))
    if pack.get("visuals"):
        parts.append("visual: " + _compact(pack["visuals"][0].get("text"), 300))
    if pack.get("conflicts"):
        parts.append(f"conflicts: {len(pack['conflicts'])} unresolved")
    return " | ".join(parts) or "page-content records found"


# --- router overlay ----------------------------------------------------------


def install_page_content_bridge(router: MutableMapping[str, Any]) -> None:
    """Attach exact-page content packs to the envelope for page-oriented routes.

    Read-only and additive: it never calls add_unified/add_guided (no upstream or
    model call) and never mutates source data. The pack is placed in
    coverage['page_content'] (fed to the single Gemma answer) plus one citable
    per-page guidance summary, and any conflicts are surfaced.
    """
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

        packs = []
        for pid in page_ids:
            pack = page_content_pack(graph, pid)
            if not pack.get("found"):
                continue
            packs.append(pack)
            # One citable, guidance-only summary per page so the answer can cite
            # the exact page content by id. Full pack goes into coverage below.
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
                    "page_id": pack["page_id"],
                    "page_content_conflict": True,
                    **conflict,
                })

        if packs:
            envelope.coverage["page_content"] = {
                "available": True,
                "pages": packs,
                "page_count": len(packs),
                "guidance_only": True,
                "source_truth_confirmation_required": True,
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
            "page_content_bridge_v2_edge": "HAS_CONTEXT_V2",
            "page_content_bridge_v3_edge": "HAS_V3_PAGE_INTELLIGENCE",
            "page_content_bridge_adds_gemma_call": False,
            "page_content_guidance_only": True,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        })
        return result

    runtime_cls.gather_initial = gather_with_page_content
    runtime_cls.health = health_with_page_content
    router[marker] = True
