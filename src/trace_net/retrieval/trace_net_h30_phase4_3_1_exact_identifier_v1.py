#!/usr/bin/env python3
"""TRACE-Net H30 Phase 4.3.1 exact-identifier and planner-readiness helpers.

This module is deterministic and read-only. It improves contextual identifier
classification, reapplies final candidate/evidence filtering after bounded repair,
and defines a validated proposal contract for a future Engram-assisted LLM planner.
The planner contract is proposal-only in this phase: it cannot execute retrieval,
grant answer permission, select evidence, or mutate source truth.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional, Set

MODULE = "trace_net_h30_phase4_3_1_exact_identifier_v1"
PATCH_ID = "trace_net_h30_phase4_3_1_exact_identifier_and_planner_readiness_v1"
VERSION = "v1"

_EXPLICIT_PART_RE = re.compile(
    r"\b(?:p/?n|pn|part(?:\s+number)?|component(?:\s+number)?|"
    r"part\s+identifier|item(?:\s+number)?)\b"
    r"\s*(?:is|=|:|#)?\s*([A-Za-z0-9][A-Za-z0-9-]{2,39})",
    re.I,
)
_BARE_LOOKUP_RE = re.compile(
    r"\b(?:find|locate|search(?:\s+for)?|look\s+up|lookup|where\s+is)\b"
    r"\s*(?:the\s+)?(?:exact\s+)?"
    r"(?:(?:part(?:\s+number)?|p/?n|pn|component(?:\s+number)?|identifier|item)\s+)?"
    r"([A-Za-z0-9][A-Za-z0-9-]{3,39})\b",
    re.I,
)
_WHERE_DOES_RE = re.compile(
    r"\bwhere\s+(?:does|is)\s+([A-Za-z0-9][A-Za-z0-9-]{3,39})\b",
    re.I,
)
_TOKEN_RE = re.compile(r"\b[A-Za-z0-9][A-Za-z0-9-]{3,39}\b")

_UNAMBIGUOUS_PARTIAL_PHRASES = (
    "partial", "fragment", "family", "series", "base number",
    "only know", "only remember", "cannot remember", "can't remember",
    "do not know", "don't know",
)

_PART_ENTITY_WORDS = r"p/?n|pn|part(?:\s+number)?|component(?:\s+number)?|item(?:\s+number)?|number"
_PARTIAL_VERBS = {
    "prefix": r"starts?|begins?|prefix(?:ed)?",
    "contains": r"contains?|includes?|has",
    "suffix": r"ends?|suffix(?:ed)?",
}

_GENERAL_SOURCE_NOUNS = (
    "manual", "document", "source material", "source", "information", "evidence types",
    "topics", "sections", "maintenance manual", "document structure",
)
_GENERAL_SOURCE_ACTIONS = (
    "overview", "high level", "summarize", "summary", "scope", "structure",
    "what kinds", "what information", "what topics", "what sections", "what evidence",
    "describe", "covered", "covers", "available", "explain", "tell me about",
)

_ALLOWED_PLANNER_KEYS = {
    "intent", "identifier_mode", "identifier", "entity_type", "requested_claims",
    "suggested_routes", "suggested_tunnels", "uncertainties", "authority_required",
    "answer_permission", "final_answer_allowed", "can_answer_directly",
    "can_prove_claims", "source_truth_mutation_allowed",
}


def normalize_identifier(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def clean_identifier(value: Any) -> str:
    return str(value or "").strip().strip(".,;:()[]{}<>\"'").upper()


def looks_identifier_shaped(value: Any) -> bool:
    """Conservatively recognize a complete identifier without repairing OCR."""
    text = clean_identifier(value)
    if not text or len(text) > 40:
        return False
    if not re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)*", text):
        return False
    normalized = normalize_identifier(text)
    if len(normalized) < 4 or not any(ch.isdigit() for ch in normalized):
        return False
    # Compact mixed alpha-numeric IDs are valid. Purely numeric IDs need a
    # multi-segment aviation part shape; context later distinguishes ATA codes.
    if not any(ch.isalpha() for ch in normalized) and text.count("-") < 2:
        return False
    if re.fullmatch(r"[0O1ILSZB]{4,}", normalized):
        return False
    return True


def _directly_bound(query: str, token: str, labels: str) -> bool:
    escaped = re.escape(token)
    pattern = (
        rf"\b(?:{labels})\b\s*"
        rf"(?:(?:number|no\.?|reference|section|code|id)\s*)?"
        rf"(?:is|=|:|#)?\s*{escaped}\b"
    )
    return bool(re.search(pattern, query, re.I))


def _ata_values(atoms: Optional[Any]) -> Set[str]:
    values: Set[str] = set()
    if atoms is None:
        return values
    prefix = normalize_identifier(getattr(atoms, "ata_prefix", ""))
    if prefix:
        values.add(prefix)
    for item in list(getattr(atoms, "ata_exact", []) or []):
        normalized = normalize_identifier(item)
        if normalized:
            values.add(normalized)
    return values


def classify_identifier_entity(query: str, token: str, atoms: Optional[Any] = None) -> str:
    """Classify a token without assuming every ID-shaped string is a part."""
    value = clean_identifier(token)
    normalized = normalize_identifier(value)
    if not looks_identifier_shaped(value):
        return "not_identifier"

    if normalized in _ata_values(atoms):
        return "ata_reference"

    if _directly_bound(query, value, r"ata|chapter|system"):
        return "ata_reference"
    if _directly_bound(query, value, r"manual\s+reference|manual\s+section|manual|document|revision|file"):
        return "document_reference"
    if _directly_bound(query, value, r"figure|fig\.?|callout"):
        return "figure_reference"
    if _directly_bound(query, value, r"page|sheet"):
        return "page_reference"
    if _directly_bound(query, value, r"table|row|column"):
        return "table_reference"

    # Explicit part language takes precedence over document-like substrings.
    explicit = _EXPLICIT_PART_RE.search(query)
    if explicit and normalize_identifier(explicit.group(1)) == normalized:
        return "part_number"

    if any(fragment in value for fragment in ("-IPL", "CMM", "AMM")):
        return "document_reference"

    # Strong part shapes: compact mixed alpha-numeric IDs, a hyphenated mixed ID,
    # or a three-segment numeric aviation part number.
    if any(ch.isalpha() for ch in normalized) or value.count("-") >= 2:
        return "part_number"
    return "unknown_identifier"


def infer_exact_identifier_candidate(
    query: str,
    atoms: Optional[Any] = None,
    *,
    legacy_identifier: Optional[str] = None,
) -> Optional[str]:
    """Return an exact part ID only when query wording and entity type support it."""
    text = str(query or "").strip()
    low = re.sub(r"\s+", " ", text.lower()).strip()
    if explicit_part_partial_wording(text):
        return None

    candidates = []
    explicit = _EXPLICIT_PART_RE.search(text)
    if explicit:
        candidates.append(explicit.group(1))
    for pattern in (_BARE_LOOKUP_RE, _WHERE_DOES_RE):
        match = pattern.search(text)
        if match:
            candidates.append(match.group(1))
    if legacy_identifier:
        candidates.append(legacy_identifier)

    # A query containing only one identifier token is also a valid exact lookup.
    stripped = clean_identifier(text)
    if stripped == text.upper().strip() and looks_identifier_shaped(stripped):
        candidates.append(stripped)

    # Last resort for a lookup command: inspect every shaped token, while the
    # entity classifier rejects ATA, page, figure, table, and document references.
    if not candidates and re.search(r"\b(?:find|locate|search|lookup)\b", low):
        candidates.extend(match.group(0) for match in _TOKEN_RE.finditer(text))

    seen = set()
    for raw in candidates:
        value = clean_identifier(raw)
        key = normalize_identifier(value)
        if not key or key in seen:
            continue
        seen.add(key)
        if classify_identifier_entity(text, value, atoms) == "part_number":
            return value
    return None



def part_fragment_is_explicit(query: str, value: Optional[str], mode: str) -> bool:
    """Return true only when a partial verb is bound to a part/number entity."""
    token = clean_identifier(value)
    verb = _PARTIAL_VERBS.get(str(mode))
    if not token or not verb:
        return False
    escaped = re.escape(token)
    forward = (
        rf"\b(?:{_PART_ENTITY_WORDS})\b.{{0,40}}?\b(?:{verb})\b"
        rf"\s*(?:with\s+)?(?:is|=|:)?\s*{escaped}\b"
    )
    reverse = (
        rf"\b(?:{verb})\b\s*(?:with\s+)?(?:is|=|:)?\s*{escaped}\b"
        rf".{{0,40}}?\b(?:{_PART_ENTITY_WORDS})\b"
    )
    return bool(re.search(forward, query, re.I) or re.search(reverse, query, re.I))


def explicit_part_partial_wording(query: str) -> bool:
    """Recognize partial-part intent only when wording is identifier-bound.

    This deliberately rejects answer-format phrases such as "Include the page"
    that merely occur near an exact part number in an OCR or procedure request.
    """
    low = re.sub(r"\s+", " ", str(query or "").lower()).strip()
    if any(phrase in low for phrase in _UNAMBIGUOUS_PARTIAL_PHRASES):
        return True

    for verb in _PARTIAL_VERBS.values():
        patterns = (
            rf"\b(?:{_PART_ENTITY_WORDS})\b.{{0,40}}?\b(?:{verb})\b"
            rf"\s*(?:with\s+)?(?:is|=|:)?\s*([a-z0-9][a-z0-9-]{{1,23}})\b",
            rf"\b(?:{verb})\b\s*(?:with\s+)?(?:is|=|:)?\s*"
            rf"([a-z0-9][a-z0-9-]{{1,23}})\b.{{0,40}}?"
            rf"\b(?:{_PART_ENTITY_WORDS})\b",
        )
        for pattern in patterns:
            for match in re.finditer(pattern, low, re.I):
                candidate = normalize_identifier(match.group(1))
                if len(candidate) >= 2 and any(ch.isdigit() for ch in candidate):
                    return True
    return False

def general_source_overview_requested(query: str) -> bool:
    """Recognize broad manual/source questions that should not ask for a part clue."""
    low = re.sub(r"\s+", " ", str(query or "").lower()).strip()
    return any(noun in low for noun in _GENERAL_SOURCE_NOUNS) and any(
        action in low for action in _GENERAL_SOURCE_ACTIONS
    )


def _candidate_value(row: Mapping[str, Any]) -> str:
    for key in ("candidate_value", "candidate_part_number", "part_number", "value", "matched_token"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _row_supports_identifier(row: Mapping[str, Any], requested: str) -> bool:
    target = normalize_identifier(requested)
    if not target:
        return False
    try:
        blob = json.dumps(dict(row), ensure_ascii=False, sort_keys=True)
    except Exception:
        blob = str(row)
    return target in normalize_identifier(blob)


_UNBACKED_PAGE_VALUES = {"", "unknown", "none", "n/a", "null"}


def _candidate_page_backed(row: Mapping[str, Any]) -> bool:
    """True when the candidate carries a concrete source page id (its own or a
    graph page). An echoed query token resolves to page_id 'unknown'/empty."""
    page = str(row.get("page_id") or "").strip().lower()
    if page and page not in _UNBACKED_PAGE_VALUES:
        return True
    pages = row.get("graph_pages")
    if isinstance(pages, list):
        for graph_page in pages:
            if isinstance(graph_page, Mapping):
                gpid = str(graph_page.get("page_id") or "").strip().lower()
                if gpid and gpid not in _UNBACKED_PAGE_VALUES:
                    return True
    return False


def _candidate_is_backed(row: Mapping[str, Any], direct_supports: bool) -> bool:
    """An exact-equal candidate is real only if corroborated by a retrieved
    record: direct-evidence support for the identifier, or a concrete source
    page on the candidate. A pure query echo has neither and must be dropped."""
    return bool(direct_supports) or _candidate_page_backed(row)


def enforce_final_identifier_filter(envelope: Any, intent: Mapping[str, Any]) -> Dict[str, Any]:
    """Reapply exact constraints after initial retrieval and every CRAG repair."""
    mode = str(intent.get("identifier_mode") or "none")
    requested = str(intent.get("normalized_identifier") or "")
    dropped_candidates = 0
    dropped_direct = 0

    candidates = list(getattr(envelope, "candidate_evidence", []) or [])
    echo_dropped = 0
    if mode == "exact" and requested:
        direct = list(getattr(envelope, "direct_evidence", []) or [])
        direct_supports = any(_row_supports_identifier(row, requested) for row in direct)
        matching = [
            row for row in candidates
            if normalize_identifier(_candidate_value(row)) == requested
        ]
        # A candidate equal to the requested identifier must be backed by a real
        # retrieved record, not a query echo. This closes the negative-control
        # fabrication where a self-contaminated guided-discovery artifact echoed
        # the query's own part id with page_id "unknown".
        kept = [row for row in matching if _candidate_is_backed(row, direct_supports)]
        echo_dropped = len(matching) - len(kept)
        dropped_candidates = len(candidates) - len(kept)
        envelope.candidate_evidence = kept

        kept_direct = [row for row in direct if _row_supports_identifier(row, requested)]
        dropped_direct = len(direct) - len(kept_direct)
        envelope.direct_evidence = kept_direct

    for row in list(getattr(envelope, "candidate_evidence", []) or []):
        if isinstance(row, MutableMapping):
            row["guidance_only"] = True
            row["source_truth"] = False
            row["final_answer_allowed"] = False

    safety = getattr(envelope, "safety_contract", None)
    if isinstance(safety, MutableMapping):
        safety.update({
            "answer_permission": False,
            "final_answer_allowed": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
        })

    coverage = getattr(envelope, "coverage", None)
    if isinstance(coverage, MutableMapping):
        coverage["phase4_3_1_final_filter_applied"] = mode != "none"
        coverage["phase4_3_1_final_candidate_drop_count"] = dropped_candidates
        coverage["phase4_3_1_final_direct_drop_count"] = dropped_direct
        coverage["phase4_3_1_query_echo_drop_count"] = echo_dropped

    return {
        "identifier_mode": mode,
        "requested_identifier": requested,
        "candidate_drop_count": dropped_candidates,
        "direct_drop_count": dropped_direct,
        "query_echo_drop_count": echo_dropped,
        "applied_after_repair": True,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }


def build_planner_seed(
    query: str,
    intent: Mapping[str, Any],
    route: str,
    *,
    engram_policy: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a grounded seed for a future LLM planner; no LLM is called here."""
    return {
        "planner_mode": "proposal_only",
        "query": str(query or ""),
        "deterministic_intent": dict(intent),
        "deterministic_route": str(route or ""),
        "engram_policy_available": bool(engram_policy),
        "llm_may_propose": [
            "entity_type", "identifier_mode", "requested_claims",
            "suggested_routes", "suggested_tunnels", "uncertainties",
        ],
        "llm_may_not": [
            "invent_identifiers", "execute_retrieval", "select_evidence",
            "grant_answer_permission", "mutate_source_truth", "authorize_safety_claims",
        ],
        "validation_required": True,
        "execution_enabled": False,
        "answer_permission": False,
        "final_answer_allowed": False,
        "source_truth_mutation_allowed": False,
    }


