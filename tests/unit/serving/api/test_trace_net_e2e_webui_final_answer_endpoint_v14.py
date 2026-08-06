from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_e2e_webui_final_answer_endpoint_v14 import (
    ask_final_answer,
    build_endpoint_manifest,
    make_chat_completion,
    normalize_final_answer_record,
    write_report_files,
)


def sample_final_gate():
    return {
        "quality_status": "PASS",
        "final_answer_gates": [
            {
                "final_answer_gate_id": "final_answer_gate_v13_0001",
                "final_answer_gate_status": "FINAL_ANSWER_GATE_PASS",
                "final_answer_ready_for_webui": True,
                "user_query": "Find part number 120-36834-509",
                "query_intent": "covered_part_number",
                "final_answer_text": "TRACE-Net found part number 120-36834-509 as a covered part number on page t_p_120_1176_p000003 [1]. The evidence is sufficient to confirm the listing, but not enough to describe what the part physically is.",
                "citations": [
                    {
                        "citation_marker": "[1]",
                        "field_name": "covered_part_number",
                        "normalized_value": "120-36834-509",
                        "page_id": "t_p_120_1176_p000003",
                        "citation_ready": True,
                        "source_trace_ready": True,
                        "answer_authority": "source_truth_evidence_only",
                    },
                    {
                        "citation_marker": "[2]",
                        "field_name": "covered_part_number",
                        "normalized_value": "120-36833-001",
                        "page_id": "t_p_120_1176_p000003",
                        "citation_ready": True,
                        "source_trace_ready": True,
                        "answer_authority": "source_truth_evidence_only",
                    },
                    {
                        "citation_marker": "[3]",
                        "field_name": "covered_part_number",
                        "normalized_value": "120-36833-003",
                        "page_id": "t_p_120_1176_p000003",
                        "citation_ready": True,
                        "source_trace_ready": True,
                        "answer_authority": "source_truth_evidence_only",
                    },
                ],
                "limitations": ["The evidence confirms listing but not physical description."],
                "unsupported_claim_count": 0,
                "graph_summary_proof_violation_count": 0,
            },
            {
                "final_answer_gate_id": "final_answer_gate_v13_0002",
                "final_answer_gate_status": "FINAL_ANSWER_GATE_PASS",
                "final_answer_ready_for_webui": True,
                "user_query": "Search table text MAINTENANCE MANUAL WITH",
                "query_intent": "table_text",
                "final_answer_text": "TRACE-Net found the table text 'MAINTENANCE MANUAL WITH' on page t_p_120_1176_p000027 [1], page t_p_120_1176_p000028 [2], and page t_p_120_1176_p000029 [3].",
                "citations": [
                    {"citation_marker": "[1]", "field_name": "ipl_text", "normalized_value": "MAINTENANCE MANUAL WITH", "page_id": "t_p_120_1176_p000027"},
                    {"citation_marker": "[2]", "field_name": "ipl_text", "normalized_value": "MAINTENANCE MANUAL WITH", "page_id": "t_p_120_1176_p000028"},
                    {"citation_marker": "[3]", "field_name": "ipl_text", "normalized_value": "MAINTENANCE MANUAL WITH", "page_id": "t_p_120_1176_p000029"},
                ],
                "unsupported_claim_count": 0,
                "graph_summary_proof_violation_count": 0,
            },
        ],
    }


def test_normalize_final_answer_record_is_ready():
    record = sample_final_gate()["final_answer_gates"][0]
    normalized = normalize_final_answer_record(record, 1)
    assert normalized is not None
    assert normalized["ready_for_webui_endpoint"] is True
    assert normalized["citation_count"] == 3
    assert normalized["answer_permission"] is False
    assert normalized["source_truth_mutation_allowed"] is False
    assert "t_p_120_1176_p000003" in normalized["page_ids"]


def test_build_endpoint_manifest_passes_with_relaxed_counts():
    report = build_endpoint_manifest(
        sample_final_gate(),
        min_final_answers=2,
        min_ready_final_answers=2,
        min_total_citations=6,
        min_endpoint_routes=4,
        require_no_answer_permission=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["e2e_webui_final_answer_endpoint_status"] == "E2E_WEBUI_FINAL_ANSWER_ENDPOINT_READY"
    assert report["summary"]["ready_final_answer_count"] == 2
    assert report["summary"]["total_citation_count"] == 6
    assert report["base_url_open_webui_docker"].endswith(":8017/v1")


def test_ask_final_answer_exact_match_returns_final_gated_response():
    state = build_endpoint_manifest(sample_final_gate(), min_final_answers=2, min_ready_final_answers=2, min_total_citations=6)
    response = ask_final_answer("Find part number 120-36834-509", state)
    assert response["matched_final_answer"] is True
    assert response["response_status"] == "FINAL_GATED_ANSWER_READY"
    assert "120-36834-509" in response["message"]["content"]
    assert response["safety"]["response_is_final_gated"] is True
    assert response["safety"]["source_truth_mutation_allowed"] is False


def test_ask_final_answer_unknown_query_returns_audit_limitation():
    state = build_endpoint_manifest(sample_final_gate(), min_final_answers=2, min_ready_final_answers=2, min_total_citations=6)
    response = ask_final_answer("Unknown part ABC-DOES-NOT-EXIST", state)
    assert response["matched_final_answer"] is False
    assert response["response_status"] == "FINAL_GATED_ANSWER_NOT_FOUND"
    assert "no final-gated" in response["message"]["content"]


def test_make_chat_completion_includes_citations():
    state = build_endpoint_manifest(sample_final_gate(), min_final_answers=2, min_ready_final_answers=2, min_total_citations=6)
    ask = ask_final_answer("Search table text MAINTENANCE MANUAL WITH", state)
    chat = make_chat_completion("Search table text MAINTENANCE MANUAL WITH", ask, model="trace-net-test")
    content = chat["choices"][0]["message"]["content"]
    assert "MAINTENANCE MANUAL WITH" in content
    assert "Citations:" in content
    assert "page=t_p_120_1176_p000027" in content
    assert chat["trace_net"]["matched_final_answer"] is True


def test_write_report_files(tmp_path: Path):
    report = build_endpoint_manifest(sample_final_gate(), min_final_answers=2, min_ready_final_answers=2, min_total_citations=6)
    paths = write_report_files(report, tmp_path)
    assert Path(paths["report_path"]).exists()
    assert Path(paths["responses_jsonl_path"]).exists()
    assert Path(paths["inspect_md_path"]).exists()
    data = json.loads(Path(paths["report_path"]).read_text(encoding="utf-8"))
    assert data["quality_status"] == "PASS"
