from tiff.trace_net_table_route_value_normalizer_v1 import evaluate_quality


def base_summary():
    return {
        "source_table_route_cell_extractor_quality_status": "PASS",
        "source_table_route_cell_extraction_record_count": 20,
        "source_table_value_record_count": 100,
        "table_route_value_normalizer_record_count": 20,
        "normalized_table_value_record_count": 80,
        "normalized_table_count": 19,
        "covered_part_number_record_count": 20,
        "manual_page_reference_record_count": 5,
        "ipl_part_number_record_count": 10,
        "unsafe_table_route_value_normalizer_record_count": 0,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }


def test_quality_passes():
    status, failures = evaluate_quality(base_summary(), {
        "min_source_cell_extraction_records": 20,
        "min_source_value_records": 1,
        "min_normalizer_records": 20,
        "min_normalized_records": 1,
        "min_normalized_tables": 1,
        "min_covered_part_number_records": 1,
        "min_manual_page_reference_records": 1,
        "min_ipl_part_number_records": 1,
        "max_unsafe_records": 0,
        "max_answer_permission_count": 0,
        "max_source_truth_mutation_allowed": 0,
        "require_table_route_cell_extractor_quality_pass": True,
        "require_no_answer_permission": True,
    })
    assert status == "PASS"
    assert failures == []


def test_quality_fails_on_answer_permission():
    summary = base_summary()
    summary["answer_permission_count"] = 1
    status, failures = evaluate_quality(summary, {"require_no_answer_permission": True, "max_answer_permission_count": 0})
    assert status == "FAIL"
    assert "answer_permission_above_limit" in failures


def test_quality_fails_on_lep_context_cap():
    summary = base_summary()
    summary["lep_context_record_count"] = 10
    summary["lep_row_derived_manual_page_reference_record_count"] = 0
    status, failures = evaluate_quality(summary, {"max_lep_context_records": 3})
    assert status == "FAIL"
    assert "lep_context_record_count_above_max" in failures


def test_quality_checks_row_derived_lep_refs():
    summary = base_summary()
    summary["lep_row_derived_manual_page_reference_record_count"] = 2
    status, failures = evaluate_quality(summary, {"min_lep_row_derived_manual_page_reference_records": 1})
    assert status == "PASS"
    assert failures == []
