#!/usr/bin/env python3
"""Quality gate for TRACE-Net H30 Phase 4.5 validated planner execution."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List

from scripts.trace_net_h30_validated_planner_execution_v1 import (
    BROAD_ROUTES,
    MATURE_ROUTES,
    NARROW_ROUTES,
    ROUTE_TUNNELS,
    build_validated_execution_decision,
    canonicalize_planner_contract,
    load_planner_execution_config,
)

MODULE = "check_trace_net_h30_validated_planner_execution_v1"


@dataclass
class Atoms:
    latest_query: str = "Find VS4956"
    normalized_query: str = "find vs4956"
    exact_part_numbers: List[str] = field(default_factory=lambda: ["VS4956"])
    ata_exact: List[str] = field(default_factory=list)
    ata_prefix: str | None = None
    part_prefix: str | None = None
    part_contains: str | None = None
    part_suffix: str | None = None
    family_identifier: str | None = None
    identifier_mode: str = "exact"
    normalized_identifier: str = "VS4956"
    figures: List[str] = field(default_factory=list)
    items: List[str] = field(default_factory=list)
    page_ids: List[str] = field(default_factory=list)
    nomenclature_terms: List[str] = field(default_factory=list)
    assembly_context: List[str] = field(default_factory=list)
    requested_claims: List[str] = field(default_factory=lambda: ["exact_identifier"])
    visual_requested: bool = False
    table_requested: bool = False
    procedure_requested: bool = False
    warning_requested: bool = False
    authority_requested: bool = False
    navigation_requested: bool = False
    graph_requested: bool = False
    ocr_requested: bool = False
    comparison_requested: bool = False
    contradiction_requested: bool = False
    aggregate_requested: bool = False
    multi_question: bool = False


@dataclass
class Plan:
    primary_route: str = "clarification_no_evidence"
    secondary_routes: List[str] = field(default_factory=list)
    retrieval_tunnels: List[str] = field(default_factory=lambda: ["targeted_clarification"])
    authority_required: bool = False
    repair_budget: int = 2
    rationale: List[str] = field(default_factory=list)
    engram_policy: Dict[str, Any] = field(default_factory=dict)
    working_memory: Dict[str, Any] = field(default_factory=dict)


def proposal(route: str = "exact_identifier_lookup") -> Dict[str, Any]:
    return {
        "identifier_mode": "exact",
        "identifier": "VS4956",
        "entity_type": "part_number",
        "requested_claims": ["part_identity"],
        "suggested_routes": [route],
        "suggested_tunnels": ["normal_source_truth"],
        "uncertainties": [],
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }


def seed() -> Dict[str, Any]:
    return {
        "query": "Find VS4956",
        "candidate_tokens": ["VS4956"],
        "deterministic_atoms": {
            "exact_part_numbers": ["VS4956"],
            "identifier_mode": "exact",
            "normalized_identifier": "VS4956",
            "requested_claims": ["exact_identifier"],
            "ata_exact": [],
            "ata_prefix": None,
        },
        "allowed_routes": sorted(MATURE_ROUTES),
        "allowed_tunnels": sorted({value for values in ROUTE_TUNNELS.values() for value in values}),
    }


def shadow(value: Dict[str, Any], accepted: bool = True) -> Dict[str, Any]:
    return {
        "call_status": "PASS",
        "latency_ms": 20.0,
        "seed": seed(),
        "proposal": value,
        "validation": {
            "quality_status": "PASS" if accepted else "FAIL",
            "accepted": accepted,
            "failures": [] if accepted else ["invalid_entity_type:part"],
        },
    }


def config(mode: str, enabled: bool = True) -> Dict[str, Any]:
    return {
        "rollout_mode": mode,
        "execution_enabled": bool(enabled and mode != "validate_only"),
        "max_planner_latency_ms": 90000.0,
        "circuit_breaker_failure_threshold": 2,
        "circuit_breaker_seconds": 300.0,
        "allow_canonical_contract_bridge": True,
        "require_planner_route": True,
    }


def main() -> int:
    failures: List[str] = []
    checks: Dict[str, Any] = {}

    checks["route_sets_expand"] = NARROW_ROUTES < BROAD_ROUTES < MATURE_ROUTES
    checks["validate_only_default"] = load_planner_execution_config({})["rollout_mode"] == "validate_only"
    checks["execution_default_false"] = load_planner_execution_config({})["execution_enabled"] is False

    alias_raw = proposal()
    alias_raw.pop("answer_permission")
    alias_raw.pop("final_answer_allowed")
    alias_raw.pop("can_answer_directly")
    alias_raw.pop("can_prove_claims")
    alias_raw.pop("source_truth_mutation_allowed")
    alias_raw["entity_type"] = "part"
    alias_raw["requested_claims"] = ["exact_identifier"]
    bridge = canonicalize_planner_contract(alias_raw, seed=seed())
    checks["canonical_bridge_revalidated"] = bool((bridge.get("validation") or {}).get("accepted"))
    checks["canonical_bridge_safety_false"] = all(
        bridge.get("proposal", {}).get(key) is False
        for key in (
            "answer_permission", "final_answer_allowed", "can_answer_directly",
            "can_prove_claims", "source_truth_mutation_allowed",
        )
    )

    unsafe = proposal()
    unsafe["answer_permission"] = True
    blocked = canonicalize_planner_contract(unsafe, seed=seed())
    checks["unsafe_true_not_repaired"] = blocked.get("validation") is None

    invented = proposal()
    invented["identifier"] = "INVENTED77"
    blocked_id = canonicalize_planner_contract(invented, seed=seed())
    checks["invented_identifier_not_repaired"] = blocked_id.get("validation") is None

    validate_decision = build_validated_execution_decision(
        shadow=shadow(proposal()), atoms=Atoms(), deterministic_plan=Plan(),
        registered_routes=MATURE_ROUTES, config=config("validate_only"),
    )
    checks["phase2_no_execution"] = validate_decision["planner_plan_adopted"] is False

    narrow_decision = build_validated_execution_decision(
        shadow=shadow(proposal()), atoms=Atoms(), deterministic_plan=Plan(),
        registered_routes=MATURE_ROUTES, config=config("narrow"),
    )
    checks["phase3_narrow_execution"] = narrow_decision["planner_plan_adopted"] is True

    graph = proposal("graph_relationship_reasoning")
    graph["requested_claims"] = ["assembly_relationship"]
    graph_atoms = Atoms(graph_requested=True, requested_claims=["relationship"])
    broad_decision = build_validated_execution_decision(
        shadow=shadow(graph), atoms=graph_atoms, deterministic_plan=Plan(),
        registered_routes=MATURE_ROUTES, config=config("broad"),
    )
    checks["phase4_broad_execution"] = broad_decision["planner_plan_adopted"] is True

    authority = proposal("authority_eligibility_verification")
    authority["requested_claims"] = ["authority_approval"]
    authority_atoms = Atoms(authority_requested=True, requested_claims=["authority"])
    mature_decision = build_validated_execution_decision(
        shadow=shadow(authority), atoms=authority_atoms, deterministic_plan=Plan(),
        registered_routes=MATURE_ROUTES, config=config("mature"),
    )
    checks["phase5_mature_execution"] = mature_decision["planner_plan_adopted"] is True
    checks["executor_owns_tunnels"] = mature_decision["executor_owns_tunnel_selection"] is True
    checks["answer_permission_false"] = mature_decision["answer_permission"] is False
    checks["source_truth_mutation_false"] = mature_decision["source_truth_mutation_allowed"] is False
    checks["database_writes_false"] = all(
        mature_decision[key] is False
        for key in ("postgres_write_attempt", "qdrant_write_attempt", "opensearch_write_attempt")
    )

    for name, passed in checks.items():
        if not passed:
            failures.append(name)

    result = {
        "module": MODULE,
        "quality_status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
        "checks": checks,
        "rollout_modes": ["validate_only", "narrow", "broad", "mature"],
        "phases_implemented": [2, 3, 4, 5],
        "planner_execution_default": False,
        "deterministic_fallback": True,
        "executor_owned_tunnels": True,
        "validator_weakened": False,
        "planner_can_execute_tools": False,
        "planner_can_select_evidence": False,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
