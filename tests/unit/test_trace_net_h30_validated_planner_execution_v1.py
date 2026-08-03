from __future__ import annotations

from dataclasses import dataclass, field

from src.trace_net.router.trace_net_h30_validated_planner_execution_v1 import (
    BROAD_ROUTES,
    MATURE_ROUTES,
    NARROW_ROUTES,
    ROUTE_TUNNELS,
    build_validated_execution_decision,
    canonicalize_planner_contract,
    install_validated_planner_execution,
    load_planner_execution_config,
    routes_for_mode,
)


@dataclass
class Atoms:
    latest_query: str = "Find VS4956"
    normalized_query: str = "find vs4956"
    exact_part_numbers: list[str] = field(default_factory=lambda: ["VS4956"])
    ata_exact: list[str] = field(default_factory=list)
    ata_prefix: str | None = None
    part_prefix: str | None = None
    part_contains: str | None = None
    part_suffix: str | None = None
    family_identifier: str | None = None
    identifier_mode: str = "exact"
    normalized_identifier: str = "VS4956"
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
    aggregate_requested: bool = False
    multi_question: bool = False


@dataclass
class Plan:
    primary_route: str = "exact_identifier_lookup"
    secondary_routes: list[str] = field(default_factory=list)
    retrieval_tunnels: list[str] = field(default_factory=lambda: ["normal_source_truth"])
    authority_required: bool = False
    repair_budget: int = 2
    rationale: list[str] = field(default_factory=list)
    engram_policy: dict = field(default_factory=dict)
    working_memory: dict = field(default_factory=dict)


def valid_proposal(route: str = "exact_identifier_lookup") -> dict:
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


def seed(query: str = "Find VS4956") -> dict:
    return {
        "query": query,
        "candidate_tokens": ["VS4956"],
        "deterministic_atoms": {
            "exact_part_numbers": ["VS4956"],
            "identifier_mode": "exact",
            "normalized_identifier": "VS4956",
            "requested_claims": ["exact_identifier"],
            "ata_exact": [],
            "ata_prefix": None,
        },
        "allowed_routes": sorted(MATURE_ROUTES | {"safe_general_chat"}),
        "allowed_tunnels": sorted({value for values in ROUTE_TUNNELS.values() for value in values}),
    }


def shadow(proposal: dict | None = None, accepted: bool = True, latency: float = 10.0) -> dict:
    value = valid_proposal() if proposal is None else proposal
    return {
        "call_status": "PASS",
        "latency_ms": latency,
        "seed": seed(),
        "proposal": value,
        "validation": {
            "quality_status": "PASS" if accepted else "FAIL",
            "accepted": accepted,
            "failures": [] if accepted else ["invalid_entity_type:part"],
        },
        "comparison": {},
    }


def config(mode: str, enabled: bool = True, bridge: bool = True) -> dict:
    return {
        "rollout_mode": mode,
        "execution_enabled": enabled and mode != "validate_only",
        "max_planner_latency_ms": 90000.0,
        "circuit_breaker_failure_threshold": 2,
        "circuit_breaker_seconds": 300.0,
        "allow_canonical_contract_bridge": bridge,
        "require_planner_route": True,
    }


def test_config_defaults_fail_closed():
    value = load_planner_execution_config({})
    assert value["rollout_mode"] == "validate_only"
    assert value["execution_enabled"] is False


def test_invalid_mode_falls_back_to_validate_only():
    value = load_planner_execution_config({
        "TRACE_NET_H30_PLANNER_ROLLOUT_MODE": "anything",
        "TRACE_NET_H30_PLANNER_EXECUTION_ENABLED": "1",
    })
    assert value["rollout_mode"] == "validate_only"
    assert value["execution_enabled"] is False


def test_phase_route_sets_expand_monotonically():
    registry = MATURE_ROUTES | {"safe_general_chat"}
    narrow = routes_for_mode("narrow", registry)
    broad = routes_for_mode("broad", registry)
    mature = routes_for_mode("mature", registry)
    assert narrow == NARROW_ROUTES
    assert narrow < broad
    assert broad < mature
    assert "safe_general_chat" not in mature


