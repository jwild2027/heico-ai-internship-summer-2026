from __future__ import annotations
import importlib.util, sys, json
from pathlib import Path

SCRIPT = Path("scripts/operations/serving/serve_trace_net_openwebui_unified_rag_v2.py")

def load():
    spec = importlib.util.spec_from_file_location("unified_v2", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["unified_v2"] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod

def visual_doc(page="p1", part="120-41824-003", subject="passenger seat assembly"):
    return {
        "page_id": page,
        "document_id": "d-" + page,
        "retrieval_text": f"{subject} figure 2 {part}",
        "structured_visual_card": {
            "normalized_subject": subject,
            "normalized_visual_page_type": "technical_diagram",
            "figure_refs": ["figure 2 sheet 1"],
            "part_numbers": [part],
            "visible_callouts": ["1", "2"],
            "retrieval_keywords": ["passenger seat", "assembly"],
        },
        "safety_contract": {"answer_permission":False,"final_answer_allowed":False,"source_truth_mutation_allowed":False},
    }

def write_docs(tmp_path, docs):
    p = tmp_path / "docs.jsonl"
    p.write_text("\n".join(json.dumps(d) for d in docs) + "\n", encoding="utf-8")
    return p

def test_exact_visual_part_filters_unrelated(tmp_path):
    mod = load()
    idx = mod.VisualIndex(write_docs(tmp_path, [visual_doc("p1"), visual_doc("p2","120-99999-001","other diagram")]))
    ranked = idx.rank("Find diagram for part number 120-41824-003")
    assert len(ranked) == 1
    assert ranked[0][1]["page_id"] == "p1"

def test_generic_visual_terms_do_not_return_everything(tmp_path):
    mod = load()
    idx = mod.VisualIndex(write_docs(tmp_path, [visual_doc("p1"), visual_doc("p2","120-99999-001","unrelated latch")]))
    ranked = idx.rank("Show a diagram")
    assert ranked == []

def test_malformed_visual_jsonl_fails_closed(tmp_path):
    mod = load()
    p = tmp_path / "bad.jsonl"
    p.write_text('{"page_id":"p1"}\nnot-json\n', encoding="utf-8")
    try:
        mod.VisualIndex(p, strict=True)
    except ValueError as exc:
        assert "strict validation" in str(exc)
    else:
        raise AssertionError("expected strict failure")

def test_multiturn_context_reuses_part_number():
    mod = load()
    resolved = mod.resolve_conversation({"messages":[
        {"role":"user","content":"Find part number 120-41824-003"},
        {"role":"assistant","content":"Okay"},
        {"role":"user","content":"What figure is it in?"},
    ]})
    assert resolved["working_memory_applied"] is True
    assert "120-41824-003" in resolved["resolved_query"]

def test_guided_router_detection():
    mod = load()
    assert mod.route_kind("I only know the part starts with 24") == "guided_discovery"
    assert mod.route_kind("Find diagram for part 120-41824-003") == "gemma_confirmed_image_visual"
    assert mod.route_kind("Find part number 120-41824-003") == "normal_ask"

def test_self_rag_rejects_unrelated_exact_visual():
    mod = load()
    result = {"citations":[{"part_numbers":["120-99999-001"]}],"answer_permission":False,"final_answer_allowed":False,"source_truth_mutation_allowed":False}
    critic = mod.self_rag_critic("gemma_confirmed_image_visual", result, "Find diagram for 120-41824-003")
    assert critic["quality_status"] == "RETRY"
    assert "visual_exact_part_returned_unrelated_doc" in critic["failures"]
