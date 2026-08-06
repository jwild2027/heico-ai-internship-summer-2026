
import json
from pathlib import Path

from tiff.trace_net_fishnet_route_dispatch_handoff_v1 import (
    build_route_dispatch_handoff,
    check_route_dispatch_handoff_quality,
)


def _write(path: Path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_emits_all_route_handoffs(tmp_path):
    manifest = {
        "quality_status": "PASS",
        "summary": {"accepted_route_manifest_page_count": 4},
        "records": [
            {"page_id": "p1", "original_route": "blank_candidate", "accepted_route": "normal_text", "route_changed": True, "route_change_authorized": True},
            {"page_id": "p2", "original_route": "blank_candidate", "accepted_route": "blank_candidate"},
            {"page_id": "p3", "original_route": "table", "accepted_route": "table"},
            {"page_id": "p4", "original_route": "image_visual", "accepted_route": "image_visual"},
        ],
    }
    in_path = tmp_path / "accepted.json"
    out = tmp_path / "out"
    _write(in_path, manifest)

    payload = build_route_dispatch_handoff(accepted_route_manifest_path=in_path, output_dir=out)

    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["dispatch_record_count"] == 4
    assert payload["summary"]["normal_text_handoff_count"] == 1
    assert payload["summary"]["blank_candidate_handoff_count"] == 1
    assert payload["summary"]["table_handoff_count"] == 1
    assert payload["summary"]["image_visual_handoff_count"] == 1
    assert payload["summary"]["changed_route_handoff_count"] == 1
    assert payload["summary"]["processor_execution_allowed_count"] == 0
    assert (out / "normal_text" / "trace_net_fishnet_route_dispatch_handoff_v1_normal_text.json").exists()


def test_quality_checker_passes_expected_counts(tmp_path):
    report = {
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
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
        }
    }
    path = tmp_path / "report.json"
    _write(path, report)
    result = check_route_dispatch_handoff_quality(
        report_path=path,
        require_source_accepted_manifest_quality_pass=True,
        require_page_count=509,
        min_normal_text_handoffs=15,
        min_blank_candidate_handoffs=461,
        min_table_handoffs=21,
        min_image_visual_handoffs=12,
        min_changed_route_handoffs=14,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
    )
    assert result["quality_status"] == "PASS"


def test_quality_checker_fails_unknown_routes(tmp_path):
    report = {
        "summary": {
            "source_accepted_route_manifest_quality_status": "PASS",
            "dispatch_record_count": 1,
            "normal_text_handoff_count": 0,
            "blank_candidate_handoff_count": 0,
            "table_handoff_count": 0,
            "image_visual_handoff_count": 0,
            "changed_route_handoff_count": 0,
            "unknown_route_handoff_count": 1,
            "unsafe_record_count": 1,
            "processor_execution_allowed_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
        }
    }
    path = tmp_path / "report.json"
    _write(path, report)
    result = check_route_dispatch_handoff_quality(report_path=path, max_unknown_routes=0, max_unsafe=0)
    assert result["quality_status"] == "FAIL"
