#!/usr/bin/env python3
"""Deterministic graph-source retrieval for TRACE-Net H30.

This overlay traverses the canonical retrieval graph
(local_data/organization/graph/graph_nodes.json + graph_edges.json) to connect a
query's exact/partial part identifier, ATA chapter, or nomenclature noun to the
pages and source traces that mention it. It reuses the read-only traversal
primitives in tiff.trace_net_graph_query_helper_v1 and adds the results to the
evidence envelope as guidance-only candidate/navigation leads that carry a
source trace (page id, rescarta URL, tiff path, Dublin Core identity).

It is deliberately fail-closed and read-only:

- The graph connects and locates; it never asserts proof. Every record is
  guidance_only=True, source_truth=False, final_answer_allowed=False. A confirmed
  technical claim must still come from the linked OCR/table/figure/source-trace
  evidence produced by the other tunnels.
- No database, Qdrant, or OpenSearch write is ever performed.
- Functional phrasing (e.g. "item that retains the pin") is not present as text
  in the graph and is not asserted here; only exact/partial identifiers, ATA
  codes, and nomenclature NOUNS (hinge, pin, cover, ...) are traversable.

Enabled with TRACE_NET_H30_GRAPH_RETRIEVAL_ENABLED=1 (off by default at the
module level so unit tests and direct invocation keep prior behavior).
"""
from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple

try:  # Reuse the read-only traversal primitives; import is side-effect free.
    from tiff.trace_net_graph_query_helper_v1 import (
        GraphIndex,
        collect_part_nomenclature,
        extract_edges,
        extract_nodes,
        is_page_node,
        is_part_node,
        load_json_any,
        page_card,
        page_id as _page_id,
        part_number as _part_number,
    )

    _HELPER_AVAILABLE = True
except Exception:  # pragma: no cover - defensive; overlay no-ops if helper absent
    _HELPER_AVAILABLE = False

MODULE = "trace_net_h30_graph_source_retrieval_v1"
PATCH_ID = "trace_net_h30_phase2_graph_source_retrieval_v1"
GRAPH_TUNNEL = "graph_source_traversal"

# Routes for which graph traversal adds value (part/ATA/nomenclature discovery
# and document navigation). Authority and general chat are intentionally excluded.
# multi_question_research is included because a compound request such as "find
# part X and explain its nomenclature, connected page, and source evidence"
# routes here yet still carries an exact/partial/ATA/nomenclature clue whose
# graph-connected part, nomenclature, and source pages must be surfaced.
GRAPH_ROUTES = {
    "exact_identifier_lookup",
    "guided_part_discovery",
    "ata_system_discovery",
    "nomenclature_function_search",
    "exact_table_ipl_lookup",
    "document_page_navigation",
    "visual_figure_callout_lookup",
    "procedure_task_lookup",
    "warning_caution_note_lookup",
    "high_degree_entity_aggregation",
    "graph_relationship_reasoning",
    "semantic_discovery",
    "multi_question_research",
}

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
# Common IPL/structure words that carry little discriminating signal for a
# nomenclature-noun search. Kept small on purpose.
_NOMENCLATURE_STOPWORDS = {
    "THE", "AND", "FOR", "WITH", "ASSY", "ASSEMBLY", "REF", "SEE",
}

_GRAPH_CACHE: Dict[Tuple[str, str], Optional["GraphIndex"]] = {}
_NOMEN_CACHE: Dict[int, Dict[str, set]] = {}
_LOCK = threading.RLock()


# --- configuration ----------------------------------------------------------


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def graph_retrieval_enabled() -> bool:
    return _bool_env("TRACE_NET_H30_GRAPH_RETRIEVAL_ENABLED", False)


