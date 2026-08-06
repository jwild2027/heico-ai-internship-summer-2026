from tiff.trace_net_table_geometry_review_bridge_v1 import QualityThresholds
from tiff.trace_net_table_geometry_review_bridge_v1_quality import check_report


def test_quality_checker_passes_clean_summary():
    report = {
        "schema_version": "trace_net_table_geometry_review_bridge_v1",
        "quality_status": "PASS",
        "summary": {
            "source_quality_status": "PASS",
            "source_table_geometry_card_count": 20,
            "review_task_count": 20,
            "unsafe_source_card_count": 0,
            "unsafe_review_task_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
    }
    quality = check_report(
        report,
        QualityThresholds(
            min_review_tasks=1,
            min_source_cards=1,
            require_source_quality_pass=True,
            require_no_answer_permission=True,
        ),
    )
    assert quality["quality_status"] == "PASS"
    assert quality["checks"]["answer_permission_zero"] is True


def test_quality_checker_fails_on_answer_permission():
    report = {
        "schema_version": "trace_net_table_geometry_review_bridge_v1",
        "summary": {
            "source_quality_status": "PASS",
            "source_table_geometry_card_count": 1,
            "review_task_count": 1,
            "unsafe_source_card_count": 0,
            "unsafe_review_task_count": 0,
            "answer_permission_count": 1,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
    }
    quality = check_report(report, QualityThresholds(require_no_answer_permission=True))
    assert quality["quality_status"] == "FAIL"
    assert any("answer_permission_count" in e for e in quality["quality_errors"])
