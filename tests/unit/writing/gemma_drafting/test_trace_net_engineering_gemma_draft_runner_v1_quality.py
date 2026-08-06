
import json

from tiff.trace_net_engineering_gemma_draft_runner_v1 import check_engineering_gemma_draft_runner_quality


def test_quality_flags_final_answer_ready(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "source_adapter_quality_status": "PASS",
            "runner_record_count": 1,
            "request_sent_count": 1,
            "response_received_count": 1,
            "ready_for_final_gate_review_count": 1,
            "ready_for_final_answer_count": 1,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "retrieval_execution_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "llm_call_allowed_count": 1,
        }
    }), encoding="utf-8")
    result = check_engineering_gemma_draft_runner_quality(
        report_path=path,
        max_ready_for_final_answer=0,
    )
    assert result["quality_status"] == "FAIL"


def test_quality_flags_answer_permission(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "source_adapter_quality_status": "PASS",
            "runner_record_count": 1,
            "request_sent_count": 0,
            "response_received_count": 0,
            "ready_for_final_gate_review_count": 0,
            "ready_for_final_answer_count": 0,
            "unsafe_record_count": 0,
            "answer_permission_count": 1,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "retrieval_execution_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "llm_call_allowed_count": 0,
        }
    }), encoding="utf-8")
    result = check_engineering_gemma_draft_runner_quality(
        report_path=path,
        require_no_answer_permission=True,
    )
    assert result["quality_status"] == "FAIL"


def test_quality_flags_dry_run_sent_request(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "source_adapter_quality_status": "PASS",
            "runner_record_count": 1,
            "request_sent_count": 1,
            "response_received_count": 1,
            "ready_for_final_gate_review_count": 1,
            "ready_for_final_answer_count": 0,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "retrieval_execution_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "llm_call_allowed_count": 1,
        }
    }), encoding="utf-8")
    result = check_engineering_gemma_draft_runner_quality(
        report_path=path,
        require_dry_run_no_llm_calls=True,
    )
    assert result["quality_status"] == "FAIL"
