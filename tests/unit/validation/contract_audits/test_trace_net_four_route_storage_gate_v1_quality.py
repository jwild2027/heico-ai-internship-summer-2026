from tiff.trace_net_four_route_storage_gate_v1_quality import evaluate_storage_gate_quality


def _payload():
    return {
        "quality_status": "PASS",
        "summary": {
            "storage_gate_record_count": 509,
            "postgres_graph_record_count": 509,
            "qdrant_embedding_allowed_count": 450,
            "opensearch_index_allowed_count": 282,
            "final_do_not_embed_count": 59,
            "validator_gated_count": 45,
            "source_route_unresolved_retry_probe_quality_status": "PASS",
            "human_review_required_count": 0,
            "manual_review_required_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "unsafe_record_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "invalid_operational_route_count": 0,
        },
    }


def test_quality_passes_expected_thresholds():
    status, failures = evaluate_storage_gate_quality(
        _payload(),
        min_records=509,
        min_postgres_graph_records=509,
        min_qdrant_allowed=400,
        min_opensearch_allowed=250,
        max_final_do_not_embed=100,
        require_source_quality_pass=True,
        require_no_human_review_required=True,
        max_unsafe=0,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
        require_no_write_attempts=True,
    )
    assert status == "PASS"
    assert failures == []


def test_quality_fails_bad_do_not_embed_threshold():
    status, failures = evaluate_storage_gate_quality(_payload(), max_final_do_not_embed=10)
    assert status == "FAIL"
    assert any("final_do_not_embed_count" in failure for failure in failures)


def test_quality_fails_write_attempts():
    payload = _payload()
    payload["summary"]["qdrant_write_attempt_count"] = 1
    status, failures = evaluate_storage_gate_quality(payload, require_no_write_attempts=True)
    assert status == "FAIL"
    assert any("qdrant_write_attempt_count" in failure for failure in failures)
