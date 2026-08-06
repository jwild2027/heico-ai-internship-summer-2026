from __future__ import annotations

from tiff.trace_net_human_review_workbench_preview_wiring_v1 import compute_quality


def test_quality_fails_when_page_scoped_preview_missing() -> None:
    report = {
        "summary": {
            "workbench_card_count": 2,
            "page_workbench_profile_count": 2,
            "page_scoped_workbench_card_count": 1,
            "cards_with_page_preview_count": 0,
            "cards_with_source_package_summary_count": 0,
            "page_profiles_with_page_preview_count": 0,
            "missing_page_preview_for_page_scoped_card_count": 1,
            "cards_with_checksum_mismatch_count": 0,
            "unsafe_preview_card_count": 0,
            "preview_can_answer_directly_count": 0,
            "preview_can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "raw_feedback_direct_to_llm_count": 0,
            "final_answer_allowed_count": 0,
            "source_workbench_quality_status": "PASS",
            "source_dublin_core_source_package_quality_status": "PASS",
        }
    }
    quality = compute_quality(
        report,
        min_workbench_cards=1,
        min_page_profiles=1,
        min_page_scoped_cards=1,
        min_cards_with_page_preview=1,
        min_cards_with_source_package_summary=1,
        min_page_profiles_with_preview=1,
        require_source_workbench_quality_pass=True,
        require_source_package_quality_pass=True,
    )
    assert quality["status"] == "FAIL"
    assert quality["checks"]["min_cards_with_page_preview"] is False
    assert quality["checks"]["no_missing_preview_for_page_scoped_cards"] is False


def test_quality_passes_for_safe_preview_counts() -> None:
    report = {
        "summary": {
            "workbench_card_count": 544,
            "page_workbench_profile_count": 509,
            "page_scoped_workbench_card_count": 492,
            "cards_with_page_preview_count": 492,
            "cards_with_source_package_summary_count": 492,
            "page_profiles_with_page_preview_count": 509,
            "missing_page_preview_for_page_scoped_card_count": 0,
            "cards_with_checksum_mismatch_count": 0,
            "unsafe_preview_card_count": 0,
            "preview_can_answer_directly_count": 0,
            "preview_can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "raw_feedback_direct_to_llm_count": 0,
            "final_answer_allowed_count": 0,
            "source_workbench_quality_status": "PASS",
            "source_dublin_core_source_package_quality_status": "PASS",
        }
    }
    quality = compute_quality(
        report,
        min_workbench_cards=544,
        min_page_profiles=509,
        min_page_scoped_cards=492,
        min_cards_with_page_preview=492,
        min_cards_with_source_package_summary=492,
        min_page_profiles_with_preview=509,
        require_source_workbench_quality_pass=True,
        require_source_package_quality_pass=True,
    )
    assert quality["status"] == "PASS"
    assert all(quality["checks"].values())
