from tiff.trace_net_table_crop_margin_expansion_experiment_v1 import Thresholds, evaluate_checks


def test_quality_checks_pass():
    summary = {
        "schema_version": "trace_net_table_crop_margin_expansion_experiment_v1",
        "diagnostic_card_count": 20,
        "margin_candidate_card_count": 120,
        "successful_image_card_count": 20,
        "unsafe_diagnostic_card_count": 0,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "source_quality_statuses": {"table_line_geometry": "PASS", "table_bbox_resolver": "PASS"},
    }
    checks = evaluate_checks(summary, Thresholds(min_diagnostic_cards=20, min_margin_candidate_cards=1, min_successful_image_cards=1, require_table_line_geometry_quality_pass=True, require_table_bbox_resolver_quality_pass=True, require_no_answer_permission=True))
    assert all(checks.values())


def test_quality_checks_fail_on_answer_permission():
    summary = {
        "schema_version": "trace_net_table_crop_margin_expansion_experiment_v1",
        "diagnostic_card_count": 1,
        "margin_candidate_card_count": 1,
        "successful_image_card_count": 1,
        "unsafe_diagnostic_card_count": 0,
        "answer_permission_count": 1,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "source_quality_statuses": {},
    }
    checks = evaluate_checks(summary, Thresholds(require_no_answer_permission=True))
    assert checks["answer_permission_zero"] is False
