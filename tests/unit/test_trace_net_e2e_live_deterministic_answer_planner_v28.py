import json
from pathlib import Path

from tiff.trace_net_e2e_live_deterministic_answer_planner_v28 import (
    build_state,
    deterministic_mode_can_skip_llm,
    evaluate_quality,
    infer_response_mode,
    run_live_query_v28,
)


def _adapter(path: Path) -> Path:
    rows = [
        {"page_id": "t_p_120_1176_p000003", "field_name": "covered_part_number", "normalized_value": "120-36833-001", "source_evidence_id": "doc-1"},
        {"page_id": "t_p_120_1176_p000003", "field_name": "covered_part_number", "normalized_value": "120-36833-003", "source_evidence_id": "doc-2"},
        {"page_id": "t_p_120_1176_p000003", "field_name": "covered_part_number", "normalized_value": "120-36833-503", "source_evidence_id": "doc-3"},
        {"page_id": "t_p_120_1176_p000005", "field_name": "manual_page_reference", "normalized_value": "25-21-00", "source_evidence_id": "doc-4"},
        {"page_id": "t_p_120_1176_p000027", "field_name": "ipl_text", "normalized_value": "ILLUSTRATED PARTS LIST", "source_evidence_id": "doc-5"},
        {"page_id": "t_p_120_1176_p000028", "field_name": "ipl_text", "normalized_value": "ILLUSTRATED PARTS LIST", "source_evidence_id": "doc-6"},
        {"page_id": "t_p_120_1176_p000027", "field_name": "ipl_text", "normalized_value": "i", "source_evidence_id": "doc-7"},
    ]
    p = path / "exact.json"
    p.write_text(json.dumps({"quality_status": "PASS", "exact_search_documents": rows}), encoding="utf-8")
    return p


def test_v28_exact_lookup_uses_deterministic_planner(tmp_path):
    state = build_state(_adapter(tmp_path), llm_mode="ollama", deterministic_mode="expanded")
    result = run_live_query_v28("Find part number 120-36833-503", state)
    assert result["response_mode"] == "exact_single_value"
    assert result["deterministic_answer_planner_used"] is True
    assert result["llm_status"] == "LLM_SKIPPED_DETERMINISTIC_PLANNER"
    assert result["llm_called"] is False
    assert result["final_gate_status"] == "LIVE_ORCHESTRATOR_FINAL_GATE_PASS"
    assert "120-36833-503" in result["final_answer"]


def test_v28_missing_exact_value_audit_only_without_llm(tmp_path):
    state = build_state(_adapter(tmp_path), llm_mode="ollama", deterministic_mode="expanded")
    result = run_live_query_v28("Where is manual reference 99-99-99 used?", state)
    assert result["response_mode"] == "exact_missing_value"
    assert result["deterministic_answer_planner_used"] is True
    assert result["final_gate_status"] == "LIVE_ORCHESTRATOR_AUDIT_ONLY"
    assert result["retrieval"]["total_match_count"] == 0
    assert "did not find" in result["final_answer"]


def test_v28_field_listing_skips_llm_for_broad_covered_part_query(tmp_path):
    state = build_state(_adapter(tmp_path), llm_mode="ollama", deterministic_mode="expanded")
    result = run_live_query_v28("What maintenance manual pages mention covered part numbers?", state)
    assert result["response_mode"] in {"field_listing", "capped_listing"}
    assert result["deterministic_answer_planner_used"] is True
    assert result["llm_called"] is False
    assert result["final_gate_status"] == "LIVE_ORCHESTRATOR_FINAL_GATE_PASS"
    assert "covered part numbers" in result["final_answer"]


def test_v28_drilldown_request_skips_llm_and_returns_grouping(tmp_path):
    state = build_state(_adapter(tmp_path), llm_mode="ollama", deterministic_mode="expanded")
    result = run_live_query_v28("Drill down covered part numbers by page", state)
    assert result["response_mode"] == "drilldown_request"
    assert result["deterministic_answer_planner_used"] is True
    assert result["llm_called"] is False
    assert result["drilldown_axis"] == "page"
    assert "drill-down by page" in result["final_answer"]


def test_v28_exact_mode_keeps_broad_query_llm_eligible(tmp_path):
    state = build_state(_adapter(tmp_path), llm_mode="simulate", deterministic_mode="exact")
    result = run_live_query_v28("What maintenance manual pages mention covered part numbers?", state)
    assert result["response_mode"] in {"field_listing", "capped_listing"}
    assert result["deterministic_answer_planner_used"] is False
    assert result["llm_status"] == "LLM_SIMULATED"


def test_v28_build_state_quality_with_expanded_samples(tmp_path):
    state = build_state(
        _adapter(tmp_path),
        llm_mode="simulate",
        deterministic_mode="expanded",
        include_standard_demo_queries=True,
    )
    quality_status, checks = evaluate_quality(
        state,
        min_exact_search_documents=7,
        min_endpoint_routes=4,
        min_sample_queries=8,
        min_sample_successes=8,
        min_stage_timing_records=8,
        min_deterministic_answer_samples=8,
        min_drilldown_samples=1,
        max_sample_llm_calls=0,
        require_no_answer_permission=True,
    )
    assert quality_status == "PASS", checks
    assert state["deterministic_answer_sample_count"] == 8
    assert state["drilldown_sample_count"] >= 1


def test_deterministic_mode_can_skip_llm_rules():
    used, reason = deterministic_mode_can_skip_llm("drilldown_request", deterministic_mode="expanded")
    assert used is True
    assert "drilldown" in reason
    used, reason = deterministic_mode_can_skip_llm("drilldown_request", deterministic_mode="exact")
    assert used is False
    assert reason == "deterministic_exact_only_requires_llm"
    used, reason = deterministic_mode_can_skip_llm("relationship_or_synthesis_needs_llm", deterministic_mode="expanded")
    assert used is False
    assert reason == "relationship_or_synthesis_requires_llm"


def test_v28_output_polish_fixes_citation_spacing_and_joined_words(tmp_path):
    state = build_state(_adapter(tmp_path), llm_mode="ollama", deterministic_mode="expanded")
    result = run_live_query_v28("What maintenance manual pages mention covered part numbers?", state)
    text = result["final_answer"]
    assert "005[" not in text
    assert "doesnot" not in text
    assert "onlyand" not in text


def test_v28_exact_filter_preserves_raw_and_collapsed_metadata(tmp_path):
    rows = [
        {"page_id": "p1", "field_name": "manual_page_reference", "normalized_value": "25-21-00", "source_evidence_id": f"doc-{i}"}
        for i in range(4)
    ]
    rows.extend([
        {"page_id": "p2", "field_name": "manual_page_reference", "normalized_value": "99-99-99", "source_evidence_id": "noise-1"},
        {"page_id": "p3", "field_name": "covered_part_number", "normalized_value": "120-36833-001", "source_evidence_id": "noise-2"},
    ])
    p = tmp_path / "exact.json"
    p.write_text(json.dumps({"quality_status": "PASS", "exact_search_documents": rows}), encoding="utf-8")
    state = build_state(p, llm_mode="ollama", deterministic_mode="expanded")
    result = run_live_query_v28("Where is manual reference 25-21-00 used?", state)
    retrieval = result["retrieval"]
    assert retrieval["raw_candidate_match_count"] >= retrieval["target_occurrence_count"]
    assert retrieval["target_unique_match_count"] == 1
    assert retrieval["target_occurrence_count"] == 4
    assert retrieval["collapsed_duplicate_record_count"] == 3
    assert "collapsed from 3 repeated source records" in result["final_answer"]
