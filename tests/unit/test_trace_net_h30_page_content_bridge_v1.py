from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = Path("scripts/trace_net_h30_page_content_bridge_v1.py")
FIXTURE = Path("tests/data/trace_net_page_content_fixture_v1.json")
V3_ARTIFACT = Path("tests/data/trace_net_page_content_fixture_v3_artifact.json")

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


def _texts(rows):
    return " ".join(r.get("text", "") for r in rows)


def test_p18_retrieves_only_its_own_v1_v2_v3_ocr_visual():
    mod = load_module()
    pack = mod.page_content_pack(load_graph(), P18)
    assert pack["found"] is True and pack["page_id"] == P18
    assert len(pack["v1_context"]) == 1 and "V1 context" in pack["v1_context"][0]["text"]
    assert len(pack["v2_context"]) == 1 and "seat structure" in pack["v2_context"][0]["text"].lower()
    assert len(pack["v3_page_intelligence"]) == 1
    assert pack["v3_page_intelligence"][0]["role"] == "image_visual_diagram"
    assert len(pack["ocr"]) == 1 and "FIGURE 2" in pack["ocr"][0]["text"]
    assert len(pack["visuals"]) == 2  # understanding + region chain
    assert any(p.get("part_number") == "120-20970-001" for p in pack["parts"])
    assert pack["source_trace"]["source_resolved"] is True
    assert pack["conflicts"] == []
    assert pack["telemetry"]["cross_page_record_count"] == 0
    assert pack["telemetry"]["exact_page_match"] is True
    assert pack["telemetry"]["gemma_call_count_added"] == 0
    blob = json.dumps(pack).lower()
    assert "armrest" not in blob and "cushion" not in blob


def test_p81_retrieves_only_its_own_v1_v2_v3_ocr_visual():
    mod = load_module()
    pack = mod.page_content_pack(load_graph(), P81)
    assert pack["page_id"] == P81
    assert "armrest" in _texts(pack["v2_context"]).lower()
    assert "ARMREST COVER" in _texts(pack["ocr"])
    assert len(pack["visuals"]) == 2
    blob = json.dumps(pack).lower()
    assert "seat structure" not in blob and "cushion" not in blob


def test_p482_retrieves_v1_v2_ocr_table_and_procedure_v3_from_artifact():
    mod = load_module()
    graph = load_graph()
    # No graph V3 for p482; supply the V3 artifact fixture for fallback.
    import os

    os.environ["TRACE_NET_H30_PAGE_V3_ARTIFACT"] = str(V3_ARTIFACT)
    # Only the V3 artifact index is relevant here.
    artifacts = {"v3_page_intelligence": mod._load_artifact_index(str(V3_ARTIFACT))}
    pack = mod.page_content_pack(graph, P482, artifacts=artifacts)
    os.environ.pop("TRACE_NET_H30_PAGE_V3_ARTIFACT", None)

    assert pack["page_id"] == P482
    assert len(pack["v2_context"]) == 1 and "removal procedure" in pack["v2_context"][0]["text"].lower()
    # V3 filled from the artifact (graph had none).
    assert len(pack["v3_page_intelligence"]) == 1
    assert pack["v3_page_intelligence"][0]["origin"] == "artifact"
    assert pack["v3_page_intelligence"][0]["role"] == "procedure_or_description"
    assert "STEP 1" in _texts(pack["ocr"])
    # Table chain element -> row -> cell all collected.
    table_text = _texts(pack["tables"])
    assert "IPL table" in table_text and "item 1" in table_text and "120-29073-006" in table_text
    assert len(pack["tables"]) == 3
    assert pack["visuals"] == []
    assert any(p.get("part_number") == "120-29073-006" for p in pack["parts"])
    assert pack["telemetry"]["artifact_fallback_record_count"] >= 1
    assert pack["telemetry"]["cross_page_record_count"] == 0


def test_nonexistent_page_returns_no_content():
    mod = load_module()
    graph = load_graph()
    pack = mod.page_content_pack(graph, "t_p_120_1176_p999999")
    assert pack["found"] is False
    assert pack["telemetry"]["exact_page_match"] is False
    for key in ("v1_context", "v2_context", "v3_page_intelligence", "ocr", "tables", "visuals"):
        assert pack[key] == []
    # A substring must not match a real page (p000018 vs p000181 defect class).
    assert mod.page_content_pack(graph, "t_p_120_1176_p0000")["found"] is False


def test_v1_stays_has_context_and_v2_stays_has_context_v2():
    mod = load_module()
    assert mod.V1_EDGES == ("HAS_CONTEXT",)
    assert mod.V2_EDGES == ("HAS_CONTEXT_V2",)
    assert mod.V3_EDGES == ("HAS_V3_PAGE_INTELLIGENCE",)
    pack = mod.page_content_pack(load_graph(), P18)
    # V1 and V2 are distinct records from distinct edges (not aliased).
    assert pack["v1_context"][0]["text"] != pack["v2_context"][0]["text"]
    assert pack["v1_context"][0]["node_id"] != pack["v2_context"][0]["node_id"]


def test_table_chain_uses_element_row_cell_edges():
    mod = load_module()
    assert mod.TABLE_CHAIN == (("HAS_TABLE_ELEMENT",), ("HAS_TABLE_ROW",), ("HAS_TABLE_CELL",))
    pack = mod.page_content_pack(load_graph(), P482)
    node_ids = {r["node_id"] for r in pack["tables"]}
    assert {"tel:p482", "trow:p482", "tcell:p482"} <= node_ids


def test_visual_chain_uses_understanding_and_region_edges():
    mod = load_module()
    assert mod.VISUAL_CHAIN == (("HAS_VISUAL_UNDERSTANDING",), ("HAS_VISUAL_REGION",))
    pack = mod.page_content_pack(load_graph(), P18)
    node_ids = {r["node_id"] for r in pack["visuals"]}
    assert {"vu:p18", "region:p18"} <= node_ids


def test_conflicting_ata_is_reported_as_conflict():
    mod = load_module()
    pack = mod.page_content_pack(load_graph(), P81)
    ata_conflicts = [c for c in pack["conflicts"] if c["field"] == "ata"]
    assert ata_conflicts
    assert set(ata_conflicts[0]["conflicting_values"]) >= {"25-21-00", "51-25-00"}
    assert ata_conflicts[0]["resolution_status"] == "unresolved"


def test_full_pack_reaches_the_writer_prompt():
    mod = load_module()
    pack = mod.page_content_pack(load_graph(), P18)
    result = {"evidence_envelope": {"coverage": {"page_content": {"available": True, "pages": [pack]}}}}
    block = mod.render_page_content_prompt(result)
    assert block, "expected a non-empty page-content prompt block"
    assert P18 in block
    assert "V1 context" in block and "V2 context" in block and "V3 intelligence" in block
    assert "OCR text" in block and "Visual understanding" in block
    assert "seat structure" in block.lower()


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


def test_bridge_overlay_adds_no_upstream_or_second_gemma_call(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_PAGE_CONTENT_BRIDGE_ENABLED", "1")
    mod = load_module()
    graph = load_graph()
    monkeypatch.setattr(mod, "load_graph_index", lambda: graph)
    monkeypatch.setattr(mod, "load_page_artifacts", lambda: {})

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

    assert upstream_calls == []  # no upstream / no second model call
    pc = env.coverage["page_content"]
    assert pc["available"] is True and pc["page_count"] == 1
    assert pc["telemetry"]["gemma_call_count_added"] == 0
    assert pc["telemetry"]["cross_page_record_count"] == 0
    assert "page_content_bridge" in env.retrieval_tunnels_used
