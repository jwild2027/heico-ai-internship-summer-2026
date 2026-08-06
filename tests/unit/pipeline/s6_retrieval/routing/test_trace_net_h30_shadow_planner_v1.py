from __future__ import annotations

import os
from dataclasses import dataclass, field
from types import SimpleNamespace

from src.trace_net.router.trace_net_h30_shadow_planner_v1 import (
    build_shadow_planner_seed,
    compare_shadow_to_deterministic,
    extract_candidate_tokens,
    install_shadow_planner,
    parse_json_object,
    validate_shadow_planner_proposal,
)


@dataclass
class Atoms:
    latest_query: str
    normalized_query: str
    exact_part_numbers: list[str] = field(default_factory=list)
    ata_exact: list[str] = field(default_factory=list)
    ata_prefix: str | None = None
    identifier_mode: str = "none"
    normalized_identifier: str = ""
    figures: list[str] = field(default_factory=list)
    items: list[str] = field(default_factory=list)
    page_ids: list[str] = field(default_factory=list)
    nomenclature_terms: list[str] = field(default_factory=list)
    assembly_context: list[str] = field(default_factory=list)
    requested_claims: list[str] = field(default_factory=list)
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
    primary_route: str
    secondary_routes: list[str] = field(default_factory=list)
    retrieval_tunnels: list[str] = field(default_factory=list)
    authority_required: bool = False
    repair_budget: int = 2
    rationale: list[str] = field(default_factory=list)


def seed(query: str = "Find VS4956"):
    atoms = Atoms(
        latest_query=query,
        normalized_query=query.lower(),
        exact_part_numbers=["VS4956"],
        identifier_mode="exact",
        normalized_identifier="VS4956",
        requested_claims=["exact_identifier"],
    )
    plan = Plan(
        primary_route="exact_identifier_lookup",
        secondary_routes=["guided_part_discovery"],
        retrieval_tunnels=["normal_source_truth"],
        rationale=["deterministic exact identifier"],
    )
    return build_shadow_planner_seed(
        query=query,
        atoms=atoms,
        plan=plan,
        engram_policy={"preferred_behavior": "use exact identity proof"},
        allowed_routes=["exact_identifier_lookup", "graph_relationship_reasoning", "semantic_discovery"],
        allowed_tunnels=["normal_source_truth", "table_rows_cells", "graph_readonly"],
    )


def proposal(**updates):
    value = {
        "identifier_mode": "exact",
        "identifier": "VS4956",
        "entity_type": "part_number",
        "requested_claims": ["part_identity", "page_location"],
        "suggested_routes": ["exact_identifier_lookup"],
        "suggested_tunnels": ["normal_source_truth", "table_rows_cells"],
        "uncertainties": [],
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }
    value.update(updates)
    return value


def test_seed_contains_trusted_interpretation_but_no_retrieved_evidence():
    value = seed()
    assert value["planner_mode"] == "shadow_proposal_only"
    assert value["candidate_tokens"] == ["VS4956"]
    assert value["retrieved_evidence_in_seed"] is False
    blob = str(value).lower()
    assert "direct_evidence" not in blob
    assert "candidate_evidence" not in blob
    assert value["safety_invariants"]["planner_can_execute"] is False


def test_candidate_token_extraction_handles_mixed_identifier_shapes():
    assert extract_candidate_tokens("Find VS4956 and compare E075221 with 1002-F") == [
        "VS4956", "E075221", "1002-F"
    ]


def test_valid_grounded_proposal_is_accepted():
    result = validate_shadow_planner_proposal(proposal(), seed=seed())
    assert result["quality_status"] == "PASS"
    assert result["accepted"] is True
    assert result["execution_enabled"] is False


def test_invented_identifier_is_rejected():
    result = validate_shadow_planner_proposal(proposal(identifier="MADEUP77"), seed=seed())
    assert "identifier_not_grounded" in result["failures"]


def test_unallowlisted_route_is_rejected():
    result = validate_shadow_planner_proposal(
        proposal(suggested_routes=["postgres_write"]),
        seed=seed(),
    )
    assert "route_not_allowlisted:postgres_write" in result["failures"]


def test_unallowlisted_tunnel_is_rejected():
    result = validate_shadow_planner_proposal(
        proposal(suggested_tunnels=["qdrant_upsert"]),
        seed=seed(),
    )
    assert "tunnel_not_allowlisted:qdrant_upsert" in result["failures"]


