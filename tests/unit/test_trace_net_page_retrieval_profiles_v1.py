from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_page_retrieval_profiles_v1 import (
    PAGE_PROFILE_AUTHORITY,
    PAGE_PROFILE_BUCKET,
    build_page_profile_bundle,
    build_page_profile_qdrant_point,
    build_page_profile_qdrant_points,
    check_page_profile_quality,
    deterministic_hash_embedding,
    parse_page_range,
    profile_embedding_text,
    unsafe_profile_reasons,
    write_page_profile_outputs,
)


def sample_pages(n=3):
    return [
        {
            "page_id": f"t_p_120_1176_p{i:06d}",
            "page_number": i,
            "document_id": "t_p_120_1176",
            "ata_code": "25-21-00" if i == 1 else "",
        }
        for i in range(1, n + 1)
    ]


def sample_embedding_records(n=3):
    rows = []
    for i in range(1, n + 1):
        rows.append(
            {
                "schema_version": "trace_net_embedding_candidates_v1",
                "embedding_candidate_id": f"emb_source_{i}",
                "source_candidate_id": f"source_trace_{i}",
                "page_id": f"t_p_120_1176_p{i:06d}",
                "document_id": "t_p_120_1176",
                "rag_bucket": "source_evidence",
                "authority": "source_exists_only",
                "source_url": f"https://example.invalid/page/{i}",
                "tiff_path": f"local/page_{i}.tiff",
                "ocr_path": f"local/page_{i}.txt",
                "citation_id": f"cit_{i}",
                "embedding_text": f"source trace for page {i}",
                "can_answer_directly": False,
                "can_prove_claims": False,
                "requires_source_resolution": True,
                "requires_citation": True,
            }
        )
        rows.append(
            {
                "embedding_candidate_id": f"emb_text_{i}",
                "source_candidate_id": f"text_{i}",
                "page_id": f"t_p_120_1176_p{i:06d}",
                "rag_bucket": "source_text_evidence",
                "embedding_text": f"placard warning panel part {i}",
                "can_answer_directly": False,
                "can_prove_claims": False,
                "requires_source_resolution": True,
                "requires_citation": True,
            }
        )
    return rows


def sample_context_records():
    return [
        {
            "helper_id": "ctx1",
            "page_id": "t_p_120_1176_p000001",
            "summary": "This page covers title block and revision information.",
            "retrieval_cues": ["title block", "manual revision"],
            "query_tunnel_terms": ["T.P. 120/1176", "Revision 4"],
        }
    ]


def test_parse_page_range_supports_ranges_and_commas():
    assert parse_page_range("1-3, 7, 9-10") == [1, 2, 3, 7, 9, 10]


def test_build_page_profile_bundle_creates_route_only_profiles():
    bundle = build_page_profile_bundle(
        sample_pages(3),
        embedding_records=sample_embedding_records(3),
        context_records=sample_context_records(),
        require_pages=[1, 2, 3],
    )
    assert bundle["record_count"] == 3
    assert bundle["unsafe_profile_count"] == 0
    first = bundle["records"][0]
    assert first["rag_bucket"] == PAGE_PROFILE_BUCKET
    assert first["authority"] == PAGE_PROFILE_AUTHORITY
    assert first["can_answer_directly"] is False
    assert first["can_prove_claims"] is False
    assert first["requires_source_resolution"] is True
    assert first["requires_citation"] is True
    assert first["embedding_answer_authority_allowed"] is False
    assert first["context_v2_present"] is True


def test_profile_embedding_text_includes_json_details():
    bundle = build_page_profile_bundle(sample_pages(1), embedding_records=sample_embedding_records(1), context_records=sample_context_records())
    text = profile_embedding_text(bundle["records"][0])
    assert "TRACE-Net page retrieval profile" in text
    assert "Authority: page_route_only" in text
    assert "ContextV2 retrieval summary" in text
    assert "Safe evidence buckets" in text


def test_unsafe_profile_reasons_detect_answer_authority_violation():
    bundle = build_page_profile_bundle(sample_pages(1), embedding_records=sample_embedding_records(1))
    profile = dict(bundle["records"][0])
    profile["can_answer_directly"] = True
    reasons = unsafe_profile_reasons(profile)
    assert "can_answer_directly" in reasons


def test_quality_passes_for_safe_profiles():
    bundle = build_page_profile_bundle(
        sample_pages(3),
        embedding_records=sample_embedding_records(3),
        context_records=sample_context_records(),
        require_pages=[1, 2, 3],
    )
    result = check_page_profile_quality(
        bundle,
        min_profile_records=3,
        min_pages_with_profiles=3,
        min_source_trace_pages=3,
        min_context_v2_pages=1,
        min_profiles_with_retrieval_cues=3,
        require_pages=[1, 2, 3],
    )
    assert result.status == "PASS"


def test_quality_fails_when_required_page_missing():
    bundle = build_page_profile_bundle(sample_pages(2), embedding_records=sample_embedding_records(2), require_pages=[1, 2, 3])
    result = check_page_profile_quality(bundle, min_profile_records=2, min_pages_with_profiles=2, require_pages=[1, 2, 3])
    assert result.status == "FAIL"
    assert result.summary["required_page_missing_count"] == 1