def test_canonical_bridge_maps_benign_aliases_and_false_safety_defaults():
    raw = {
        "identifier_mode": "exact",
        "identifier": "VS4956",
        "entity_type": "part",
        "requested_claims": ["exact_identifier"],
        "suggested_routes": ["exact_identifier_lookup"],
        "suggested_tunnels": ["normal_source_truth"],
        "uncertainties": [],
    }
    result = canonicalize_planner_contract(raw, seed=seed())
    assert result["validation"]["accepted"] is True
    assert result["proposal"]["entity_type"] == "part_number"
    assert result["proposal"]["requested_claims"] == ["part_identity"]
    assert result["proposal"]["answer_permission"] is False


def test_canonical_bridge_fills_only_query_grounded_identifier():
    raw = valid_proposal()
    raw["identifier"] = None
    result = canonicalize_planner_contract(raw, seed=seed())
    assert result["validation"]["accepted"] is True
    assert result["proposal"]["identifier"] == "VS4956"


def test_canonical_bridge_never_repairs_invented_identifier():
    raw = valid_proposal()
    raw["identifier"] = "INVENTED77"
    result = canonicalize_planner_contract(raw, seed=seed())
    assert result["validation"] is None
    assert "identifier_not_grounded" in result["audit"]["blocked_reasons"]


def test_canonical_bridge_never_repairs_true_safety_flag():
    raw = valid_proposal()
    raw["answer_permission"] = True
    result = canonicalize_planner_contract(raw, seed=seed())
    assert result["validation"] is None
    assert "unsafe_true:answer_permission" in result["audit"]["blocked_reasons"]


def test_canonical_bridge_rejects_write_or_admin_language():
    raw = valid_proposal()
    raw["intent"] = "write to postgres"
    result = canonicalize_planner_contract(raw, seed=seed())
    assert result["validation"] is None
    assert "unsafe_write_or_admin_instruction" in result["audit"]["blocked_reasons"]


def test_validate_only_never_adopts_plan():
    decision = build_validated_execution_decision(
        shadow=shadow(), atoms=Atoms(), deterministic_plan=Plan(),
        registered_routes=MATURE_ROUTES, config=config("validate_only", enabled=True),
    )
    assert decision["planner_plan_adopted"] is False
    assert decision["retrieval_influenced"] is False


def test_execution_switch_must_be_explicitly_enabled():
    decision = build_validated_execution_decision(
        shadow=shadow(), atoms=Atoms(), deterministic_plan=Plan(),
        registered_routes=MATURE_ROUTES, config=config("narrow", enabled=False),
    )
    assert decision["planner_plan_adopted"] is False


def test_narrow_mode_adopts_exact_route():
    decision = build_validated_execution_decision(
        shadow=shadow(), atoms=Atoms(), deterministic_plan=Plan(primary_route="clarification_no_evidence"),
        registered_routes=MATURE_ROUTES, config=config("narrow"),
    )
    assert decision["planner_plan_adopted"] is True
    assert decision["selected_route"] == "exact_identifier_lookup"
    assert decision["route_changed"] is True


def test_narrow_mode_rejects_graph_route():
    value = valid_proposal("graph_relationship_reasoning")
    value["requested_claims"] = ["assembly_relationship"]
    atoms = Atoms(graph_requested=True, requested_claims=["relationship"])
    decision = build_validated_execution_decision(
        shadow=shadow(value), atoms=atoms, deterministic_plan=Plan(),
        registered_routes=MATURE_ROUTES, config=config("narrow"),
    )
    assert decision["planner_plan_adopted"] is False
    assert "no_eligible_planner_route" in decision["failures"]


def test_broad_mode_adopts_graph_route_with_relationship_clue():
    value = valid_proposal("graph_relationship_reasoning")
    value["requested_claims"] = ["assembly_relationship"]
    atoms = Atoms(graph_requested=True, requested_claims=["relationship"])
    decision = build_validated_execution_decision(
        shadow=shadow(value), atoms=atoms, deterministic_plan=Plan(),
        registered_routes=MATURE_ROUTES, config=config("broad"),
    )
    assert decision["planner_plan_adopted"] is True
    assert decision["selected_route"] == "graph_relationship_reasoning"


def test_broad_mode_does_not_enable_authority_route():
    value = valid_proposal("authority_eligibility_verification")
    value["requested_claims"] = ["authority_approval"]
    atoms = Atoms(authority_requested=True, requested_claims=["authority"])
    decision = build_validated_execution_decision(
        shadow=shadow(value), atoms=atoms, deterministic_plan=Plan(),
        registered_routes=MATURE_ROUTES, config=config("broad"),
    )
    assert decision["planner_plan_adopted"] is False


