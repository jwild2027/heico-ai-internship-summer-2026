import json
from pathlib import Path

from tiff.trace_net_e2e_live_orchestrator_endpoint_v25 import (
    MODEL_ID,
    attach_quality,
    build_orchestrator_state,
    chat_completion_response,
    detect_query_plan,
    evaluate_quality,
    load_state_for_serving,
    run_live_query,
    write_endpoint_files,
)


def sample_adapter(path: Path) -> Path:
    docs = []
    for value in ["120-36834-509", "120-36833-501", "120-36833-001", "120-36833-003", "120-36833-005"]:
        docs.append({"document_id": f"doc-{value}", "page_id": "t_p_120_1176_p000003", "field_name": "covered_part_number", "normalized_value": value, "search_text": value})
    for i in range(12):
        docs.append({"document_id": f"manual-{i}", "page_id": "t_p_120_1176_p000005", "field_name": "manual_page_reference", "normalized_value": "25-21-00", "search_text": "manual reference 25-21-00"})
    docs.extend([
        {"document_id": "txt-1", "page_id": "t_p_120_1176_p000027", "field_name": "ipl_text", "normalized_value": "MAINTENANCE MANUAL WITH", "search_text": "MAINTENANCE MANUAL WITH"},
        {"document_id": "txt-2", "page_id": "t_p_120_1176_p000027", "field_name": "ipl_text", "normalized_value": "ILLUSTRATED PARTS LIST", "search_text": "ILLUSTRATED PARTS LIST"},
        {"document_id": "txt-3", "page_id": "t_p_120_1176_p000027", "field_name": "ipl_text", "normalized_value": "i", "search_text": "i"},
    ])
    path.write_text(json.dumps({"quality_status": "PASS", "exact_search_documents": docs}), encoding="utf-8")
    return path


def sample_page_context(path: Path) -> Path:
    rows = [
        {"page_id": "t_p_120_1176_p000003", "summary": "parts list summary"},
        {"page_id": "t_p_120_1176_p000005", "summary": "manual reference summary"},
    ]
    path.write_text(json.dumps({"page_contexts": rows}), encoding="utf-8")
    return path


def sample_leiden(path: Path) -> Path:
    rows = [
        {"community_id": "c1", "page_ids": ["t_p_120_1176_p000003", "t_p_120_1176_p000319"]},
        {"community_id": "c2", "page_ids": ["t_p_120_1176_p000005"]},
    ]
    path.write_text(json.dumps({"communities": rows}), encoding="utf-8")
    return path


def test_v25_detect_query_plan():
    assert detect_query_plan("Find part number 120-36834-509")["query_intent"] == "part_number"
    missing_plan = detect_query_plan("Find part number DOES-NOT-EXIST-999")
    assert missing_plan["query_intent"] == "part_number"
    assert missing_plan["target_value"] == "DOES-NOT-EXIST-999"
    assert missing_plan["strict_target_match_required"] is True
    assert detect_query_plan("Where is manual reference 25-21-00 used?")["query_intent"] == "manual_page_reference"
    assert detect_query_plan("Search table text MAINTENANCE MANUAL WITH")["query_intent"] == "table_text"


def test_v25_build_quality_and_write(tmp_path):
    state = build_orchestrator_state(
        sample_adapter(tmp_path / "adapter.json"),
        page_context_v2_path=sample_page_context(tmp_path / "page_context.json"),
        leiden_communities_path=sample_leiden(tmp_path / "leiden.json"),
        include_standard_demo_queries=True,
    )
    quality, checks = evaluate_quality(state, min_exact_search_documents=10, min_sample_successes=5)
    assert quality == "PASS"
    attach_quality(state, quality, checks)
    assert state["model_id"] == MODEL_ID
    paths = write_endpoint_files(state, tmp_path / "out")
    assert Path(paths["report_path"]).exists()
    assert Path(paths["inspect_md_path"]).read_text(encoding="utf-8").startswith("# TRACE-Net")


def test_v25_live_query_final_gate_behaviors(tmp_path):
    state = build_orchestrator_state(sample_adapter(tmp_path / "adapter.json"), include_standard_demo_queries=False)
    part = run_live_query("Find part number 120-36834-509", state)
    assert "covered_part_number" in part["final_answer"]
    assert "physically" in part["final_answer"]
    assert part["retrieval"]["total_match_count"] == 1
    manual = run_live_query("Where is manual reference 25-21-00 used?", state)
    assert "Results were capped" in manual["final_answer"]
    assert manual["retrieval"]["total_match_count"] == 12
    table = run_live_query("Search table text MAINTENANCE MANUAL WITH", state)
    assert "Nearby OCR/table records" in table["final_answer"]
    assert "ILLUSTRATED" not in table["final_answer"]


def test_v25_unknown_part_number_is_audit_only(tmp_path):
    state = build_orchestrator_state(sample_adapter(tmp_path / "adapter.json"), include_standard_demo_queries=False)
    missing = run_live_query("Find part number DOES-NOT-EXIST-999", state)
    assert missing["query_plan"]["query_intent"] == "part_number"
    assert missing["final_gate_status"] == "LIVE_ORCHESTRATOR_AUDIT_ONLY"
    assert missing["final_answer_ready_for_webui"] is False
    assert "did not find direct citation-ready source-truth evidence" in missing["final_answer"]
    assert missing["retrieval"]["total_match_count"] == 0


def test_v25_chat_completion_and_reload(tmp_path):
    adapter = sample_adapter(tmp_path / "adapter.json")
    state = build_orchestrator_state(adapter, include_standard_demo_queries=True)
    quality, checks = evaluate_quality(state)
    attach_quality(state, quality, checks)
    paths = write_endpoint_files(state, tmp_path / "out")
    loaded = load_state_for_serving(Path(paths["report_path"]))
    response = chat_completion_response(loaded, {"messages": [{"role": "user", "content": "Find part number 120-36833-501"}]})
    assert response["trace_net"]["endpoint_version"] == "live_orchestrator_v25"
    assert "120-36833-501" in response["choices"][0]["message"]["content"]
