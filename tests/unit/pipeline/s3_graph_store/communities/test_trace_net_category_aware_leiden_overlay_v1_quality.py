from __future__ import annotations

from tiff.trace_net_category_aware_leiden_overlay_v1 import build_overlay, quality_report


def sample_leiden() -> dict:
    return {
        "schema_version": "trace_net_leiden_graph_communities_v1",
        "quality_status": "PASS",
        "summary": {"community_count": 1, "page_count": 2},
        "communities": [{"community_id": "tracenet_community_00001", "label": "Test", "page_ids": ["p1", "p2"]}],
        "node_membership": [],
    }


def sample_taxonomy() -> dict:
    return {
        "schema_version": "trace_net_element_category_taxonomy_v1",
        "quality_status": "PASS",
        "summary": {"page_count": 2, "page_category_profile_count": 2},
        "page_category_profiles": [
            {
                "page_id": "p1",
                "page_category_label": "text_source_page",
                "dc_type": ["technical_manual_page", "text_page"],
                "element_family_counts": {"source": 2, "text": 2, "citation": 1},
                "element_category_counts": {"source_trace": 1},
                "leiden_hint_element_families": ["source", "text", "citation"],
                "suppressed_leiden_hint_families": ["table"],
                "review_required": False,
            },
            {
                "page_id": "p2",
                "page_category_label": "table_parts_diagram_page_review",
                "dc_type": ["technical_manual_page", "table_page", "visual_page", "parts_page"],
                "element_family_counts": {"source": 1, "table": 20, "diagram": 5, "part": 4, "review": 1},
                "element_category_counts": {"table_cell": 20},
                "leiden_hint_element_families": ["source", "table", "diagram", "part", "review"],
                "suppressed_leiden_hint_families": [],
                "review_required": True,
            },
        ],
    }


def test_quality_report_passes_with_thresholds() -> None:
    report = build_overlay(leiden=sample_leiden(), taxonomy=sample_taxonomy())
    quality = quality_report(
        report,
        require_page_count=2,
        min_communities=1,
        min_page_category_profiles=2,
        min_communities_with_category_summary=1,
        min_category_overlay_edges=1,
        require_source_leiden_quality_pass=True,
        require_source_taxonomy_quality_pass=True,
    )
    assert quality["status"] == "PASS"


def test_quality_report_requires_no_source_truth_mutation() -> None:
    report = build_overlay(leiden=sample_leiden(), taxonomy=sample_taxonomy())
    report["summary"]["source_truth_mutation_allowed_count"] = 1
    quality = quality_report(report)
    assert quality["status"] == "FAIL"


def test_quality_report_requires_source_status_when_enabled() -> None:
    leiden = sample_leiden()
    leiden["quality_status"] = "FAIL"
    report = build_overlay(leiden=leiden, taxonomy=sample_taxonomy())
    quality = quality_report(report, require_source_leiden_quality_pass=True)
    assert quality["status"] == "FAIL"
