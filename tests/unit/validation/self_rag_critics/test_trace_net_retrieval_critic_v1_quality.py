from __future__ import annotations

from tiff.trace_net_retrieval_critic_v1 import quality_report, summarize


def test_quality_report_fails_when_critic_can_answer():
    report = {
        "critic_records": [
            {
                "query": "x",
                "critic_status": "bad",
                "can_answer_directly": True,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            }
        ],
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }
    report["summary"] = summarize(report)
    q = quality_report(report, min_critic_records=1, min_queries=1)
    assert q["status"] == "FAIL"
    assert q["checks"]["critic_can_answer_directly_zero"] is False


def test_quality_report_can_require_hybrid_pass():
    report = {
        "critic_records": [
            {
                "query": "x",
                "critic_status": "abstain_no_evidence",
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            }
        ],
        "source_quality_statuses": {"hybrid_v2": "PASS"},
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }
    report["summary"] = summarize(report)
    q = quality_report(report, min_critic_records=1, min_queries=1, require_hybrid_v2_quality_pass=True)
    assert q["status"] == "PASS"
    assert q["checks"]["hybrid_v2_quality_pass"] is True
