from __future__ import annotations

from tiff import trace_net_vector_search_smoke_v1 as smoke


def baseline_summary(**overrides):
    summary = {
        "smoke_query_count": 5,
        "total_hit_count": 50,
        "candidate_hit_count": 25,
        "page_profile_hit_count": 25,
        "queries_with_candidate_hits": 5,
        "queries_with_page_profile_hits": 5,
        "missing_page_id_count": 0,
        "missing_candidate_id_count": 0,
        "missing_profile_id_count": 0,
        "unsafe_hit_payload_count": 0,
        "direct_answer_allowed_hit_count": 0,
        "claim_proof_allowed_hit_count": 0,
        "qdrant_source_truth_hit_count": 0,
        "answer_authority_allowed_hit_count": 0,
        "answer_capable_page_profile_count": 0,
        "context_helper_answer_allowed_count": 0,
        "source_evidence_answer_allowed_count": 0,
        "source_evidence_claim_proof_allowed_count": 0,
        "candidate_collection_count": 1476,
        "page_profile_collection_count": 509,
        "candidate_collection_vector_size": 1024,
        "page_profile_collection_vector_size": 1024,
        "embedding_dim": 1024,
    }
    summary.update(overrides)
    return summary


def check(summary):
    return smoke.check_vector_search_smoke_quality(
        summary,
        min_smoke_queries=5,
        min_total_hits=10,
        min_candidate_hits=5,
        min_page_profile_hits=5,
        min_queries_with_candidate_hits=5,
        min_queries_with_page_profile_hits=5,
        min_candidate_collection_count=1476,
        min_page_profile_collection_count=509,
        require_candidate_count=1476,
        require_page_profile_count=509,
        require_embedding_dim=1024,
    )


def test_quality_requires_exact_collection_counts():
    assert check(baseline_summary()).status == "PASS"
    assert check(baseline_summary(candidate_collection_count=1475)).status == "FAIL"
    assert check(baseline_summary(page_profile_collection_count=508)).status == "FAIL"


def test_quality_requires_vector_dimensions():
    assert check(baseline_summary(candidate_collection_vector_size=384)).status == "FAIL"
    assert check(baseline_summary(page_profile_collection_vector_size=384)).status == "FAIL"
    assert check(baseline_summary(embedding_dim=384)).status == "FAIL"


def test_quality_blocks_missing_trace_fields():
    assert check(baseline_summary(missing_page_id_count=1)).status == "FAIL"
    assert check(baseline_summary(missing_candidate_id_count=1)).status == "FAIL"
    assert check(baseline_summary(missing_profile_id_count=1)).status == "FAIL"


def test_quality_blocks_answer_or_claim_authority():
    assert check(baseline_summary(direct_answer_allowed_hit_count=1)).status == "FAIL"
    assert check(baseline_summary(claim_proof_allowed_hit_count=1)).status == "FAIL"
    assert check(baseline_summary(answer_authority_allowed_hit_count=1)).status == "FAIL"
    assert check(baseline_summary(qdrant_source_truth_hit_count=1)).status == "FAIL"


def test_quality_blocks_retrieval_only_answer_misuse():
    assert check(baseline_summary(answer_capable_page_profile_count=1)).status == "FAIL"
    assert check(baseline_summary(context_helper_answer_allowed_count=1)).status == "FAIL"
    assert check(baseline_summary(source_evidence_answer_allowed_count=1)).status == "FAIL"
    assert check(baseline_summary(source_evidence_claim_proof_allowed_count=1)).status == "FAIL"


def test_quality_requires_hits_from_both_collections():
    assert check(baseline_summary(candidate_hit_count=0)).status == "FAIL"
    assert check(baseline_summary(page_profile_hit_count=0)).status == "FAIL"
    assert check(baseline_summary(queries_with_candidate_hits=0)).status == "FAIL"
    assert check(baseline_summary(queries_with_page_profile_hits=0)).status == "FAIL"
