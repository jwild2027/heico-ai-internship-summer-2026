from __future__ import annotations

from tiff.trace_net_hybrid_retrieval_sim_v1 import (
    build_quality_report,
    build_resolution_indexes,
    compact_hit,
    group_hits_for_query,
    load_queries,
    normalize_qdrant_hits,
    resolve_candidate_hit,
    resolve_page_profile_hit,
    summarize_hybrid_results,
    unsafe_payload_reasons,
)


def candidate_record(**updates):
    record = {
        "schema_version": "trace_net_embedding_candidates_v1",
        "embedding_candidate_id": "embcand__1",
        "source_candidate_id": "rag_candidate:source_text_evidence:test",
        "page_id": "t_p_120_1176_p000001",
        "document_id": "t_p_120_1176",
        "rag_bucket": "source_text_evidence",
        "authority": "source_text_support_only",
        "trust_tier": "B",
        "citation_id": "cite_1",
        "source_url": "https://example.test/source",
        "tiff_path": "page001.tif",
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_prove_source_truth": False,
        "canonical_source_truth": False,
        "can_mutate_source_truth": False,
        "embedding_answer_authority_allowed": False,
        "qdrant_is_source_truth": False,
        "qdrant_can_answer_directly": False,
        "qdrant_can_prove_claims": False,
        "must_resolve_through_postgres": True,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "embedding_text": "safe source-backed text",
    }
    record.update(updates)
    return record


def page_profile_record(**updates):
    record = {
        "schema_version": "trace_net_page_retrieval_profiles_v1",
        "profile_id": "page_profile__1",
        "page_id": "t_p_120_1176_p000001",
        "document_id": "t_p_120_1176",
        "rag_bucket": "page_retrieval_profile",
        "authority": "page_route_only",
        "context_v2_present": True,
        "source_trace_present": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_prove_source_truth": False,
        "canonical_source_truth": False,
        "can_mutate_source_truth": False,
        "embedding_answer_authority_allowed": False,
        "qdrant_is_source_truth": False,
        "qdrant_can_answer_directly": False,
        "qdrant_can_prove_claims": False,
        "must_resolve_through_postgres": True,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "embedding_text": "safe page route profile",
    }
    record.update(updates)
    return record


def build_indexes():
    return build_resolution_indexes([candidate_record()], [page_profile_record()])


def test_unsafe_payload_reasons_accepts_safe_candidate_and_page_profile():
    assert unsafe_payload_reasons(candidate_record(), collection_role="candidate") == []
    assert unsafe_payload_reasons(page_profile_record(), collection_role="page_profile") == []


def test_unsafe_payload_reasons_rejects_answer_capable_context_helper():
    payload = candidate_record(
        rag_bucket="context_retrieval_helper",
        authority="retrieval_helper_only",
        can_answer_directly=True,
    )
    reasons = unsafe_payload_reasons(payload, collection_role="candidate")
    assert "payload_can_answer_directly" in reasons


def test_resolution_indexes_resolve_candidate_and_page_profile():
    indexes = build_indexes()
    resolved_candidate, reasons = resolve_candidate_hit(candidate_record(), indexes)
    assert resolved_candidate is not None
    assert resolved_candidate["embedding_candidate_id"] == "embcand__1"
    assert reasons == []
    resolved_profile, profile_reasons = resolve_page_profile_hit(page_profile_record(), indexes)
    assert resolved_profile is not None
    assert resolved_profile["profile_id"] == "page_profile__1"
    assert profile_reasons == []


def test_compact_hit_preserves_resolution_and_safety():
    hit = compact_hit(
        {"rank": 1, "id": "point1", "score": 0.81, "payload": candidate_record()},
        collection_role="candidate",
        collection="trace_net_embedding_candidates_v1",
        indexes=build_indexes(),
    )
    assert hit["is_safe_hit"] is True
    assert hit["resolved_to_artifact"] is True
    assert hit["embedding_candidate_id"] == "embcand__1"
    assert hit["requires_citation"] is True


