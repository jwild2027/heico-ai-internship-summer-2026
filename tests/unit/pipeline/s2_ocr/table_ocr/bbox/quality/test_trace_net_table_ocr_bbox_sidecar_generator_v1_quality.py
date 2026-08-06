from tiff.trace_net_table_ocr_bbox_sidecar_generator_v1_quality import (
    SidecarQualityThresholds,
    evaluate_sidecar_generator_quality,
)


def test_quality_passes_clean_report():
    report = {
        "schema_version": "trace_net_table_ocr_bbox_sidecar_generator_v1",
        "summary": {
            "source_table_image_card_count": 20,
            "attempted_page_count": 20,
            "generated_sidecar_page_count": 20,
            "ocr_word_record_count": 300,
            "part_number_match_count": 4,
            "unsafe_sidecar_card_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "table_image_resolver_quality_status": "PASS",
            "tesseract_available": True,
        }
    }
    quality = evaluate_sidecar_generator_quality(
        report,
        SidecarQualityThresholds(
            min_source_cards=1,
            min_attempted_pages=1,
            min_generated_sidecar_pages=1,
            min_ocr_word_records=1,
            min_part_number_matches=1,
            require_table_image_resolver_quality_pass=True,
            require_no_answer_permission=True,
            require_tesseract_available=True,
        ),
    )
    assert quality["quality_status"] == "PASS"


def test_quality_fails_when_sidecars_missing():
    report = {
        "schema_version": "trace_net_table_ocr_bbox_sidecar_generator_v1",
        "summary": {
            "source_table_image_card_count": 20,
            "attempted_page_count": 20,
            "generated_sidecar_page_count": 0,
            "ocr_word_record_count": 0,
            "unsafe_sidecar_card_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        }
    }
    quality = evaluate_sidecar_generator_quality(report, SidecarQualityThresholds(min_generated_sidecar_pages=1, min_ocr_word_records=1))
    assert quality["quality_status"] == "FAIL"
    assert "generated_sidecar_pages_min_met" in quality["quality_fail_reasons"]

