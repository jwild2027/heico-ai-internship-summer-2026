from __future__ import annotations

from pathlib import Path

import pytest

from tiff import trace_net_vector_search_smoke_v1 as smoke


class FakeSearchClient:
    def __init__(self):
        self.search_calls = []

    def count_points(self, collection, *, exact=True):
        if collection == "trace_net_embedding_candidates_v1":
            return 1476
        if collection == "trace_net_page_retrieval_profiles_v1":
            return 509
        return 0

    def get_collection(self, collection):
        return {"result": {"config": {"params": {"vectors": {"size": 1024, "distance": "Cosine"}}}}}

    def search_points(self, collection, vector, *, limit=5, score_threshold=None, with_payload=True):
        self.search_calls.append((collection, list(vector), limit, score_threshold, with_payload))
        if collection == "trace_net_embedding_candidates_v1":
            return [
                {
                    "id": "point-candidate-1",
                    "score": 0.91,
                    "payload": safe_candidate_payload("source_text_evidence", "answer_support_with_gate"),
                },
                {
                    "id": "point-candidate-2",
                    "score": 0.82,
                    "payload": safe_candidate_payload("context_retrieval_helper", "retrieval_helper_only"),
                },
            ][:limit]
        return [
            {
                "id": "point-page-1",
                "score": 0.89,
                "payload": safe_page_profile_payload(),
            }
        ][:limit]


def safe_common_payload():
    return {
        "page_id": "t_p_120_1176_p000001",
        "page_number": 1,
        "document_id": "t_p_120_1176",
        "qdrant_is_source_truth": False,
        "qdrant_can_answer_directly": False,
        "qdrant_can_prove_claims": False,
        "must_resolve_through_postgres": True,
        "must_pass_authority_gate": True,
        "must_use_source_citation": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_prove_source_truth": False,
        "canonical_source_truth": False,
        "can_mutate_source_truth": False,
        "can_override_trust": False,
        "can_replace_citation": False,
        "requires_source_resolution": True,
        "requires_citation": True,
        "requires_authority_gate": True,
        "embedding_answer_authority_allowed": False,
        "embedding_mode": "ollama",
        "embedding_model_name": "bge-m3:latest",
        "embedding_dim": 1024,
        "embedding_text_preview": "safe preview",
    }


def safe_candidate_payload(bucket: str, authority: str):
    payload = safe_common_payload()
    payload.update(
        {
            "embedding_candidate_id": f"embcand-{bucket}",
            "source_candidate_id": f"source-{bucket}",
            "rag_bucket": bucket,
            "authority": authority,
            "citation_id": "citation-1",
            "source_url": "rescarta://page/1",
        }
    )
    if bucket == "context_retrieval_helper":
        payload["authority"] = "retrieval_helper_only"
    if bucket == "source_evidence":
        payload["authority"] = "source_exists_only"
    return payload


def safe_page_profile_payload():
    payload = safe_common_payload()
    payload.update(
        {
            "profile_id": "page_profile_1",
            "embedding_candidate_id": "page_profile_emb_1",
            "source_candidate_id": "page_profile_source_1",
            "record_type": "page_retrieval_profile",
            "rag_bucket": "page_retrieval_profile",
            "authority": "page_route_only",
            "page_route_only": True,
            "source_trace_present": True,
            "context_v2_present": True,
        }
    )
    return payload


def test_parse_query_items_defaults_when_empty():
    rows = smoke.parse_query_items([])
    assert len(rows) >= 3
    assert all(row["query_id"] for row in rows)
    assert all(row["query_text"] for row in rows)


def test_parse_query_items_supports_custom_ids():
    rows = smoke.parse_query_items(["custom::find part nomenclature", "plain query"])
    assert rows[0]["query_id"] == "custom"
    assert rows[0]["query_text"] == "find part nomenclature"
    assert rows[1]["query_id"] == "q_custom_002"


def test_query_vector_hash_is_dimensioned():
    vector, model = smoke.query_vector("manual revision history", embedding_mode="hash", embedding_dim=16)
    assert model == "trace_net_hash_embed_v1"
    assert len(vector) == 16
    assert sum(value * value for value in vector) > 0


def test_unsafe_payload_reasons_accepts_safe_candidate_payload():
    reasons = smoke.unsafe_payload_reasons(safe_candidate_payload("source_text_evidence", "answer_support_with_gate"), collection_role="candidate")
    assert reasons == []


def test_unsafe_payload_reasons_blocks_answer_capable_payload():
    payload = safe_candidate_payload("source_text_evidence", "answer_support_with_gate")
    payload["can_answer_directly"] = True
    payload["embedding_answer_authority_allowed"] = True
    reasons = smoke.unsafe_payload_reasons(payload, collection_role="candidate")
    assert "can_answer_directly_true" in reasons
    assert "embedding_answer_authority_allowed_true" in reasons


def test_unsafe_payload_reasons_blocks_bad_source_evidence_authority():
    payload = safe_candidate_payload("source_evidence", "source_exists_only")
    payload["authority"] = "wrong"
    reasons = smoke.unsafe_payload_reasons(payload, collection_role="candidate")
    assert "source_evidence_authority_not_source_exists_only" in reasons


