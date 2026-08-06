from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_graph_ui_community_overlay_v1 import build_graph_ui_community_overlay


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def base_source_overlay() -> dict:
    nodes = [
        {"node_id": "page::p1", "node_type": "Page", "label": "Page 1", "page_id": "p1", "properties": {}},
        {"node_id": "part_candidate::120-ABC", "node_type": "PartCandidate", "label": "120-ABC", "properties": {"part_number": "120-ABC", "source_page_ids": ["p1"]}},
        {"node_id": "table_cell::c1", "node_type": "TableCell", "label": "Cell", "page_id": "p1", "properties": {}},
        {"node_id": "nomenclature::x", "node_type": "Nomenclature", "label": "Nomenclature", "properties": {}},
        {"node_id": "context_v2::p1", "node_type": "PageContextV2", "label": "ContextV2", "page_id": "p1", "properties": {}},
    ]
    edges = [
        {"edge_id": "e1", "edge_type": "HAS_NOMENCLATURE", "source_node_id": "part_candidate::120-ABC", "target_node_id": "nomenclature::x", "properties": {}},
        {"edge_id": "e2", "edge_type": "HAS_CONTEXT_V2", "source_node_id": "page::p1", "target_node_id": "context_v2::p1", "page_id": "p1", "properties": {}},
    ]
    return {
        "quality_status": "PASS",
        "node_plans": nodes,
        "edge_plans": edges,
        "summary": {
            "quality_status": "PASS",
            "page_count": 1,
            "has_nomenclature_edges_preserved": 1,
            "has_context_v2_edges_preserved": 1,
            "confirmed_blank_pages_preserve_source_trace_count": 0,
        },
    }


def leiden_payload() -> dict:
    return {
        "quality_status": "PASS",
        "communities": [
            {"community_id": "tracenet_community_00001", "label": "Community 1", "node_count": 3, "page_count": 1, "part_families": ["120-ABC"], "page_ids": ["p1"]}
        ],
        "node_membership": [
            {"node_id": "page::p1", "node_type": "Page", "community_id": "tracenet_community_00001"},
            {"node_id": "part_candidate::120-ABC", "node_type": "PartCandidate", "community_id": "tracenet_community_00001"},
            {"node_id": "table_cell::c1", "node_type": "TableCell", "community_id": "tracenet_community_00001"},
        ],
        "summary": {"quality_status": "PASS", "page_count": 1, "page_nodes_with_community_count": 1, "part_candidate_nodes_with_community_count": 1, "table_cell_nodes_with_community_count": 1},
    }


def feedback_payload() -> dict:
    return {
        "quality_status": "PASS",
        "memory_records": [
            {"memory_id": "mem1", "target_type": "community", "target_id": "tracenet_community_00001", "feedback_signal": "boost_community", "rating_score": 1, "feedback_summary": "Helpful community", "llm_reference_allowed": True, "retrieval_advisory_allowed": True}
        ],
        "summary": {"quality_status": "PASS", "memory_record_count": 1},
    }


def community_aware_payload() -> dict:
    return {
        "quality_status": "PASS",
        "query_results": [
            {"query_id": "q1", "query": "test", "ranked_groups": [
                {"page_id": "p1", "community_ids": ["tracenet_community_00001"], "community_aware_rank": 1, "base_hybrid_score": 1.0, "community_boost": 0.1, "feedback_advisory_delta": 0.05, "community_aware_score": 1.15, "feedback_memory_ids_applied": ["mem1"]}
            ]}
        ],
        "summary": {"quality_status": "PASS", "community_aware_query_count": 1},
    }


def test_build_graph_ui_community_overlay_links_communities_feedback_results(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    leiden = tmp_path / "leiden.json"
    feedback = tmp_path / "feedback.json"
    community_aware = tmp_path / "community_aware.json"
    write_json(source, base_source_overlay())
    write_json(leiden, leiden_payload())
    write_json(feedback, feedback_payload())
    write_json(community_aware, community_aware_payload())

    report = build_graph_ui_community_overlay(
        source,
        leiden,
        feedback,
        community_aware,
        tmp_path / "out",
        require_source_overlay_quality_pass=True,
        require_leiden_quality_pass=True,
        require_feedback_quality_pass=True,
        require_community_aware_quality_pass=True,
        write_quality=True,
    )

    summary = report["summary"]
    assert report["quality_status"] == "PASS"
    assert summary["community_count"] == 1
    assert summary["feedback_memory_records_linked_count"] == 1
    assert summary["community_aware_results_linked_count"] == 1
    assert summary["orphan_community_edge_count"] == 0
    assert summary["community_as_proof_count"] == 0
    assert summary["feedback_as_proof_count"] == 0
    assert (tmp_path / "out" / "trace_net_graph_ui_community_overlay_v1.json").exists()


def test_community_overlay_nodes_are_advisory_only(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    leiden = tmp_path / "leiden.json"
    feedback = tmp_path / "feedback.json"
    community_aware = tmp_path / "community_aware.json"
    write_json(source, base_source_overlay())
    write_json(leiden, leiden_payload())
    write_json(feedback, feedback_payload())
    write_json(community_aware, community_aware_payload())

    report = build_graph_ui_community_overlay(source, leiden, feedback, community_aware, tmp_path / "out")
    for n in report["community_nodes"] + report["feedback_memory_nodes"] + report["community_aware_result_nodes"]:
        assert n["properties"]["can_answer_directly"] is False
        assert n["properties"]["can_prove_claims"] is False
        assert n["properties"]["can_mutate_source_truth"] is False
