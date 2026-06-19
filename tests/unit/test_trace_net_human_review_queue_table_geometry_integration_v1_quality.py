from __future__ import annotations

from tiff.trace_net_human_review_queue_table_geometry_integration_v1 import compute_quality


def test_quality_passes_for_safe_integrated_queue() -> None:
    report = {
        "summary": {
            "review_task_count": 5,
            "table_geometry_review_task_count": 2,
            "unsafe_review_task_count": 0,
            "review_task_can_answer_directly_count": 0,
            "review_task_can_prove_claims_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "table_geometry_review_bridge_quality_status": "PASS",
        }
    }
    quality = compute_quality(
        report,
        min_review_tasks=1,
        min_table_geometry_review_tasks=1,
        require_table_geometry_bridge_quality_pass=True,
        require_no_answer_permission=True,
    )
    assert quality["quality_status"] == "PASS"
    assert all(quality["checks"].values())


def test_quality_fails_for_answer_permission() -> None:
    report = {
        "summary": {
            "review_task_count": 5,
            "table_geometry_review_task_count": 2,
            "unsafe_review_task_count": 0,
            "review_task_can_answer_directly_count": 0,
            "review_task_can_prove_claims_count": 0,
            "answer_permission_count": 1,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "table_geometry_review_bridge_quality_status": "PASS",
        }
    }
    quality = compute_quality(
        report,
        min_review_tasks=1,
        min_table_geometry_review_tasks=1,
        require_table_geometry_bridge_quality_pass=True,
        require_no_answer_permission=True,
    )
    assert quality["quality_status"] == "FAIL"
    assert quality["checks"]["answer_permission_zero"] is False
