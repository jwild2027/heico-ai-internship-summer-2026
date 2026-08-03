import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/build/visual/build_trace_net_visual_question_context_adapter_v1_3.py"

def load():
    spec = importlib.util.spec_from_file_location("vqc13", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    assert spec.loader
    spec.loader.exec_module(m)
    return m

def test_llava_adapter_uses_real_fields():
    m = load()
    out = m.adapt_llava({
        "visual_summary": "A technical drawing.",
        "diagram_type": "technical_drawing",
        "visual_confidence": "medium",
        "visible_text_candidates": ["Technical Drawing"],
        "source_trace_ready": True,
        "llava_model": "llava:13b",
    })
    assert out["visual_summary"] == "A technical drawing."
    assert out["diagram_type"] == "technical_drawing"
    assert out["model"] == "llava:13b"

def test_figure_adapter_uses_regions_and_callouts():
    m = load()
    out = m.adapt_figure_understanding({
        "ata_code": "25-21-00",
        "figure_refs": ["figure 601"],
        "callout_labels": ["1", "2"],
        "visual_regions": [{
            "region_id": "vis_region__t_p_120_1176_p000491__abc",
            "source_snippet": "repair procedure",
            "detected_callout_labels": ["1"],
            "detected_figure_refs": ["figure 601"],
        }],
    })
    assert out["ata_code"] == "25-21-00"
    assert out["visual_regions"][0]["region_id"].endswith("__abc")
    assert out["callout_labels"] == ["1", "2"]

def test_build_context_is_read_only(tmp_path):
    m = load()
    root = tmp_path/"trace_net"
    (root/"page_route_manifest").mkdir(parents=True)
    route = root/"page_route_manifest/routes.jsonl"
    route.write_text(json.dumps({"page_id":"t_p_120_1176_p000491","route":"image_visual"})+"\n", encoding="utf-8")
    d = root/"llava_visual_summary_batch_v1"
    d.mkdir()
    (d/"x.jsonl").write_text(json.dumps({
        "page_id":"t_p_120_1176_p000491",
        "visual_summary":"A technical drawing.",
        "diagram_type":"technical_drawing",
        "source_trace_ready":True
    })+"\n", encoding="utf-8")
    f = root/"figure_chart_understanding"
    f.mkdir()
    (f/"records.jsonl").write_text(json.dumps({
        "page_id":"t_p_120_1176_p000491",
        "ata_code":"25-21-00",
        "figure_refs":["figure 601"],
        "visual_regions":[{"region_id":"vis_region__t_p_120_1176_p000491__abc","source_snippet":"seat repair"}]
    })+"\n", encoding="utf-8")
    pages, contexts, metrics = m.build_contexts(root, route, None)
    assert len(contexts) == 1
    record = contexts[0]
    assert record["visual_summary"]["descriptions"] == ["A technical drawing."]
    assert record["visual_ids"] == ["vis_region__t_p_120_1176_p000491__abc"]
    assert record["safety_contract"]["source_truth_mutation_allowed"] is False
    assert record["evidence_status"]["final_answer_allowed"] is False
