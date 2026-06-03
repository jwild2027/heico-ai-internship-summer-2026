from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_postgres_graph_audit import compute_graph_components
from tiff.trace_net_graph_audit_quality import run_quality as run_graph_quality


def test_compute_graph_components_connected_and_singleton():
    nodes = ["a", "b", "c", "d"]
    edges = [("a", "b"), ("b", "c")]
    m = compute_graph_components(nodes, edges)
    assert m["component_count"] == 2
    assert m["largest_component_nodes"] == 3
    assert m["singleton_components"] == 1
    assert m["orphan_edges_scan"] == 0


def test_compute_graph_components_orphan_and_self_loop():
    nodes = ["a", "b"]
    edges = [("a", "a"), ("a", "missing")]
    m = compute_graph_components(nodes, edges)
    assert m["self_loop_edges_scan"] == 1
    assert m["orphan_edges_scan"] == 1


def test_graph_quality_passes_minimal_summary():
    summary = {
        "postgres_pages": 509,
        "postgres_graph_nodes": 30000,
        "postgres_graph_edges": 100000,
        "largest_component_nodes": 100,
        "graph_orphan_edges_sql": 0,
        "pages_without_graph_node": 0,
        "rag_candidates_without_page": 0,
        "citations_without_page": 0,
        "unsafe_rag_candidate_records": 0,
        "rag_candidate_missing_source_url": 0,
    }
    q = run_graph_quality(summary, {"min_pages": 509, "min_graph_nodes": 1, "min_graph_edges": 1, "max_orphan_edges": 0, "max_pages_without_graph_node": 0})
    assert q["status"] == "OK"


def test_graph_quality_fails_orphans():
    summary = {
        "postgres_pages": 509,
        "postgres_graph_nodes": 10,
        "postgres_graph_edges": 10,
        "largest_component_nodes": 5,
        "graph_orphan_edges_sql": 2,
        "pages_without_graph_node": 0,
        "rag_candidates_without_page": 0,
        "citations_without_page": 0,
        "unsafe_rag_candidate_records": 0,
        "rag_candidate_missing_source_url": 0,
    }
    q = run_graph_quality(summary, {"min_pages": 1, "min_graph_nodes": 1, "min_graph_edges": 1, "max_orphan_edges": 0})
    assert q["status"] == "FAIL"
