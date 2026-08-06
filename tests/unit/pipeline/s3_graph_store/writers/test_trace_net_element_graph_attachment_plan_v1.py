import json
from pathlib import Path

from tiff.trace_net_element_graph_attachment_plan_v1 import build_element_graph_attachment_plan, check_quality_from_report


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def sample_inputs(tmp_path: Path):
    page_registry = {
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "t_p_120_1176_p000001",
                "page_number": 1,
                "page_traits": ["source_trace_present", "ocr_text_present", "text_heavy"],
                "recommended_extraction_routes": ["source_trace_route", "ocr_text_route"],
                "detected_elements": [{"element_type": "source_text"}],
                "context_v2_present": True,
            },
            {
                "page_id": "t_p_120_1176_p000002",
                "page_number": 2,
                "page_traits": ["source_trace_present", "blank"],
                "recommended_extraction_routes": ["blank_page_review_route"],
                "detected_elements": [{"element_type": "blank_page"}],
            },
        ],
    }
    table_normalizer = {
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "t_p_120_1176_p000001",
                "table_id": "tbl_p1",
                "table_type": "parts_list_table",
                "trust_tier": "B",
                "rag_bucket": "table_part_catalog_evidence",
                "citation_ids": ["cite:table:p1"],
                "rows": [
                    {
                        "row_id": "row_p1_1",
                        "row_index": 1,
                        "row_type": "part_number_row",
                        "row_text": "120-46137-001",
                        "answer_support_candidate": True,
                        "citation_ids": ["cite:table:p1"],
                    }
                ],
                "cells": [
                    {"cell_id": "cell_p1_1", "row_id": "row_p1_1", "text": "120-46137-001", "cell_kind": "part_number"}
                ],
                "repairs": [
                    {"source_cell_texts": ["120-46", "137-001"], "merged_part_number": "120-46137-001", "repair_status": "catalog_supported"}
                ],
            }
        ],
    }
    figure_chart = {
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "t_p_120_1176_p000001",
                "visual_type": "parts_diagram_or_illustrated_parts_list",
                "rag_bucket": "figure_part_catalog_retrieval_helper",
                "trust_tier": "C",
                "visual_region_count": 1,
                "callout_labels": ["1", "2"],
                "linked_part_candidates": ["120-46137-001"],
                "requires_catalog_compare": True,
                "needs_human_review": True,
            }
        ],
    }
    fishnet = {
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "t_p_120_1176_p000001",
                "fishnet_disposition": "review_required",
                "priority": "high",
                "layout_class": "parts_list_table",
                "ocr_state": "ocr_present",
                "actual_retry_actions": ["validate_table_rows_and_cells"],
                "review_actions": ["human_review_for_unverified_visual_page"],
                "baseline_validation_actions": ["compare_against_source_graph_and_citations", "enforce_trust_authority_gate"],
            },
            {
                "page_id": "t_p_120_1176_p000002",
                "fishnet_disposition": "source_confirmed_blank_preserve_trace",
                "priority": "low",
                "layout_class": "blank",
                "ocr_state": "source_confirmed_blank",
                "blank_handling_actions": ["confirm_blank_without_losing_source_trace"],
                "baseline_validation_actions": ["enforce_trust_authority_gate"],
            },
        ],
    }
    candidates = {
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "t_p_120_1176_p000001",
                "embedding_candidate_id": "emb1",
                "source_candidate_id": "cand1",
                "rag_bucket": "source_text_evidence",
                "authority": "ocr_text_claim_with_citation",
                "trust_tier": "A",
                "citation_id": "cite:source_text:p1",
                "requires_citation": True,
                "requires_source_resolution": True,
                "requires_authority_gate": True,
            },
            {
                "page_id": "t_p_120_1176_p000002",
                "embedding_candidate_id": "emb2",
                "source_candidate_id": "cand2",
                "rag_bucket": "source_evidence",
                "authority": "source_exists_only",
                "trust_tier": "A",
                "citation_id": "cite:source:p2",
            },
        ],
    }
    paths = {}
    for name, payload in [
        ("page_registry", page_registry),
        ("table_normalizer", table_normalizer),
        ("figure_chart", figure_chart),
        ("fishnet", fishnet),
        ("candidates", candidates),
    ]:
        path = tmp_path / f"{name}.json"
        write_json(path, payload)
        paths[name] = path
    return paths


