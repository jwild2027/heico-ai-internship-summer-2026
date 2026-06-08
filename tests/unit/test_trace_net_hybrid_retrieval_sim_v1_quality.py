from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_hybrid_retrieval_sim_v1 import build_quality_report, check_hybrid_retrieval_sim_quality, write_json


def passing_summary():
    return {
        "hybrid_query_count": 5,
        "queries_with_results_count": 5,
        "grouped_result_count": 25,
        "candidate_hit_count": 25,
        "page_profile_hit_count": 25,
        "resolved_candidate_hit_count": 25,
        "resolved_page_profile_hit_count": 25,
        "missing_page_id_count": 0,
        "unsafe_result_count": 0,
        "unsafe_hit_payload_count": 0,
        "direct_answer_allowed_result_count": 0,
        "claim_proof_allowed_without_authority_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "answer_capable_page_profile_hit_count": 0,
        "context_helper_answer_allowed_hit_count": 0,
        "source_evidence_answer_allowed_hit_count": 0,
        "requires_source_resolution_false_count": 0,
        "requires_citation_false_count": 0,
        "requires_authority_gate_false_count": 0,
        "candidate_collection_count": 1476,
        "page_profile_collection_count": 509,
        "embedding_dim": 1024,
        "vector_smoke_status": "PASS",
    }


def test_build_quality_report_with_strict_counts_passes():
    quality = build_quality_report(
        passing_summary(),
        min_hybrid_queries=5,
        min_queries_with_results=5,
        min_grouped_results=25,
        min_candidate_hits=25,
        min_page_profile_hits=25,
        min_resolved_candidate_hits=25,
        min_resolved_page_profile_hits=25,
        min_candidate_collection_count=1476,
        min_page_profile_collection_count=509,
        require_candidate_count=1476,
        require_page_profile_count=509,
        require_embedding_dim=1024,
        require_vector_smoke_quality_pass=True,
    )
    assert quality.status == "PASS"


def test_build_quality_report_fails_bad_vector_smoke_status():
    summary = passing_summary()
    summary["vector_smoke_status"] = "FAIL"
    quality = build_quality_report(summary, require_vector_smoke_quality_pass=True)
    assert quality.status == "FAIL"
    assert any(check["name"] == "vector_smoke_status_pass" for check in quality.checks)


def test_check_hybrid_retrieval_sim_quality_from_report_with_fake_qdrant(tmp_path: Path, monkeypatch):
    report = tmp_path / "report.json"
    write_json(report, {"summary": passing_summary()})

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def count_points(self, collection: str, exact: bool = True) -> int:
            return 1476 if "embedding" in collection else 509

    monkeypatch.setattr("tiff.trace_net_hybrid_retrieval_sim_v1.QdrantHybridClient", FakeClient)
    result = check_hybrid_retrieval_sim_quality(
        report_path=report,
        qdrant_url="http://fake-qdrant",
        min_hybrid_queries=5,
        min_queries_with_results=5,
        min_grouped_results=25,
        min_candidate_hits=25,
        min_page_profile_hits=25,
        min_resolved_candidate_hits=25,
        min_resolved_page_profile_hits=25,
        min_candidate_collection_count=1476,
        min_page_profile_collection_count=509,
        require_candidate_count=1476,
        require_page_profile_count=509,
        require_embedding_dim=1024,
        require_vector_smoke_quality_pass=True,
        write_json_report=True,
    )
    assert result["status"] == "PASS"
    assert (tmp_path / "trace_net_hybrid_retrieval_sim_v1_quality.json").exists()
