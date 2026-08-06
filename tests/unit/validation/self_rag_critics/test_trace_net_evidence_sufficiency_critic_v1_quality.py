from tiff.trace_net_evidence_sufficiency_critic_v1 import quality_report


def base_report(**summary_overrides):
    summary = {
        "status": "PASS",
        "sufficiency_record_count": 2,
        "query_count": 2,
        "sufficiency_can_answer_directly_count": 0,
        "sufficiency_can_prove_claims_count": 0,
        "unsafe_sufficiency_record_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "feedback_as_proof_count": 0,
        "community_as_proof_count": 0,
        "category_as_proof_count": 0,
        "raw_feedback_direct_to_llm_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "hybrid_v2_quality_status": "PASS",
        "dynamic_final_gate_quality_status": "PASS",
        "retrieval_critic_quality_status": "PASS",
    }
    summary.update(summary_overrides)
    return {"summary": summary}


def test_quality_passes_with_safe_counts():
    q = quality_report(
        base_report(),
        min_sufficiency_records=1,
        min_queries=1,
        require_hybrid_v2_quality_pass=True,
        require_dynamic_final_gate_quality_pass=True,
        require_retrieval_critic_quality_pass=True,
    )
    assert q["status"] == "PASS"


def test_quality_fails_on_answer_capable_critic():
    q = quality_report(base_report(sufficiency_can_answer_directly_count=1), min_sufficiency_records=1, min_queries=1)
    assert q["status"] == "FAIL"
    assert q["checks"]["sufficiency_can_answer_directly_zero"] is False


def test_quality_fails_on_source_truth_mutation():
    q = quality_report(base_report(source_truth_mutation_allowed_count=1), min_sufficiency_records=1, min_queries=1)
    assert q["status"] == "FAIL"
    assert q["checks"]["source_truth_mutation_allowed_zero"] is False


def test_quality_fails_when_required_source_quality_missing():
    q = quality_report(base_report(hybrid_v2_quality_status=""), min_sufficiency_records=1, min_queries=1, require_hybrid_v2_quality_pass=True)
    assert q["status"] == "FAIL"
    assert q["checks"]["hybrid_v2_quality_pass"] is False
