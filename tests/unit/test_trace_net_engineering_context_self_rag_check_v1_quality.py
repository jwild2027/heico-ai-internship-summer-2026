
import json

from tiff.trace_net_engineering_context_self_rag_check_v1 import check_engineering_context_self_rag_check_quality


def test_quality_flags_answer_permission(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "source_context_pack_builder_quality_status": "PASS",
            "self_rag_record_count": 1,
            "ready_for_gemma_draft_count": 1,
            "crag_retry_required_count": 0,
            "unsafe_record_count": 0,
            "answer_permission_count": 1,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "llm_call_allowed_count": 0,
            "retrieval_execution_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
        }
    }), encoding="utf-8")
    result = check_engineering_context_self_rag_check_quality(
        report_path=path,
        require_no_answer_permission=True,
    )
    assert result["quality_status"] == "FAIL"


def test_quality_flags_llm_calls(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "source_context_pack_builder_quality_status": "PASS",
            "self_rag_record_count": 1,
            "ready_for_gemma_draft_count": 1,
            "crag_retry_required_count": 0,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "llm_call_allowed_count": 1,
            "retrieval_execution_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
        }
    }), encoding="utf-8")
    result = check_engineering_context_self_rag_check_quality(
        report_path=path,
        require_no_llm_calls=True,
    )
    assert result["quality_status"] == "FAIL"