def test_group_hits_for_query_groups_by_page_and_never_allows_answer():
    indexes = build_indexes()
    page_hit = compact_hit(
        {"rank": 1, "id": "page1", "score": 0.9, "payload": page_profile_record()},
        collection_role="page_profile",
        collection="pages",
        indexes=indexes,
    )
    candidate_hit = compact_hit(
        {"rank": 1, "id": "cand1", "score": 0.85, "payload": candidate_record()},
        collection_role="candidate",
        collection="candidates",
        indexes=indexes,
    )
    groups = group_hits_for_query(
        {
            "query_id": "q1",
            "query": "revision history",
            "page_profile_hits": [page_hit],
            "candidate_hits": [candidate_hit],
        }
    )
    assert len(groups) == 1
    group = groups[0]
    assert group["page_id"] == "t_p_120_1176_p000001"
    assert group["page_profile_hit_count"] == 1
    assert group["candidate_hit_count"] == 1
    assert group["answer_allowed"] is False
    assert group["can_prove_claims"] is False
    assert group["safety_status"] == "retrieval_safe"


def test_summarize_and_quality_report_pass_for_safe_groups():
    indexes = build_indexes()
    page_hit = compact_hit({"rank": 1, "id": "page1", "score": 0.9, "payload": page_profile_record()}, collection_role="page_profile", collection="pages", indexes=indexes)
    candidate_hit = compact_hit({"rank": 1, "id": "cand1", "score": 0.85, "payload": candidate_record()}, collection_role="candidate", collection="candidates", indexes=indexes)
    groups = group_hits_for_query({"query_id": "q1", "query": "revision history", "page_profile_hits": [page_hit], "candidate_hits": [candidate_hit]})
    query_results = [
        {
            "query_id": "q1",
            "query": "revision history",
            "page_profile_hits": [page_hit],
            "candidate_hits": [candidate_hit],
            "ranked_groups": groups,
            "ranked_group_count": len(groups),
        }
    ]
    summary = summarize_hybrid_results(
        query_results,
        candidate_collection="candidates",
        page_profile_collection="pages",
        candidate_collection_count=1476,
        page_profile_collection_count=509,
        candidate_artifact_count=1476,
        page_profile_artifact_count=509,
        embedding_mode="ollama",
        embedding_model_name="bge-m3:latest",
        embedding_dim=1024,
        vector_smoke_status="PASS",
    )
    quality = build_quality_report(
        summary,
        min_hybrid_queries=1,
        min_queries_with_results=1,
        min_grouped_results=1,
        min_candidate_hits=1,
        min_page_profile_hits=1,
        min_resolved_candidate_hits=1,
        min_resolved_page_profile_hits=1,
        min_candidate_collection_count=1476,
        min_page_profile_collection_count=509,
        require_candidate_count=1476,
        require_page_profile_count=509,
        require_embedding_dim=1024,
        require_vector_smoke_quality_pass=True,
    )
    assert summary["unsafe_result_count"] == 0
    assert summary["direct_answer_allowed_result_count"] == 0
    assert quality.status == "PASS"


def test_quality_report_fails_when_group_allows_answer():
    summary = {
        "hybrid_query_count": 1,
        "queries_with_results_count": 1,
        "grouped_result_count": 1,
        "candidate_hit_count": 1,
        "page_profile_hit_count": 1,
        "resolved_candidate_hit_count": 1,
        "resolved_page_profile_hit_count": 1,
        "missing_page_id_count": 0,
        "unsafe_result_count": 0,
        "unsafe_hit_payload_count": 0,
        "direct_answer_allowed_result_count": 1,
        "claim_proof_allowed_without_authority_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "answer_capable_page_profile_hit_count": 0,
        "context_helper_answer_allowed_hit_count": 0,
        "source_evidence_answer_allowed_hit_count": 0,
        "requires_source_resolution_false_count": 0,
        "requires_citation_false_count": 0,
        "requires_authority_gate_false_count": 0,
        "candidate_collection_count": 1,
        "page_profile_collection_count": 1,
    }
    assert build_quality_report(summary).status == "FAIL"


def test_normalize_qdrant_hits_accepts_search_and_query_shapes():
    search_shape = {"result": [{"id": "1", "score": 0.5, "payload": {"page_id": "p"}}]}
    query_shape = {"result": {"points": [{"id": "2", "score": 0.6, "payload": {"page_id": "p"}}]}}
    assert normalize_qdrant_hits(search_shape)[0]["id"] == "1"
    assert normalize_qdrant_hits(query_shape)[0]["id"] == "2"


def test_load_queries_defaults_and_inline():
    assert len(load_queries()) >= 5
    queries = load_queries(inline_queries=["find revision history"])
    assert queries[0]["query"] == "find revision history"
