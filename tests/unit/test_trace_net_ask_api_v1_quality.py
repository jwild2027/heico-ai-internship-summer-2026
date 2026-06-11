from tiff.trace_net_ask_api_v1 import quality_report


def test_quality_report_passes_read_only_report() -> None:
    report = {
        "schema_version": "trace_net_ask_api_v1",
        "summary": {
            "read_only_api": True,
            "source_truth_mutation_allowed_count": 0,
            "feedback_as_proof_count": 0,
            "community_as_proof_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "final_answer_quality_status": "PASS",
        },
    }
    quality = quality_report(report, require_final_answer_quality_pass=True)
    assert quality["quality_status"] == "PASS"


def test_quality_report_fails_mutation_count() -> None:
    report = {
        "schema_version": "trace_net_ask_api_v1",
        "summary": {
            "read_only_api": True,
            "source_truth_mutation_allowed_count": 1,
            "feedback_as_proof_count": 0,
            "community_as_proof_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
    }
    quality = quality_report(report)
    assert quality["quality_status"] == "FAIL"
    assert quality["checks"]["source_truth_mutation_allowed_ok"] is False


def test_quality_report_fails_write_attempt() -> None:
    report = {
        "schema_version": "trace_net_ask_api_v1",
        "summary": {
            "read_only_api": True,
            "source_truth_mutation_allowed_count": 0,
            "feedback_as_proof_count": 0,
            "community_as_proof_count": 0,
            "postgres_write_attempt_count": 1,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
    }
    quality = quality_report(report)
    assert quality["quality_status"] == "FAIL"
    assert quality["checks"]["write_attempts_zero"] is False