def test_normalized_hit_marks_safe_hit():
    hit = smoke.normalized_hit(
        query={"query_id": "q1", "query_text": "query"},
        collection="trace_net_embedding_candidates_v1",
        collection_role="candidate",
        rank=1,
        hit={"id": "p1", "score": 0.9, "payload": safe_candidate_payload("context_retrieval_helper", "retrieval_helper_only")},
    )
    assert hit["safe_for_smoke_retrieval"] is True
    assert hit["answer_use_allowed_from_vector_hit"] is False
    assert hit["must_resolve_through_postgres_before_answer"] is True


def test_summarize_hits_counts_safety():
    query = {"query_id": "q1", "query_text": "query"}
    hits = [
        smoke.normalized_hit(
            query=query,
            collection="trace_net_embedding_candidates_v1",
            collection_role="candidate",
            rank=1,
            hit={"id": "p1", "score": 0.9, "payload": safe_candidate_payload("source_evidence", "source_exists_only")},
        ),
        smoke.normalized_hit(
            query=query,
            collection="trace_net_page_retrieval_profiles_v1",
            collection_role="page_profile",
            rank=1,
            hit={"id": "p2", "score": 0.8, "payload": safe_page_profile_payload()},
        ),
    ]
    summary = smoke.summarize_hits(
        queries=[query],
        hits=hits,
        candidate_collection="trace_net_embedding_candidates_v1",
        page_profile_collection="trace_net_page_retrieval_profiles_v1",
        candidate_collection_count=1476,
        page_profile_collection_count=509,
        candidate_collection_vector_size=1024,
        page_profile_collection_vector_size=1024,
        embedding_mode="ollama",
        embedding_model_name="bge-m3:latest",
        embedding_dim=1024,
    )
    assert summary["total_hit_count"] == 2
    assert summary["unsafe_hit_payload_count"] == 0
    assert summary["source_evidence_answer_allowed_count"] == 0
    assert summary["answer_capable_page_profile_count"] == 0


def test_quality_passes_for_safe_summary():
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
    quality = smoke.check_vector_search_smoke_quality(
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
    assert quality.status == "PASS"


def test_quality_fails_for_unsafe_summary():
    summary = {
        "smoke_query_count": 1,
        "total_hit_count": 1,
        "candidate_hit_count": 1,
        "page_profile_hit_count": 1,
        "queries_with_candidate_hits": 1,
        "queries_with_page_profile_hits": 1,
        "missing_page_id_count": 0,
        "missing_candidate_id_count": 0,
        "missing_profile_id_count": 0,
        "unsafe_hit_payload_count": 1,
        "direct_answer_allowed_hit_count": 1,
        "claim_proof_allowed_hit_count": 0,
        "qdrant_source_truth_hit_count": 0,
        "answer_authority_allowed_hit_count": 0,
        "answer_capable_page_profile_count": 0,
        "context_helper_answer_allowed_count": 0,
        "source_evidence_answer_allowed_count": 0,
        "source_evidence_claim_proof_allowed_count": 0,
        "candidate_collection_count": 1476,
        "page_profile_collection_count": 509,
    }
    quality = smoke.check_vector_search_smoke_quality(summary)
    assert quality.status == "FAIL"


def test_run_vector_search_smoke_writes_outputs_with_fake_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(smoke, "query_vector", lambda query_text, **kwargs: ([0.1] * kwargs.get("embedding_dim", 1024), "bge-m3:latest"))
    result = smoke.run_vector_search_smoke(
        output_dir=tmp_path,
        client=FakeSearchClient(),
        queries=[{"query_id": "q1", "query_text": "manual revision"}],
        limit=2,
        min_smoke_queries=1,
        min_total_hits=2,
        min_candidate_hits=1,
        min_page_profile_hits=1,
        min_queries_with_candidate_hits=1,
        min_queries_with_page_profile_hits=1,
        min_candidate_collection_count=1476,
        min_page_profile_collection_count=509,
        require_candidate_count=1476,
        require_page_profile_count=509,
        require_embedding_dim=1024,
        quality=True,
    )
    assert result["quality_status"] == "PASS"
    assert (tmp_path / smoke.DEFAULT_SMOKE_FILE).exists()
    assert (tmp_path / smoke.DEFAULT_HITS_JSONL_FILE).exists()
    assert (tmp_path / smoke.DEFAULT_QUALITY_FILE).exists()


def test_quality_from_file(tmp_path: Path):
    summary = {
        "smoke_query_count": 1,
        "total_hit_count": 2,
        "candidate_hit_count": 1,
        "page_profile_hit_count": 1,
        "queries_with_candidate_hits": 1,
        "queries_with_page_profile_hits": 1,
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
    path = tmp_path / smoke.DEFAULT_SUMMARY_FILE
    smoke.write_json(path, summary)
    quality, quality_path = smoke.check_vector_search_smoke_quality_from_file(
        summary_path=path,
        require_candidate_count=1476,
        require_page_profile_count=509,
        require_embedding_dim=1024,
        write_json_output=True,
    )
    assert quality.status == "PASS"
    assert quality_path.exists()
