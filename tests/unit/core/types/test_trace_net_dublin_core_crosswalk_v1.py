import json
from pathlib import Path

from tiff.trace_net_dublin_core_crosswalk_v1 import build_crosswalk_report, quality_report


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def registry_payload() -> dict:
    return {
        "schema_version": "trace_net_page_element_registry_v1",
        "status": "PAGE_ELEMENT_REGISTRY_BUILT",
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "t_p_120_1176_p000001",
                "document_id": "t_p_120_1176",
                "page_number": 1,
                "page_traits": ["source_trace_present", "ocr_text_present", "front_matter_or_title_signal"],
                "detected_elements": [
                    {"element_type": "source_trace"},
                    {"element_type": "source_text"},
                ],
                "recommended_extraction_routes": ["source_trace_route", "ocr_text_route"],
                "candidate_bucket_counts": {"source_text_evidence": 1, "source_evidence": 1},
                "citation_ids": ["cite:source_text:t_p_120_1176_p000001:aaa"],
                "citation_count": 1,
                "source_candidate_count": 2,
                "context_v2_present": True,
                "needs_human_review": False,
                "trust_assignment_policy": "evidence_consensus_then_trust_authority_gate",
            },
            {
                "page_id": "t_p_120_1176_p000003",
                "document_id": "t_p_120_1176",
                "page_number": 3,
                "page_traits": ["source_trace_present", "ocr_text_present", "table_or_list_signal"],
                "detected_elements": [
                    {"element_type": "source_trace"},
                    {"element_type": "source_text"},
                    {"element_type": "table_or_list"},
                ],
                "recommended_extraction_routes": ["table_cell_normalizer_route", "part_catalog_compare_route"],
                "candidate_bucket_counts": {"verified_part_evidence": 1},
                "citation_ids": ["cite:table_structured:t_p_120_1176_p000003:bbb"],
                "citation_count": 1,
                "source_candidate_count": 1,
                "context_v2_present": False,
                "needs_human_review": True,
                "trust_assignment_policy": "evidence_consensus_then_trust_authority_gate",
            },
        ],
    }


def table_payload() -> dict:
    return {
        "schema_version": "trace_net_table_cell_normalizer_v1",
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "t_p_120_1176_p000003",
                "table_type": "parts_list_table",
                "normalized_row_count": 2,
                "normalized_cell_count": 5,
                "repair_count": 1,
                "answer_support_row_count": 1,
                "repairs": [{"merged_part_number": "120-46137-001"}],
                "rows": [{"citation_ids": ["cite:table_structured:t_p_120_1176_p000003:bbb"]}],
            }
        ],
    }


def figure_payload() -> dict:
    return {
        "schema_version": "trace_net_figure_chart_understanding_v1",
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "t_p_120_1176_p000003",
                "visual_type": "parts_diagram_or_illustrated_parts_list",
                "visual_region_count": 1,
                "callout_labels": ["1", "2", "1998"],
                "linked_part_candidates": ["120-46137-001"],
                "needs_human_review": True,
                "requires_catalog_compare": True,
            }
        ],
    }


def graph_payload() -> dict:
    return {
        "schema_version": "trace_net_element_graph_attachment_plan_v1",
        "quality_status": "PASS",
        "node_plans": [
            {"node_id": "page::t_p_120_1176_p000003", "node_type": "Page", "page_id": "t_p_120_1176_p000003", "label": "Page 3"},
            {"node_id": "table_cell::1", "node_type": "TableCell", "page_id": "t_p_120_1176_p000003", "label": "Cell"},
            {"node_id": "part_candidate::120-46137-001", "node_type": "PartCandidate", "source_page_ids": ["t_p_120_1176_p000003"], "label": "120-46137-001", "properties": {"part_number": "120-46137-001"}},
            {"node_id": "citation::c1", "node_type": "Citation", "page_id": "t_p_120_1176_p000003", "label": "Citation"},
        ],
        "edge_plans": [
            {"edge_type": "HAS_TABLE_CELL", "page_id": "t_p_120_1176_p000003", "source_node_id": "row", "target_node_id": "table_cell::1"}
        ],
    }


