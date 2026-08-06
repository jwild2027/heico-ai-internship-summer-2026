from __future__ import annotations

from tiff.trace_net_hybrid_retrieval_v2 import (
    build_query_result,
    exact_search,
    is_safe_opensearch_doc,
    quality_report,
    score_exact_doc,
    summarize,
)


def os_doc(**updates):
    doc = {
        "opensearch_document_id": "doc1",
        "document_type": "table_cell_normalized",
        "title": "Part table page 3",
        "text": "Part number 120-46137-001 is in this normalized table cell.",
        "page_id": "t_p_120_1176_p000003",
        "source_page_ids": ["t_p_120_1176_p000003"],
        "citation_ids": ["cite:table_structured:t_p_120_1176_p000003:test"],
        "community_ids": ["tracenet_community_00001"],
        "part_numbers": ["120-46137-001"],
        "rag_bucket": "table_cell_normalized",
        "authority": "table_cell_retrieval_helper_only",
        "retrieval_only": True,
        "answer_support_candidate": False,
        "safe_for_opensearch": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
        "raw_feedback_indexed": False,
        "raw_visual_output": False,
        "raw_ocr_unfiltered": False,
    }
    doc.update(updates)
    return doc


def semantic_report():
    return {
        "quality_status": "PASS",
        "query_results": [
            {
                "query_id": "part_120_46137_001",
                "query": "120-46137-001",
                "ranked_groups": [
                    {
                        "page_id": "t_p_120_1176_p000003",
                        "hybrid_score": 0.82,
                        "citation_ids": ["cite:table_structured:t_p_120_1176_p000003:test"],
                        "part_numbers": ["120-46137-001"],
                        "bucket_counts": {"table_cell_normalized": 1},
                        "can_answer_directly": False,
                        "can_prove_claims": False,
                    }
                ],
            }
        ],
    }


def category_overlay():
    return {
        "quality_status": "PASS",
        "page_category_membership": [
            {
                "page_id": "t_p_120_1176_p000003",
                "page_category_label": "table_parts_diagram_page_review",
                "leiden_hint_element_families": ["table", "part", "diagram", "source"],
            }
        ],
        "community_category_profiles": [
            {
                "community_id": "tracenet_community_00001",
                "category_aware_label": "Table + parts + diagram review community",
                "dominant_leiden_hint_families": ["table", "part", "diagram"],
            }
        ],
    }


def feedback_memory():
    return {
        "quality_status": "PASS",
        "memory_records": [
            {
                "memory_id": "mem1",
                "target_type": "page",
                "target_id": "t_p_120_1176_p000003",
                "rating_score": 1,
                "raw_feedback_direct_to_llm": False,
            }
        ],
    }


def test_score_exact_doc_matches_exact_part_number():
    score = score_exact_doc("120-46137-001", os_doc())
    assert score["score"] > 4
    assert "120-46137-001" in score["matched_part_numbers"]


def test_exact_search_filters_unsafe_docs():
    docs = [os_doc(), os_doc(opensearch_document_id="bad", can_answer_directly=True)]
    hits = exact_search("120-46137-001", docs, top_k=5)
    assert len(hits) == 1
    assert hits[0]["opensearch_document_id"] == "doc1"
    assert hits[0]["can_answer_directly"] is False


def test_unsafe_doc_rejected_when_missing_lineage():
    assert is_safe_opensearch_doc(os_doc()) is True
    assert is_safe_opensearch_doc(os_doc(page_id=None, source_page_ids=[])) is False


def test_build_query_result_combines_exact_semantic_category_feedback():
    result = build_query_result(
        {"query_id": "part_120_46137_001", "query": "120-46137-001"},
        docs=[os_doc()],
        hybrid_report=semantic_report(),
        community_report={},
        category_overlay=category_overlay(),
        feedback_memory=feedback_memory(),
        top_k_exact=5,
        max_groups=5,
    )
    assert result["ranked_group_count"] == 1
    group = result["ranked_groups"][0]
    assert group["page_id"] == "t_p_120_1176_p000003"
    assert group["exact_hit_count"] == 1
    assert group["semantic_group_count"] == 1
    assert group["category_boost"] > 0
    assert group["feedback_advisory_delta"] > 0
    assert group["answer_allowed"] is False
    assert group["can_prove_claims"] is False


def test_quality_report_passes_for_safe_result():
    result = build_query_result(
        {"query_id": "part_120_46137_001", "query": "120-46137-001"},
        docs=[os_doc()],
        hybrid_report=semantic_report(),
        community_report={},
        category_overlay=category_overlay(),
        feedback_memory=feedback_memory(),
        top_k_exact=5,
        max_groups=5,
    )
    report = {
        "query_results": [result],
        "source_quality_statuses": {"hybrid_report": "PASS", "opensearch_adapter": "PASS"},
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }
    report["summary"] = summarize(report)
    q = quality_report(
        report,
        min_queries=1,
        min_queries_with_results=1,
        min_groups=1,
        min_exact_hit_groups=1,
        min_semantic_groups=1,
        require_opensearch_quality_pass=True,
        require_hybrid_quality_pass=True,
    )
    assert q["status"] == "PASS"
    assert q["summary"]["combined_exact_semantic_group_count"] == 1
    assert q["summary"]["feedback_as_proof_count"] == 0
