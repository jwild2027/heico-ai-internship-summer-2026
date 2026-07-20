#!/usr/bin/env python3
"""Quality check for TRACE-Net H30 Phase 4.3.1."""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List

from scripts.trace_net_h30_phase4_3_1_exact_identifier_v1 import (
    build_planner_seed,
    enforce_final_identifier_filter,
    expected_h30_routes,
    general_source_overview_requested,
    infer_exact_identifier_candidate,
    phase4_3_1_health,
    validate_planner_proposal,
)
from scripts.trace_net_h30_part_intent_source_resolution_v1 import derive_part_intent

MODULE = "check_trace_net_h30_phase4_3_1_exact_identifier_v1"


def main() -> int:
    failures: List[str] = []

    exact_cases = {
        "Find VS4956": "VS4956",
        "Locate E075221": "E075221",
        "Search for 1002-F": "1002-F",
        "Where does VS4956 appear?": "VS4956",
    }
    exact_results: Dict[str, Any] = {}
    for query, expected in exact_cases.items():
        inferred = infer_exact_identifier_candidate(query)
        intent = derive_part_intent(query)
        exact_results[query] = {"inferred": inferred, "intent": intent}
        if inferred != expected:
            failures.append(f"inference:{query}:{inferred}!={expected}")
        if intent.get("identifier_mode") != "exact":
            failures.append(f"intent_mode:{query}:{intent.get('identifier_mode')}!=exact")
        if intent.get("requested_identifier") != expected:
            failures.append(f"intent_identifier:{query}:{intent.get('requested_identifier')}!={expected}")

    atoms = SimpleNamespace(ata_prefix="25", ata_exact=["25-21-00"])
    if infer_exact_identifier_candidate("Find ATA 25-21-00", atoms, legacy_identifier="25-21-00") is not None:
        failures.append("ata_reclassified_as_part")
    if infer_exact_identifier_candidate("Find manual n25-IPL", legacy_identifier="n25-IPL") is not None:
        failures.append("document_reclassified_as_part")
    if not general_source_overview_requested("Describe the manual at a high level"):
        failures.append("general_source_overview_not_detected")

    envelope = SimpleNamespace(
        candidate_evidence=[
            {"candidate_value": "VS4956"},
            {"candidate_value": "120-50645-005"},
        ],
        direct_evidence=[
            {"field_name": "part_number", "value": "VS4956"},
            {"field_name": "part_number", "value": "120-50645-005"},
        ],
        coverage={},
        safety_contract={"answer_permission": True},
    )
    final_filter = enforce_final_identifier_filter(
        envelope,
        {"identifier_mode": "exact", "normalized_identifier": "VS4956"},
    )
    if [row.get("candidate_value") for row in envelope.candidate_evidence] != ["VS4956"]:
        failures.append("final_candidate_filter_failed")
    if [row.get("value") for row in envelope.direct_evidence] != ["VS4956"]:
        failures.append("final_direct_filter_failed")

    planner_seed = build_planner_seed(
        "Find VS4956",
        {"identifier_mode": "exact", "requested_identifier": "VS4956"},
        "exact_identifier_lookup",
        engram_policy={"selected_atoms": ["identifier_fidelity"]},
    )
    accepted = validate_planner_proposal(
        {
            "identifier_mode": "exact",
            "identifier": "VS4956",
            "suggested_routes": ["exact_identifier_lookup"],
            "suggested_tunnels": ["normal_source_truth"],
            "answer_permission": False,
        },
        query="Find VS4956",
        allowed_routes=["exact_identifier_lookup"],
        allowed_tunnels=["normal_source_truth"],
    )
    rejected = validate_planner_proposal(
        {
            "identifier": "INVENTED123",
            "suggested_tunnels": ["postgres_write"],
            "answer_permission": True,
        },
        query="Find VS4956",
        allowed_routes=[],
        allowed_tunnels=["normal_source_truth"],
    )
    if not accepted.get("accepted"):
        failures.append("grounded_planner_proposal_rejected")
    if rejected.get("accepted"):
        failures.append("unsafe_planner_proposal_accepted")
    if planner_seed.get("execution_enabled") is not False:
        failures.append("planner_execution_enabled_too_early")

    general_routes = expected_h30_routes({
        "category": "general_source_truth",
        "expected_tunnel": "general_source_truth_retrieval",
    })
    if general_routes != {"semantic_discovery"}:
        failures.append("general_source_route_mapping_failed")

    health = phase4_3_1_health()
    for key in (
        "answer_permission", "final_answer_allowed", "can_answer_directly",
        "can_prove_claims", "source_truth_mutation_allowed", "postgres_write_attempt",
        "qdrant_write_attempt", "opensearch_write_attempt",
    ):
        if health.get(key) is not False:
            failures.append(f"unsafe_health_flag:{key}")

    payload = {
        "module": MODULE,
        "patch_id": health.get("phase4_3_1_exact_identifier_context_v1") and "trace_net_h30_phase4_3_1_exact_identifier_and_planner_readiness_v1",
        "quality_status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
        "exact_identifier_cases": exact_results,
        "final_filter": final_filter,
        "general_source_routes": sorted(general_routes),
        "planner_seed": planner_seed,
        "accepted_planner_proposal": accepted,
        "rejected_planner_proposal": rejected,
        "health": health,
        "read_only": True,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
        "source_truth_mutation_allowed": False,
        "answer_permission": False,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
