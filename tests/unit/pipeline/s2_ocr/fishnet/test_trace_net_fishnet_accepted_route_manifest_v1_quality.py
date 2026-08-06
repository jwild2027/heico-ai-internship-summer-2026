
import json
from pathlib import Path

from tiff.trace_net_fishnet_accepted_route_manifest_v1 import check_accepted_route_manifest_quality


def test_quality_flags_official_manifest_mutation(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "source_overlay_quality_status": "PASS",
            "accepted_route_manifest_page_count": 509,
            "accepted_delta_record_count": 14,
            "normal_text_accepted_change_count": 14,
            "current_route_match_missing_count": 0,
            "unsafe_record_count": 0,
            "official_route_manifest_mutated_count": 1,
            "route_manifest_write_allowed_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "route_change_authorized_count": 14,
        }
    }), encoding="utf-8")
    result = check_accepted_route_manifest_quality(
        report_path=path,
        max_official_manifest_mutated=0,
    )
    assert result["quality_status"] == "FAIL"


def test_quality_flags_missing_pages(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({
        "summary": {
            "source_overlay_quality_status": "PASS",
            "accepted_route_manifest_page_count": 508,
            "accepted_delta_record_count": 14,
            "normal_text_accepted_change_count": 14,
            "current_route_match_missing_count": 0,
            "unsafe_record_count": 0,
            "official_route_manifest_mutated_count": 0,
            "route_manifest_write_allowed_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "route_change_authorized_count": 14,
        }
    }), encoding="utf-8")
    result = check_accepted_route_manifest_quality(report_path=path, require_page_count=509)
    assert result["quality_status"] == "FAIL"
