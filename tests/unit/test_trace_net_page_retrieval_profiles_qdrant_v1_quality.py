from __future__ import annotations

from tiff.trace_net_page_retrieval_profiles_v1 import (
    build_page_profile_bundle,
    build_page_profile_qdrant_points,
    check_qdrant_page_profile_quality,
    summarize_qdrant_points,
    unsafe_qdrant_payload_reasons,
)


def profile_bundle(n=2):
    pages = [
        {"page_id": f"t_p_120_1176_p{i:06d}", "page_number": i, "document_id": "t_p_120_1176"}
        for i in range(1, n + 1)
    ]
    embeddings = [
        {
            "embedding_candidate_id": f"src_{i}",
            "source_candidate_id": f"source_{i}",
            "page_id": f"t_p_120_1176_p{i:06d}",
            "rag_bucket": "source_evidence",
            "source_url": f"https://example.invalid/{i}",
            "embedding_text": f"source trace {i}",
            "can_answer_directly": False,
            "can_prove_claims": False,
            "requires_source_resolution": True,
            "requires_citation": True,
        }
        for i in range(1, n + 1)
    ]
    context = [
        {
            "helper_id": "ctx1",
            "page_id": "t_p_120_1176_p000001",
            "summary": "Context one",
            "retrieval_cues": ["cue one"],
            "query_tunnel_terms": ["term one"],
        }
    ]
    return build_page_profile_bundle(pages, embedding_records=embeddings, context_records=context)


def test_summarize_qdrant_points_counts_route_only_payloads():
    bundle = profile_bundle(2)
    points, rejected = build_page_profile_qdrant_points(bundle["records"], embedding_dim=24)
    summary = summarize_qdrant_points(points, rejected)
    assert summary["point_count"] == 2
    assert summary["page_count"] == 2
    assert summary["page_profile_point_count"] == 2
    assert summary["context_v2_point_count"] == 1
    assert summary["answer_capable_payload_count"] == 0
    assert summary["claim_proof_payload_count"] == 0


def test_unsafe_qdrant_payload_reasons_detect_bad_payload():
    bundle = profile_bundle(1)
    points, _ = build_page_profile_qdrant_points(bundle["records"], embedding_dim=24)
    payload = dict(points[0]["payload"])
    payload["can_answer_directly"] = True
    reasons = unsafe_qdrant_payload_reasons(payload)
    assert "can_answer_directly" in reasons


def test_check_qdrant_page_profile_quality_passes():
    bundle = profile_bundle(2)
    points, rejected = build_page_profile_qdrant_points(bundle["records"], embedding_dim=24)
    manifest = {"summary": summarize_qdrant_points(points, rejected), "loaded_point_count": 2, "qdrant_count": 2, "rejected_count": 0, "profiles_quality_status": "PASS"}
    result = check_qdrant_page_profile_quality(
        manifest,
        qdrant_count=2,
        min_loaded_points=2,
        min_pages_with_points=2,
        min_source_trace_points=2,
        min_context_v2_points=1,
        require_exact_qdrant_count=True,
        require_profile_quality_pass=True,
    )
    assert result.status == "PASS"


def test_check_qdrant_page_profile_quality_fails_on_mismatch():
    bundle = profile_bundle(2)
    points, rejected = build_page_profile_qdrant_points(bundle["records"], embedding_dim=24)
    manifest = {"summary": summarize_qdrant_points(points, rejected), "loaded_point_count": 2, "qdrant_count": 1, "rejected_count": 0, "profiles_quality_status": "PASS"}
    result = check_qdrant_page_profile_quality(
        manifest,
        qdrant_count=1,
        min_loaded_points=2,
        min_pages_with_points=2,
        min_source_trace_points=2,
        min_context_v2_points=1,
        require_exact_qdrant_count=True,
    )
    assert result.status == "FAIL"


def test_dry_run_loader_progress_reports_no_upload(tmp_path):
    import io
    from tiff.trace_net_page_retrieval_profiles_v1 import load_page_profiles_to_qdrant

    bundle = profile_bundle(2)
    stream = io.StringIO()
    manifest = load_page_profiles_to_qdrant(
        bundle,
        output_dir=tmp_path,
        dry_run=True,
        embedding_dim=24,
        progress=True,
        progress_every=1,
        progress_stream=stream,
    )
    output = stream.getvalue()
    assert manifest["dry_run"] is True
    assert manifest["progress_enabled"] is True
    assert manifest["loaded_point_count"] == 2
    assert "profiles=2" in output
    assert "dry run enabled" in output
