from tiff.trace_net_element_category_taxonomy_v1 import quality_report


def test_quality_passes_for_safe_report() -> None:
    report = {
        "summary": {
            "page_count": 2,
            "page_category_profile_count": 2,
            "category_record_count": 4,
            "categorized_element_count": 10,
            "diagram_category_count": 2,
            "table_category_count": 3,
            "part_category_count": 1,
            "review_category_count": 1,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "unsafe_category_record_count": 0,
        }
    }
    quality = quality_report(
        report,
        require_page_count=2,
        min_page_profiles=2,
        min_categorized_elements=1,
        min_diagram_categories=1,
        min_table_categories=1,
        min_part_categories=1,
        min_review_categories=1,
    )
    assert quality["status"] == "PASS"


def test_quality_fails_on_safety_counts() -> None:
    report = {
        "summary": {
            "page_count": 2,
            "page_category_profile_count": 2,
            "categorized_element_count": 10,
            "diagram_category_count": 2,
            "table_category_count": 3,
            "part_category_count": 1,
            "review_category_count": 1,
            "can_answer_directly_count": 1,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "unsafe_category_record_count": 0,
        }
    }
    quality = quality_report(report, require_page_count=2)
    assert quality["status"] == "FAIL"
    assert any("can_answer_directly_count" in issue for issue in quality["issues"])
