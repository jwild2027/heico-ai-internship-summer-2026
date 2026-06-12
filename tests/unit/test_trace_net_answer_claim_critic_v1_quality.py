from __future__ import annotations

from tiff.trace_net_answer_claim_critic_v1 import build_report, quality_report


def test_quality_fails_for_feedback_as_proof_text() -> None:
    dynamic = {
        "quality_status": "PASS",
        "query_results": [
            {
                "query": "bad",
                "answer_status": "DYNAMIC_FINAL_GATE_APPROVED",
                "final_answer_allowed": True,
                "final_answer_text": "Feedback proves this answer.",
                "final_claims": [
                    {
                        "claim_text": "Feedback proves this claim.",
                        "page_id": "p1",
                        "citation_ids": ["c1"],
                    }
                ],
                "uncited_final_claim_count": 0,
                "retrieval_only_final_claim_count": 0,
            }
        ],
    }
    report = build_report(dynamic_final_gate_report=dynamic)
    q = quality_report(report, min_answer_records=1, min_queries=1, min_claim_records=1)
    assert q["status"] == "FAIL"
    assert q["checks"]["feedback_as_proof_zero"] is False


def test_quality_enforces_minimums() -> None:
    report = build_report(dynamic_final_gate_report={"quality_status": "PASS", "query_results": []})
    q = quality_report(report, min_answer_records=1, min_queries=1)
    assert q["status"] == "FAIL"
    assert q["checks"]["answer_claim_record_count_minimum_met"] is False
