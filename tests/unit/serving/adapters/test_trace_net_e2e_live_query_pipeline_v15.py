from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_e2e_live_query_pipeline_v15 import (
    PIPELINE_STAGE_NAMES,
    ask_live_query,
    build_live_query_pipeline_manifest,
    build_pipeline_record,
    build_pipeline_stages,
    make_chat_completion,
    write_report_files,
)


def sample_v14_endpoint():
    answer1 = {
        "webui_final_answer_id": "webui_final_answer_v14_0001",
        "webui_final_answer_status": "WEBUI_FINAL_ANSWER_READY",
        "user_query": "Find part number 120-36834-509",
        "normalized_query": "find part number 120 36834 509",
        "query_intent": "covered_part_number",
        "message": {
            "role": "assistant",
            "content": "TRACE-Net found part number 120-36834-509 as a covered part number on page t_p_120_1176_p000003 [1]. The evidence is sufficient to confirm the listing, but not enough to describe what the part physically is.",
        },
        "citations": [
            {"citation_marker": "[1]", "page_id": "t_p_120_1176_p000003", "field_name": "covered_part_number", "normalized_value": "120-36834-509"},
            {"citation_marker": "[2]", "page_id": "t_p_120_1176_p000003", "field_name": "covered_part_number", "normalized_value": "120-36833-001"},
            {"citation_marker": "[3]", "page_id": "t_p_120_1176_p000003", "field_name": "covered_part_number", "normalized_value": "120-36833-003"},
        ],
        "page_ids": ["t_p_120_1176_p000003"],
        "field_names": ["covered_part_number"],
        "limitations": ["The evidence confirms listing but not physical description."],
        "ready_for_webui_endpoint": True,
    }
    answer2 = {
        "webui_final_answer_id": "webui_final_answer_v14_0002",
        "webui_final_answer_status": "WEBUI_FINAL_ANSWER_READY",
        "user_query": "Search table text MAINTENANCE MANUAL WITH",
        "normalized_query": "search table text maintenance manual with",
        "query_intent": "table_text",
        "message": {"role": "assistant", "content": "TRACE-Net found the table text 'MAINTENANCE MANUAL WITH' on page t_p_120_1176_p000027 [1], page t_p_120_1176_p000028 [2], and page t_p_120_1176_p000029 [3]."},
        "citations": [
            {"citation_marker": "[1]", "page_id": "t_p_120_1176_p000027", "field_name": "ipl_text", "normalized_value": "MAINTENANCE MANUAL WITH"},
            {"citation_marker": "[2]", "page_id": "t_p_120_1176_p000028", "field_name": "ipl_text", "normalized_value": "MAINTENANCE MANUAL WITH"},
            {"citation_marker": "[3]", "page_id": "t_p_120_1176_p000029", "field_name": "ipl_text", "normalized_value": "MAINTENANCE MANUAL WITH"},
        ],
        "page_ids": ["t_p_120_1176_p000027", "t_p_120_1176_p000028", "t_p_120_1176_p000029"],
        "field_names": ["ipl_text"],
        "limitations": ["The evidence confirms occurrence only."],
        "ready_for_webui_endpoint": True,
    }
    return {
        "quality_status": "PASS",
        "model": "trace-net-e2e-webui-final-answer-endpoint-v14",
        "summary": {"ready_final_answer_count": 2, "total_citation_count": 6},
        "ready_final_answers": [answer1, answer2],
    }


def test_build_pipeline_stages_have_expected_names():
    stages = build_pipeline_stages({}, matched=True)
    assert [s["stage_name"] for s in stages] == PIPELINE_STAGE_NAMES
    assert stages[-1]["stage_status"] == "STAGE_READY_FOR_WEBUI"
    assert all(s["source_truth_mutation_allowed"] is False for s in stages)


