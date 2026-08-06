
import json

from tiff.trace_net_engineering_context_crag_retry_plan_v1 import check_engineering_context_crag_retry_plan_quality


def test_quality_flags_unknown_target_routes(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "source_self_rag_quality_status": "PASS",
            "crag_retry_plan_count": 1,
            "total_retry_action_count": 1,
            "ready_for_crag_execution_count": 1,
            "unknown_target_route_count": 1,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "llm_call_allowed_count": 0,
            "retrieval_execution_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
        }
    }), encoding="utf-8")
    result = check_engineering_context_crag_retry_plan_quality(
        report_path=path,
        max_unknown_target_routes=0,
    )
    assert result["quality_status"] == "FAIL"


def test_quality_flags_retrieval_execution(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "source_self_rag_quality_status": "PASS",
            "crag_retry_plan_count": 1,
            "total_retry_action_count": 1,
            "ready_for_crag_execution_count": 1,
            "unknown_target_route_count": 0,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "llm_call_allowed_count": 0,
            "retrieval_execution_allowed_count": 1,
            "source_truth_mutation_allowed_count": 0,
        }
    }), encoding="utf-8")
    result = check_engineering_context_crag_retry_plan_quality(
        report_path=path,
        require_no_retrieval_execution=True,
    )
    assert result["quality_status"] == "FAIL"
