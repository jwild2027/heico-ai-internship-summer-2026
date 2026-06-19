from __future__ import annotations

from tiff.trace_net_route_dispatch_warning_triage_v1_quality import (
    FAIL,
    PASS,
    RouteDispatchWarningTriageQualityThresholds,
    evaluate_quality,
)


def test_warning_triage_quality_passes_with_safe_counts() -> None:
    report = {
        "schema_version": "trace_net_route_dispatch_warning_triage_v1",
        "summary": {
            "warning_triage_card_count": 5,
            "unsafe_triage_card_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "route_dispatch_coverage_audit_quality_status": "PASS",
        },
    }
    quality = evaluate_quality(
        report,
        RouteDispatchWarningTriageQualityThresholds(
            min_warning_triage_cards=1,
            require_route_dispatch_coverage_audit_quality_pass=True,
            require_no_answer_permission=True,
        ),
    )
    assert quality["quality_status"] == PASS


def test_warning_triage_quality_fails_on_unsafe_count() -> None:
    report = {
        "schema_version": "trace_net_route_dispatch_warning_triage_v1",
        "summary": {
            "warning_triage_card_count": 5,
            "unsafe_triage_card_count": 1,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "route_dispatch_coverage_audit_quality_status": "PASS",
        },
    }
    quality = evaluate_quality(report, RouteDispatchWarningTriageQualityThresholds(max_unsafe_triage_cards=0))
    assert quality["quality_status"] == FAIL
    assert "unsafe_triage_cards_within_limit" in quality["quality_fail_reasons"]
