from tiff.trace_net_human_review_workbench_v1 import compute_quality


def test_quality_requires_zero_safety_counts():
    report = {
        "summary": {
            "workbench_card_count": 3,
            "page_workbench_profile_count": 2,
            "cards_with_page_ids_count": 2,
            "high_priority_workbench_card_count": 1,
            "critical_workbench_card_count": 1,
            "cards_with_recommended_actions_count": 3,
            "cards_with_allowed_decisions_count": 3,
            "unsafe_workbench_card_count": 0,
            "workbench_can_answer_directly_count": 1,
            "workbench_can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "raw_feedback_direct_to_llm_count": 0,
            "final_answer_allowed_count": 0,
            "source_triage_quality_status": "PASS",
            "source_queue_quality_status": "PASS",
        }
    }
    q = compute_quality(report, min_workbench_cards=1, require_source_triage_quality_pass=True, require_source_queue_quality_pass=True)
    assert q["status"] == "FAIL"
    assert q["checks"]["workbench_can_answer_directly_count_zero"] is False


def test_quality_passes_for_clean_summary():
    report = {
        "summary": {
            "workbench_card_count": 3,
            "page_workbench_profile_count": 2,
            "cards_with_page_ids_count": 2,
            "high_priority_workbench_card_count": 1,
            "critical_workbench_card_count": 1,
            "cards_with_recommended_actions_count": 3,
            "cards_with_allowed_decisions_count": 3,
            "unsafe_workbench_card_count": 0,
            "workbench_can_answer_directly_count": 0,
            "workbench_can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "raw_feedback_direct_to_llm_count": 0,
            "final_answer_allowed_count": 0,
            "source_triage_quality_status": "PASS",
            "source_queue_quality_status": "PASS",
        }
    }
    q = compute_quality(report, require_page_count=2, min_workbench_cards=3, min_page_profiles=2, min_cards_with_page_ids=2, min_high_priority_cards=1, min_critical_cards=1, require_source_triage_quality_pass=True, require_source_queue_quality_pass=True)
    assert q["status"] == "PASS"
