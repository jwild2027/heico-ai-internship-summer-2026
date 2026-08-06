from tiff.trace_net_table_structure_bbox_localizer_v1_quality import evaluate_report


def test_quality_evaluate_report_passes_clean_summary():
    report = {
        "summary": {
            "source_table_visual_bbox_localizer_quality_status": "PASS",
            "source_table_bbox_scoped_cell_extraction_quality_status": "PASS",
            "source_visual_record_count": 20,
            "structure_record_count": 20,
            "structure_selected_bbox_record_count": 20,
            "structure_visual_bbox_rejected_count": 7,
            "unsafe_table_structure_bbox_localizer_record_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        }
    }
    quality = evaluate_report(report, {
        "min_source_visual_records": 20,
        "min_structure_records": 20,
        "min_selected_bbox_records": 20,
        "min_visual_bbox_rejected_records": 1,
        "max_unsafe_records": 0,
        "max_answer_permission_count": 0,
        "max_source_truth_mutation_allowed": 0,
        "require_table_visual_bbox_localizer_quality_pass": True,
        "require_table_bbox_scoped_cell_extraction_quality_pass": True,
        "require_all_records_selected_bbox_ready": True,
    })
    assert quality["status"] == "PASS"


def test_quality_fails_when_answer_permission_leaks():
    report = {"summary": {"source_visual_record_count": 1, "structure_record_count": 1, "structure_selected_bbox_record_count": 1, "answer_permission_count": 1}}
    quality = evaluate_report(report, {"max_answer_permission_count": 0})
    assert quality["status"] == "FAIL"
