from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = Path("scripts/trace_net_h30_graph_source_retrieval_v1.py")

NODES = {
    "nodes": [
        {
            "id": "part:120-41824-003",
            "type": "part",
            "label": "120-41824-003",
            "properties": {
                "part_number": "120-41824-003",
                "nomenclature": "RING, LOCKING",
            },
        },
        {
            "id": "page:p1",
            "type": "page",
            "label": "page 1",
            "properties": {
                "page_id": "t_p_demo_p1",
                "ata_code": "25-21-00",
                "source_url": "http://localhost/rescarta/demo/000001",
                "tiff_path": "local_data/demo/000001.tif",
            },
        },
        {
            "id": "nom:ring",
            "type": "nomenclature",
            "label": "RING, LOCKING",
            "properties": {"text": "RING, LOCKING"},
        },
        {
            "id": "ata:2521",
            "type": "ata_section",
            "label": "ATA 25-21-00",
            "properties": {"ata_code": "25-21-00"},
        },
    ]
}
EDGES = {
    "edges": [
        {"type": "APPEARS_ON", "source": "part:120-41824-003", "target": "page:p1"},
        {"type": "HAS_NOMENCLATURE", "source": "part:120-41824-003", "target": "nom:ring"},
        {"type": "BELONGS_TO_ATA", "source": "page:p1", "target": "ata:2521"},
        {"type": "CONTAINS_PAGE", "source": "ata:2521", "target": "page:p1"},
    ]
}


