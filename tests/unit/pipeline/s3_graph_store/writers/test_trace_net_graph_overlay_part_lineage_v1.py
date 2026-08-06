from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_graph_overlay_part_lineage_v1 import (
    QualityThresholds,
    build_part_lineage_overlay,
    enrich_part_candidate_lineage,
    evaluate_quality,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def overlay_payload() -> dict:
    return {
        "schema_version": "trace_net_graph_writeback_overlay_v1",
        "status": "GRAPH_WRITEBACK_OVERLAY_BUILT",
        "quality_status": "PASS",
        "summary": {
            "writeback_mode": "dry_run_overlay",
            "page_count": 2,
            "has_nomenclature_edges_preserved": 386,
            "has_context_v2_edges_preserved": 50,
            "confirmed_blank_pages_preserve_source_trace_count": 14,
            "retrieval_only_answer_allowed_count": 0,
            "answer_capable_without_citation_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
        "node_plans": [
            {"node_id": "page::p1", "node_type": "Page", "page_id": "p1", "label": "Page 1", "properties": {}},
            {"node_id": "page::p2", "node_type": "Page", "page_id": "p2", "label": "Page 2", "properties": {}},
            {"node_id": "vu::p1", "node_type": "VisualUnderstanding", "page_id": "p1", "label": "Visual p1", "properties": {}},
            {"node_id": "vu::p2", "node_type": "VisualUnderstanding", "page_id": "p2", "label": "Visual p2", "properties": {}},
            {"node_id": "part::120", "node_type": "PartCandidate", "page_id": None, "label": "Part 120", "properties": {"part_number": "120-ABC"}},
            {"node_id": "trust::a", "node_type": "TrustAuthority", "page_id": None, "label": "Trust", "properties": {}},
        ],
        "edge_plans": [
            {"edge_id": "e1", "edge_type": "MAY_REFER_TO_PART", "source_node_id": "vu::p1", "target_node_id": "part::120", "page_id": "p1", "properties": {}},
            {"edge_id": "e2", "edge_type": "MAY_REFER_TO_PART", "source_node_id": "vu::p2", "target_node_id": "part::120", "page_id": "p2", "properties": {}},
        ],
    }


def test_enriches_part_candidate_source_page_ids() -> None:
    source = overlay_payload()
    nodes, edges, lineage = enrich_part_candidate_lineage(source["node_plans"], source["edge_plans"])
    part = next(n for n in nodes if n["node_type"] == "PartCandidate")
    assert part["node_scope"] == "cross_page_entity"
    assert part["source_page_ids"] == ["p1", "p2"]
    assert part["source_page_count"] == 2
    assert part["properties"]["source_page_ids"] == ["p1", "p2"]
    assert lineage["part_candidate_nodes_with_source_page_ids_count"] == 1
    assert lineage["part_candidate_missing_source_page_ids_count"] == 0
    assert len(edges) == 2


def test_build_report_passes_quality(tmp_path: Path) -> None:
    source_path = tmp_path / "overlay.json"
    write_json(source_path, overlay_payload())
    report = build_part_lineage_overlay(
        source_path,
        output_dir=tmp_path / "out",
        thresholds=QualityThresholds(
            require_page_count=2,
            min_overlay_nodes=6,
            min_overlay_edges=2,
            min_part_candidate_nodes=1,
            min_part_candidate_nodes_with_source_page_ids=1,
            min_nomenclature_edges_preserved=1,
            min_context_v2_edges_preserved=50,
            min_confirmed_blank_preserve_source_trace=14,
            require_source_overlay_quality_pass=True,
        ),
        write_quality=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["page_scoped_missing_page_id_count"] == 0
    assert report["summary"]["missing_page_id_count"] == 2  # PartCandidate + TrustAuthority are cross-scope.
    assert (tmp_path / "out" / "trace_net_graph_overlay_part_lineage_v1_part_candidates.jsonl").exists()


def test_quality_fails_when_part_candidate_has_no_source_pages() -> None:
    source = overlay_payload()
    source["edge_plans"] = []
    nodes, edges, lineage = enrich_part_candidate_lineage(source["node_plans"], source["edge_plans"])
    summary_report = {
        "summary": {
            "page_count": 2,
            "overlay_node_count": len(nodes),
            "overlay_edge_count": len(edges),
            "part_candidate_node_count": lineage["part_candidate_node_count"],
            "part_candidate_nodes_with_source_page_ids_count": lineage["part_candidate_nodes_with_source_page_ids_count"],
            "part_candidate_missing_source_page_ids_count": lineage["part_candidate_missing_source_page_ids_count"],
            "page_scoped_missing_page_id_count": 0,
            "orphan_edge_count": 0,
            "direct_answer_allowed_count": 0,
            "claim_proof_allowed_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "answer_capable_without_citation_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "postgres_write_attempted": False,
            "writeback_mode": "dry_run_lineage_refinement",
        }
    }
    quality = evaluate_quality(summary_report, QualityThresholds(min_part_candidate_nodes=1))
    assert quality["status"] == "FAIL"
    assert any(c["name"] == "part_candidate_missing_source_page_ids_zero" and not c["passed"] for c in quality["checks"])


def test_quality_fails_page_scoped_missing_page_id() -> None:
    report = {
        "summary": {
            "page_count": 1,
            "overlay_node_count": 2,
            "overlay_edge_count": 1,
            "part_candidate_node_count": 1,
            "part_candidate_nodes_with_source_page_ids_count": 1,
            "part_candidate_missing_source_page_ids_count": 0,
            "page_scoped_missing_page_id_count": 1,
            "orphan_edge_count": 0,
            "direct_answer_allowed_count": 0,
            "claim_proof_allowed_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "answer_capable_without_citation_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "postgres_write_attempted": False,
            "writeback_mode": "dry_run_lineage_refinement",
        }
    }
    quality = evaluate_quality(report, QualityThresholds())
    assert quality["status"] == "FAIL"
    assert any(c["name"] == "page_scoped_missing_page_id_zero" and not c["passed"] for c in quality["checks"])
