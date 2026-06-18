from tiff.trace_net_table_crop_selection_diagnostics_v1 import build_quality_payload


def test_quality_payload_passes_for_clean_report():
    report = {
        "schema_version": "trace_net_table_crop_selection_diagnostics_v1",
        "quality_status": "PASS",
        "summary": {
            "diagnostic_card_count": 1,
            "crop_selected_card_count": 1,
            "unsafe_diagnostic_card_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
    }
    payload = build_quality_payload(report)
    assert payload["quality_status"] == "PASS"
    assert payload["checks"]["answer_permission_zero"] is True


def test_quality_payload_fails_for_answer_permission():
    report = {
        "schema_version": "trace_net_table_crop_selection_diagnostics_v1",
        "quality_status": "PASS",
        "summary": {
            "diagnostic_card_count": 1,
            "crop_selected_card_count": 1,
            "unsafe_diagnostic_card_count": 0,
            "answer_permission_count": 1,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
    }
    payload = build_quality_payload(report)
    assert payload["quality_status"] == "FAIL"
    assert payload["checks"]["answer_permission_zero"] is False
