from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_e2e_live_dynamic_fallback_v16 import (
    ask_live_dynamic_fallback,
    build_dynamic_fallback_record,
    build_live_dynamic_fallback_manifest,
    classify_query,
    make_chat_completion,
    rank_exact_docs,
    write_report_files,
)


def sample_v15():
    return {
        "quality_status": "PASS",
        "model": "trace-net-e2e-live-query-pipeline-v15",
        "summary": {"ready_pipeline_query_count": 1},
        "ready_live_query_pipelines": [
            {
                "user_query": "Find part number 120-36834-509",
                "normalized_query": "find part number 120 36834 509",
                "query_intent": "covered_part_number",
                "message": {"role": "assistant", "content": "Existing final answer for 120-36834-509 [1]."},
                "citations": [{"citation_marker": "[1]", "page_id": "p003", "field_name": "covered_part_number", "normalized_value": "120-36834-509"}],
                "pipeline_stages": [],
                "pipeline_stage_count": 9,
                "page_ids": ["p003"],
                "field_names": ["covered_part_number"],
                "ready_for_webui": True,
            }
        ],
    }


def sample_exact():
    docs = [
        {"page_id": "p003", "field_name": "covered_part_number", "normalized_value": "120-36833-001", "search_text": "covered 120-36833-001", "answer_permission": False, "can_answer_directly": False, "can_prove_claims": False, "source_truth_mutation_allowed": False},
        {"page_id": "p003", "field_name": "covered_part_number", "normalized_value": "120-36833-003", "search_text": "covered 120-36833-003", "answer_permission": False, "can_answer_directly": False, "can_prove_claims": False, "source_truth_mutation_allowed": False},
        {"page_id": "p005", "field_name": "manual_page_reference", "normalized_value": "25-21-00", "search_text": "manual 25-21-00", "answer_permission": False, "can_answer_directly": False, "can_prove_claims": False, "source_truth_mutation_allowed": False},
        {"page_id": "p027", "field_name": "ipl_part_number", "normalized_value": "25-21-00", "search_text": "ipl 25-21-00", "answer_permission": False, "can_answer_directly": False, "can_prove_claims": False, "source_truth_mutation_allowed": False},
        {"page_id": "p027", "field_name": "ipl_text", "normalized_value": "MAINTENANCE MANUAL WITH", "search_text": "MAINTENANCE MANUAL WITH", "answer_permission": False, "can_answer_directly": False, "can_prove_claims": False, "source_truth_mutation_allowed": False},
    ]
    return {"quality_status": "PASS", "summary": {"table_exact_search_document_count": len(docs)}, "exact_search_documents": docs}


def test_classify_query_extracts_intent_and_value():
    assert classify_query("Find part number 120-36833-001") == ("covered_part_number", "120-36833-001")
    assert classify_query("Where is manual reference 25-21-00 used?") == ("manual_page_reference", "25-21-00")
    assert classify_query("Search table text MAINTENANCE MANUAL WITH") == ("table_text", "MAINTENANCE MANUAL WITH")


def test_rank_exact_docs_matches_new_part_number():
    intent, extracted, rows = rank_exact_docs("Find part number 120-36833-001", sample_exact()["exact_search_documents"])
    assert intent == "covered_part_number"
    assert extracted == "120-36833-001"
    assert rows[0]["normalized_value"] == "120-36833-001"


def test_dynamic_fallback_record_is_citation_backed():
    rec = build_dynamic_fallback_record("Find part number 120-36833-001", sample_exact()["exact_search_documents"], 1)
    assert rec["ready_for_webui"] is True
    assert rec["citation_count"] >= 1
    assert "120-36833-001" in rec["message"]["content"]
    assert "[1]" in rec["message"]["content"]
    assert rec["answer_permission"] is False


def test_manifest_passes_with_relaxed_counts():
    report = build_live_dynamic_fallback_manifest(
        sample_v15(),
        sample_exact(),
        min_existing_pipeline_queries=1,
        min_exact_search_documents=5,
        min_dynamic_fallback_probes=3,
        min_ready_dynamic_fallback_probes=3,
        min_total_citations=3,
    )
    assert report["quality_status"] == "PASS"
    assert report["e2e_live_dynamic_fallback_status"] == "E2E_LIVE_DYNAMIC_FALLBACK_READY"
    assert report["summary"]["ready_dynamic_fallback_probe_count"] >= 3


def test_existing_pipeline_wins_before_dynamic_fallback():
    state = build_live_dynamic_fallback_manifest(
        sample_v15(), sample_exact(), min_existing_pipeline_queries=1, min_exact_search_documents=5, min_total_citations=3
    )
    response = ask_live_dynamic_fallback("Find part number 120-36834-509", state)
    assert response["matched_existing_pipeline"] is True
    assert response["matched_dynamic_fallback"] is False


def test_unknown_new_exact_query_uses_dynamic_fallback():
    state = build_live_dynamic_fallback_manifest(
        sample_v15(), sample_exact(), min_existing_pipeline_queries=1, min_exact_search_documents=5, min_total_citations=3
    )
    response = ask_live_dynamic_fallback("Find part number 120-36833-001", state)
    assert response["matched_existing_pipeline"] is False
    assert response["matched_dynamic_fallback"] is True
    assert response["response_status"] == "LIVE_DYNAMIC_FALLBACK_FINAL_GATED_ANSWER_READY"
    assert "Citations:" in make_chat_completion("Find part number 120-36833-001", response)["choices"][0]["message"]["content"]


def test_no_match_returns_audit_only():
    state = build_live_dynamic_fallback_manifest(
        sample_v15(), sample_exact(), min_existing_pipeline_queries=1, min_exact_search_documents=5, min_total_citations=3
    )
    response = ask_live_dynamic_fallback("Who signed this manual?", state)
    assert response["matched_dynamic_fallback"] is False
    assert response["safety"]["response_is_final_gated"] is False


def test_write_report_files(tmp_path: Path):
    report = build_live_dynamic_fallback_manifest(
        sample_v15(), sample_exact(), min_existing_pipeline_queries=1, min_exact_search_documents=5, min_total_citations=3
    )
    paths = write_report_files(report, tmp_path)
    assert Path(paths["report_path"]).exists()
    assert Path(paths["probes_jsonl_path"]).exists()
    data = json.loads(Path(paths["report_path"]).read_text(encoding="utf-8"))
    assert data["quality_status"] == "PASS"
