
import json

from tiff.trace_net_engineering_question_orchestrator_v1 import check_engineering_question_orchestrator_quality


def test_quality_flags_answer_permission(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "source_final_gate_quality_status": "PASS",
            "source_runner_quality_status": "PASS",
            "matched_question_count": 1,
            "manual_review_ready_response_count": 1,
            "response_text_char_count": 500,
            "ready_for_final_answer_count": 0,
            "unsafe_record_count": 0,
            "answer_permission_count": 1,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "llm_call_allowed_count": 0,
            "retrieval_execution_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
        }
    }), encoding="utf-8")
    result = check_engineering_question_orchestrator_quality(
        report_path=path,
        require_no_answer_permission=True,
    )
    assert result["quality_status"] == "FAIL"


def test_quality_flags_not_enough_response_chars(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "source_final_gate_quality_status": "PASS",
            "source_runner_quality_status": "PASS",
            "matched_question_count": 1,
            "manual_review_ready_response_count": 1,
            "response_text_char_count": 5,
            "ready_for_final_answer_count": 0,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "llm_call_allowed_count": 0,
            "retrieval_execution_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
        }
    }), encoding="utf-8")
    result = check_engineering_question_orchestrator_quality(
        report_path=path,
        min_response_chars=300,
    )
    assert result["quality_status"] == "FAIL"
