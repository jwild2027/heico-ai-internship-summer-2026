import json

from tiff.trace_net_hybrid_retrieval_v3 import build_hybrid_retrieval_v3, build_live_hits_by_query_id
from tiff.trace_net_hybrid_retrieval_v3_quality import evaluate_quality


def _hybrid_v2_payload():
    return {
        "schema_version": "trace_net_hybrid_retrieval_v2",
        "quality_status": "PASS",
        "summary": {"quality_status": "PASS"},
        "query_results": [
            {
                "query_id": "part_120_50648_001",
                "query": "120-50648-001",
                "ranked_groups": [
                    {
                        "page_id": "t_p_120_1176_p000003",
                        "source_page_ids": ["t_p_120_1176_p000003"],
                        "part_numbers": ["120-50648-001"],
                        "hybrid_v2_score": 0.72,
                        "semantic_groups": [{"page_id": "t_p_120_1176_p000003", "score": 0.61}],
                    }
                ],
            }
        ],
    }


def _planner_payload():
    return {
        "schema_version": "trace_net_corrective_retrieval_planner_v1",
        "quality_status": "PASS",
        "summary": {"quality_status": "PASS", "source_quality_statuses": {"qdrant_page_profile_quality": "PASS"}},
        "corrective_retrieval_records": [
            {
                "record_id": "corrective_retrieval::opensearch_loader_smoke::exact_search_channel_available",
                "issue_type": "exact_search_channel_available",
                "severity": "INFO",
                "recommended_actions": ["use_opensearch_exact_for_identifiers"],
            }
        ],
    }


def _live_hit():
    return {
        "_id": "normcell__01ac63e4943341",
        "_score": 5.9,
        "_source": {
            "opensearch_document_id": "normcell__01ac63e4943341",
            "document_type": "table_cell_normalized",
            "page_id": "t_p_120_1176_p000003",
            "source_page_ids": ["t_p_120_1176_p000003"],
            "part_numbers": [],
            "text": "120-50648-001",
            "title": "Table cell | t_p_120_1176_p000003 | 120-50648-001",
            "retrieval_only": True,
            "safe_for_opensearch": True,
            "source_trace_present": True,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
        },
    }


def test_hybrid_v3_attaches_live_opensearch_hits_without_answer_authority():
    payload = build_hybrid_retrieval_v3(
        hybrid_v2=_hybrid_v2_payload(),
        corrective_planner=_planner_payload(),
        graph_enrichment={"quality_status": "PASS", "enriched_page_records": [{"page_id": "t_p_120_1176_p000003"}]},
        opensearch_loader_smoke={"quality_status": "PASS"},
        opensearch_live_loader={"quality_status": "PASS"},
        qdrant_page_profile_quality={"quality_status": "PASS"},
        live_opensearch_hits_by_query_id={"part_120_50648_001": [_live_hit()]},
        min_queries=1,
        min_queries_with_results=1,
        min_groups=1,
        min_corrective_groups=0,
        min_live_exact_hit_groups=1,
        require_hybrid_v2_quality_pass=True,
        require_corrective_planner_quality_pass=True,
        require_graph_enrichment_quality_pass=True,
        require_opensearch_loader_quality_pass=True,
        require_opensearch_live_loader_quality_pass=True,
        require_qdrant_quality_pass=True,
        require_no_answer_permission=True,
    )

    assert payload["quality_status"] == "PASS"
    assert payload["source_quality_statuses"]["opensearch_live_loader"] == "PASS"
    assert payload["summary"]["live_opensearch_exact_hit_group_count"] == 1
    assert payload["summary"]["live_opensearch_exact_hit_count"] == 1
    assert payload["summary"]["opensearch_write_attempt_count"] == 0

    group = payload["query_results"][0]["ranked_groups"][0]
    assert group["has_live_opensearch_exact_signal"] is True
    assert group["live_opensearch_exact_hit_count"] == 1
    assert group["live_opensearch_exact_hits"][0]["document_type"] == "table_cell_normalized"
    assert group["can_answer_directly"] is False
    assert group["can_prove_claims"] is False
    assert group["source_truth_mutation_allowed"] is False
    assert group["opensearch_write_attempted"] is False


def test_quality_can_require_live_opensearch_source_and_hits():
    payload = build_hybrid_retrieval_v3(
        hybrid_v2=_hybrid_v2_payload(),
        corrective_planner=_planner_payload(),
        graph_enrichment={"quality_status": "PASS"},
        opensearch_loader_smoke={"quality_status": "PASS"},
        opensearch_live_loader={"quality_status": "PASS"},
        qdrant_page_profile_quality={"quality_status": "PASS"},
        live_opensearch_hits_by_query_id={"part_120_50648_001": [_live_hit()]},
        min_live_exact_hit_groups=1,
        require_opensearch_live_loader_quality_pass=True,
    )
    quality = evaluate_quality(
        payload,
        min_queries=1,
        min_queries_with_results=1,
        min_groups=1,
        min_corrective_groups=0,
        min_live_exact_hit_groups=1,
        require_opensearch_live_loader_quality_pass=True,
        require_no_answer_permission=True,
    )
    assert quality["quality_status"] == "PASS"
    assert quality["summary"]["live_opensearch_exact_hit_group_count"] == 1


def test_live_opensearch_query_uses_real_index_fields(monkeypatch):
    seen = {}

    def fake_query(*, opensearch_url, index_name, query_text, max_hits):
        seen["args"] = (opensearch_url, index_name, query_text, max_hits)
        return [{"opensearch_document_id": "hit-1", "page_id": "t_p_120_1176_p000003", "text": "120-50648-001"}]

    monkeypatch.setattr("tiff.trace_net_hybrid_retrieval_v3.run_live_opensearch_query", fake_query)
    hits = build_live_hits_by_query_id(
        hybrid_v2=_hybrid_v2_payload(),
        opensearch_url="http://localhost:9200",
        index_name="trace_net_safe_search_v1",
        max_hits_per_query=3,
    )
    assert seen["args"] == ("http://localhost:9200", "trace_net_safe_search_v1", "120-50648-001", 3)
    assert hits["part_120_50648_001"][0]["opensearch_document_id"] == "hit-1"
