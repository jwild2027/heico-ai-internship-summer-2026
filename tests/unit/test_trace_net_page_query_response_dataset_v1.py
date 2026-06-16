import json
from pathlib import Path

from tiff.trace_net_page_query_response_dataset_v1 import (
    build_page_query_response_records,
    build_dataset,
    check_dataset_quality,
    extract_context_summary_from_prompt,
)


def sample_eval_payload():
    return {
        "status": "PAGE_RETRIEVAL_LARGE_EVAL_V2_BUILT",
        "quality_status": "PASS",
        "summary": {
            "query_record_count": 2,
            "evaluated_record_count": 2,
            "context_v2_query_count": 2,
            "graph_path_resolved_count": 2,
            "target_hit_at_k_rate": 1.0,
        },
        "query_records": [
            {
                "page_id": "t_p_120_1176_p000001",
                "page_number": 1,
                "blank_expected": False,
                "graph_path_resolved": True,
                "evaluated": True,
                "target_hit_at_k": True,
                "target_rank": 1,
                "top_hits": [{"rank": 1, "page_id": "t_p_120_1176_p000001", "score": 0.9}],
            },
            {
                "page_id": "t_p_120_1176_p000002",
                "page_number": 2,
                "blank_expected": True,
                "graph_path_resolved": True,
                "evaluated": True,
                "target_hit_at_k": True,
                "target_rank": 2,
                "blank_detection": {"blank_by_profile": True},
                "top_hits": [{"rank": 2, "page_id": "t_p_120_1176_p000002", "score": 0.8}],
            },
        ],
        "llm_graph_path_cards": [
            {
                "page_id": "t_p_120_1176_p000001",
                "page_number": 1,
                "graph_path_resolved": True,
                "llm_question": "Using the TRACE-Net graph path, locate page 1 and summarize it.",
                "llm_graph_path_prompt": "Target page: t_p_120_1176_p000001 Source package entry: 00000001.tif Page context summary: This page contains the title block and revision history. Retrieval cues: revision; title block",
            },
            {
                "page_id": "t_p_120_1176_p000002",
                "page_number": 2,
                "graph_path_resolved": True,
                "llm_question": "Using the TRACE-Net graph path, locate page 2. If blank, say blank.",
                "llm_graph_path_prompt": "Target page: t_p_120_1176_p000002 Source package entry: 00000002.tif Page context summary: Page 2 is blank. Retrieval cues: blank; empty",
            },
        ],
    }


def sample_profiles_payload():
    return {
        "page_profiles": [
            {"page_id": "t_p_120_1176_p000001", "role": "front_matter"},
            {"page_id": "t_p_120_1176_p000002", "role": "blank"},
        ]
    }


def test_extract_context_summary_from_prompt():
    prompt = "Page context summary: This is a title page. Retrieval cues: title"
    assert extract_context_summary_from_prompt(prompt) == "This is a title page."


def test_build_page_query_response_records_blank_and_source_anchor():
    records = build_page_query_response_records(sample_eval_payload(), sample_profiles_payload(), first_pages=2)
    assert len(records) == 2
    assert records[0]["page_id"] == "t_p_120_1176_p000001"
    assert "00000001.tif" in records[0]["response"]
    blank = records[1]
    assert blank["blank_expected"] is True
    assert "blank" in blank["response"].lower()
    assert blank["safety_contract"]["can_answer_directly"] is False
    assert blank["safety_contract"]["can_prove_claims"] is False


def test_build_dataset_writes_outputs(tmp_path):
    eval_path = tmp_path / "eval.json"
    profiles_path = tmp_path / "profiles.json"
    out_dir = tmp_path / "out"
    eval_path.write_text(json.dumps(sample_eval_payload()), encoding="utf-8")
    profiles_path.write_text(json.dumps(sample_profiles_payload()), encoding="utf-8")

    payload = build_dataset(
        page_retrieval_large_eval_v2=eval_path,
        profiles_path=profiles_path,
        output_dir=out_dir,
        first_pages=2,
        manual_label="Manual",
        thresholds={
            "min_records": 2,
            "min_responses": 2,
            "min_blank_responses": 1,
            "min_graph_path_resolved": 2,
            "min_source_identity_resolved": 2,
            "min_qdrant_evaluated": 2,
            "max_unsafe_responses": 0,
            "max_answer_capable_responses": 0,
            "max_claim_proof_responses": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_eval_quality_pass": True,
            "require_no_answer_permission": True,
        },
    )
    assert payload["quality_status"] == "PASS"
    assert (out_dir / "trace_net_page_query_response_dataset_v1.json").exists()
    assert (out_dir / "trace_net_page_query_response_dataset_v1_records.jsonl").exists()
    assert (out_dir / "trace_net_page_query_response_dataset_v1_responses.jsonl").exists()

    checked = check_dataset_quality(
        out_dir / "trace_net_page_query_response_dataset_v1.json",
        {
            "min_records": 2,
            "min_responses": 2,
            "min_blank_responses": 1,
            "min_graph_path_resolved": 2,
            "min_source_identity_resolved": 2,
            "min_qdrant_evaluated": 2,
            "max_unsafe_responses": 0,
            "max_answer_capable_responses": 0,
            "max_claim_proof_responses": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_eval_quality_pass": True,
            "require_no_answer_permission": True,
        },
    )
    assert checked["quality_status"] == "PASS"
