#!/usr/bin/env python3
"""TRACE-Net H30 unified cognitive router v1.

This read-only orchestration layer sits above the existing TRACE-Net normal,
guided, and visual/unified services. It adds:

- explicit query-atom extraction (ATA clues cannot become part prefixes)
- a registry containing every planned route family
- multi-tunnel retrieval instead of one-route-or-fail behavior
- a standardized evidence envelope
- universal Self-RAG criticism
- bounded CRAG repair
- deterministic fail-closed rendering

The service never writes source truth, Postgres, Qdrant, or OpenSearch. Candidate,
semantic, visual, graph, and summary evidence remains guidance until resolved to
direct citation-ready source evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from scripts.trace_net_h30_answer_boundary_v1 import enforce_h30_answer_boundaries
from scripts.trace_net_h30_engram_policy_compiler_v1 import (
    build_working_memory,
    compile_engram_policy,
    refresh_working_memory,
)
from scripts.trace_net_h30_retrieval_completion_v1 import install_retrieval_completion
from scripts.trace_net_h30_engram_critic_repair_v1 import install_engram_critic_repair
from scripts.trace_net_h30_user_facing_renderer_v1 import install_user_facing_renderer
from scripts.trace_net_h30_navigation_latency_fastpath_v1 import install_navigation_latency_fastpath
from scripts.trace_net_h30_part_intent_source_resolution_v1 import install_part_intent_source_resolution
from scripts.trace_net_h30_shadow_planner_v1 import install_shadow_planner
from scripts.trace_net_h30_validated_planner_execution_v1 import install_validated_planner_execution
from scripts.trace_net_h30_engram_skill_shadow_v1 import install_engram_skill_shadow
from scripts.trace_net_h30_typed_evidence_envelope_v1 import install_typed_evidence_envelope
from scripts.trace_net_h30_claim_ready_evidence_v1 import install_claim_ready_evidence
from scripts.trace_net_h30_graph_source_retrieval_v1 import install_graph_source_retrieval
from scripts.trace_net_h30_page_content_bridge_v1 import install_page_content_bridge
from scripts.trace_net_h30_cognitive_precision_v1 import (
    decompose_claim_queries,
    explicit_semantic_intent,
    filter_entity_consistent,
    has_any_phrase as precision_has_any_phrase,
    select_engram_memory,
    specialized_route_queries,
    valid_identifier_fragment,
)

MODULE = "trace_net_cognitive_router_v1"
PATCH_ID = "trace_net_h30_retrieval_completion_v2"
MODEL_ID = "trace-net-cognitive-router-v1"

PART_EXACT_RE = re.compile(r"\b\d{2,3}-\d{5}(?:-\d{3})?\b", re.I)
ATA_EXACT_RE = re.compile(r"\b(?:ATA\s*)?(\d{2}-\d{2}-\d{2})\b", re.I)
PAGE_RE = re.compile(r"\bt_p_[A-Za-z0-9_]+\b", re.I)
FIGURE_RE = re.compile(r"\b(?:figure|fig\.?)[\s#:.-]*(\d{1,4})(?:\s+sheet\s+(\d{1,3}))?\b", re.I)
ITEM_RE = re.compile(r"\bitem[\s#:.-]*(\d{1,4})\b", re.I)
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-/]*")

GENERAL_CHAT_PATTERNS = (
    r"^(?:hi|hello|hey|good\s+(?:morning|afternoon|evening)|howdy)[!.?\s]*$",
    r"^(?:thanks|thank\s+you|thank\s+you\s+very\s+much)[!.?\s]*$",
    r"^(?:what\s+can\s+you\s+do|help|how\s+do\s+i\s+use\s+trace[- ]?net)[?.!\s]*$",
)

TECHNICAL_TERMS = {
    "part", "p/n", "pn", "ata", "manual", "figure", "diagram", "table",
    "ipl", "page", "warning", "caution", "procedure", "install", "remove",
    "replacement", "effectivity", "interchangeable", "aircraft", "assembly",
    "component", "nomenclature", "callout", "revision", "vendor",
}

VISUAL_TERMS = {
    "diagram", "figure", "fig", "image", "drawing", "illustration", "callout",
    "schematic", "exploded", "visual", "view",
}
TABLE_TERMS = {"table", "ipl", "illustrated parts list", "row", "column", "item"}
PROCEDURE_TERMS = {
    "procedure", "steps", "step", "remove", "removal", "install", "installation",
    "installed", "removed", "assemble", "disassemble", "replace", "tools required",
    "task",
}
WARNING_TERMS = {
    "warning", "warnings", "caution", "cautions", "note", "notes",
    "precaution", "hazard", "safety",
}
AUTHORITY_TERMS = {
    "interchangeable", "interchangeability", "approved", "approved replacement", "approved for",
    "safe to install", "fit approval", "fits", "fitment", "effectivity",
    "eligibility", "eligible", "installation authority", "applicability",
}
NAVIGATION_TERMS = {
    "where is", "which page", "take me to", "nearby pages", "first page",
    "find the page", "where does", "location in the manual",
    "which source document", "source document and page",
}
GRAPH_TERMS = {
    "contains this part", "assembly contains", "connected to", "relationship",
    "mentioned together", "references this", "what assembly", "linked to",
    "parent assembly",
}
SEMANTIC_TERMS = {
    "about", "related to", "discusses", "pages on", "something about", "topic",
}
COMPARE_TERMS = {"compare", "both manuals", "between revisions", "difference between"}
CONFLICT_TERMS = {
    "conflict", "conflicts", "conflicting", "contradiction", "contradict",
    "disagree", "disagrees", "different numbers", "mismatch",
}
OCR_TERMS = {
    "blurry", "scan", "scanned", "ocr", "read the image", "hard to read", "faint",
}
AGGREGATE_TERMS = {
    "every document", "all references", "all pages", "across the manuals",
    "every page", "summarize all", "where is this used",
}
NOMENCLATURE_TERMS = {
    "ring", "locking ring", "retaining ring", "bracket", "latch", "pin", "bolt",
    "screw", "fastener", "fitting", "cover", "panel", "seat", "armrest",
    "tray table", "table", "hinge", "clip", "spring", "washer", "nut",
    "ashtray", "bearing", "support rail", "rail", "buckle", "actuator",
    "switch", "valve", "hose", "connector", "clamp", "lever",
}

AUTHORITY_FIELD_HINTS = {
    "approval", "approved_replacement", "interchange", "interchangeability",
    "effectivity", "eligibility", "installation_authority", "applicability",
}

GARBAGE_CANDIDATE_WORDS = {
    "LIST", "VENDORS", "VENDOR", "NUMERICAL", "LEP", "INDEX", "TOC",
    "CONTENTS", "PAGE", "PAGES", "FIGURE", "TABLE", "REVISION", "REV",
}

ALL_ROUTES: Tuple[str, ...] = (
    "safe_general_chat",
    "exact_identifier_lookup",
    "guided_part_discovery",
    "ata_system_discovery",
    "nomenclature_function_search",
    "exact_table_ipl_lookup",
    "visual_figure_callout_lookup",
    "procedure_task_lookup",
    "warning_caution_note_lookup",
    "authority_eligibility_verification",
    "document_page_navigation",
    "graph_relationship_reasoning",
    "semantic_discovery",
    "cross_source_comparison",
    "contradiction_resolution",
    "ocr_scan_recovery",
    "high_degree_entity_aggregation",
    "multi_question_research",
    "clarification_no_evidence",
)


@dataclass
class QueryAtoms:
    latest_query: str
    normalized_query: str
    exact_part_numbers: List[str] = field(default_factory=list)
    ata_exact: List[str] = field(default_factory=list)
    ata_prefix: Optional[str] = None
    part_prefix: Optional[str] = None
    part_suffix: Optional[str] = None
    part_contains: Optional[str] = None
    identifier_mode: str = "none"
    normalized_identifier: str = ""
    family_identifier: Optional[str] = None
    allow_family_expansion: bool = False
    allow_partial_candidates: bool = False
    explicit_partial_wording: bool = False
    page_ids: List[str] = field(default_factory=list)
    figures: List[str] = field(default_factory=list)
    items: List[str] = field(default_factory=list)
    nomenclature_terms: List[str] = field(default_factory=list)
    assembly_context: List[str] = field(default_factory=list)
    manufacturer: Optional[str] = None
    visual_requested: bool = False
    table_requested: bool = False
    procedure_requested: bool = False
    warning_requested: bool = False
    authority_requested: bool = False
    navigation_requested: bool = False
    graph_requested: bool = False
    comparison_requested: bool = False
    contradiction_requested: bool = False
    ocr_requested: bool = False
    aggregate_requested: bool = False
    general_chat: bool = False
    multi_question: bool = False
    requested_claims: List[str] = field(default_factory=list)


@dataclass
class RoutePlan:
    primary_route: str
    secondary_routes: List[str]
    retrieval_tunnels: List[str]
    authority_required: bool
    repair_budget: int
    rationale: List[str]
    engram_policy: Dict[str, Any] = field(default_factory=dict)
    working_memory: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceEnvelope:
    route: str
    query_atoms: Dict[str, Any]
    retrieval_tunnels_used: List[str] = field(default_factory=list)
    direct_evidence: List[Dict[str, Any]] = field(default_factory=list)
    candidate_evidence: List[Dict[str, Any]] = field(default_factory=list)
    semantic_guidance: List[Dict[str, Any]] = field(default_factory=list)
    visual_guidance: List[Dict[str, Any]] = field(default_factory=list)
    authority_evidence: List[Dict[str, Any]] = field(default_factory=list)
    contradictions: List[Dict[str, Any]] = field(default_factory=list)
    uncertainties: List[str] = field(default_factory=list)
    coverage: Dict[str, Any] = field(default_factory=dict)
    upstream_results: List[Dict[str, Any]] = field(default_factory=list)
    crag_repairs: List[Dict[str, Any]] = field(default_factory=list)
    source_resolution: List[Dict[str, Any]] = field(default_factory=list)
    claim_evidence: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    safety_contract: Dict[str, Any] = field(default_factory=lambda: {
        "read_only": True,
        "answer_permission": False,
        "final_answer_allowed": False,
        "source_truth_mutation_allowed": False,
        "qdrant_is_guidance_not_proof": True,
        "visual_is_guidance_not_proof": True,
        "candidate_discovery_is_not_final_identification": True,
        "engram_is_behavior_policy_not_source_truth": True,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
    })


def compact(value: Any, limit: int = 4000) -> str:
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


def normalize_identifier(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def unique_dicts(rows: Iterable[Mapping[str, Any]], keys: Sequence[str]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    seen = set()
    for raw in rows:
        row = dict(raw)
        key = tuple(compact(row.get(name), 1000).upper() for name in keys)
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def extract_latest_user(payload: Mapping[str, Any]) -> str:
    for key in ("query", "question", "input", "prompt"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    messages = payload.get("messages")
    if isinstance(messages, list):
        for message in reversed(messages):
            if not isinstance(message, Mapping) or str(message.get("role", "")).lower() != "user":
                continue
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, Mapping):
                        text = block.get("text") or block.get("content")
                        if text:
                            parts.append(str(text))
                return "\n".join(parts).strip()
    return ""


def has_any_phrase(text: str, phrases: Iterable[str]) -> bool:
    low = text.lower()
    return any(phrase in low for phrase in phrases)


def extract_query_atoms(query: str) -> QueryAtoms:
    latest = query.strip()
    low = re.sub(r"\s+", " ", latest.lower()).strip()
    tokens = set(TOKEN_RE.findall(low))

    exact_parts = list(dict.fromkeys(p.upper() for p in PART_EXACT_RE.findall(latest)))
    ata_exact = list(dict.fromkeys(m.upper() for m in ATA_EXACT_RE.findall(latest)))
    page_ids = list(dict.fromkeys(PAGE_RE.findall(latest)))
    figures = [
        "figure " + match.group(1) + (" sheet " + match.group(2) if match.group(2) else "")
        for match in FIGURE_RE.finditer(latest)
    ]
    items = [match.group(1) for match in ITEM_RE.finditer(latest)]

    # Entity-bound ATA prefix extraction. The word ATA/chapter/system must be near
    # the prefix language; this prevents ATA 25 from becoming part_prefix=25.
    ata_prefix: Optional[str] = None
    ata_patterns = (
        r"\bata(?:\s+(?:number|chapter|code))?\s*(?:starts?|begins?|prefix(?:ed)?)?\s*(?:with|is|=|:)?\s*(\d{2})(?!\d)",
        r"\b(?:ata|chapter)\s+(\d{2})(?![-\d])",
        r"\b(?:starts?|begins?)\s+with\s+(\d{2})(?!\d).{0,20}\bata\b",
    )
    for pattern in ata_patterns:
        match = re.search(pattern, low, re.I)
        if match:
            ata_prefix = match.group(1)
            break
    if not ata_prefix and ata_exact:
        ata_prefix = ata_exact[0][:2]

    part_prefix: Optional[str] = None
    part_contains: Optional[str] = None
    part_suffix: Optional[str] = None

    if not ata_prefix:
        prefix_patterns = (
            r"\b(?:p/?n|part(?:\s+number)?|component(?:\s+number)?)\b.{0,35}?\b(?:starts?|begins?|prefix(?:ed)?)\b\s*(?:with\s+)?([A-Za-z0-9-]{2,16})",
            r"\b(?:starts?|begins?)\s+with\s+([A-Za-z0-9-]{2,16}).{0,35}\b(?:p/?n|part(?:\s+number)?)\b",
        )
        for pattern in prefix_patterns:
            match = re.search(pattern, latest, re.I)
            if match:
                part_prefix = match.group(1).strip(".,;: ").upper()
                break

    contains_patterns = (
        r"\b(?:p/?n|part(?:\s+number)?|component(?:\s+number)?)\b.{0,35}?\bcontains?\b.{0,15}?([A-Za-z0-9-]{2,16})",
        r"\bcontains?\s+([A-Za-z0-9-]{2,16}).{0,35}\b(?:p/?n|part(?:\s+number)?)\b",
    )
    for pattern in contains_patterns:
        match = re.search(pattern, latest, re.I)
        if match:
            part_contains = match.group(1).strip(".,;: ").upper()
            break

    suffix_patterns = (
        r"\b(?:p/?n|part(?:\s+number)?)\b.{0,35}?\b(?:ends?|suffix)\b.{0,15}?([A-Za-z0-9-]{2,16})",
        r"\bends?\s+with\s+([A-Za-z0-9-]{2,16}).{0,35}\b(?:p/?n|part(?:\s+number)?)\b",
    )
    for pattern in suffix_patterns:
        match = re.search(pattern, latest, re.I)
        if match:
            part_suffix = match.group(1).strip(".,;: ").upper()
            break

    # Reject prose accidentally captured by permissive proximity regexes.
    if part_prefix and not valid_identifier_fragment(part_prefix):
        part_prefix = None
    if part_contains and not valid_identifier_fragment(part_contains):
        part_contains = None
    if part_suffix and not valid_identifier_fragment(part_suffix):
        part_suffix = None

    manufacturer = None
    for name in ("Honeywell", "Embraer", "Collins", "Safran", "Boeing", "Airbus", "Recaro"):
        if name.lower() in low:
            manufacturer = name
            break

    nomenclature_terms = sorted(
        {term for term in NOMENCLATURE_TERMS if precision_has_any_phrase(low, (term,))},
        key=lambda value: (-len(value), value),
    )
    assembly_context = sorted(
        {
            term
            for term in ("seat", "seat assembly", "armrest", "tray table", "cabin", "panel", "door", "galley")
            if precision_has_any_phrase(low, (term,))
        },
        key=lambda value: (-len(value), value),
    )

    general_chat = any(re.fullmatch(pattern, low, re.I) for pattern in GENERAL_CHAT_PATTERNS)
    if general_chat and any(term in tokens for term in TECHNICAL_TERMS):
        general_chat = False

    visual_requested = precision_has_any_phrase(low, VISUAL_TERMS)
    table_requested = precision_has_any_phrase(low, TABLE_TERMS)
    procedure_requested = precision_has_any_phrase(low, PROCEDURE_TERMS)
    warning_requested = precision_has_any_phrase(low, WARNING_TERMS)
    authority_requested = precision_has_any_phrase(low, AUTHORITY_TERMS)
    navigation_requested = precision_has_any_phrase(low, NAVIGATION_TERMS)
    graph_requested = precision_has_any_phrase(low, GRAPH_TERMS)
    comparison_requested = precision_has_any_phrase(low, COMPARE_TERMS)
    contradiction_requested = precision_has_any_phrase(low, CONFLICT_TERMS)
    ocr_requested = precision_has_any_phrase(low, OCR_TERMS)
    aggregate_requested = precision_has_any_phrase(low, AGGREGATE_TERMS)

    requested_claims: List[str] = []
    for name, active in (
        ("exact_identifier", bool(exact_parts or page_ids)),
        ("ata_system", bool(ata_prefix or ata_exact)),
        ("visual_identity", visual_requested),
        ("table_value", table_requested),
        ("procedure", procedure_requested),
        ("warning", warning_requested),
        ("authority", authority_requested),
        ("comparison", comparison_requested),
        ("relationship", graph_requested),
    ):
        if active:
            requested_claims.append(name)

    # Multi-question means multiple materially different claim types, not merely
    # a long sentence with several descriptive clues.
    multi_question = len(set(requested_claims)) >= 2 and any(
        connector in low for connector in (" and ", ";", " also ", " then ", " plus ")
    )

    return QueryAtoms(
        latest_query=latest,
        normalized_query=low,
        exact_part_numbers=exact_parts,
        ata_exact=ata_exact,
        ata_prefix=ata_prefix,
        part_prefix=part_prefix,
        part_suffix=part_suffix,
        part_contains=part_contains,
        page_ids=page_ids,
        figures=figures,
        items=items,
        nomenclature_terms=nomenclature_terms,
        assembly_context=assembly_context,
        manufacturer=manufacturer,
        visual_requested=visual_requested,
        table_requested=table_requested,
        procedure_requested=procedure_requested,
        warning_requested=warning_requested,
        authority_requested=authority_requested,
        navigation_requested=navigation_requested,
        graph_requested=graph_requested,
        comparison_requested=comparison_requested,
        contradiction_requested=contradiction_requested,
        ocr_requested=ocr_requested,
        aggregate_requested=aggregate_requested,
        general_chat=general_chat,
        multi_question=multi_question,
        requested_claims=requested_claims,
    )


def plan_route(atoms: QueryAtoms) -> RoutePlan:
    low = atoms.normalized_query
    rationale: List[str] = []
    secondary: List[str] = []

    if atoms.general_chat:
        return RoutePlan(
            primary_route="safe_general_chat",
            secondary_routes=[],
            retrieval_tunnels=["restricted_conversation_template"],
            authority_required=False,
            repair_budget=0,
            rationale=["query matches a narrow nontechnical conversational allow-list"],
        )
    # Specialized single-intent signals (conflict resolution, scan recovery) take
    # precedence over the multi-question heuristic when there is no strong
    # independent claim: "the OCR and table disagree" or "the scan is blurry and
    # the table is hard to read" is one intent, not two. But an exact identifier
    # (or page id) alongside those signals IS a genuine second claim and stays
    # multi-question (e.g. "find part 120-... and recover its OCR labels").
    strong_multi = bool(
        atoms.multi_question and (atoms.exact_part_numbers or atoms.page_ids)
    )
    if atoms.contradiction_requested and not strong_multi:
        route = "contradiction_resolution"
        rationale.append("query explicitly asks about conflicting or disagreeing evidence")
    elif atoms.ocr_requested and not strong_multi:
        route = "ocr_scan_recovery"
        rationale.append("query asks to recover information from a difficult scan")
    elif atoms.multi_question:
        route = "multi_question_research"
        rationale.append("multiple independent technical claims were requested")
    elif atoms.authority_requested:
        route = "authority_eligibility_verification"
        rationale.append("approval/effectivity/interchangeability authority is requested")
    elif atoms.comparison_requested:
        route = "cross_source_comparison"
        rationale.append("query requests source or revision comparison")
    elif atoms.warning_requested:
        route = "warning_caution_note_lookup"
        rationale.append("query targets warning/caution/note evidence")
    elif atoms.procedure_requested:
        route = "procedure_task_lookup"
        rationale.append("query targets a procedure or ordered task")
    elif atoms.table_requested or atoms.items:
        route = "exact_table_ipl_lookup"
        rationale.append("query targets an IPL/table row, item, or column")
    elif atoms.visual_requested or atoms.figures:
        route = "visual_figure_callout_lookup"
        rationale.append("query requests visual, figure, drawing, or callout evidence")
    elif atoms.aggregate_requested:
        route = "high_degree_entity_aggregation"
        rationale.append("query requests broad cross-document coverage")
    elif atoms.graph_requested:
        route = "graph_relationship_reasoning"
        rationale.append("query asks for typed entity relationships")
    elif atoms.navigation_requested or atoms.page_ids:
        route = "document_page_navigation"
        rationale.append("query asks where evidence is located")
    elif atoms.exact_part_numbers:
        route = "exact_identifier_lookup"
        rationale.append("an exact aviation-style part identifier was extracted")
    elif atoms.ata_prefix or atoms.ata_exact:
        route = "ata_system_discovery"
        rationale.append("ATA clue is entity-bound and separated from part-number clues")
    elif atoms.part_prefix or atoms.part_contains or atoms.part_suffix or "only know" in low or "only remember" in low:
        route = "guided_part_discovery"
        rationale.append("partial part-number clues require candidate discovery")
    elif explicit_semantic_intent(low):
        route = "semantic_discovery"
        rationale.append("explicit topical/page-discovery intent outranks incidental component nouns")
    elif atoms.nomenclature_terms or atoms.assembly_context:
        route = "nomenclature_function_search"
        rationale.append("nomenclature/function/assembly clues were extracted")
    elif precision_has_any_phrase(low, SEMANTIC_TERMS):
        route = "semantic_discovery"
        rationale.append("query is topical rather than identifier-exact")
    else:
        route = "clarification_no_evidence"
        rationale.append("no sufficiently specific supported technical intent was extracted")

    if route == "exact_identifier_lookup":
        secondary = ["guided_part_discovery", "visual_figure_callout_lookup"]
    elif route == "ata_system_discovery":
        secondary = ["semantic_discovery", "document_page_navigation"]
    elif route == "nomenclature_function_search":
        secondary = ["semantic_discovery", "visual_figure_callout_lookup", "guided_part_discovery"]
    elif route == "authority_eligibility_verification":
        secondary = ["exact_identifier_lookup", "cross_source_comparison"]
    elif route == "multi_question_research":
        secondary = [
            "exact_identifier_lookup", "exact_table_ipl_lookup",
            "visual_figure_callout_lookup", "authority_eligibility_verification",
        ]

    tunnels = {
        "safe_general_chat": ["restricted_conversation_template"],
        "exact_identifier_lookup": ["normal_source_truth", "guided_exact_candidate", "confirmed_visual", "qdrant_guidance"],
        "guided_part_discovery": ["guided_candidate_discovery", "normal_source_resolution", "qdrant_guidance"],
        "ata_system_discovery": ["normal_source_truth", "document_metadata", "guided_broad_candidates", "graph_leiden_guidance", "v2_v3_summary_guidance", "qdrant_guidance"],
        "nomenclature_function_search": ["normal_source_truth", "guided_nomenclature_candidates", "confirmed_visual", "graph_leiden_guidance", "v2_v3_summary_guidance", "qdrant_guidance"],
        "exact_table_ipl_lookup": ["normal_source_truth", "table_rows_cells", "ocr_fallback", "figure_item_linkage"],
        "visual_figure_callout_lookup": ["confirmed_visual", "llava_observations", "ocr_labels", "table_figure_linkage", "qdrant_guidance"],
        "procedure_task_lookup": ["normal_source_truth", "procedure_sections", "warnings", "referenced_figures"],
        "warning_caution_note_lookup": ["normal_source_truth", "warning_blocks", "task_context"],
        "authority_eligibility_verification": ["normal_source_truth", "authority_fields", "cross_source_resolution"],
        "document_page_navigation": ["normal_source_truth", "page_metadata", "graph_leiden_guidance", "v2_v3_summary_guidance"],
        "graph_relationship_reasoning": ["typed_graph_guidance", "normal_source_resolution", "qdrant_guidance"],
        "semantic_discovery": ["qdrant_guidance", "v2_v3_summary_guidance", "graph_leiden_guidance", "normal_source_resolution"],
        "cross_source_comparison": ["normal_source_truth", "document_revision_metadata", "source_separation"],
        "contradiction_resolution": ["normal_source_truth", "revision_effectivity_context", "ocr_visual_crosscheck"],
        "ocr_scan_recovery": ["normal_ocr", "visual_crosscheck", "table_geometry", "neighbor_context"],
        "high_degree_entity_aggregation": ["normal_source_truth", "typed_graph_aggregation", "faceting", "coverage_metadata"],
        "multi_question_research": ["query_decomposition", "multiple_bounded_routes", "claim_level_evidence_gates"],
        "clarification_no_evidence": ["targeted_clarification"],
    }[route]

    return RoutePlan(
        primary_route=route,
        secondary_routes=secondary,
        retrieval_tunnels=tunnels,
        authority_required=route == "authority_eligibility_verification",
        repair_budget=2,
        rationale=rationale,
    )


DISCOVERY_FOLLOWUP_ROUTES = {
    "guided_part_discovery",
    "nomenclature_function_search",
    "semantic_discovery",
    "clarification_no_evidence",
}


def build_follow_up_questions(
    atoms: QueryAtoms,
    route: str,
) -> List[str]:
    """Build five bounded discovery questions without treating them as evidence."""
    if route not in DISCOVERY_FOLLOWUP_ROUTES:
        return []

    questions: List[str] = []
    if atoms.part_prefix:
        questions.append(
            "What additional part number characters do you remember after "
            f"the prefix {atoms.part_prefix}?"
        )
    elif atoms.part_contains:
        questions.append(
            "What characters appear before or after "
            f"{atoms.part_contains} in the part number?"
        )
    elif atoms.part_suffix:
        questions.append(
            "What part number characters appear before "
            f"the suffix {atoms.part_suffix}?"
        )
    else:
        questions.append(
            "Do you remember any part number characters, digits, separators, "
            "or stamped markings?"
        )

    questions.append(
        "Do you know the manufacturer, vendor, or supplier?"
        if not atoms.manufacturer
        else "Are there any additional vendor markings or supplier codes?"
    )

    if atoms.nomenclature_terms or atoms.assembly_context:
        clue = atoms.nomenclature_terms[0] if atoms.nomenclature_terms else atoms.assembly_context[0]
        questions.append(
            f"What function does the {clue} perform, and what assembly or "
            "installation location is it associated with?"
        )
    else:
        questions.append(
            "What component, function, assembly, or installation location is "
            "the part associated with?"
        )

    questions.append(
        "What does the part look like, including its shape, color, size, "
        "markings, and nearby hardware?"
    )
    questions.append(
        "Do you know the ATA chapter, aircraft system, figure, diagram, IPL "
        "item, table, manual, or page?"
    )

    output: List[str] = []
    seen = set()
    for question in questions:
        normalized = re.sub(r"\s+", " ", question).strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            output.append(question)
    return output[:5]


def http_json(
    url: str,
    payload: Optional[Mapping[str, Any]],
    *,
    api_key: Optional[str],
    timeout: float,
) -> Tuple[int, Dict[str, Any]]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="GET" if data is None else "POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            value = json.loads(raw)
            return response.status, value if isinstance(value, dict) else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            value = json.loads(raw)
        except Exception:
            value = {"error": raw or str(exc)}
        return exc.code, value if isinstance(value, dict) else {}
    except Exception as exc:
        return 599, {"error": f"{type(exc).__name__}: {exc}"}


def candidate_value(row: Mapping[str, Any]) -> str:
    for key in (
        "candidate_part_number", "candidate_value", "part_number", "value", "matched_token",
    ):
        value = compact(row.get(key), 300)
        if value:
            return value
    return ""


def is_garbage_candidate(value: str) -> bool:
    upper = value.upper().strip()
    if not upper:
        return True
    if any(word in GARBAGE_CANDIDATE_WORDS for word in re.split(r"[^A-Z0-9]+", upper) if word):
        return True
    if re.fullmatch(r"\d{2}-\d{2}-\d{2}-\d{1,4}", upper):
        return True
    if upper.startswith("ATA") or upper.startswith("PAGE") or upper.startswith("FIG"):
        return True
    normalized = normalize_identifier(upper)
    digit_count = sum(character.isdigit() for character in normalized)
    return len(normalized) < 4 or digit_count < 2


def candidate_matches_atoms(value: str, atoms: QueryAtoms) -> bool:
    normalized = normalize_identifier(value)
    if atoms.exact_part_numbers:
        return any(normalized == normalize_identifier(part) for part in atoms.exact_part_numbers)
    if atoms.part_prefix:
        return normalized.startswith(normalize_identifier(atoms.part_prefix))
    if atoms.part_contains:
        return normalize_identifier(atoms.part_contains) in normalized
    if atoms.part_suffix:
        return normalized.endswith(normalize_identifier(atoms.part_suffix))
    return not is_garbage_candidate(value)



def candidate_matches_nomenclature(row: Mapping[str, Any], atoms: QueryAtoms) -> bool:
    hay = " ".join([
        candidate_value(row),
        compact(row.get("nomenclature"), 500),
        compact(row.get("snippet"), 1000),
        compact(row.get("v2_summary"), 1000),
        compact(row.get("v3_summary"), 1000),
    ]).lower()
    component_terms = [
        term for term in atoms.nomenclature_terms
        if term not in set(atoms.assembly_context) and term not in {"part", "component", "assembly"}
    ]
    if component_terms:
        return any(term.lower() in hay for term in component_terms)
    return bool(atoms.assembly_context and any(term.lower() in hay for term in atoms.assembly_context))

def apply_exact_entity_gate(envelope: EvidenceEnvelope, atoms: QueryAtoms) -> None:
    if not atoms.exact_part_numbers:
        return
    dropped_total = 0
    for attribute in ("direct_evidence", "candidate_evidence", "visual_guidance", "semantic_guidance"):
        rows = getattr(envelope, attribute)
        kept, dropped = filter_entity_consistent(rows, atoms.exact_part_numbers)
        setattr(envelope, attribute, kept)
        dropped_total += len(dropped)
        if dropped:
            envelope.uncertainties.append(
                f"entity_gate_removed_{len(dropped)}_{attribute}_row(s)_with_explicit_mismatched_part_numbers"
            )
    if dropped_total:
        envelope.coverage["entity_mismatch_drop_count"] = (
            int(envelope.coverage.get("entity_mismatch_drop_count") or 0) + dropped_total
        )


def document_ata(document: str) -> Optional[str]:
    match = ATA_EXACT_RE.search(document or "")
    return match.group(1) if match else None


def metadata_conflict(row: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    ata = compact(row.get("ata"), 100)
    document = compact(row.get("document"), 400)
    doc_ata = document_ata(document)
    if ata and ata != "unknown" and doc_ata and ata != doc_ata:
        return {
            "type": "ata_document_mismatch",
            "candidate": candidate_value(row),
            "candidate_ata": ata,
            "document_ata": doc_ata,
            "document": document,
        }
    return None


def extract_direct(result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    rows = result.get("citations")
    if not isinstance(rows, list):
        return []
    output = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        page = compact(row.get("page_id"), 300)
        field_name = compact(row.get("field_name"), 300)
        value = compact(row.get("normalized_value") or row.get("value"), 2000)
        if not page or not value:
            # Visual citations can be guidance but not direct textual proof.
            continue
        row.setdefault("source_trace_ready", bool(row.get("citation_ready", True)))
        row.setdefault("direct_proof_authority", bool(field_name))
        output.append(row)
    return output


def extract_visual(result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    rows = result.get("citations")
    if not isinstance(rows, list):
        return []
    output = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        if row.get("figure_refs") or row.get("part_numbers") or row.get("subject") or result.get("route") == "gemma_confirmed_image_visual":
            row["guidance_only"] = True
            row["source_truth"] = False
            output.append(row)
    return output


def extract_semantic(result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    qdrant = result.get("qdrant_guidance")
    if not isinstance(qdrant, Mapping):
        return []
    hits = qdrant.get("hits")
    output = []
    for raw in hits if isinstance(hits, list) else []:
        if isinstance(raw, Mapping):
            row = dict(raw)
            row["guidance_only"] = True
            row["source_truth"] = False
            output.append(row)
    return output


def extract_candidates(result: Mapping[str, Any], atoms: QueryAtoms, *, allow_broad: bool = False) -> List[Dict[str, Any]]:
    rows: List[Any] = []
    for key in ("strict_prefix_candidates", "contains_candidates", "candidate_routes", "loose_candidates"):
        value = result.get(key)
        if isinstance(value, list):
            rows.extend(value)
    output: List[Dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        value = candidate_value(row)
        if is_garbage_candidate(value):
            continue
        if not allow_broad and not candidate_matches_atoms(value, atoms):
            continue
        row["candidate_value"] = value
        row["guidance_only"] = True
        row["source_truth"] = False
        row["final_answer_allowed"] = False
        output.append(row)
    return unique_dicts(output, ("candidate_value", "page_id", "document", "ata"))


class CognitiveRuntime:
    def __init__(
        self,
        *,
        unified_base_url: str,
        guided_base_url: str,
        unified_api_key: str,
        api_key: str,
        timeout: float,
        max_request_bytes: int,
        max_concurrency: int,
        queue_timeout: float,
    ) -> None:
        self.unified_base_url = unified_base_url.rstrip("/")
        self.guided_base_url = guided_base_url.rstrip("/")
        self.unified_api_key = unified_api_key
        self.api_key = api_key
        self.timeout = timeout
        self.max_request_bytes = max_request_bytes
        self.semaphore = threading.BoundedSemaphore(max(1, max_concurrency))
        self.queue_timeout = queue_timeout

    def call_unified(self, query: str, *, top_k: int = 8) -> Tuple[int, Dict[str, Any]]:
        return http_json(
            self.unified_base_url + "/api/trace-net/ask",
            {"query": query, "messages": [{"role": "user", "content": query}], "top_k": top_k},
            api_key=self.unified_api_key,
            timeout=getattr(self, "retrieval_timeout", None) or self.timeout,
        )

    def call_guided(self, query: str, *, top_k: int = 8) -> Tuple[int, Dict[str, Any]]:
        return http_json(
            self.guided_base_url + "/api/trace-net/guided-discovery",
            {"question": query, "top_k": top_k, "loose_top_k": top_k, "include_view": False},
            api_key=None,
            timeout=getattr(self, "retrieval_timeout", None) or self.timeout,
        )

    def add_unified(self, envelope: EvidenceEnvelope, query: str, label: str) -> Dict[str, Any]:
        status, result = self.call_unified(query)
        envelope.retrieval_tunnels_used.append(label)
        envelope.upstream_results.append({
            "tunnel": label,
            "status_code": status,
            "query": query,
            "route": result.get("route"),
            "quality_status": result.get("quality_status"),
            "content_preview": compact(result.get("content"), 1000),
        })
        envelope.direct_evidence.extend(extract_direct(result))
        envelope.visual_guidance.extend(extract_visual(result))
        envelope.semantic_guidance.extend(extract_semantic(result))
        if status != 200:
            envelope.uncertainties.append(f"{label} returned status {status}")
        return result

    def add_guided(self, envelope: EvidenceEnvelope, query: str, atoms: QueryAtoms, label: str, *, allow_broad: bool = False) -> Dict[str, Any]:
        status, result = self.call_guided(query)
        envelope.retrieval_tunnels_used.append(label)
        envelope.upstream_results.append({
            "tunnel": label,
            "status_code": status,
            "query": query,
            "route": "guided_discovery",
            "quality_status": result.get("quality_status"),
            "candidate_count": result.get("total_candidate_route_count"),
        })
        new_candidates = extract_candidates(result, atoms, allow_broad=allow_broad)
        per_tunnel_cap = getattr(self, "max_candidates_per_tunnel", 0) or 0
        if per_tunnel_cap > 0:
            new_candidates = new_candidates[:per_tunnel_cap]
        envelope.candidate_evidence.extend(new_candidates)
        if status != 200:
            envelope.uncertainties.append(f"{label} returned status {status}")
        return result

    def gather_initial(self, plan: RoutePlan, atoms: QueryAtoms) -> EvidenceEnvelope:
        envelope = EvidenceEnvelope(route=plan.primary_route, query_atoms=asdict(atoms))
        query = atoms.latest_query
        route = plan.primary_route

        if route == "safe_general_chat":
            envelope.retrieval_tunnels_used.append("restricted_conversation_template")
            envelope.coverage = {"technical_retrieval_required": False, "route_registry_size": len(ALL_ROUTES)}
            return envelope
        if route == "clarification_no_evidence":
            envelope.retrieval_tunnels_used.append("targeted_clarification")
            envelope.uncertainties.append("no precise supported route clues were extracted")
            return envelope

        if route == "exact_identifier_lookup":
            self.add_unified(envelope, query, "normal_source_truth")
            for part in atoms.exact_part_numbers[:2]:
                self.add_guided(envelope, f"The P/N contains {part}.", atoms, "guided_exact_candidate")
                self.add_unified(envelope, f"Find diagram for part {part}", "confirmed_visual")
        elif route == "guided_part_discovery":
            self.add_guided(envelope, query, atoms, "guided_candidate_discovery")
            self.add_unified(envelope, query, "normal_source_resolution")
        elif route == "ata_system_discovery":
            ata_clue = atoms.ata_exact[0] if atoms.ata_exact else (atoms.ata_prefix or "")
            self.add_unified(envelope, f"Find source-backed manual sections and pages for ATA {ata_clue}", "normal_source_truth")
            broad = f"I need to identify a part in the ATA {ata_clue} system area, but I do not know the part number."
            self.add_guided(envelope, broad, atoms, "guided_broad_candidates", allow_broad=True)
            envelope.candidate_evidence = [
                row for row in envelope.candidate_evidence
                if compact(row.get("ata"), 100).startswith(str(ata_clue))
            ]
        elif route == "nomenclature_function_search":
            self.add_unified(envelope, query, "normal_source_truth")
            self.add_guided(envelope, query, atoms, "guided_nomenclature_candidates", allow_broad=True)
            envelope.candidate_evidence = [
                row for row in envelope.candidate_evidence
                if candidate_matches_nomenclature(row, atoms)
            ]
            self.add_unified(envelope, "Find diagram for " + query, "confirmed_visual")
        elif route == "visual_figure_callout_lookup":
            self.add_unified(envelope, query, "confirmed_visual")
        elif route in {
            "exact_table_ipl_lookup", "procedure_task_lookup", "warning_caution_note_lookup",
            "cross_source_comparison", "contradiction_resolution", "ocr_scan_recovery",
            "high_degree_entity_aggregation",
        }:
            for index, subquery in enumerate(specialized_route_queries(route, query, atoms, maximum=3), 1):
                self.add_unified(envelope, subquery, f"{route}_specialized_{index}")
        elif route == "multi_question_research":
            subqueries = decompose_claim_queries(query, atoms, maximum=6)
            for index, subquery in enumerate(subqueries, 1):
                self.add_unified(envelope, subquery, f"claim_subquery_{index}")
        else:
            self.add_unified(envelope, query, plan.retrieval_tunnels[0])

        envelope.direct_evidence = unique_dicts(envelope.direct_evidence, ("page_id", "field_name", "normalized_value", "value"))
        envelope.candidate_evidence = unique_dicts(envelope.candidate_evidence, ("candidate_value", "page_id", "document", "ata"))
        envelope.visual_guidance = unique_dicts(envelope.visual_guidance, ("page_id", "subject", "figure_refs", "part_numbers"))
        envelope.semantic_guidance = unique_dicts(envelope.semantic_guidance, ("point_id", "page_id", "candidate_type"))
        apply_exact_entity_gate(envelope, atoms)
        for row in envelope.candidate_evidence:
            conflict = metadata_conflict(row)
            if conflict:
                row["metadata_conflict"] = conflict
                envelope.contradictions.append(conflict)
        envelope.authority_evidence = [
            row for row in envelope.direct_evidence
            if any(hint in compact(row.get("field_name"), 300).lower() for hint in AUTHORITY_FIELD_HINTS)
        ]
        envelope.coverage = {
            "direct_evidence_count": len(envelope.direct_evidence),
            "candidate_evidence_count": len(envelope.candidate_evidence),
            "visual_guidance_count": len(envelope.visual_guidance),
            "semantic_guidance_count": len(envelope.semantic_guidance),
            "authority_evidence_count": len(envelope.authority_evidence),
            "contradiction_count": len(envelope.contradictions),
            "entity_mismatch_drop_count": int(envelope.coverage.get("entity_mismatch_drop_count") or 0),
            "upstream_request_count": len(envelope.upstream_results),
            "result_was_capped": any(len(group) >= 8 for group in (envelope.candidate_evidence, envelope.visual_guidance, envelope.semantic_guidance)),
        }
        return envelope

    def critic(self, plan: RoutePlan, atoms: QueryAtoms, envelope: EvidenceEnvelope) -> Dict[str, Any]:
        failures: List[str] = []
        warnings: List[str] = []

        route = plan.primary_route
        technical = route not in {"safe_general_chat", "clarification_no_evidence"}

        if route not in ALL_ROUTES:
            failures.append("unregistered_route")
        if route == "safe_general_chat":
            if not atoms.general_chat:
                failures.append("general_chat_not_allowlisted")
            if any(term in atoms.normalized_query for term in TECHNICAL_TERMS):
                failures.append("technical_query_in_general_chat")
        if route == "ata_system_discovery":
            if not (atoms.ata_prefix or atoms.ata_exact):
                failures.append("ata_route_without_ata_atom")
            if atoms.part_prefix and atoms.part_prefix == atoms.ata_prefix:
                failures.append("ata_prefix_leaked_into_part_prefix")
        if route == "exact_identifier_lookup" and not atoms.exact_part_numbers:
            failures.append("exact_route_without_exact_identifier")
        if route == "guided_part_discovery" and not (atoms.part_prefix or atoms.part_contains or atoms.part_suffix or envelope.candidate_evidence):
            warnings.append("guided_route_has_no_explicit_part_pattern")
        if route == "authority_eligibility_verification" and not envelope.authority_evidence:
            failures.append("explicit_authority_not_found")

        if technical and not (
            envelope.direct_evidence or envelope.candidate_evidence or envelope.visual_guidance or envelope.semantic_guidance
        ):
            failures.append("no_evidence_or_guidance")

        for candidate in envelope.candidate_evidence:
            value = candidate_value(candidate)
            if is_garbage_candidate(value):
                failures.append("garbage_candidate_exposed")
                break
            if route in {"exact_identifier_lookup", "guided_part_discovery"} and not candidate_matches_atoms(value, atoms):
                failures.append("candidate_violates_explicit_identifier_clue")
                break

        if route == "exact_identifier_lookup" and atoms.exact_part_numbers:
            requested = {normalize_identifier(value) for value in atoms.exact_part_numbers}
            returned = {normalize_identifier(candidate_value(row)) for row in envelope.candidate_evidence}
            direct_blob = " ".join(compact(row, 2000) for row in envelope.direct_evidence)
            visual_blob = " ".join(compact(row, 2000) for row in envelope.visual_guidance)
            for exact in requested:
                if exact not in returned and exact not in normalize_identifier(direct_blob) and exact not in normalize_identifier(visual_blob):
                    failures.append("exact_identifier_not_recovered_by_any_tunnel")
                    break

        if envelope.contradictions:
            warnings.append("metadata_conflict_requires_source_resolution")
        if envelope.semantic_guidance and not envelope.direct_evidence:
            warnings.append("semantic_guidance_not_resolved_to_direct_proof")
        if envelope.visual_guidance and not envelope.direct_evidence:
            warnings.append("visual_guidance_not_promoted_to_source_truth")

        for key in ("answer_permission", "final_answer_allowed", "source_truth_mutation_allowed"):
            if envelope.safety_contract.get(key):
                failures.append(f"unsafe_contract:{key}")

        return {
            "quality_status": "PASS" if not failures else "RETRY",
            "failures": list(dict.fromkeys(failures)),
            "warnings": list(dict.fromkeys(warnings)),
            "retry_required": bool(failures),
            "dimensions": {
                "route_correctness": "PASS" if not any("route" in item or "ata_prefix" in item for item in failures) else "FAIL",
                "query_clue_fidelity": "PASS" if not any("candidate" in item or "identifier" in item for item in failures) else "FAIL",
                "citation_readiness": "PASS" if envelope.direct_evidence else "GUIDANCE_ONLY",
                "source_authority": "PASS" if (not plan.authority_required or envelope.authority_evidence) else "FAIL",
                "metadata_consistency": "WARN" if envelope.contradictions else "PASS",
                "safety": "PASS" if not any("unsafe_contract" in item for item in failures) else "FAIL",
            },
        }

    def repair(self, plan: RoutePlan, atoms: QueryAtoms, envelope: EvidenceEnvelope, critic: Mapping[str, Any]) -> None:
        failures = set(critic.get("failures") or [])
        if not failures or len(envelope.crag_repairs) >= plan.repair_budget:
            return

        if "exact_identifier_not_recovered_by_any_tunnel" in failures or "no_evidence_or_guidance" in failures:
            if atoms.exact_part_numbers:
                for part in atoms.exact_part_numbers[:1]:
                    before = len(envelope.candidate_evidence)
                    self.add_guided(envelope, f"The P/N contains {part}.", atoms, "crag_exact_guided_recovery")
                    self.add_unified(envelope, f"Search the IPL table for exact part {part}", "crag_exact_table_resolution")
                    envelope.crag_repairs.append({
                        "repair": "exact_identifier_cross_route_recovery",
                        "part_number": part,
                        "new_candidate_count": len(envelope.candidate_evidence) - before,
                    })
                    break
        elif plan.primary_route == "ata_system_discovery":
            ata_clue = atoms.ata_exact[0] if atoms.ata_exact else atoms.ata_prefix
            self.add_unified(envelope, f"Find pages about the ATA {ata_clue} aircraft system area", "crag_ata_semantic_resolution")
            envelope.crag_repairs.append({"repair": "ata_entity_rebind_and_semantic_resolution", "ata_clue": ata_clue})
        elif plan.primary_route == "nomenclature_function_search":
            search_terms = " ".join(atoms.nomenclature_terms + atoms.assembly_context) or atoms.latest_query
            self.add_unified(envelope, f"Search IPL nomenclature, tables, figures, and pages for {search_terms}", "crag_nomenclature_multitunnel")
            envelope.crag_repairs.append({"repair": "nomenclature_synonym_and_multitunnel_expansion", "terms": search_terms})
        elif plan.primary_route == "authority_eligibility_verification":
            self.add_unified(envelope, atoms.latest_query + " Search only explicit approval, effectivity, eligibility, interchangeability, applicability, or installation-authority fields.", "crag_authority_field_search")
            envelope.crag_repairs.append({"repair": "authority_specific_field_search"})
        else:
            self.add_unified(envelope, "Find source pages related to: " + atoms.latest_query, "crag_semantic_to_source_resolution")
            envelope.crag_repairs.append({"repair": "semantic_to_source_resolution"})

        envelope.direct_evidence = unique_dicts(envelope.direct_evidence, ("page_id", "field_name", "normalized_value", "value"))
        envelope.candidate_evidence = unique_dicts(envelope.candidate_evidence, ("candidate_value", "page_id", "document", "ata"))
        envelope.visual_guidance = unique_dicts(envelope.visual_guidance, ("page_id", "subject", "figure_refs", "part_numbers"))
        envelope.semantic_guidance = unique_dicts(envelope.semantic_guidance, ("point_id", "page_id", "candidate_type"))
        apply_exact_entity_gate(envelope, atoms)
        envelope.authority_evidence = [
            row for row in envelope.direct_evidence
            if any(hint in compact(row.get("field_name"), 300).lower() for hint in AUTHORITY_FIELD_HINTS)
        ]
        envelope.coverage.update({
            "direct_evidence_count": len(envelope.direct_evidence),
            "candidate_evidence_count": len(envelope.candidate_evidence),
            "visual_guidance_count": len(envelope.visual_guidance),
            "semantic_guidance_count": len(envelope.semantic_guidance),
            "authority_evidence_count": len(envelope.authority_evidence),
            "upstream_request_count": len(envelope.upstream_results),
            "repair_count": len(envelope.crag_repairs),
        })

    def render(self, plan: RoutePlan, atoms: QueryAtoms, envelope: EvidenceEnvelope, critic: Mapping[str, Any]) -> str:
        route = plan.primary_route

        if route == "safe_general_chat":
            if "what can you do" in atoms.normalized_query or "help" == atoms.normalized_query:
                return (
                    "Hello! I can help locate parts, ATA sections, tables, IPL rows, figures, callouts, procedures, warnings, "
                    "manual pages, and source-backed authority evidence. Technical claims remain citation-gated, and uncertain "
                    "results are presented as candidates rather than facts."
                )
            if atoms.normalized_query.startswith("thank") or atoms.normalized_query.startswith("thanks"):
                return "You’re welcome."
            return "Hello! I can help you search TRACE-Net’s connected manuals for parts, figures, tables, procedures, and source-backed technical evidence."

        if route == "clarification_no_evidence":
            return (
                "I can help search the manuals, but I need one technical clue. Provide a part-number fragment, ATA chapter, "
                "component name or function, manufacturer, figure/table reference, page, or a description of what the part looks like."
            )

        lines: List[str] = []
        direct = envelope.direct_evidence
        candidates = envelope.candidate_evidence
        visuals = envelope.visual_guidance
        semantic = envelope.semantic_guidance

        if route == "ata_system_discovery":
            clue = atoms.ata_exact[0] if atoms.ata_exact else atoms.ata_prefix
            lines.append(f"TRACE-Net interpreted {clue} as an ATA/system clue, not as the beginning of a part number.")
            pairs = []
            for row in candidates:
                ata = compact(row.get("ata"), 100)
                document = compact(row.get("document"), 400)
                if ata and ata != "unknown" and (not clue or ata.startswith(str(clue))):
                    pairs.append((ata, document))
            pairs = list(dict.fromkeys(pairs))
            if pairs:
                lines.append("Relevant ATA/document areas found:")
                for ata, document in pairs[:5]:
                    lines.append(f"- ATA {ata}" + (f" — {document}" if document and document != "unknown" else ""))
            elif semantic:
                pages = list(dict.fromkeys(compact(row.get("page_id"), 100) for row in semantic if row.get("page_id")))
                lines.append("Semantic guidance located possible source pages" + (": " + ", ".join(pages[:5]) if pages else "") + ", but they are not yet direct proof of a specific part.")
            else:
                lines.append("No citation-ready part identification was recovered from that ATA clue alone.")
            lines.append("Describe the component’s function, appearance, manufacturer, nearby figure/table, or any characters from the actual part number.")
            return "\n".join(lines)

        if route == "authority_eligibility_verification" and not envelope.authority_evidence:
            return (
                "TRACE-Net did not locate explicit source authority for the requested approval, fit, effectivity, "
                "interchangeability, eligibility, applicability, or installation claim. No approval or installation claim is made."
            )

        if direct:
            lines.append("TRACE-Net found citation-ready source evidence:")
            for index, row in enumerate(direct[:8], 1):
                value = compact(row.get("normalized_value") or row.get("value"), 600)
                field_name = compact(row.get("field_name"), 200) or "source field"
                page = compact(row.get("page_id"), 200)
                lines.append(f"- [{index}] page {page}; {field_name}: {value}")
        elif candidates:
            lines.append("TRACE-Net found candidate evidence, not a final identification:")
            for row in candidates[:8]:
                value = candidate_value(row)
                ata = compact(row.get("ata"), 100)
                document = compact(row.get("document"), 400)
                nomenclature = compact(row.get("nomenclature"), 300)
                details = []
                if row.get("metadata_conflict"):
                    details.append("metadata conflict—ATA/document association is unresolved")
                else:
                    if ata and ata != "unknown":
                        details.append("ATA " + ata)
                    if document and document != "unknown":
                        details.append(document)
                if nomenclature and nomenclature != "unknown":
                    details.append(nomenclature)
                lines.append("- " + value + (" — " + "; ".join(details) if details else ""))
        elif visuals:
            lines.append("TRACE-Net found confirmed visual guidance, but not citation-ready source proof:")
            for row in visuals[:5]:
                page = compact(row.get("page_id"), 100) or "unknown page"
                subject = compact(row.get("subject"), 300) or "visual candidate"
                figures = ", ".join(str(value) for value in (row.get("figure_refs") or []))
                lines.append(f"- page {page}: {subject}" + (f"; {figures}" if figures else ""))
        elif semantic:
            pages = list(dict.fromkeys(compact(row.get("page_id"), 100) for row in semantic if row.get("page_id")))
            lines.append("TRACE-Net found semantic guidance" + (" on pages " + ", ".join(pages[:8]) if pages else "") + ", but it did not resolve to direct source-truth evidence.")
        else:
            lines.append("TRACE-Net did not recover direct or candidate evidence for this query. No technical claim is made.")

        if envelope.contradictions:
            lines.append("Metadata conflict detected; the conflicting ATA/document values were not promoted to fact.")
        if not direct:
            lines.append("Candidate, visual, graph, summary, and semantic results are guidance only until resolved to direct source evidence.")
        if critic.get("quality_status") != "PASS":
            lines.append("The evidence critic did not permit a stronger answer after bounded repair.")
        return "\n".join(lines)

    def process(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        query = extract_latest_user(payload)
        atoms = extract_query_atoms(query)
        plan = plan_route(atoms)

        # Engram is selected before retrieval and compiled into a validated
        # preference policy. Adapters and absolute safety remain deterministic.
        engram_memory = select_engram_memory(
            atoms.latest_query,
            plan.primary_route,
            atoms.requested_claims,
            maximum_atoms=6,
        )
        plan.engram_policy = compile_engram_policy(
            engram_memory,
            plan.primary_route,
            atoms.requested_claims,
        )
        plan.working_memory = build_working_memory(
            query,
            atoms,
            plan,
            plan.engram_policy,
        )

        envelope = self.gather_initial(plan, atoms)
        envelope.coverage["engram_policy"] = plan.engram_policy
        plan.working_memory = refresh_working_memory(
            plan.working_memory,
            envelope,
            plan,
        )
        envelope.coverage["working_memory"] = plan.working_memory
        critic_before = self.critic(plan, atoms, envelope)

        for _ in range(plan.repair_budget):
            if not critic_before.get("retry_required"):
                break
            previous_repairs = len(envelope.crag_repairs)
            self.repair(plan, atoms, envelope, critic_before)
            if len(envelope.crag_repairs) == previous_repairs:
                break
            plan.working_memory = refresh_working_memory(
                plan.working_memory,
                envelope,
                plan,
            )
            envelope.coverage["working_memory"] = plan.working_memory
            critic_before = self.critic(plan, atoms, envelope)

        final_critic = critic_before
        plan.working_memory = refresh_working_memory(
            plan.working_memory,
            envelope,
            plan,
        )
        envelope.coverage["working_memory"] = plan.working_memory
        content = self.render(plan, atoms, envelope, final_critic)
        content = enforce_h30_answer_boundaries(
            route=plan.primary_route,
            query=atoms.latest_query,
            query_atoms=asdict(atoms),
            evidence_envelope=asdict(envelope),
            answer=content,
        )
        follow_up_questions = build_follow_up_questions(
            atoms,
            plan.primary_route,
        )

        return {
            "module": MODULE,
            "model": MODEL_ID,
            "quality_status": "PASS" if content else "FAIL",
            "query": query,
            "route": plan.primary_route,
            "route_plan": asdict(plan),
            "route_registry": list(ALL_ROUTES),
            "query_atoms": asdict(atoms),
            "engram_memory": engram_memory,
            "engram_policy": plan.engram_policy,
            "working_memory": plan.working_memory,
            "content": content,
            "follow_up_questions": follow_up_questions,
            "clarification_required": bool(follow_up_questions),
            "clarification_recommended": bool(follow_up_questions),
            "evidence_envelope": asdict(envelope),
            "self_rag_critic": final_critic,
            "crag_repair_attempts": envelope.crag_repairs,
            "citation_count": len(envelope.direct_evidence),
            "citations": envelope.direct_evidence,
            "answer_permission": False,
            "final_answer_allowed": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "safety_contract": envelope.safety_contract,
        }

    def health(self) -> Dict[str, Any]:
        unified_status, unified = http_json(
            self.unified_base_url + "/health", None, api_key=None, timeout=min(5.0, self.timeout)
        )
        guided_status, guided = http_json(
            self.guided_base_url + "/health", None, api_key=None, timeout=min(5.0, self.timeout)
        )
        unified_ok = unified_status == 200 and unified.get("quality_status") == "PASS"
        guided_ok = guided_status == 200 and guided.get("quality_status") in {"PASS", "WARN"}
        ready = unified_ok and guided_ok
        return {
            "status": "ok" if ready else "needs_repair",
            "quality_status": "PASS" if ready else "FAIL",
            "module": MODULE,
            "model_id": MODEL_ID,
            "route_count": len(ALL_ROUTES),
            "routes": list(ALL_ROUTES),
            "unified_upstream": {"status_code": unified_status, "identity": unified.get("module"), "ready": unified_ok},
            "guided_upstream": {"status_code": guided_status, "identity": guided.get("service"), "ready": guided_ok},
            "self_rag_connected": True,
            "crag_connected": True,
            "max_crag_repairs": 2,
            "read_only": True,
            "answer_permission": False,
            "final_answer_allowed": False,
            "source_truth_mutation_allowed": False,
        }


def openai_response(result: Mapping[str, Any], model: str) -> Dict[str, Any]:
    return {
        "id": "chatcmpl-trace-cognitive-" + uuid.uuid4().hex[:16],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": str(result.get("content") or "")},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "trace_net": dict(result),
    }


def error_payload(message: str, code: str, status: int) -> Dict[str, Any]:
    return {"error": {"message": message, "type": "trace_net_error", "param": None, "code": code}, "status": status}


def make_handler(runtime: CognitiveRuntime):
    class Handler(BaseHTTPRequestHandler):
        server_version = "TraceNetCognitiveRouter/1.0"

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def send_json(self, status: int, payload: Mapping[str, Any]) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def authorized(self) -> bool:
            return self.headers.get("Authorization", "") == f"Bearer {runtime.api_key}"

        def read_payload(self) -> Tuple[Optional[Dict[str, Any]], Optional[Tuple[int, Dict[str, Any]]]]:
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
            except ValueError:
                length = 0
            if length <= 0:
                return None, (400, error_payload("Request body is required.", "invalid_request", 400))
            if length > runtime.max_request_bytes:
                return None, (413, error_payload("Request exceeds TRACE-Net request-size limit.", "request_too_large", 413))
            try:
                value = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception as exc:
                return None, (400, error_payload(f"Invalid JSON: {exc}", "invalid_json", 400))
            if not isinstance(value, dict):
                return None, (400, error_payload("JSON body must be an object.", "invalid_request", 400))
            return value, None

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/health":
                health = runtime.health()
                self.send_json(200 if health["quality_status"] == "PASS" else 503, health)
                return
            if not self.authorized():
                self.send_json(401, error_payload("Invalid or missing API key.", "unauthorized", 401))
                return
            if path == "/v1/models":
                self.send_json(200, {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "created": int(time.time()), "owned_by": "trace-net-local"}]})
                return
            if path == "/api/trace-net/routes":
                self.send_json(200, {"quality_status": "PASS", "route_count": len(ALL_ROUTES), "routes": list(ALL_ROUTES)})
                return
            self.send_json(404, error_payload("Route not found.", "not_found", 404))

        def do_POST(self) -> None:
            if not self.authorized():
                self.send_json(401, error_payload("Invalid or missing API key.", "unauthorized", 401))
                return
            if not runtime.semaphore.acquire(timeout=runtime.queue_timeout):
                self.send_json(429, error_payload("TRACE-Net cognitive queue timed out.", "rate_limit", 429))
                return
            try:
                payload, error = self.read_payload()
                if error:
                    self.send_json(*error)
                    return
                assert payload is not None
                query = extract_latest_user(payload)
                if not query:
                    self.send_json(400, error_payload("Missing query or user message.", "missing_query", 400))
                    return
                path = self.path.split("?", 1)[0]
                if path == "/api/trace-net/shadow-plan":
                    self.send_json(200, runtime.shadow_plan(query))
                    return
                if path == "/api/trace-net/planner-decision":
                    self.send_json(200, runtime.planner_decision(query))
                    return
                if path == "/api/trace-net/plan":
                    atoms = extract_query_atoms(query)
                    plan = plan_route(atoms)
                    engram_memory = select_engram_memory(
                        atoms.latest_query,
                        plan.primary_route,
                        atoms.requested_claims,
                        maximum_atoms=6,
                    )
                    plan.engram_policy = compile_engram_policy(
                        engram_memory,
                        plan.primary_route,
                        atoms.requested_claims,
                    )
                    plan.working_memory = build_working_memory(
                        query,
                        atoms,
                        plan,
                        plan.engram_policy,
                    )
                    self.send_json(200, {
                        "quality_status": "PASS",
                        "module": MODULE,
                        "query": query,
                        "query_atoms": asdict(atoms),
                        "route_plan": asdict(plan),
                        "engram_memory": engram_memory,
                        "engram_policy": plan.engram_policy,
                        "working_memory": plan.working_memory,
                        "route_registry": list(ALL_ROUTES),
                        "retrieval_executed": False,
                        "answer_permission": False,
                        "final_answer_allowed": False,
                        "source_truth_mutation_allowed": False,
                    })
                    return
                result = runtime.process(payload)
                if path == "/api/trace-net/ask":
                    self.send_json(200, result)
                    return
                if path == "/v1/chat/completions":
                    self.send_json(200, openai_response(result, str(payload.get("model") or MODEL_ID)))
                    return
                self.send_json(404, error_payload("Route not found.", "not_found", 404))
            except Exception as exc:
                self.send_json(500, error_payload(f"{type(exc).__name__}: {exc}", "internal_error", 500))
            finally:
                runtime.semaphore.release()

    return Handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8118)
    parser.add_argument("--unified-base-url", default="http://127.0.0.1:8117")
    parser.add_argument("--guided-base-url", default="http://127.0.0.1:8116")
    parser.add_argument("--unified-api-key", default=os.environ.get("TRACE_NET_API_KEY", "trace-net-canary-local"))
    parser.add_argument("--api-key", default="trace-net-cognitive-local")
    parser.add_argument("--timeout-seconds", type=float, default=1200.0)
    parser.add_argument("--max-request-bytes", type=int, default=1_000_000)
    parser.add_argument("--max-concurrency", type=int, default=2)
    parser.add_argument("--queue-timeout-seconds", type=float, default=1200.0)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    runtime = CognitiveRuntime(
        unified_base_url=args.unified_base_url,
        guided_base_url=args.guided_base_url,
        unified_api_key=args.unified_api_key,
        api_key=args.api_key,
        timeout=args.timeout_seconds,
        max_request_bytes=args.max_request_bytes,
        max_concurrency=args.max_concurrency,
        queue_timeout=args.queue_timeout_seconds,
    )
    health = runtime.health()
    if health["quality_status"] != "PASS":
        print(json.dumps(health, indent=2))
        raise SystemExit("Cognitive router refused to start because required upstream services are not healthy")
    server = ThreadingHTTPServer((args.host, args.port), make_handler(runtime))
    print("status=TRACE_NET_COGNITIVE_ROUTER_V1_READY")
    print("quality_status=PASS")
    print(f"host={args.host}")
    print(f"port={args.port}")
    print(f"model={MODEL_ID}")
    print(f"route_count={len(ALL_ROUTES)}")
    print("self_rag_connected=true")
    print("crag_connected=true")
    server.serve_forever()
    return 0


install_retrieval_completion(globals())
install_engram_critic_repair(globals())
install_user_facing_renderer(globals())
install_navigation_latency_fastpath(globals())
install_part_intent_source_resolution(globals())
install_shadow_planner(globals())
install_validated_planner_execution(globals())
install_engram_skill_shadow(globals())
install_typed_evidence_envelope(globals())
install_graph_source_retrieval(globals())
install_page_content_bridge(globals())
# TRACE_NET_H30_PHASE2_CLAIM_READY_EVIDENCE_INSTALL
install_claim_ready_evidence(globals())

if __name__ == "__main__":
    raise SystemExit(main())
