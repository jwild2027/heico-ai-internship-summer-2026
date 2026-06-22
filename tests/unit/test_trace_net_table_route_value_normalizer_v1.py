from pathlib import Path

from tiff.trace_net_table_route_value_normalizer_v1 import build_report, normalize_part_number


def sample_source_report():
    values = [
        {
            "value_record_id": "v1",
            "cell_id": "c1",
            "row_id": "r1",
            "page_id": "p1",
            "table_id": "t1",
            "table_template_type": "part_number_coverage_list",
            "template_value_role": "covered_part_number",
            "value_kind": "part_number",
            "normalized_value": "B= 120-36834-519",
            "part_number_candidates": ["120-36834-519"],
            "row_index": 1,
            "column_index": 0,
        },
        {
            "value_record_id": "v2",
            "cell_id": "c2",
            "row_id": "r2",
            "page_id": "p2",
            "table_id": "t2",
            "table_template_type": "list_of_effective_pages",
            "template_value_role": "manual_page_reference",
            "value_kind": "text",
            "normalized_value": "25-21-00-101",
            "part_number_candidates": [],
            "row_index": 2,
            "column_index": 0,
        },
        {
            "value_record_id": "v3",
            "cell_id": "c3",
            "row_id": "r3",
            "page_id": "p3",
            "table_id": "t3",
            "table_template_type": "ipl_split_column_table",
            "template_value_role": "part_number",
            "value_kind": "part_number",
            "normalized_value": "120-29083-001",
            "part_number_candidates": ["120-29083-001"],
            "row_index": 3,
            "column_index": 2,
        },
        {
            "value_record_id": "v4",
            "cell_id": "c4",
            "row_id": "r4",
            "page_id": "p3",
            "table_id": "t3",
            "table_template_type": "ipl_split_column_table",
            "template_value_role": "fig_item_or_quantity",
            "value_kind": "numeric",
            "normalized_value": "10",
            "part_number_candidates": [],
            "row_index": 3,
            "column_index": 0,
        },
    ]
    records = [
        {"page_id": "p1", "table_id": "t1", "table_extraction_allowed": True, "table_bbox_review_only": False, "table_template_type": "part_number_coverage_list", "table_template_confidence": 0.99},
        {"page_id": "p2", "table_id": "t2", "table_extraction_allowed": True, "table_bbox_review_only": False, "table_template_type": "list_of_effective_pages", "table_template_confidence": 0.99},
        {"page_id": "p3", "table_id": "t3", "table_extraction_allowed": True, "table_bbox_review_only": False, "table_template_type": "ipl_split_column_table", "table_template_confidence": 0.99},
        {"page_id": "p4", "table_id": "t4", "table_extraction_allowed": False, "table_bbox_review_only": True, "table_template_type": "unknown_table_template"},
    ]
    return {
        "schema_version": "trace_net_table_route_cell_extractor_v1",
        "status": "TABLE_ROUTE_CELL_EXTRACTOR_BUILT",
        "quality_status": "PASS",
        "summary": {"template_detected_table_count": 3},
        "table_route_cell_extraction_records": records,
        "table_route_value_records": values,
    }


def test_normalize_part_number_extracts_inner_value():
    assert normalize_part_number("B= 120-36834-519") == "120-36834-519"


def test_build_report_creates_fielded_records(tmp_path: Path):
    report = build_report(sample_source_report(), tmp_path, {
        "min_source_cell_extraction_records": 4,
        "min_source_value_records": 4,
        "min_normalizer_records": 4,
        "min_normalized_records": 4,
        "min_normalized_tables": 3,
        "min_covered_part_number_records": 1,
        "min_manual_page_reference_records": 1,
        "min_ipl_part_number_records": 1,
        "max_unsafe_records": 0,
        "max_answer_permission_count": 0,
        "max_source_truth_mutation_allowed": 0,
        "require_table_route_cell_extractor_quality_pass": True,
        "require_no_answer_permission": True,
    })
    assert report["quality_status"] == "PASS"
    summary = report["summary"]
    assert summary["covered_part_number_record_count"] == 1
    assert summary["manual_page_reference_record_count"] == 1
    assert summary["ipl_part_number_record_count"] == 1
    assert summary["ipl_figure_item_or_quantity_record_count"] == 1
    assert summary["review_only_source_skipped_count"] == 1
    fields = {r["field_name"] for r in report["table_route_normalized_value_records"]}
    assert {"covered_part_number", "manual_page_reference", "ipl_part_number", "ipl_figure_item_or_quantity"}.issubset(fields)


def test_records_are_retrieval_only_and_no_writes(tmp_path: Path):
    report = build_report(sample_source_report(), tmp_path, {})
    for record in report["table_route_normalized_value_records"]:
        assert record["retrieval_only"] is True
        assert record["answer_permission"] is False
        assert record["can_answer_directly"] is False
        assert record["can_prove_claims"] is False
        assert record["source_truth_mutation_allowed"] is False
        assert record["postgres_write_attempted"] is False
        assert record["qdrant_write_attempted"] is False
        assert record["opensearch_write_attempted"] is False


