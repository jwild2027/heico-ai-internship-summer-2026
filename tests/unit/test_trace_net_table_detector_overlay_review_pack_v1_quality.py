from tiff.trace_net_table_detector_overlay_review_pack_v1 import Thresholds, evaluate_quality


def test_quality_passes_for_safe_report():
    report = {
        "schema_version": "trace_net_table_detector_overlay_review_pack_v1",
        "summary": {
            "review_card_count": 20,
            "overlay_ready_card_count": 20,
            "contact_sheet_count": 1,
            "unsafe_review_card_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "overlay_audit_quality_status": "PASS",
        },
    }
    quality = evaluate_quality(report, Thresholds(
        min_review_cards=20,
        min_overlay_ready_cards=1,
        require_overlay_audit_quality_pass=True,
        require_no_answer_permission=True,
        require_contact_sheet=True,
    ))
    assert quality["quality_status"] == "PASS"


def test_quality_fails_for_answer_permission():
    report = {
        "schema_version": "trace_net_table_detector_overlay_review_pack_v1",
        "summary": {
            "review_card_count": 1,
            "overlay_ready_card_count": 1,
            "unsafe_review_card_count": 0,
            "answer_permission_count": 1,
            "source_truth_mutation_allowed_count": 0,
            "overlay_audit_quality_status": "PASS",
        },
    }
    quality = evaluate_quality(report, Thresholds(require_no_answer_permission=True))
    assert quality["quality_status"] == "FAIL"
    assert "no_answer_permission" in quality["summary"]["quality_fail_reasons"]
