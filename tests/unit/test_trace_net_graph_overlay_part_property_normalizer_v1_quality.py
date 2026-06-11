from __future__ import annotations

from tiff import trace_net_graph_overlay_part_property_normalizer_v1 as mod


def test_quality_passes_for_safe_summary() -> None:
    report = {
        "summary": {
            "page_count": 509,
            "overlay_node_count": 32446,
            "overlay_edge_count": 35907,
            "part_candidate_node_count": 301,
            "part_candidate_nodes_with_source_page_ids_count": 301,
            "part_candidate_nodes_with_part_number_count": 301,
            "part_candidate_missing_part_number_count": 0,
            "part_family_count": 100,
            "table_cell_node_count": 3090,
            "has_context_v2_edges_preserved": 50,
            "has_nomenclature_edges_preserved": 386,
            "confirmed_blank_pages_preserve_source_trace_count": 14,
            "page_scoped_missing_page_id_count": 0,
            "orphan_edge_count": 0,
            "direct_answer_allowed_count": 0,
            "claim_proof_allowed_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "postgres_write_attempted": False,
            "source_lineage_quality_status": "PASS",
        }
    }
    q = mod.evaluate_quality(
        report,
        mod.QualityThresholds(
            require_page_count=509,
            min_overlay_nodes=1000,
            min_overlay_edges=1000,
            min_part_candidate_nodes=301,
            min_part_candidate_nodes_with_source_page_ids=301,
            min_part_candidate_nodes_with_part_number=301,
            min_part_families=1,
            min_table_cell_nodes=3090,
            min_context_v2_edges_preserved=50,
            min_nomenclature_edges_preserved=1,
            min_confirmed_blank_preserve_source_trace=14,
            require_source_lineage_quality_pass=True,
        ),
    )
    assert q["status"] == "PASS"


def test_quality_requires_no_answer_permission() -> None:
    report = {"summary": {"direct_answer_allowed_count": 1, "postgres_write_attempted": False, "postgres_write_attempt_count": 0}}
    q = mod.evaluate_quality(report, mod.QualityThresholds())
    assert q["status"] == "FAIL"
