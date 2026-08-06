import json
from pathlib import Path
from tiff.trace_net_graph_explorer_quality import run_quality


def test_quality_passes_minimal_artifacts(tmp_path: Path):
    html_path = tmp_path / "x.html"
    data_path = tmp_path / "x.json"
    html_path.write_text("TRACE-Net Graph Explorer Click any node", encoding="utf-8")
    data_path.write_text("{}", encoding="utf-8")
    summary = {
        "nodes": 10,
        "edges": 12,
        "page_nodes": 2,
        "part_nodes": 1,
        "candidate_nodes": 3,
        "citation_nodes": 1,
        "node_type_counts": {"page": 2, "part": 1, "candidate": 3, "citation": 1},
        "edge_type_counts": {"HAS_CANDIDATE": 3, "PART_ON_PAGE": 2, "HAS_TRUST_TRAIT": 2},
    }
    report = run_quality(summary, {"min_nodes": 1, "min_edges": 1, "min_pages": 1, "min_part_nodes": 1, "min_candidate_nodes": 1, "min_citation_nodes": 1, "min_has_candidate_edges": 1, "min_part_page_edges": 1, "min_trust_edges": 1, "require_html_text": True}, html_path, data_path)
    assert report["status"] == "OK"


def test_quality_fails_missing_part_nodes(tmp_path: Path):
    html_path = tmp_path / "x.html"
    data_path = tmp_path / "x.json"
    html_path.write_text("TRACE-Net Graph Explorer Click any node", encoding="utf-8")
    data_path.write_text("{}", encoding="utf-8")
    summary = {"nodes": 3, "edges": 1, "page_nodes": 1, "part_nodes": 0, "candidate_nodes": 1, "node_type_counts": {}, "edge_type_counts": {"HAS_CANDIDATE": 1, "PART_ON_PAGE": 0, "HAS_TRUST_TRAIT": 1}}
    report = run_quality(summary, {"min_nodes": 1, "min_edges": 1, "min_pages": 1, "min_part_nodes": 1, "min_candidate_nodes": 1, "min_citation_nodes": 0, "min_has_candidate_edges": 1, "min_part_page_edges": 0, "min_trust_edges": 1}, html_path, data_path)
    assert report["status"] == "FAIL"
