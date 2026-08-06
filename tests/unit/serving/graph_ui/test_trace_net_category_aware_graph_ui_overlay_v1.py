from __future__ import annotations

from pathlib import Path

from tiff.trace_net_category_aware_graph_ui_overlay_v1 import build_category_aware_graph_ui_overlay, read_json


def write_json(path: Path, payload: dict) -> None:
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def synthetic_inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    graph = {
        "quality_status": "PASS",
        "summary": {"overlay_node_count": 3, "overlay_edge_count": 1, "community_count": 1},
        "node_plans": [
            {"node_id": "page::p1", "node_type": "Page", "label": "Page p1", "page_id": "p1", "properties": {"can_answer_directly": False}},
            {"node_id": "page::p2", "node_type": "Page", "label": "Page p2", "page_id": "p2", "properties": {"can_answer_directly": False}},
            {"node_id": "leiden_community::c1", "node_type": "LeidenCommunity", "label": "Community c1", "properties": {"can_answer_directly": False}},
        ],
        "edge_plans": [
            {"edge_id": "e1", "edge_type": "HAS_COMMUNITY_MEMBER", "source_node_id": "leiden_community::c1", "target_node_id": "page::p1", "page_id": "p1", "properties": {}},
        ],
    }
    cat = {
        "quality_status": "PASS",
        "summary": {"page_count": 2, "community_count": 1, "category_overlay_node_count": 2, "category_overlay_edge_count": 2, "giant_global_category_hub_count": 0},
        "community_category_profiles": [
            {"community_id": "c1", "category_aware_label": "Text / source evidence community", "page_count": 2, "page_ids": ["p1", "p2"], "review_page_count": 0, "dominant_page_category_labels": ["text_source_page"], "dominant_leiden_hint_families": ["source", "text"], "part_numbers": []}
        ],
        "page_category_membership": [
            {"community_id": "c1", "page_id": "p1", "page_category_label": "text_source_page", "dc_type": ["technical_manual_page", "text_page"], "leiden_hint_element_families": ["source", "text"], "suppressed_leiden_hint_families": ["table"]},
            {"community_id": "c1", "page_id": "p2", "page_category_label": "text_source_page", "dc_type": ["technical_manual_page", "text_page"], "leiden_hint_element_families": ["source", "text"], "suppressed_leiden_hint_families": []},
        ],
        "category_overlay_nodes": [
            {"node_id": "page_category::p1::source", "node_type": "PageLocalCategoryHint", "label": "p1 source", "page_id": "p1", "properties": {}},
            {"node_id": "community_category_summary::c1", "node_type": "CommunityCategorySummary", "label": "c1 summary", "properties": {}},
        ],
        "category_overlay_edges": [
            {"edge_id": "ce1", "edge_type": "PAGE_HAS_CATEGORY_HINT", "source_node_id": "page::p1", "target_node_id": "page_category::p1::source", "page_id": "p1", "properties": {}},
            {"edge_id": "ce2", "edge_type": "COMMUNITY_HAS_CATEGORY_SUMMARY", "source_node_id": "leiden_community::c1", "target_node_id": "community_category_summary::c1", "properties": {}},
        ],
    }
    tax = {"quality_status": "PASS", "summary": {"page_count": 2}}
    dc = {"quality_status": "PASS", "summary": {"page_record_count": 2}}
    graph_path = tmp_path / "graph.json"
    cat_path = tmp_path / "cat.json"
    tax_path = tmp_path / "tax.json"
    dc_path = tmp_path / "dc.json"
    write_json(graph_path, graph)
    write_json(cat_path, cat)
    write_json(tax_path, tax)
    write_json(dc_path, dc)
    return graph_path, cat_path, tax_path, dc_path


def test_build_category_aware_graph_ui_overlay(tmp_path: Path) -> None:
    graph_path, cat_path, tax_path, dc_path = synthetic_inputs(tmp_path)
    report = build_category_aware_graph_ui_overlay(
        graph_ui_community_overlay_path=graph_path,
        category_aware_leiden_overlay_path=cat_path,
        element_category_taxonomy_path=tax_path,
        dublin_core_refined_path=dc_path,
        output_dir=tmp_path / "out",
        require_page_count=2,
        require_source_graph_ui_quality_pass=True,
        require_source_category_overlay_quality_pass=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["category_aware_community_card_count"] == 1
    assert report["summary"]["page_category_profile_card_count"] == 2
    assert report["summary"]["orphan_edge_count"] == 0
    assert report["summary"]["giant_global_category_hub_count"] == 0
    assert report["summary"]["category_as_proof_count"] == 0
    assert (tmp_path / "out" / "trace_net_category_aware_graph_ui_overlay_v1.json").exists()


def test_report_contains_page_profile_cards(tmp_path: Path) -> None:
    graph_path, cat_path, tax_path, dc_path = synthetic_inputs(tmp_path)
    report = build_category_aware_graph_ui_overlay(
        graph_ui_community_overlay_path=graph_path,
        category_aware_leiden_overlay_path=cat_path,
        element_category_taxonomy_path=tax_path,
        dublin_core_refined_path=dc_path,
        output_dir=tmp_path / "out",
    )
    cards = report["page_category_profile_cards"]
    assert {c["page_id"] for c in cards} == {"p1", "p2"}
    assert all(c["properties"]["can_answer_directly"] is False for c in cards)
    assert all(c["properties"]["can_prove_claims"] is False for c in cards)


def test_external_reference_nodes_are_added_for_missing_source_nodes(tmp_path: Path) -> None:
    graph_path, cat_path, tax_path, dc_path = synthetic_inputs(tmp_path)
    graph = read_json(graph_path)
    graph["node_plans"] = [n for n in graph["node_plans"] if n["node_id"] != "page::p2"]
    write_json(graph_path, graph)
    report = build_category_aware_graph_ui_overlay(
        graph_ui_community_overlay_path=graph_path,
        category_aware_leiden_overlay_path=cat_path,
        element_category_taxonomy_path=tax_path,
        dublin_core_refined_path=dc_path,
        output_dir=tmp_path / "out",
    )
    assert report["summary"]["external_reference_node_count"] >= 1
    assert report["summary"]["orphan_edge_count"] == 0