def test_build_pipeline_record_from_final_answer():
    record = build_pipeline_record(sample_v14_endpoint()["ready_final_answers"][0], 1)
    assert record["live_query_pipeline_status"] == "LIVE_QUERY_PIPELINE_FINAL_GATED_READY"
    assert record["pipeline_stage_count"] == len(PIPELINE_STAGE_NAMES)
    assert record["citation_count"] == 3
    assert record["answer_permission"] is False
    assert "120-36834-509" in record["message"]["content"]


def test_build_manifest_passes_with_relaxed_counts():
    report = build_live_query_pipeline_manifest(
        sample_v14_endpoint(),
        min_final_answers=2,
        min_ready_pipeline_queries=2,
        min_total_pipeline_stages=18,
        min_total_citations=6,
    )
    assert report["quality_status"] == "PASS"
    assert report["e2e_live_query_pipeline_status"] == "E2E_LIVE_QUERY_PIPELINE_READY"
    assert report["summary"]["ready_pipeline_query_count"] == 2
    assert report["summary"]["total_pipeline_stage_count"] == 18
    assert report["base_url_open_webui_docker"].endswith(":8018/v1")


def test_build_manifest_fails_when_threshold_too_high():
    report = build_live_query_pipeline_manifest(sample_v14_endpoint(), min_final_answers=10)
    assert report["quality_status"] == "FAIL"


def test_ask_live_query_exact_match_returns_final_gated_answer():
    state = build_live_query_pipeline_manifest(
        sample_v14_endpoint(),
        min_final_answers=2,
        min_ready_pipeline_queries=2,
        min_total_pipeline_stages=18,
        min_total_citations=6,
    )
    response = ask_live_query("Find part number 120-36834-509", state)
    assert response["matched_live_pipeline"] is True
    assert response["response_status"] == "LIVE_QUERY_PIPELINE_FINAL_GATED_ANSWER_READY"
    assert response["pipeline_stage_count"] == len(PIPELINE_STAGE_NAMES)
    assert response["safety"]["response_is_live_pipeline_orchestrated"] is True
    assert "120-36834-509" in response["message"]["content"]


def test_ask_live_query_unknown_returns_audit_limitation():
    state = build_live_query_pipeline_manifest(
        sample_v14_endpoint(),
        min_final_answers=2,
        min_ready_pipeline_queries=2,
        min_total_pipeline_stages=18,
        min_total_citations=6,
    )
    response = ask_live_query("Completely unknown query", state)
    assert response["matched_live_pipeline"] is False
    assert response["response_status"] == "LIVE_QUERY_PIPELINE_REQUIRES_DYNAMIC_EXECUTION"
    assert response["citations"] == []
    assert response["pipeline_trace"][-1]["stage_status"] == "STAGE_BLOCKED_NO_FINAL_GATED_ANSWER"


def test_make_chat_completion_includes_citations_and_trace():
    state = build_live_query_pipeline_manifest(
        sample_v14_endpoint(),
        min_final_answers=2,
        min_ready_pipeline_queries=2,
        min_total_pipeline_stages=18,
        min_total_citations=6,
    )
    ask = ask_live_query("Search table text MAINTENANCE MANUAL WITH", state)
    chat = make_chat_completion("Search table text MAINTENANCE MANUAL WITH", ask, model="trace-net-test")
    content = chat["choices"][0]["message"]["content"]
    assert "Citations:" in content
    assert "page=t_p_120_1176_p000027" in content
    assert chat["trace_net"]["matched_live_pipeline"] is True
    assert chat["trace_net"]["pipeline_stage_count"] == len(PIPELINE_STAGE_NAMES)


def test_write_report_files(tmp_path: Path):
    report = build_live_query_pipeline_manifest(
        sample_v14_endpoint(),
        min_final_answers=2,
        min_ready_pipeline_queries=2,
        min_total_pipeline_stages=18,
        min_total_citations=6,
    )
    paths = write_report_files(report, tmp_path)
    assert Path(paths["report_path"]).exists()
    assert Path(paths["pipelines_jsonl_path"]).exists()
    assert Path(paths["inspect_md_path"]).exists()
    data = json.loads(Path(paths["report_path"]).read_text(encoding="utf-8"))
    assert data["quality_status"] == "PASS"
