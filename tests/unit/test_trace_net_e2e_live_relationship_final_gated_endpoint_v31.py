from pathlib import Path
import json

from tiff.trace_net_e2e_live_relationship_final_gated_endpoint_v31 import (
    MODEL_ID,
    apply_relationship_final_gate,
    make_chat_completion_response,
    build_report,
    check_report,
)


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_apply_relationship_gate_repairs_graph_as_proof():
    result = {
        "answer": "The Leiden community proves that part number 120-36833-503 is related to manual reference 25-21-00.",
        "response_mode": "relationship_synthesis",
        "relationship_query": True,
        "final_gate_status": None,
    }
    gated = apply_relationship_final_gate("Explain relationship", result)
    assert gated["relationship_final_gate_status"] == "RELATIONSHIP_FINAL_GATE_PASS"
    assert gated["relationship_final_gate_repaired"] is True
    assert "not proof authority" in gated["answer"] or "guidance only" in gated["answer"]
    assert gated["relationship_final_gate_post_issue_count"] == 0


def test_apply_relationship_gate_preserves_safe_metadata_answer():
    result = {
        "answer": "TRACE-Net found graph Has_nomenclature guidance for 11 page(s). Graph nomenclature signals are navigation/count guidance and should be confirmed with source-truth records before factual part claims.",
        "response_mode": "artifact_metadata_count",
        "relationship_query": False,
        "relationship_guidance_only": True,
        "final_gate_status": "LIVE_ORCHESTRATOR_METADATA_COUNT_PASS",
        "metadata_count_source": "graph_has_nomenclature_signal",
    }
    gated = apply_relationship_final_gate("how many pages mention a nomenclature", result)
    assert gated["relationship_final_gate_status"] == "RELATIONSHIP_FINAL_GATE_PASS"
    assert gated["relationship_final_gate_repaired"] is False
    assert "Has_nomenclature" in gated["answer"]


def test_chat_completion_response_exposes_relationship_gate_trace():
    gated = apply_relationship_final_gate(
        "q",
        {"answer": "safe answer", "response_mode": "audit_only", "relationship_query": False, "final_gate_status": "LIVE_ORCHESTRATOR_AUDIT_ONLY"},
    )
    response = make_chat_completion_response(MODEL_ID, "q", gated)
    assert response["model"] == MODEL_ID
    assert response["choices"][0]["message"]["content"] == "safe answer"
    assert response["trace_net"]["relationship_final_gate_applied"] is True
    assert response["trace_net"]["relationship_final_gate_status"] == "RELATIONSHIP_FINAL_GATE_PASS"


def test_build_and_check_report_with_tiny_artifacts(tmp_path):
    table = tmp_path / "table.json"
    page_context = tmp_path / "page_context.json"
    leiden = tmp_path / "leiden.json"
    graph = tmp_path / "graph.json"
    router_report = tmp_path / "router.json"
    gate_report = tmp_path / "gate.json"
    out = tmp_path / "out"

    _write_json(table, {"records": [
        {"record_id": "r1", "page_id": "t_p_120_1176_p000003", "field": "covered_part_number", "value": "120-36833-503"},
        {"record_id": "r2", "page_id": "t_p_120_1176_p000005", "field": "manual_page_reference", "value": "25-21-00"},
        {"record_id": "r3", "page_id": "t_p_120_1176_p000027", "field": "ipl_text", "value": "ILLUSTRATED PARTS LIST"},
    ]})
    _write_json(page_context, {"records": [{"page_id": "t_p_120_1176_p000001", "summary": "s"}]})
    _write_json(leiden, {"communities": [{"leiden_community_id": "tracenet_community_00001", "pages": ["t_p_120_1176_p000003", "t_p_120_1176_p000004"]}]})
    _write_json(graph, {"edges": [
        {"source": "part_120-36833-503", "target": "nomenclature_foo", "edge_type": "HAS_NOMENCLATURE"},
        {"source": "part_120-36833-503", "target": "t_p_120_1176_p000003", "edge_type": "APPEARS_ON"},
    ]})
    _write_json(router_report, {
        "quality_status": "PASS",
        "exact_search_document_count": 3,
        "page_context_v2_page_count": 1,
        "graph_has_v2_page_count": 0,
        "graph_has_nomenclature_page_count": 1,
        "graph_signal_paths": [str(graph)],
    })
    _write_json(gate_report, {"quality_status": "PASS", "post_gate_issue_count": 0})

    report = build_report(
        relationship_router_hardening=router_report,
        relationship_final_gate_hardener=gate_report,
        table_exact_search_adapter=table,
        page_context_v2=page_context,
        leiden_communities=leiden,
        graph_signal_paths=[graph],
        output_dir=out,
        include_standard_demo_queries=True,
        min_sample_queries=8,
        min_sample_successes=8,
        min_relationship_final_gate_applied=8,
        min_relationship_records=2,
        max_post_gate_issue_count=0,
        require_no_answer_permission=True,
        quality=True,
    )
    assert report["quality_status"] == "PASS"
    checked = check_report(
        report_path=out / "trace_net_e2e_live_relationship_final_gated_endpoint_v31.json",
        min_sample_queries=8,
        min_sample_successes=8,
        min_relationship_final_gate_applied=8,
        min_relationship_records=2,
        max_post_gate_issue_count=0,
        require_no_answer_permission=True,
    )
    assert checked["quality_status"] == "PASS"
