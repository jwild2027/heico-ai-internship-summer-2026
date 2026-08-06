from __future__ import annotations

from scripts.benchmark.run_trace_net_engram_retrieval_audit_v1 import selected_skill
from scripts.operations.s6_retrieval.serve_trace_net_cognitive_router_v1 import (
    extract_query_atoms,
    plan_route,
)
from src.trace_net.validation.trace_net_h30_final_engram_rollout_v1 import (
    select_primary_skill,
)


def test_exact_identifier_plus_visual_is_one_visual_intent() -> None:
    query = (
        "Show the diagram or figure for part 120-41824-003 "
        "and cite the strongest visual source page."
    )
    assert plan_route(extract_query_atoms(query)).primary_route == (
        "visual_figure_callout_lookup"
    )


def test_exact_identifier_plus_authority_remains_multi_question() -> None:
    query = "Find part 120-41824-003 and determine whether it is approved"
    assert plan_route(extract_query_atoms(query)).primary_route == (
        "multi_question_research"
    )


def test_route_consistency_overrides_stale_exact_skill_for_partial() -> None:
    result = {
        "route": "guided_part_discovery",
        "query_atoms": {"part_contains": "41824"},
        "engram_skill_shadow": {
            "selected_skill_id": "exact_identifier_lookup",
        },
    }
    selected = select_primary_skill(result)
    assert selected["skill_id"] == "partial_identifier_discovery"
    assert selected["selection_basis"] == "deterministic_route_skill_override"


def test_route_consistency_overrides_stale_exact_skill_for_ata() -> None:
    result = {
        "route": "ata_system_discovery",
        "query_atoms": {"ata_prefix": "25"},
        "engram_skill_shadow": {
            "selected_skill_id": "exact_identifier_lookup",
        },
    }
    selected = select_primary_skill(result)
    assert selected["skill_id"] == "ata_plus_description_discovery"


def test_manufacturer_description_owns_nomenclature_route() -> None:
    result = {
        "route": "nomenclature_function_search",
        "query_atoms": {
            "manufacturer": "Recaro",
            "nomenclature_terms": ["latch"],
        },
        "engram_skill_shadow": {
            "selected_skill_id": "nomenclature_function_discovery",
        },
    }
    selected = select_primary_skill(result)
    assert selected["skill_id"] == "manufacturer_plus_description_discovery"


def test_audit_reads_explicit_final_selected_skill_not_supported_registry() -> None:
    trace = {
        "health_like_metadata": {
            "supported_skill_ids": [
                "exact_identifier_lookup",
                "partial_identifier_discovery",
            ]
        },
        "final_engram_rollout": {
            "selected_skill_id": "partial_identifier_discovery",
            "skill_selection_basis": "deterministic_route_skill_override",
        },
    }
    skill, basis, candidates = selected_skill(trace)
    assert skill == "partial_identifier_discovery"
    assert basis == "deterministic_route_skill_override"
    assert candidates == ["partial_identifier_discovery"]
