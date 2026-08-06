from __future__ import annotations

from tiff.trace_net_page_ink_route_evidence_v1_quality import (
    InkRouteEvidenceQualityThresholds,
    evaluate_quality,
)


def test_quality_passes_with_required_counts() -> None:
    report = {
        "schema_version": "trace_net_page_ink_route_evidence_v1",
        "summary": {
            "ink_evidence_card_count": 3,
            "source_page_ink_evidence_card_count": 3,
            "image_analyzed_card_count": 3,
            "image_read_error_card_count": 0,
            "unsafe_ink_card_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "page_route_manifest_quality_status": "PASS",
        },
    }
    q = evaluate_quality(report, InkRouteEvidenceQualityThresholds(
        min_ink_evidence_cards=3,
        min_source_page_ink_evidence_cards=3,
        min_image_analyzed_cards=3,
        require_page_route_manifest_quality_pass=True,
        require_no_answer_permission=True,
    ))
    assert q["quality_status"] == "PASS"


def test_quality_fails_on_image_read_errors() -> None:
    report = {
        "schema_version": "trace_net_page_ink_route_evidence_v1",
        "summary": {
            "ink_evidence_card_count": 3,
            "source_page_ink_evidence_card_count": 3,
            "image_analyzed_card_count": 2,
            "image_read_error_card_count": 1,
            "unsafe_ink_card_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "page_route_manifest_quality_status": "PASS",
        },
    }
    q = evaluate_quality(report, InkRouteEvidenceQualityThresholds(max_image_read_error_cards=0))
    assert q["quality_status"] == "FAIL"
    assert "image_read_error_cards_within_limit" in q["quality_fail_reasons"]
