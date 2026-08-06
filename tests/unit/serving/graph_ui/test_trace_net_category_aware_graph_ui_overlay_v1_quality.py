from __future__ import annotations

from tiff.trace_net_category_aware_graph_ui_overlay_v1 import quality_report


def test_quality_report_passes_clean_summary() -> None:
    report = {
        "summary": {
            "page_count": 2,
            "community_count": 1,
            "category_aware_community_card_count": 1,
            "page_category_profile_card_count": 2,
            "total_ui_edge_count": 5,
            "orphan_edge_count": 0,
            "giant_global_category_hub_count": 0,
            "category_as_proof_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "source_graph_ui_quality_status": "PASS",
            "source_category_aware_leiden_quality_status": "PASS",
        }
    }
    q = quality_report(
        report,
        require_page_count=2,
        require_source_graph_ui_quality_pass=True,
        require_source_category_overlay_quality_pass=True,
    )
    assert q["status"] == "PASS"


def test_quality_report_fails_on_orphan_edges() -> None:
    report = {
        "summary": {
            "page_count": 2,
            "community_count": 1,
            "category_aware_community_card_count": 1,
            "page_category_profile_card_count": 2,
            "total_ui_edge_count": 5,
            "orphan_edge_count": 1,
            "giant_global_category_hub_count": 0,
            "category_as_proof_count": 0,
            "source_truth_mutation_allowed_count": 0,
        }
    }
    q = quality_report(report, require_page_count=2)
    assert q["status"] == "FAIL"
    assert any("orphan" in issue for issue in q["issues"])


def test_quality_report_fails_on_category_as_proof() -> None:
    report = {
        "summary": {
            "page_count": 2,
            "community_count": 1,
            "category_aware_community_card_count": 1,
            "page_category_profile_card_count": 2,
            "total_ui_edge_count": 5,
            "orphan_edge_count": 0,
            "giant_global_category_hub_count": 0,
            "category_as_proof_count": 1,
            "source_truth_mutation_allowed_count": 0,
        }
    }
    q = quality_report(report)
    assert q["status"] == "FAIL"
