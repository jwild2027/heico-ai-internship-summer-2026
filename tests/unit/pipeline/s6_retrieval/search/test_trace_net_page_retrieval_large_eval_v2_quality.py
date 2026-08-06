from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_page_retrieval_large_eval_v2 import check_report_quality


def test_quality_check_passes_minimal_payload(tmp_path: Path):
    path = tmp_path / "report.json"
    payload = {
        "status": "PAGE_RETRIEVAL_LARGE_EVAL_V2_BUILT",
        "summary": {
            "query_record_count": 10,
            "blank_expected_count": 2,
            "context_v2_query_count": 10,
            "graph_path_resolved_count": 10,
            "graph_path_missing_count": 0,
            "llm_graph_path_card_count": 10,
            "target_hit_at_k_count": 5,
            "evaluated_record_count": 10,
            "answer_capable_payload_count": 0,
            "claim_proof_payload_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_load_statuses": {"profile_quality_status": "PASS"},
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    checked = check_report_quality(
        report_path=path,
        thresholds={
            "min_query_records": 10,
            "min_blank_queries": 1,
            "min_context_v2_queries": 10,
            "min_graph_path_resolved": 10,
            "min_llm_graph_path_cards": 10,
            "min_evaluated_records": 10,
            "min_target_hit_at_k": 1,
            "max_answer_capable_payloads": 0,
            "max_claim_proof_payloads": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_profile_quality_pass": True,
            "require_graph_paths": True,
            "require_no_answer_permission": True,
        },
        write_json_report=True,
    )
    assert checked["quality_status"] == "PASS"
    assert path.with_name("trace_net_page_retrieval_large_eval_v2_quality.json").exists()


def test_quality_check_fails_answer_permission(tmp_path: Path):
    path = tmp_path / "report.json"
    payload = {
        "status": "PAGE_RETRIEVAL_LARGE_EVAL_V2_BUILT",
        "summary": {
            "query_record_count": 1,
            "blank_expected_count": 0,
            "context_v2_query_count": 1,
            "graph_path_resolved_count": 1,
            "graph_path_missing_count": 0,
            "llm_graph_path_card_count": 1,
            "answer_capable_payload_count": 0,
            "claim_proof_payload_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "can_answer_directly_count": 1,
            "can_prove_claims_count": 0,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    checked = check_report_quality(
        report_path=path,
        thresholds={
            "min_query_records": 1,
            "max_answer_capable_payloads": 0,
            "max_claim_proof_payloads": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_no_answer_permission": True,
        },
    )
    assert checked["quality_status"] == "FAIL"
