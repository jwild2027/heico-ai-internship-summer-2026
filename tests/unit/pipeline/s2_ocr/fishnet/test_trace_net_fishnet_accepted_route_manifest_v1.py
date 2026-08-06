
import json
from pathlib import Path

import pytest

from tiff.trace_net_fishnet_accepted_route_manifest_v1 import (
    build_accepted_route_manifest,
    check_accepted_route_manifest_quality,
)


def _write(path: Path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_accepts_reviewed_overlays_without_mutating_official(tmp_path):
    overlay = {
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "source_p000001",
                "current_route_manifest_page_id": "t_p_120_1176_p000001",
                "current_route": "blank_candidate",
                "proposed_target_route": "normal_text",
                "overlay_status": "proposed_review_only",
                "validation_status": "overlay_ready_for_review",
                "fishnet_route_confidence": 0.91,
                "fishnet_ocr_text_length": 1000,
                "fishnet_ocr_word_box_count": 120,
                "fishnet_ocr_sample_text": "manual text",
            }
        ],
    }
    current = {
        "quality_status": "PASS",
        "records": [
            {"page_id": "t_p_120_1176_p000001", "selected_route": "blank_candidate"},
            {"page_id": "t_p_120_1176_p000002", "selected_route": "table"},
        ],
    }
    overlay_path = tmp_path / "overlay.json"
    current_path = tmp_path / "current.json"
    out = tmp_path / "out"
    _write(overlay_path, overlay)
    _write(current_path, current)

    payload = build_accepted_route_manifest(
        overlay_path=overlay_path,
        current_route_manifest_path=current_path,
        output_dir=out,
        accept_reviewed_overlays=True,
    )

    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["accepted_route_manifest_page_count"] == 2
    assert payload["summary"]["accepted_delta_record_count"] == 1
    assert payload["summary"]["normal_text_accepted_change_count"] == 1
    assert payload["summary"]["official_route_manifest_mutated_count"] == 0
    assert payload["records"][0]["selected_route"] == "normal_text"
    assert payload["records"][0]["route_change_authorized"] is True
    assert payload["records"][1]["selected_route"] == "table"
    assert current["records"][0]["selected_route"] == "blank_candidate"


def test_build_refuses_without_explicit_accept_flag(tmp_path):
    overlay_path = tmp_path / "overlay.json"
    current_path = tmp_path / "current.json"
    _write(overlay_path, {"quality_status": "PASS", "records": []})
    _write(current_path, {"records": []})
    with pytest.raises(ValueError):
        build_accepted_route_manifest(
            overlay_path=overlay_path,
            current_route_manifest_path=current_path,
            output_dir=tmp_path / "out",
            accept_reviewed_overlays=False,
        )


def test_quality_checker_passes_expected_counts(tmp_path):
    report = {
        "quality_status": "PASS",
        "summary": {
            "source_overlay_quality_status": "PASS",
            "accepted_route_manifest_page_count": 509,
            "accepted_delta_record_count": 14,
            "normal_text_accepted_change_count": 14,
            "current_route_match_missing_count": 0,
            "unsafe_record_count": 0,
            "official_route_manifest_mutated_count": 0,
            "route_manifest_write_allowed_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "route_change_authorized_count": 14,
        },
    }
    path = tmp_path / "report.json"
    _write(path, report)
    result = check_accepted_route_manifest_quality(
        report_path=path,
        require_source_overlay_quality_pass=True,
        require_page_count=509,
        min_accepted_route_changes=14,
        min_normal_text_changes=14,
        max_missing_current_routes=0,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_route_changes_authorized=True,
    )
    assert result["quality_status"] == "PASS"


def test_quality_checker_fails_missing_authorization(tmp_path):
    report = {
        "quality_status": "PASS",
        "summary": {
            "source_overlay_quality_status": "PASS",
            "accepted_route_manifest_page_count": 509,
            "accepted_delta_record_count": 14,
            "normal_text_accepted_change_count": 14,
            "current_route_match_missing_count": 0,
            "unsafe_record_count": 0,
            "official_route_manifest_mutated_count": 0,
            "route_manifest_write_allowed_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "route_change_authorized_count": 0,
        },
    }
    path = tmp_path / "report.json"
    _write(path, report)
    result = check_accepted_route_manifest_quality(
        report_path=path,
        min_accepted_route_changes=14,
        require_route_changes_authorized=True,
    )
    assert result["quality_status"] == "FAIL"
