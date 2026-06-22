from tiff.trace_net_table_route_value_audit_v1 import evaluate_quality


def base_summary():
    return {
        "source_table_route_value_normalizer_quality_status": "PASS",
        "source_table_route_value_normalizer_record_count": 20,
        "source_normalized_table_value_record_count": 3273,
        "table_route_value_audit_record_count": 20,
        "audited_table_count": 19,
        "promoted_table_value_evidence_record_count": 2000,
        "search_ready_evidence_record_count": 2000,
        "covered_part_number_promoted_count": 151,
        "manual_page_reference_promoted_count": 39,
        "ipl_part_number_promoted_count": 767,
        "unsafe_table_route_value_audit_record_count": 0,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }


def test_quality_passes():
    status, failures = evaluate_quality(base_summary(), {
        "min_source_normalizer_records": 20,
        "min_source_normalized_records": 1,
        "min_audit_records": 20,
        "min_audited_tables": 19,
        "min_promoted_evidence_records": 1,
        "min_search_ready_evidence_records": 1,
        "min_covered_part_number_promoted": 1,
        "min_manual_page_reference_promoted": 1,
        "min_ipl_part_number_promoted": 1,
        "max_unsafe_records": 0,
        "max_answer_permission_count": 0,
        "max_source_truth_mutation_allowed": 0,
        "require_table_route_value_normalizer_quality_pass": True,
        "require_no_answer_permission": True,
    })
    assert status == "PASS"
    assert failures == []


def test_quality_fails_on_missing_promoted_evidence():
    summary = base_summary()
    summary["search_ready_evidence_record_count"] = 0
    status, failures = evaluate_quality(summary, {"min_search_ready_evidence_records": 1})
    assert status == "FAIL"
    assert "search_ready_evidence_record_count_below_min" in failures


def test_quality_fails_on_write_attempt():
    summary = base_summary()
    summary["opensearch_write_attempt_count"] = 1
    status, failures = evaluate_quality(summary, {})
    assert status == "FAIL"
    assert "write_attempt_detected" in failures
