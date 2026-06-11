from __future__ import annotations

from tiff.trace_net_human_review_triage_v1 import compute_quality


def report(summary: dict) -> dict:
    return {"summary": summary}


def base_summary() -> dict:
    return {
        "input_review_task_count": 10,
        "triage_card_count": 5,
        "high_priority_triage_card_count": 2,
        "critical_task_input_count": 1,
        "critical_task_preserved_count": 1,
        "missing_page_id_count": 0,
        "unsafe_triage_card_count": 0,
        "triage_card_can_answer_directly_count": 0,
        "triage_card_can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "raw_feedback_direct_to_llm_count": 0,
        "final_answer_allowed_count": 0,
        "source_queue_quality_status": "PASS",
    }


def test_compute_quality_passes_clean_report() -> None:
    quality = compute_quality(report(base_summary()), require_source_queue_quality_pass=True)
    assert quality["status"] == "PASS"


def test_compute_quality_fails_when_critical_not_preserved() -> None:
    summary = base_summary()
    summary["critical_task_preserved_count"] = 0
    quality = compute_quality(report(summary))
    assert quality["status"] == "FAIL"
    assert quality["checks"]["critical_tasks_preserved"] is False


def test_compute_quality_fails_when_no_dedup_if_required() -> None:
    summary = base_summary()
    summary["triage_card_count"] = 10
    quality = compute_quality(report(summary), require_deduplication=True)
    assert quality["status"] == "FAIL"
    assert quality["checks"]["triage_cards_less_than_input_tasks"] is False


def test_compute_quality_allows_no_dedup_when_disabled() -> None:
    summary = base_summary()
    summary["triage_card_count"] = 10
    quality = compute_quality(report(summary), require_deduplication=False)
    assert quality["status"] == "PASS"
