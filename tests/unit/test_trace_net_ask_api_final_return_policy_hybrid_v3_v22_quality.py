from __future__ import annotations

from tiff.trace_net_ask_api_final_return_policy_hybrid_v3_v22 import build_quality_report


def test_quality_report_fails_when_hybrid_v3_not_pass():
    report = {
        "quality_status": "FAIL",
        "summary": {
            "schema_version": "trace_net_ask_api_final_return_policy_hybrid_v3_v22",
            "read_only_api": True,
            "hybrid_v3_quality_status": "FAIL",
            "query_count": 1,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "corrective_action_as_proof_count": 0,
        },
    }
    quality = build_quality_report(report, require_hybrid_v3_quality_pass=True)
    assert quality["quality_status"] == "FAIL"


def test_quality_report_passes_for_safe_report():
    report = {
        "quality_status": "PASS",
        "summary": {
            "schema_version": "trace_net_ask_api_final_return_policy_hybrid_v3_v22",
            "read_only_api": True,
            "hybrid_v3_quality_status": "PASS",
            "query_count": 1,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "corrective_action_as_proof_count": 0,
        },
    }
    quality = build_quality_report(report, require_hybrid_v3_quality_pass=True)
    assert quality["quality_status"] == "PASS"
    assert quality["checks"]["corrective_action_as_proof_zero"] is True
