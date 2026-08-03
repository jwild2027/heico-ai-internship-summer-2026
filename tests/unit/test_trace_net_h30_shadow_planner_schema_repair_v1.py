from __future__ import annotations

from dataclasses import dataclass, field

from scripts.trace_net_h30_shadow_planner_v1 import (
    PROPOSAL_SCHEMA_GUIDANCE,
    build_schema_repair_seed,
    build_shadow_planner_seed,
    install_shadow_planner,
    should_attempt_schema_repair,
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
    graph_requested: bool = True
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


def make_seed():
    query = "Can you find VS4956 and tell me what assembly it belongs to?"
    return build_shadow_planner_seed(
        query=query,
        atoms=Atoms(
            latest_query=query,
            normalized_query=query.lower(),
            exact_part_numbers=["VS4956"],
            identifier_mode="exact",
            normalized_identifier="VS4956",
            requested_claims=["relationship"],
        ),
        plan=Plan(
            primary_route="graph_relationship_reasoning",
            retrieval_tunnels=["typed_graph_guidance", "normal_source_resolution", "qdrant_guidance"],
        ),
        engram_policy={"route": "graph_relationship_reasoning"},
        allowed_routes=["graph_relationship_reasoning", "exact_identifier_lookup"],
        allowed_tunnels=["typed_graph_guidance", "normal_source_resolution", "qdrant_guidance"],
    )


def malformed_live_proposal():
    return {
        "entity_type": "part",
        "identifier_mode": "exact",
        "requested_claims": ["VS4956 belongs to which assembly"],
        "suggested_routes": ["graph_relationship_reasoning"],
        "suggested_tunnels": ["typed_graph_guidance", "normal_source_resolution", "qdrant_guidance"],
        "uncertainties": [],
    }


def corrected_proposal(identifier="VS4956"):
    return {
        "identifier_mode": "exact",
        "identifier": identifier,
        "entity_type": "part_number",
        "requested_claims": ["part_identity", "assembly_relationship"],
        "suggested_routes": ["graph_relationship_reasoning"],
        "suggested_tunnels": ["typed_graph_guidance", "normal_source_resolution", "qdrant_guidance"],
        "uncertainties": [],
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }


def test_prompt_contains_exact_contract_and_forbids_part_alias():
    assert '"identifier"' in PROPOSAL_SCHEMA_GUIDANCE
    assert "Use entity_type part_number, never the shorthand part" in PROPOSAL_SCHEMA_GUIDANCE
    assert '"answer_permission": false' in PROPOSAL_SCHEMA_GUIDANCE


def test_live_contract_failure_is_repairable():
    seed = make_seed()
    value = malformed_live_proposal()
    validation = validate_shadow_planner_proposal(value, seed=seed)
    assert validation["accepted"] is False
    assert should_attempt_schema_repair(value, validation) is True


def test_repair_seed_contains_failures_but_no_retrieved_evidence():
    seed = make_seed()
    value = malformed_live_proposal()
    validation = validate_shadow_planner_proposal(value, seed=seed)
    repair = build_schema_repair_seed(seed, value, validation)
    assert repair["planner_mode"] == "shadow_proposal_schema_repair"
    assert repair["validator_failures"]
    assert repair["retrieved_evidence_in_seed"] is False
    blob = str(repair).lower()
    assert "direct_evidence" not in blob
    assert "candidate_evidence" not in blob


def test_unsafe_true_is_not_repairable():
    value = malformed_live_proposal()
    value["answer_permission"] = True
    validation = validate_shadow_planner_proposal(value, seed=make_seed())
    assert should_attempt_schema_repair(value, validation) is False


def test_invented_identifier_is_not_repairable():
    value = corrected_proposal("INVENTED77")
    validation = validate_shadow_planner_proposal(value, seed=make_seed())
    assert "identifier_not_grounded" in validation["failures"]
    assert should_attempt_schema_repair(value, validation) is False


def module_fixture(events):
    class Runtime:
        def process(self, payload):
            events.append("deterministic_process")
            return {
                "route": "graph_relationship_reasoning",
                "evidence_envelope": {"coverage": {}},
                "answer_permission": False,
                "final_answer_allowed": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            }

        def health(self):
            return {"quality_status": "PASS"}

    return {
        "CognitiveRuntime": Runtime,
        "extract_latest_user": lambda payload: payload["query"],
        "extract_query_atoms": lambda value: Atoms(
            latest_query=value,
            normalized_query=value.lower(),
            exact_part_numbers=["VS4956"],
            identifier_mode="exact",
            normalized_identifier="VS4956",
            requested_claims=["relationship"],
        ),
        "plan_route": lambda atoms: Plan(
            primary_route="graph_relationship_reasoning",
            retrieval_tunnels=["typed_graph_guidance", "normal_source_resolution", "qdrant_guidance"],
        ),
        "select_engram_memory": lambda *args, **kwargs: [{"memory": "relationship reasoning"}],
        "compile_engram_policy": lambda *args, **kwargs: {"route": "graph_relationship_reasoning"},
        "ALL_ROUTES": ("graph_relationship_reasoning", "exact_identifier_lookup"),
    }


def test_one_bounded_repair_is_revalidated_and_accepted(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_SHADOW_PLANNER_ENABLED", "1")
    events = []

    def first(seed, config):
        events.append("initial_planner")
        return malformed_live_proposal()

    def repair(seed, config):
        events.append("schema_repair")
        assert seed["validator_failures"]
        return corrected_proposal()

    module = module_fixture(events)
    install_shadow_planner(module, planner_callable=first, planner_repair_callable=repair)
    result = module["CognitiveRuntime"]().process({
        "query": "Can you find VS4956 and tell me what assembly it belongs to?"
    })
    shadow = result["shadow_planner"]
    assert events == ["initial_planner", "schema_repair", "deterministic_process"]
    assert shadow["initial_validation"]["accepted"] is False
    assert shadow["validation"]["accepted"] is True
    assert shadow["schema_repair_attempted"] is True
    assert shadow["schema_repair_used"] is True
    assert result["route"] == "graph_relationship_reasoning"
    assert result["planner_route_applied"] is False


def test_failed_repair_stays_fail_closed(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_SHADOW_PLANNER_ENABLED", "1")
    module = module_fixture([])
    install_shadow_planner(
        module,
        planner_callable=lambda seed, config: malformed_live_proposal(),
        planner_repair_callable=lambda seed, config: corrected_proposal("INVENTED77"),
    )
    result = module["CognitiveRuntime"]().process({
        "query": "Can you find VS4956 and tell me what assembly it belongs to?"
    })
    shadow = result["shadow_planner"]
    assert shadow["schema_repair_attempted"] is True
    assert shadow["schema_repair_used"] is False
    assert shadow["validation"]["accepted"] is False
    assert "identifier_not_grounded" in shadow["validation"]["failures"]
    assert result["route"] == "graph_relationship_reasoning"
    assert result["answer_permission"] is False


def test_health_exposes_one_repair_and_no_override(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_SHADOW_PLANNER_ENABLED", "1")
    module = module_fixture([])
    install_shadow_planner(module, planner_callable=lambda seed, config: corrected_proposal())
    health = module["CognitiveRuntime"]().health()
    assert health["shadow_planner_bounded_schema_repair"] is True
    assert health["shadow_planner_max_schema_repairs"] == 1
    assert health["shadow_planner_schema_repair_can_override_grounding"] is False
