import json
from pathlib import Path

from tiff.trace_net_qdrant_loader_v1 import (
    QdrantHTTPClient,
    QdrantLoaderError,
    build_and_load_qdrant_index,
    build_qdrant_points,
    check_qdrant_loader_quality,
    iter_batches,
    main_load,
    main_quality,
    read_json,
    summarize_points,
)


def candidate(**overrides):
    record = {
        "embedding_candidate_id": "embcand__001",
        "qdrant_point_id": "11111111-1111-4111-8111-111111111111",
        "source_candidate_id": "rag_candidate:source_text:t_p_120_1176_p000001",
        "source_kind": "rag_candidate_chunk",
        "source_table": "rag_candidate_chunks",
        "page_id": "t_p_120_1176_p000001",
        "page_number": 1,
        "rag_bucket": "source_text_evidence",
        "embedding_bucket": "source_text_evidence",
        "candidate_type": "source_text_evidence",
        "evidence_layer": "source_text_evidence",
        "embedding_text": "Install decal placard on page 1 using source backed text.",
        "authority": "answer_support_after_postgres_resolution",
        "answer_use_policy": "answer_support_after_postgres_resolution",
        "trust_tier": "B",
        "final_trust_tier": "B",
        "final_rag_action": "allow_with_citation",
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
        "citation_id": "cite-1",
        "source_url": "https://example.invalid/source",
        "traceability": {"page_id": "t_p_120_1176_p000001", "must_resolve_through_postgres": True},
        "safety_status": "safe",
    }
    record.update(overrides)
    return record


def context_helper(**overrides):
    row = candidate(
        embedding_candidate_id="embcand__ctx001",
        qdrant_point_id="22222222-2222-4222-8222-222222222222",
        source_candidate_id="ctx_helper__p000001",
        source_kind="context_retrieval_helper",
        source_table="trace_net_context_retrieval_helpers_v1",
        rag_bucket="context_retrieval_helper",
        embedding_bucket="context_retrieval_helper",
        candidate_type="context_retrieval_helper",
        evidence_layer="context_retrieval_helper",
        embedding_text="query tunnel for placards and title block",
        authority="retrieval_helper_only",
        answer_use_policy="retrieval_only",
        trust_tier="RETRIEVAL_ONLY",
        retrieval_only=True,
        citation_id="",
        source_url="",
        query_tunnel_terms=["placard", "title block"],
    )
    row.update(overrides)
    return row


def test_check_quality_passes_for_safe_points():
    points, rejected = build_qdrant_points([candidate(), context_helper()], embedding_dim=16)
    quality = check_qdrant_loader_quality(
        points=points,
        required_pages=[1],
        min_loaded_points=2,
        min_rag_points=1,
        min_context_helper_points=1,
        min_pages_with_points=1,
    )
    assert quality.status == "PASS"
    assert quality.summary["unsafe_qdrant_payload_count"] == 0


def test_check_quality_fails_when_required_page_missing():
    points, rejected = build_qdrant_points([candidate()], embedding_dim=16)
    quality = check_qdrant_loader_quality(points=points, required_pages=[1, 2], min_loaded_points=1)
    assert quality.status == "FAIL"
    assert quality.summary["required_page_missing_count"] == 1


def test_check_quality_fails_when_payload_allows_source_truth_mutation():
    points, rejected = build_qdrant_points([candidate()], embedding_dim=16)
    points[0]["payload"]["can_mutate_source_truth"] = True
    quality = check_qdrant_loader_quality(points=points, min_loaded_points=1)
    assert quality.status == "FAIL"
    assert quality.summary["unsafe_qdrant_payload_count"] > 0


def test_check_quality_respects_candidate_quality_pass_requirement():
    points, rejected = build_qdrant_points([candidate()], embedding_dim=16)
    quality = check_qdrant_loader_quality(
        points=points,
        candidate_quality={"status": "FAIL"},
        min_loaded_points=1,
        require_candidate_quality_pass=True,
    )
    assert quality.status == "FAIL"
    assert any(check["name"] == "candidate_quality_status" and not check["passed"] for check in quality.checks)


def test_build_and_load_dry_run_writes_artifacts(tmp_path: Path):
    candidates = tmp_path / "trace_net_embedding_candidates_v1.json"
    candidates.write_text(json.dumps({"records": [candidate(), context_helper()], "record_count": 2}), encoding="utf-8")
    (tmp_path / "trace_net_embedding_candidates_v1_quality.json").write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
    out = tmp_path / "out"
    result = build_and_load_qdrant_index(
        candidates_path=candidates,
        output_dir=out,
        embedding_dim=16,
        dry_run=True,
        require_candidate_quality_pass=True,
        required_pages=[1],
        min_loaded_points=2,
        min_rag_points=1,
        min_context_helper_points=1,
        min_pages_with_points=1,
        write_quality=True,
    )
    assert result["manifest"]["status"] == "DRY_RUN"
    assert result["quality"]["status"] == "PASS"
    assert (out / "trace_net_qdrant_loader_v1_manifest.json").exists()
    assert (out / "trace_net_qdrant_loader_v1_points_preview.jsonl").exists()
    assert (out / "trace_net_qdrant_loader_v1_quality.json").exists()


def test_main_load_and_quality_dry_run(tmp_path: Path):
    candidates = tmp_path / "trace_net_embedding_candidates_v1.json"
    candidates.write_text(json.dumps({"records": [candidate(), context_helper()], "record_count": 2}), encoding="utf-8")
    (tmp_path / "trace_net_embedding_candidates_v1_quality.json").write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
    out = tmp_path / "out"
    code = main_load([
        "--candidates-path", str(candidates),
        "--output-dir", str(out),
        "--embedding-dim", "16",
        "--dry-run",
        "--quality",
        "--require-candidate-quality-pass",
        "--require-first-pages", "1",
        "--min-loaded-points", "2",
        "--min-rag-points", "1",
        "--min-context-helper-points", "1",
        "--min-pages-with-points", "1",
    ])
    assert code == 0
    code = main_quality([
        "--manifest-path", str(out / "trace_net_qdrant_loader_v1_manifest.json"),
        "--require-first-pages", "1",
        "--min-loaded-points", "2",
        "--min-rag-points", "1",
        "--min-context-helper-points", "1",
        "--min-pages-with-points", "1",
        "--require-candidate-quality-pass",
        "--write-json",
    ])
    assert code == 0
    quality = read_json(out / "trace_net_qdrant_loader_v1_quality.json")
    assert quality["status"] == "PASS"


def test_iter_batches_validates_size():
    assert list(iter_batches([1, 2, 3], 2)) == [[1, 2], [3]]
    try:
        list(iter_batches([1], 0))
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_qdrant_client_404_collection_exists_false(monkeypatch):
    client = QdrantHTTPClient("http://localhost:6333")

    def fake_request(method, path, payload=None):
        raise KeyError(path)

    monkeypatch.setattr(client, "request", fake_request)
    assert client.get_collection("missing") is None


def test_qdrant_client_count_parses_result(monkeypatch):
    client = QdrantHTTPClient("http://localhost:6333")

    def fake_request(method, path, payload=None):
        assert method == "POST"
        assert path.endswith("/points/count")
        return {"result": {"count": 1476}}

    monkeypatch.setattr(client, "request", fake_request)
    assert client.count_points("trace_net_embedding_candidates_v1") == 1476


def test_summarize_points_reports_missing_traceability():
    points, rejected = build_qdrant_points([candidate(traceability={})], embedding_dim=16)
    summary = summarize_points(points, rejected)
    assert summary["missing_traceability_count"] == 1
