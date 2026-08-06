from tiff.trace_net_table_margin_detector_parity_v1 import Thresholds
from tiff.trace_net_table_margin_detector_parity_v1_quality import build_quality_report


def test_quality_passes_with_required_counts():
    report = {
        "schema_version": "trace_net_table_margin_detector_parity_v1",
        "summary": {
            "parity_card_count": 20,
            "margin_candidate_evaluation_count": 120,
            "successful_image_card_count": 20,
            "detector_disagreement_card_count": 19,
            "unsafe_parity_card_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "table_line_geometry_quality_status": "PASS",
            "table_bbox_resolver_quality_status": "PASS",
        },
    }
    quality = build_quality_report(report, Thresholds(
        min_parity_cards=20,
        min_margin_candidate_evaluations=120,
        min_successful_image_cards=20,
        min_detector_disagreement_cards=1,
        require_table_line_geometry_quality_pass=True,
        require_table_bbox_resolver_quality_pass=True,
        require_no_answer_permission=True,
    ))
    assert quality["quality_status"] == "PASS"


def test_quality_fails_when_disagreement_missing():
    report = {
        "schema_version": "trace_net_table_margin_detector_parity_v1",
        "summary": {
            "parity_card_count": 20,
            "margin_candidate_evaluation_count": 120,
            "successful_image_card_count": 20,
            "detector_disagreement_card_count": 0,
            "unsafe_parity_card_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
    }
    quality = build_quality_report(report, Thresholds(min_detector_disagreement_cards=1))
    assert quality["quality_status"] == "FAIL"
    assert "min_detector_disagreement_cards_met" in quality["summary"]["quality_fail_reasons"]
