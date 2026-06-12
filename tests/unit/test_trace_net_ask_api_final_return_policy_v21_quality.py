from tiff.trace_net_ask_api_final_return_policy_v21 import quality_report


def test_quality_passes_for_safe_policy():
    report = {
        "quality_status": "PASS",
        "summary": {
            "policy_record_count": 2,
            "query_count": 2,
            "final_answer_return_allowed_count": 1,
            "unsafe_return_allowed_count": 0,
            "audit_return_allowed_count": 0,
            "hard_safety_violation_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "feedback_as_proof_count": 0,
            "community_as_proof_count": 0,
            "category_as_proof_count": 0,
            "retrieval_only_as_proof_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "local_path_leak_count": 0,
            "raw_bytes_repr_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "source_quality_statuses": {
                "dynamic_final_gate": "PASS",
                "retrieval_critic": "PASS",
                "evidence_sufficiency_critic": "PASS",
                "answer_claim_critic": "PASS",
            },
        },
    }
    q = quality_report(
        report,
        min_policy_records=2,
        min_queries=2,
        min_return_allowed=1,
        require_dynamic_final_gate_quality_pass=True,
        require_retrieval_critic_quality_pass=True,
        require_evidence_sufficiency_quality_pass=True,
        require_answer_claim_critic_quality_pass=True,
    )
    assert q["quality_status"] == "PASS"
    assert q["issue_count"] == 0


def test_quality_fails_for_unsafe_return():
    report = {
        "summary": {
            "policy_record_count": 1,
            "query_count": 1,
            "unsafe_return_allowed_count": 1,
            "audit_return_allowed_count": 0,
            "hard_safety_violation_count": 0,
        }
    }
    q = quality_report(report, min_policy_records=1, min_queries=1)
    assert q["quality_status"] == "FAIL"
    assert any(i["issue_code"] == "unsafe_return_allowed_count_must_be_zero" for i in q["issues"])
