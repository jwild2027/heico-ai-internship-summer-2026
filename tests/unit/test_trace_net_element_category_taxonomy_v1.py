from pathlib import Path
import json

from tiff.trace_net_element_category_taxonomy_v1 import (
    build_element_category_taxonomy,
    categorize_element,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def refined_payload() -> dict:
    return {
        "schema_version": "trace_net_dublin_core_crosswalk_refinement_v1",
        "status": "DUBLIN_CORE_CROSSWALK_REFINEMENT_BUILT",
        "quality_status": "PASS",
        "page_records": [
            {
                "page_id": "p1",
                "dc": {"dc:identifier": "p1", "dc:type": ["technical_manual_page", "text_page"], "dcterms:isPartOf": "doc1"},
                "trace_net": {
                    "trace_net:physical_element_type_counts": {"source_text": 1, "table_cell": 3, "callout_candidate": 2},
                    "trace_net:operational_element_type_counts": {"fishnet_action": 2, "review_task": 1, "community": 1},
                    "trace_net:secondary_type_signals": ["diagram_signal", "review_required"],
                    "trace_net:review_required": True,
                    "trace_net:complexity_class_refined": "high_review",
                    "trace_net:community_ids": ["c1"],
                    "trace_net:part_numbers": ["120-1"],
                },
            },
            {
                "page_id": "p2",
                "dc": {"dc:identifier": "p2", "dc:type": ["technical_manual_page", "blank_page"], "dcterms:isPartOf": "doc1"},
                "trace_net": {
                    "trace_net:physical_element_type_counts": {},
                    "trace_net:operational_element_type_counts": {"blank_source_trace_preservation": 1, "fishnet_plan": 1},
                    "trace_net:review_required": False,
                    "trace_net:complexity_class_refined": "blank",
                },
            },
        ],
    }


def test_categorize_core_element_types() -> None:
    assert categorize_element("TableCell")["element_family"] == "table"
    assert categorize_element("CalloutCandidate")["element_family"] == "diagram"
    assert categorize_element("visual_type:chart_or_plot_candidate")["element_family"] == "chart"
    assert categorize_element("review:page_visual_review_card")["element_family"] == "review"


def test_build_taxonomy_creates_page_profiles(tmp_path: Path) -> None:
    refined_path = tmp_path / "refined.json"
    write_json(refined_path, refined_payload())

    report = build_element_category_taxonomy(
        dublin_core_refined_path=refined_path,
        output_dir=tmp_path / "out",
        require_page_count=2,
        min_page_profiles=2,
        min_categorized_elements=1,
        min_diagram_categories=1,
        min_table_categories=1,
        min_review_categories=1,
        write_quality=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["page_count"] == 2
    assert report["summary"]["page_category_profile_count"] == 2
    assert report["summary"]["diagram_category_count"] >= 1
    assert report["summary"]["table_category_count"] >= 1
    assert report["summary"]["review_category_count"] >= 1
    assert report["summary"]["can_answer_directly_count"] == 0
    assert (tmp_path / "out" / "trace_net_element_category_taxonomy_v1.json").exists()
    assert (tmp_path / "out" / "trace_net_page_category_profiles_v1.jsonl").exists()

    profile = next(p for p in report["page_category_profiles"] if p["page_id"] == "p1")
    assert "table" in profile["element_family_counts"]
    assert "diagram" in profile["element_family_counts"]
    assert profile["page_category_label"] == "text_source_page_review"
    assert "operation" not in profile["semantic_dominant_element_families"]
    assert profile["leiden_grouping_hints"]["avoid_global_category_hub_edges"] is True
    assert profile["can_answer_directly"] is False


def test_optional_sources_add_categories(tmp_path: Path) -> None:
    refined_path = tmp_path / "refined.json"
    graph_path = tmp_path / "graph.json"
    opensearch_path = tmp_path / "os.json"
    write_json(refined_path, refined_payload())
    write_json(graph_path, {"node_plans": [{"node_id": "n1", "node_type": "PartCandidate", "page_id": "p1"}]})
    write_json(opensearch_path, {"documents": [{"opensearch_document_id": "d1", "document_type": "community_summary", "rag_bucket": "community_retrieval_helper", "source_page_ids": ["p1"]}]})

    report = build_element_category_taxonomy(
        dublin_core_refined_path=refined_path,
        element_graph_attachment_path=graph_path,
        opensearch_adapter_path=opensearch_path,
        output_dir=tmp_path / "out",
        require_page_count=2,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["part_category_count"] >= 1
    assert report["summary"]["community_category_count"] >= 1



def test_leiden_hints_do_not_promote_weak_table_visual_signals_for_text_page(tmp_path: Path) -> None:
    refined_path = tmp_path / "refined.json"
    write_json(refined_path, refined_payload())

    report = build_element_category_taxonomy(
        dublin_core_refined_path=refined_path,
        output_dir=tmp_path / "out",
        require_page_count=2,
        min_page_profiles=2,
        min_categorized_elements=1,
        min_diagram_categories=1,
        min_table_categories=1,
        min_review_categories=1,
    )

    profile = next(p for p in report["page_category_profiles"] if p["page_id"] == "p1")
    hint_families = [h["element_family"] for h in profile["leiden_grouping_hints"]["suggested_page_category_nodes"]]

    assert profile["page_category_label"] == "text_source_page_review"
    assert "table" not in hint_families
    assert "diagram" not in hint_families
    assert "table" in profile["suppressed_leiden_hint_families"]
    assert "diagram" in profile["suppressed_leiden_hint_families"]
    assert report["summary"]["table_hint_without_table_type_count"] == 0
    assert report["summary"]["visual_hint_without_visual_type_count"] == 0


def test_leiden_hints_keep_strong_table_visual_part_page(tmp_path: Path) -> None:
    payload = refined_payload()
    payload["page_records"].append({
        "page_id": "p3",
        "dc": {"dc:identifier": "p3", "dc:type": ["technical_manual_page", "text_page", "table_page", "visual_page", "parts_page"], "dcterms:isPartOf": "doc1"},
        "trace_net": {
            "trace_net:physical_element_type_counts": {"source_text": 1, "table_row": 10, "table_cell": 30, "callout_candidate": 7, "linked_part_candidate": 4},
            "trace_net:operational_element_type_counts": {"review_task": 2, "fishnet_action": 3},
            "trace_net:review_required": True,
            "trace_net:complexity_class_refined": "high_review",
        },
    })
    refined_path = tmp_path / "refined.json"
    write_json(refined_path, payload)

    report = build_element_category_taxonomy(
        dublin_core_refined_path=refined_path,
        output_dir=tmp_path / "out",
        require_page_count=3,
        min_page_profiles=3,
        min_categorized_elements=1,
        min_diagram_categories=1,
        min_table_categories=1,
        min_part_categories=1,
        min_review_categories=1,
    )

    profile = next(p for p in report["page_category_profiles"] if p["page_id"] == "p3")
    hint_families = [h["element_family"] for h in profile["leiden_grouping_hints"]["suggested_page_category_nodes"]]

    assert profile["page_category_label"] == "table_parts_diagram_page_review"
    assert "table" in hint_families
    assert "diagram" in hint_families
    assert "part" in hint_families
    assert profile["leiden_hint_policy"]["dc_type_first"] is True
