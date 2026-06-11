from __future__ import annotations

import json
from pathlib import Path

from tiff import trace_net_graph_overlay_part_property_normalizer_v1 as mod


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def sample_lineage_report() -> dict:
    nodes = [
        {
            "node_id": "page::p1",
            "node_type": "Page",
            "page_id": "p1",
            "label": "Page 1",
            "properties": {"page_id": "p1"},
        },
        {
            "node_id": "part_candidate::120-29067-005",
            "node_type": "PartCandidate",
            "label": "120-29067-005",
            "source_page_ids": ["p1", "p2"],
            "source_page_count": 2,
            "properties": {
                "node_scope": "cross_page_entity",
                "source_page_ids": ["p1", "p2"],
                "source_page_count": 2,
                "part_number": None,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "can_mutate_source_truth": False,
            },
        },
        {
            "node_id": "part_candidate::ABC-12345-678",
            "node_type": "PartCandidate",
            "label": "ABC-12345-678",
            "source_page_ids": ["p3"],
            "source_page_count": 1,
            "properties": {"node_scope": "cross_page_entity", "source_page_ids": ["p3"]},
        },
        {
            "node_id": "table_cell::c1",
            "node_type": "TableCell",
            "page_id": "p1",
            "label": "TableCell c1",
            "properties": {"page_id": "p1", "text": "1", "can_answer_directly": False},
        },
    ]
    edges = [
        {"edge_id": "e1", "edge_type": "HAS_TABLE_CELL", "source_node_id": "page::p1", "target_node_id": "table_cell::c1", "page_id": "p1"},
        {"edge_id": "e2", "edge_type": "MAY_REFER_TO_PART", "source_node_id": "page::p1", "target_node_id": "part_candidate::120-29067-005", "page_id": "p1"},
    ]
    return {
        "schema_version": "trace_net_graph_overlay_part_lineage_v1",
        "status": "GRAPH_OVERLAY_PART_LINEAGE_BUILT",
        "quality_status": "PASS",
        "summary": {
            "page_count": 1,
            "overlay_node_count": len(nodes),
            "overlay_edge_count": len(edges),
            "has_nomenclature_edges_preserved": 386,
            "has_context_v2_edges_preserved": 50,
            "confirmed_blank_pages_preserve_source_trace_count": 14,
            "source_lineage_quality_status": "PASS",
        },
        "node_plans": nodes,
        "edge_plans": edges,
    }


def test_derive_part_number_from_label_and_node_id() -> None:
    node = {"node_id": "part_candidate::120-46137-501", "node_type": "PartCandidate", "label": "PartCandidate | 120-46137-501", "properties": {}}
    part, source = mod.derive_part_number(node)
    assert part == "120-46137-501"
    assert source in {"node.label", "node_id"}


def test_normalizer_adds_part_number_and_family(tmp_path: Path) -> None:
    source = tmp_path / "lineage.json"
    write_json(source, sample_lineage_report())

    report = mod.build_graph_overlay_part_property_normalizer(
        source,
        output_dir=tmp_path / "out",
        thresholds=mod.QualityThresholds(
            require_page_count=1,
            min_overlay_nodes=4,
            min_overlay_edges=2,
            min_part_candidate_nodes=2,
            min_part_candidate_nodes_with_source_page_ids=2,
            min_part_candidate_nodes_with_part_number=2,
            min_part_families=2,
            min_table_cell_nodes=1,
            min_context_v2_edges_preserved=50,
            min_nomenclature_edges_preserved=1,
            min_confirmed_blank_preserve_source_trace=14,
            require_source_lineage_quality_pass=True,
        ),
    )

    assert report["quality_status"] == "PASS"
    summary = report["summary"]
    assert summary["part_candidate_nodes_with_part_number_count"] == 2
    assert summary["part_candidate_missing_part_number_count"] == 0
    assert summary["part_family_count"] == 2
    part_nodes = report["part_candidate_nodes"]
    assert {n["part_number"] for n in part_nodes} == {"120-29067-005", "ABC-12345-678"}
    assert all(n["node_scope"] == "cross_page_entity" for n in part_nodes)
    assert all(n["properties"]["can_answer_directly"] is False for n in part_nodes)


def test_quality_fails_when_part_number_missing() -> None:
    report = {"summary": {"part_candidate_node_count": 1, "part_candidate_nodes_with_part_number_count": 0, "part_candidate_missing_part_number_count": 1}}
    quality = mod.evaluate_quality(report, mod.QualityThresholds(min_part_candidate_nodes=1, min_part_candidate_nodes_with_part_number=1))
    assert quality["status"] == "FAIL"


def test_clean_part_number_rejects_non_part_text() -> None:
    assert mod.clean_part_number("PartCandidate") is None
    assert mod.clean_part_number("120-29067-005") == "120-29067-005"
