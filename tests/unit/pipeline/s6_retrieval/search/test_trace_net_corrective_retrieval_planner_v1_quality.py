import json
from pathlib import Path

from tiff.trace_net_corrective_retrieval_planner_v1 import Thresholds, check_corrective_retrieval_plan_quality


def test_check_quality_recomputes_counts(tmp_path):
    report = {
        "schema_version": "trace_net_corrective_retrieval_planner_v1",
        "status": "CORRECTIVE_RETRIEVAL_PLAN_BUILT",
        "source_artifacts": {},
        "corrective_retrieval_records": [
            {
                "record_id": "r1",
                "source_module": "x",
                "issue_type": "semantic_page_target_miss",
                "severity": "HIGH",
                "recommended_actions": ["rerank_with_graph_page_anchor", "route_to_review"],
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
                "safety_contract": {"can_answer_directly": False, "can_prove_claims": False, "source_truth_mutation_allowed": False},
            }
        ],
    }
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    result = check_corrective_retrieval_plan_quality(
        report_path=path,
        thresholds=Thresholds(min_correction_records=1, min_safe_action_records=1, min_review_routed_records=1, require_no_answer_permission=True),
        write_json_report=True,
    )
    assert result["quality_status"] == "PASS"
    assert result["summary"]["correction_record_count"] == 1
    assert (tmp_path / "trace_net_corrective_retrieval_planner_v1_quality.json").exists()


def test_check_quality_fails_on_answer_permission(tmp_path):
    report = {
        "status": "CORRECTIVE_RETRIEVAL_PLAN_BUILT",
        "source_artifacts": {},
        "corrective_retrieval_records": [
            {
                "record_id": "r1",
                "source_module": "x",
                "issue_type": "bad",
                "severity": "HIGH",
                "recommended_actions": ["direct_answer"],
                "can_answer_directly": True,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            }
        ],
    }
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    result = check_corrective_retrieval_plan_quality(
        report_path=path,
        thresholds=Thresholds(max_unsafe_correction_records=0, max_answer_permission_count=0, require_no_answer_permission=True),
    )
    assert result["quality_status"] == "FAIL"
    assert result["summary"]["unsafe_correction_record_count"] == 1
    assert result["summary"]["answer_permission_count"] == 1