def test_builds_read_only_graph_attachment_plan(tmp_path: Path):
    paths = sample_inputs(tmp_path)
    report = build_element_graph_attachment_plan(
        page_registry_path=paths["page_registry"],
        table_cell_normalizer_path=paths["table_normalizer"],
        figure_chart_understanding_path=paths["figure_chart"],
        fishnet_retry_refined_path=paths["fishnet"],
        embedding_candidates_path=paths["candidates"],
        output_dir=tmp_path / "out",
        thresholds={
            "require_page_count": 2,
            "min_page_nodes": 2,
            "min_element_node_plans": 10,
            "min_edge_plans": 10,
            "min_table_node_plans": 1,
            "min_table_row_node_plans": 1,
            "min_table_cell_node_plans": 1,
            "min_visual_node_plans": 1,
            "min_fishnet_node_plans": 2,
            "min_citation_edge_plans": 1,
            "min_confirmed_blank_preserve_source_trace": 1,
            "require_page_registry_quality_pass": True,
            "require_fishnet_refinement_quality_pass": True,
        },
        write_quality=True,
    )
    assert report["quality_status"] == "PASS"
    summary = report["summary"]
    assert summary["page_count"] == 2
    assert summary["orphan_edge_count"] == 0
    assert summary["answer_capable_without_citation_count"] == 0
    assert summary["source_truth_mutation_allowed_count"] == 0
    assert summary["confirmed_blank_pages_preserve_source_trace_count"] == 1
    assert Path(report["nodes_path"]).exists()
    assert Path(report["edges_path"]).exists()


def test_quality_fails_when_answer_support_lacks_citation(tmp_path: Path):
    paths = sample_inputs(tmp_path)
    candidates = json.loads(paths["candidates"].read_text())
    candidates["records"][0].pop("citation_id")
    paths["candidates"].write_text(json.dumps(candidates), encoding="utf-8")
    report = build_element_graph_attachment_plan(
        page_registry_path=paths["page_registry"],
        table_cell_normalizer_path=paths["table_normalizer"],
        fishnet_retry_refined_path=paths["fishnet"],
        embedding_candidates_path=paths["candidates"],
        output_dir=tmp_path / "out2",
        thresholds={"require_page_count": 2},
        write_quality=True,
    )
    assert report["quality_status"] == "FAIL"
    assert report["summary"]["answer_capable_without_citation_count"] == 1


def test_quality_check_can_be_rerun_from_report(tmp_path: Path):
    paths = sample_inputs(tmp_path)
    report = build_element_graph_attachment_plan(
        page_registry_path=paths["page_registry"],
        table_cell_normalizer_path=paths["table_normalizer"],
        figure_chart_understanding_path=paths["figure_chart"],
        fishnet_retry_refined_path=paths["fishnet"],
        embedding_candidates_path=paths["candidates"],
        output_dir=tmp_path / "out3",
        thresholds={"require_page_count": 2},
        write_quality=True,
    )
    quality = check_quality_from_report(report["report_path"], {"require_page_count": 2}, write_json_flag=True)
    assert quality["status"] == "PASS"
    assert Path(quality["quality_path"]).exists()


def test_normalized_table_cells_link_when_cells_use_source_row_id(tmp_path: Path):
    """Step 15.1 cells keep source row ids while rows expose normalized ids."""
    page_registry = {
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "t_p_120_1176_p000003",
                "page_number": 3,
                "page_traits": ["source_trace_present", "parts_list_table"],
                "recommended_extraction_routes": ["table_structure_route"],
                "detected_elements": [{"element_type": "table"}],
            }
        ],
    }
    table_normalizer = {
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "t_p_120_1176_p000003",
                "normalized_table_id": "normtable_p3",
                "table_type": "parts_list_table",
                "trust_tier": "B",
                "citation_ids": ["cite:table:p3"],
                "rows": [
                    {
                        "normalized_row_id": "normrow_p3_1",
                        "source_row_id": "source_row_1",
                        "row_index": 1,
                        "row_type": "part_catalog_row",
                        "row_text": "120-46137-001",
                        "answer_support_candidate": True,
                        "citation_ids": ["cite:table:p3"],
                    }
                ],
                "cells": [
                    {
                        "normalized_cell_id": "normcell_p3_1",
                        "row_id": "source_row_1",
                        "col_index": 0,
                        "normalized_text": "120-46137-001",
                        "normalized_kind": "part_number",
                    }
                ],
            }
        ],
    }
    fishnet = {
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "t_p_120_1176_p000003",
                "fishnet_disposition": "review_required",
                "baseline_validation_actions": ["enforce_trust_authority_gate"],
            }
        ],
    }
    paths = {}
    for name, payload in [("registry", page_registry), ("table", table_normalizer), ("fishnet", fishnet)]:
        path = tmp_path / f"{name}.json"
        write_json(path, payload)
        paths[name] = path

    report = build_element_graph_attachment_plan(
        page_registry_path=paths["registry"],
        table_cell_normalizer_path=paths["table"],
        fishnet_retry_refined_path=paths["fishnet"],
        output_dir=tmp_path / "out_normalized_cells",
        thresholds={
            "require_page_count": 1,
            "min_table_cell_node_plans": 1,
            "require_page_registry_quality_pass": True,
            "require_fishnet_refinement_quality_pass": True,
        },
        write_quality=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["table_cell_node_plan_count"] == 1
    assert any(n["node_type"] == "TableCell" for n in report["node_plans"])
    assert any(e["edge_type"] == "HAS_TABLE_CELL" for e in report["edge_plans"])
