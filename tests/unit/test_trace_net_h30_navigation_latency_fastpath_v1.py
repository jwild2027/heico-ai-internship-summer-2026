from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

MODULE_PATH = Path("scripts/trace_net_h30_navigation_latency_fastpath_v1.py")


def load_module():
    spec = importlib.util.spec_from_file_location(
        "trace_net_h30_navigation_latency_fastpath_v1",
        MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Envelope:
    def __init__(self):
        self.direct_evidence = []
        self.visual_guidance = []
        self.candidate_evidence = []
        self.coverage = {}


class BaseRuntime:
    def __init__(self, *, resolve_on_call=1):
        self.resolve_on_call = resolve_on_call
        self.real_calls = []

    def add_unified(self, envelope, query, label):
        self.real_calls.append(("unified", label))
        if len(self.real_calls) == self.resolve_on_call:
            envelope.visual_guidance.append({
                "page_id": "t_p_120_1176_p000084",
                "part_numbers": ["120-41824-003"],
                "figure_refs": ["figure 2 sheet 1"],
            })
        return {"status": 200, "quality_status": "PASS"}

    def add_guided(self, envelope, query, atoms, label, *, allow_broad=False):
        self.real_calls.append(("guided", label))
        return {"status": 200, "quality_status": "PASS"}

    def process(self, payload):
        envelope = Envelope()
        atoms = SimpleNamespace(exact_part_numbers=["120-41824-003"])
        self.add_unified(envelope, "original", "original_navigation")
        self.add_unified(envelope, "strongest", "navigation_exact_source_fallback")
        self.add_unified(envelope, "diagram", "navigation_visual_fallback")
        self.add_guided(envelope, "candidate", atoms, "navigation_candidate_page_fallback")
        self.add_unified(envelope, "direct", "direct_source_resolution_v2")
        return {
            "route": payload.get("_route", "document_page_navigation"),
            "content": "ok",
            "evidence_envelope": {"coverage": {}},
        }

    def health(self):
        return {"quality_status": "PASS"}


def router_mapping(*, route="document_page_navigation", exact=True):
    def extract_latest_user(payload):
        return str(payload.get("query") or "")

    def extract_query_atoms(query):
        return SimpleNamespace(
            latest_query=query,
            exact_part_numbers=["120-41824-003"] if exact else [],
            navigation_requested=route == "document_page_navigation",
        )

    def plan_route(atoms):
        return SimpleNamespace(primary_route=route)

    return {
        "CognitiveRuntime": type("Runtime", (BaseRuntime,), {}),
        "extract_latest_user": extract_latest_user,
        "extract_query_atoms": extract_query_atoms,
        "plan_route": plan_route,
    }


def test_stops_after_first_entity_matching_page():
    mod = load_module()
    router = router_mapping()
    mod.install_navigation_latency_fastpath(router)
    runtime = router["CognitiveRuntime"](resolve_on_call=1)

    result = runtime.process({"query": "Which page contains part 120-41824-003?"})
    info = result["navigation_latency_fastpath"]

    assert runtime.real_calls == [("unified", "original_navigation")]
    assert info["active"] is True
    assert info["used_upstream_calls"] == 1
    assert info["skipped_upstream_calls"] == 4
    assert all(
        row["reason"] == "entity_matching_page_already_resolved"
        for row in info["skipped_tunnels"]
    )


def test_caps_navigation_at_two_calls_when_no_page_is_found():
    mod = load_module()
    router = router_mapping()
    mod.install_navigation_latency_fastpath(router)
    runtime = router["CognitiveRuntime"](resolve_on_call=99)

    result = runtime.process({"query": "Which page contains part 120-41824-003?"})
    info = result["navigation_latency_fastpath"]

    assert runtime.real_calls == [
        ("unified", "original_navigation"),
        ("unified", "navigation_exact_source_fallback"),
    ]
    assert info["used_upstream_calls"] == 2
    assert info["skipped_upstream_calls"] == 3
    assert all(
        row["reason"] == "navigation_upstream_budget_exhausted"
        for row in info["skipped_tunnels"]
    )


def test_second_call_can_resolve_page_and_stops_remaining_calls():
    mod = load_module()
    router = router_mapping()
    mod.install_navigation_latency_fastpath(router)
    runtime = router["CognitiveRuntime"](resolve_on_call=2)

    result = runtime.process({"query": "Which page contains part 120-41824-003?"})
    info = result["navigation_latency_fastpath"]

    assert len(runtime.real_calls) == 2
    assert info["used_upstream_calls"] == 2
    assert info["skipped_upstream_calls"] == 3
    assert all(
        row["reason"] == "entity_matching_page_already_resolved"
        for row in info["skipped_tunnels"]
    )


def test_non_navigation_route_is_unchanged():
    mod = load_module()
    router = router_mapping(route="exact_identifier_lookup")
    mod.install_navigation_latency_fastpath(router)
    runtime = router["CognitiveRuntime"](resolve_on_call=1)

    result = runtime.process({
        "query": "Find part 120-41824-003",
        "_route": "exact_identifier_lookup",
    })
    info = result["navigation_latency_fastpath"]

    assert len(runtime.real_calls) == 5
    assert info["active"] is False
    assert info["skipped_upstream_calls"] == 0


def test_navigation_without_full_part_number_is_unchanged():
    mod = load_module()
    router = router_mapping(exact=False)
    mod.install_navigation_latency_fastpath(router)
    runtime = router["CognitiveRuntime"](resolve_on_call=1)

    result = runtime.process({"query": "Which page discusses the component?"})
    info = result["navigation_latency_fastpath"]

    assert len(runtime.real_calls) == 5
    assert info["active"] is False


def test_health_exposes_fastpath_contract():
    mod = load_module()
    router = router_mapping()
    mod.install_navigation_latency_fastpath(router)
    health = router["CognitiveRuntime"]().health()

    assert health["navigation_latency_fastpath_v1"] is True
    assert health["navigation_max_upstream_calls"] == 2
    assert health["navigation_stops_after_entity_page"] is True
    assert health["navigation_other_routes_unchanged"] is True


def test_general_budget_caps_total_tunnels_on_any_route(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_RETRIEVAL_BUDGET_ENABLED", "1")
    monkeypatch.setenv("TRACE_NET_H30_RETRIEVAL_MAX_TUNNELS", "2")
    mod = load_module()
    router = router_mapping(route="nomenclature_function_search", exact=False)
    mod.install_navigation_latency_fastpath(router)
    runtime = router["CognitiveRuntime"](resolve_on_call=99)

    result = runtime.process({
        "query": "I need the item that retains the pin",
        "_route": "nomenclature_function_search",
    })
    info = result["retrieval_budget"]

    # The general budget applies to a non-navigation route and stops the serial
    # fan-out after the configured maximum number of executed tunnels.
    assert info["active"] is True
    assert info["nav_active"] is False
    assert info["budget_enabled"] is True
    assert info["used_upstream_calls"] == 2
    assert info["skipped_upstream_calls"] == 3
    assert info["retrieval_max_tunnels_exhausted"] is True
    assert len(runtime.real_calls) == 2
    assert all(
        row["reason"] == "retrieval_max_tunnels_exhausted"
        for row in info["skipped_tunnels"]
    )


def test_general_budget_deadline_is_a_hard_bound():
    mod = load_module()
    envelope = Envelope()
    state = {
        "nav_active": False,
        "budget_enabled": True,
        "used_calls": 0,
        "global_max_calls": 16,
        "deadline": mod.time.monotonic() - 1.0,
    }
    assert mod._skip_reason(state, envelope) == "retrieval_deadline_exhausted"


def test_general_budget_disabled_by_default_leaves_routes_unchanged(monkeypatch):
    monkeypatch.delenv("TRACE_NET_H30_RETRIEVAL_BUDGET_ENABLED", raising=False)
    mod = load_module()
    router = router_mapping(route="nomenclature_function_search", exact=False)
    mod.install_navigation_latency_fastpath(router)
    runtime = router["CognitiveRuntime"](resolve_on_call=99)

    result = runtime.process({
        "query": "I need the item that retains the pin",
        "_route": "nomenclature_function_search",
    })
    info = result["retrieval_budget"]

    assert info["active"] is False
    assert info["budget_enabled"] is False
    assert info["skipped_upstream_calls"] == 0
    assert len(runtime.real_calls) == 5


def test_health_exposes_retrieval_budget(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_RETRIEVAL_BUDGET_ENABLED", "1")
    monkeypatch.setenv("TRACE_NET_H30_RETRIEVAL_MAX_TUNNELS", "7")
    mod = load_module()
    router = router_mapping()
    mod.install_navigation_latency_fastpath(router)
    health = router["CognitiveRuntime"]().health()

    assert health["retrieval_budget_enabled"] is True
    assert health["retrieval_budget_all_routes"] is True
    assert health["retrieval_max_tunnels"] == 7
