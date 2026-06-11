import json
from pathlib import Path

from tiff.trace_net_callout_visual_part_verifier_v1 import (
    build_callout_visual_part_verifier_report,
    is_probable_random_number,
    norm_label,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def sample_visual_payload() -> dict:
    return {
        "schema_version": "trace_net_figure_chart_understanding_v1",
        "quality_status": "PASS",
        "records": [
            {
                "visual_record_id": "vis_p3",
                "page_id": "t_p_120_1176_p000003",
                "page_number": 3,
                "visual_type": "parts_diagram_or_illustrated_parts_list",
                "callout_labels": ["1", "2", "1998", "003"],
                "item_refs": ["item 1"],
                "linked_part_candidates": ["120-46137-001"],
                "requires_catalog_compare": True,
                "needs_human_review": True,
                "visual_regions": [
                    {
                        "region_id": "r1",
                        "detected_callout_labels": ["1", "2"],
                        "linked_part_candidates": ["120-46137-001"],
                    }
                ],
                "can_answer_directly": False,
                "can_prove_claims": False,
            }
        ],
        "summary": {"visual_understanding_record_count": 1},
    }


def sample_table_payload() -> dict:
    return {
        "schema_version": "trace_net_table_cell_normalizer_v1",
        "quality_status": "PASS",
        "records": [
            {
                "normalized_table_id": "normtable1",
                "page_id": "t_p_120_1176_p000003",
                "rows": [
                    {
                        "normalized_row_id": "row1",
                        "source_row_id": "srcrow1",
                        "row_index": 1,
                        "row_type": "part_number_row",
                        "row_text": "1 120-46137-001 bracket",
                        "answer_support_candidate": True,
                        "citation_ids": ["cite:table:p3:1"],
                    }
                ],
                "cells": [
                    {"row_id": "srcrow1", "col_index": 0, "normalized_text": "1"},
                    {"row_id": "srcrow1", "col_index": 1, "normalized_text": "120-46137-001"},
                ],
            }
        ],
    }


def sample_part_payload() -> dict:
    return {
        "schema_version": "trace_net_graph_overlay_part_property_normalizer_v1",
        "quality_status": "PASS",
        "part_candidate_nodes": [
            {
                "node_id": "part_candidate::120-46137-001",
                "label": "120-46137-001",
                "part_number": "120-46137-001",
                "properties": {"part_number": "120-46137-001"},
                "source_page_ids": ["t_p_120_1176_p000003"],
            }
        ],
    }


def test_norm_label_strips_item_prefix() -> None:
    assert norm_label("Item 12") == "12"
    assert norm_label("callout #7A") == "7A"


def test_random_number_rules_keep_supported_items() -> None:
    is_random, reason = is_probable_random_number("1", page_number=3, table_item_tokens={"1"}, visual_type="parts_diagram_or_illustrated_parts_list")
    assert not is_random
    assert reason == "supported_by_table_item"


def test_random_number_rules_suppress_year_and_page_number() -> None:
    assert is_probable_random_number("1998", page_number=3, table_item_tokens=set(), visual_type="parts_diagram_or_illustrated_parts_list")[0]
    assert is_probable_random_number("3", page_number=3, table_item_tokens=set(), visual_type="parts_diagram_or_illustrated_parts_list")[0]


def test_build_report_links_callouts_to_table_and_catalog(tmp_path: Path) -> None:
    visual = tmp_path / "visual.json"
    table = tmp_path / "table.json"
    parts = tmp_path / "parts.json"
    out = tmp_path / "out"
    write_json(visual, sample_visual_payload())
    write_json(table, sample_table_payload())
    write_json(parts, sample_part_payload())

    report = build_callout_visual_part_verifier_report(
        figure_chart_understanding_path=visual,
        table_cell_normalizer_path=table,
        graph_overlay_part_normalizer_path=parts,
        output_dir=out,
        quality_config={"min_verifier_records": 1, "min_clean_callouts": 1, "min_callout_to_table_row_links": 1, "min_catalog_verified_visual_parts": 1},
        write_quality=True,
    )

    assert report["quality_status"] == "PASS"
    summary = report["summary"]
    assert summary["callout_verifier_record_count"] == 1
    assert summary["clean_callout_count"] >= 1
    assert summary["random_number_suppressed_count"] >= 1
    assert summary["callout_to_table_row_link_count"] == 1
    assert summary["catalog_verified_visual_part_count"] == 1
    assert summary["visual_answer_allowed_count"] == 0
    assert summary["source_truth_mutation_allowed_count"] == 0
    assert (out / "trace_net_callout_visual_part_verifier_v1.json").exists()
    assert (out / "trace_net_callout_visual_part_verifier_v1_quality.json").exists()