def load_module():
    spec = importlib.util.spec_from_file_location(
        "trace_net_graph_source_retrieval_test", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _fake_graph(monkeypatch, tmp_path):
    nodes = tmp_path / "graph_nodes.json"
    edges = tmp_path / "graph_edges.json"
    nodes.write_text(json.dumps(NODES), encoding="utf-8")
    edges.write_text(json.dumps(EDGES), encoding="utf-8")
    monkeypatch.setenv("TRACE_NET_H30_GRAPH_NODES_PATH", str(nodes))
    monkeypatch.setenv("TRACE_NET_H30_GRAPH_EDGES_PATH", str(edges))
    module = load_module()
    module._GRAPH_CACHE.clear()
    module._NOMEN_CACHE.clear()
    return module


def test_disabled_by_default(monkeypatch):
    # Verify the code's default independently of the launcher's ambient
    # environment, which enables the flag before running unit tests.
    monkeypatch.delenv("TRACE_NET_H30_GRAPH_RETRIEVAL_ENABLED", raising=False)
    module = load_module()
    assert module.graph_retrieval_enabled() is False


def test_enabled_by_environment(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_GRAPH_RETRIEVAL_ENABLED", "1")
    module = load_module()
    assert module.graph_retrieval_enabled() is True


def test_exact_part_traversal(monkeypatch, tmp_path):
    module = _fake_graph(monkeypatch, tmp_path)
    out = module.graph_retrieve(exact_parts=["120-41824-003"])
    assert out["available"] is True
    assert len(out["candidates"]) == 1
    cand = out["candidates"][0]
    assert cand["candidate_value"] == "120-41824-003"
    assert cand["page_id"] == "t_p_demo_p1"
    assert cand["source_resolved"] is True
    assert "RING, LOCKING" in cand["nomenclature"]
    # Graph output is guidance-only, never proof.
    assert cand["guidance_only"] is True
    assert cand["source_truth"] is False
    assert cand["final_answer_allowed"] is False


def test_fragment_traversal(monkeypatch, tmp_path):
    module = _fake_graph(monkeypatch, tmp_path)
    out = module.graph_retrieve(fragments=["41824"])
    assert [c["candidate_value"] for c in out["candidates"]] == ["120-41824-003"]


def test_ata_navigation_leads(monkeypatch, tmp_path):
    module = _fake_graph(monkeypatch, tmp_path)
    out = module.graph_retrieve(ata_codes=["25-21-00"])
    assert out["candidates"] == []
    assert len(out["navigation_leads"]) == 1
    assert out["navigation_leads"][0]["page_id"] == "t_p_demo_p1"


def test_page_pinning_is_exact_not_substring(monkeypatch, tmp_path):
    module = _fake_graph(monkeypatch, tmp_path)
    # A full canonical page id pins exactly that page's source trace.
    exact = module.graph_retrieve(page_ids=["t_p_demo_p1"])
    assert exact["stats"]["pinned_page_count"] == 1
    assert exact["navigation_leads"][0]["page_id"] == "t_p_demo_p1"
    # A substring of a page id must NOT match (the p000018 -> p000181 defect).
    sub = module.graph_retrieve(page_ids=["t_p_demo_p"])
    assert sub["stats"]["pinned_page_count"] == 0
    # A nonexistent page id resolves to nothing (no fabricated page).
    missing = module.graph_retrieve(page_ids=["t_p_demo_p999999"])
    assert missing["stats"]["pinned_page_count"] == 0


def test_nomenclature_noun_traversal(monkeypatch, tmp_path):
    module = _fake_graph(monkeypatch, tmp_path)
    out = module.graph_retrieve(nomenclature_terms=["ring"])
    assert [c["candidate_value"] for c in out["candidates"]] == ["120-41824-003"]
    assert out["candidates"][0]["graph_match_reason"] == "nomenclature_noun"


def test_missing_graph_is_safe(monkeypatch, tmp_path):
    monkeypatch.setenv("TRACE_NET_H30_GRAPH_NODES_PATH", str(tmp_path / "nope.json"))
    monkeypatch.setenv("TRACE_NET_H30_GRAPH_EDGES_PATH", str(tmp_path / "nope2.json"))
    module = load_module()
    module._GRAPH_CACHE.clear()
    out = module.graph_retrieve(exact_parts=["120-41824-003"])
    assert out["available"] is False
    assert out["candidates"] == []


# --- router overlay ----------------------------------------------------------


class _Env:
    def __init__(self):
        self.candidate_evidence = []
        self.retrieval_tunnels_used = []
        self.coverage = {}


class _Plan:
    def __init__(self, route):
        self.primary_route = route
        self.retrieval_tunnels = ["guided_candidate_discovery"]


class _Atoms:
    exact_part_numbers = []
    part_prefix = None
    part_contains = "41824"
    part_suffix = None
    ata_exact = []
    ata_prefix = None
    nomenclature_terms = []
    assembly_context = []


def _fake_router(module):
    class FakeRuntime:
        def gather_initial(self, plan, atoms):
            return _Env()

        def health(self):
            return {"quality_status": "PASS"}

    router = {
        "CognitiveRuntime": FakeRuntime,
        "candidate_matches_atoms": lambda value, atoms: True,
        "is_garbage_candidate": lambda value: False,
        "unique_dicts": lambda rows, keys: list(rows),
    }
    module.install_graph_source_retrieval(router)
    return FakeRuntime


def test_overlay_adds_candidates_and_declares_tunnel(monkeypatch, tmp_path):
    module = _fake_graph(monkeypatch, tmp_path)
    monkeypatch.setenv("TRACE_NET_H30_GRAPH_RETRIEVAL_ENABLED", "1")
    runtime = _fake_router(module)()
    plan = _Plan("guided_part_discovery")
    env = runtime.gather_initial(plan, _Atoms())

    assert any(c.get("graph_source_traversal") for c in env.candidate_evidence)
    assert "120-41824-003" in [c["candidate_value"] for c in env.candidate_evidence]
    assert "graph_source_traversal" in env.retrieval_tunnels_used
    # Declared as a plan amendment so used_tunnel stays a subset of declared.
    assert "graph_source_traversal" in plan.retrieval_tunnels
    assert env.coverage["graph_source_traversal"]["available"] is True


def test_overlay_merges_graph_into_existing_candidate(monkeypatch, tmp_path):
    module = _fake_graph(monkeypatch, tmp_path)
    monkeypatch.setenv("TRACE_NET_H30_GRAPH_RETRIEVAL_ENABLED", "1")

    # Base retrieval already produced this part (different page, no graph data).
    base_row = {
        "candidate_value": "120-41824-003",
        "page_id": "t_p_other_p999",
        "nomenclature": [],
        "source_resolved": False,
        "guidance_only": True,
    }

    class FakeRuntime:
        def gather_initial(self, plan, atoms):
            env = _Env()
            env.candidate_evidence.append(dict(base_row))
            return env

        def health(self):
            return {"quality_status": "PASS"}

    router = {
        "CognitiveRuntime": FakeRuntime,
        "candidate_matches_atoms": lambda value, atoms: True,
        "is_garbage_candidate": lambda value: False,
        # normalize_identifier intentionally omitted -> module fallback is used.
    }
    module.install_graph_source_retrieval(router)
    env = FakeRuntime().gather_initial(_Plan("guided_part_discovery"), _Atoms())

    matches = [
        c for c in env.candidate_evidence if c.get("candidate_value") == "120-41824-003"
    ]
    # Exactly one candidate for the part, identity by normalized candidate_value.
    assert len(matches) == 1
    assert len(env.candidate_evidence) == 1
    row = matches[0]
    # Graph metadata merged into the existing row.
    assert row["graph_source_traversal"] is True
    assert any(
        page.get("page_id") == "t_p_demo_p1" for page in row.get("graph_pages") or []
    )
    assert "RING, LOCKING" in row.get("nomenclature")
    assert row["source_resolved"] is True
    assert row.get("graph_match_reasons")
    # The overlay reports a merge, not an append.
    cov = env.coverage["graph_source_traversal"]
    assert cov["candidates_merged"] == 1
    assert cov["candidates_added"] == 0


def test_merge_does_not_explode_string_nomenclature():
    # q05 regression: a base candidate may store nomenclature as a plain string;
    # merging must not char-explode it into ['S','T','R','U',...].
    module = load_module()
    existing = {
        "candidate_value": "120-29067-005",
        "nomenclature": "STRUCTURE, ASSY",
        "page_id": "t_p_demo_p1",
        "ata_codes": "25-21-00",
    }
    graph_record = {
        "nomenclature": ["STRUCTURE, LATERAL LEG"],
        "ata_codes": ["25-21-00"],
        "graph_pages": [],
        "graph_match_reason": "partial_fragment",
    }
    module._merge_graph_record(existing, graph_record)
    assert existing["nomenclature"] == ["STRUCTURE, ASSY", "STRUCTURE, LATERAL LEG"]
    assert all(len(name) > 2 for name in existing["nomenclature"])
    assert existing["ata_codes"] == ["25-21-00"]


def test_overlay_disabled_by_default_is_noop(monkeypatch, tmp_path):
    module = _fake_graph(monkeypatch, tmp_path)
    monkeypatch.delenv("TRACE_NET_H30_GRAPH_RETRIEVAL_ENABLED", raising=False)
    runtime = _fake_router(module)()
    plan = _Plan("guided_part_discovery")
    env = runtime.gather_initial(plan, _Atoms())

    assert env.candidate_evidence == []
    assert "graph_source_traversal" not in env.retrieval_tunnels_used
    assert "graph_source_traversal" not in plan.retrieval_tunnels


def test_overlay_fires_for_multi_question_research_route(monkeypatch, tmp_path):
    # A compound "find part X and explain its nomenclature/page/source" request
    # routes to multi_question_research; the graph overlay must still traverse so
    # the exact part's nomenclature and source pages are surfaced (regression for
    # the live run where q01-q03 returned candidates=0 / nomenclature not found).
    module = _fake_graph(monkeypatch, tmp_path)
    monkeypatch.setenv("TRACE_NET_H30_GRAPH_RETRIEVAL_ENABLED", "1")
    runtime = _fake_router(module)()
    env = runtime.gather_initial(_Plan("multi_question_research"), _Atoms())

    assert "multi_question_research" in module.GRAPH_ROUTES
    assert any(c.get("graph_source_traversal") for c in env.candidate_evidence)
    assert "graph_source_traversal" in env.retrieval_tunnels_used


def test_overlay_skips_non_graph_routes(monkeypatch, tmp_path):
    module = _fake_graph(monkeypatch, tmp_path)
    monkeypatch.setenv("TRACE_NET_H30_GRAPH_RETRIEVAL_ENABLED", "1")
    runtime = _fake_router(module)()
    plan = _Plan("safe_general_chat")
    env = runtime.gather_initial(plan, _Atoms())

    assert env.candidate_evidence == []
    assert "graph_source_traversal" not in env.retrieval_tunnels_used
