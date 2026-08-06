from tiff.trace_net_dynamic_final_gate_execution_v1 import quality_report


def test_quality_report_passes_clean_retrieval_only_result():
    report = {
        "query_results": [
            {"answer_status": "DYNAMIC_FINAL_GATE_RETRIEVAL_ONLY", "final_answer_allowed": False, "blocked_claims": []}
        ],
        "summary": {
            "dynamic_gate_query_count": 1,
            "uncited_final_claim_count": 0,
            "retrieval_only_final_claim_count": 0,
            "feedback_as_proof_count": 0,
            "community_as_proof_count": 0,
            "category_as_proof_count": 0,
            "local_path_leak_count": 0,
            "raw_bytes_repr_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "hybrid_v2_quality_status": "PASS",
            "final_answer_gate_quality_status": "PASS",
        },
    }
    q = quality_report(report, require_hybrid_v2_quality_pass=True, require_final_answer_quality_pass=True)
    assert q["status"] == "PASS"


def test_quality_report_requires_hybrid_quality_when_requested():
    report = {
        "query_results": [{}],
        "summary": {
            "dynamic_gate_query_count": 1,
            "uncited_final_claim_count": 0,
            "retrieval_only_final_claim_count": 0,
            "feedback_as_proof_count": 0,
            "community_as_proof_count": 0,
            "category_as_proof_count": 0,
            "local_path_leak_count": 0,
            "raw_bytes_repr_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "hybrid_v2_quality_status": "FAIL",
        },
    }
    q = quality_report(report, require_hybrid_v2_quality_pass=True)
    assert q["status"] == "FAIL"
