
import json

from tiff.trace_net_engineering_gemma_draft_retry_prompt_v1 import check_engineering_gemma_draft_retry_prompt_quality


def test_quality_flags_prompt_too_large(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "source_final_gate_quality_status": "PASS",
            "source_draft_packet_quality_status": "PASS",
            "retry_prompt_record_count": 1,
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
            "total_message_character_count": 9999,
        },
        "records": [
            {"provider": "ollama", "ollama_think": False, "prompt_style": "micro", "request_payload": {"think": False}}
        ],
    }), encoding="utf-8")
    result = check_engineering_gemma_draft_retry_prompt_quality(
        report_path=path,
        max_total_message_chars=7000,
    )
    assert result["quality_status"] == "FAIL"


def test_quality_flags_wrong_prompt_style(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "source_final_gate_quality_status": "PASS",
            "source_draft_packet_quality_status": "PASS",
            "retry_prompt_record_count": 1,
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
            "total_message_character_count": 1000,
        },
        "records": [
            {"provider": "ollama", "ollama_think": False, "prompt_style": "compact_json", "request_payload": {"think": False}}
        ],
    }), encoding="utf-8")
    result = check_engineering_gemma_draft_retry_prompt_quality(
        report_path=path,
        require_prompt_style="micro",
    )
    assert result["quality_status"] == "FAIL"


def test_quality_flags_answer_permission(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "source_final_gate_quality_status": "PASS",
            "source_draft_packet_quality_status": "PASS",
            "retry_prompt_record_count": 1,
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
            "total_message_character_count": 1000,
        }
    }), encoding="utf-8")
    result = check_engineering_gemma_draft_retry_prompt_quality(
        report_path=path,
        require_no_answer_permission=True,
    )
    assert result["quality_status"] == "FAIL"