def test_lep_row_reconstruction_recovers_fragmented_page_references(tmp_path: Path):
    source = {
        "schema_version": "trace_net_table_route_cell_extractor_v1",
        "status": "TABLE_ROUTE_CELL_EXTRACTOR_BUILT",
        "quality_status": "PASS",
        "summary": {"template_detected_table_count": 1},
        "table_route_cell_extraction_records": [
            {
                "page_id": "p_lep",
                "table_id": "t_lep",
                "table_extraction_allowed": True,
                "table_bbox_review_only": False,
                "table_template_type": "list_of_effective_pages",
                "table_template_confidence": 0.99,
            }
        ],
        "table_route_value_records": [
            {
                "value_record_id": "lep1",
                "cell_id": "c1",
                "row_id": "r1",
                "page_id": "p_lep",
                "table_id": "t_lep",
                "table_template_type": "list_of_effective_pages",
                "template_value_role": "lep_other",
                "value_kind": "text",
                "normalized_value": "25-21",
                "row_index": 7,
                "column_index": 0,
            },
            {
                "value_record_id": "lep2",
                "cell_id": "c2",
                "row_id": "r1",
                "page_id": "p_lep",
                "table_id": "t_lep",
                "table_template_type": "list_of_effective_pages",
                "template_value_role": "lep_other",
                "value_kind": "text",
                "normalized_value": "-00-",
                "row_index": 7,
                "column_index": 1,
            },
            {
                "value_record_id": "lep3",
                "cell_id": "c3",
                "row_id": "r1",
                "page_id": "p_lep",
                "table_id": "t_lep",
                "table_template_type": "list_of_effective_pages",
                "template_value_role": "lep_other",
                "value_kind": "numeric",
                "normalized_value": "103",
                "row_index": 7,
                "column_index": 2,
            },
        ],
    }
    report = build_report(source, tmp_path, {
        "min_source_cell_extraction_records": 1,
        "min_source_value_records": 3,
        "min_normalizer_records": 1,
        "min_normalized_records": 1,
        "min_normalized_tables": 1,
        "min_manual_page_reference_records": 1,
        "min_lep_row_derived_manual_page_reference_records": 1,
        "max_lep_context_records": 0,
        "require_table_route_cell_extractor_quality_pass": True,
        "require_no_answer_permission": True,
    })
    assert report["quality_status"] == "PASS"
    summary = report["summary"]
    assert summary["manual_page_reference_record_count"] == 1
    assert summary["lep_row_derived_manual_page_reference_record_count"] == 1
    assert summary["lep_context_record_count"] == 0
    assert summary["lep_context_suppressed_record_count"] == 3
    refs = [r for r in report["table_route_normalized_value_records"] if r["field_name"] == "manual_page_reference"]
    assert refs[0]["normalized_value"] == "25-21-00-103"
    assert refs[0]["source_template_value_role"] == "lep_row_derived_manual_page_reference"


def test_lep_row_reconstruction_recovers_digit_split_page_reference(tmp_path: Path):
    source = {
        "schema_version": "trace_net_table_route_cell_extractor_v1",
        "status": "TABLE_ROUTE_CELL_EXTRACTOR_BUILT",
        "quality_status": "PASS",
        "summary": {"template_detected_table_count": 1},
        "table_route_cell_extraction_records": [
            {
                "page_id": "p_lep_split",
                "table_id": "t_lep_split",
                "table_extraction_allowed": True,
                "table_bbox_review_only": False,
                "table_template_type": "list_of_effective_pages",
                "table_template_confidence": 0.99,
            }
        ],
        "table_route_value_records": [
            {
                "value_record_id": "s1",
                "cell_id": "c1",
                "row_id": "r1",
                "page_id": "p_lep_split",
                "table_id": "t_lep_split",
                "table_template_type": "list_of_effective_pages",
                "template_value_role": "header",
                "value_kind": "text",
                "normalized_value": "25-2",
                "row_index": 4,
                "column_index": 0,
            },
            {
                "value_record_id": "s2",
                "cell_id": "c2",
                "row_id": "r1",
                "page_id": "p_lep_split",
                "table_id": "t_lep_split",
                "table_template_type": "list_of_effective_pages",
                "template_value_role": "header",
                "value_kind": "text",
                "normalized_value": "1-00-92",
                "row_index": 4,
                "column_index": 1,
            },
        ],
    }
    report = build_report(source, tmp_path, {
        "min_source_cell_extraction_records": 1,
        "min_source_value_records": 2,
        "min_normalizer_records": 1,
        "min_normalized_records": 1,
        "min_normalized_tables": 1,
        "min_manual_page_reference_records": 1,
        "min_lep_row_derived_manual_page_reference_records": 1,
        "max_lep_context_records": 0,
        "require_table_route_cell_extractor_quality_pass": True,
        "require_no_answer_permission": True,
    })
    assert report["quality_status"] == "PASS"
    refs = [r for r in report["table_route_normalized_value_records"] if r["field_name"] == "manual_page_reference"]
    assert [r["normalized_value"] for r in refs] == ["25-21-00-92"]
    assert report["summary"]["lep_context_record_count"] == 0
    assert report["summary"]["lep_context_suppressed_record_count"] == 2


