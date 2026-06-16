import json
from pathlib import Path

from tiff.trace_net_llm_graph_path_response_guard_v1 import (
    build_response_guard,
    build_response_prompt,
    score_response,
)


def sample_eval_payload():
    return {
        "quality_status": "PASS",
        "summary": {
            "query_record_count": 3,
            "graph_path_resolved_count": 3,
            "llm_graph_path_card_count": 3,
            "target_hit_at_k_rate": 1.0,
        },
        "query_records": [
            {
                "page_id": "t_p_120_1176_p000001",
                "page_number": 1,
                "blank_expected": False,
                "target_hit_at_k": True,
                "graph_path_resolved": True,
                "query_type": "page_source_context_graph_check",
                "semantic_retrieval_query": "revision history title block",
            },
            {
                "page_id": "t_p_120_1176_p000002",
                "page_number": 2,
                "blank_expected": True,
                "target_hit_at_k": True,
                "graph_path_resolved": True,
                "query_type": "blank_page_graph_check",
                "semantic_retrieval_query": "blank page",
            },
            {
                "page_id": "t_p_120_1176_p000003",
                "page_number": 3,
                "blank_expected": False,
                "target_hit_at_k": False,
                "evaluated": True,
                "graph_path_resolved": True,
                "query_type": "page_source_context_graph_check",
                "semantic_retrieval_query": "parts list",
            },
        ],
        "llm_graph_path_cards": [
            {
                "page_id": "t_p_120_1176_p000001",
                "page_number": 1,
                "graph_path_resolved": True,
                "llm_question": "Summarize page 1.",
                "llm_graph_path_prompt": "Target page: t_p_120_1176_p000001 Source package entry: 00000001.tif Page context summary: title and revision page",
            },
            {
                "page_id": "t_p_120_1176_p000002",
                "page_number": 2,
                "graph_path_resolved": True,
                "llm_question": "What is on page 2?",
                "llm_graph_path_prompt": "Target page: t_p_120_1176_p000002 Source package entry: 00000002.tif Page context summary: blank page",
            },
            {
                "page_id": "t_p_120_1176_p000003",
                "page_number": 3,
                "graph_path_resolved": True,
                "llm_question": "Summarize page 3.",
                "llm_graph_path_prompt": "Target page: t_p_120_1176_p000003 Source package entry: 00000003.tif Page context summary: parts list",
            },
        ],
    }


def test_score_response_accepts_source_bound_plain_text():
    record = {"page_id": "t_p_120_1176_p000002", "page_number": 2, "blank_expected": True}
    card = {"llm_graph_path_prompt": "Source package entry: 00000002.tif"}
    response = "Page t_p_120_1176_p000002 (00000002.tif) was resolved through the graph/source package path. This source-linked page is blank or empty."
    scored = score_response(record, card, response, True, None)
    assert scored["passed"] is True
    assert scored["blank_correct"] is True
    assert scored["target_page_id_anchored"] is True
    assert scored["source_identity_anchored"] is True


def test_score_response_rejects_retrieval_as_proof():
    record = {"page_id": "t_p_120_1176_p000001", "page_number": 1, "blank_expected": False}
    card = {"llm_graph_path_prompt": "Source package entry: 00000001.tif"}
    response = "Page t_p_120_1176_p000001 (00000001.tif) Qdrant proves this answer."
    scored = score_response(record, card, response, True, None)
    assert scored["passed"] is False
    assert "retrieval_as_proof" in scored["violations"]


def test_prompt_excludes_json_and_permissions():
    record = {"page_id": "t_p_120_1176_p000001", "page_number": 1, "blank_expected": False}
    card = {"llm_question": "Summarize page 1", "llm_graph_path_prompt": "Source package entry: 00000001.tif Page context summary: title block"}
    prompt = build_response_prompt(record, card)
    assert "Do not output JSON" in prompt
    assert "can_answer_directly" not in prompt
    assert "can_prove_claims" not in prompt
    assert "Page t_p_120_1176_p000001 (00000001.tif)" in prompt


def test_build_plan_only_report(tmp_path: Path):
    eval_path = tmp_path / "eval.json"
    eval_path.write_text(json.dumps(sample_eval_payload()), encoding="utf-8")
    out = tmp_path / "out"
    payload = build_response_guard(
        page_retrieval_large_eval_v2=eval_path,
        output_dir=out,
        sample_size=3,
        min_blank_cards_in_sample=1,
        min_miss_cards_in_sample=1,
        run_ollama=False,
        ollama_url="http://localhost:11434",
        ollama_model="gemma4:26b",
        ollama_timeout=1,
        ollama_retries=0,
        ollama_num_predict=50,
        ollama_num_ctx=2048,
        progress=False,
        thresholds={
            "min_sampled_records": 3,
            "min_evaluated_records": 0,
            "min_graph_path_bound": 3,
            "min_graph_path_anchored": 0,
            "min_target_page_id_anchored": 0,
            "min_source_identity_anchored": 0,
            "min_blank_correct": 0,
            "max_unsafe_responses": 0,
            "max_retrieval_as_proof": 0,
            "max_community_as_proof": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_eval_quality_pass": True,
            "require_no_answer_permission": True,
        },
    )
    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["sampled_record_count"] == 3
    assert payload["summary"]["evaluated_record_count"] == 0
    assert (out / "trace_net_llm_graph_path_response_guard_v1.json").exists()


def test_apply_source_anchor_prefix_turns_weak_model_text_into_guarded_anchor():
    from tiff.trace_net_llm_graph_path_response_guard_v1 import apply_source_anchor_prefix, score_response

    record = {"page_id": "t_p_120_1176_p000002", "page_number": 2, "blank_expected": True}
    card = {"llm_graph_path_prompt": "Source package entry: 00000002.tif"}
    weak_response = "It appears to be empty."
    guarded, applied = apply_source_anchor_prefix(record, card, weak_response, enabled=True)
    assert applied is True
    scored = score_response(record, card, guarded, True, None)
    assert scored["passed"] is True
    assert scored["graph_path_anchored"] is True
    assert scored["target_page_id_anchored"] is True
    assert scored["source_identity_anchored"] is True
    assert scored["blank_correct"] is True


def test_build_response_guard_with_source_anchor_prefix_reports_system_enforcement(tmp_path: Path):
    eval_path = tmp_path / "eval.json"
    eval_path.write_text(json.dumps(sample_eval_payload()), encoding="utf-8")
    out = tmp_path / "out"
    payload = build_response_guard(
        page_retrieval_large_eval_v2=eval_path,
        output_dir=out,
        sample_size=3,
        min_blank_cards_in_sample=1,
        min_miss_cards_in_sample=1,
        run_ollama=False,
        ollama_url="http://localhost:11434",
        ollama_model="gemma4:26b",
        ollama_timeout=1,
        ollama_retries=0,
        ollama_num_predict=50,
        ollama_num_ctx=2048,
        progress=False,
        thresholds={
            "min_sampled_records": 3,
            "min_evaluated_records": 0,
            "min_graph_path_bound": 3,
            "min_graph_path_anchored": 0,
            "min_target_page_id_anchored": 0,
            "min_source_identity_anchored": 0,
            "min_blank_correct": 0,
            "max_unsafe_responses": 0,
            "max_retrieval_as_proof": 0,
            "max_community_as_proof": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_eval_quality_pass": True,
            "require_no_answer_permission": True,
            "enforce_source_anchor_prefix": True,
        },
    )
    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["enforce_source_anchor_prefix"] is True