def leiden_payload() -> dict:
    return {
        "schema_version": "trace_net_leiden_graph_communities_v1",
        "quality_status": "PASS",
        "communities": [
            {"community_id": "tracenet_community_00001", "page_ids": ["t_p_120_1176_p000003"], "part_families": ["120-46137"]}
        ],
        "node_membership": [
            {"node_id": "page::t_p_120_1176_p000003", "node_type": "Page", "community_id": "tracenet_community_00001"}
        ],
    }


def triage_payload() -> dict:
    return {
        "schema_version": "trace_net_human_review_triage_v1",
        "quality_status": "PASS",
        "triage_cards": [
            {"triage_card_id": "triage_1", "page_ids": ["t_p_120_1176_p000003"], "task_count": 3, "community_ids": ["tracenet_community_00001"], "part_numbers": ["120-46137-001"]}
        ],
    }


def test_build_crosswalk_creates_dc_and_trace_net_fields(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    table = tmp_path / "table.json"
    figure = tmp_path / "figure.json"
    graph = tmp_path / "graph.json"
    leiden = tmp_path / "leiden.json"
    triage = tmp_path / "triage.json"
    write_json(registry, registry_payload())
    write_json(table, table_payload())
    write_json(figure, figure_payload())
    write_json(graph, graph_payload())
    write_json(leiden, leiden_payload())
    write_json(triage, triage_payload())

    report = build_crosswalk_report(
        page_registry_path=registry,
        table_cell_normalizer_path=table,
        figure_chart_understanding_path=figure,
        element_graph_attachment_path=graph,
        leiden_communities_path=leiden,
        human_review_triage_path=triage,
        output_dir=tmp_path / "out",
        quality_config={"require_page_count": 2, "min_pages_with_element_counts": 2},
        write_quality=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["page_dc_record_count"] == 2
    page3 = next(r for r in report["page_records"] if r["page_id"] == "t_p_120_1176_p000003")
    assert page3["dc"]["dc:identifier"] == "t_p_120_1176_p000003"
    assert "table_page" in page3["dc"]["dc:type"]
    assert "visual_page" in page3["dc"]["dc:type"]
    assert page3["trace_net"]["trace_net:element_count"] > 0
    assert page3["trace_net"]["trace_net:element_type_count"] > 0
    assert page3["trace_net"]["trace_net:element_type_counts"]["table_cell"] >= 5
    assert page3["trace_net"]["trace_net:review_required"] is True
    assert page3["can_answer_directly"] is False
    assert page3["source_truth_mutation_allowed"] is False
    assert (tmp_path / "out" / "trace_net_dublin_core_pages_v1.jsonl").exists()


def test_quality_report_fails_missing_element_count(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    write_json(
        report_path,
        {
            "summary": {
                "page_dc_record_count": 1,
                "document_dc_record_count": 1,
                "page_records_with_element_counts": 0,
                "missing_dc_identifier_count": 0,
                "missing_dc_source_count": 0,
                "missing_dc_format_count": 0,
                "missing_trace_net_element_count": 1,
                "missing_trace_net_element_type_count": 1,
                "direct_answer_allowed_count": 0,
                "claim_proof_allowed_count": 0,
                "source_truth_mutation_allowed_count": 0,
            }
        },
    )
    quality = quality_report(report_path=report_path, quality_config={"require_page_count": 1})
    assert quality["status"] == "FAIL"


def test_document_record_summarizes_pages(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    write_json(registry, registry_payload())
    report = build_crosswalk_report(page_registry_path=registry, output_dir=tmp_path / "out")
    assert report["document_records"]
    doc = report["document_records"][0]
    assert doc["dc"]["dc:identifier"] == "t_p_120_1176"
    assert doc["trace_net"]["trace_net:page_count"] == 2
    assert doc["trace_net"]["trace_net:can_answer_directly"] is False
