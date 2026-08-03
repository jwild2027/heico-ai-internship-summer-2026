"""TRACE-Net deterministic query-atom router v1.1.

The router extracts small, inspectable atoms with regex and keyword lists.
It never gives an LLM permission to invent routes or source-truth fields.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from tiff.trace_net_follow_up_question_planner_v1 import build_follow_up_plan

PART_RE = re.compile(r"\b\d{2,3}-\d{5}(?:-\d{3})?\b")
MANUAL_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
ATA_SECTION_RE = re.compile(r"\bATA\s*(\d{2})(?!\s*-\s*\d{2})\b", re.I)
FIGURE_RE = re.compile(r"\b(?:figure|fig\.?)\s*(\d{1,4})(?:\s+sheet\s+(\d{1,3}))?\b", re.I)
PAGE_RE = re.compile(r"\b(?:page|pg\.?)\b\s*([A-Za-z0-9_-]+)\b", re.I)
PREFIX_RE = re.compile(r"\b(?:starts?|begins?)\s+(?:with\s+)?([A-Za-z0-9-]{1,16})", re.I)
CONTAINS_RE = re.compile(r"\bcontains?\s+([A-Za-z0-9-]{2,16})", re.I)

PART_WORDS = {
    "part", "p/n", "pn", "part number", "item number", "nomenclature",
    "component", "number",
}
PART_HINTS = {
    "fastener", "screw", "bolt", "clip", "pin", "ring", "locking", "seat",
    "assembly", "assy", "bracket", "latch", "cover", "panel", "fitting",
    "table", "ashtray", "armrest", "hinge", "handle", "door", "spring",
    "washer", "nut", "bearing", "support", "rail", "track", "leg", "cushion",
    "belt", "buckle", "actuator", "switch", "valve", "tube", "hose",
    "connector", "clamp", "spacer", "shaft", "rod", "link", "hook",
    "knob", "lever", "strap", "protector", "frame",
}
FUNCTION_HINTS = {
    "pivot", "rotate", "opens", "closes", "holds", "supports", "connects",
    "locks", "releases", "slides", "folds", "attaches", "secures", "protects",
    "adjusts", "moves", "guides", "stops", "retains",
}
DISCOVERY_WORDS = {
    "find", "find me", "looking for", "searching for", "trying to find",
    "i need", "need a", "need an", "i want", "want a", "want an",
    "i would like", "identify", "locate", "which part", "what part",
}
COMPANY_WORDS = {
    "honeywell", "embraer", "boeing", "airbus", "collins", "safran",
    "recaro", "zodiac", "rockwell collins", "bae", "ge", "parker",
}
LOW_CONTEXT = {
    "only know", "only remember", "do not know", "don't know", "partial",
    "starts with", "begins with", "contains", "looked like", "might be",
    "i think", "first few pages", "somewhere", "not sure", "cannot remember",
    "might",
    "can't remember", "all i know", "all i remember",
}
VISUAL_WORDS = {
    "diagram", "figure", "fig", "image", "drawing", "illustration",
    "callout", "callouts", "schematic", "exploded", "view",
}
TABLE_WORDS = {
    "table", "index", "list", "row", "column", "cell", "ipl",
    "illustrated parts list", "parts list", "item number",
}
PROCEDURE_WORDS = {
    "procedure", "remove", "removal", "install", "installation", "inspect",
    "inspection", "repair", "replace", "replacement", "step", "torque",
    "clean", "test", "adjust", "assemble", "disassemble", "reassemble",
    "disassembled", "reassembly", "adjusted", "removing",
}
SAFETY_WORDS = {
    "fit", "fits", "safe to", "interchangeable", "interchangeability",
    "approved replacement", "effectivity", "eligibility", "approved for",
    "can i install", "installation safety", "authorized substitute",
    "eligible", "substitute", "approved source", "authorizes", "authorize",
}
WARNING_WORDS = {"warning", "caution", "note", "danger", "hazard"}
REFERENTIAL = {
    "it", "that", "this", "the figure", "the diagram", "that part",
    "what figure", "which page",
}


def _contains_term(text: str, term: str) -> bool:
    low = text.lower()
    value = term.lower()
    if re.fullmatch(r"[a-z0-9]+", value):
        return bool(re.search(rf"\b{re.escape(value)}\b", low))
    return value in low


def _hits(text: str, vocabulary: set[str]) -> List[str]:
    return sorted(term for term in vocabulary if _contains_term(text, term))


def analyze_query(query: str) -> Dict[str, Any]:
    text = str(query or "").strip()
    part_numbers = PART_RE.findall(text)
    manual_refs = MANUAL_RE.findall(text)
    ata_sections = ATA_SECTION_RE.findall(text)
    figures = [
        {"figure": m.group(1), "sheet": m.group(2) or ""}
        for m in FIGURE_RE.finditer(text)
    ]
    pages = PAGE_RE.findall(text)
    prefix_match = PREFIX_RE.search(text)
    prefix = prefix_match.group(1) if prefix_match else ""
    contains_match = CONTAINS_RE.search(text)
    contains_value = contains_match.group(1) if contains_match else ""

    atoms = {
        "part_numbers": list(dict.fromkeys(part_numbers)),
        "manual_references": list(dict.fromkeys(manual_refs)),
        "ata_sections": list(dict.fromkeys(ata_sections)),
        "figures": figures,
        "pages": list(dict.fromkeys(pages)),
        "prefix": prefix,
        "contains": contains_value,
        "part_words": _hits(text, PART_WORDS),
        "part_hints": _hits(text, PART_HINTS),
        "function_hints": _hits(text, FUNCTION_HINTS),
        "discovery_words": _hits(text, DISCOVERY_WORDS),
        "companies": _hits(text, COMPANY_WORDS),
        "low_context_markers": _hits(text, LOW_CONTEXT),
        "visual_words": _hits(text, VISUAL_WORDS),
        "table_words": _hits(text, TABLE_WORDS),
        "procedure_words": _hits(text, PROCEDURE_WORDS),
        "safety_words": _hits(text, SAFETY_WORDS),
        "warning_words": _hits(text, WARNING_WORDS),
        "referential_words": _hits(text, REFERENTIAL),
    }

    has_part_clue = bool(
        atoms["part_numbers"]
        or atoms["part_words"]
        or atoms["part_hints"]
        or atoms["function_hints"]
        or atoms["companies"]
        or prefix
    )
    low_context = bool(atoms["low_context_markers"])
    partial_part_clue = bool(prefix or contains_value)
    two_part_replacement = len(atoms["part_numbers"]) >= 2 and _contains_term(text, "replace")
    exact_entity = bool(
        atoms["part_numbers"]
        or atoms["manual_references"]
        or atoms["figures"]
        or atoms["pages"]
    )
    descriptive_part_request = bool(
        not atoms["part_numbers"]
        and (atoms["part_hints"] or atoms["function_hints"] or atoms["companies"])
        and (
            atoms["part_words"]
            or atoms["discovery_words"]
            or atoms["part_hints"]
            or atoms["function_hints"]
        )
    )

    if atoms["safety_words"] or two_part_replacement:
        selected_tunnel = "safety_authority_search"
        execution_route = "normal_ask"
        reason = "safety_or_approval_claim_requires_explicit_authority"
    elif low_context and partial_part_clue and not atoms["part_numbers"]:
        selected_tunnel = "guided_candidate_discovery"
        execution_route = "guided_discovery"
        reason = "partial_or_low_context_part_clue"
    elif low_context and not atoms["part_numbers"] and not atoms["manual_references"]:
        selected_tunnel = "fast_clarification"
        execution_route = "guided_discovery"
        reason = "low_context_query_without_resolved_entity"
    elif atoms["visual_words"] or atoms["figures"]:
        selected_tunnel = "visual_figure_retrieval"
        execution_route = "gemma_confirmed_image_visual"
        reason = "visual_or_figure_atom_present"
    elif atoms["procedure_words"] or atoms["warning_words"]:
        selected_tunnel = "procedure_warning_text_retrieval"
        execution_route = "normal_ask"
        reason = "procedure_warning_or_note_atom_present"
    elif atoms["table_words"]:
        selected_tunnel = "table_exact_or_structured_retrieval"
        execution_route = "normal_ask"
        reason = "table_or_index_atom_present"
    elif descriptive_part_request:
        selected_tunnel = "descriptive_part_discovery"
        execution_route = "guided_discovery"
        reason = "descriptive_part_or_function_clue_needs_more_identifiers"
    elif exact_entity:
        selected_tunnel = "exact_source_lookup"
        execution_route = "normal_ask"
        reason = "exact_part_manual_figure_or_page_entity"
    else:
        selected_tunnel = "general_source_truth_retrieval"
        execution_route = "normal_ask"
        reason = "no_specialized_atom_requires_other_route"

    follow_up_plan = build_follow_up_plan(text, atoms, selected_tunnel)

    return {
        "router_version": "query_atom_router_v1.1",
        "selected_tunnel": selected_tunnel,
        "execution_route": execution_route,
        "reason": reason,
        "atoms": atoms,
        "follow_up_plan": follow_up_plan,
        "clarifying_questions": follow_up_plan["clarifying_questions"],
        "follow_up_topics": follow_up_plan["follow_up_topics"],
        "clarification_required": follow_up_plan["clarification_required"],
        "clarification_recommended": follow_up_plan["clarification_recommended"],
        "llm_route_selection_allowed": False,
        "validator_gated": True,
        "source_truth_mutation_allowed": False,
        "answer_permission": False,
        "final_answer_allowed": False,
    }
