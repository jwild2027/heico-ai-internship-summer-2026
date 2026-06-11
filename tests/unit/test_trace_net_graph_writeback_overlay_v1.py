from __future__ import annotations

import json
from pathlib import Path

import pytest

from tiff.trace_net_graph_writeback_overlay_v1 import (
    QualityThresholds,
    build_graph_writeback_overlay,
    evaluate_quality,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def sample_attachment(tmp_path: Path) -> Path:
    payload = {
        "schema_version": "trace_net_element_graph_attachment_plan_v1",
        "status": "ELEMENT_GRAPH_ATTACHMENT_PLAN_BUILT",
        "quality_status": "PASS",
        "summary": {
            "page_count": 2,
            "node_plan_count": 8,
            "edge_plan_count": 6,
        },
        "node_plans": [
            {"node_id": "page::p1", "node_type": "Page", "page_id": "p1", "label": "Page 1"},
            {"node_id": "table::p1", "node_type": "TableElement", "page_id": "p1", "label": "Table p1"},
            {"node_id": "cell::p1::r1::c1", "node_type": "TableCell", "page_id": "p1", "label": "TableCell", "properties": {"text": "120-46137-001", "requires_citation": False}},
            {"node_id": "visual::p1", "node_type": "VisualUnderstanding", "page_id": "p1", "label": "Visual p1"},
            {"node_id": "fishnet::p1", "node_type": "FishnetRetryPlan", "page_id": "p1", "label": "Fishnet p1"},
            {"node_id": "evidence::p1", "node_type": "EvidenceCandidate", "page_id": "p1", "label": "Evidence p1", "properties": {"requires_citation": True}},
            {"node_id": "citation::c1", "node_type": "Citation", "page_id": "p1", "label": "Citation c1"},
            {"node_id": "blank::p2", "node_type": "BlankSourceTracePreservation", "page_id": "p2", "label": "Blank p2"},
            {"node_id": "page::p2", "node_type": "Page", "page_id": "p2", "label": "Page 2"},
        ],
        "edge_plans": [
            {"edge_type": "HAS_TABLE_ELEMENT", "source_node_id": "page::p1", "target_node_id": "table::p1", "page_id": "p1"},
            {"edge_type": "HAS_TABLE_CELL", "source_node_id": "table::p1", "target_node_id": "cell::p1::r1::c1", "page_id": "p1"},
            {"edge_type": "HAS_VISUAL_UNDERSTANDING", "source_node_id": "page::p1", "target_node_id": "visual::p1", "page_id": "p1"},
            {"edge_type": "HAS_FISHNET_RETRY_PLAN", "source_node_id": "page::p1", "target_node_id": "fishnet::p1", "page_id": "p1"},
            {"edge_type": "HAS_EVIDENCE_CANDIDATE", "source_node_id": "page::p1", "target_node_id": "evidence::p1", "page_id": "p1"},
            {"edge_type": "HAS_CITATION", "source_node_id": "evidence::p1", "target_node_id": "citation::c1", "page_id": "p1"},
            {"edge_type": "HAS_BLANK_SOURCE_TRACE_PRESERVATION", "source_node_id": "page::p2", "target_node_id": "blank::p2", "page_id": "p2"},
        ],
    }
    path = tmp_path / "attachment.json"
    write_json(path, payload)
    return path


def graph_quality_dir(tmp_path: Path) -> Path:
    root = tmp_path / "graph_explorer"
    write_json(
        root / "trace_net_graph_explorer_v2_nomenclature_quality.json",
        {
            "status": "PASS",
            "nomenclature_nodes": 2,
            "has_nomenclature_edges": 3,
            "page_context_v2_nodes": 2,
            "has_context_v2_edges": 2,
            "required_context_v2_missing_page_count": 0,
        },
    )
    return root


def test_build_graph_overlay_preserves_safety_and_existing_graph_quality(tmp_path: Path) -> None:
    report = build_graph_writeback_overlay(
        sample_attachment(tmp_path),
        graph_quality_dir(tmp_path),
        tmp_path / "out",
        thresholds=QualityThresholds(
            require_page_count=2,
            min_overlay_nodes=8,
            min_overlay_edges=6,
            min_page_nodes=2,
            min_table_cell_nodes=1,
            min_visual_nodes=1,
            min_fishnet_nodes=1,
            min_citation_edges=1,
            min_nomenclature_edges_preserved=3,
            min_context_v2_edges_preserved=2,
            min_confirmed_blank_preserve_source_trace=1,
            require_attachment_quality_pass=True,
            require_graph_explorer_quality_pass=True,
        ),
    )

    assert report["quality_status"] == "PASS"
    summary = report["summary"]
    assert summary["table_cell_node_count"] == 1
    assert summary["orphan_edge_count"] == 0
    assert summary["has_nomenclature_edges_preserved"] == 3
    assert summary["has_context_v2_edges_preserved"] == 2
    assert summary["postgres_write_attempt_count"] == 0
    assert Path(report["nodes_path"]).exists()
    assert Path(report["edges_path"]).exists()


def test_build_graph_overlay_refuses_postgres_writeback_mode(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        build_graph_writeback_overlay(sample_attachment(tmp_path), graph_quality_dir(tmp_path), tmp_path / "out", mode="write-postgres")


def test_quality_fails_orphan_edges() -> None:
    report = {
        "summary": {
            "page_count": 1,
            "overlay_node_count": 1,
            "overlay_edge_count": 1,
            "page_node_count": 1,
            "table_cell_node_count": 0,
            "visual_node_count": 0,
            "fishnet_node_count": 0,
            "citation_edge_count": 0,
            "has_nomenclature_edges_preserved": 0,
            "has_context_v2_edges_preserved": 0,
            "confirmed_blank_pages_preserve_source_trace_count": 0,
            "orphan_edge_count": 1,
            "answer_capable_without_citation_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "direct_answer_allowed_count": 0,
            "claim_proof_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "postgres_write_attempted": False,
            "writeback_mode": "dry_run_overlay",
        }
    }
    quality = evaluate_quality(report, QualityThresholds(require_page_count=1))
    assert quality["status"] == "FAIL"
    assert any(c["name"] == "orphan_edge_count_zero" and not c["passed"] for c in quality["checks"])
