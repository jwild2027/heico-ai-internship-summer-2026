
import json

from tiff.trace_net_engineering_query_planner_v1 import check_engineering_query_planner_quality


def test_planner_quality_flags_llm_calls(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "source_kernel_quality_status": "PASS",
            "query_plan_count": 1,
            "plans_with_seed_entities_count": 1,
            "plans_with_requested_change_count": 0,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "llm_call_allowed_count": 1,
            "retrieval_execution_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
        }
    }), encoding="utf-8")
    result = check_engineering_query_planner_quality(
        report_path=path,
        require_no_llm_calls=True,
    )
    assert result["quality_status"] == "FAIL"


def test_planner_quality_flags_answer_permission(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "source_kernel_quality_status": "PASS",
            "query_plan_count": 1,
            "plans_with_seed_entities_count": 1,
            "plans_with_requested_change_count": 0,
            "unsafe_record_count": 0,
            "answer_permission_count": 1,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "llm_call_allowed_count": 0,
            "retrieval_execution_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
        }
    }), encoding="utf-8")
    result = check_engineering_query_planner_quality(
        report_path=path,
        require_no_answer_permission=True,
    )
    assert result["quality_status"] == "FAIL"
