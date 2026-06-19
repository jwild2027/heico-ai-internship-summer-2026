from tiff.trace_net_table_full_region_recovery_v1 import evaluate_quality, SCHEMA_VERSION


def test_evaluate_quality_passes():
    report = {
        "schema_version": SCHEMA_VERSION,
        "summary": {
            "recovery_card_count": 20,
            "expanded_full_table_bbox_card_count": 20,
            "ocr_content_bbox_card_count": 20,
            "unsafe_recovery_card_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "source_quality_statuses": {
                "table_bbox_resolver": "PASS",
                "table_ocr_bbox_enrichment": "PASS",
            },
        },
    }
    status, checks, reasons = evaluate_quality(
        report,
        {
            "min_recovery_cards": 20,
            "min_expanded_full_table_bbox_cards": 1,
            "min_ocr_content_bbox_cards": 1,
            "max_unsafe_recovery_cards": 0,
            "max_answer_permission_count": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_table_bbox_resolver_quality_pass": True,
            "require_table_ocr_bbox_enrichment_quality_pass": True,
            "require_no_answer_permission": True,
        },
    )
    assert status == "PASS"
    assert not reasons


def test_evaluate_quality_fails_source_quality():
    report = {
        "schema_version": SCHEMA_VERSION,
        "summary": {
            "recovery_card_count": 20,
            "expanded_full_table_bbox_card_count": 20,
            "ocr_content_bbox_card_count": 20,
            "unsafe_recovery_card_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "source_quality_statuses": {"table_bbox_resolver": "FAIL"},
        },
    }
    status, checks, reasons = evaluate_quality(report, {"require_table_bbox_resolver_quality_pass": True})
    assert status == "FAIL"
    assert "table_bbox_resolver_quality_pass" in reasons
