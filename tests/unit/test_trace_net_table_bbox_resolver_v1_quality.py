from tiff.trace_net_table_bbox_resolver_v1 import evaluate_quality


def test_quality_passes_clean_summary():
    summary = {
        "source_table_geometry_card_count": 2,
        "bbox_card_count": 2,
        "crop_ready_card_count": 2,
        "unsafe_bbox_card_count": 0,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "source_quality_statuses": {"table_line_geometry": "PASS", "table_image_resolver": "PASS"},
    }
    status, reasons, checks = evaluate_quality(summary, {
        "min_source_cards": 1,
        "min_bbox_cards": 1,
        "min_crop_ready_cards": 1,
        "max_unsafe_bbox_cards": 0,
        "max_answer_permission_count": 0,
        "max_source_truth_mutation_allowed": 0,
        "require_table_line_geometry_quality_pass": True,
        "require_table_image_resolver_quality_pass": True,
        "require_no_answer_permission": True,
    })
    assert status == "PASS"
    assert reasons == []
    assert checks["answer_permission_zero"] is True


def test_quality_fails_answer_permission():
    summary = {
        "source_table_geometry_card_count": 1,
        "bbox_card_count": 1,
        "crop_ready_card_count": 1,
        "unsafe_bbox_card_count": 0,
        "answer_permission_count": 1,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "source_quality_statuses": {"table_line_geometry": "PASS", "table_image_resolver": "PASS"},
    }
    status, reasons, checks = evaluate_quality(summary, {
        "min_source_cards": 1,
        "min_bbox_cards": 1,
        "min_crop_ready_cards": 1,
        "max_unsafe_bbox_cards": 0,
        "max_answer_permission_count": 0,
        "max_source_truth_mutation_allowed": 0,
        "require_table_line_geometry_quality_pass": True,
        "require_table_image_resolver_quality_pass": True,
        "require_no_answer_permission": True,
    })
    assert status == "FAIL"
    assert checks["answer_permission_zero"] is False