def test_existing_lep_manual_reference_is_marked_row_derived_when_verified(tmp_path: Path):
    source = {
        "schema_version": "trace_net_table_route_cell_extractor_v1",
        "status": "TABLE_ROUTE_CELL_EXTRACTOR_BUILT",
        "quality_status": "PASS",
        "summary": {"template_detected_table_count": 1},
        "table_route_cell_extraction_records": [
            {
                "page_id": "p_lep_existing",
                "table_id": "t_lep_existing",
                "table_extraction_allowed": True,
                "table_bbox_review_only": False,
                "table_template_type": "list_of_effective_pages",
                "table_template_confidence": 0.99,
            }
        ],
        "table_route_value_records": [
            {
                "value_record_id": "existing_ref",
                "cell_id": "c1",
                "row_id": "r1",
                "page_id": "p_lep_existing",
                "table_id": "t_lep_existing",
                "table_template_type": "list_of_effective_pages",
                "template_value_role": "manual_page_reference",
                "value_kind": "text",
                "normalized_value": "25-21-00-103",
                "row_index": 7,
                "column_index": 0,
            },
            {
                "value_record_id": "seq",
                "cell_id": "c2",
                "row_id": "r1",
                "page_id": "p_lep_existing",
                "table_id": "t_lep_existing",
                "table_template_type": "list_of_effective_pages",
                "template_value_role": "lep_other",
                "value_kind": "short_code",
                "normalized_value": "A",
                "row_index": 7,
                "column_index": 1,
            },
        ],
    }
    report = build_report(source, tmp_path, {
        "min_source_cell_extraction_records": 1,
        "min_source_value_records": 2,
        "min_normalizer_records": 1,
        "min_normalized_records": 1,
        "min_normalized_tables": 1,
        "min_manual_page_reference_records": 1,
        "min_lep_row_derived_manual_page_reference_records": 1,
        "max_lep_context_records": 0,
        "require_table_route_cell_extractor_quality_pass": True,
        "require_no_answer_permission": True,
    })
    assert report["quality_status"] == "PASS"
    refs = [r for r in report["table_route_normalized_value_records"] if r["field_name"] == "manual_page_reference"]
    assert len(refs) == 1
    assert refs[0]["source_template_value_role"] == "lep_row_derived_manual_page_reference"
    assert "row_level_existing_value_verified" in refs[0]["normalization_flags"]


def test_lep_table_with_no_fielded_rows_keeps_single_coverage_marker(tmp_path: Path):
    source = {
        "schema_version": "trace_net_table_route_cell_extractor_v1",
        "status": "TABLE_ROUTE_CELL_EXTRACTOR_BUILT",
        "quality_status": "PASS",
        "summary": {"template_detected_table_count": 1},
        "table_route_cell_extraction_records": [
            {
                "page_id": "p_lep_empty",
                "table_id": "t_lep_empty",
                "table_extraction_allowed": True,
                "table_bbox_review_only": False,
                "table_template_type": "list_of_effective_pages",
                "table_template_confidence": 0.65,
            }
        ],
        "table_route_value_records": [
            {
                "value_record_id": "noise1",
                "cell_id": "c1",
                "row_id": "r1",
                "page_id": "p_lep_empty",
                "table_id": "t_lep_empty",
                "table_template_type": "list_of_effective_pages",
                "template_value_role": "lep_other",
                "value_kind": "text",
                "normalized_value": "random body fragment",
                "row_index": 1,
                "column_index": 0,
            }
        ],
    }
    report = build_report(source, tmp_path, {
        "min_source_cell_extraction_records": 1,
        "min_source_value_records": 1,
        "min_normalizer_records": 1,
        "min_normalized_records": 1,
        "min_normalized_tables": 1,
        "max_lep_context_records": 1,
        "require_table_route_cell_extractor_quality_pass": True,
        "require_no_answer_permission": True,
    })
    assert report["quality_status"] == "PASS"
    summary = report["summary"]
    assert summary["normalized_table_count"] == 1
    assert summary["lep_context_record_count"] == 1
    values = report["table_route_normalized_value_records"]
    assert values[0]["source_template_value_role"] == "lep_table_presence_context"
    assert "lep_table_coverage_marker" in values[0]["normalization_flags"]
