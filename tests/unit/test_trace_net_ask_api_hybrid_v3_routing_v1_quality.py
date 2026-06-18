from tiff.trace_net_ask_api_hybrid_v3_routing_v1 import quality_report


def _report(hybrid_status="PASS", mutation_count=0):
    return {
        "schema_version": "trace_net_ask_api_hybrid_v3_routing_v1",
        "quality_status": "PASS",
        "summary": {
            "read_only_api": True,
            "hybrid_v3_routing_available": hybrid_status == "PASS",
            "hybrid_v3_quality_status": hybrid_status,
            "source_truth_mutation_allowed_count": mutation_count,
            "feedback_as_proof_count": 0,
            "community_as_proof_count": 0,
            "category_as_proof_count": 0,
            "corrective_action_as_proof_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
    }


def test_quality_passes_when_hybrid_v3_is_pass_and_safety_counters_are_zero():
    quality = quality_report(_report(), require_hybrid_v3_quality_pass=True)
    assert quality["quality_status"] == "PASS"
    assert quality["checks"]["hybrid_v3_quality_pass"] is True
    assert quality["checks"]["write_attempts_zero"] is True


def test_quality_fails_when_hybrid_v3_is_not_pass_but_required():
    quality = quality_report(_report(hybrid_status="FAIL"), require_hybrid_v3_quality_pass=True)
    assert quality["quality_status"] == "FAIL"
    assert quality["checks"]["hybrid_v3_quality_pass"] is False


def test_quality_fails_on_source_truth_mutation_counter():
    quality = quality_report(_report(mutation_count=1), require_hybrid_v3_quality_pass=True)
    assert quality["quality_status"] == "FAIL"
    assert quality["checks"]["source_truth_mutation_allowed_zero"] is False
