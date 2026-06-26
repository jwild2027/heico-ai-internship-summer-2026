import json
from pathlib import Path

from tiff.trace_net_fishnet_route_review_packet_v1 import check_review_packet_quality


def _payload(**summary_overrides):
    summary = {
        "review_record_count": 20,
        "high_confidence_review_record_count": 14,
        "review_records_with_ocr_text_count": 18,
        "selected_route_pair_counts": {"blank_candidate->normal_text": 10, "image_visual->normal_text": 4},
        "unsafe_record_count": 0,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "route_change_authorized_count": 0,
    }
    summary.update(summary_overrides)
    return {"quality_status": "PASS", "summary": summary, "records": []}


def test_quality_passes_expected_thresholds(tmp_path):
    report = tmp_path / "packet.json"
    report.write_text(json.dumps(_payload()), encoding="utf-8")
    result = check_review_packet_quality(
        report_path=report,
        require_review_record_count=10,
        min_high_confidence_records=14,
        min_selected_route_pairs=2,
        min_records_with_ocr_text=10,
        max_unsafe=0,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_route_change_authorization=True,
        write_json_report=True,
    )
    assert result["quality_status"] == "PASS"
    assert not result["errors"]
    assert (tmp_path / "trace_net_fishnet_route_review_packet_v1_quality_check.json").exists()


def test_quality_fails_on_route_change_authorization(tmp_path):
    report = tmp_path / "packet.json"
    report.write_text(json.dumps(_payload(route_change_authorized_count=1)), encoding="utf-8")
    result = check_review_packet_quality(report_path=report, require_no_route_change_authorization=True)
    assert result["quality_status"] == "FAIL"
    assert any("route_change_authorized_count" in e for e in result["errors"])


def test_quality_fails_on_answer_permission(tmp_path):
    report = tmp_path / "packet.json"
    report.write_text(json.dumps(_payload(answer_permission_count=1)), encoding="utf-8")
    result = check_review_packet_quality(report_path=report, require_no_answer_permission=True)
    assert result["quality_status"] == "FAIL"
    assert any("answer_permission_count" in e for e in result["errors"])
