import json
from pathlib import Path

from tiff.trace_net_e2e_live_webui_final_gated_gemma_endpoint_v24 import (
    MODEL_ID,
    attach_quality,
    build_endpoint_state,
    chat_completion_response,
    evaluate_quality,
    health_response,
    match_final_answer,
    openai_models_response,
    write_endpoint_files,
)


def sample_v23(path: Path) -> Path:
    rows = []
    for i in range(5):
        cap = i >= 2
        answer = f"TRACE-Net found value {i} on page p{i} [1]."
        if cap:
            answer += " Results were capped: TRACE-Net returned 10 of 150 matching records."
        rows.append(
            {
                "final_gate_id": f"live_llm_final_gate_v23_000{i}",
                "user_query": f"Find item {i}",
                "final_gate_status": "LIVE_LLM_FINAL_GATE_PASS",
                "final_answer": answer,
                "unsupported_claim_count": 0,
                "final_non_direct_citation_marker_count": 0,
                "graph_proof_authority_violation_count": 0,
                "summary_proof_authority_violation_count": 0,
                "repaired_from_draft": True,
            }
        )
    payload = {"module": "trace_net_e2e_live_llm_final_gate_v23", "quality_status": "PASS", "final_gate_records": rows}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_v24_build_endpoint_state_and_quality(tmp_path):
    source = sample_v23(tmp_path / "v23.json")
    state = build_endpoint_state(source, host="127.0.0.1", port=8020)
    assert state["model_id"] == MODEL_ID
    assert state["final_gate_count"] == 5
    assert state["ready_final_answer_count"] == 5
    assert state["cap_disclosures_in_final_answers_count"] == 3
    quality, checks = evaluate_quality(state)
    assert quality == "PASS"
    attach_quality(state, quality, checks)
    assert state["status"].endswith("READY")


def test_v24_match_and_chat_completion(tmp_path):
    state = build_endpoint_state(sample_v23(tmp_path / "v23.json"))
    quality, checks = evaluate_quality(state)
    attach_quality(state, quality, checks)
    match = match_final_answer(state, "find item 1")
    assert match is not None
    response = chat_completion_response(state, {"messages": [{"role": "user", "content": "Find item 1"}]})
    assert response["trace_net"]["matched_final_gated_answer"] is True
    assert "TRACE-Net found value 1" in response["choices"][0]["message"]["content"]
    missing = chat_completion_response(state, {"messages": [{"role": "user", "content": "not there"}]})
    assert missing["trace_net"]["matched_final_gated_answer"] is False
    assert "No source-truth claim is made" in missing["choices"][0]["message"]["content"]


def test_v24_health_models_and_write_files(tmp_path):
    state = build_endpoint_state(sample_v23(tmp_path / "v23.json"))
    quality, checks = evaluate_quality(state)
    attach_quality(state, quality, checks)
    assert health_response(state)["status"] == "ok"
    assert openai_models_response(state)["data"][0]["id"] == MODEL_ID
    paths = write_endpoint_files(state, tmp_path / "out")
    assert Path(paths["report_path"]).exists()
    assert Path(paths["inspect_md_path"]).read_text(encoding="utf-8").startswith("# TRACE-Net")
