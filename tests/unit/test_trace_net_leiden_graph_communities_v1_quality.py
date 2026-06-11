from argparse import Namespace

from tiff.trace_net_leiden_graph_communities_v1 import build_quality


def args(**overrides):
    base = dict(
        require_page_count=2,
        min_communities=1,
        min_nodes=1,
        min_edges=1,
        min_page_nodes_with_community=2,
        min_part_candidate_nodes_with_community=1,
        min_table_cell_nodes_with_community=1,
        min_nomenclature_edges_preserved=1,
        min_context_v2_edges_preserved=1,
        min_confirmed_blank_preserve_source_trace=0,
        require_source_overlay_quality_pass=True,
    )
    base.update(overrides)
    return Namespace(**base)


def good_summary():
    return {
        "page_count": 2,
        "community_count": 1,
        "node_count": 6,
        "edge_count": 5,
        "page_nodes_with_community_count": 2,
        "part_candidate_nodes_with_community_count": 1,
        "table_cell_nodes_with_community_count": 1,
        "has_nomenclature_edges_preserved": 1,
        "has_context_v2_edges_preserved": 1,
        "confirmed_blank_pages_preserve_source_trace_count": 0,
        "source_overlay_quality_status": "PASS",
        "orphan_edge_count": 0,
        "direct_answer_allowed_count": 0,
        "claim_proof_allowed_count": 0,
        "retrieval_only_answer_allowed_count": 0,
        "source_truth_mutation_allowed_count": 0,
    }


def test_quality_passes_for_good_summary() -> None:
    q = build_quality(good_summary(), args())
    assert q["status"] == "PASS"


def test_quality_fails_for_orphan_edges() -> None:
    s = good_summary()
    s["orphan_edge_count"] = 1
    q = build_quality(s, args())
    assert q["status"] == "FAIL"


def test_quality_fails_for_missing_part_candidates() -> None:
    s = good_summary()
    s["part_candidate_nodes_with_community_count"] = 0
    q = build_quality(s, args())
    assert q["status"] == "FAIL"


def test_quality_fails_when_source_overlay_not_passed() -> None:
    s = good_summary()
    s["source_overlay_quality_status"] = "FAIL"
    q = build_quality(s, args())
    assert q["status"] == "FAIL"
