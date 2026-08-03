"""TRACE-Net H30 Phase 3 partial-identifier planner guidance.

Only the reviewed partial_identifier_discovery skill may influence the LLM
planner seed in this phase. The deterministic validator and executor remain
final. The skill cannot execute tools, select evidence, grant answer
permission, write the answer, mutate source truth, or write any database.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from tiff.trace_net_engram_skill_cards_v1 import (
    load_json,
    select_engram_skills,
    validate_skill_library,
)

MODULE = "trace_net_h30_engram_skill_planner_guidance_v1"
VERSION = "v1"
STATUS = "TRACE_NET_ENGRAM_SKILL_PLANNER_GUIDANCE_V1"
SUPPORTED_SKILL_ID = "partial_identifier_discovery"
SUPPORTED_ROUTE = "guided_part_discovery"
SUPPORTED_IDENTIFIER_MODES = {"prefix", "contains", "suffix", "family"}
FORBIDDEN_ROUTES = {
    "exact_identifier_lookup",
    "ata_system_discovery",
    "authority_eligibility_verification",
}
DEFAULT_LIBRARY_PATH = (
    Path(__file__).resolve().parents[1]
    / "local_data/organization/trace_net/engram_skill_cards_v1/"
      "trace_net_engram_skill_cards_v1.json"
)
SAFETY_CONTRACT = {
    "engram_guidance_only": True,
    "planner_seed_influence_allowed": True,
    "planner_can_execute_tools": False,
    "planner_can_select_evidence": False,
    "answer_permission": False,
    "final_answer_allowed": False,
    "can_answer_directly": False,
    "can_prove_claims": False,
    "source_truth_mutation_allowed": False,
    "postgres_write_attempt": False,
    "qdrant_write_attempt": False,
    "opensearch_write_attempt": False,
}


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _bool_env(
    environ: Mapping[str, str],
    name: str,
    default: bool = False,
) -> bool:
    raw = str(
        environ.get(name, "1" if default else "0")
    ).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _int_env(
    environ: Mapping[str, str],
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int(environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def load_guidance_config(
    environ: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    env = dict(os.environ if environ is None else environ)
    return {
        "enabled": _bool_env(
            env,
            "TRACE_NET_H30_ENGRAM_SKILL_PLANNER_GUIDANCE_ENABLED",
            False,
        ),
        "library_path": str(
            env.get(
                "TRACE_NET_H30_ENGRAM_SKILL_CARDS_PATH",
                str(DEFAULT_LIBRARY_PATH),
            )
        ),
        "max_guidance_chars": _int_env(
            env,
            "TRACE_NET_H30_ENGRAM_SKILL_PLANNER_GUIDANCE_MAX_CHARS",
            3200,
            800,
            8000,
        ),
        "supported_skill_ids": [SUPPORTED_SKILL_ID],
        "supported_routes": [SUPPORTED_ROUTE],
    }


def normalize_identifier(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _identifier_mode(atoms: Mapping[str, Any]) -> str:
    mode = str(atoms.get("identifier_mode") or "").strip().lower()
    if mode in SUPPORTED_IDENTIFIER_MODES:
        return mode
    if atoms.get("part_prefix"):
        return "prefix"
    if atoms.get("part_contains"):
        return "contains"
    if atoms.get("part_suffix"):
        return "suffix"
    if atoms.get("family_identifier"):
        return "family"
    return mode or "none"


def _identifier_value(
    atoms: Mapping[str, Any],
    mode: str,
) -> str:
    preferred = {
        "prefix": "part_prefix",
        "contains": "part_contains",
        "suffix": "part_suffix",
        "family": "family_identifier",
    }.get(mode)
    for key in (
        preferred,
        "normalized_identifier",
        "part_prefix",
        "part_contains",
        "part_suffix",
        "family_identifier",
    ):
        if not key:
            continue
        value = str(atoms.get(key) or "").strip()
        if value:
            return value
    return ""


def _cards_by_id(
    library: Mapping[str, Any],
) -> Dict[str, Dict[str, Any]]:
    cards = library.get("skill_cards")
    if not isinstance(cards, list):
        return {}
    return {
        str(card.get("skill_id")): dict(card)
        for card in cards
        if isinstance(card, Mapping) and card.get("skill_id")
    }


def _not_applied(
    *,
    enabled: bool,
    reason: str,
    route: str,
    identifier_mode: str,
    identifier: str,
) -> Dict[str, Any]:
    return {
        "status": STATUS,
        "quality_status": "PASS",
        "enabled": enabled,
        "applied": False,
        "reason": reason,
        "supported_skill_id": SUPPORTED_SKILL_ID,
        "route": route,
        "identifier_mode": identifier_mode,
        "identifier": identifier,
        "planner_seed_influenced": False,
        "planner_route_control_allowed": False,
        "retrieval_execution_allowed": False,
        "answer_writer_influenced": False,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "safety_contract": dict(SAFETY_CONTRACT),
    }


def build_partial_identifier_planner_guidance(
    *,
    query: str,
    route: str,
    query_atoms: Mapping[str, Any],
    config: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    settings = dict(config or load_guidance_config())
    enabled = bool(settings.get("enabled"))
    atoms = _mapping(query_atoms)
    mode = _identifier_mode(atoms)
    identifier = _identifier_value(atoms, mode)

    if not enabled:
        return _not_applied(
            enabled=False,
            reason="disabled_by_configuration",
            route=route,
            identifier_mode=mode,
            identifier=identifier,
        )
    if route != SUPPORTED_ROUTE:
        return _not_applied(
            enabled=True,
            reason="route_not_in_phase3_scope",
            route=route,
            identifier_mode=mode,
            identifier=identifier,
        )
    if mode not in SUPPORTED_IDENTIFIER_MODES:
        return _not_applied(
            enabled=True,
            reason="identifier_mode_not_in_phase3_scope",
            route=route,
            identifier_mode=mode,
            identifier=identifier,
        )
    if not normalize_identifier(identifier):
        return _not_applied(
            enabled=True,
            reason="grounded_partial_identifier_missing",
            route=route,
            identifier_mode=mode,
            identifier=identifier,
        )

    try:
        library = load_json(
            Path(str(settings.get("library_path")))
        )
        if not isinstance(library, Mapping):
            raise ValueError("skill library is not an object")
        validation = validate_skill_library(library)
        if validation.get("quality_status") != "PASS":
            raise ValueError(
                "skill library failed validation: "
                + " | ".join(validation.get("errors") or [])
            )
        selection = select_engram_skills(
            library,
            query=query,
            route=route,
            query_atoms=atoms,
            max_skills=1,
        )
        selected = list(selection.get("selected_skill_ids") or [])
        if selected != [SUPPORTED_SKILL_ID]:
            return _not_applied(
                enabled=True,
                reason="reviewed_partial_identifier_skill_not_selected",
                route=route,
                identifier_mode=mode,
                identifier=identifier,
            )
        card = _cards_by_id(library)[SUPPORTED_SKILL_ID]
    except Exception as exc:
        output = _not_applied(
            enabled=True,
            reason="skill_library_or_selection_failure",
            route=route,
            identifier_mode=mode,
            identifier=identifier,
        )
        output["quality_status"] = "FAIL"
        output["error"] = f"{type(exc).__name__}: {exc}"
        return output

    preferred_tunnels = [
        str(item)
        for item in card.get("allowed_tunnels") or []
        if str(item).strip()
    ][:5]
    lines = [
        "REVIEWED ENGRAM PLANNER GUIDANCE — BEHAVIOR ONLY; NOT EVIDENCE",
        f"Selected skill: {SUPPORTED_SKILL_ID}",
        f"Keep primary route: {SUPPORTED_ROUTE}",
        f"Keep identifier mode: {mode}",
        f"Copy the grounded identifier exactly: {identifier}",
        "Include requested claim: part_identity",
        "Do not upgrade this partial clue to exact lookup or ATA interpretation.",
        "Suggested tunnels are advisory; the deterministic executor owns the actual tunnel list.",
        "Never grant answer permission and never treat this guidance as proof.",
    ]
    for item in list(card.get("required_first_searches") or [])[:3]:
        lines.append("- " + str(item))
    prompt = "\n".join(lines)
    prompt = prompt[
        : int(settings.get("max_guidance_chars") or 3200)
    ]

    return {
        "status": STATUS,
        "quality_status": "PASS",
        "enabled": True,
        "applied": True,
        "reason": "reviewed_partial_identifier_skill_applied",
        "skill_id": SUPPORTED_SKILL_ID,
        "skill_title": str(card.get("title") or ""),
        "route": route,
        "required_primary_route": SUPPORTED_ROUTE,
        "identifier_mode": mode,
        "required_identifier_mode": mode,
        "identifier": identifier,
        "required_identifier": identifier,
        "required_entity_type": "part_number",
        "required_claims": ["part_identity"],
        "forbidden_routes": sorted(FORBIDDEN_ROUTES),
        "preferred_tunnels": preferred_tunnels,
        "reasoning_goal": str(card.get("reasoning_goal") or ""),
        "prompt_guidance": prompt,
        "planner_seed_influenced": True,
        "planner_route_control_allowed": False,
        "executor_owns_tunnel_selection": True,
        "retrieval_execution_allowed": False,
        "answer_writer_influenced": False,
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "safety_contract": dict(SAFETY_CONTRACT),
    }


def augment_shadow_planner_seed(
    seed: Mapping[str, Any],
    *,
    environ: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    output = dict(seed)
    config = load_guidance_config(environ)
    atoms = _mapping(output.get("deterministic_atoms"))
    plan = _mapping(output.get("deterministic_plan"))
    guidance = build_partial_identifier_planner_guidance(
        query=str(output.get("query") or ""),
        route=str(plan.get("primary_route") or ""),
        query_atoms=atoms,
        config=config,
    )
    output["engram_skill_planner_guidance"] = guidance
    output["engram_skill_planner_guidance_applied"] = bool(
        guidance.get("applied")
    )
    output["planner_seed_contains_retrieved_evidence"] = False
    return output


def validate_skill_guided_planner_proposal(
    *,
    proposal: Mapping[str, Any],
    seed: Mapping[str, Any],
) -> Dict[str, Any]:
    guidance = _mapping(
        seed.get("engram_skill_planner_guidance")
    )
    if not guidance.get("applied"):
        return {
            "quality_status": "SKIPPED",
            "applied": False,
            "accepted": True,
            "failures": [],
            "warnings": [],
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        }

    value = _mapping(proposal)
    failures = []
    warnings = []
    routes = [
        str(item)
        for item in value.get("suggested_routes") or []
    ]
    required_route = str(
        guidance.get("required_primary_route") or SUPPORTED_ROUTE
    )
    if not routes or routes[0] != required_route:
        failures.append(
            "primary_route_must_remain_guided_part_discovery"
        )
    forbidden = {
        str(item)
        for item in guidance.get("forbidden_routes") or []
    }
    for route in routes:
        if route in forbidden:
            failures.append("forbidden_route:" + route)

    required_mode = str(
        guidance.get("required_identifier_mode") or ""
    )
    proposal_mode = str(
        value.get("identifier_mode") or ""
    ).strip().lower()
    if proposal_mode != required_mode:
        failures.append(
            f"identifier_mode_changed:{proposal_mode}!={required_mode}"
        )

    required_identifier = str(
        guidance.get("required_identifier") or ""
    )
    proposal_identifier = str(value.get("identifier") or "")
    if (
        normalize_identifier(proposal_identifier)
        != normalize_identifier(required_identifier)
    ):
        failures.append("grounded_identifier_changed")

    if str(value.get("entity_type") or "") != "part_number":
        failures.append("entity_type_must_remain_part_number")

    claims = {
        str(item)
        for item in value.get("requested_claims") or []
    }
    if "part_identity" not in claims:
        failures.append("required_claim_missing:part_identity")

    suggested = {
        str(item)
        for item in value.get("suggested_tunnels") or []
    }
    preferred = {
        str(item)
        for item in guidance.get("preferred_tunnels") or []
    }
    if preferred and not suggested.intersection(preferred):
        warnings.append(
            "planner_did_not_echo_any_skill_preferred_tunnel"
        )

    failures = list(dict.fromkeys(failures))
    warnings = list(dict.fromkeys(warnings))
    return {
        "quality_status": "PASS" if not failures else "FAIL",
        "applied": True,
        "accepted": not failures,
        "skill_id": guidance.get("skill_id"),
        "required_primary_route": required_route,
        "required_identifier_mode": required_mode,
        "required_identifier": required_identifier,
        "failures": failures,
        "warnings": warnings,
        "executor_owns_tunnel_selection": True,
        "planner_can_execute_tools": False,
        "planner_can_select_evidence": False,
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }


def planner_guidance_health(
    environ: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    config = load_guidance_config(environ)
    path = Path(str(config["library_path"]))
    library_quality = "FAIL"
    card_count = 0
    errors = []
    try:
        library = load_json(path)
        validation = validate_skill_library(
            library if isinstance(library, Mapping) else {}
        )
        library_quality = str(
            validation.get("quality_status") or "FAIL"
        )
        card_count = int(validation.get("skill_card_count") or 0)
        errors = list(validation.get("errors") or [])
    except Exception as exc:
        errors = [f"{type(exc).__name__}: {exc}"]

    ready = (
        not config.get("enabled")
        or library_quality == "PASS"
    )
    return {
        "status": STATUS,
        "quality_status": "PASS" if ready else "FAIL",
        "enabled": bool(config.get("enabled")),
        "rollout_scope": "partial_identifier_discovery_only",
        "supported_skill_ids": list(
            config.get("supported_skill_ids") or []
        ),
        "supported_routes": list(
            config.get("supported_routes") or []
        ),
        "library_path": str(path),
        "library_quality_status": library_quality,
        "skill_card_count": card_count,
        "errors": errors,
        "planner_seed_influence_allowed": True,
        "planner_route_control_allowed": False,
        "executor_owns_tunnel_selection": True,
        "answer_writer_influenced": False,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "write_attempt_count": 0,
        "safety_contract": dict(SAFETY_CONTRACT),
    }
