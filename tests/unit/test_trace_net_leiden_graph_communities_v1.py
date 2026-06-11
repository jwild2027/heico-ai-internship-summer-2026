import json
from pathlib import Path

from tiff.trace_net_leiden_graph_communities_v1 import build_leiden_graph_communities, build_report


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def sample_overlay() -> dict:
    nodes = [
        {"node_id": "page::p1", "node_type": "Page", "label": "Page 1", "page_id": "p1", "properties": {"page_id": "p1"}},
        {"node_id": "page::p2", "node_type": "Page", "label": "Page 2", "page_id": "p2", "properties": {"page_id": "p2"}},
        {"node_id": "page_element_registry::p1", "node_type": "PageElementRegistry", "label": "Registry p1", "page_id": "p1", "properties": {"can_answer_directly": False}},
        {"node_id": "table_cell::c1", "node_type": "TableCell", "label": "Cell 1", "page_id": "p1", "properties": {"text": "120-1"}},
        {"node_id": "part_candidate::120-11111-001", "node_type": "PartCandidate", "label": "120-11111-001", "source_page_ids": ["p1", "p2"], "part_number": "120-11111-001", "properties": {"part_number": "120-11111-001", "source_page_ids": ["p1", "p2"], "can_answer_directly": False}},
        {"node_id": "trust_authority::source_text", "node_type": "TrustAuthority", "label": "trust", "properties": {}},
    ]
    edges = [
        {"source_node_id": "page::p1", "target_node_id": "page_element_registry::p1", "edge_type": "HAS_PAGE_ELEMENT_REGISTRY", "page_id": "p1"},
        {"source_node_id": "page::p1", "target_node_id": "table_cell::c1", "edge_type": "HAS_TABLE_CELL", "page_id": "p1"},
        {"source_node_id": "page::p1", "target_node_id": "part_candidate::120-11111-001", "edge_type": "MAY_REFER_TO_PART", "page_id": "p1"},
        {"source_node_id": "page::p2", "target_node_id": "part_candidate::120-11111-001", "edge_type": "MAY_REFER_TO_PART", "page_id": "p2"},
        {"source_node_id": "page::p1", "target_node_id": "trust_authority::source_text", "edge_type": "HAS_TRUST_AUTHORITY", "page_id": "p1"},
    ]
    return {
        "quality_status": "PASS",
        "summary": {
            "page_count": 2,
            "has_nomenclature_edges_preserved": 1,
            "has_context_v2_edges_preserved": 1,
            "confirmed_blank_pages_preserve_source_trace_count": 0,
        },
        "node_plans": nodes,
        "edge_plans": edges,
    }


def test_build_report_assigns_communities_and_preserves_safety() -> None:
    report = build_report(sample_overlay(), algorithm="connected-components")
    summary = report["summary"]
    assert report["quality_status"] == "PASS"
    assert summary["community_count"] >= 1
    assert summary["page_nodes_with_community_count"] == 2
    assert summary["part_candidate_nodes_with_community_count"] == 1
    assert summary["table_cell_nodes_with_community_count"] == 1
    assert summary["orphan_edge_count"] == 0
    assert summary["direct_answer_allowed_count"] == 0
    assert summary["source_truth_mutation_allowed_count"] == 0
    assert all(not c["can_answer_directly"] for c in report["communities"])


def test_build_writes_outputs(tmp_path: Path) -> None:
    source = tmp_path / "overlay.json"
    write_json(source, sample_overlay())
    out = tmp_path / "communities"
    report = build_leiden_graph_communities(source, out, algorithm="connected-components")
    assert Path(report["report_path"]).exists()
    assert Path(report["communities_path"]).exists()
    assert Path(report["membership_path"]).exists()
    assert Path(report["quality_path"]).exists()


def test_trust_authority_edges_are_excluded_from_community_graph() -> None:
    report = build_report(sample_overlay(), algorithm="connected-components")
    assert report["summary"]["community_graph_edge_count"] == 4
