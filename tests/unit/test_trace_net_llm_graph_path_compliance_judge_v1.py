import json
from pathlib import Path

from tiff.trace_net_llm_graph_path_compliance_judge_v1 import (
    Thresholds,
    build_compliance_judge,
    extract_json_object,
    judge_response,
    select_sample_cards,
)


def sample_eval_payload():
    cards = []
    records = []
    for i in range(1, 6):
        page_id = f"t_p_120_1176_p{i:06d}"
        blank = i == 2
        card = {
            "page_id": page_id,
            "page_number": i,
            "query_type": "blank_page_graph_check" if blank else "page_source_context_graph_check",
            "blank_expected": blank,
            "graph_path_resolved": True,
            "llm_question": f"Using graph path, locate page {i}.",
            "expected_answer_behavior": "LLM_MUST_FOLLOW_GRAPH_PATH_AND_STATE_PAGE_IS_BLANK_OR_EMPTY" if blank else "LLM_MUST_FOLLOW_GRAPH_PATH_AND_SUMMARIZE_SOURCE_LINKED_PAGE_ONLY",
            "llm_graph_path_prompt": f"Resolve page node page:{page_id}; follow Page -> SourceLink / Dublin Core source package entry.",
            "source_package_entry": {"trace_net:source_package_entry_name": f"{i:08d}.tif"},
        }
        cards.append(card)
        records.append({
            "page_id": page_id,
            "evaluated": True,
            "target_hit_at_k": i != 3,
            "blank_expected": blank,
        })
    return {
        "schema_version": "trace_net_page_retrieval_large_eval_v2",
        "status": "PAGE_RETRIEVAL_LARGE_EVAL_V2_BUILT",
        "quality_status": "PASS",
        "summary": {
            "query_record_count": 5,
            "graph_path_resolved_count": 5,
            "llm_graph_path_card_count": 5,
            "target_hit_at_k_rate": 0.8,
        },
        "llm_graph_path_cards": cards,
        "query_records": records,
    }


def test_select_sample_includes_blank_and_miss():
    payload = sample_eval_payload()
    records = {r["page_id"]: r for r in payload["query_records"]}
    selected = select_sample_cards(payload["llm_graph_path_cards"], records, sample_size=4, min_blank_cards=1, min_miss_cards=1)
    ids = {c["page_id"] for c in selected}
    assert "t_p_120_1176_p000002" in ids
    assert "t_p_120_1176_p000003" in ids
    assert len(selected) == 4


def test_extract_json_object_from_wrapped_text():
    parsed, error = extract_json_object('prefix {"graph_path_followed": true, "target_page_id": "x"} suffix')
    assert error is None
    assert parsed["graph_path_followed"] is True


def test_judge_response_good_blank_json():
    card = sample_eval_payload()["llm_graph_path_cards"][1]
    raw = json.dumps({
        "target_page_id": "t_p_120_1176_p000002",
        "target_page_id_seen": True,
        "graph_path_followed": True,
        "source_identity_confirmed": True,
        "answer": "The source-linked page is blank.",
        "blank_page_statement": "Page t_p_120_1176_p000002 is blank/empty.",
        "needs_review": False,
        "used_retrieval_as_proof": False,
        "used_leiden_or_community_as_proof": False,
        "source_truth_mutation_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
    })
    parsed, error = extract_json_object(raw)
    judged = judge_response(card, raw, parsed, error)
    assert judged["passed"] is True
    assert judged["blank_correct"] is True
    assert judged["graph_path_followed"] is True
    assert judged["target_page_id_mentioned"] is True


def test_judge_response_flags_retrieval_as_proof():
    card = sample_eval_payload()["llm_graph_path_cards"][0]
    raw = json.dumps({
        "target_page_id": "t_p_120_1176_p000001",
        "graph_path_followed": True,
        "source_identity_confirmed": True,
        "answer": "Retrieval proves this answer.",
        "used_retrieval_as_proof": True,
        "used_leiden_or_community_as_proof": False,
        "source_truth_mutation_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
    })
    parsed, error = extract_json_object(raw)
    judged = judge_response(card, raw, parsed, error)
    assert judged["passed"] is False
    assert "retrieval_used_as_proof" in judged["violations"]


def test_build_plan_only_report(tmp_path):
    eval_path = tmp_path / "eval.json"
    eval_path.write_text(json.dumps(sample_eval_payload()), encoding="utf-8")
    out_dir = tmp_path / "out"
    report = build_compliance_judge(
        eval_report_path=eval_path,
        output_dir=out_dir,
        sample_size=4,
        min_blank_cards=1,
        min_miss_cards=1,
        run_ollama=False,
        ollama_url="http://localhost:11434",
        ollama_model="gemma4:26b",
        ollama_timeout=5,
        quality=True,
        thresholds=Thresholds(
            min_sampled_records=4,
            min_evaluated_records=0,
            require_eval_quality_pass=True,
            require_no_answer_permission=True,
        ),
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["sampled_record_count"] == 4
    assert report["summary"]["evaluated_record_count"] == 0
    assert (out_dir / "trace_net_llm_graph_path_compliance_judge_v1.json").exists()
    assert (out_dir / "trace_net_llm_graph_path_compliance_judge_v1_records.jsonl").exists()


def test_text_fallback_accepts_source_anchored_non_json_response():
    card = sample_eval_payload()["llm_graph_path_cards"][0]
    raw = (
        "Using the approved graph path, I resolved page t_p_120_1176_p000001 "
        "through the Dublin Core source package entry 00000001.tif and confirmed the source identity. "
        "The source-linked page contains the title block and revision history."
    )
    parsed, error = extract_json_object(raw)
    judged = judge_response(card, raw, parsed, error, allow_text_fallback=True)
    assert judged["passed"] is True
    assert judged["json_format_valid"] is False
    assert judged["text_fallback_used"] is True
    assert judged["malformed_json"] is False
    assert judged["graph_path_followed"] is True
    assert judged["target_page_id_mentioned"] is True
