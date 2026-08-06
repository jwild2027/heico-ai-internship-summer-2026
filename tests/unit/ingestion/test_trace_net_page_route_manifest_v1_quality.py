from __future__ import annotations

from tiff.trace_net_page_route_manifest_v1_quality import (
    PageRouteManifestQualityThresholds,
    evaluate_quality,
)


def test_quality_passes_with_required_counts() -> None:
    report = {
        "schema_version": "trace_net_page_route_manifest_v1",
        "summary": {
            "page_route_card_count": 10,
            "source_page_route_card_count": 10,
            "table_primary_route_count": 2,
            "safe_for_routing_route_card_count": 10,
            "unsafe_route_card_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "artifact_detector_quality_status": "PASS",
        },
    }
    q = evaluate_quality(report, PageRouteManifestQualityThresholds(
        min_page_route_cards=10,
        min_source_page_route_cards=10,
        min_table_route_cards=1,
        require_artifact_detector_quality_pass=True,
        require_no_answer_permission=True,
    ))
    assert q["quality_status"] == "PASS"


def test_quality_fails_when_unsafe_route_present() -> None:
    report = {
        "schema_version": "trace_net_page_route_manifest_v1",
        "summary": {
            "page_route_card_count": 10,
            "source_page_route_card_count": 10,
            "safe_for_routing_route_card_count": 9,
            "unsafe_route_card_count": 1,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "artifact_detector_quality_status": "PASS",
        },
    }
    q = evaluate_quality(report, PageRouteManifestQualityThresholds(max_unsafe_route_cards=0))
    assert q["quality_status"] == "FAIL"
    assert "unsafe_route_cards_within_limit" in q["quality_fail_reasons"]


def test_quality_requires_ink_evidence_when_requested() -> None:
    report = {
        "schema_version": "trace_net_page_route_manifest_v1",
        "summary": {
            "page_route_card_count": 10,
            "source_page_route_card_count": 10,
            "table_primary_route_count": 2,
            "safe_for_routing_route_card_count": 10,
            "unsafe_route_card_count": 0,
            "page_ink_route_evidence_quality_status": "FAIL",
            "page_ink_route_evidence_available_card_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "artifact_detector_quality_status": "PASS",
        },
    }
    q = evaluate_quality(report, PageRouteManifestQualityThresholds(
        min_page_route_cards=10,
        min_source_page_route_cards=10,
        min_table_route_cards=1,
        min_page_ink_route_evidence_cards=10,
        require_page_ink_route_evidence_quality_pass=True,
    ))
    assert q["quality_status"] == "FAIL"
    assert "min_page_ink_route_evidence_cards_met" in q["quality_fail_reasons"]
    assert "page_ink_route_evidence_quality_pass" in q["quality_fail_reasons"]
