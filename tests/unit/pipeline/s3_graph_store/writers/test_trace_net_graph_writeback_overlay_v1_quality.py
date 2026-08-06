from __future__ import annotations

from tiff.trace_net_graph_writeback_overlay_v1 import QualityThresholds, evaluate_quality


def base_report() -> dict:
    return {
        "summary": {
            "page_count": 509,
            "overlay_node_count": 32446,
            "overlay_edge_count": 35907,
            "page_node_count": 509,
            "table_cell_node_count": 3090,
            "visual_node_count": 1018,
            "fishnet_node_count": 509,
            "citation_edge_count": 2860,
            "has_nomenclature_edges_preserved": 386,
            "has_context_v2_edges_preserved": 50,
            "required_context_v2_missing_page_count": 0,
            "confirmed_blank_pages_preserve_source_trace_count": 14,
            "orphan_edge_count": 0,
            "answer_capable_without_citation_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "direct_answer_allowed_count": 0,
            "claim_proof_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "postgres_write_attempted": False,
            "writeback_mode": "dry_run_overlay",
            "attachment_plan_quality_status": "PASS",
            "graph_explorer_quality_status": "PASS",
        }
    }


def test_quality_passes_expected_realistic_counts() -> None:
    quality = evaluate_quality(
        base_report(),
        QualityThresholds(
            require_page_count=509,
            min_overlay_nodes=1000,
            min_overlay_edges=1000,
            min_page_nodes=509,
            min_table_cell_nodes=100,
            min_visual_nodes=100,
            min_fishnet_nodes=509,
            min_citation_edges=1,
            min_nomenclature_edges_preserved=1,
            min_context_v2_edges_preserved=50,
            min_confirmed_blank_preserve_source_trace=14,
            require_attachment_quality_pass=True,
            require_graph_explorer_quality_pass=True,
        ),
    )
    assert quality["status"] == "PASS"


def test_quality_fails_if_context_v2_not_preserved() -> None:
    report = base_report()
    report["summary"]["has_context_v2_edges_preserved"] = 0
    quality = evaluate_quality(report, QualityThresholds(min_context_v2_edges_preserved=50))
    assert quality["status"] == "FAIL"


def test_quality_fails_if_postgres_write_attempted() -> None:
    report = base_report()
    report["summary"]["postgres_write_attempt_count"] = 1
    report["summary"]["postgres_write_attempted"] = True
    quality = evaluate_quality(report, QualityThresholds())
    assert quality["status"] == "FAIL"
