from pathlib import Path

from tiff.trace_net_table_route_value_audit_v1 import build_report, is_promotable_value


def sample_normalizer_report():
    records = [
        {"normalizer_record_id": "nr1", "page_id": "p1", "table_id": "t1", "table_template_type": "part_number_coverage_list", "status": "TABLE_ROUTE_VALUE_NORMALIZER_BUILT"},
        {"normalizer_record_id": "nr2", "page_id": "p2", "table_id": "t2", "table_template_type": "list_of_effective_pages", "status": "TABLE_ROUTE_VALUE_NORMALIZER_BUILT"},
        {"normalizer_record_id": "nr3", "page_id": "p3", "table_id": "t3", "table_template_type": "ipl_split_column_table", "status": "TABLE_ROUTE_VALUE_NORMALIZER_BUILT"},
        {"normalizer_record_id": "nr4", "page_id": "p4", "table_id": "t4", "table_template_type": "unknown_table_template", "status": "TABLE_ROUTE_VALUE_NORMALIZATION_SKIPPED", "table_bbox_review_only": True},
    ]
    values = [
        {"normalized_value_record_id": "v1", "page_id": "p1", "table_id": "t1", "field_name": "covered_part_number", "normalized_value": "120-36833-001", "raw_value_text": "120-36833-001", "evidence_kind": "part_number", "normalization_confidence": 0.96, "row_index": 1, "column_index": 0},
        {"normalized_value_record_id": "v2", "page_id": "p1", "table_id": "t1", "field_name": "part_number_coverage_context", "normalized_value": "ILLUSTRATED PARTS LIST", "raw_value_text": "ILLUSTRATED PARTS LIST", "evidence_kind": "context", "normalization_confidence": 0.55, "row_index": 0, "column_index": 0},
        {"normalized_value_record_id": "v3", "page_id": "p2", "table_id": "t2", "field_name": "manual_page_reference", "normalized_value": "25-21-00-101", "raw_value_text": "25-21-00-101", "evidence_kind": "manual_page_reference", "normalization_confidence": 0.88, "row_index": 3, "column_index": 0},
        {"normalized_value_record_id": "v4", "page_id": "p2", "table_id": "t2", "field_name": "page_rev_or_sequence_value", "normalized_value": "4", "raw_value_text": "4", "evidence_kind": "lep_sequence_or_revision", "normalization_confidence": 0.76, "row_index": 3, "column_index": 1},
        {"normalized_value_record_id": "v5", "page_id": "p3", "table_id": "t3", "field_name": "ipl_part_number", "normalized_value": "120-29083-001", "raw_value_text": "120-29083-001", "evidence_kind": "part_number", "normalization_confidence": 0.90, "row_index": 5, "column_index": 2},
        {"normalized_value_record_id": "v6", "page_id": "p3", "table_id": "t3", "field_name": "ipl_figure_item_or_quantity", "normalized_value": "10", "raw_value_text": "10", "evidence_kind": "numeric", "normalization_confidence": 0.72, "row_index": 5, "column_index": 0},
    ]
    return {
        "schema_version": "trace_net_table_route_value_normalizer_v1",
        "status": "TABLE_ROUTE_VALUE_NORMALIZER_BUILT",
        "quality_status": "PASS",
        "summary": {
            "table_route_value_normalizer_record_count": 4,
            "normalized_table_value_record_count": len(values),
            "normalized_table_count": 3,
            "covered_part_number_record_count": 1,
            "manual_page_reference_record_count": 1,
            "ipl_part_number_record_count": 1,
            "review_only_source_skipped_count": 1,
        },
        "table_route_value_normalizer_records": records,
        "table_route_normalized_value_records": values,
    }


def test_context_values_are_not_promoted():
    ok, flags = is_promotable_value({"field_name": "lep_context", "evidence_kind": "context", "normalized_value": "REV", "normalization_confidence": 0.9}, 0.6)
    assert ok is False
    assert "context_only_value" in flags


def test_build_report_promotes_search_ready_values(tmp_path: Path):
    report = build_report(sample_normalizer_report(), tmp_path, {
        "min_source_normalizer_records": 4,
        "min_source_normalized_records": 1,
        "min_audit_records": 4,
        "min_audited_tables": 3,
        "min_promoted_evidence_records": 5,
        "min_search_ready_evidence_records": 5,
        "min_covered_part_number_promoted": 1,
        "min_manual_page_reference_promoted": 1,
        "min_ipl_part_number_promoted": 1,
        "max_unsafe_records": 0,
        "max_answer_permission_count": 0,
        "max_source_truth_mutation_allowed": 0,
        "require_table_route_value_normalizer_quality_pass": True,
        "require_no_answer_permission": True,
    })
    assert report["quality_status"] == "PASS"
    summary = report["summary"]
    assert summary["promoted_table_value_evidence_record_count"] == 5
    assert summary["context_only_record_count"] == 1
    assert summary["covered_part_number_promoted_count"] == 1
    assert summary["manual_page_reference_promoted_count"] == 1
    assert summary["ipl_part_number_promoted_count"] == 1
    assert summary["review_only_audit_skipped_count"] == 1


def test_promoted_records_are_read_only(tmp_path: Path):
    report = build_report(sample_normalizer_report(), tmp_path, {})
    for record in report["table_route_search_ready_value_records"]:
        assert record["retrieval_only"] is True
        assert record["search_index_candidate"] is True
        assert record["answer_permission"] is False
        assert record["can_answer_directly"] is False
        assert record["can_prove_claims"] is False
        assert record["source_truth_mutation_allowed"] is False
        assert record["postgres_write_attempted"] is False
        assert record["qdrant_write_attempted"] is False
        assert record["opensearch_write_attempted"] is False
