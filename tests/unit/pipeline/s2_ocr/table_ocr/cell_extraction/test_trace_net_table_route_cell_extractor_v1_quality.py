from tiff.trace_net_table_route_cell_extractor_v1 import evaluate_quality


def good_summary():
    return {
        "source_table_bbox_record_count": 20,
        "table_route_cell_extraction_record_count": 20,
        "extraction_ready_table_count": 19,
        "review_only_skipped_count": 1,
        "cell_extraction_attempted_count": 19,
        "cell_extraction_success_record_count": 19,
        "table_row_record_count": 100,
        "table_cell_record_count": 300,
        "table_value_record_count": 300,
        "part_number_candidate_count": 10,
        "unsafe_table_route_cell_extraction_record_count": 0,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "retrieval_only_answer_allowed_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "source_quality_statuses": {
            "table_full_enclosure_bbox_reconstructor": "PASS",
            "table_ocr_bbox_enrichment": "PASS",
            "table_bbox_scoped_cell_extraction": "PASS",
        },
    }


def thresholds():
    return {
        "min_source_table_bbox_records": 20,
        "min_extraction_records": 20,
        "min_extraction_ready_tables": 19,
        "min_review_only_skipped": 1,
        "min_cell_extraction_attempted": 19,
        "min_cell_extraction_success_records": 1,
        "min_row_records": 1,
        "min_cell_records": 1,
        "min_value_records": 1,
        "min_part_number_candidates": 0,
        "max_unsafe_records": 0,
        "max_answer_permission_count": 0,
        "max_source_truth_mutation_allowed": 0,
        "require_table_full_enclosure_bbox_reconstructor_quality_pass": True,
        "require_table_ocr_bbox_enrichment_quality_pass": True,
        "require_table_bbox_scoped_cell_extraction_quality_pass": True,
        "require_no_answer_permission": True,
    }


def test_quality_passes_good_summary():
    status, failures = evaluate_quality(good_summary(), thresholds())
    assert status == "PASS"
    assert failures == []


def test_quality_fails_on_answer_permission():
    summary = good_summary()
    summary["answer_permission_count"] = 1
    status, failures = evaluate_quality(summary, thresholds())
    assert status == "FAIL"
    assert "answer_permission_count_exceeded" in failures