def test_mature_mode_allows_authority_only_with_explicit_request():
    value = valid_proposal("authority_eligibility_verification")
    value["requested_claims"] = ["authority_approval"]
    atoms = Atoms(authority_requested=True, requested_claims=["authority"])
    decision = build_validated_execution_decision(
        shadow=shadow(value), atoms=atoms, deterministic_plan=Plan(),
        registered_routes=MATURE_ROUTES, config=config("mature"),
    )
    assert decision["planner_plan_adopted"] is True
    atoms.authority_requested = False
    value["requested_claims"] = ["part_identity"]
    decision2 = build_validated_execution_decision(
        shadow=shadow(value), atoms=atoms, deterministic_plan=Plan(),
        registered_routes=MATURE_ROUTES, config=config("mature"),
    )
    assert decision2["planner_plan_adopted"] is False


def test_semantic_route_cannot_replace_exact_lookup_without_overview_intent():
    value = valid_proposal("semantic_discovery")
    decision = build_validated_execution_decision(
        shadow=shadow(value), atoms=Atoms(), deterministic_plan=Plan(),
        registered_routes=MATURE_ROUTES, config=config("mature"),
    )
    assert decision["planner_plan_adopted"] is False


def test_executor_ignores_model_tunnel_order():
    value = valid_proposal()
    value["suggested_tunnels"] = ["qdrant_guidance", "normal_source_truth"]
    decision = build_validated_execution_decision(
        shadow=shadow(value), atoms=Atoms(), deterministic_plan=Plan(),
        registered_routes=MATURE_ROUTES, config=config("mature"),
    )
    assert decision["planner_plan_adopted"] is True
    assert decision["executor_owns_tunnel_selection"] is True
    assert decision["effective_tunnels"] == list(ROUTE_TUNNELS["exact_identifier_lookup"])


def test_latency_budget_forces_deterministic_fallback():
    decision = build_validated_execution_decision(
        shadow=shadow(latency=100000.0), atoms=Atoms(), deterministic_plan=Plan(),
        registered_routes=MATURE_ROUTES, config=config("mature"),
    )
    assert decision["planner_plan_adopted"] is False
    assert "planner_latency_budget_exceeded" in decision["failures"]


def test_planner_transport_error_forces_fallback():
    record = shadow()
    record["call_status"] = "ERROR"
    decision = build_validated_execution_decision(
        shadow=record, atoms=Atoms(), deterministic_plan=Plan(),
        registered_routes=MATURE_ROUTES, config=config("mature"),
    )
    assert decision["deterministic_fallback_used"] is True
    assert decision["answer_permission"] is False


def _fake_module(events: list[str], planner_record: dict):
    holder: dict = {}

    class Runtime:
        def process(self, payload):
            events.append("deterministic_process")
            atoms = holder["module"]["extract_query_atoms"](payload["query"])
            plan = holder["module"]["plan_route"](atoms)
            return {
                "route": plan.primary_route,
                "route_plan": {"primary_route": plan.primary_route},
                "evidence_envelope": {"coverage": {}},
                "safety_contract": {},
                "answer_permission": False,
                "final_answer_allowed": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            }

        def health(self):
            return {"quality_status": "PASS"}

        def shadow_plan(self, query):
            events.append("planner_call")
            return dict(planner_record)

    def extract_atoms(query):
        return Atoms(latest_query=query, normalized_query=query.lower())

    def plan_route(atoms):
        return Plan(primary_route="clarification_no_evidence", retrieval_tunnels=["targeted_clarification"])

    module = {
        "CognitiveRuntime": Runtime,
        "RoutePlan": Plan,
        "extract_latest_user": lambda payload: payload["query"],
        "extract_query_atoms": extract_atoms,
        "plan_route": plan_route,
        "ALL_ROUTES": tuple(MATURE_ROUTES | {"safe_general_chat"}),
        "_TRACE_NET_H30_SHADOW_PLANNER_V1_INSTALLED": True,
    }
    holder["module"] = module
    return module