def test_writes_outputs_with_repo_style_paths(tmp_path: Path):
    bundle = build_page_profile_bundle(sample_pages(2), embedding_records=sample_embedding_records(2))
    paths = write_page_profile_outputs(bundle, tmp_path / "local_data" / "organization" / "trace_net" / "page_retrieval_profiles")
    assert paths["profiles_path"].exists()
    payload = json.loads(paths["profiles_path"].read_text(encoding="utf-8"))
    assert payload["record_count"] == 2


def test_hash_embedding_is_deterministic_and_normalized():
    left = deterministic_hash_embedding("page retrieval profile", dim=32)
    right = deterministic_hash_embedding("page retrieval profile", dim=32)
    assert left == right
    assert len(left) == 32
    assert 0.99 <= sum(value * value for value in left) ** 0.5 <= 1.01


def test_qdrant_point_payload_is_route_only():
    bundle = build_page_profile_bundle(sample_pages(1), embedding_records=sample_embedding_records(1), context_records=sample_context_records())
    point, reasons = build_page_profile_qdrant_point(bundle["records"][0], embedding_dim=24)
    assert reasons == []
    assert len(point["vector"]) == 24
    payload = point["payload"]
    assert payload["rag_bucket"] == PAGE_PROFILE_BUCKET
    assert payload["authority"] == PAGE_PROFILE_AUTHORITY
    assert payload["qdrant_is_source_truth"] is False
    assert payload["can_answer_directly"] is False
    assert payload["requires_source_resolution"] is True


def test_qdrant_points_reject_unsafe_profile():
    bundle = build_page_profile_bundle(sample_pages(1), embedding_records=sample_embedding_records(1))
    profile = dict(bundle["records"][0])
    profile["can_prove_claims"] = True
    points, rejected = build_page_profile_qdrant_points([profile], embedding_dim=24)
    assert points == []
    assert rejected[0]["safety_reasons"]


def test_qdrant_point_builder_progress_reports_vectorization():
    import io

    bundle = build_page_profile_bundle(sample_pages(3), embedding_records=sample_embedding_records(3))
    stream = io.StringIO()
    points, rejected = build_page_profile_qdrant_points(
        bundle["records"],
        embedding_dim=24,
        progress=True,
        progress_every=2,
        progress_stream=stream,
    )
    output = stream.getvalue()
    assert len(points) == 3
    assert rejected == []
    assert "0/3 profiles vectorized" in output
    assert "2/3 profiles vectorized" in output
    assert "3/3 profiles vectorized" in output


def test_page_profile_sentence_transformer_mode_can_be_monkeypatched(monkeypatch):
    import math
    import tiff.trace_net_page_retrieval_profiles_v1 as profiles

    class FakeModel:
        def encode(self, texts, **kwargs):
            assert texts
            return [[0.0, 5.0, 12.0] for _ in texts]

    monkeypatch.setattr(profiles, "load_sentence_transformer_model", lambda model_name, device=None: FakeModel())
    bundle = build_page_profile_bundle(sample_pages(1), embedding_records=sample_embedding_records(1))
    point, reasons = profiles.build_page_profile_qdrant_point(
        bundle["records"][0],
        embedding_mode="bge-m3",
        embedding_dim=3,
        embedding_model="BAAI/bge-m3",
    )
    assert reasons == []
    assert len(point["vector"]) == 3
    assert 0.99 <= math.sqrt(sum(value * value for value in point["vector"])) <= 1.01
    assert point["payload"]["embedding_mode"] == "bge-m3"
    assert point["payload"]["embedding_model_name"] == "BAAI/bge-m3"
    assert point["payload"]["embedding_dim"] == 3


def test_ollama_page_profile_vector_uses_local_api(monkeypatch):
    import tiff.trace_net_page_retrieval_profiles_v1 as profiles

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
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(profiles, "urlopen", fake_urlopen)
    bundle = build_page_profile_bundle(sample_pages(1), embedding_records=sample_embedding_records(1), context_records=sample_context_records())
    profile = bundle["records"][0]

    point, reasons = profiles.build_page_profile_qdrant_point(
        profile,
        embedding_mode="ollama",
        embedding_dim=3,
        embedding_model="bge-m3:latest",
        ollama_url="http://localhost:11434",
    )

    assert reasons == []
    assert point["vector"] == [1.0, 0.0, 0.0]
    assert captured["url"] == "http://localhost:11434/api/embed"
    assert captured["payload"]["model"] == "bge-m3:latest"
    assert captured["payload"]["input"] == [profile["embedding_text"]]
    payload = point["payload"]
    assert payload["record_type"] == PAGE_PROFILE_BUCKET
    assert payload["authority"] == PAGE_PROFILE_AUTHORITY
    assert payload["embedding_mode"] == "ollama"
    assert payload["embedding_model_name"] == "bge-m3:latest"
    assert payload["can_answer_directly"] is False
    assert payload["can_prove_claims"] is False