def _int_env(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(low, min(value, high))


def _graph_paths() -> Tuple[str, str]:
    nodes = os.environ.get(
        "TRACE_NET_H30_GRAPH_NODES_PATH",
        "local_data/organization/graph/graph_nodes.json",
    )
    edges = os.environ.get(
        "TRACE_NET_H30_GRAPH_EDGES_PATH",
        "local_data/organization/graph/graph_edges.json",
    )
    return nodes, edges


def _limits() -> Dict[str, int]:
    return {
        "max_parts": _int_env("TRACE_NET_H30_GRAPH_MAX_PARTS", 10, 1, 50),
        "max_pages_per_part": _int_env("TRACE_NET_H30_GRAPH_MAX_PAGES_PER_PART", 5, 1, 25),
        "max_ata_pages": _int_env("TRACE_NET_H30_GRAPH_MAX_ATA_PAGES", 15, 1, 100),
        "max_nomenclature_parts": _int_env("TRACE_NET_H30_GRAPH_MAX_NOMENCLATURE_PARTS", 10, 1, 50),
    }


# --- graph loading (cached) --------------------------------------------------


def _load_graph() -> Optional["GraphIndex"]:
    if not _HELPER_AVAILABLE:
        return None
    nodes_path, edges_path = _graph_paths()
    key = (nodes_path, edges_path)
    with _LOCK:
        if key in _GRAPH_CACHE:
            return _GRAPH_CACHE[key]
        graph: Optional[GraphIndex] = None
        try:
            if Path(nodes_path).exists() and Path(edges_path).exists():
                nodes = extract_nodes(load_json_any(nodes_path))
                edges = extract_edges(load_json_any(edges_path))
                graph = GraphIndex(nodes, edges)
        except Exception:
            graph = None
        _GRAPH_CACHE[key] = graph
        return graph


def _tokens(text: str) -> List[str]:
    out: List[str] = []
    for raw in _TOKEN_RE.findall(str(text or "").upper()):
        if len(raw) < 3 or raw.isdigit() or raw in _NOMENCLATURE_STOPWORDS:
            continue
        out.append(raw)
    return out


def _nomenclature_index(graph: "GraphIndex") -> Dict[str, set]:
    """token -> set(part_node_id), built from nomenclature nodes and the
    nomenclature property carried on part nodes. Cached per graph instance."""
    with _LOCK:
        cached = _NOMEN_CACHE.get(id(graph))
        if cached is not None:
            return cached
        index: Dict[str, set] = {}

        def add(token: str, node_id: str) -> None:
            if token and node_id:
                index.setdefault(token, set()).add(node_id)

        for node in graph.nodes:
            node_type = str(node.get("node_type") or "").lower()
            props = node.get("properties") if isinstance(node.get("properties"), Mapping) else {}
            if node_type == "nomenclature":
                label = node.get("label") or props.get("text") or ""
                for _edge, part in graph.in_neighbors(node["node_id"], ["HAS_NOMENCLATURE"]):
                    if is_part_node(part):
                        for token in _tokens(label):
                            add(token, part["node_id"])
            elif is_part_node(node):
                for token in _tokens(props.get("nomenclature") or ""):
                    add(token, node["node_id"])
        _NOMEN_CACHE[id(graph)] = index
        return index


# --- record construction -----------------------------------------------------


def _part_pages(graph: "GraphIndex", part: Mapping[str, Any], limit: int) -> List[Dict[str, Any]]:
    cards: List[Dict[str, Any]] = []
    seen = set()
    for _edge, page in graph.out_neighbors(part["node_id"], ["APPEARS_ON"]):
        if not is_page_node(page):
            continue
        pid = _page_id(page)
        if pid in seen:
            continue
        seen.add(pid)
        cards.append(page_card(graph, page))
        if len(cards) >= limit:
            break
    return cards


def _candidate_record(
    graph: "GraphIndex",
    part: Mapping[str, Any],
    *,
    match_reason: str,
    max_pages_per_part: int,
) -> Dict[str, Any]:
    pn = _part_number(part) or ""
    pages = _part_pages(graph, part, max_pages_per_part)
    nomenclature = collect_part_nomenclature(graph, part)
    if not nomenclature:
        props = part.get("properties") if isinstance(part.get("properties"), Mapping) else {}
        if props.get("nomenclature"):
            nomenclature = [str(props.get("nomenclature"))]
    first = pages[0] if pages else {}
    ata_codes = sorted({code for card in pages for code in (card.get("ata_codes") or [])})
    return {
        "candidate_value": pn,
        "part_number": pn,
        "nomenclature": nomenclature,
        "page_id": first.get("page_id", ""),
        "ata": ata_codes[0] if ata_codes else "",
        "ata_codes": ata_codes,
        "graph_pages": pages,
        "graph_match_reason": match_reason,
        "graph_source_traversal": True,
        # Guidance-only: the graph locates and connects; it is never proof.
        "guidance_only": True,
        "source_truth": False,
        "final_answer_allowed": False,
        "source_resolved": any(card.get("source_resolved") for card in pages),
    }


def _normalize_identifier(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _merge_graph_record(
    existing: MutableMapping[str, Any],
    graph_record: Mapping[str, Any],
) -> None:
    """Merge a graph candidate into an existing candidate row, in place.

    Candidate identity is the normalized part number: the same part found by
    both base retrieval and the graph is a single row that gains the graph's
    connected pages, nomenclature, ATA codes, and source-resolution status. No
    duplicate row is created.
    """
    pages = existing.get("graph_pages")
    if not isinstance(pages, list):
        pages = []
    seen_pages = {p.get("page_id") for p in pages if isinstance(p, Mapping)}
    for page in graph_record.get("graph_pages") or []:
        if isinstance(page, Mapping) and page.get("page_id") not in seen_pages:
            pages.append(page)
            seen_pages.add(page.get("page_id"))
    existing["graph_pages"] = pages

    nomenclature = list(existing.get("nomenclature") or [])
    for name in graph_record.get("nomenclature") or []:
        if name not in nomenclature:
            nomenclature.append(name)
    existing["nomenclature"] = nomenclature

    ata_codes = list(existing.get("ata_codes") or [])
    for code in graph_record.get("ata_codes") or []:
        if code not in ata_codes:
            ata_codes.append(code)
    if ata_codes:
        existing["ata_codes"] = ata_codes
    if not existing.get("page_id") and graph_record.get("page_id"):
        existing["page_id"] = graph_record.get("page_id")
    if not existing.get("ata") and graph_record.get("ata"):
        existing["ata"] = graph_record.get("ata")

    # Preserve or upgrade source resolution; mark graph provenance.
    existing["source_resolved"] = bool(existing.get("source_resolved")) or bool(
        graph_record.get("source_resolved")
    )
    existing["graph_source_traversal"] = True

    reasons = existing.get("graph_match_reasons")
    if not isinstance(reasons, list):
        reasons = []
        if existing.get("graph_match_reason"):
            reasons.append(existing.get("graph_match_reason"))
    reason = graph_record.get("graph_match_reason")
    if reason and reason not in reasons:
        reasons.append(reason)
    existing["graph_match_reasons"] = reasons


# --- public retrieval --------------------------------------------------------


def graph_retrieve(
    *,
    exact_parts: Sequence[str] = (),
    fragments: Sequence[str] = (),
    ata_codes: Sequence[str] = (),
    nomenclature_terms: Sequence[str] = (),
    page_ids: Sequence[str] = (),
) -> Dict[str, Any]:
    """Deterministic traversal. Returns candidate parts (with page/source trace)
    and ATA/page navigation-lead page cards. When a full canonical page id is
    supplied it PINS that exact page (exact-equality lookup), returning that
    page's source trace and part mentions rather than semantically similar
    pages. Never raises; returns available=False when the graph artifact is
    missing so callers can no-op safely."""
    graph = _load_graph()
    if graph is None:
        return {"available": False, "candidates": [], "navigation_leads": [], "stats": {}}

    limits = _limits()
    candidates: List[Dict[str, Any]] = []
    seen_parts: set = set()

    def add_part(part: Mapping[str, Any], reason: str) -> None:
        node_id = part.get("node_id")
        if not node_id or node_id in seen_parts:
            return
        if len(candidates) >= limits["max_parts"]:
            return
        seen_parts.add(node_id)
        candidates.append(
            _candidate_record(
                graph,
                part,
                match_reason=reason,
                max_pages_per_part=limits["max_pages_per_part"],
            )
        )

    for value in exact_parts:
        for part in graph.find_part_nodes(value):
            add_part(part, "exact_part")
    for value in fragments:
        for part in graph.find_part_nodes(value):
            add_part(part, "partial_fragment")

    if nomenclature_terms and len(candidates) < limits["max_parts"]:
        index = _nomenclature_index(graph)
        scores: Dict[str, int] = {}
        for term in nomenclature_terms:
            for token in _tokens(term):
                for node_id in index.get(token, ()):  # type: ignore[union-attr]
                    scores[node_id] = scores.get(node_id, 0) + 1
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        for node_id, _score in ranked[: limits["max_nomenclature_parts"]]:
            node = graph.get(node_id)
            if node is not None:
                add_part(node, "nomenclature_noun")

    navigation_leads: List[Dict[str, Any]] = []
    seen_pages: set = set()

    # Exact page-id pinning: a supplied canonical page id returns THAT page's
    # source trace and part mentions (find_page_nodes is exact-equality), never
    # a semantically similar page. A nonexistent page id resolves to nothing.
    pinned = 0
    for pid_query in page_ids:
        for page in graph.find_page_nodes(pid_query):
            pid = _page_id(page)
            if pid in seen_pages:
                continue
            seen_pages.add(pid)
            navigation_leads.append(page_card(graph, page, include_parts=True))
            pinned += 1

    for code in ata_codes:
        for page in graph.page_nodes_with_ata(code):
            pid = _page_id(page)
            if pid in seen_pages:
                continue
            seen_pages.add(pid)
            navigation_leads.append(page_card(graph, page))
            if len(navigation_leads) >= limits["max_ata_pages"]:
                break

    return {
        "available": True,
        "candidates": candidates,
        "navigation_leads": navigation_leads,
        "stats": {
            "candidate_count": len(candidates),
            "navigation_lead_count": len(navigation_leads),
            "pinned_page_count": pinned,
            "graph_node_count": len(graph.nodes),
            "graph_edge_count": len(graph.edges),
        },
    }


# --- router overlay ----------------------------------------------------------


def _atom_list(atoms: Any, name: str) -> List[str]:
    value = getattr(atoms, name, None)
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def install_graph_source_retrieval(router: MutableMapping[str, Any]) -> None:
    """Wrap gather_initial to append deterministic graph-source evidence.

    Runs after the base/overlay retrieval so it can add complementary
    graph-connected candidates and navigation leads without altering existing
    records. Gated by TRACE_NET_H30_GRAPH_RETRIEVAL_ENABLED.
    """
    marker = "_TRACE_NET_H30_GRAPH_SOURCE_RETRIEVAL_V1_INSTALLED"
    if router.get(marker):
        return

    runtime_cls = router["CognitiveRuntime"]
    original_gather = runtime_cls.gather_initial
    original_health = runtime_cls.health
    candidate_matches_atoms = router.get("candidate_matches_atoms")
    is_garbage_candidate = router.get("is_garbage_candidate")
    normalize_identifier = router.get("normalize_identifier") or _normalize_identifier

    def _declare_tunnel(plan: Any, label: str) -> None:
        tunnels = getattr(plan, "retrieval_tunnels", None)
        if isinstance(tunnels, list) and label not in tunnels:
            tunnels.append(label)

    def gather_with_graph(self: Any, plan: Any, atoms: Any) -> Any:
        envelope = original_gather(self, plan, atoms)
        if not graph_retrieval_enabled():
            return envelope
        route = str(getattr(plan, "primary_route", "") or "")
        if route not in GRAPH_ROUTES:
            return envelope

        exact_parts = _atom_list(atoms, "exact_part_numbers")
        fragments = [
            frag
            for frag in (
                getattr(atoms, "part_prefix", None),
                getattr(atoms, "part_contains", None),
                getattr(atoms, "part_suffix", None),
            )
            if frag
        ]
        ata_codes = _atom_list(atoms, "ata_exact")
        prefix = getattr(atoms, "ata_prefix", None)
        if prefix:
            ata_codes = ata_codes + [str(prefix)]
        nomenclature_terms = _atom_list(atoms, "nomenclature_terms") + _atom_list(
            atoms, "assembly_context"
        )
        page_id_atoms = _atom_list(atoms, "page_ids")

        if not (exact_parts or fragments or ata_codes or nomenclature_terms or page_id_atoms):
            return envelope

        found = graph_retrieve(
            exact_parts=exact_parts,
            fragments=fragments,
            ata_codes=ata_codes,
            nomenclature_terms=nomenclature_terms,
            page_ids=page_id_atoms,
        )
        if not found.get("available"):
            envelope.coverage["graph_source_traversal"] = {"available": False}
            return envelope

        # Add graph candidate parts, but only those consistent with an explicit
        # identifier clue (so the deterministic critic's clue-fidelity check is
        # never violated) and that are not garbage tokens. Candidate identity is
        # the normalized part number: a graph record for a part already present
        # in the envelope is MERGED into that row (union pages/nomenclature/ATA,
        # upgrade source_resolved) rather than appended as a page/ATA duplicate.
        index: Dict[str, MutableMapping[str, Any]] = {}
        for row in envelope.candidate_evidence:
            if isinstance(row, MutableMapping):
                key = normalize_identifier(row.get("candidate_value"))
                if key and key not in index:
                    index[key] = row

        added = 0
        merged = 0
        for record in found["candidates"]:
            value = str(record.get("candidate_value") or "")
            if not value:
                continue
            if callable(is_garbage_candidate) and is_garbage_candidate(value):
                continue
            if callable(candidate_matches_atoms) and not candidate_matches_atoms(value, atoms):
                continue
            key = normalize_identifier(value)
            if not key:
                continue
            existing = index.get(key)
            if existing is not None:
                _merge_graph_record(existing, record)
                merged += 1
            else:
                new_row = dict(record)
                new_row["graph_match_reasons"] = (
                    [new_row["graph_match_reason"]]
                    if new_row.get("graph_match_reason")
                    else []
                )
                envelope.candidate_evidence.append(new_row)
                index[key] = new_row
                added += 1

        # Navigation leads (page cards with source trace) go into coverage so the
        # writer prompt and page-citation allow-list can use them without being
        # treated as part candidates.
        leads = list(found.get("navigation_leads") or [])
        if leads:
            existing = envelope.coverage.get("navigation_leads")
            if not isinstance(existing, list):
                existing = []
            envelope.coverage["navigation_leads"] = existing + leads

        envelope.coverage["graph_source_traversal"] = {
            "available": True,
            "candidates_added": added,
            "candidates_merged": merged,
            "navigation_leads": len(leads),
            "stats": found.get("stats", {}),
            "guidance_only": True,
            "source_truth_confirmation_required": True,
        }
        envelope.coverage["candidate_evidence_count"] = len(envelope.candidate_evidence)
        if GRAPH_TUNNEL not in envelope.retrieval_tunnels_used:
            envelope.retrieval_tunnels_used.append(GRAPH_TUNNEL)
        _declare_tunnel(plan, GRAPH_TUNNEL)
        return envelope

    def health_with_graph(self: Any) -> Dict[str, Any]:
        result = dict(original_health(self))
        graph = _load_graph() if graph_retrieval_enabled() else None
        result.update({
            "graph_source_retrieval_enabled": graph_retrieval_enabled(),
            "graph_source_retrieval_helper_available": _HELPER_AVAILABLE,
            "graph_source_retrieval_loaded": graph is not None,
            "graph_source_retrieval_node_count": len(graph.nodes) if graph else 0,
            "graph_source_traversal_is_guidance_only": True,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        })
        return result

    runtime_cls.gather_initial = gather_with_graph
    runtime_cls.health = health_with_graph
    router[marker] = True