def test_installed_mature_mode_calls_planner_once_and_changes_route(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_PLANNER_ROLLOUT_MODE", "mature")
    monkeypatch.setenv("TRACE_NET_H30_PLANNER_EXECUTION_ENABLED", "1")
    events: list[str] = []
    module = _fake_module(events, shadow())
    install_validated_planner_execution(module)
    runtime = module["CognitiveRuntime"]()
    result = runtime.process({"query": "Find VS4956"})
    assert events == ["planner_call", "deterministic_process"]
    assert result["route"] == "exact_identifier_lookup"
    assert result["planner_plan_adopted"] is True
    assert result["planner_retrieval_influenced"] is True
    assert result["answer_permission"] is False


def test_installed_validate_only_preserves_deterministic_route(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_PLANNER_ROLLOUT_MODE", "validate_only")
    monkeypatch.setenv("TRACE_NET_H30_PLANNER_EXECUTION_ENABLED", "1")
    events: list[str] = []
    module = _fake_module(events, shadow())
    install_validated_planner_execution(module)
    result = module["CognitiveRuntime"]().process({"query": "Find VS4956"})
    assert result["route"] == "clarification_no_evidence"
    assert result["planner_plan_adopted"] is False


def test_planner_decision_endpoint_method_never_executes_retrieval(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_PLANNER_ROLLOUT_MODE", "mature")
    monkeypatch.setenv("TRACE_NET_H30_PLANNER_EXECUTION_ENABLED", "1")
    events: list[str] = []
    module = _fake_module(events, shadow())
    install_validated_planner_execution(module)
    result = module["CognitiveRuntime"]().planner_decision("Find VS4956")
    assert events == ["planner_call"]
    assert result["retrieval_executed"] is False
    assert result["planner_execution"]["planner_plan_adopted"] is True


def test_health_exposes_all_phases_and_keeps_safety_false(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_PLANNER_ROLLOUT_MODE", "broad")
    monkeypatch.setenv("TRACE_NET_H30_PLANNER_EXECUTION_ENABLED", "1")
    module = _fake_module([], shadow())
    install_validated_planner_execution(module)
    health = module["CognitiveRuntime"]().health()
    assert health["phase4_5_validated_planner_execution_v1"] is True
    assert health["planner_rollout_modes_implemented"] == ["validate_only", "narrow", "broad", "mature"]
    assert health["planner_rollout_mode"] == "broad"
    assert health["planner_execution_enabled"] is True
    assert health["planner_executor_owns_tunnel_selection"] is True
    assert health["answer_permission"] is False
    assert health["source_truth_mutation_allowed"] is False


def test_install_is_idempotent():
    module = _fake_module([], shadow())
    install_validated_planner_execution(module)
    first = module["CognitiveRuntime"].process
    install_validated_planner_execution(module)
    assert module["CognitiveRuntime"].process is first


def test_circuit_breaker_skips_repeated_failed_planner_calls(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_PLANNER_ROLLOUT_MODE", "mature")
    monkeypatch.setenv("TRACE_NET_H30_PLANNER_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("TRACE_NET_H30_PLANNER_BREAKER_FAILURE_THRESHOLD", "1")
    monkeypatch.setenv("TRACE_NET_H30_PLANNER_BREAKER_SECONDS", "300")
    events: list[str] = []
    failed = shadow()
    failed["call_status"] = "ERROR"
    failed["error"] = "TimeoutError: planner timed out"
    module = _fake_module(events, failed)
    install_validated_planner_execution(module)
    runtime = module["CognitiveRuntime"]()
    runtime.process({"query": "Find VS4956"})
    runtime.process({"query": "Find VS4956"})
    assert events.count("planner_call") == 1
    assert events.count("deterministic_process") == 2


def test_execution_exception_retries_once_with_deterministic_plan(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_PLANNER_ROLLOUT_MODE", "mature")
    monkeypatch.setenv("TRACE_NET_H30_PLANNER_EXECUTION_ENABLED", "1")
    events: list[str] = []
    module = _fake_module(events, shadow())
    runtime_cls = module["CognitiveRuntime"]
    original = runtime_cls.process

    def fail_planner_route_once(self, payload):
        atoms = module["extract_query_atoms"](payload["query"])
        plan = module["plan_route"](atoms)
        events.append("attempt:" + plan.primary_route)
        if plan.primary_route == "exact_identifier_lookup":
            raise RuntimeError("simulated route executor failure")
        return original(self, payload)

    runtime_cls.process = fail_planner_route_once
    install_validated_planner_execution(module)
    result = runtime_cls().process({"query": "Find VS4956"})
    assert result["route"] == "clarification_no_evidence"
    assert result["planner_execution"]["execution_fallback_used"] is True
    assert result["planner_plan_adopted"] is False
