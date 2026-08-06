from __future__ import annotations

from tiff.trace_net_hybrid_retrieval_v2 import quality_report, summarize


def test_quality_report_fails_when_group_can_prove_claims():
    report = {
        "query_results": [
            {
                "query_id": "q",
                "query": "test",
                "ranked_group_count": 1,
                "ranked_groups": [
                    {
                        "page_id": "p1",
                        "exact_hit_count": 1,
                        "semantic_group_count": 1,
                        "can_answer_directly": False,
                        "can_prove_claims": True,
                        "source_truth_mutation_allowed": False,
                    }
                ],
            }
        ],
        "source_quality_statuses": {},
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }
    report["summary"] = summarize(report)
    q = quality_report(report, min_queries=1, min_queries_with_results=1, min_groups=1, min_exact_hit_groups=1, min_semantic_groups=1)
    assert q["status"] == "FAIL"
    assert q["summary"]["claim_proof_allowed_count"] == 1


def test_quality_report_requires_source_quality_when_requested():
    report = {
        "query_results": [
            {
                "query_id": "q",
                "query": "test",
                "ranked_group_count": 1,
                "ranked_groups": [
                    {
                        "page_id": "p1",
                        "exact_hit_count": 1,
                        "semantic_group_count": 1,
                        "can_answer_directly": False,
                        "can_prove_claims": False,
                        "source_truth_mutation_allowed": False,
                    }
                ],
            }
        ],
        "source_quality_statuses": {"opensearch_adapter": "FAIL", "hybrid_report": "PASS"},
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }
    report["summary"] = summarize(report)
    q = quality_report(report, require_opensearch_quality_pass=True)
    assert q["status"] == "FAIL"
