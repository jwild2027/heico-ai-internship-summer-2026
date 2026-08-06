from tiff.trace_net_table_full_enclosure_bbox_reconstructor_v1_quality import evaluate_report


def test_quality_evaluate_report_passes_required_thresholds():
    report = {
        "summary": {
            "source_table_structure_bbox_localizer_quality_status": "PASS",
            "source_table_presence_verifier_quality_status": "PASS",
            "source_structure_record_count": 20,
            "source_presence_record_count": 20,
            "full_enclosure_reconstructor_record_count": 20,
            "final_table_bbox_ready_record_count": 20,
            "full_table_enclosure_recommended_record_count": 18,
            "full_table_enclosure_reconstructed_record_count": 18,
            "unsafe_table_full_enclosure_bbox_record_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        }
    }
    quality = evaluate_report(report, {
        "min_source_structure_records": 20,
        "min_source_presence_records": 20,
        "min_reconstructor_records": 20,
        "min_final_bbox_ready_records": 20,
        "min_full_enclosure_reconstructed_records": 18,
        "max_unsafe_records": 0,
        "max_answer_permission_count": 0,
        "max_source_truth_mutation_allowed": 0,
        "require_table_structure_bbox_localizer_quality_pass": True,
        "require_table_presence_verifier_quality_pass": True,
        "require_all_final_bboxes_ready": True,
        "require_all_recommended_reconstructed": True,
    })
    assert quality["status"] == "PASS"


def test_quality_evaluate_report_fails_when_recommended_not_reconstructed():
    report = {
        "summary": {
            "source_table_structure_bbox_localizer_quality_status": "PASS",
            "source_table_presence_verifier_quality_status": "PASS",
            "source_structure_record_count": 20,
            "source_presence_record_count": 20,
            "full_enclosure_reconstructor_record_count": 20,
            "final_table_bbox_ready_record_count": 20,
            "full_table_enclosure_recommended_record_count": 18,
            "full_table_enclosure_reconstructed_record_count": 17,
            "unsafe_table_full_enclosure_bbox_record_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        }
    }
    quality = evaluate_report(report, {"require_all_recommended_reconstructed": True})
    assert quality["status"] == "FAIL"


def test_quality_requires_bounded_content_band_and_review_only_when_requested():
    report = {
        "summary": {
            "source_structure_record_count": 20,
            "source_presence_record_count": 20,
            "full_enclosure_reconstructor_record_count": 20,
            "final_table_bbox_ready_record_count": 19,
            "full_table_enclosure_reconstructed_record_count": 18,
            "bounded_table_content_band_record_count": 18,
            "diagram_or_image_review_only_record_count": 1,
            "unsafe_table_full_enclosure_bbox_record_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        }
    }
    quality = evaluate_report(report, {
        "min_bounded_content_band_records": 18,
        "min_diagram_or_image_review_only_records": 1,
        "min_final_bbox_ready_records": 19,
    })
    assert quality["status"] == "PASS"


def test_quality_requires_full_page_bbox_records_when_requested():
    report = {
        "summary": {
            "source_structure_record_count": 20,
            "source_presence_record_count": 20,
            "full_enclosure_reconstructor_record_count": 20,
            "final_table_bbox_ready_record_count": 19,
            "full_table_enclosure_reconstructed_record_count": 19,
            "full_page_bbox_applied_record_count": 19,
            "unsafe_table_full_enclosure_bbox_record_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        }
    }
    quality = evaluate_report(report, {"min_full_page_bbox_records": 19})
    assert quality["status"] == "PASS"
