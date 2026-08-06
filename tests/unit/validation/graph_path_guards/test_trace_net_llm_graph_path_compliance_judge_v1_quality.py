import json
from pathlib import Path

from tiff.trace_net_llm_graph_path_compliance_judge_v1 import Thresholds, check_compliance_quality


def test_quality_passes_for_safe_evaluated_report(tmp_path):
    report = {
        "schema_version": "trace_net_llm_graph_path_compliance_judge_v1",
        "status": "LLM_GRAPH_PATH_COMPLIANCE_JUDGE_BUILT",
        "quality_status": "NOT_RUN",
        "summary": {
            "source_eval_quality_status": "PASS",
            "sampled_record_count": 2,
            "evaluated_record_count": 2,
            "graph_path_followed_count": 2,
            "target_page_id_mentioned_count": 2,
            "source_identity_confirmed_count": 2,
            "blank_correct_count": 1,
            "malformed_json_response_count": 0,
            "unsafe_response_count": 0,
            "retrieval_as_proof_count": 0,
            "community_as_proof_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
    }
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    checked = check_compliance_quality(
        path,
        Thresholds(
            min_sampled_records=2,
            min_evaluated_records=2,
            min_graph_path_followed=2,
            min_target_page_mentioned=2,
            min_source_identity_confirmed=2,
            min_blank_correct=1,
            max_malformed_responses=0,
            max_unsafe_responses=0,
            require_eval_quality_pass=True,
            require_no_answer_permission=True,
        ),
        write_json_report=True,
    )
    assert checked["quality_status"] == "PASS"
    assert (tmp_path / "trace_net_llm_graph_path_compliance_judge_v1_quality.json").exists()


def test_quality_fails_for_malformed_response(tmp_path):
    report = {
        "schema_version": "trace_net_llm_graph_path_compliance_judge_v1",
        "status": "LLM_GRAPH_PATH_COMPLIANCE_JUDGE_BUILT",
        "summary": {
            "source_eval_quality_status": "PASS",
            "sampled_record_count": 1,
            "evaluated_record_count": 1,
            "graph_path_followed_count": 0,
            "target_page_id_mentioned_count": 0,
            "source_identity_confirmed_count": 0,
            "blank_correct_count": 0,
            "malformed_json_response_count": 1,
            "unsafe_response_count": 0,
            "retrieval_as_proof_count": 0,
            "community_as_proof_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
    }
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    checked = check_compliance_quality(
        path,
        Thresholds(min_sampled_records=1, min_evaluated_records=1, max_malformed_responses=0),
    )
    assert checked["quality_status"] == "FAIL"
