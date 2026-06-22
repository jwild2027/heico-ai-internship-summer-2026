from tiff.trace_net_table_bbox_scoped_cell_extraction_v1 import quality_checks


def base_summary(**overrides):
    summary = {
        "source_table_understanding_quality_status": "PASS",
        "source_table_ocr_bbox_enrichment_quality_status": "PASS",
        "source_table_record_count": 20,
        "scoped_table_record_count": 20,
        "scoped_cell_count": 120,
        "scoped_value_record_count": 120,
        "table_extraction_bbox_consumed_record_count": 20,
        "table_extraction_bbox_missing_or_invalid_record_count": 0,
        "unsafe_scoped_table_record_count": 0,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }
    summary.update(overrides)
    return summary


def thresholds(**overrides):
    values = {
        "min_source_table_records": 20,
        "min_scoped_table_records": 20,
        "min_bbox_consumed_records": 20,
        "min_scoped_cells": 1,
        "min_scoped_value_records": 1,
        "max_unsafe_scoped_table_records": 0,
        "max_answer_permission_count": 0,
        "max_source_truth_mutation_allowed": 0,
        "require_table_understanding_quality_pass": True,
        "require_table_ocr_bbox_enrichment_quality_pass": True,
        "require_all_records_bbox_scoped": True,
    }
    values.update(overrides)
    return values


def test_quality_passes_expected_shape():
    status, checks = quality_checks(base_summary(), thresholds())
    assert status == "PASS"
    assert all(check["ok"] for check in checks)


def test_quality_fails_on_unsafe_or_missing_bbox():
    status, checks = quality_checks(
        base_summary(unsafe_scoped_table_record_count=1, table_extraction_bbox_missing_or_invalid_record_count=2),
        thresholds(),
    )
    assert status == "FAIL"
    failed = {check["name"] for check in checks if not check["ok"]}
    assert "unsafe_scoped_table_records" in failed
    assert "all_bbox_target_records_scoped" in failed
