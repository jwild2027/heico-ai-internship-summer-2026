from __future__ import annotations

from tiff.trace_net_graph_overlay_part_lineage_v1 import QualityThresholds, evaluate_quality


def good_report() -> dict:
    return {
        "summary": {
            "page_count": 509,
            "overlay_node_count": 32446,
            "overlay_edge_count": 35907,
            "part_candidate_node_count": 301,
            "part_candidate_nodes_with_source_page_ids_count": 301,
            "part_candidate_missing_source_page_ids_count": 0,
            "part_candidate_source_page_link_count": 892,
            "missing_page_id_count": 302,
            "page_scoped_missing_page_id_count": 0,
            "orphan_edge_count": 0,
            "has_nomenclature_edges_preserved": 386,
            "has_context_v2_edges_preserved": 50,
            "confirmed_blank_pages_preserve_source_trace_count": 14,
            "direct_answer_allowed_count": 0,
            "claim_proof_allowed_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "answer_capable_without_citation_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "postgres_write_attempted": False,
            "source_graph_overlay_quality_status": "PASS",
            "writeback_mode": "dry_run_lineage_refinement",
        }
    }


def test_quality_passes_for_good_report() -> None:
    quality = evaluate_quality(
        good_report(),
        QualityThresholds(
            require_page_count=509,
            min_overlay_nodes=1000,
            min_overlay_edges=1000,
            min_part_candidate_nodes=301,
            min_part_candidate_nodes_with_source_page_ids=301,
            min_nomenclature_edges_preserved=1,
            min_context_v2_edges_preserved=50,
            min_confirmed_blank_preserve_source_trace=14,
            require_source_overlay_quality_pass=True,
        ),
    )
    assert quality["status"] == "PASS"


def test_quality_fails_source_truth_mutation() -> None:
    report = good_report()
    report["summary"]["source_truth_mutation_allowed_count"] = 1
    quality = evaluate_quality(report, QualityThresholds())
    assert quality["status"] == "FAIL"
