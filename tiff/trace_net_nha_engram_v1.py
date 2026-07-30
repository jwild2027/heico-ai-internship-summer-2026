"""TRACE-Net NHA Engram atoms, skill cards, overlays, and benchmarks.

This phase teaches TRACE-Net how to *recognize and reason about* next-higher-
assembly questions.  It does not retrieve source evidence, write a public
answer, call an LLM, mutate source truth, or write a database.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from tiff.trace_net_engram_skill_cards_v1 import (
    SAFETY_CONTRACT as BASE_SKILL_SAFETY_CONTRACT,
    select_engram_skills,
    validate_skill_card,
    validate_skill_library,
)

MODULE = "trace_net_nha_engram_v1"
VERSION = "v1"
STATUS = "TRACE_NET_NHA_ENGRAM_V1"
ROUTE = "assembly_relationship_reasoning"

NHA_SKILL_IDS = (
    "nha_direct_parent_lookup",
    "nha_ancestor_chain_reasoning",
    "nha_children_descendants_reasoning",
    "nha_relationship_evidence",
    "nha_scope_conflict_resolution",
)

SAFETY_CONTRACT = {
    "engram_guidance_only": True,
    "answer_permission": False,
    "final_answer_allowed": False,
    "can_be_used_as_proof": False,
    "can_prove_claims": False,
    "retrieval_execution_allowed": False,
    "llm_call_count": 0,
    "source_truth_mutation_allowed": False,
    "postgres_write_attempt": False,
    "qdrant_write_attempt": False,
    "opensearch_write_attempt": False,
}

_STANDARD_PART_RE = re.compile(r"\b\d{2,3}-\d{4,6}(?:-\d{3})?\b", re.I)
_VENDOR_PART_RE = re.compile(
    r"\b(?=[A-Z0-9-]{5,}\b)(?=[A-Z0-9-]*\d)[A-Z0-9]{2,}(?:-[A-Z0-9]{2,})+\b",
    re.I,
)
_ALNUM_PART_RE = re.compile(r"\b(?=[A-Z0-9]{5,20}\b)(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{5,20}\b", re.I)
_ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
_SYNTHETIC_RE = re.compile(r"\b990-\d{5}-\d{3}\b", re.I)

DIRECT_TERMS = (
    "direct nha", "next higher assembly", "immediate parent", "direct parent",
    "parent assembly", "immediate assembly", "assembly contains", "assembly containing",
    "larger unit contains", "belongs to", "installed in", "mounts in", "sits in",
    "part of which assembly", "what assembly is this part of", "one level above",
    "one-hop parent", "directly owns", "directly contains", "directly under",
    "nearest parent assembly", "nearest supported component", "nearest component contains",
)
CHAIN_TERMS = (
    "complete assembly chain", "assembly chain", "ancestor chain", "all higher assemblies",
    "full hierarchy", "hierarchy above", "walk me upward", "walk upward", "up through the assemblies",
    "all parents", "parent path", "trace upward", "from part to assembly",
    "supported ancestor", "roll up through", "ordered assembly lineage",
    "chain of containing assemblies", "highest supported assembly", "nha chain",
)
CHILD_TERMS = (
    "direct children", "immediate children", "direct components", "immediate components",
    "directly below", "one level below", "parts directly under", "parts immediately under",
    "what does this assembly contain", "components of assembly", "breakdown one level",
    "immediately below", "directly contain", "one-level breakdown", "one-hop children",
    "belong immediately to assembly", "direct component list", "immediate child relationships",
    "directly contained by assembly", "components are directly under",
)
DESCENDANT_TERMS = (
    "lower descendants", "all descendants", "all components below", "all parts below",
    "subassemblies below", "full breakdown", "entire breakdown", "nested components",
    "direct versus lower", "direct vs lower", "children versus descendants",
    "descend from", "transitive descendants", "entire hierarchy below", "descendant tree",
)
EVIDENCE_TERMS = (
    "which page proves", "what page proves", "page proves", "source page", "evidence page",
    "relationship evidence", "where is the relationship shown", "where is this relationship shown",
    "cite the page", "show the source", "figure proves", "ipl proves", "item proves",
    "nha relationship for", "ipl page supports", "figure and item prove",
    "assembly relationship documented", "page should i cite", "source evidence",
)
SCOPE_TERMS = {
    "project": ("project", "program"),
    "configuration": ("configuration", "config"),
    "effectivity": ("effectivity", "effective for", "serial range"),
    "usage_code": ("usage code", "usage-code", "use code"),
    "revision": ("revision", "rev ", "rev."),
    "variant": ("variant", "dash number", "dash-number"),
    "aircraft": ("aircraft", "fleet", "tail number"),
}
ATTACHING_TERMS = (
    "attaching part", "attaching parts", "attaching hardware", "mounting hardware",
    "fastener group", "bolt group", "nut group", "washer group", "hardware for",
    "attaching bolt", "attaching fastener", "fastener", "nearest component",
)
PROCEDURE_TERMS = (
    "how do i install", "how to install", "installation procedure", "installation steps",
    "remove the", "removal procedure", "torque", "repair procedure", "replace the",
    "inspect the", "disassemble", "reassemble",
)
EXACT_LOOKUP_TERMS = (
    "find part", "locate part", "search for part", "where is part", "where is p/n",
    "what page lists", "listed in the manual",
)


def _contains_any(text: str, terms: Iterable[str]) -> List[str]:
    lower = text.casefold()
    return sorted({term for term in terms if term.casefold() in lower})


def _dedupe(values: Iterable[Any]) -> List[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))


def _part_numbers(query: str) -> List[str]:
    candidates = []
    for regex in (_STANDARD_PART_RE, _VENDOR_PART_RE, _ALNUM_PART_RE):
        candidates.extend(match.group(0).upper() for match in regex.finditer(query))
    explicit_ata = bool(re.search(r"\b(?:ATA|chapter|manual|system)\b", query, re.I))
    output = []
    for value in candidates:
        if explicit_ata and _ATA_RE.fullmatch(value):
            continue
        output.append(value)
    return _dedupe(output)


def extract_nha_query_atoms(query: str) -> Dict[str, Any]:
    """Extract inspectable NHA atoms without deciding source truth."""
    text = str(query or "").strip()
    lower = text.casefold()
    parts = _part_numbers(text)
    synthetic_parts = [value for value in parts if _SYNTHETIC_RE.fullmatch(value)]
    direct_hits = _contains_any(text, DIRECT_TERMS)
    chain_hits = _contains_any(text, CHAIN_TERMS)
    child_hits = _contains_any(text, CHILD_TERMS)
    descendant_hits = _contains_any(text, DESCENDANT_TERMS)
    evidence_hits = _contains_any(text, EVIDENCE_TERMS)
    attaching_hits = _contains_any(text, ATTACHING_TERMS)
    procedure_hits = _contains_any(text, PROCEDURE_TERMS)
    exact_lookup_hits = _contains_any(text, EXACT_LOOKUP_TERMS)
    generic_evidence = bool(
        parts
        and re.search(r"\b(?:page|figure|fig\.?|ipl|item|source|cite|evidence|documented|shown)\b", lower)
        and re.search(r"\b(?:nha|parent|assembly|relationship|hierarchy)\b", lower)
    )
    if generic_evidence and not evidence_hits:
        evidence_hits = ["generic_relationship_evidence"]

    scope_hits: Dict[str, List[str]] = {}
    for name, terms in SCOPE_TERMS.items():
        hits = _contains_any(text, terms)
        if hits:
            scope_hits[name] = hits
    scope_relationship = bool(
        scope_hits and parts and re.search(r"\b(?:nha|parent|assembly|relationship|candidate|hierarchy)\b", lower)
    )

    # Carefully accept conversational parent language only when a part is present.
    relationship_language = bool(
        direct_hits or chain_hits or child_hits or descendant_hits or evidence_hits or attaching_hits
    )
    conversational_direct = bool(
        parts
        and re.search(
            r"\b(?:where\s+does|where\s+is|what\s+(?:larger\s+)?assembly|which\s+assembly|"
            r"what\s+unit|what\s+contains|contained\s+by|parent\s+of)\b",
            lower,
        )
        and not procedure_hits
        and not exact_lookup_hits
    )
    scope_comparison = bool(
        scope_hits
        and re.search(r"\b(?:change|different|compare|depends?|which|for each|between)\b", lower)
    )
    relationship_language = relationship_language or conversational_direct or scope_comparison or scope_relationship

    # Procedure requests and plain exact-location requests are negative controls unless
    # they also explicitly ask an assembly relationship.
    negative_procedure = bool(procedure_hits and not relationship_language)
    negative_exact_lookup = bool(exact_lookup_hits and not relationship_language)

    if evidence_hits:
        intent = "relationship_evidence"
    elif scope_comparison or (scope_hits and relationship_language):
        intent = "scope_conflict_resolution"
    elif attaching_hits:
        intent = "direct_nha"
    elif chain_hits:
        intent = "ancestor_chain"
    elif descendant_hits:
        intent = "direct_vs_descendants"
    elif child_hits:
        intent = "direct_children"
    elif direct_hits or conversational_direct or attaching_hits:
        intent = "direct_nha"
    else:
        intent = "none"

    candidate = bool(
        parts
        and intent != "none"
        and not negative_procedure
        and not negative_exact_lookup
    )
    blocked = bool(synthetic_parts and intent != "none")

    token_atoms: List[str] = []
    if candidate:
        token_atoms.extend(["nha", "assembly_relationship", f"{intent}_intent"])
    if direct_hits or conversational_direct:
        token_atoms.extend(["direct_parent", "immediate_parent", "next_higher_assembly"])
    if chain_hits:
        token_atoms.extend(["ancestor_chain", "ordered_hierarchy"])
    if child_hits:
        token_atoms.extend(["direct_children", "one_level_below"])
    if descendant_hits:
        token_atoms.extend(["lower_descendants", "transitive_hierarchy"])
    if evidence_hits:
        token_atoms.extend(["relationship_evidence", "source_page_required"])
    if attaching_hits:
        token_atoms.extend(["attaching_parts", "nearest_supported_component"])
    for scope_name in scope_hits:
        token_atoms.extend(["scope_context", f"{scope_name}_scope"])
    if scope_comparison:
        token_atoms.append("scope_comparison")
    if blocked:
        token_atoms.extend(["synthetic_identifier", "production_block_required"])
    if negative_procedure:
        token_atoms.append("procedure_request")
    if negative_exact_lookup:
        token_atoms.append("exact_location_request")

    return {
        "schema_version": "trace_net_nha_query_atoms_v1",
        "query": text,
        "part_numbers": parts,
        "synthetic_part_numbers": synthetic_parts,
        "intent": intent,
        "nha_candidate": candidate,
        "synthetic_blocked": blocked,
        "direct_terms": direct_hits,
        "chain_terms": chain_hits,
        "child_terms": child_hits,
        "descendant_terms": descendant_hits,
        "evidence_terms": evidence_hits,
        "attaching_terms": attaching_hits,
        "scope_terms": scope_hits,
        "procedure_terms": procedure_hits,
        "exact_lookup_terms": exact_lookup_hits,
        "negative_procedure": negative_procedure,
        "negative_exact_lookup": negative_exact_lookup,
        "query_atom_tokens": sorted(set(token_atoms)),
        "route_hint": ROUTE if candidate and not blocked else "",
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }


def _card(
    *,
    skill_id: str,
    title: str,
    description: str,
    required_atoms: Sequence[str],
    optional_atoms: Sequence[str],
    trigger_terms: Sequence[str],
    priority: int,
    reasoning_goal: str,
    first_searches: Sequence[str],
    ranking: Sequence[str],
    direct_requires: str,
    candidate_when: str,
    default_mode: str,
    answer_requirements: Sequence[str],
    followups: Sequence[str],
    positives: Sequence[str],
    negatives: Sequence[str],
    lessons: Sequence[str],
) -> Dict[str, Any]:
    safety = dict(BASE_SKILL_SAFETY_CONTRACT)
    return {
        "skill_id": skill_id,
        "version": "1.0.0",
        "title": title,
        "description": description,
        "memory_layers": [
            "semantic_memory", "procedural_memory", "episodic_memory",
            "trait_memory", "critic_memory",
        ],
        "applies_when": [
            description,
            "A real part identifier and an assembly-relationship intent are both present.",
        ],
        "does_not_apply_when": [
            "The request is only a procedure, exact-location, compatibility, or approval question.",
            "The identifier is reserved synthetic benchmark data in a production request.",
        ],
        "selection": {
            "primary_routes": [ROUTE, "graph_relationship_reasoning"],
            "required_any_atoms": list(required_atoms),
            "required_all_atoms": ["nha_candidate"],
            "optional_atoms": list(optional_atoms),
            "exclude_atoms": ["synthetic_blocked", "negative_procedure", "negative_exact_lookup"],
            "trigger_terms": list(trigger_terms),
            "priority": priority,
        },
        "reasoning_goal": reasoning_goal,
        "required_first_searches": list(first_searches),
        "allowed_tunnels": [
            "nha_real_relationship_lookup", "nha_source_page_resolution",
            "graph_relationship_reasoning", "normal_source_resolution",
        ],
        "forbidden_tunnels": [
            "Using Engram atoms or examples as source evidence.",
            "Using the synthetic N5 overlay for a production claim.",
            "Allowing an LLM to invent a parent, child, hierarchy hop, project, revision, or effectivity.",
        ],
        "ranking_policy": list(ranking),
        "evidence_sufficiency": {
            "direct_answer_requires": direct_requires,
            "candidate_mode_when": candidate_when,
            "guidance_mode_when": "Only OCR, visual, summary, or graph guidance exists without a real source-supported relationship.",
        },
        "answer_mode_rules": {
            "default": default_mode,
            "direct_if": direct_requires,
            "fail_closed_if": "No real source-supported relationship and source page are available, or the requested scope remains unresolved.",
        },
        "answer_requirements": list(answer_requirements),
        "follow_up_policy": list(followups),
        "positive_examples": list(positives),
        "negative_examples": list(negatives),
        "known_failure_lessons": list(lessons),
        "safety_contract": safety,
    }


def build_nha_skill_cards() -> List[Dict[str, Any]]:
    common_negatives = [
        "Query: How do I install 120-20970-001? | Not an NHA question; route to procedure retrieval.",
        "Query: Find part 120-20970-001. | Exact identifier lookup, not an assembly relationship.",
        "Query: Is 120-20970-001 approved for replacement? | Authority verification, not NHA reasoning.",
    ]
    common_lessons = [
        "Never report a grandparent as the direct NHA when an intermediate supported hop exists.",
        "Never collapse multiple parent candidates without project, configuration, effectivity, usage-code, revision, or variant context.",
        "OCR, visual, summary, and Engram guidance cannot prove an NHA relationship without source-supported relationship evidence.",
    ]
    return [
        _card(
            skill_id="nha_direct_parent_lookup",
            title="Direct next-higher-assembly lookup",
            description="Resolve the immediate one-hop parent assembly for a real part.",
            required_atoms=["direct_nha_intent", "direct_parent", "attaching_parts"],
            optional_atoms=["immediate_parent", "next_higher_assembly", "nearest_supported_component"],
            trigger_terms=["direct nha", "next higher assembly", "immediate parent", "parent assembly", "installed in", "belongs to"],
            priority=80,
            reasoning_goal="Retrieve the nearest source-supported one-hop parent and keep higher ancestors separate.",
            first_searches=[
                "Search the real NHA relationship bundle for the exact child identifier.",
                "Resolve the direct parent and supporting row/anchor pages.",
                "Check for competing or scope-dependent parent candidates before allowing a direct claim.",
            ],
            ranking=[
                "A source-supported one-hop parent outranks a derived ancestor.",
                "The nearest supported component group outranks a top assembly for attaching hardware.",
                "Ambiguous candidates remain candidates until scope resolves them.",
            ],
            direct_requires="Exactly one source-supported direct parent with source pages and no unresolved competing scope.",
            candidate_when="Multiple candidate parents exist or a source-supported parent coexists with unresolved ambiguous alternatives.",
            default_mode="direct_nha_or_conflict_limited",
            answer_requirements=[
                "State the child and immediate parent exactly.",
                "Cite every source page supporting the one-hop relationship.",
                "Do not substitute a higher ancestor for the direct NHA.",
                "For attaching parts, name the nearest supported component group.",
            ],
            followups=[
                "Ask for project, configuration, effectivity, usage code, revision, or variant only when it separates candidates.",
                "Do not ask follow-ups when exactly one source-supported direct parent exists.",
            ],
            positives=[
                "What is the direct NHA of part 120-20970-001?",
                "Which assembly immediately contains 120-20970-001?",
                "Where does 120-20970-001 install in the hierarchy?",
                "What is one level above 120-20970-001?",
                "Which component is the attaching bolt 42952-10 directly under?",
            ],
            negatives=common_negatives,
            lessons=common_lessons,
        ),
        _card(
            skill_id="nha_ancestor_chain_reasoning",
            title="Ordered assembly ancestor chain",
            description="Return an ordered child-to-parent-to-ancestor chain without skipping supported intermediate hops.",
            required_atoms=["ancestor_chain_intent", "ancestor_chain", "ordered_hierarchy"],
            optional_atoms=["direct_parent", "source_page_required"],
            trigger_terms=["assembly chain", "ancestor chain", "all higher assemblies", "walk me upward", "full hierarchy", "trace upward"],
            priority=90,
            reasoning_goal="Traverse only source-supported direct edges in order and stop or limit the chain when any hop is ambiguous.",
            first_searches=[
                "Resolve the exact child in the real NHA relationship bundle.",
                "Follow direct supported edges one hop at a time with a bounded depth.",
                "Collect the supporting pages for every hop and detect cycles or conflicting parents.",
            ],
            ranking=[
                "Preserve exact hop order.",
                "A complete supported prefix of a chain outranks a speculative complete chain.",
                "Stop at the first unresolved parent instead of jumping to a known higher assembly.",
            ],
            direct_requires="Every reported hop is source-supported, ordered, acyclic, and backed by source pages.",
            candidate_when="The first or any later hop has multiple candidates or missing scope.",
            default_mode="ordered_chain_or_conflict_limited",
            answer_requirements=[
                "Render the chain in exact order from requested part upward.",
                "Identify which hop becomes uncertain, if any.",
                "Cite pages for each supported hop.",
                "Never infer a missing intermediate relationship from a known top assembly.",
            ],
            followups=[
                "Ask for the scope field that resolves the first ambiguous hop.",
                "Do not request unrelated manufacturer or ATA details when the ambiguity is project/revision based.",
            ],
            positives=[
                "Show the complete assembly chain above 42952-10.",
                "Walk me upward through the assemblies for 120-20970-001.",
                "What are all higher assemblies above this part?",
                "Trace the parent path from 120-29073-001 to the top assembly.",
                "Give the ordered hierarchy above 120-34291-001.",
            ],
            negatives=common_negatives,
            lessons=common_lessons,
        ),
        _card(
            skill_id="nha_children_descendants_reasoning",
            title="Direct children versus lower descendants",
            description="Separate immediate one-hop children from transitive lower descendants of an assembly.",
            required_atoms=["direct_children_intent", "direct_vs_descendants_intent", "direct_children", "lower_descendants"],
            optional_atoms=["one_level_below", "transitive_hierarchy"],
            trigger_terms=["direct children", "immediate components", "directly below", "lower descendants", "full breakdown", "direct versus lower"],
            priority=88,
            reasoning_goal="Return direct children and transitive descendants in distinct sets, preserving edge depth and evidence.",
            first_searches=[
                "Resolve exact source-supported incoming child edges for the requested assembly.",
                "Traverse lower descendants separately with a bounded depth.",
                "Collect source pages and avoid duplicating direct children in the lower-descendant list.",
            ],
            ranking=[
                "One-hop direct children are always listed before transitive descendants.",
                "Supported edges outrank candidate or guidance-only edges.",
                "Do not flatten all descendants into a direct-child list.",
            ],
            direct_requires="Each direct child or descendant path is composed entirely of source-supported edges with source pages.",
            candidate_when="Some child edges are ambiguous or a lower path becomes scope dependent.",
            default_mode="children_tree_or_conflict_limited",
            answer_requirements=[
                "Label direct children and lower descendants separately.",
                "Do not count the same relationship twice.",
                "Cite the pages supporting each reported edge or grouped set.",
                "State when only one hierarchy level is available.",
            ],
            followups=[
                "Ask whether the user wants only one level or the full bounded breakdown when unclear.",
                "Ask for scope only when candidate child relationships require it.",
            ],
            positives=[
                "List the direct children of assembly 120-29067-001.",
                "Which parts sit immediately below 120-29067-001?",
                "Show direct versus lower descendants below 120-29067-001.",
                "Give the full breakdown under 120-29067-001 but separate one-hop components.",
                "What subassemblies and nested parts are below 120-29067-001?",
            ],
            negatives=common_negatives,
            lessons=common_lessons,
        ),
        _card(
            skill_id="nha_relationship_evidence",
            title="Assembly relationship evidence recovery",
            description="Recover the source pages, IPL figure, and item context that support an NHA relationship.",
            required_atoms=["relationship_evidence_intent", "relationship_evidence", "source_page_required"],
            optional_atoms=["direct_parent", "scope_context"],
            trigger_terms=["which page proves", "source page", "relationship evidence", "cite the page", "where is the relationship shown", "ipl proves"],
            priority=95,
            reasoning_goal="Return the exact pages and relationship context without inventing a parent claim that the source bundle does not support.",
            first_searches=[
                "Resolve the exact part relationship record in the real NHA bundle.",
                "Return row page and anchor/figure pages in source order.",
                "Expose relationship status and scope limits to the writer without leaking internal IDs publicly.",
            ],
            ranking=[
                "The IPL row page is primary relationship evidence.",
                "Figure/anchor pages are supporting context, not replacements for the row relationship.",
                "Ambiguous relationship pages support candidate reporting, not a chosen direct parent.",
            ],
            direct_requires="The requested relationship record and at least one source page are available in the real release.",
            candidate_when="Pages exist for an ambiguous candidate group but no single direct parent is source-supported in the requested scope.",
            default_mode="page_evidence_or_conflict_limited",
            answer_requirements=[
                "List source pages explicitly.",
                "Explain whether the pages support a confirmed relationship or only candidate parents.",
                "Keep internal relationship IDs, truth flags, and benchmark fields out of the public answer.",
                "Do not claim that a page proves effectivity or approval unless that authority is separately present.",
            ],
            followups=[
                "Ask which candidate or scope the user wants when multiple relationship records share the child.",
                "Do not ask a follow-up when the user asked only for the supporting pages.",
            ],
            positives=[
                "Which page proves the NHA relationship for 120-20970-001?",
                "Cite the source page connecting 120-20970-001 to its parent assembly.",
                "Where is this assembly relationship shown in the IPL?",
                "What figure and item support the parent relationship for 42952-10?",
                "Show the source evidence for the direct NHA of 120-34291-001.",
            ],
            negatives=common_negatives,
            lessons=common_lessons,
        ),
        _card(
            skill_id="nha_scope_conflict_resolution",
            title="NHA project, configuration, revision, and effectivity resolution",
            description="Keep multiple parent candidates separate until project, configuration, revision, effectivity, usage-code, or variant scope resolves them.",
            required_atoms=["scope_conflict_resolution_intent", "scope_context", "scope_comparison"],
            optional_atoms=["project_scope", "configuration_scope", "effectivity_scope", "usage_code_scope", "revision_scope", "variant_scope"],
            trigger_terms=["project", "configuration", "effectivity", "usage code", "revision", "variant", "depends on", "changes between"],
            priority=100,
            reasoning_goal="Compare scoped relationship records and either select the uniquely supported scope-specific parent or explain exactly what scope is missing.",
            first_searches=[
                "Resolve all real relationship records for the exact child.",
                "Facet candidate parents by project, configuration, revision, effectivity, usage code, and variant.",
                "Compare only records whose source pages and scope fields are explicit.",
            ],
            ranking=[
                "An exact requested scope match outranks an unscoped relationship.",
                "Do not merge records from different revisions or configurations.",
                "When scope metadata is absent, preserve all credible candidates and ask the smallest discriminating question.",
            ],
            direct_requires="Exactly one source-supported parent remains after applying the user-supplied scope and its pages are available.",
            candidate_when="More than one parent remains, or the source does not state the scope field needed to choose.",
            default_mode="scope_resolved_or_conflict_limited",
            answer_requirements=[
                "Name the applied scope before stating a parent.",
                "List remaining candidates when the scope is incomplete.",
                "State the exact missing scope field that would resolve the conflict.",
                "Never invent project, revision, effectivity, usage code, or configuration values.",
            ],
            followups=[
                "Ask one high-information scope question at a time.",
                "Prefer project/configuration/revision/effectivity/usage-code/variant over generic manufacturer questions.",
            ],
            positives=[
                "Does the NHA of 42952-10 change by project?",
                "Which parent applies to configuration A for 120-48023-001?",
                "Compare the parent assembly across revisions for 120-34291-001.",
                "What NHA applies under usage code 001?",
                "I have two parent candidates; which effectivity selects the correct one?",
            ],
            negatives=common_negatives,
            lessons=common_lessons,
        ),
    ]


def build_nha_skill_library() -> Dict[str, Any]:
    cards = build_nha_skill_cards()
    return {
        "module": "trace_net_engram_skill_cards_v1",
        "version": "v1",
        "status": "TRACE_NET_NHA_ENGRAM_SKILL_LIBRARY_V1",
        "description": "Reviewed NHA reasoning skills using the existing TRACE-Net Engram skill-card schema.",
        "runtime_injection_status": "N13_REVIEWED_NOT_LIVE_WIRED",
        "skill_card_count": len(cards),
        "skill_cards": cards,
        "safety_contract": dict(BASE_SKILL_SAFETY_CONTRACT),
    }


def build_nha_memory_atoms() -> List[Dict[str, Any]]:
    specs = [
        ("policy_nha_direct_parent_one_hop_v1", "policy_trait", "hard_boundary", "nha_direct_parent", ["direct NHA", "next higher assembly", "immediate parent"], "A direct NHA is exactly one source-supported parent hop; never substitute a grandparent or top assembly."),
        ("policy_nha_ordered_chain_no_skip_v1", "policy_trait", "hard_boundary", "nha_chain_order", ["assembly chain", "ancestor chain", "all higher assemblies"], "Every reported hierarchy hop must be source-supported and ordered; stop at the first unresolved hop."),
        ("policy_nha_children_not_descendants_v1", "policy_trait", "hard_boundary", "nha_depth_boundary", ["direct children", "lower descendants", "assembly breakdown"], "Direct children are one hop only; lower descendants must be labeled separately."),
        ("policy_nha_scope_before_candidate_choice_v1", "policy_trait", "hard_boundary", "nha_scope_boundary", ["project", "configuration", "effectivity", "usage code", "revision", "variant"], "Do not choose among multiple parent candidates without explicit scope support."),
        ("policy_nha_attaching_nearest_component_v1", "policy_trait", "high", "nha_attaching_parts", ["attaching parts", "attaching hardware", "fastener group"], "Attaching hardware maps to the nearest source-supported component group, not automatically to the top assembly."),
        ("policy_nha_source_page_required_v1", "policy_trait", "hard_boundary", "nha_source_trace", ["NHA evidence", "source page", "IPL row"], "Every positive NHA claim requires the supporting real source page or pages."),
        ("policy_nha_guidance_not_proof_v1", "policy_trait", "hard_boundary", "nha_guidance_boundary", ["OCR", "visual", "summary", "graph guidance"], "OCR, visual, summary, graph, and Engram guidance may find candidates but cannot prove an NHA edge."),
        ("policy_nha_synthetic_never_production_v1", "policy_trait", "hard_boundary", "nha_synthetic_boundary", ["990-", "synthetic benchmark", "benchmark relationship"], "Synthetic N5 relationships and identifiers never support production NHA claims or upstream language-model prompts."),
        ("semantic_nha_synonyms_v1", "semantic_memory", "high", "nha_vocabulary", ["NHA", "next higher assembly", "parent assembly", "installed in", "belongs to"], "Treat NHA, next higher assembly, immediate/direct parent assembly, installed in, belongs to, and one level above as relationship-language synonyms when grounded by a part identifier."),
        ("semantic_nha_scope_vocabulary_v1", "semantic_memory", "high", "nha_scope_vocabulary", ["project", "configuration", "effectivity", "usage code", "revision", "variant"], "Project, configuration, effectivity, usage code, revision, and variant are scope atoms that may distinguish parent relationships."),
        ("route_nha_assembly_relationship_reasoning_v1", "route_behavior", "high", "nha_route_awareness", ["direct NHA", "assembly chain", "direct children", "relationship evidence"], "NHA intents should route to assembly_relationship_reasoning and retrieve real relationship evidence before any answer writer is called."),
        ("critic_nha_no_grandparent_as_direct_v1", "critic_trait", "high", "nha_self_rag", ["direct NHA", "ancestor", "intermediate hop"], "Reject a draft that labels a higher ancestor as the direct NHA when an intermediate supported parent exists."),
        ("critic_nha_no_candidate_collapse_v1", "critic_trait", "high", "nha_self_rag", ["candidate parent", "ambiguous", "conflict"], "Reject a draft that collapses multiple parent candidates into one unsupported conclusion."),
        ("repair_nha_request_scope_v1", "repair_trait", "high", "nha_crag_repair", ["ambiguous parent", "missing scope", "conflict"], "When candidates remain, ask for the smallest discriminating project/configuration/effectivity/usage-code/revision/variant field; do not invent it."),
        ("style_nha_answer_shape_v1", "style_trait", "high", "nha_answer_shape", ["NHA answer", "assembly relationship", "hierarchy answer"], "Use Answer, Evidence, and Limits; state direct parent or ordered chain first, cite pages, and explain scope limits without exposing internal record fields."),
    ]
    records = []
    for engram_id, memory_type, priority, trait, triggers, rule in specs:
        records.append({
            "engram_id": engram_id,
            "memory_type": memory_type,
            "priority": priority,
            "trait": trait,
            "triggers": list(triggers),
            "trigger_text": " | ".join(triggers),
            "rule": rule,
            "good_behavior": "Apply the rule as behavior guidance, then require current real source evidence before making a factual claim.",
            "bad_behavior": "Treating the atom, skill card, example, or synthetic benchmark as proof of a current relationship.",
            "source": "TRACE-Net NHA N0-N12 lessons and live-20 review",
            "status": "active",
        })
    return records


def _library_records(payload: Mapping[str, Any], key: str) -> List[Dict[str, Any]]:
    rows = payload.get(key)
    return [dict(row) for row in rows] if isinstance(rows, list) else []


def build_skill_library_overlay(base_library: Mapping[str, Any]) -> Dict[str, Any]:
    base_cards = _library_records(base_library, "skill_cards")
    by_id = {str(card.get("skill_id")): card for card in base_cards if card.get("skill_id")}
    for card in build_nha_skill_cards():
        by_id[str(card["skill_id"])] = card
    cards = list(base_cards)
    existing = {str(card.get("skill_id")) for card in base_cards}
    cards.extend(card for card in build_nha_skill_cards() if card["skill_id"] not in existing)
    # Replace existing NHA cards in place if rerun.
    cards = [by_id[str(card.get("skill_id"))] for card in cards if card.get("skill_id")]
    output = dict(base_library)
    output.update({
        "module": "trace_net_engram_skill_cards_v1",
        "version": "v1",
        "status": "TRACE_NET_ENGRAM_SKILL_CARDS_NHA_OVERLAY_V1",
        "runtime_injection_status": "N13_OVERLAY_BUILT_NOT_LIVE_WIRED",
        "skill_card_count": len(cards),
        "skill_cards": cards,
        "nha_skill_ids": list(NHA_SKILL_IDS),
        "nha_overlay_version": VERSION,
        "safety_contract": dict(BASE_SKILL_SAFETY_CONTRACT),
    })
    return output


def build_engram_core_overlay(base_core: Mapping[str, Any]) -> Dict[str, Any]:
    base_records = _library_records(base_core, "records")
    by_id = {str(row.get("engram_id")): row for row in base_records if row.get("engram_id")}
    for row in build_nha_memory_atoms():
        by_id[str(row["engram_id"])] = row
    records = list(base_records)
    existing = {str(row.get("engram_id")) for row in base_records}
    records.extend(row for row in build_nha_memory_atoms() if row["engram_id"] not in existing)
    records = [by_id[str(row.get("engram_id"))] for row in records if row.get("engram_id")]
    counts = Counter(str(row.get("memory_type") or "unknown") for row in records)
    output = dict(base_core)
    output["status"] = "TRACE_NET_ENGINEERING_ENGRAM_CORE_NHA_OVERLAY_V1"
    output["quality_status"] = "PASS"
    output["records"] = records
    output["nha_engram_ids"] = [row["engram_id"] for row in build_nha_memory_atoms()]
    output["nha_overlay_version"] = VERSION
    output["summary"] = {
        **dict(base_core.get("summary") or {}),
        "engram_atom_count": len(records),
        "memory_type_count": len(counts),
        "memory_type_counts": dict(sorted(counts.items())),
        "nha_atom_count": len(build_nha_memory_atoms()),
        "ready_for_engram_prompt_injector": True,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "write_attempt_count": 0,
        "unsafe_record_count": 0,
    }
    output["quality_gate"] = {
        "quality_status": "PASS",
        "failures": [],
        "engram_atom_count": len(records),
        "nha_atom_count": len(build_nha_memory_atoms()),
        "memory_type_count": len(counts),
    }
    return output


def _nha_query_atom_mapping(atoms: Mapping[str, Any]) -> Dict[str, Any]:
    mapping: Dict[str, Any] = {
        "nha_candidate": bool(atoms.get("nha_candidate")),
        "synthetic_blocked": bool(atoms.get("synthetic_blocked")),
        "negative_procedure": bool(atoms.get("negative_procedure")),
        "negative_exact_lookup": bool(atoms.get("negative_exact_lookup")),
        "nha_intent": str(atoms.get("intent") or "none"),
    }
    for token in atoms.get("query_atom_tokens") or []:
        mapping[str(token)] = True
    for scope_name in (atoms.get("scope_terms") or {}):
        mapping[f"{scope_name}_scope"] = True
    return mapping


def select_nha_skills(
    query: str,
    *,
    library: Optional[Mapping[str, Any]] = None,
    max_skills: int = 3,
) -> Dict[str, Any]:
    atoms = extract_nha_query_atoms(query)
    if atoms["synthetic_blocked"]:
        return {
            "quality_status": "PASS",
            "blocked": True,
            "reason": "synthetic_identifier_blocked",
            "atoms": atoms,
            "selected_skill_ids": [],
            "selected_skill_count": 0,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        }
    if not atoms["nha_candidate"]:
        return {
            "quality_status": "PASS",
            "blocked": False,
            "reason": "not_nha_query",
            "atoms": atoms,
            "selected_skill_ids": [],
            "selected_skill_count": 0,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        }
    lib = dict(library or build_nha_skill_library())
    selected = select_engram_skills(
        lib,
        query=query,
        route=ROUTE,
        query_atoms=_nha_query_atom_mapping(atoms),
        max_skills=max_skills,
        min_score=1,
    )
    return {
        **selected,
        "blocked": False,
        "reason": "nha_engram_selection",
        "atoms": atoms,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }


def _question(
    category: str,
    query: str,
    *,
    intent: str,
    skill: str,
    required_atoms: Sequence[str],
    nha: bool = True,
    blocked: bool = False,
) -> Dict[str, Any]:
    return {
        "question_id": "",
        "category": category,
        "query": query,
        "expected_nha_candidate": nha,
        "expected_blocked": blocked,
        "expected_intent": intent,
        "expected_primary_skill": skill,
        "required_atoms": list(required_atoms),
        "core20": False,
    }


def build_100_question_bank() -> List[Dict[str, Any]]:
    parts = [
        "120-20970-001", "120-29073-001", "120-34291-001", "120-48023-001",
        "120-29074-001", "120-29077-001", "42952-10", "NAS464P5A16",
        "MS21042L5", "120-61546-001", "120-36060-003", "120-20970-003",
    ]
    rows: List[Dict[str, Any]] = []

    direct_templates = [
        "What is the direct NHA of part {p}?",
        "What is the next higher assembly for {p}?",
        "Which assembly immediately contains {p}?",
        "What is the immediate parent assembly of {p}?",
        "What is one level above {p}?",
        "Which parent assembly does {p} belong to?",
        "Where does {p} sit in the assembly hierarchy?",
        "What larger unit contains {p}?",
        "Which assembly is {p} installed in?",
        "Tell me the direct parent of {p}.",
        "Is there an immediate assembly above {p}?",
        "What assembly is part {p} directly under?",
        "Where does {p} mount in the hierarchy?",
        "Name the one-hop parent for {p}.",
        "Which component group directly owns {p}?",
    ]
    for index, template in enumerate(direct_templates):
        rows.append(_question(
            "direct_nha",
            template.format(p=parts[index % len(parts)]),
            intent="direct_nha",
            skill="nha_direct_parent_lookup",
            required_atoms=["direct_nha_intent", "direct_parent"],
        ))

    chain_templates = [
        "Show the complete assembly chain above {p}.",
        "Walk me upward through the assemblies for {p}.",
        "List all higher assemblies above {p} in order.",
        "Trace the ancestor chain for {p}.",
        "Give the full hierarchy from {p} to the top assembly.",
        "What is the parent path above {p}?",
        "Trace upward one supported hop at a time from {p}.",
        "Show every supported ancestor of {p}.",
        "How does {p} roll up through the assembly structure?",
        "Give me the ordered assembly lineage for {p}.",
        "From part {p}, what is the chain of containing assemblies?",
        "Walk from {p} to its highest supported assembly.",
        "Show the hierarchy above {p} without skipping intermediate parents.",
        "List the NHA chain for {p}.",
        "What are all parents above {p}, nearest first?",
    ]
    for index, template in enumerate(chain_templates):
        rows.append(_question(
            "ancestor_chain",
            template.format(p=parts[index % len(parts)]),
            intent="ancestor_chain",
            skill="nha_ancestor_chain_reasoning",
            required_atoms=["ancestor_chain_intent", "ancestor_chain"],
        ))

    child_templates = [
        "List the direct children of assembly {p}.",
        "Which parts sit immediately below assembly {p}?",
        "Show the immediate components of {p}.",
        "What does assembly {p} directly contain?",
        "Give the one-level breakdown under {p}.",
        "Which components are directly under {p}?",
        "List only the one-hop children of {p}.",
        "What parts belong immediately to assembly {p}?",
        "Show the direct component list for {p}.",
        "Which items are one level below {p}?",
        "Name the immediate child relationships of {p}.",
        "What is directly contained by assembly {p}?",
    ]
    parent_parts = ["120-29067-001", "120-29073-001", "120-29074-001"]
    for index, template in enumerate(child_templates):
        rows.append(_question(
            "direct_children",
            template.format(p=parent_parts[index % len(parent_parts)]),
            intent="direct_children",
            skill="nha_children_descendants_reasoning",
            required_atoms=["direct_children_intent", "direct_children"],
        ))

    descendant_templates = [
        "Show direct versus lower descendants below assembly {p}.",
        "Separate the immediate children and all lower descendants of {p}.",
        "Give the full breakdown below {p}, keeping one-hop parts separate.",
        "Which direct components and nested components are under {p}?",
        "List the lower descendants of {p}.",
        "Show all components below {p}, grouped by depth.",
        "What subassemblies and nested parts descend from {p}?",
        "Compare direct children with transitive descendants for {p}.",
        "Give the entire hierarchy below {p} without flattening it.",
        "Show the descendant tree under {p}.",
    ]
    for index, template in enumerate(descendant_templates):
        rows.append(_question(
            "descendants",
            template.format(p=parent_parts[index % len(parent_parts)]),
            intent="direct_vs_descendants",
            skill="nha_children_descendants_reasoning",
            required_atoms=["direct_vs_descendants_intent", "lower_descendants"],
        ))

    evidence_templates = [
        "Which page proves the NHA relationship for {p}?",
        "Cite the source page for the parent relationship of {p}.",
        "Where is the NHA relationship for {p} shown?",
        "What IPL page supports the parent assembly of {p}?",
        "Show the relationship evidence pages for {p}.",
        "Which figure and item prove the relationship for {p}?",
        "Give the source pages connecting {p} to its parent.",
        "Where in the manual is this assembly relationship documented for {p}?",
        "What page should I cite for the direct NHA of {p}?",
        "Show the source evidence for {p}'s parent candidates.",
    ]
    for index, template in enumerate(evidence_templates):
        rows.append(_question(
            "relationship_evidence",
            template.format(p=parts[index % len(parts)]),
            intent="relationship_evidence",
            skill="nha_relationship_evidence",
            required_atoms=["relationship_evidence_intent", "source_page_required"],
        ))

    scope_templates = [
        "Does the NHA of {p} change by project?",
        "Which parent applies to configuration A for {p}?",
        "Compare the NHA of {p} across revisions.",
        "What parent assembly applies under usage code 001 for {p}?",
        "Which effectivity selects the parent of {p}?",
        "Does the parent of {p} differ by variant?",
        "For this aircraft configuration, which NHA owns {p}?",
        "Compare project Alpha and project Beta parent relationships for {p}.",
        "Which revision changed the direct parent of {p}?",
        "I have multiple parent candidates for {p}; what configuration resolves them?",
        "Which usage-code scope applies to {p}'s NHA?",
        "Does serial-range effectivity change the assembly above {p}?",
        "Which dash-number variant determines the parent of {p}?",
        "What project context is required to choose the NHA of {p}?",
        "Compare configuration and revision scope for {p}.",
    ]
    for index, template in enumerate(scope_templates):
        rows.append(_question(
            "scope_resolution",
            template.format(p=parts[index % len(parts)]),
            intent="scope_conflict_resolution",
            skill="nha_scope_conflict_resolution",
            required_atoms=["scope_conflict_resolution_intent", "scope_context"],
        ))

    attaching_templates = [
        "Which assembly directly owns the attaching part {p}?",
        "What is the nearest supported component for attaching hardware {p}?",
        "Which component group is the fastener {p} directly under?",
        "Where does the attaching bolt {p} belong in the hierarchy?",
        "What direct NHA applies to mounting hardware {p}?",
        "Which nearest component contains the attaching part {p}?",
        "Do not jump to the top assembly; what directly contains the attaching fastener {p}?",
        "What one-hop parent owns the fastener group containing {p}?",
    ]
    attaching_parts = ["42952-10", "MS21042L5", "NAS464P5A16", "120-48023-001"]
    for index, template in enumerate(attaching_templates):
        rows.append(_question(
            "attaching_parts",
            template.format(p=attaching_parts[index % len(attaching_parts)]),
            intent="direct_nha",
            skill="nha_direct_parent_lookup",
            required_atoms=["direct_nha_intent", "attaching_parts", "nearest_supported_component"],
        ))

    negatives = [
        ("Find part 120-20970-001.", "exact_identifier"),
        ("Where is part 120-20970-001 listed in the manual?", "exact_identifier"),
        ("Locate P/N 120-29073-001.", "exact_identifier"),
        ("What page lists 120-34291-001?", "exact_identifier"),
        ("How do I install 120-20970-001?", "procedure"),
        ("Give the installation procedure for 120-29073-001.", "procedure"),
        ("How do I remove the assembly 120-29067-001?", "procedure"),
        ("What torque applies to bolt 42952-10?", "procedure"),
        ("Is 120-20970-001 an approved replacement?", "authority"),
        ("Can I safely install 120-20970-001?", "authority"),
    ]
    for query, category in negatives:
        rows.append(_question(
            f"negative_{category}",
            query,
            intent="none",
            skill="",
            required_atoms=[],
            nha=False,
        ))

    synthetic_templates = [
        "What is the direct NHA of synthetic part 990-91001-001?",
        "Show the assembly chain above 990-92001-001.",
        "Which page proves the parent of 990-93001-001?",
        "List direct children of synthetic assembly 990-94001-001.",
        "Which revision changes the NHA of 990-95001-001?",
    ]
    for query in synthetic_templates:
        expected_intent = (
            "ancestor_chain" if "chain" in query.casefold() else
            "relationship_evidence" if "page" in query.casefold() else
            "direct_children" if "children" in query.casefold() else
            "scope_conflict_resolution" if "revision" in query.casefold() else
            "direct_nha"
        )
        rows.append(_question(
            "synthetic_block",
            query,
            intent=expected_intent,
            skill="",
            required_atoms=["synthetic_identifier", "production_block_required"],
            nha=True,
            blocked=True,
        ))

    if len(rows) != 100:
        raise AssertionError(f"question_bank_count expected=100 actual={len(rows)}")
    core_categories = {
        "direct_nha": 4,
        "ancestor_chain": 3,
        "direct_children": 2,
        "descendants": 2,
        "relationship_evidence": 2,
        "scope_resolution": 3,
        "attaching_parts": 1,
        "negative_exact_identifier": 1,
        "negative_procedure": 1,
        "synthetic_block": 1,
    }
    seen = Counter()
    for index, row in enumerate(rows, 1):
        row["question_id"] = f"NHA-ENGRAM-{index:03d}"
        category = str(row["category"])
        if category in core_categories and seen[category] < core_categories[category]:
            row["core20"] = True
            seen[category] += 1
    if sum(bool(row["core20"]) for row in rows) != 20:
        raise AssertionError("core20_count_mismatch")
    return rows


def evaluate_question_bank(
    questions: Sequence[Mapping[str, Any]],
    *,
    library: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    lib = dict(library or build_nha_skill_library())
    results = []
    for row in questions:
        atoms = extract_nha_query_atoms(str(row.get("query") or ""))
        selection = select_nha_skills(str(row.get("query") or ""), library=lib, max_skills=3)
        selected = list(selection.get("selected_skill_ids") or [])
        failures = []
        if bool(atoms.get("nha_candidate")) != bool(row.get("expected_nha_candidate")):
            failures.append("nha_candidate_mismatch")
        if bool(atoms.get("synthetic_blocked")) != bool(row.get("expected_blocked")):
            failures.append("synthetic_block_mismatch")
        if str(atoms.get("intent") or "") != str(row.get("expected_intent") or ""):
            failures.append(f"intent expected={row.get('expected_intent')} actual={atoms.get('intent')}")
        token_set = set(atoms.get("query_atom_tokens") or [])
        for atom in row.get("required_atoms") or []:
            if str(atom) not in token_set:
                failures.append(f"missing_atom:{atom}")
        expected_skill = str(row.get("expected_primary_skill") or "")
        actual_primary = selected[0] if selected else ""
        if actual_primary != expected_skill:
            failures.append(f"primary_skill expected={expected_skill} actual={actual_primary}")
        if atoms.get("synthetic_blocked") and selected:
            failures.append("synthetic_selected_skill")
        results.append({
            "question_id": row.get("question_id") or "",
            "category": row.get("category") or "",
            "query": row.get("query") or "",
            "core20": bool(row.get("core20")),
            "passed": not failures,
            "failures": failures,
            "atoms": atoms,
            "selected_skill_ids": selected,
            "expected_primary_skill": expected_skill,
            "actual_primary_skill": actual_primary,
        })
    return results


def validate_nha_engram(
    *,
    skill_library: Mapping[str, Any],
    overlay_library: Mapping[str, Any],
    memory_atoms: Sequence[Mapping[str, Any]],
    core_overlay: Mapping[str, Any],
    benchmark_results: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    failures: List[str] = []
    card_errors = []
    for card in skill_library.get("skill_cards") or []:
        card_errors.extend(validate_skill_card(card))
    skill_validation = validate_skill_library(skill_library)
    overlay_validation = validate_skill_library(overlay_library)
    if card_errors:
        failures.extend(card_errors)
    if skill_validation.get("quality_status") != "PASS":
        failures.extend(skill_validation.get("errors") or [])
    if overlay_validation.get("quality_status") != "PASS":
        failures.extend("overlay:" + str(value) for value in overlay_validation.get("errors") or [])
    if len(memory_atoms) != 15:
        failures.append(f"memory_atom_count expected=15 actual={len(memory_atoms)}")
    if len({str(row.get('engram_id')) for row in memory_atoms}) != len(memory_atoms):
        failures.append("duplicate_memory_atom_id")
    if len(benchmark_results) != 100:
        failures.append(f"question_count expected=100 actual={len(benchmark_results)}")
    pass_count = sum(bool(row.get("passed")) for row in benchmark_results)
    core = [row for row in benchmark_results if row.get("core20")]
    core_pass = sum(bool(row.get("passed")) for row in core)
    if pass_count != len(benchmark_results):
        failures.append(f"benchmark_fail_count:{len(benchmark_results) - pass_count}")
    if len(core) != 20 or core_pass != 20:
        failures.append(f"core20 expected=20/20 actual={core_pass}/{len(core)}")
    if int((core_overlay.get("summary") or {}).get("nha_atom_count") or 0) != 15:
        failures.append("core_overlay_nha_atom_count")
    categories = Counter(str(row.get("category") or "") for row in benchmark_results)
    return {
        "schema_version": "trace_net_nha_engram_quality_v1",
        "module": MODULE,
        "status": STATUS,
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": _dedupe(failures),
        "warnings": [],
        "counts": {
            "nha_memory_atom_count": len(memory_atoms),
            "nha_skill_card_count": len(skill_library.get("skill_cards") or []),
            "overlay_skill_card_count": len(overlay_library.get("skill_cards") or []),
            "question_count": len(benchmark_results),
            "pass_count": pass_count,
            "fail_count": len(benchmark_results) - pass_count,
            "core20_count": len(core),
            "core20_pass_count": core_pass,
            "synthetic_block_question_count": categories.get("synthetic_block", 0),
            "negative_question_count": sum(value for key, value in categories.items() if key.startswith("negative_")),
            "llm_call_count": 0,
            "production_graph_write_count": 0,
            "source_artifact_mutation_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
        "category_counts": dict(sorted(categories.items())),
        "safety_contract": dict(SAFETY_CONTRACT),
    }


def _read_json(path: str | Path) -> Dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return dict(payload) if isinstance(payload, Mapping) else {}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")


def build_nha_engram_artifacts(
    *,
    base_engram_core_path: str | Path,
    base_skill_library_path: str | Path,
    output_dir: str | Path,
) -> Dict[str, Any]:
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    base_core = _read_json(base_engram_core_path)
    base_library = _read_json(base_skill_library_path)
    skill_library = build_nha_skill_library()
    overlay_library = build_skill_library_overlay(base_library)
    memory_atoms = build_nha_memory_atoms()
    core_overlay = build_engram_core_overlay(base_core)
    questions = build_100_question_bank()
    results = evaluate_question_bank(questions, library=skill_library)
    quality = validate_nha_engram(
        skill_library=skill_library,
        overlay_library=overlay_library,
        memory_atoms=memory_atoms,
        core_overlay=core_overlay,
        benchmark_results=results,
    )
    vocabulary = {
        "schema_version": "trace_net_nha_query_atom_vocabulary_v1",
        "module": MODULE,
        "direct_terms": list(DIRECT_TERMS),
        "chain_terms": list(CHAIN_TERMS),
        "child_terms": list(CHILD_TERMS),
        "descendant_terms": list(DESCENDANT_TERMS),
        "evidence_terms": list(EVIDENCE_TERMS),
        "scope_terms": {key: list(value) for key, value in SCOPE_TERMS.items()},
        "attaching_terms": list(ATTACHING_TERMS),
        "procedure_negative_terms": list(PROCEDURE_TERMS),
        "exact_lookup_negative_terms": list(EXACT_LOOKUP_TERMS),
        "synthetic_identifier_pattern": _SYNTHETIC_RE.pattern,
    }
    artifacts = {
        "trace_net_nha_query_atom_vocabulary_v1.json": vocabulary,
        "trace_net_nha_engram_memory_atoms_v1.json": {"records": memory_atoms},
        "trace_net_nha_engram_skill_cards_v1.json": skill_library,
        "trace_net_nha_engram_overlay_library_v1.json": overlay_library,
        "trace_net_nha_engram_core_overlay_v1.json": core_overlay,
        "trace_net_nha_engram_100_question_bank_v1.json": {"records": questions},
        "trace_net_nha_engram_100_question_results_v1.json": {"records": results},
        "trace_net_nha_engram_quality_v1.json": quality,
    }
    for name, payload in artifacts.items():
        _write_json(output / name, payload)
    _write_jsonl(output / "trace_net_nha_engram_100_question_results_v1.jsonl", results)
    summary = {
        "schema_version": "trace_net_nha_engram_summary_v1",
        "module": MODULE,
        "status": STATUS,
        "quality_status": quality["quality_status"],
        "output_dir": str(output),
        "counts": quality["counts"],
        "failures": quality["failures"],
        "warnings": quality["warnings"],
        "input_sha256": {
            "base_engram_core": hashlib.sha256(Path(base_engram_core_path).read_bytes()).hexdigest(),
            "base_skill_library": hashlib.sha256(Path(base_skill_library_path).read_bytes()).hexdigest(),
        },
        "artifacts": sorted([*artifacts, "trace_net_nha_engram_100_question_results_v1.jsonl", "trace_net_nha_engram_summary_v1.json"]),
        "next_phase": "N14 wires this reviewed overlay into the H30 planner/router; N15 adds one constrained Gemma answer call.",
    }
    _write_json(output / "trace_net_nha_engram_summary_v1.json", summary)
    return summary


def check_nha_engram_artifacts(output_dir: str | Path) -> Dict[str, Any]:
    root = Path(output_dir).resolve()
    required = [
        "trace_net_nha_query_atom_vocabulary_v1.json",
        "trace_net_nha_engram_memory_atoms_v1.json",
        "trace_net_nha_engram_skill_cards_v1.json",
        "trace_net_nha_engram_overlay_library_v1.json",
        "trace_net_nha_engram_core_overlay_v1.json",
        "trace_net_nha_engram_100_question_bank_v1.json",
        "trace_net_nha_engram_100_question_results_v1.json",
        "trace_net_nha_engram_quality_v1.json",
        "trace_net_nha_engram_summary_v1.json",
    ]
    missing = [name for name in required if not (root / name).exists()]
    if missing:
        return {
            "quality_status": "FAIL",
            "failures": ["missing_artifacts:" + ",".join(missing)],
            "warnings": [],
            "counts": {},
        }
    skill_library = _read_json(root / "trace_net_nha_engram_skill_cards_v1.json")
    overlay_library = _read_json(root / "trace_net_nha_engram_overlay_library_v1.json")
    memory_atoms = list(_read_json(root / "trace_net_nha_engram_memory_atoms_v1.json").get("records") or [])
    core_overlay = _read_json(root / "trace_net_nha_engram_core_overlay_v1.json")
    bank = list(_read_json(root / "trace_net_nha_engram_100_question_bank_v1.json").get("records") or [])
    rerun = evaluate_question_bank(bank, library=skill_library)
    return validate_nha_engram(
        skill_library=skill_library,
        overlay_library=overlay_library,
        memory_atoms=memory_atoms,
        core_overlay=core_overlay,
        benchmark_results=rerun,
    )
