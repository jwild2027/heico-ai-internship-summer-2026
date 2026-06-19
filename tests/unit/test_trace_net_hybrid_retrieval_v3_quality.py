from tiff.trace_net_hybrid_retrieval_v3_quality import evaluate_quality
from tiff.trace_net_hybrid_retrieval_v3 import build_hybrid_retrieval_v3


def _hybrid_v2_payload():
    return {
        "schema_version": "trace_net_hybrid_retrieval_v2",
        "quality_status": "PASS",
        "query_results": [
            {
                "query_id": "part_120_46137_001",
                "query": "120-46137-001",
                "ranked_groups": [
                    {
                        "page_id": "t_p_120_1176_p000003",
                        "source_page_ids": ["t_p_120_1176_p000003"],
                        "hybrid_v2_score": 0.82,
                        "exact_hits": [{"page_id": "t_p_120_1176_p000003", "score": 8.5}],
                    }
                ],
            }
        ],
    }


def _planner_payload():
    return {
        "quality_status": "PASS",
        "summary": {
            "quality_status": "PASS",
            "source_quality_statuses": {"qdrant_page_profile_quality": "PASS"},
        },
        "corrective_retrieval_records": [
            {
                "record_id": "corrective_retrieval::page_retrieval_large_eval_v2::t_p_120_1176_p000003::semantic_page_target_miss",
                "issue_type": "semantic_page_target_miss",
                "severity": "HIGH",
                "recommended_actions": ["run_opensearch_exact_if_identifier_present"],
            }
        ],
    }


def _passing_payload():
    return build_hybrid_retrieval_v3(
        hybrid_v2=_hybrid_v2_payload(),
        corrective_planner=_planner_payload(),
        graph_enrichment={"quality_status": "PASS", "enriched_page_records": [{"page_id": "t_p_120_1176_p000003"}]},
        opensearch_loader_smoke={"quality_status": "PASS"},
        qdrant_page_profile_quality={"quality_status": "PASS"},
        min_queries=1,
        min_queries_with_results=1,
        min_groups=1,
        min_corrective_groups=1,
        min_review_routed_groups=1,
        require_hybrid_v2_quality_pass=True,
        require_corrective_planner_quality_pass=True,
        require_graph_enrichment_quality_pass=True,
        require_opensearch_loader_quality_pass=True,
        require_qdrant_quality_pass=True,
        require_no_answer_permission=True,
    )


def test_quality_checker_passes_clean_hybrid_v3_report():
    payload = _passing_payload()
    result = evaluate_quality(
        payload,
        min_queries=1,
        min_queries_with_results=1,
        min_groups=1,
        min_corrective_groups=1,
        min_review_routed_groups=1,
        require_hybrid_v2_quality_pass=True,
        require_corrective_planner_quality_pass=True,
        require_graph_enrichment_quality_pass=True,
        require_opensearch_loader_quality_pass=True,
        require_qdrant_quality_pass=True,
        require_no_answer_permission=True,
    )
    assert result["quality_status"] == "PASS"
    assert result["summary"]["answer_permission_count"] == 0
    assert result["summary"]["source_truth_mutation_allowed_count"] == 0


def test_quality_checker_fails_when_required_source_not_pass():
    payload = _passing_payload()
    payload["source_quality_statuses"]["corrective_retrieval_planner"] = "FAIL"
    result = evaluate_quality(payload, require_corrective_planner_quality_pass=True)
    assert result["quality_status"] == "FAIL"
    assert "source_quality_not_pass:corrective_retrieval_planner" in result["summary"]["quality_fail_reasons"]


def test_quality_checker_fails_when_answer_permission_leaks():
    payload = _passing_payload()
    payload["query_results"][0]["ranked_groups"][0]["can_answer_directly"] = True
    result = evaluate_quality(payload, require_no_answer_permission=True)
    assert result["quality_status"] == "FAIL"
    assert "hard_zero_safety_counter_nonzero" in result["summary"]["quality_fail_reasons"]
