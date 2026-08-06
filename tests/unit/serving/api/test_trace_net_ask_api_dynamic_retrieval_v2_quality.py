from __future__ import annotations

from tiff.trace_net_ask_api_dynamic_retrieval_v2 import quality_report


def test_quality_report_passes_for_safe_read_only_report() -> None:
    report = {
        "schema_version": "trace_net_ask_api_dynamic_retrieval_v2",
        "summary": {
            "read_only_api": True,
            "dynamic_retrieval_available": True,
            "source_truth_mutation_allowed_count": 0,
            "feedback_as_proof_count": 0,
            "community_as_proof_count": 0,
            "category_as_proof_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "final_answer_quality_status": "PASS",
        },
    }
    q = quality_report(report, require_dynamic_retrieval_available=True, require_final_answer_quality_pass=True)
    assert q["status"] == "PASS"


def test_quality_report_fails_on_write_attempt_or_proof_misuse() -> None:
    report = {
        "schema_version": "trace_net_ask_api_dynamic_retrieval_v2",
        "summary": {
            "read_only_api": True,
            "dynamic_retrieval_available": True,
            "source_truth_mutation_allowed_count": 0,
            "feedback_as_proof_count": 1,
            "community_as_proof_count": 0,
            "category_as_proof_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "postgres_write_attempt_count": 1,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
    }
    q = quality_report(report)
    assert q["status"] == "FAIL"
    assert q["checks"]["feedback_as_proof_zero"] is False
    assert q["checks"]["write_attempts_zero"] is False
