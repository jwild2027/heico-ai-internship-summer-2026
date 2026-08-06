from __future__ import annotations

from tiff.trace_net_graph_ui_community_overlay_v1 import quality_report


def test_quality_report_passes_expected_counts() -> None:
    report = {
        "summary": {
            "page_count": 509,
            "overlay_node_count": 1001,
            "overlay_edge_count": 1001,
            "community_count": 229,
            "page_nodes_with_community_count": 509,
            "part_candidate_nodes_with_community_count": 301,
            "table_cell_nodes_with_community_count": 3090,
            "feedback_memory_records_linked_count": 4,
            "community_aware_results_linked_count": 40,
            "has_nomenclature_edges_preserved": 386,
            "has_context_v2_edges_preserved": 50,
            "confirmed_blank_pages_preserve_source_trace_count": 14,
            "orphan_edge_count": 0,
            "orphan_community_edge_count": 0,
            "community_as_proof_count": 0,
            "feedback_as_proof_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "source_overlay_quality_status": "PASS",
            "leiden_quality_status": "PASS",
            "feedback_memory_quality_status": "PASS",
            "community_aware_quality_status": "PASS",
        }
    }
    q = quality_report(
        report,
        require_page_count=509,
        min_overlay_nodes=1000,
        min_overlay_edges=1000,
        min_communities=229,
        min_page_nodes_with_community=509,
        min_part_candidate_nodes_with_community=301,
        min_table_cell_nodes_with_community=3090,
        min_feedback_memory_records_linked=1,
        min_community_aware_results_linked=1,
        min_nomenclature_edges_preserved=1,
        min_context_v2_edges_preserved=50,
        min_confirmed_blank_preserve_source_trace=14,
        require_source_overlay_quality_pass=True,
        require_leiden_quality_pass=True,
        require_feedback_quality_pass=True,
        require_community_aware_quality_pass=True,
    )
    assert q["status"] == "PASS"


def test_quality_report_fails_if_feedback_becomes_proof() -> None:
    report = {"summary": {"feedback_as_proof_count": 1, "orphan_edge_count": 0, "orphan_community_edge_count": 0, "community_as_proof_count": 0, "retrieval_only_answer_allowed_count": 0, "source_truth_mutation_allowed_count": 0, "postgres_write_attempt_count": 0}}
    q = quality_report(report)
    assert q["status"] == "FAIL"
    failed = {c["name"] for c in q["checks"] if not c["passed"]}
    assert "feedback_as_proof_zero" in failed