def test_any_true_safety_flag_is_rejected():
    result = validate_shadow_planner_proposal(proposal(answer_permission=True), seed=seed())
    assert "unsafe_or_missing_false:answer_permission" in result["failures"]
    assert result["answer_permission"] is False


def test_missing_safety_flag_is_rejected():
    value = proposal()
    value.pop("can_prove_claims")
    result = validate_shadow_planner_proposal(value, seed=seed())
    assert any(item.startswith("missing_fields:") for item in result["failures"])
    assert "unsafe_or_missing_false:can_prove_claims" in result["failures"]


def test_exact_mode_conflicting_with_partial_wording_is_rejected():
    partial_seed = seed("I only remember part VS4956")
    result = validate_shadow_planner_proposal(proposal(), seed=partial_seed)
    assert "exact_mode_conflicts_with_partial_wording" in result["failures"]


def test_ata_value_cannot_become_part_without_explicit_part_binding():
    atoms = Atoms(
        latest_query="Find ATA 25-21-00",
        normalized_query="find ata 25-21-00",
        ata_exact=["25-21-00"],
        ata_prefix="25",
        identifier_mode="none",
        requested_claims=["ata_system"],
    )
    plan = Plan(primary_route="ata_system_discovery", retrieval_tunnels=["document_metadata"])
    ata_seed = build_shadow_planner_seed(
        query=atoms.latest_query,
        atoms=atoms,
        plan=plan,
        engram_policy={},
        allowed_routes=["ata_system_discovery", "exact_identifier_lookup"],
        allowed_tunnels=["document_metadata"],
    )
    value = proposal(
        identifier="25-21-00",
        entity_type="part_number",
        suggested_routes=["exact_identifier_lookup"],
        suggested_tunnels=["document_metadata"],
    )
    result = validate_shadow_planner_proposal(value, seed=ata_seed)
    assert "ata_value_misclassified_as_part" in result["failures"]




def test_descriptive_mode_may_omit_identifier():
    value = proposal(
        identifier_mode="descriptive",
        identifier=None,
        entity_type="component_description",
        requested_claims=["nomenclature"],
        suggested_routes=["semantic_discovery"],
        suggested_tunnels=["normal_source_truth"],
    )
    result = validate_shadow_planner_proposal(value, seed=seed("Find a locking ring near the seat"))
    assert result["quality_status"] == "PASS"


def test_relationship_word_contains_does_not_force_partial_mode():
    relationship_seed = seed("Which assembly contains part 120-41824-003?")
    value = proposal(
        identifier="120-41824-003",
        requested_claims=["part_identity", "assembly_relationship"],
        suggested_routes=["graph_relationship_reasoning"],
        suggested_tunnels=["graph_readonly"],
    )
    result = validate_shadow_planner_proposal(value, seed=relationship_seed)
    assert "exact_mode_conflicts_with_partial_wording" not in result["failures"]


def test_route_and_mode_disagreement_are_observable_but_not_applied():
    value = proposal(
        identifier_mode="descriptive",
        identifier="VS4956",
        suggested_routes=["graph_relationship_reasoning"],
        suggested_tunnels=["graph_readonly"],
    )
    validation = validate_shadow_planner_proposal(value, seed=seed())
    comparison = compare_shadow_to_deterministic(value, validation, seed())
    assert comparison["route_disagreement"] is True
    assert comparison["identifier_mode_disagreement"] is True
    assert comparison["planner_route_applied"] is False
    assert comparison["effective_route"] == "exact_identifier_lookup"


def test_json_parser_accepts_code_fence_and_surrounding_text():
    value = parse_json_object('```json\n{"identifier_mode":"none"}\n```')
    assert value["identifier_mode"] == "none"
    value2 = parse_json_object('proposal follows: {"identifier_mode":"exact"} end')
    assert value2["identifier_mode"] == "exact"


