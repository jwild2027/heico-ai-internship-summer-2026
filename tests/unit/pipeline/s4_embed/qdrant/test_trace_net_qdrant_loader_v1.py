import json
import math
from pathlib import Path

import pytest

from tiff.trace_net_qdrant_loader_v1 import (
    DEFAULT_EMBEDDING_DIM,
    QdrantLoaderError,
    build_embedding_vector,
    build_qdrant_point,
    build_qdrant_points,
    candidate_is_safe_for_qdrant,
    deterministic_hash_embedding,
    ensure_collection,
    extract_collection_vector_size,
    point_uuid,
    summarize_points,
    unsafe_payload_reasons,
)


def safe_candidate(**overrides):
    row = {
        "schema_version": "trace_net_embedding_candidates_v1",
        "embedding_candidate_id": "embcand__abc123",
        "qdrant_point_id": "",
        "source_candidate_id": "rag_candidate:source_text:1",
        "source_kind": "rag_candidate_chunk",
        "source_table": "rag_candidate_chunks",
        "page_id": "t_p_120_1176_p000001",
        "page_number": 1,
        "document_id": "t_p_120_1176",
        "ata_code": "25-21-00",
        "rag_bucket": "source_text_evidence",
        "embedding_bucket": "source_text_evidence",
        "candidate_type": "source_text_evidence",
        "evidence_layer": "source_text_evidence",
        "embedding_text": "Placard installation instructions and source-backed OCR text.",
        "content_sha256": "abc",
        "trust_tier": "B",
        "final_trust_tier": "B",
        "authority": "answer_support_after_postgres_resolution",
        "answer_use_policy": "answer_support_after_postgres_resolution",
        "allowed_use": ["retrieve", "rank", "route", "candidate_discovery", "answer_support_after_postgres_resolution"],
        "forbidden_use": ["direct_answer_from_vector_hit"],
        "can_embed": True,
        "can_retrieve": True,
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
        "citation_id": "cit-1",
        "source_url": "https://example.test/source",
        "tiff_path": "page1.tif",
        "ocr_path": "page1.txt",
        "traceability": {"must_resolve_through_postgres": True, "page_id": "t_p_120_1176_p000001"},
        "safety_status": "safe",
    }
    row.update(overrides)
    return row


def context_helper_candidate(**overrides):
    row = safe_candidate(
        embedding_candidate_id="embcand__ctx001",
        source_candidate_id="ctx_helper__p000001",
        source_kind="context_retrieval_helper",
        source_table="trace_net_context_retrieval_helpers_v1",
        rag_bucket="context_retrieval_helper",
        embedding_bucket="context_retrieval_helper",
        candidate_type="context_retrieval_helper",
        evidence_layer="context_retrieval_helper",
        embedding_text="query tunnel terms for manual revision title block",
        trust_tier="RETRIEVAL_ONLY",
        authority="retrieval_helper_only",
        answer_use_policy="retrieval_only",
        retrieval_only=True,
        citation_id="",
        source_url="",
        query_tunnel_terms=["revision", "title block"],
        retrieval_cues=["manual revision"],
    )
    row.update(overrides)
    return row


def source_evidence_candidate(**overrides):
    row = safe_candidate(
        embedding_candidate_id="embcand__src001",
        source_candidate_id="rag_candidate:source_evidence:source_trace_t_p_120_1176_p000001",
        rag_bucket="source_evidence",
        embedding_bucket="source_evidence",
        candidate_type="source_evidence",
        evidence_layer="source_evidence",
        embedding_text="source locator for page 1 TIFF OCR source path",
        trust_tier="SOURCE_TRACE",
        authority="source_exists_only",
        answer_use_policy="not_answer_capable",
        retrieval_only=True,
    )
    row.update(overrides)
    return row


def test_hash_embedding_is_deterministic_and_normalized():
    first = deterministic_hash_embedding("alpha beta beta", dim=32)
    second = deterministic_hash_embedding("alpha beta beta", dim=32)
    assert first == second
    assert len(first) == 32
    norm = math.sqrt(sum(value * value for value in first))
    assert norm == pytest.approx(1.0, abs=1e-5)


def test_point_uuid_is_stable():
    assert point_uuid("embcand__abc123") == point_uuid("embcand__abc123")
    assert point_uuid("embcand__abc123") != point_uuid("embcand__different")


def test_candidate_safety_accepts_safe_source_text_candidate():
    is_safe, reasons = candidate_is_safe_for_qdrant(safe_candidate())
    assert is_safe is True
    assert reasons == []


def test_candidate_safety_rejects_direct_answer_candidate():
    is_safe, reasons = candidate_is_safe_for_qdrant(safe_candidate(can_answer_directly=True))
    assert is_safe is False
    assert "candidate_can_answer_directly" in reasons


def test_candidate_safety_rejects_context_helper_claim_proof():
    is_safe, reasons = candidate_is_safe_for_qdrant(context_helper_candidate(can_prove_claims=True))
    assert is_safe is False
    assert "candidate_can_prove_claims" in reasons


def test_source_evidence_locator_is_safe_but_not_answer_capable():
    point, reasons = build_qdrant_point(source_evidence_candidate(), embedding_dim=32)
    assert reasons == []
    payload = point["payload"]
    assert payload["authority"] == "source_exists_only"
    assert payload["can_answer_directly"] is False
    assert payload["can_prove_claims"] is False
    assert payload["must_resolve_through_postgres"] is True
    assert unsafe_payload_reasons(payload) == []


def test_build_qdrant_point_excludes_full_text_by_default():
    point, reasons = build_qdrant_point(safe_candidate(), embedding_dim=32)
    assert reasons == []
    payload = point["payload"]
    assert "embedding_text_preview" in payload
    assert "embedding_text" not in payload
    assert payload["qdrant_is_source_truth"] is False
    assert payload["qdrant_can_answer_directly"] is False


