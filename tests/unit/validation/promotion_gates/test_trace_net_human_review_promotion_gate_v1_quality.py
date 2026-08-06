from __future__ import annotations

from tiff.trace_net_human_review_promotion_gate_v1 import APPROVED_STATUS, quality_report


def safe_record():
    return {
        "promotion_candidate": True,
        "promotion_gate_status": APPROVED_STATUS,
        "approved_without_citation": False,
        "approved_without_source_or_page": False,
        "approved_without_graph_or_catalog_support": False,
        "unsafe_promotion_record": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
        "final_answer_allowed": False,
        "raw_feedback_direct_to_llm": False,
    }


def test_quality_passes_for_safe_promotion_record():
    quality = quality_report([safe_record()], min_review_decisions=1, min_promotion_evaluations=1)
    assert quality["status"] == "PASS"
    assert quality["summary"]["promotion_approved_count"] == 1


def test_quality_fails_when_source_truth_mutation_allowed():
    record = safe_record()
    record["source_truth_mutation_allowed"] = True
    quality = quality_report([record], min_review_decisions=1, min_promotion_evaluations=1)
    assert quality["status"] == "FAIL"


def test_quality_fails_when_source_decision_required_but_not_pass():
    quality = quality_report({"promotion_records": [safe_record()], "summary": {"review_decision_count": 1, "promotion_evaluation_count": 1, "source_decision_quality_status": "FAIL"}}, require_source_decision_quality_pass=True)
    assert quality["status"] == "FAIL"
