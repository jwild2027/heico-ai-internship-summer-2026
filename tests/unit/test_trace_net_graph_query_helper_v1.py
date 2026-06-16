from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_graph_query_helper_v1 import (
    QualityThresholds,
    build_graph_query_helper,
    extract_edges,
    extract_nodes,
    load_json,
)


def write(path: Path, payload) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def sample_graph(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    nodes = [
        {"node_id": "doc:T.P.120/1176", "node_type": "document", "label": "T.P. 120/1176"},
        {"node_id": "ata:25-21-00", "node_type": "ata_section", "label": "25-21-00"},
        {"node_id": "page:t_p_120_1176_p000003", "node_type": "page", "label": "Page 3", "properties": {"page_id": "t_p_120_1176_p000003", "ata_code": "25-21-00"}},
        {"node_id": "source:t_p_120_1176_p000003", "node_type": "source_link", "label": "Source page 3", "properties": {"source_uri": "http://localhost:8080/rescarta/t_p_120_1176/000003"}},
        {"node_id": "file:000003.tif", "node_type": "source_file", "label": "000003.tif", "properties": {"tiff_path": "000003.tif"}},
        {"node_id": "part:120-46137-001", "node_type": "part", "label": "120-46137-001", "properties": {"part_number": "120-46137-001"}},
        {"node_id": "mention:1", "node_type": "part_mention", "label": "mention 1"},
        {"node_id": "nom:1", "node_type": "nomenclature", "label": "TEST PART"},
    ]
    edges = [
        {"source_id": "doc:T.P.120/1176", "target_id": "page:t_p_120_1176_p000003", "edge_type": "HAS_PAGE"},
        {"source_id": "ata:25-21-00", "target_id": "page:t_p_120_1176_p000003", "edge_type": "CONTAINS_PAGE"},
        {"source_id": "page:t_p_120_1176_p000003", "target_id": "ata:25-21-00", "edge_type": "BELONGS_TO_ATA"},
        {"source_id": "page:t_p_120_1176_p000003", "target_id": "source:t_p_120_1176_p000003", "edge_type": "HAS_SOURCE_LINK"},
        {"source_id": "source:t_p_120_1176_p000003", "target_id": "file:000003.tif", "edge_type": "POINTS_TO_TIFF"},
        {"source_id": "part:120-46137-001", "target_id": "mention:1", "edge_type": "HAS_MENTION"},
        {"source_id": "mention:1", "target_id": "page:t_p_120_1176_p000003", "edge_type": "FOUND_ON"},
        {"source_id": "mention:1", "target_id": "part:120-46137-001", "edge_type": "REFERS_TO_PART"},
        {"source_id": "page:t_p_120_1176_p000003", "target_id": "part:120-46137-001", "edge_type": "MENTIONS_PART"},
        {"source_id": "part:120-46137-001", "target_id": "nom:1", "edge_type": "HAS_NOMENCLATURE"},
    ]
    dublin = {
        "quality_status": "PASS",
        "page_records": [
            {
                "page_id": "t_p_120_1176_p000003",
                "dc": {"dc:title": "Page 3", "dc:type": ["technical_manual_page", "text_page"]},
                "source_package": {"href": "file://./00000003.tif", "checksum_match": True},
            }
        ],
    }
    leiden = {
        "quality_status": "PASS",
        "page_navigation_hints": [
            {
                "page_id": "t_p_120_1176_p000003",
                "community_id": "tracenet_community_00011",
                "refined_label": "Part family community 120-46137",
                "navigation_confidence": "MODERATE_NAVIGATION_CONFIDENCE",
                "navigation_intent": "part_family_navigation",
            }
        ],
    }
    return (
        write(tmp_path / "nodes.json", {"nodes": nodes}),
        write(tmp_path / "edges.json", {"edges": edges}),
        write(tmp_path / "dublin.json", dublin),
        write(tmp_path / "leiden.json", leiden),
    )


def test_extract_nodes_and_edges_accept_common_shapes(tmp_path: Path) -> None:
    nodes_path, edges_path, _, _ = sample_graph(tmp_path)
    nodes = extract_nodes(json.loads(nodes_path.read_text()))
    edges = extract_edges(json.loads(edges_path.read_text()))
    assert len(nodes) == 8
    assert len(edges) == 10
    assert any(n["node_type"] == "part" for n in nodes)
    assert any(e["edge_type"] == "HAS_SOURCE_LINK" for e in edges)


def test_build_helper_resolves_part_page_and_ata(tmp_path: Path) -> None:
    nodes_path, edges_path, dublin_path, leiden_path = sample_graph(tmp_path)
    out_dir = tmp_path / "out"
    report = build_graph_query_helper(
        graph_nodes_path=nodes_path,
        graph_edges_path=edges_path,
        dublin_core_source_package_extension=dublin_path,
        leiden_navigation_metadata_bridge=leiden_path,
        part_numbers=["120-46137-001"],
        page_ids=["t_p_120_1176_p000003"],
        ata_codes=["25-21-00"],
        output_dir=out_dir,
        thresholds=QualityThresholds(
            min_query_records=3,
            min_page_results=3,
            min_source_resolved_results=3,
            min_part_query_results=1,
            min_page_query_results=1,
            min_ata_query_results=1,
            require_graph_nodes=True,
            require_graph_edges=True,
            require_no_answer_permission=True,
        ),
        write_quality=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["query_record_count"] == 3
    assert report["summary"]["source_resolved_result_count"] >= 3
    assert report["summary"]["result_with_dublin_core_identity_count"] >= 3
    assert report["summary"]["result_with_leiden_navigation_hint_count"] >= 3
    assert report["summary"]["can_answer_directly_count"] == 0
    assert (out_dir / "trace_net_graph_query_helper_v1.json").exists()
    assert (out_dir / "trace_net_graph_query_helper_v1_quality.json").exists()
    assert (out_dir / "trace_net_graph_query_helper_v1_records.jsonl").exists()

    reloaded = load_json(out_dir / "trace_net_graph_query_helper_v1.json")
    part_record = next(r for r in reloaded["query_records"] if r["query_type"] == "part_lookup")
    assert part_record["nomenclature"] == ["TEST PART"]
    assert part_record["pages"][0]["source_resolved"] is True


def test_helper_stays_retrieval_only(tmp_path: Path) -> None:
    nodes_path, edges_path, dublin_path, leiden_path = sample_graph(tmp_path)
    report = build_graph_query_helper(
        graph_nodes_path=nodes_path,
        graph_edges_path=edges_path,
        dublin_core_source_package_extension=dublin_path,
        leiden_navigation_metadata_bridge=leiden_path,
        part_numbers=["120-46137-001"],
        output_dir=tmp_path / "out",
        thresholds=QualityThresholds(require_no_answer_permission=True),
        write_quality=True,
    )
    assert report["summary"]["can_answer_directly_count"] == 0
    assert report["summary"]["can_prove_claims_count"] == 0
    assert all(record["retrieval_only"] is True for record in report["query_records"])
