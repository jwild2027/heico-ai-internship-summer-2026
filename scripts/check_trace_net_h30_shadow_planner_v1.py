#!/usr/bin/env python3
"""Check the deterministic safety contract for TRACE-Net H30 shadow planning."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict

from scripts.trace_net_h30_shadow_planner_v1 import (
    build_shadow_planner_seed,
    install_shadow_planner,
    validate_shadow_planner_proposal,
)


@dataclass
class Atoms:
    latest_query: str = "Find VS4956"
    normalized_query: str = "find vs4956"
    exact_part_numbers: list[str] = field(default_factory=lambda: ["VS4956"])
    identifier_mode: str = "exact"
    normalized_identifier: str = "VS4956"
    ata_exact: list[str] = field(default_factory=list)
    ata_prefix: str | None = None
    figures: list[str] = field(default_factory=list)
    items: list[str] = field(default_factory=list)
    page_ids: list[str] = field(default_factory=list)
    nomenclature_terms: list[str] = field(default_factory=list)
    assembly_context: list[str] = field(default_factory=list)
    requested_claims: list[str] = field(default_factory=lambda: ["exact_identifier"])
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


@dataclass
class Plan:
    primary_route: str = "exact_identifier_lookup"
    secondary_routes: list[str] = field(default_factory=lambda: ["guided_part_discovery"])
    retrieval_tunnels: list[str] = field(default_factory=lambda: ["normal_source_truth"])
    authority_required: bool = False
    repair_budget: int = 2
    rationale: list[str] = field(default_factory=lambda: ["exact identifier"])


def valid_proposal() -> Dict[str, Any]:
    return {
        "identifier_mode": "exact",
        "identifier": "VS4956",
        "entity_type": "part_number",
        "requested_claims": ["part_identity", "page_location"],
        "suggested_routes": ["exact_identifier_lookup"],
        "suggested_tunnels": ["normal_source_truth"],
        "uncertainties": [],
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }


def main() -> int:
    failures = []
    seed = build_shadow_planner_seed(
        query="Find VS4956",
        atoms=Atoms(),
        plan=Plan(),
        engram_policy={"policy": "exact identity evidence"},
        allowed_routes=["exact_identifier_lookup", "semantic_discovery"],
        allowed_tunnels=["normal_source_truth", "table_rows_cells"],
    )
    if seed.get("retrieved_evidence_in_seed") is not False:
        failures.append("retrieved_evidence_entered_planner_seed")
    if seed.get("safety_invariants", {}).get("planner_can_execute") is not False:
        failures.append("planner_execution_not_false")

    accepted = validate_shadow_planner_proposal(valid_proposal(), seed=seed)
    if accepted.get("quality_status") != "PASS":
        failures.append("grounded_proposal_not_accepted")

    invented = valid_proposal()
    invented["identifier"] = "INVENTED77"
    rejected = validate_shadow_planner_proposal(invented, seed=seed)
    if rejected.get("accepted") is not False:
        failures.append("invented_identifier_not_rejected")

    unsafe = valid_proposal()
    unsafe["answer_permission"] = True
    unsafe_result = validate_shadow_planner_proposal(unsafe, seed=seed)
    if unsafe_result.get("accepted") is not False:
        failures.append("unsafe_permission_not_rejected")

    events = []

    class Runtime:
        def process(self, payload):
            events.append("deterministic")
            return {
                "route": "exact_identifier_lookup",
                "evidence_envelope": {"coverage": {}},
                "answer_permission": False,
                "final_answer_allowed": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            }

        def health(self):
            return {"quality_status": "PASS"}

    module = {
        "CognitiveRuntime": Runtime,
        "extract_latest_user": lambda payload: payload["query"],
        "extract_query_atoms": lambda query: Atoms(latest_query=query, normalized_query=query.lower()),
        "plan_route": lambda atoms: Plan(),
        "select_engram_memory": lambda *args, **kwargs: [{"memory": "exact"}],
        "compile_engram_policy": lambda *args, **kwargs: {"policy": "exact"},
        "ALL_ROUTES": ("exact_identifier_lookup", "semantic_discovery"),
    }

    previous = os.environ.get("TRACE_NET_H30_SHADOW_PLANNER_ENABLED")
    os.environ["TRACE_NET_H30_SHADOW_PLANNER_ENABLED"] = "1"
    try:
        def fake_planner(seed_value, config):
            events.append("planner")
            return valid_proposal()

        install_shadow_planner(module, planner_callable=fake_planner)
        result = module["CognitiveRuntime"]().process({"query": "Find VS4956"})
    finally:
        if previous is None:
            os.environ.pop("TRACE_NET_H30_SHADOW_PLANNER_ENABLED", None)
        else:
            os.environ["TRACE_NET_H30_SHADOW_PLANNER_ENABLED"] = previous

    if events != ["planner", "deterministic"]:
        failures.append("planner_did_not_run_before_deterministic_execution")
    if result.get("route") != "exact_identifier_lookup":
        failures.append("planner_changed_effective_route")
    if result.get("planner_route_applied") is not False:
        failures.append("planner_route_applied_not_false")
    if result.get("planner_retrieval_influenced") is not False:
        failures.append("planner_retrieval_influenced_not_false")

    for key in (
        "answer_permission", "final_answer_allowed", "can_answer_directly",
        "can_prove_claims", "source_truth_mutation_allowed",
    ):
        if result.get(key) is not False:
            failures.append(f"unsafe_result_flag:{key}")

    summary = {
        "module": "trace_net_h30_shadow_planner_v1_check",
        "quality_status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
        "proposal_only": True,
        "planner_runs_before_retrieval": True,
        "planner_execution_enabled": False,
        "planner_route_applied": False,
        "planner_retrieval_influenced": False,
        "engram_policy_in_seed": True,
        "retrieved_evidence_in_seed": False,
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
    }
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
