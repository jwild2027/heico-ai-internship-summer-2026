
import json

from tiff.trace_net_fishnet_route_dispatch_handoff_v1 import check_route_dispatch_handoff_quality


def test_quality_flags_processor_execution(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "source_accepted_route_manifest_quality_status": "PASS",
            "dispatch_record_count": 509,
            "normal_text_handoff_count": 15,
            "blank_candidate_handoff_count": 461,
            "table_handoff_count": 21,
            "image_visual_handoff_count": 12,
            "changed_route_handoff_count": 14,
            "unknown_route_handoff_count": 0,
            "unsafe_record_count": 0,
            "processor_execution_allowed_count": 1,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
        }
    }), encoding="utf-8")
    result = check_route_dispatch_handoff_quality(
        report_path=path,
        max_processor_execution_allowed=0,
    )
    assert result["quality_status"] == "FAIL"


def test_quality_flags_answer_permission(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "source_accepted_route_manifest_quality_status": "PASS",
            "dispatch_record_count": 509,
            "normal_text_handoff_count": 15,
            "blank_candidate_handoff_count": 461,
            "table_handoff_count": 21,
            "image_visual_handoff_count": 12,
            "changed_route_handoff_count": 14,
            "unknown_route_handoff_count": 0,
            "unsafe_record_count": 0,
            "processor_execution_allowed_count": 0,
            "answer_permission_count": 1,
            "source_truth_mutation_allowed_count": 0,
        }
    }), encoding="utf-8")
    result = check_route_dispatch_handoff_quality(
        report_path=path,
        require_no_answer_permission=True,
    )
    assert result["quality_status"] == "FAIL"
