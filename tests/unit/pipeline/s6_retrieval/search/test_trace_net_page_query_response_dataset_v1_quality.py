from tiff.trace_net_page_query_response_dataset_v1 import quality_checks, summarize


def test_quality_checks_fail_on_low_counts():
    status, checks = quality_checks(
        {
            "source_eval_quality_status": "PASS",
            "record_count": 1,
            "response_count": 1,
            "blank_response_count": 0,
            "graph_path_resolved_count": 1,
            "source_identity_resolved_count": 1,
            "qdrant_evaluated_record_count": 1,
            "unsafe_response_count": 0,
            "answer_capable_response_count": 0,
            "claim_proof_response_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
        },
        {
            "min_records": 2,
            "min_responses": 2,
            "min_blank_responses": 1,
            "min_graph_path_resolved": 2,
            "min_source_identity_resolved": 2,
            "min_qdrant_evaluated": 2,
            "max_unsafe_responses": 0,
            "max_answer_capable_responses": 0,
            "max_claim_proof_responses": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_eval_quality_pass": True,
            "require_no_answer_permission": True,
        },
    )
    assert status == "FAIL"
    assert any(not c["ok"] for c in checks)


def test_summarize_has_zero_permission_counts():
    summary = summarize(
        [
            {
                "response": "Page x resolved.",
                "question": "What is page x?",
                "blank_expected": False,
                "graph_path": {"graph_path_resolved": True, "source_identity_resolved": True},
                "qdrant_eval": {"evaluated": True, "target_hit_at_k": True},
                "page_role": "page_context",
            }
        ],
        {"quality_status": "PASS", "status": "OK", "summary": {}},
    )
    assert summary["can_answer_directly_count"] == 0
    assert summary["can_prove_claims_count"] == 0
    assert summary["source_truth_mutation_allowed_count"] == 0
    assert summary["qdrant_target_hit_at_k_rate"] == 1.0
