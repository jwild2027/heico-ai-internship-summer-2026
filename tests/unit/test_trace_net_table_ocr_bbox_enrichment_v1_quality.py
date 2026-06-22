from tiff.trace_net_table_ocr_bbox_enrichment_v1 import build_quality_payload


def test_quality_fails_when_crop_candidate_required_but_absent():
    report = {
        "schema_version": "trace_net_table_ocr_bbox_enrichment_v1",
        "summary": {
            "source_table_geometry_card_count": 1,
            "ocr_bbox_enrichment_card_count": 1,
            "crop_candidate_ready_card_count": 0,
            "unsafe_ocr_bbox_enrichment_card_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "source_quality_statuses": {"table_line_geometry": "PASS"},
        },
    }
    quality = build_quality_payload(
        report,
        {
            "min_source_cards": 1,
            "min_enrichment_cards": 1,
            "min_crop_candidate_cards": 1,
            "max_unsafe_enrichment_cards": 0,
            "max_answer_permission_count": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_table_line_geometry_quality_pass": True,
            "require_no_answer_permission": True,
        },
    )
    assert quality["quality_status"] == "FAIL"
    assert "min_crop_candidate_cards_not_met" in quality["quality_errors"]


def test_quality_passes_safety_zeroes():
    report = {
        "schema_version": "trace_net_table_ocr_bbox_enrichment_v1",
        "summary": {
            "source_table_geometry_card_count": 1,
            "ocr_bbox_enrichment_card_count": 1,
            "crop_candidate_ready_card_count": 1,
            "table_extraction_bbox_available_card_count": 1,
            "table_extraction_bbox_valid_card_count": 1,
            "table_extraction_bbox_preferred_card_count": 1,
            "table_extraction_bbox_consumed_card_count": 1,
            "unsafe_ocr_bbox_enrichment_card_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "source_quality_statuses": {"table_line_geometry": "PASS"},
        },
    }
    quality = build_quality_payload(
        report,
        {
            "min_source_cards": 1,
            "min_enrichment_cards": 1,
            "min_crop_candidate_cards": 1,
            "max_unsafe_enrichment_cards": 0,
            "max_answer_permission_count": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_table_line_geometry_quality_pass": True,
            "require_no_answer_permission": True,
        },
    )
    assert quality["quality_status"] == "PASS"
    assert quality["summary"]["table_extraction_bbox_consumed_card_count"] == 1
