from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_community_aware_retrieval_sim_v1 import (
    build_community_indexes,
    run_community_aware_retrieval_sim,
    safe_feedback_records,
)


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def hybrid_payload() -> dict:
    return {
        "schema_version": "trace_net_hybrid_retrieval_sim_v1",
        "quality_status": "PASS",
        "summary": {"embedding_dim": 1024, "embedding_mode": "ollama", "embedding_model_name": "bge-m3:latest"},
        "query_results": [
            {
                "query_id": "manual_revision_history",
                "query": "Which pages discuss manual revision history?",
                "ranked_groups": [
                    {"rank": 1, "page_id": "t_p_120_1176_p000013", "hybrid_score": 1.4, "safety_status": "retrieval_safe", "citation_ids": ["cite:source_text:t_p_120_1176_p000013:e2f10387d0"]},
                    {"rank": 2, "page_id": "t_p_120_1176_p000001", "hybrid_score": 1.2, "safety_status": "retrieval_safe", "citation_ids": ["cite:source_text:t_p_120_1176_p000001:092378ba20"]},
                ],
            }
        ],
    }


def leiden_payload() -> dict:
    return {
        "schema_version": "trace_net_leiden_graph_communities_v1",
        "quality_status": "PASS",
        "summary": {"community_algorithm_used": "leiden", "leiden_used": True, "fallback_used": False},
        "communities": [
            {"community_id": "tracenet_community_00001", "label": "revision community", "page_ids": ["t_p_120_1176_p000013", "t_p_120_1176_p000001"]}
        ],
        "node_membership": [
            {"node_id": "page::t_p_120_1176_p000013", "node_type": "Page", "page_id": "t_p_120_1176_p000013", "community_id": "tracenet_community_00001"},
            {"node_id": "page::t_p_120_1176_p000001", "node_type": "Page", "page_id": "t_p_120_1176_p000001", "community_id": "tracenet_community_00001"},
        ],
    }


def feedback_payload() -> dict:
    return {
        "schema_version": "trace_net_feedback_memory_v1",
        "quality_status": "PASS",
        "summary": {"feedback_event_count": 2, "memory_record_count": 2, "raw_feedback_direct_to_llm_count": 0, "feedback_can_answer_directly_count": 0, "feedback_can_prove_claims_count": 0, "feedback_can_mutate_source_truth_count": 0},
        "memory_records": [
            {"memory_id": "fbmem_1", "target_type": "community", "target_id": "tracenet_community_00001", "rating_score": 1, "retrieval_advisory_allowed": True, "llm_reference_allowed": True, "can_answer_directly": False, "can_prove_claims": False, "can_mutate_source_truth": False},
            {"memory_id": "fbmem_2", "target_type": "answer", "target_id": "trace_net_final_answer_gate_v1", "rating_score": -1, "prompt_injection_flagged": True, "retrieval_advisory_allowed": True, "llm_reference_allowed": False, "can_answer_directly": False, "can_prove_claims": False, "can_mutate_source_truth": False},
        ],
    }


def test_community_index_maps_pages() -> None:
    idx = build_community_indexes(leiden_payload())
    assert idx["page_to_communities"]["t_p_120_1176_p000013"] == ["tracenet_community_00001"]
    assert idx["community_count"] == 1


def test_safe_feedback_records_filters_authority() -> None:
    payload = feedback_payload()
    payload["memory_records"].append({"memory_id": "bad", "can_answer_directly": True, "rating_score": 1})
    safe = safe_feedback_records(payload)
    assert len(safe) == 2


def test_run_community_aware_retrieval_sim_passes(tmp_path: Path) -> None:
    hybrid = write_json(tmp_path / "hybrid.json", hybrid_payload())
    leiden = write_json(tmp_path / "leiden.json", leiden_payload())
    feedback = write_json(tmp_path / "feedback.json", feedback_payload())
    report = run_community_aware_retrieval_sim(
        hybrid_report_path=hybrid,
        leiden_communities_path=leiden,
        feedback_memory_path=feedback,
        output_dir=tmp_path / "out",
        max_groups_per_query=2,
        min_queries=1,
        min_queries_with_results=1,
        min_grouped_results=2,
        min_community_boosted_results=2,
        min_feedback_boosted_results=2,
        require_hybrid_quality_pass=True,
        require_leiden_quality_pass=True,
        require_feedback_quality_pass=True,
        write_quality=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["community_boosted_result_count"] == 2
    assert report["summary"]["feedback_adjusted_result_count"] == 2
    assert report["summary"]["community_as_proof_count"] == 0
    assert report["summary"]["feedback_as_proof_count"] == 0
    assert Path(report["groups_path"]).exists()


def test_community_aware_groups_do_not_grant_answer_authority(tmp_path: Path) -> None:
    hybrid = hybrid_payload()
    hybrid["query_results"][0]["ranked_groups"][0]["can_answer_directly"] = True
    report = run_community_aware_retrieval_sim(
        hybrid_report_path=write_json(tmp_path / "hybrid.json", hybrid),
        leiden_communities_path=write_json(tmp_path / "leiden.json", leiden_payload()),
        feedback_memory_path=write_json(tmp_path / "feedback.json", feedback_payload()),
        output_dir=tmp_path / "out",
        min_queries=1,
        min_queries_with_results=1,
        min_grouped_results=1,
        min_community_boosted_results=1,
        min_feedback_boosted_results=0,
        require_hybrid_quality_pass=True,
        require_leiden_quality_pass=True,
        require_feedback_quality_pass=True,
    )
    group = report["groups"][0]
    assert group["can_answer_directly"] is False
    assert group["community_as_proof"] is False
    assert group["feedback_as_proof"] is False