def _module_fixture(events, fake_proposal):
    class Runtime:
        def process(self, payload):
            events.append("deterministic_process")
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

    def extract_query_atoms(query):
        return Atoms(
            latest_query=query,
            normalized_query=query.lower(),
            exact_part_numbers=["VS4956"],
            identifier_mode="exact",
            normalized_identifier="VS4956",
            requested_claims=["exact_identifier"],
        )

    def plan_route(atoms):
        return Plan(
            primary_route="exact_identifier_lookup",
            secondary_routes=["guided_part_discovery"],
            retrieval_tunnels=["normal_source_truth"],
        )

    return {
        "CognitiveRuntime": Runtime,
        "extract_latest_user": lambda payload: payload["query"],
        "extract_query_atoms": extract_query_atoms,
        "plan_route": plan_route,
        "select_engram_memory": lambda *args, **kwargs: [{"memory": "exact identifiers"}],
        "compile_engram_policy": lambda *args, **kwargs: {"policy": "exact"},
        "ALL_ROUTES": ("exact_identifier_lookup", "graph_relationship_reasoning"),
    }


def test_shadow_planner_runs_before_deterministic_process_and_never_changes_route(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_SHADOW_PLANNER_ENABLED", "1")
    events = []

    def fake(seed_value, config):
        events.append("shadow_planner")
        return proposal()

    module = _module_fixture(events, proposal())
    install_shadow_planner(module, planner_callable=fake)
    runtime = module["CognitiveRuntime"]()
    result = runtime.process({"query": "Find VS4956"})
    assert events == ["shadow_planner", "deterministic_process"]
    assert result["route"] == "exact_identifier_lookup"
    assert result["planner_route_applied"] is False
    assert result["planner_retrieval_influenced"] is False
    assert result["shadow_planner"]["validation"]["accepted"] is True


def test_invalid_shadow_proposal_does_not_break_deterministic_answer(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_SHADOW_PLANNER_ENABLED", "1")
    events = []

    def fake(seed_value, config):
        return proposal(identifier="INVENTED77")

    module = _module_fixture(events, proposal())
    install_shadow_planner(module, planner_callable=fake)
    result = module["CognitiveRuntime"]().process({"query": "Find VS4956"})
    assert result["route"] == "exact_identifier_lookup"
    assert result["shadow_planner"]["validation"]["accepted"] is False
    assert result["answer_permission"] is False


def test_planner_exception_is_nonfatal(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_SHADOW_PLANNER_ENABLED", "1")
    events = []

    def fake(seed_value, config):
        raise RuntimeError("planner unavailable")

    module = _module_fixture(events, proposal())
    install_shadow_planner(module, planner_callable=fake)
    result = module["CognitiveRuntime"]().process({"query": "Find VS4956"})
    assert result["route"] == "exact_identifier_lookup"
    assert result["shadow_planner"]["call_status"] == "ERROR"
    assert result["planner_route_applied"] is False


def test_disabled_shadow_planner_skips_call(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_SHADOW_PLANNER_ENABLED", "0")
    events = []

    def fake(seed_value, config):
        events.append("should_not_run")
        return proposal()

    module = _module_fixture(events, proposal())
    install_shadow_planner(module, planner_callable=fake)
    result = module["CognitiveRuntime"]().process({"query": "Find VS4956"})
    assert "should_not_run" not in events
    assert result["shadow_planner"]["call_status"] == "SKIPPED"
    assert result["route"] == "exact_identifier_lookup"


def test_health_exposes_shadow_mode_and_keeps_permissions_false(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_SHADOW_PLANNER_ENABLED", "1")
    module = _module_fixture([], proposal())
    install_shadow_planner(module, planner_callable=lambda seed_value, config: proposal())
    health = module["CognitiveRuntime"]().health()
    assert health["phase4_4_shadow_planner_v1"] is True
    assert health["shadow_planner_enabled"] is True
    assert health["shadow_planner_execution_enabled"] is False
    assert health["shadow_planner_route_applied"] is False
    for key in (
        "answer_permission", "final_answer_allowed", "can_answer_directly",
        "can_prove_claims", "source_truth_mutation_allowed", "postgres_write_attempt",
        "qdrant_write_attempt", "opensearch_write_attempt",
    ):
        assert health[key] is False


def test_install_is_idempotent(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_SHADOW_PLANNER_ENABLED", "0")
    module = _module_fixture([], proposal())
    install_shadow_planner(module, planner_callable=lambda seed_value, config: proposal())
    first = module["CognitiveRuntime"].process
    install_shadow_planner(module, planner_callable=lambda seed_value, config: proposal())
    assert module["CognitiveRuntime"].process is first