def validate_planner_proposal(
    proposal: Mapping[str, Any],
    *,
    query: str,
    allowed_routes: Iterable[str],
    allowed_tunnels: Iterable[str],
) -> Dict[str, Any]:
    """Fail closed unless an LLM proposal is query-grounded and allow-listed."""
    failures = []
    unknown = sorted(set(proposal) - _ALLOWED_PLANNER_KEYS)
    if unknown:
        failures.append("unknown_fields:" + ",".join(unknown))

    identifier = clean_identifier(proposal.get("identifier"))
    if identifier and normalize_identifier(identifier) not in normalize_identifier(query):
        failures.append("identifier_not_grounded_in_query")

    route_set = {str(value) for value in allowed_routes}
    for route in proposal.get("suggested_routes", []) or []:
        if str(route) not in route_set:
            failures.append(f"route_not_allowlisted:{route}")

    tunnel_set = {str(value) for value in allowed_tunnels}
    for tunnel in proposal.get("suggested_tunnels", []) or []:
        if str(tunnel) not in tunnel_set:
            failures.append(f"tunnel_not_allowlisted:{tunnel}")

    for key in (
        "answer_permission", "final_answer_allowed", "can_answer_directly",
        "can_prove_claims", "source_truth_mutation_allowed",
    ):
        if proposal.get(key) not in (None, False):
            failures.append(f"unsafe_true:{key}")

    return {
        "quality_status": "PASS" if not failures else "FAIL",
        "accepted": not failures,
        "failures": list(dict.fromkeys(failures)),
        "proposal_only": True,
        "execution_enabled": False,
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }


def expected_h30_routes(record: Mapping[str, Any]) -> Set[str]:
    """Map legacy benchmark expectations to suitable H30 cognitive routes."""
    tunnel = str(record.get("expected_tunnel") or "")
    category = str(record.get("category") or "")
    mapping = {
        "guided_candidate_discovery": {"guided_part_discovery"},
        "descriptive_part_discovery": {
            "nomenclature_function_search", "guided_part_discovery", "ata_system_discovery",
        },
        "exact_source_lookup": {
            "exact_identifier_lookup", "document_page_navigation", "ata_system_discovery",
        },
        "table_exact_or_structured_retrieval": {"exact_table_ipl_lookup"},
        "visual_figure_retrieval": {"visual_figure_callout_lookup"},
        "procedure_warning_text_retrieval": {
            "procedure_task_lookup", "warning_caution_note_lookup",
        },
        "safety_authority_search": {"authority_eligibility_verification"},
        "fast_clarification": {"clarification_no_evidence", "guided_part_discovery"},
        "general_source_truth_retrieval": {"semantic_discovery"},
    }
    if tunnel in mapping:
        return set(mapping[tunnel])
    if category == "general_source_truth":
        return {"semantic_discovery"}
    return set()


def phase4_3_1_health() -> Dict[str, Any]:
    return {
        "phase4_3_1_exact_identifier_context_v1": True,
        "bare_alphanumeric_exact_identifiers": True,
        "one_character_identifier_segments": True,
        "non_part_identifier_context_guard": True,
        "post_crag_final_identifier_filter": True,
        "semantic_benchmark_route_validation": True,
        "general_source_overview_intent": True,
        "validated_llm_planner_ready": True,
        "llm_planner_proposal_only": True,
        "llm_planner_execution_enabled": False,
        "planner_proposal_requires_query_grounding": True,
        "engram_can_guide_planner_behavior": True,
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
    }
