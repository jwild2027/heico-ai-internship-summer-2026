#!/usr/bin/env python3
"""TRACE-Net H30 Phase 4.5 validated planner execution.

This layer implements rollout phases 2 through 5 behind explicit configuration:

- validate_only: validate and compare proposals; deterministic execution remains active.
- narrow: accepted plans may select a small set of low-risk read-only routes.
- broad: accepted plans may select broader read-only retrieval routes.
- mature: accepted plans may lead interpretation and route selection across the full
  registered read-only route family, while deterministic validators, bounded
  retrieval, Self-RAG, CRAG, answer boundaries, and write prohibitions remain final.

The LLM never receives tool handles and never executes retrieval directly. It cannot
select evidence, grant answer permission, prove claims, mutate source truth, or write
PostgreSQL, Qdrant, or OpenSearch. Every invalid, unavailable, over-latency, or
unsupported plan falls back to the deterministic router.
"""
from __future__ import annotations

import contextvars
import copy
import os
import threading
import time
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Set, Tuple

from src.trace_net.router.trace_net_h30_shadow_planner_v1 import (
    DEFAULT_READ_ONLY_TUNNELS,
    ENTITY_TYPES,
    IDENTIFIER_MODES,
    REQUESTED_CLAIMS,
    SAFETY_KEYS,
    normalize_identifier,
    validate_shadow_planner_proposal,
)
from src.trace_net.engram.trace_net_h30_engram_skill_planner_guidance_v1 import (
    planner_guidance_health,
    validate_skill_guided_planner_proposal,
)

MODULE = "trace_net_h30_validated_planner_execution_v1"
PATCH_ID = "trace_net_h30_phase4_5_validated_planner_autonomy_v1"
VERSION = "v1"
DECISION_VERSION = "trace_net_h30_validated_planner_decision_v1"

ROLLOUT_MODES = ("validate_only", "narrow", "broad", "mature")

# Phase 3: deliberately small and inexpensive route family.
NARROW_ROUTES: Set[str] = {
    "exact_identifier_lookup",
    "exact_table_ipl_lookup",
    "document_page_navigation",
    "semantic_discovery",
}

# Phase 4: broader read-only interpretation and retrieval. High-consequence authority,
# contradiction, high-degree aggregation, and multi-question orchestration remain for
# mature mode only.
BROAD_ROUTES: Set[str] = NARROW_ROUTES | {
    "guided_part_discovery",
    "ata_system_discovery",
    "nomenclature_function_search",
    "visual_figure_callout_lookup",
    "procedure_task_lookup",
    "warning_caution_note_lookup",
    "graph_relationship_reasoning",
    "cross_source_comparison",
    "ocr_scan_recovery",
}

MATURE_ROUTES: Set[str] = BROAD_ROUTES | {
    "authority_eligibility_verification",
    "contradiction_resolution",
    "high_degree_entity_aggregation",
    "multi_question_research",
    "clarification_no_evidence",
}

# Fixed executor-owned tunnel plans. The model may suggest tunnels for audit and
# comparison, but it never controls the actual tunnel list.
ROUTE_TUNNELS: Dict[str, Tuple[str, ...]] = {
    "safe_general_chat": ("restricted_conversation_template",),
    "exact_identifier_lookup": (
        "normal_source_truth", "guided_exact_candidate", "confirmed_visual",
        "phase4_3_exact_source_resolution", "qdrant_guidance",
    ),
    "guided_part_discovery": (
        "guided_candidate_discovery", "normal_source_resolution",
        "phase4_3_candidate_source_resolution", "qdrant_guidance",
    ),
    "ata_system_discovery": (
        "normal_source_truth", "document_metadata", "guided_broad_candidates",
        "graph_leiden_guidance", "v2_v3_summary_guidance", "qdrant_guidance",
    ),
    "nomenclature_function_search": (
        "normal_source_truth", "guided_nomenclature_candidates", "confirmed_visual",
        "graph_leiden_guidance", "v2_v3_summary_guidance", "qdrant_guidance",
    ),
    "exact_table_ipl_lookup": (
        "normal_source_truth", "table_rows_cells", "ocr_fallback", "figure_item_linkage",
    ),
    "visual_figure_callout_lookup": (
        "confirmed_visual", "llava_observations", "ocr_labels", "table_figure_linkage", "qdrant_guidance",
    ),
    "procedure_task_lookup": (
        "normal_source_truth", "procedure_sections", "warnings", "referenced_figures",
    ),
    "warning_caution_note_lookup": (
        "normal_source_truth", "warning_blocks", "task_context",
    ),
    "authority_eligibility_verification": (
        "normal_source_truth", "authority_fields", "cross_source_resolution",
    ),
    "document_page_navigation": (
        "normal_source_truth", "page_metadata", "graph_leiden_guidance", "v2_v3_summary_guidance",
    ),
    "graph_relationship_reasoning": (
        "typed_graph_guidance", "normal_source_resolution", "qdrant_guidance",
    ),
    "semantic_discovery": (
        "qdrant_guidance", "v2_v3_summary_guidance", "graph_leiden_guidance", "normal_source_resolution",
    ),
    "cross_source_comparison": (
        "normal_source_truth", "document_revision_metadata", "source_separation",
    ),
    "contradiction_resolution": (
        "normal_source_truth", "revision_effectivity_context", "ocr_visual_crosscheck",
    ),
    "ocr_scan_recovery": (
        "normal_ocr", "visual_crosscheck", "table_geometry", "neighbor_context",
    ),
    "high_degree_entity_aggregation": (
        "normal_source_truth", "typed_graph_aggregation", "faceting", "coverage_metadata",
    ),
    "multi_question_research": (
        "query_decomposition", "multiple_bounded_routes", "claim_level_evidence_gates",
    ),
    "clarification_no_evidence": ("targeted_clarification",),
}

