from tiff.trace_net_table_presence_verifier_v1_quality import evaluate_report


def test_quality_passes_clean_presence_report():
    report = {
        "summary": {
            "source_structure_record_count": 20,
            "table_presence_record_count": 20,
            "table_presence_decision_record_count": 20,
            "table_localization_allowed_record_count": 18,
            "table_localization_suppressed_record_count": 2,
            "unsafe_table_presence_verifier_record_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "source_table_structure_bbox_localizer_quality_status": "PASS",
            "source_table_visual_bbox_localizer_quality_status": "PASS",
            "source_table_bbox_scoped_cell_extraction_quality_status": "PASS",
            "source_table_ocr_bbox_enrichment_quality_status": "PASS",
        }
    }
    quality = evaluate_report(report, {
        "min_source_structure_records": 20,
        "min_presence_records": 20,
        "min_presence_decisions": 20,
        "min_localization_allowed_records": 1,
        "min_suppressed_candidates": 1,
        "max_unsafe_records": 0,
        "max_answer_permission_count": 0,
        "max_source_truth_mutation_allowed": 0,
        "require_table_structure_bbox_localizer_quality_pass": True,
        "require_table_visual_bbox_localizer_quality_pass": True,
        "require_table_bbox_scoped_cell_extraction_quality_pass": True,
        "require_table_ocr_bbox_enrichment_quality_pass": True,
        "require_all_records_have_presence_decision": True,
    })
    assert quality["status"] == "PASS"


def test_quality_fails_unsafe_record():
    report = {
        "summary": {
            "source_structure_record_count": 1,
            "table_presence_record_count": 1,
            "table_presence_decision_record_count": 1,
            "table_localization_allowed_record_count": 1,
            "table_localization_suppressed_record_count": 0,
            "unsafe_table_presence_verifier_record_count": 1,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        }
    }
    quality = evaluate_report(report, {"max_unsafe_records": 0})
    assert quality["status"] == "FAIL"
