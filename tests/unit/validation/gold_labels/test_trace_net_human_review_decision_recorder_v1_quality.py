from __future__ import annotations

from tiff.trace_net_human_review_decision_recorder_v1 import create_review_decision_event, quality_report


def test_quality_report_passes_clean_decision() -> None:
    record = create_review_decision_event(
        decision_type="confirm_part_link",
        target_type="part_candidate",
        target_id="part_candidate::120-46137-001",
        page_ids=["t_p_120_1176_p000003"],
    )
    quality = quality_report([record], min_review_decisions=1)
    assert quality["status"] == "PASS"
    assert quality["summary"]["review_decision_count"] == 1
    assert quality["summary"]["source_truth_mutation_allowed_count"] == 0


def test_quality_report_fails_missing_target() -> None:
    record = create_review_decision_event(
        decision_type="approve",
        actor_id="reviewer",
        target_type="",
        target_id="",
    )
    quality = quality_report([record], min_review_decisions=1)
    assert quality["status"] == "FAIL"
    assert quality["summary"]["missing_target_count"] == 1


def test_quality_report_fails_source_truth_mutation() -> None:
    record = create_review_decision_event(
        decision_type="approve",
        target_type="page",
        target_id="t_p_120_1176_p000003",
    )
    record["source_truth_mutation_allowed"] = True
    record["can_mutate_source_truth"] = True
    quality = quality_report([record], min_review_decisions=1)
    assert quality["status"] == "FAIL"
    assert quality["summary"]["source_truth_mutation_allowed_count"] == 1
    assert quality["summary"]["decision_can_mutate_source_truth_count"] == 1


def test_quality_report_requires_triage_pass() -> None:
    record = create_review_decision_event(
        decision_type="reject_callout",
        target_type="callout_candidate",
        target_id="callout_1",
    )
    report = {"decision_records": [record], "summary": {"review_decision_count": 1, "source_triage_quality_status": "FAIL"}}
    quality = quality_report(report, min_review_decisions=1, require_source_triage_quality_pass=True)
    assert quality["status"] == "FAIL"


def test_quality_report_fails_minimum_decisions() -> None:
    quality = quality_report([], min_review_decisions=1)
    assert quality["status"] == "FAIL"
    assert quality["summary"]["review_decision_count"] == 0