_ENTITY_ALIASES = {
    "part": "part_number",
    "part_id": "part_number",
    "part_identifier": "part_number",
    "ata": "ata_reference",
    "ata_code": "ata_reference",
    "figure": "figure_reference",
    "table": "table_reference",
    "page": "page_reference",
    "manual": "document_reference",
    "document": "document_reference",
    "component": "component_description",
    "description": "component_description",
}

_CLAIM_ALIASES = {
    "exact_identifier": "part_identity",
    "part": "part_identity",
    "identity": "part_identity",
    "component_identity": "part_identity",
    "relationship": "assembly_relationship",
    "assembly": "assembly_relationship",
    "parent_assembly": "assembly_relationship",
    "visual_identity": "figure_callout",
    "figure": "figure_callout",
    "callout": "figure_callout",
    "table_value": "table_item",
    "table": "table_item",
    "procedure": "procedure_step",
    "warning": "warning_or_caution",
    "caution": "warning_or_caution",
    "authority": "authority_approval",
    "approval": "authority_approval",
    "navigation": "page_location",
    "page": "page_location",
    "overview": "document_overview",
    "ocr": "ocr_text",
    "compare": "comparison",
    "conflict": "contradiction",
}

_ATOM_CLAIM_MAP = {
    "exact_identifier": "part_identity",
    "ata_system": "part_identity",
    "visual_identity": "figure_callout",
    "table_value": "table_item",
    "procedure": "procedure_step",
    "warning": "warning_or_caution",
    "authority": "authority_approval",
    "comparison": "comparison",
    "relationship": "assembly_relationship",
}

_WRITE_OR_ADMIN_WORDS = (
    "write", "upsert", "insert", "update", "delete", "drop", "truncate",
    "admin", "shell", "command", "execute_tool", "postgres_write", "qdrant_upsert",
    "opensearch_write", "source_truth_write", "mutate",
)


def _mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    return {}


