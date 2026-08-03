from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/benchmark/run_trace_net_cognitive_route_smoke_v1.py"


def load_module():
    spec = importlib.util.spec_from_file_location("route_smoke", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def base_result(route: str) -> dict:
    return {
        "route": route,
        "content": "source-backed or bounded guidance",
        "source_truth_mutation_allowed": False,
    }


def test_deterministic_route_match_passes_without_planner():
    module = load_module()
    result = module.evaluate_live_result(
        "nomenclature_function_search",
        base_result("nomenclature_function_search"),
    )
    assert result["passed"] is True
    assert result["acceptance_basis"] == "deterministic_route_match"


def test_validated_adopted_route_change_passes():
    module = load_module()
    payload = base_result("semantic_discovery")
    payload.update({
        "planner_rollout_mode": "narrow",
        "planner_execution": {
            "quality_status": "PASS",
            "planner_plan_adopted": True,
            "planner_route_applied": True,
            "retrieval_influenced": True,
            "deterministic_fallback_used": False,
            "selected_route": "semantic_discovery",
            "failures": [],
        },
    })
    result = module.evaluate_live_result("nomenclature_function_search", payload)
    assert result["passed"] is True
    assert result["validated_planner_adoption"] is True
    assert result["acceptance_basis"] == "validated_planner_adoption"


def test_unexplained_route_change_fails():
    module = load_module()
    result = module.evaluate_live_result(
        "nomenclature_function_search",
        base_result("semantic_discovery"),
    )
    assert result["passed"] is False
    assert result["acceptance_basis"] == "route_contract_failed"


def test_selected_route_must_equal_effective_route():
    module = load_module()
    payload = base_result("semantic_discovery")
    payload.update({
        "planner_rollout_mode": "narrow",
        "planner_execution": {
            "quality_status": "PASS",
            "planner_plan_adopted": True,
            "planner_route_applied": True,
            "retrieval_influenced": True,
            "deterministic_fallback_used": False,
            "selected_route": "exact_identifier_lookup",
            "failures": [],
        },
    })
    assert module.evaluate_live_result("nomenclature_function_search", payload)["passed"] is False


def test_fallback_or_failed_decision_cannot_authorize_change():
    module = load_module()
    for overrides in (
        {"quality_status": "FALLBACK"},
        {"planner_plan_adopted": False},
        {"planner_route_applied": False},
        {"retrieval_influenced": False},
        {"deterministic_fallback_used": True},
        {"failures": ["planner_proposal_not_accepted"]},
    ):
        decision = {
            "quality_status": "PASS",
            "planner_plan_adopted": True,
            "planner_route_applied": True,
            "retrieval_influenced": True,
            "deterministic_fallback_used": False,
            "selected_route": "semantic_discovery",
            "failures": [],
        }
        decision.update(overrides)
        payload = base_result("semantic_discovery")
        payload.update({
            "planner_rollout_mode": "narrow",
            "planner_execution": decision,
        })
        assert module.evaluate_live_result("nomenclature_function_search", payload)["passed"] is False


def test_validate_only_cannot_authorize_route_change():
    module = load_module()
    payload = base_result("semantic_discovery")
    payload.update({
        "planner_rollout_mode": "validate_only",
        "planner_execution": {
            "quality_status": "PASS",
            "planner_plan_adopted": True,
            "planner_route_applied": True,
            "retrieval_influenced": True,
            "deterministic_fallback_used": False,
            "selected_route": "semantic_discovery",
            "failures": [],
        },
    })
    assert module.evaluate_live_result("nomenclature_function_search", payload)["passed"] is False


def test_safety_and_content_remain_required():
    module = load_module()
    missing_content = base_result("nomenclature_function_search")
    missing_content["content"] = ""
    assert module.evaluate_live_result("nomenclature_function_search", missing_content)["passed"] is False

    unsafe = base_result("nomenclature_function_search")
    unsafe["source_truth_mutation_allowed"] = True
    assert module.evaluate_live_result("nomenclature_function_search", unsafe)["passed"] is False
