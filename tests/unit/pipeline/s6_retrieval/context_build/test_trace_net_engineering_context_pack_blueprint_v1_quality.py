
import json

from tiff.trace_net_engineering_context_pack_blueprint_v1 import check_engineering_context_pack_blueprint_quality


def test_quality_flags_retrieval_execution(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "source_query_planner_quality_status": "PASS",
            "context_pack_blueprint_count": 1,
            "total_route_evidence_slot_count": 3,
            "blueprints_with_source_truth_required_count": 1,
            "unsafe_record_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "llm_call_allowed_count": 0,
            "retrieval_execution_allowed_count": 1,
            "source_truth_mutation_allowed_count": 0,
        }
    }), encoding="utf-8")

    result = check_engineering_context_pack_blueprint_quality(
        report_path=path,
        require_no_retrieval_execution=True,
    )
    assert result["quality_status"] == "FAIL"


def test_quality_flags_answer_permission(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "source_query_planner_quality_status": "PASS",
            "context_pack_blueprint_count": 1,
            "total_route_evidence_slot_count": 3,
            "blueprints_with_source_truth_required_count": 1,
            "unsafe_record_count": 0,
            "answer_permission_count": 1,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "llm_call_allowed_count": 0,
            "retrieval_execution_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
        }
    }), encoding="utf-8")

    result = check_engineering_context_pack_blueprint_quality(
        report_path=path,
        require_no_answer_permission=True,
    )
    assert result["quality_status"] == "FAIL"
