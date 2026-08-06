"""TRACE-Net deterministic query-atom router v1.

The router extracts small, inspectable atoms with regex and keyword lists.
It never gives an LLM permission to invent routes or source-truth fields.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

PART_RE = re.compile(r"\b\d{2,3}-\d{5}(?:-\d{3})?\b")
MANUAL_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
FIGURE_RE = re.compile(r"\b(?:figure|fig\.?)\s*(\d{1,4})(?:\s+sheet\s+(\d{1,3}))?\b", re.I)
PAGE_RE = re.compile(r"\b(?:page|pg\.?)\s*([A-Za-z0-9_-]+)\b", re.I)
PREFIX_RE = re.compile(r"\b(?:starts?|begins?)\s+(?:with\s+)?([A-Za-z0-9-]{1,16})", re.I)

PART_WORDS = {
    "part", "p/n", "pn", "part number", "item number", "nomenclature",
    "component", "number",
}
PART_HINTS = {
    "fastener", "screw", "bolt", "clip", "pin", "ring", "locking", "seat",
    "assembly", "assy", "bracket", "latch", "cover", "panel", "fitting",
    "table", "ashtray", "armrest",
}
LOW_CONTEXT = {
    "only know", "only remember", "do not know", "don't know", "partial",
    "starts with", "begins with", "contains", "looked like", "might be",
    "i think", "first few pages", "somewhere",
}
VISUAL_WORDS = {
    "diagram", "figure", "fig", "image", "drawing", "illustration",
    "callout", "callouts", "schematic", "exploded", "view",
}
TABLE_WORDS = {
    "table", "index", "list", "row", "column", "cell", "ipl",
    "illustrated parts list", "parts list",
}
PROCEDURE_WORDS = {
    "procedure", "remove", "removal", "install", "installation", "inspect",
    "inspection", "repair", "replace", "replacement", "step", "torque",
    "clean", "test", "adjust", "assemble", "disassemble",
}
SAFETY_WORDS = {
    "fit", "fits", "safe to", "interchangeable", "interchangeability",
    "approved replacement", "effectivity", "eligibility", "approved for",
    "can i install", "installation safety",
}
WARNING_WORDS = {"warning", "caution", "note", "danger", "hazard"}
REFERENTIAL = {"it", "that", "this", "the figure", "the diagram", "that part", "what figure", "which page"}


def _hits(text: str, vocabulary: set[str]) -> List[str]:
    low = text.lower()
    return sorted(term for term in vocabulary if term in low)


def analyze_query(query: str) -> Dict[str, Any]:
    text = str(query or "").strip()
    low = text.lower()
    part_numbers = PART_RE.findall(text)
    manual_refs = MANUAL_RE.findall(text)
    figures = [
        {"figure": m.group(1), "sheet": m.group(2) or ""}
        for m in FIGURE_RE.finditer(text)
    ]
    pages = PAGE_RE.findall(text)
    prefix_match = PREFIX_RE.search(text)
    prefix = prefix_match.group(1) if prefix_match else ""

    atoms = {
        "part_numbers": list(dict.fromkeys(part_numbers)),
        "manual_references": list(dict.fromkeys(manual_refs)),
        "figures": figures,
        "pages": list(dict.fromkeys(pages)),
        "prefix": prefix,
        "part_words": _hits(text, PART_WORDS),
        "part_hints": _hits(text, PART_HINTS),
        "low_context_markers": _hits(text, LOW_CONTEXT),
        "visual_words": _hits(text, VISUAL_WORDS),
        "table_words": _hits(text, TABLE_WORDS),
        "procedure_words": _hits(text, PROCEDURE_WORDS),
        "safety_words": _hits(text, SAFETY_WORDS),
        "warning_words": _hits(text, WARNING_WORDS),
        "referential_words": _hits(text, REFERENTIAL),
    }

    has_part_clue = bool(atoms["part_numbers"] or atoms["part_words"] or atoms["part_hints"] or prefix)
    low_context = bool(atoms["low_context_markers"])
    exact_entity = bool(atoms["part_numbers"] or atoms["manual_references"] or atoms["figures"] or atoms["pages"])

    if atoms["safety_words"]:
        selected_tunnel = "safety_authority_search"
        execution_route = "normal_ask"
        reason = "safety_or_approval_claim_requires_explicit_authority"
    elif has_part_clue and low_context:
        selected_tunnel = "guided_candidate_discovery"
        execution_route = "guided_discovery"
        reason = "partial_or_low_context_part_clue"
    elif low_context and not exact_entity:
        selected_tunnel = "fast_clarification"
        execution_route = "guided_discovery"
        reason = "low_context_query_without_resolved_entity"
    elif atoms["visual_words"] or atoms["figures"]:
        selected_tunnel = "visual_figure_retrieval"
        execution_route = "gemma_confirmed_image_visual"
        reason = "visual_or_figure_atom_present"
    elif atoms["table_words"]:
        selected_tunnel = "table_exact_or_structured_retrieval"
        execution_route = "normal_ask"
        reason = "table_or_index_atom_present"
    elif atoms["procedure_words"] or atoms["warning_words"]:
        selected_tunnel = "procedure_warning_text_retrieval"
        execution_route = "normal_ask"
        reason = "procedure_warning_or_note_atom_present"
    elif exact_entity:
        selected_tunnel = "exact_source_lookup"
        execution_route = "normal_ask"
        reason = "exact_part_manual_figure_or_page_entity"
    else:
        selected_tunnel = "general_source_truth_retrieval"
        execution_route = "normal_ask"
        reason = "no_specialized_atom_requires_other_route"

    return {
        "router_version": "query_atom_router_v1",
        "selected_tunnel": selected_tunnel,
        "execution_route": execution_route,
        "reason": reason,
        "atoms": atoms,
        "llm_route_selection_allowed": False,
        "validator_gated": True,
        "source_truth_mutation_allowed": False,
        "answer_permission": False,
        "final_answer_allowed": False,
    }