def test_build_qdrant_point_can_include_full_text_only_when_flagged():
    point, reasons = build_qdrant_point(safe_candidate(), embedding_dim=32, include_full_text_payload=True)
    assert reasons == []
    assert point["payload"]["embedding_text"] == safe_candidate()["embedding_text"]


def test_build_qdrant_points_rejects_unsafe_candidate():
    points, rejected = build_qdrant_points([safe_candidate(), safe_candidate(embedding_candidate_id="bad", can_mutate_source_truth=True)], embedding_dim=32)
    assert len(points) == 1
    assert len(rejected) == 1
    assert "candidate_can_mutate_source_truth" in rejected[0]["safety_reasons"]


def test_summarize_points_counts_buckets_and_pages():
    points, rejected = build_qdrant_points([safe_candidate(), context_helper_candidate(), source_evidence_candidate()], embedding_dim=32)
    summary = summarize_points(points, rejected)
    assert summary["point_count"] == 3
    assert summary["rejected_count"] == 0
    assert summary["page_count"] == 1
    assert summary["bucket_counts"]["context_retrieval_helper"] == 1
    assert summary["bucket_counts"]["source_evidence"] == 1
    assert summary["context_helper_point_count"] == 1
    assert summary["rag_candidate_point_count"] == 2


def test_precomputed_embedding_mode_validates_dimension():
    vector = [0.1] * 16
    built, mode = build_embedding_vector(safe_candidate(embedding=vector), mode="precomputed", dim=16)
    assert built == vector
    assert mode == "precomputed"
    with pytest.raises(QdrantLoaderError):
        build_embedding_vector(safe_candidate(embedding=[0.1] * 8), mode="precomputed", dim=16)


def test_extract_collection_vector_size_supports_named_and_unnamed_configs():
    unnamed = {"result": {"config": {"params": {"vectors": {"size": 384}}}}}
    named = {"result": {"config": {"params": {"vectors": {"default": {"size": 256}}}}}}
    assert extract_collection_vector_size(unnamed) == 384
    assert extract_collection_vector_size(named) == 256


def test_ensure_collection_raises_on_dimension_mismatch():
    class Client:
        def get_collection(self, collection):
            return {"result": {"config": {"params": {"vectors": {"size": 12}}}}}

        def delete_collection(self, collection):
            return {}

        def create_collection(self, collection, *, vector_size, distance="Cosine"):
            return {}

    with pytest.raises(QdrantLoaderError):
        ensure_collection(Client(), collection="c", vector_size=32, recreate=False)


def test_sentence_transformer_embedding_mode_can_be_monkeypatched(monkeypatch):
    import tiff.trace_net_qdrant_loader_v1 as qloader

    class FakeModel:
        def encode(self, texts, **kwargs):
            assert texts
            return [[3.0, 4.0, 0.0] for _ in texts]

    monkeypatch.setattr(qloader, "load_sentence_transformer_model", lambda model_name, device=None: FakeModel())
    vector, model_name = qloader.build_embedding_vector(
        safe_candidate(),
        mode="bge-m3",
        dim=3,
        embedding_model="BAAI/bge-m3",
    )
    assert model_name == "BAAI/bge-m3"
    assert len(vector) == 3
    assert 0.99 <= math.sqrt(sum(value * value for value in vector)) <= 1.01

    point, reasons = qloader.build_qdrant_point(
        safe_candidate(embedding_candidate_id="embcand__real001"),
        embedding_mode="sentence-transformers",
        embedding_dim=3,
        embedding_model="BAAI/bge-m3",
    )
    assert reasons == []
    assert point["payload"]["embedding_mode"] == "sentence-transformers"
    assert point["payload"]["embedding_model_name"] == "BAAI/bge-m3"
    assert point["payload"]["embedding_dim"] == 3


def test_ollama_embedding_mode_uses_local_api(monkeypatch):
    import tiff.trace_net_qdrant_loader_v1 as qloader

    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"embeddings": [[1.0, 0.0, 0.0]]}).encode("utf-8")

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(qloader, "urlopen", fake_urlopen)

    vector, model_name = qloader.build_embedding_vector(
        safe_candidate(),
        mode="ollama",
        dim=3,
        embedding_model="bge-m3:latest",
        ollama_url="http://localhost:11434",
    )

    assert model_name == "bge-m3:latest"
    assert vector == [1.0, 0.0, 0.0]
    assert captured["url"] == "http://localhost:11434/api/embed"
    assert captured["payload"]["model"] == "bge-m3:latest"
    assert captured["payload"]["input"] == [safe_candidate()["embedding_text"]]


def test_ollama_qdrant_point_keeps_trace_net_safety_payload(monkeypatch):
    import tiff.trace_net_qdrant_loader_v1 as qloader

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"embeddings": [[0.0, 1.0, 0.0]]}).encode("utf-8")

    monkeypatch.setattr(qloader, "urlopen", lambda request, timeout=0: FakeResponse())

    point, reasons = qloader.build_qdrant_point(
        context_helper_candidate(),
        embedding_mode="ollama",
        embedding_dim=3,
        embedding_model="bge-m3:latest",
        ollama_url="http://localhost:11434",
    )

    assert reasons == []
    payload = point["payload"]
    assert payload["embedding_mode"] == "ollama"
    assert payload["embedding_model_name"] == "bge-m3:latest"
    assert payload["can_answer_directly"] is False
    assert payload["can_prove_claims"] is False
    assert payload["requires_source_resolution"] is True
    assert payload["requires_citation"] is True
