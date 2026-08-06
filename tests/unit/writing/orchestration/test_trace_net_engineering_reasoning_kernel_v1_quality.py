
import json

from tiff.trace_net_engineering_reasoning_kernel_v1 import check_engineering_reasoning_kernel_quality


def test_quality_fails_answer_permission(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "playbook_count": 5,
            "example_card_count": 4,
            "query_plan_template_count": 1,
            "sample_intent_plan_count": 4,
            "unsafe_record_count": 0,
            "answer_permission_count": 1,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "llm_call_allowed_count": 0,
            "retrieval_execution_allowed_count": 0,
        }
    }), encoding="utf-8")
    result = check_engineering_reasoning_kernel_quality(
        report_path=path,
        require_no_answer_permission=True,
    )
    assert result["quality_status"] == "FAIL"


def test_quality_fails_route_dispatch_when_required(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "playbook_count": 5,
            "example_card_count": 4,
            "query_plan_template_count": 1,
            "sample_intent_plan_count": 4,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "llm_call_allowed_count": 0,
            "retrieval_execution_allowed_count": 0,
            "source_route_dispatch_quality_status": "FAIL",
        }
    }), encoding="utf-8")
    result = check_engineering_reasoning_kernel_quality(
        report_path=path,
        require_route_dispatch_quality_pass=True,
    )
    assert result["quality_status"] == "FAIL"
