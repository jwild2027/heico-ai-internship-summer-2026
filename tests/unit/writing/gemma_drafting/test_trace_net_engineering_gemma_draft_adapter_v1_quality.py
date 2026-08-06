
import json

from tiff.trace_net_engineering_gemma_draft_adapter_v1 import check_engineering_gemma_draft_adapter_quality


def test_quality_flags_think_true_when_false_required(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "source_draft_packet_quality_status": "PASS",
            "adapter_record_count": 1,
            "request_payload_written_count": 1,
            "request_sent_count": 0,
            "response_received_count": 0,
            "ready_for_final_answer_count": 0,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "llm_call_allowed_count": 0,
            "retrieval_execution_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
        "records": [
            {
                "provider": "ollama",
                "ollama_think": True,
                "request_payload": {"think": True},
            }
        ],
    }), encoding="utf-8")
    result = check_engineering_gemma_draft_adapter_quality(
        report_path=path,
        require_ollama_think_false=True,
    )
    assert result["quality_status"] == "FAIL"


def test_quality_flags_sent_request(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "source_draft_packet_quality_status": "PASS",
            "adapter_record_count": 1,
            "request_payload_written_count": 1,
            "request_sent_count": 1,
            "response_received_count": 0,
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
    result = check_engineering_gemma_draft_adapter_quality(
        report_path=path,
        max_request_sent=0,
        require_no_llm_calls=True,
    )
    assert result["quality_status"] == "FAIL"


def test_quality_flags_answer_permission(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "source_draft_packet_quality_status": "PASS",
            "adapter_record_count": 1,
            "request_payload_written_count": 1,
            "request_sent_count": 0,
            "response_received_count": 0,
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
    result = check_engineering_gemma_draft_adapter_quality(
        report_path=path,
        require_no_answer_permission=True,
    )
    assert result["quality_status"] == "FAIL"
