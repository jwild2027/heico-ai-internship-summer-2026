import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/build/visual/build_trace_net_visual_question_context_adapter_v1_2.py"

def load():
    spec = importlib.util.spec_from_file_location("vqc12", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    assert spec.loader
    spec.loader.exec_module(m)
    return m

def test_aggregate_container_is_not_joined_as_one_page(tmp_path):
    m = load()
    root = tmp_path/"trace_net"
    (root/"page_route_manifest").mkdir(parents=True)
    route = root/"page_route_manifest/routes.jsonl"
    route.write_text(
        json.dumps({"page_id":"t_p_120_1176_p000001","route":"image_visual"})+"\n"+
        json.dumps({"page_id":"t_p_120_1176_p000002","route":"image_visual"})+"\n",
        encoding="utf-8"
    )
    d = root/"image_visual_summary"
    d.mkdir()
    (d/"summary.json").write_text(json.dumps({
        "status":"DONE",
        "records":[
            {"page_id":"t_p_120_1176_p000001","visual_id":"vis_region__t_p_120_1176_p000001__a"},
            {"page_id":"t_p_120_1176_p000002","visual_id":"vis_region__t_p_120_1176_p000002__b"},
        ]
    }), encoding="utf-8")
    pages,_ = m.discover_image_pages(route)
    contexts, metrics = m.build_contexts(root, tmp_path/"out", pages, None)
    by_page = {r["page_id"]: r for r in contexts}
    assert by_page["t_p_120_1176_p000001"]["visual_ids"] == ["vis_region__t_p_120_1176_p000001__a"]
    assert by_page["t_p_120_1176_p000002"]["visual_ids"] == ["vis_region__t_p_120_1176_p000002__b"]

def test_cross_page_visual_id_is_rejected(tmp_path):
    m = load()
    root = tmp_path/"trace_net"
    (root/"page_route_manifest").mkdir(parents=True)
    route = root/"page_route_manifest/routes.jsonl"
    route.write_text(json.dumps({"page_id":"t_p_120_1176_p000001","route":"image_visual"})+"\n", encoding="utf-8")
    d = root/"image_visual_summary"
    d.mkdir()
    (d/"x.jsonl").write_text(json.dumps({
        "page_id":"t_p_120_1176_p000001",
        "visual_id":[
            "vis_region__t_p_120_1176_p000001__a",
            "vis_region__t_p_120_1176_p000002__b"
        ]
    })+"\n", encoding="utf-8")
    pages,_ = m.discover_image_pages(route)
    contexts, metrics = m.build_contexts(root, tmp_path/"out", pages, None)
    assert contexts[0]["visual_ids"] == ["vis_region__t_p_120_1176_p000001__a"]
    assert metrics["rejected_cross_page_visual_id_count"] == 1

def test_safety_locked(tmp_path):
    m = load()
    root = tmp_path/"trace_net"
    (root/"page_route_manifest").mkdir(parents=True)
    route = root/"page_route_manifest/routes.jsonl"
    route.write_text(json.dumps({"page_id":"t_p_120_1176_p000001","route":"image_visual"})+"\n", encoding="utf-8")
    d = root/"image_visual_evidence_pack_v1"
    d.mkdir()
    (d/"x.jsonl").write_text(json.dumps({
        "page_id":"t_p_120_1176_p000001",
        "visual_id":"vis_region__t_p_120_1176_p000001__a",
        "citation_ready":True,
        "source_trace_ready":True
    })+"\n", encoding="utf-8")
    pages,_ = m.discover_image_pages(route)
    contexts,_ = m.build_contexts(root, tmp_path/"out", pages, None)
    assert contexts[0]["evidence_status"]["final_answer_allowed"] is False
    assert contexts[0]["safety_contract"]["source_truth_mutation_allowed_count"] == 0
