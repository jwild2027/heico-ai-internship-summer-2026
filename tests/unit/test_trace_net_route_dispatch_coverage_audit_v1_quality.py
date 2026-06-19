from __future__ import annotations

from tiff.trace_net_route_dispatch_coverage_audit_v1_quality import (
    RouteDispatchCoverageAuditQualityThresholds,
    evaluate_quality,
)


def test_quality_passes_with_required_counts() -> None:
    report = {
        "schema_version": "trace_net_route_dispatch_coverage_audit_v1",
        "summary": {
            "dispatch_coverage_card_count": 509,
            "audited_page_artifact_card_count": 631,
            "unsafe_audit_card_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "route_dispatch_manifest_quality_status": "PASS",
            "artifact_detector_quality_status": "PASS",
        },
    }
    q = evaluate_quality(report, RouteDispatchCoverageAuditQualityThresholds(
        min_dispatch_coverage_cards=500,
        min_audited_page_artifact_cards=1,
        require_route_dispatch_manifest_quality_pass=True,
        require_artifact_detector_quality_pass=True,
        require_no_answer_permission=True,
    ))
    assert q["quality_status"] == "PASS"


def test_quality_fails_when_source_quality_missing() -> None:
    report = {
        "schema_version": "trace_net_route_dispatch_coverage_audit_v1",
        "summary": {
            "dispatch_coverage_card_count": 509,
            "audited_page_artifact_card_count": 631,
            "unsafe_audit_card_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "route_dispatch_manifest_quality_status": "FAIL",
            "artifact_detector_quality_status": "PASS",
        },
    }
    q = evaluate_quality(report, RouteDispatchCoverageAuditQualityThresholds(require_route_dispatch_manifest_quality_pass=True))
    assert q["quality_status"] == "FAIL"
    assert "route_dispatch_manifest_quality_pass" in q["quality_fail_reasons"]
