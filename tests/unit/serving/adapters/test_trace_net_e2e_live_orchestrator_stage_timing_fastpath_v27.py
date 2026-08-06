import json
from pathlib import Path

from tiff.trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27 import (
    build_state,
    evaluate_quality,
    run_live_query_v27,
    should_use_fast_path,
)


def _adapter(path: Path) -> Path:
    rows = [
        {"page_id": "t_p_120_1176_p000003", "field_name": "covered_part_number", "normalized_value": "120-36833-503", "source_evidence_id": "doc-1"},
        {"page_id": "t_p_120_1176_p000005", "field_name": "manual_page_reference", "normalized_value": "25-21-00", "source_evidence_id": "doc-2"},
        {"page_id": "t_p_120_1176_p000027", "field_name": "ipl_text", "normalized_value": "ILLUSTRATED PARTS LIST", "source_evidence_id": "doc-3"},
        {"page_id": "t_p_120_1176_p000027", "field_name": "ipl_text", "normalized_value": "i", "source_evidence_id": "doc-4"},
    ]
    p = path / "exact.json"
    p.write_text(json.dumps({"quality_status": "PASS", "exact_search_documents": rows}), encoding="utf-8")
    return p


def test_v27_exact_part_fast_path_skips_llm(tmp_path):
    state = build_state(_adapter(tmp_path), llm_mode="ollama", fast_path_mode="exact")
    result = run_live_query_v27("Find part number 120-36833-503", state)
    assert result["fast_path_used"] is True
    assert result["llm_status"] == "LLM_SKIPPED_FAST_PATH"
    assert result["llm_called"] is False
    assert result["final_gate_status"] == "LIVE_ORCHESTRATOR_FINAL_GATE_PASS"
    assert "120-36833-503" in result["final_answer"]
    assert result["stage_timings_ms"]["total_request_ms"] >= 0
    assert "llm_draft_ms" in result["stage_timings_ms"]


def test_v27_missing_part_fast_path_audit_only(tmp_path):
    state = build_state(_adapter(tmp_path), llm_mode="ollama", fast_path_mode="exact")
    result = run_live_query_v27("Find part number DOES-NOT-EXIST-999", state)
    assert result["fast_path_used"] is True
    assert result["final_gate_status"] == "LIVE_ORCHESTRATOR_AUDIT_ONLY"
    assert result["retrieval"]["total_match_count"] == 0
    assert "did not find" in result["final_answer"]


def test_v27_fast_path_decision_for_broad_query_requires_llm(tmp_path):
    state = build_state(_adapter(tmp_path), llm_mode="simulate", fast_path_mode="exact")
    result = run_live_query_v27("What maintenance manual pages mention covered part numbers?", state)
    assert result["fast_path_used"] is False
    assert result["llm_status"] == "LLM_SIMULATED"
    assert result["final_gate_status"] == "LIVE_ORCHESTRATOR_FINAL_GATE_PASS"


def test_v27_build_state_quality_with_sample_timings(tmp_path):
    state = build_state(
        _adapter(tmp_path),
        llm_mode="simulate",
        fast_path_mode="exact",
        include_standard_demo_queries=True,
    )
    quality_status, checks = evaluate_quality(
        state,
        min_exact_search_documents=4,
        min_endpoint_routes=4,
        min_sample_queries=6,
        min_sample_successes=6,
        min_stage_timing_records=6,
        min_fast_path_samples=5,
        max_sample_llm_calls=1,
        require_no_answer_permission=True,
    )
    assert quality_status == "PASS", checks
    assert state["stage_timing_record_count"] == 6
    assert state["fast_path_sample_count"] >= 5


def test_should_use_fast_path_can_be_disabled():
    plan = {"query_intent": "part_number", "strict_target_match_required": True}
    retrieval = {"direct_evidence": [{"page_id": "p1"}]}
    used, reason = should_use_fast_path(plan, retrieval, fast_path_mode="off")
    assert used is False
    assert reason == "fast_path_disabled"
