import importlib.util
import sys
import types
from pathlib import Path


ROUTER_PATH = Path(
    "scripts/operations/router/serve_trace_net_cognitive_router_v1.py"
)


def load_router():
    spec = importlib.util.spec_from_file_location(
        "trace_net_router_guided_first_test",
        ROUTER_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def runtime(module):
    return module.CognitiveRuntime(
        unified_base_url="http://127.0.0.1:1",
        guided_base_url="http://127.0.0.1:2",
        unified_api_key="test",
        api_key="test",
        timeout=45.0,
        max_request_bytes=100000,
        max_concurrency=1,
        queue_timeout=45.0,
    )


def plan(module, route):
    return module.RoutePlan(
        primary_route=route,
        secondary_routes=[],
        retrieval_tunnels=[],
        authority_required=False,
        repair_budget=0,
        rationale=[],
    )


def test_ata_uses_guided_first_and_short_circuits(monkeypatch):
    monkeypatch.setenv(
        "TRACE_NET_H30_DISCOVERY_TUNNEL_TIMEOUT_SECONDS",
        "7",
    )
    module = load_router()
    service = runtime(module)
    calls = []

    def guided(self, envelope, query, atoms, label, *, allow_broad=False):
        calls.append(("guided", label, self.retrieval_timeout))
        envelope.candidate_evidence.append(
            {
                "candidate_value": "120-20970-001",
                "ata": "25-21-00",
                "page_id": "t_p_demo_p1",
                "nomenclature": "STRUCTURE, ARMREST",
            }
        )
        envelope.retrieval_tunnels_used.append(label)
        return {"quality_status": "PASS"}

    def unified(self, envelope, query, label):
        raise AssertionError("ATA source-truth fallback should be short-circuited")

    service.add_guided = types.MethodType(guided, service)
    service.add_unified = types.MethodType(unified, service)

    atoms = module.QueryAtoms(
        latest_query="Search ATA 25",
        normalized_query="search ata 25",
        ata_prefix="25",
    )
    envelope = service.gather_initial(
        plan(module, "ata_system_discovery"),
        atoms,
    )

    assert [item[:2] for item in calls] == [
        ("guided", "guided_broad_candidates")
    ]
    assert calls[0][2] == 7.0
    assert len(envelope.candidate_evidence) == 1
    assert not hasattr(service, "retrieval_timeout")


def test_nomenclature_uses_guided_first_and_short_circuits(monkeypatch):
    monkeypatch.setenv(
        "TRACE_NET_H30_DISCOVERY_TUNNEL_TIMEOUT_SECONDS",
        "8",
    )
    module = load_router()
    service = runtime(module)
    calls = []

    def guided(self, envelope, query, atoms, label, *, allow_broad=False):
        calls.append(("guided", label, self.retrieval_timeout))
        envelope.candidate_evidence.append(
            {
                "candidate_value": "120-41824-003",
                "ata": "25-21-00",
                "page_id": "t_p_demo_p2",
                "nomenclature": "RING, LOCKING",
                "snippet": "locking ring near seat",
            }
        )
        envelope.retrieval_tunnels_used.append(label)
        return {"quality_status": "PASS"}

    def unified(self, envelope, query, label):
        raise AssertionError(
            "Nomenclature source-truth fallback should be short-circuited"
        )

    service.add_guided = types.MethodType(guided, service)
    service.add_unified = types.MethodType(unified, service)

    atoms = module.QueryAtoms(
        latest_query="Find the locking ring near the seat",
        normalized_query="find the locking ring near the seat",
        nomenclature_terms=["locking ring", "ring"],
        assembly_context=["seat"],
    )
    envelope = service.gather_initial(
        plan(module, "nomenclature_function_search"),
        atoms,
    )

    assert [item[:2] for item in calls] == [
        ("guided", "guided_nomenclature_candidates")
    ]
    assert calls[0][2] == 8.0
    assert len(envelope.candidate_evidence) == 1
    assert not hasattr(service, "retrieval_timeout")


def test_empty_guided_result_uses_one_bounded_source_fallback(monkeypatch):
    monkeypatch.setenv(
        "TRACE_NET_H30_DISCOVERY_TUNNEL_TIMEOUT_SECONDS",
        "6",
    )
    module = load_router()
    service = runtime(module)
    calls = []

    def guided(self, envelope, query, atoms, label, *, allow_broad=False):
        calls.append(("guided", label, self.retrieval_timeout))
        envelope.retrieval_tunnels_used.append(label)
        return {"quality_status": "PASS"}

    def unified(self, envelope, query, label):
        calls.append(("unified", label, self.retrieval_timeout))
        envelope.retrieval_tunnels_used.append(label)
        envelope.direct_evidence.append(
            {
                "page_id": "t_p_demo_p3",
                "field_name": "page_text",
                "normalized_value": "ATA 25",
            }
        )
        return {"quality_status": "PASS"}

    service.add_guided = types.MethodType(guided, service)
    service.add_unified = types.MethodType(unified, service)

    atoms = module.QueryAtoms(
        latest_query="Search ATA 25",
        normalized_query="search ata 25",
        ata_prefix="25",
    )
    envelope = service.gather_initial(
        plan(module, "ata_system_discovery"),
        atoms,
    )

    assert [item[:2] for item in calls] == [
        ("guided", "guided_broad_candidates"),
        ("unified", "normal_source_truth"),
    ]
    assert all(item[2] == 6.0 for item in calls)
    assert len(envelope.direct_evidence) == 1
    assert not hasattr(service, "retrieval_timeout")
