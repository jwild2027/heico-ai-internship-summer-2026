from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = Path("scripts/trace_net_h30_page_content_bridge_v1.py")
FIXTURE = Path("tests/data/trace_net_page_content_fixture_v1.json")

P18 = "t_p_120_1176_p000018"
P81 = "t_p_120_1176_p000081"
P482 = "t_p_120_1176_p000482"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "trace_net_h30_page_content_bridge_test", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def load_graph():
    from tiff.trace_net_graph_query_helper_v1 import GraphIndex, extract_edges, extract_nodes

    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return GraphIndex(extract_nodes(data), extract_edges(data))


def test_p18_retrieves_only_its_own_v2_v3_ocr_visual():
    mod = load_module()
    pack = mod.page_content_pack(load_graph(), P18)
    assert pack["found"] is True and pack["page_id"] == P18
    assert len(pack["v2"]) == 1 and "seat structure" in pack["v2"][0]["text"].lower()
    assert len(pack["v3"]) == 1 and pack["v3"][0]["role"] == "image_visual_diagram"
    assert len(pack["ocr"]) == 1 and "FIGURE 2" in pack["ocr"][0]["text"]
    assert len(pack["visuals"]) == 1 and pack["visuals"][0]["guidance_only"] is True
    assert any(p.get("part_number") == "120-20970-001" for p in pack["parts"])
    assert pack["source_trace"]["source_resolved"] is True
    assert pack["conflicts"] == []
    blob = json.dumps(pack).lower()
    assert "armrest cover" not in blob and "cushion" not in blob


def test_p81_retrieves_only_its_own_v2_v3_ocr_visual():
    mod = load_module()
    pack = mod.page_content_pack(load_graph(), P81)
    assert pack["found"] is True and pack["page_id"] == P81
    assert len(pack["v2"]) == 1 and "armrest" in pack["v2"][0]["text"].lower()
    assert len(pack["ocr"]) == 1 and "ARMREST COVER" in pack["ocr"][0]["text"]
    assert len(pack["visuals"]) == 1
    blob = json.dumps(pack).lower()
    assert "seat structure" not in blob and "cushion" not in blob


def test_p482_retrieves_only_its_own_v2_v3_ocr_procedure():
    mod = load_module()
    pack = mod.page_content_pack(load_graph(), P482)
    assert pack["found"] is True and pack["page_id"] == P482
    assert len(pack["v2"]) == 1 and "removal procedure" in pack["v2"][0]["text"].lower()
    assert pack["v3"][0]["role"] == "procedure_or_description"
    assert len(pack["ocr"]) == 1 and "STEP 1" in pack["ocr"][0]["text"]
    assert len(pack["tables"]) == 1 and "120-29073-006" in pack["tables"][0]["text"]
    assert pack["visuals"] == []
    assert any(p.get("part_number") == "120-29073-006" for p in pack["parts"])
    blob = json.dumps(pack).lower()
    assert "armrest" not in blob and "figure 2 sheet 1" not in blob


def test_nonexistent_page_returns_no_content():
    mod = load_module()
    graph = load_graph()
    pack = mod.page_content_pack(graph, "t_p_120_1176_p999999")
    assert pack["found"] is False
    assert pack["v2"] == [] and pack["v3"] == [] and pack["ocr"] == []
    assert pack["tables"] == [] and pack["visuals"] == []
    # A substring of a real page id must not match (p000018 vs p000181 defect).
    assert mod.page_content_pack(graph, "t_p_120_1176_p0000")["found"] is False


def test_no_cross_page_v2_v3_can_enter_the_pack():
    mod = load_module()
    graph = load_graph()
    p18 = mod.page_content_pack(graph, P18)
    p482 = mod.page_content_pack(graph, P482)
    assert p18["v2"][0]["node_id"] != p482["v2"][0]["node_id"]
    assert p18["v3"][0]["node_id"] != p482["v3"][0]["node_id"]
    ids18 = {
        rec["node_id"]
        for rec in p18["v2"] + p18["v3"] + p18["ocr"] + p18["visuals"]
    }
    assert all(node_id.endswith("p18") for node_id in ids18)


def test_conflicting_ata_is_reported_as_conflict():
    mod = load_module()
    pack = mod.page_content_pack(load_graph(), P81)
    ata_conflicts = [c for c in pack["conflicts"] if c["field"] == "ata"]
    assert ata_conflicts, "expected an unresolved ATA conflict on p81"
    assert set(ata_conflicts[0]["conflicting_values"]) >= {"25-21-00", "51-25-00"}
    assert ata_conflicts[0]["resolution_status"] == "unresolved"


def test_bridge_is_read_only():
    mod = load_module()
    graph = load_graph()
    nodes_before = copy.deepcopy(graph.nodes)
    edges_before = copy.deepcopy(graph.edges)
    mod.page_content_pack(graph, P18)
    mod.page_content_pack(graph, P482)
    mod.page_content_pack(graph, "t_p_120_1176_p999999")
    assert graph.nodes == nodes_before
    assert graph.edges == edges_before


def test_bridge_overlay_adds_no_upstream_or_model_call(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_PAGE_CONTENT_BRIDGE_ENABLED", "1")
    mod = load_module()
    graph = load_graph()
    monkeypatch.setattr(mod, "load_graph_index", lambda: graph)

    upstream_calls = []

    class Env:
        def __init__(self):
            self.semantic_guidance = []
            self.contradictions = []
            self.coverage = {}
            self.retrieval_tunnels_used = []

    class Plan:
        def __init__(self):
            self.primary_route = "document_page_navigation"
            self.retrieval_tunnels = []

    class Atoms:
        page_ids = [P18]

    class Base:
        def gather_initial(self, plan, atoms):
            return Env()

        def add_unified(self, *a, **k):
            upstream_calls.append("unified")

        def add_guided(self, *a, **k):
            upstream_calls.append("guided")

        def health(self):
            return {"quality_status": "PASS"}

    router = {"CognitiveRuntime": type("Runtime", (Base,), {})}
    mod.install_page_content_bridge(router)
    env = router["CognitiveRuntime"]().gather_initial(Plan(), Atoms())

    # The bridge is read-only and adds no upstream/model call (one-Gemma-call
    # limit preserved; it only enriches the envelope for the single writer call).
    assert upstream_calls == []
    assert env.coverage["page_content"]["available"] is True
    assert env.coverage["page_content"]["page_count"] == 1
    assert "page_content_bridge" in env.retrieval_tunnels_used
    assert any(s.get("candidate_type") == "page_content" for s in env.semantic_guidance)