def _bool_env(env: Mapping[str, str], name: str, default: bool = False) -> bool:
    raw = str(env.get(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _float_env(env: Mapping[str, str], name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(env.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _int_env(env: Mapping[str, str], name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(env.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def load_planner_execution_config(environ: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    env = dict(os.environ if environ is None else environ)
    mode = str(env.get("TRACE_NET_H30_PLANNER_ROLLOUT_MODE", "validate_only")).strip().lower()
    if mode not in ROLLOUT_MODES:
        mode = "validate_only"
    enabled = _bool_env(env, "TRACE_NET_H30_PLANNER_EXECUTION_ENABLED", False)
    return {
        "rollout_mode": mode,
        "execution_enabled": bool(enabled and mode != "validate_only"),
        "max_planner_latency_ms": _float_env(
            env, "TRACE_NET_H30_PLANNER_MAX_LATENCY_MS", 90000.0, 1000.0, 1200000.0
        ),
        "circuit_breaker_failure_threshold": _int_env(
            env, "TRACE_NET_H30_PLANNER_BREAKER_FAILURE_THRESHOLD", 2, 1, 20
        ),
        "circuit_breaker_seconds": _float_env(
            env, "TRACE_NET_H30_PLANNER_BREAKER_SECONDS", 300.0, 5.0, 3600.0
        ),
        "allow_canonical_contract_bridge": _bool_env(
            env, "TRACE_NET_H30_PLANNER_CANONICAL_BRIDGE_ENABLED", True
        ),
        "require_planner_route": _bool_env(
            env, "TRACE_NET_H30_PLANNER_REQUIRE_ROUTE", True
        ),
    }


def routes_for_mode(mode: str, registered_routes: Iterable[str]) -> Set[str]:
    registry = {str(value) for value in registered_routes}
    if mode == "narrow":
        return registry & NARROW_ROUTES
    if mode == "broad":
        return registry & BROAD_ROUTES
    if mode == "mature":
        return registry & MATURE_ROUTES
    return set()


def _contains_unsafe_instruction(value: Any) -> bool:
    """Detect explicit write/admin proposals without flagging required safety-key names."""
    if not isinstance(value, Mapping):
        return False
    for key, item in value.items():
        key_text = str(key or "").lower()
        if key not in set(SAFETY_KEYS) and any(word in key_text for word in _WRITE_OR_ADMIN_WORDS):
            return True
        if key in {"intent", "suggested_routes", "suggested_tunnels"}:
            if isinstance(item, (list, tuple, set)):
                texts = [str(part or "").lower() for part in item]
            else:
                texts = [str(item or "").lower()]
            if any(word in text for text in texts for word in _WRITE_OR_ADMIN_WORDS):
                return True
    return False


def _candidate_identifier_from_seed(seed: Mapping[str, Any], mode: str) -> str:
    atoms = dict(seed.get("deterministic_atoms") or {})
    exact = [str(value) for value in atoms.get("exact_part_numbers") or [] if str(value).strip()]
    normalized = str(atoms.get("normalized_identifier") or "").strip()
    tokens = [str(value) for value in seed.get("candidate_tokens") or [] if str(value).strip()]
    if normalized:
        for value in exact + tokens:
            if normalize_identifier(value) == normalize_identifier(normalized):
                return value
        return normalized
    if len(exact) == 1:
        return exact[0]
    if mode in {"prefix", "contains", "suffix", "family"}:
        for key in ("part_prefix", "part_contains", "part_suffix", "family_identifier"):
            value = str(atoms.get(key) or "").strip()
            if value:
                return value
    if len(tokens) == 1:
        return tokens[0]
    return ""


def _infer_entity_type(seed: Mapping[str, Any], identifier_mode: str) -> str:
    atoms = dict(seed.get("deterministic_atoms") or {})
    if atoms.get("ata_exact") or atoms.get("ata_prefix"):
        return "ata_reference"
    if atoms.get("figures"):
        return "figure_reference"
    if atoms.get("items"):
        return "table_reference"
    if atoms.get("page_ids"):
        return "page_reference"
    if identifier_mode in {"exact", "prefix", "contains", "suffix", "family"}:
        return "part_number"
    if atoms.get("nomenclature_terms") or atoms.get("assembly_context"):
        return "component_description"
    return "unknown"


def _canonical_claims(raw_claims: Any, seed: Mapping[str, Any]) -> List[str]:
    output: List[str] = []
    seen: Set[str] = set()
    values = raw_claims if isinstance(raw_claims, list) else []
    for raw in values:
        value = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
        mapped = value if value in REQUESTED_CLAIMS else _CLAIM_ALIASES.get(value)
        if mapped and mapped not in seen:
            seen.add(mapped)
            output.append(mapped)
    atoms = dict(seed.get("deterministic_atoms") or {})
    for raw in atoms.get("requested_claims") or []:
        mapped = _ATOM_CLAIM_MAP.get(str(raw))
        if mapped and mapped not in seen:
            seen.add(mapped)
            output.append(mapped)
    if atoms.get("graph_requested") and "assembly_relationship" not in seen:
        output.append("assembly_relationship")
        seen.add("assembly_relationship")
    if atoms.get("ocr_requested") and "ocr_text" not in seen:
        output.append("ocr_text")
        seen.add("ocr_text")
    if atoms.get("navigation_requested") and "page_location" not in seen:
        output.append("page_location")
        seen.add("page_location")
    return output[:8]


def canonicalize_planner_contract(
    proposal: Mapping[str, Any],
    *,
    seed: Mapping[str, Any],
) -> Dict[str, Any]:
    """Safely normalize benign contract drift, then require the original validator.

    This bridge never repairs unsafe true flags, invented identifiers, or unapproved
    route/tunnel names. It only supplies false safety defaults, maps a small explicit
    alias table, and copies query-grounded deterministic identifiers when unambiguous.
    """
    raw = dict(proposal or {})
    audit: Dict[str, Any] = {
        "attempted": True,
        "used": False,
        "changes": [],
        "blocked_reasons": [],
        "dropped_fields": [],
        "dropped_advisory_tunnels": [],
    }

    for key in SAFETY_KEYS:
        if key in raw and raw.get(key) is not False:
            audit["blocked_reasons"].append(f"unsafe_true:{key}")
    if _contains_unsafe_instruction(raw):
        audit["blocked_reasons"].append("unsafe_write_or_admin_instruction")

    allowed_routes = {str(value) for value in seed.get("allowed_routes") or []}
    allowed_tunnels = {str(value) for value in seed.get("allowed_tunnels") or DEFAULT_READ_ONLY_TUNNELS}
    raw_routes = raw.get("suggested_routes") if isinstance(raw.get("suggested_routes"), list) else []
    raw_tunnels = raw.get("suggested_tunnels") if isinstance(raw.get("suggested_tunnels"), list) else []
    for route in raw_routes:
        if str(route) not in allowed_routes:
            audit["blocked_reasons"].append(f"route_not_allowlisted:{route}")
    # Planner tunnel suggestions are advisory only. TRACE-Net always selects the
    # executed tunnel plan from ROUTE_TUNNELS after route validation. Therefore an
    # invented, non-unsafe advisory tunnel is removed and audited rather than being
    # allowed to discard an otherwise grounded route proposal. Unsafe write/admin
    # tunnel language is still blocked above by _contains_unsafe_instruction().
    for tunnel in raw_tunnels:
        if str(tunnel) not in allowed_tunnels:
            audit["dropped_advisory_tunnels"].append(str(tunnel))
    if audit["dropped_advisory_tunnels"]:
        audit["changes"].append("invalid_advisory_tunnels_dropped")

    query = str(seed.get("query") or "")
    candidate_tokens = [str(value) for value in seed.get("candidate_tokens") or []]
    raw_identifier = str(raw.get("identifier") or "").strip()
    if raw_identifier:
        target = normalize_identifier(raw_identifier)
        grounded = target and (
            target in normalize_identifier(query)
            or any(target == normalize_identifier(value) for value in candidate_tokens)
        )
        if not grounded:
            audit["blocked_reasons"].append("identifier_not_grounded")

    if audit["blocked_reasons"]:
        return {"proposal": raw, "audit": audit, "validation": None}

    atoms = dict(seed.get("deterministic_atoms") or {})
    mode = str(raw.get("identifier_mode") or "").strip().lower()
    if mode not in IDENTIFIER_MODES:
        mode = str(atoms.get("identifier_mode") or "none")
        if mode not in IDENTIFIER_MODES:
            mode = "none"
        audit["changes"].append("identifier_mode_from_deterministic_atoms")

    identifier: Optional[str]
    if raw.get("identifier") is None or not str(raw.get("identifier") or "").strip():
        inferred = _candidate_identifier_from_seed(seed, mode)
        identifier = inferred or None
        if inferred:
            audit["changes"].append("identifier_from_query_grounded_atoms")
    else:
        identifier = str(raw.get("identifier"))

    entity_type = str(raw.get("entity_type") or "").strip().lower()
    if entity_type in _ENTITY_ALIASES:
        entity_type = _ENTITY_ALIASES[entity_type]
        audit["changes"].append("entity_type_alias_mapped")
    if entity_type not in ENTITY_TYPES:
        entity_type = _infer_entity_type(seed, mode)
        audit["changes"].append("entity_type_from_deterministic_atoms")

    claims = _canonical_claims(raw.get("requested_claims"), seed)
    if claims != list(raw.get("requested_claims") or []):
        audit["changes"].append("requested_claims_canonicalized")

    routes = [str(value) for value in raw_routes if str(value) in allowed_routes][:3]
    tunnels = [str(value) for value in raw_tunnels if str(value) in allowed_tunnels][:5]
    uncertainties = [
        str(value)[:300] for value in (raw.get("uncertainties") or [])
        if isinstance(value, str)
    ][:8]

    canonical = {
        "identifier_mode": mode,
        "identifier": identifier,
        "entity_type": entity_type,
        "requested_claims": claims,
        "suggested_routes": routes,
        "suggested_tunnels": tunnels,
        "uncertainties": uncertainties,
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }
    if "intent" in raw:
        canonical["intent"] = str(raw.get("intent") or "")[:500]
    if "authority_required" in raw:
        canonical["authority_required"] = bool(raw.get("authority_required"))

    allowed_keys = set(canonical)
    audit["dropped_fields"] = sorted(set(raw) - allowed_keys)
    validation = validate_shadow_planner_proposal(canonical, seed=seed)
    audit["used"] = bool(validation.get("accepted"))
    return {"proposal": canonical, "audit": audit, "validation": validation}


def _atoms_map(atoms: Any) -> Dict[str, Any]:
    return _mapping(atoms)


def _route_prerequisite_failures(
    route: str,
    atoms: Mapping[str, Any],
    proposal: Mapping[str, Any],
) -> List[str]:
    claims = {str(value) for value in proposal.get("requested_claims") or []}
    mode = str(proposal.get("identifier_mode") or atoms.get("identifier_mode") or "none")
    identifier = str(proposal.get("identifier") or "").strip()
    query = str(atoms.get("latest_query") or atoms.get("normalized_query") or "").lower()
    exact_ids = list(atoms.get("exact_part_numbers") or [])
    partial = any(atoms.get(key) for key in ("part_prefix", "part_contains", "part_suffix", "family_identifier"))
    failures: List[str] = []

    if route == "exact_identifier_lookup":
        if mode != "exact" or not identifier or not exact_ids:
            failures.append("exact_route_requires_grounded_exact_identifier")
    elif route == "guided_part_discovery":
        if mode not in {"prefix", "contains", "suffix", "family", "descriptive"} and not partial:
            failures.append("guided_route_requires_partial_or_descriptive_clue")
    elif route == "ata_system_discovery":
        if not (atoms.get("ata_prefix") or atoms.get("ata_exact")):
            failures.append("ata_route_requires_ata_clue")
    elif route == "nomenclature_function_search":
        if not (
            atoms.get("nomenclature_terms") or atoms.get("assembly_context")
            or "nomenclature" in claims or proposal.get("entity_type") == "component_description"
        ):
            failures.append("nomenclature_route_requires_component_clue")
    elif route == "exact_table_ipl_lookup":
        if not (atoms.get("table_requested") or atoms.get("items") or "table_item" in claims):
            failures.append("table_route_requires_table_or_item_clue")
    elif route == "visual_figure_callout_lookup":
        if not (atoms.get("visual_requested") or atoms.get("figures") or "figure_callout" in claims):
            failures.append("visual_route_requires_visual_or_figure_clue")
    elif route == "procedure_task_lookup":
        if not (atoms.get("procedure_requested") or "procedure_step" in claims):
            failures.append("procedure_route_requires_procedure_clue")
    elif route == "warning_caution_note_lookup":
        if not (atoms.get("warning_requested") or "warning_or_caution" in claims):
            failures.append("warning_route_requires_warning_clue")
    elif route == "authority_eligibility_verification":
        if not (atoms.get("authority_requested") or "authority_approval" in claims):
            failures.append("authority_route_requires_explicit_authority_request")
    elif route == "document_page_navigation":
        if not (atoms.get("navigation_requested") or atoms.get("page_ids") or "page_location" in claims):
            failures.append("navigation_route_requires_location_clue")
    elif route == "graph_relationship_reasoning":
        if not (atoms.get("graph_requested") or "assembly_relationship" in claims):
            failures.append("graph_route_requires_relationship_clue")
    elif route == "semantic_discovery":
        if mode == "exact" and exact_ids and not (
            "document_overview" in claims or any(word in query for word in ("overview", "high level", "topic", "about"))
        ):
            failures.append("semantic_route_cannot_replace_explicit_exact_lookup")
    elif route == "cross_source_comparison":
        if not (atoms.get("comparison_requested") or "comparison" in claims):
            failures.append("comparison_route_requires_comparison_clue")
    elif route == "contradiction_resolution":
        if not (atoms.get("contradiction_requested") or "contradiction" in claims):
            failures.append("contradiction_route_requires_conflict_clue")
    elif route == "ocr_scan_recovery":
        if not (atoms.get("ocr_requested") or "ocr_text" in claims):
            failures.append("ocr_route_requires_ocr_or_scan_clue")
    elif route == "high_degree_entity_aggregation":
        if not atoms.get("aggregate_requested"):
            failures.append("aggregation_route_requires_explicit_broad_coverage")
    elif route == "multi_question_research":
        if not (atoms.get("multi_question") or len(claims) >= 2):
            failures.append("multi_question_route_requires_multiple_claims")
    elif route == "clarification_no_evidence":
        strong = any((
            exact_ids, partial, atoms.get("ata_prefix"), atoms.get("ata_exact"),
            atoms.get("nomenclature_terms"), atoms.get("figures"), atoms.get("items"),
            atoms.get("page_ids"), atoms.get("visual_requested"), atoms.get("table_requested"),
            atoms.get("procedure_requested"), atoms.get("warning_requested"),
            atoms.get("authority_requested"), atoms.get("navigation_requested"),
            atoms.get("graph_requested"), atoms.get("ocr_requested"),
            atoms.get("comparison_requested"), atoms.get("contradiction_requested"),
        ))
        if strong:
            failures.append("clarification_disallowed_when_supported_clue_exists")
    elif route == "safe_general_chat":
        failures.append("planner_does_not_control_safe_general_chat")
    else:
        failures.append("unknown_route")
    return failures


def _phase_number(mode: str) -> int:
    return {"validate_only": 2, "narrow": 3, "broad": 4, "mature": 5}.get(mode, 2)


def build_validated_execution_decision(
    *,
    shadow: Mapping[str, Any],
    atoms: Any,
    deterministic_plan: Any,
    registered_routes: Iterable[str],
    config: Mapping[str, Any],
) -> Dict[str, Any]:
    atom_map = _atoms_map(atoms)
    deterministic = _mapping(deterministic_plan)
    seed = dict(shadow.get("seed") or {})
    raw_proposal = dict(shadow.get("proposal") or {})
    validation = dict(shadow.get("validation") or {})
    canonicalization = {
        "attempted": False, "used": False, "changes": [], "blocked_reasons": [],
        "dropped_fields": [], "dropped_advisory_tunnels": [],
    }
    proposal = raw_proposal

    if (
        not validation.get("accepted")
        and config.get("allow_canonical_contract_bridge")
        and shadow.get("call_status") == "PASS"
        and seed
    ):
        bridged = canonicalize_planner_contract(raw_proposal, seed=seed)
        canonicalization = dict(bridged.get("audit") or canonicalization)
        if bridged.get("validation") is not None:
            proposal = dict(bridged.get("proposal") or {})
            validation = dict(bridged.get("validation") or {})

    skill_guidance_validation = validate_skill_guided_planner_proposal(
        proposal=proposal,
        seed=seed,
    )

    mode = str(config.get("rollout_mode") or "validate_only")
    phase = _phase_number(mode)
    allowed = routes_for_mode(mode, registered_routes)
    failures: List[str] = []
    warnings: List[str] = []
    if (
        validation.get("accepted")
        and skill_guidance_validation.get("applied")
        and not skill_guidance_validation.get("accepted")
    ):
        failures.extend(
            "engram_skill_planner_guidance:" + str(item)
            for item in skill_guidance_validation.get("failures") or []
        )
    warnings.extend(
        "engram_skill_planner_guidance:" + str(item)
        for item in skill_guidance_validation.get("warnings") or []
    )

    if shadow.get("call_status") != "PASS":
        failures.append("planner_call_not_pass")
    if not validation.get("accepted"):
        failures.append("planner_proposal_not_accepted")
    latency = float(shadow.get("latency_ms") or 0.0)
    if latency > float(config.get("max_planner_latency_ms") or 90000.0):
        failures.append("planner_latency_budget_exceeded")
    if mode == "validate_only":
        warnings.append("phase2_validate_only")
    if not config.get("execution_enabled"):
        warnings.append("planner_execution_disabled")

    route_evaluations: List[Dict[str, Any]] = []
    eligible_routes: List[str] = []
    proposed_routes = [str(value) for value in proposal.get("suggested_routes") or []]
    for route in proposed_routes[:3]:
        route_failures: List[str] = []
        if route not in {str(value) for value in registered_routes}:
            route_failures.append("route_not_registered")
        if route not in allowed:
            route_failures.append(f"route_not_enabled_for_{mode}")
        route_failures.extend(_route_prerequisite_failures(route, atom_map, proposal))
        route_evaluations.append({
            "route": route,
            "eligible": not route_failures,
            "failures": list(dict.fromkeys(route_failures)),
        })
        if not route_failures:
            eligible_routes.append(route)

    if config.get("require_planner_route") and not proposed_routes:
        failures.append("planner_route_missing")
    if proposed_routes and not eligible_routes:
        failures.append("no_eligible_planner_route")

    deterministic_route = str(deterministic.get("primary_route") or "")
    selected_route = eligible_routes[0] if eligible_routes else deterministic_route
    secondary = [route for route in eligible_routes[1:] if route != selected_route][:2]
    adopted = bool(
        config.get("execution_enabled")
        and validation.get("accepted")
        and not failures
        and selected_route
        and mode in {"narrow", "broad", "mature"}
    )
    route_changed = bool(adopted and selected_route != deterministic_route)

    return {
        "module": MODULE,
        "decision_version": DECISION_VERSION,
        "quality_status": "PASS" if not failures else "FALLBACK",
        "rollout_mode": mode,
        "rollout_phase": phase,
        "execution_enabled": bool(config.get("execution_enabled")),
        "planner_call_status": shadow.get("call_status"),
        "planner_latency_ms": latency,
        "planner_validation": validation,
        "canonical_proposal": proposal,
        "canonical_contract_bridge": canonicalization,
        "deterministic_route": deterministic_route,
        "proposed_routes": proposed_routes,
        "route_evaluations": route_evaluations,
        "selected_route": selected_route,
        "secondary_routes": secondary,
        "effective_tunnels": list(ROUTE_TUNNELS.get(selected_route, ())),
        "planner_suggested_tunnels": list(proposal.get("suggested_tunnels") or [])[:5],
        "engram_skill_planner_guidance_applied": bool(
            skill_guidance_validation.get("applied")
        ),
        "engram_skill_planner_guidance_validation": skill_guidance_validation,
        "executor_owns_tunnel_selection": True,
        "planner_plan_adopted": adopted,
        "planner_route_applied": adopted,
        "route_changed": route_changed,
        "retrieval_influenced": adopted,
        "deterministic_fallback_used": not adopted,
        "failures": list(dict.fromkeys(failures)),
        "warnings": list(dict.fromkeys(warnings)),
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "planner_can_execute_tools": False,
        "planner_can_select_evidence": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
    }


def _build_route_plan(module: Mapping[str, Any], deterministic_plan: Any, decision: Mapping[str, Any]) -> Any:
    original = _mapping(deterministic_plan)
    route = str(decision.get("selected_route") or original.get("primary_route") or "")
    route_cls = module["RoutePlan"]
    rationale = list(original.get("rationale") or [])
    rationale.append(
        f"validated planner {decision.get('rollout_mode')} selected {route}; "
        "executor-owned route prerequisites and tunnel policy passed"
    )
    return route_cls(
        primary_route=route,
        secondary_routes=list(decision.get("secondary_routes") or []),
        retrieval_tunnels=list(ROUTE_TUNNELS.get(route, tuple(original.get("retrieval_tunnels") or []))),
        authority_required=route == "authority_eligibility_verification",
        repair_budget=min(2, max(0, int(original.get("repair_budget") or 2))),
        rationale=rationale,
        engram_policy=dict(original.get("engram_policy") or {}),
        working_memory=dict(original.get("working_memory") or {}),
    )


def _breaker_record(reason: str, open_until: float) -> Dict[str, Any]:
    return {
        "module": MODULE,
        "enabled": True,
        "planner_mode": "circuit_breaker_fallback",
        "call_status": "SKIPPED",
        "skip_reason": reason,
        "latency_ms": 0.0,
        "error": "",
        "proposal": {},
        "validation": {"quality_status": "SKIPPED", "accepted": False, "failures": [reason]},
        "comparison": {"planner_route_applied": False, "retrieval_influenced": False},
        "circuit_breaker_open_until": open_until,
        "execution_enabled": False,
        "planner_route_applied": False,
        "retrieval_influenced": False,
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }


def install_validated_planner_execution(module: MutableMapping[str, Any]) -> None:
    """Install phases 2-5 after the Phase 4.4 shadow planner wrapper."""
    marker = "_TRACE_NET_H30_VALIDATED_PLANNER_EXECUTION_V1_INSTALLED"
    if module.get(marker):
        return
    if not module.get("_TRACE_NET_H30_SHADOW_PLANNER_V1_INSTALLED"):
        raise RuntimeError("validated planner execution requires shadow planner installation first")

    runtime_cls = module["CognitiveRuntime"]
    current_process = runtime_cls.process
    current_health = runtime_cls.health
    original_shadow_plan = runtime_cls.shadow_plan
    original_plan_route = module["plan_route"]

    cached_shadow_var: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar(
        "trace_net_h30_cached_shadow_plan", default=None
    )
    route_override_var: contextvars.ContextVar[Optional[Any]] = contextvars.ContextVar(
        "trace_net_h30_validated_route_override", default=None
    )

    breaker_lock = threading.Lock()
    breaker_state: Dict[str, Any] = {
        "consecutive_failures": 0,
        "open_until": 0.0,
        "last_error": "",
    }

    def plan_route_with_override(atoms: Any) -> Any:
        override = route_override_var.get()
        if override is not None:
            return copy.deepcopy(override)
        return original_plan_route(atoms)

    def shadow_plan_with_cache(self: Any, query: str) -> Dict[str, Any]:
        cached = cached_shadow_var.get()
        if cached and cached.get("query") == query:
            return copy.deepcopy(dict(cached.get("record") or {}))

        config = load_planner_execution_config()
        now = time.time()
        with breaker_lock:
            open_until = float(breaker_state.get("open_until") or 0.0)
        if now < open_until:
            return _breaker_record("planner_circuit_breaker_open", open_until)

        record = dict(original_shadow_plan(self, query))
        failed = record.get("call_status") not in {"PASS", "SKIPPED"}
        if failed:
            with breaker_lock:
                breaker_state["consecutive_failures"] = int(breaker_state.get("consecutive_failures") or 0) + 1
                breaker_state["last_error"] = str(record.get("error") or record.get("call_status") or "planner_error")
                if breaker_state["consecutive_failures"] >= int(config["circuit_breaker_failure_threshold"]):
                    breaker_state["open_until"] = time.time() + float(config["circuit_breaker_seconds"])
        elif record.get("call_status") == "PASS":
            with breaker_lock:
                breaker_state["consecutive_failures"] = 0
                breaker_state["open_until"] = 0.0
                breaker_state["last_error"] = ""
        return record

    def planner_decision(self: Any, query: str) -> Dict[str, Any]:
        shadow = shadow_plan_with_cache(self, query)
        atoms = module["extract_query_atoms"](query)
        deterministic_plan = original_plan_route(atoms)
        config = load_planner_execution_config()
        decision = build_validated_execution_decision(
            shadow=shadow,
            atoms=atoms,
            deterministic_plan=deterministic_plan,
            registered_routes=module.get("ALL_ROUTES", ()),
            config=config,
        )
        return {
            "quality_status": "PASS",
            "module": MODULE,
            "query": query,
            "shadow_planner": shadow,
            "planner_execution": decision,
            "retrieval_executed": False,
            "answer_permission": False,
            "final_answer_allowed": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
        }

    def process_v2(self: Any, payload: Mapping[str, Any]) -> Dict[str, Any]:
        query = module["extract_latest_user"](payload)
        shadow = shadow_plan_with_cache(self, query)
        atoms = module["extract_query_atoms"](query)
        deterministic_plan = original_plan_route(atoms)
        config = load_planner_execution_config()
        decision = build_validated_execution_decision(
            shadow=shadow,
            atoms=atoms,
            deterministic_plan=deterministic_plan,
            registered_routes=module.get("ALL_ROUTES", ()),
            config=config,
        )
        override = _build_route_plan(module, deterministic_plan, decision) if decision["planner_plan_adopted"] else None

        cache_token = cached_shadow_var.set({"query": query, "record": shadow})
        override_token = route_override_var.set(override)
        execution_fallback_used = False
        execution_error = ""
        try:
            try:
                result = dict(current_process(self, payload))
            except Exception as exc:
                if override is None:
                    raise
                execution_fallback_used = True
                execution_error = f"{type(exc).__name__}: {exc}"
                route_override_var.reset(override_token)
                override_token = route_override_var.set(None)
                result = dict(current_process(self, payload))
                decision = dict(decision)
                decision.update({
                    "quality_status": "FALLBACK",
                    "planner_plan_adopted": False,
                    "planner_route_applied": False,
                    "retrieval_influenced": False,
                    "deterministic_fallback_used": True,
                    "execution_fallback_used": True,
                    "execution_error": execution_error,
                })
        finally:
            route_override_var.reset(override_token)
            cached_shadow_var.reset(cache_token)

        effective_route = str(result.get("route") or "")
        decision = dict(decision)
        decision["effective_route"] = effective_route
        decision["execution_fallback_used"] = execution_fallback_used
        decision["execution_error"] = execution_error
        if decision.get("planner_plan_adopted") and effective_route != decision.get("selected_route"):
            decision.update({
                "quality_status": "FALLBACK",
                "planner_plan_adopted": False,
                "planner_route_applied": False,
                "retrieval_influenced": False,
                "deterministic_fallback_used": True,
                "failures": list(decision.get("failures") or []) + ["effective_route_mismatch"],
            })

        shadow = dict(shadow)
        comparison = dict(shadow.get("comparison") or {})
        comparison.update({
            "effective_route": effective_route,
            "planner_route_applied": bool(decision.get("planner_route_applied")),
            "retrieval_influenced": bool(decision.get("retrieval_influenced")),
            "route_changed": bool(decision.get("route_changed")),
        })
        shadow["comparison"] = comparison
        shadow["execution_enabled"] = bool(config.get("execution_enabled"))
        shadow["planner_route_applied"] = bool(decision.get("planner_route_applied"))
        shadow["retrieval_influenced"] = bool(decision.get("retrieval_influenced"))

        result["shadow_planner"] = shadow
        result["planner_execution"] = decision
        result["planner_proposal"] = dict(decision.get("canonical_proposal") or shadow.get("proposal") or {})
        result["planner_validation"] = dict(decision.get("planner_validation") or shadow.get("validation") or {})
        result["planner_rollout_mode"] = config.get("rollout_mode")
        result["planner_plan_adopted"] = bool(decision.get("planner_plan_adopted"))
        result["planner_route_applied"] = bool(decision.get("planner_route_applied"))
        result["planner_retrieval_influenced"] = bool(decision.get("retrieval_influenced"))

        envelope = result.get("evidence_envelope")
        if isinstance(envelope, MutableMapping):
            coverage = envelope.get("coverage")
            if isinstance(coverage, MutableMapping):
                coverage["validated_planner_execution"] = {
                    "rollout_mode": config.get("rollout_mode"),
                    "planner_plan_adopted": bool(decision.get("planner_plan_adopted")),
                    "selected_route": decision.get("selected_route"),
                    "effective_route": effective_route,
                    "route_changed": bool(decision.get("route_changed")),
                    "deterministic_fallback_used": bool(decision.get("deterministic_fallback_used")),
                    "executor_owns_tunnel_selection": True,
                }

        for key in SAFETY_KEYS:
            result[key] = False
        result["source_truth_mutation_allowed"] = False
        safety = result.get("safety_contract")
        if isinstance(safety, MutableMapping):
            for key in SAFETY_KEYS:
                safety[key] = False
            safety["source_truth_mutation_allowed"] = False
            safety["planner_can_execute_tools"] = False
            safety["planner_can_select_evidence"] = False
        return result

    def health_v2(self: Any) -> Dict[str, Any]:
        result = dict(current_health(self))
        config = load_planner_execution_config()
        with breaker_lock:
            breaker = dict(breaker_state)
        result.update({
            "phase4_5_validated_planner_execution_v1": True,
            "engram_skill_planner_guidance": planner_guidance_health(),
            "planner_rollout_modes_implemented": list(ROLLOUT_MODES),
            "planner_rollout_mode": config.get("rollout_mode"),
            "planner_rollout_phase": _phase_number(str(config.get("rollout_mode"))),
            "planner_execution_enabled": bool(config.get("execution_enabled")),
            "planner_narrow_routes": sorted(NARROW_ROUTES),
            "planner_broad_routes": sorted(BROAD_ROUTES),
            "planner_mature_routes": sorted(MATURE_ROUTES),
            "planner_route_prerequisite_validation": True,
            "planner_canonical_contract_bridge": bool(config.get("allow_canonical_contract_bridge")),
            "planner_executor_owns_tunnel_selection": True,
            "planner_deterministic_fallback": True,
            "planner_self_rag_preserved": True,
            "planner_crag_preserved": True,
            "planner_answer_boundary_preserved": True,
            "planner_engram_policy_preserved": True,
            "planner_circuit_breaker": True,
            "planner_circuit_breaker_open": time.time() < float(breaker.get("open_until") or 0.0),
            "planner_circuit_breaker_failures": int(breaker.get("consecutive_failures") or 0),
            "planner_can_execute_tools": False,
            "planner_can_select_evidence": False,
            "read_only": True,
            "answer_permission": False,
            "final_answer_allowed": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
        })
        return result

    module["plan_route"] = plan_route_with_override
    runtime_cls.shadow_plan = shadow_plan_with_cache
    runtime_cls.planner_decision = planner_decision
    runtime_cls.process = process_v2
    runtime_cls.health = health_v2
    module[marker] = True
