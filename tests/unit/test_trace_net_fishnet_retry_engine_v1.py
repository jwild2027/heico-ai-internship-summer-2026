from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_fishnet_retry_engine_v1 import (
    build_trace_net_fishnet_retry_engine,
    build_fishnet_record,
    quality_checks,
)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def sample_page_registry() -> dict:
    return {
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "t_p_120_1176_p000001",
                "page_number": 1,
                "page_traits": ["source_trace_present", "ocr_text_present", "front_matter"],
                "detected_elements": ["source_text", "revision_block"],
                "recommended_extraction_routes": ["source_trace_route", "ocr_text_route"],
                "fishnet_retry_plan": [{"layer": 1}],
                "comparison_targets": ["ocr", "source_trace"],
                "candidate_bucket_counts": {"source_text_evidence": 1},
                "context_v2_present": True,
            },
            {
                "page_id": "t_p_120_1176_p000003",
                "page_number": 3,
                "page_traits": ["table_candidate", "part_catalog_signal"],
                "detected_elements": ["table", "parts_list"],
                "recommended_extraction_routes": ["table_structure_route", "table_cell_normalizer_route", "part_catalog_compare_route"],
                "comparison_targets": ["catalog", "graph"],
                "candidate_bucket_counts": {"verified_part_evidence": 2},
                "context_v2_present": False,
            },
            {
                "page_id": "t_p_120_1176_p000014",
                "page_number": 14,
                "page_traits": ["blank_candidate"],
                "detected_elements": ["blank_page"],
                "recommended_extraction_routes": ["blank_page_review_route"],
                "comparison_targets": ["source_trace"],
                "candidate_bucket_counts": {},
                "context_v2_present": False,
            },
        ],
    }


def sample_table() -> dict:
    return {
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "t_p_120_1176_p000003",
                "table_type": "parts_list_table",
                "normalized_row_count": 75,
                "normalized_cell_count": 140,
                "normalized_repair_count": 2,
                "answer_support_row_count": 10,
            }
        ],
    }


def sample_figure() -> dict:
    return {
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "t_p_120_1176_p000003",
                "visual_type": "parts_diagram_or_illustrated_parts_list",
                "needs_human_review": True,
                "requires_catalog_compare": True,
                "linked_part_candidates": ["120-46137-001"],
                "callout_labels": ["1", "2"],
            }
        ],
    }


def sample_ink() -> dict:
    return {
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "t_p_120_1176_p000001",
                "calibrated_layout_class": "text_heavy",
                "calibrated_visual_type": "text_layout",
                "needs_vision_model": False,
            },
            {
                "page_id": "t_p_120_1176_p000003",
                "calibrated_layout_class": "parts_list_table",
                "calibrated_visual_type": "parts_list_layout",
                "needs_vision_model": True,
            },
            {
                "page_id": "t_p_120_1176_p000014",
                "calibrated_layout_class": "blank",
                "source_confirmed_blank": True,
                "ink_blank_candidate": True,
                "needs_vision_model": False,
            },
        ],
    }


def test_build_record_keeps_fishnet_route_only() -> None:
    record = build_fishnet_record(
        sample_page_registry()["records"][1],
        sample_table()["records"][0],
        sample_figure()["records"][0],
        sample_ink()["records"][1],
    )
    assert record["page_id"] == "t_p_120_1176_p000003"
    assert record["can_answer_directly"] is False
    assert record["can_prove_claims"] is False
    assert record["can_mutate_source_truth"] is False
    assert record["final_answer_allowed"] is False
    assert record["safe_for_fishnet_planning"] is True
    assert "table_cell_normalizer_route" in record["retry_routes"]
    assert "catalog_graph_visual_compare" in record["retry_routes"]
    assert record["needs_human_review"] is True


def test_build_full_artifact(tmp_path: Path) -> None:
    page_registry = tmp_path / "page_registry.json"
    table = tmp_path / "table.json"
    figure = tmp_path / "figure.json"
    ink = tmp_path / "ink.json"
    evidence = tmp_path / "evidence.json"
    write_json(page_registry, sample_page_registry())
    write_json(table, sample_table())
    write_json(figure, sample_figure())
    write_json(ink, sample_ink())
    write_json(evidence, {"status": "PASS"})

    payload = build_trace_net_fishnet_retry_engine(
        page_registry_path=page_registry,
        table_cell_normalizer_path=table,
        figure_chart_understanding_path=figure,
        visual_ink_layout_calibrator_path=ink,
        evidence_consensus_summary_path=evidence,
        output_dir=tmp_path / "out",
        require_page_count=3,
        min_fishnet_records=3,
        min_pages_with_retry_plan=3,
        min_pages_with_review_or_retry=1,
        min_extractor_family_count=5,
        min_table_retry_actions=1,
        min_visual_retry_actions=1,
        min_ocr_retry_actions=1,
        write_quality=True,
    )
    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["fishnet_record_count"] == 3
    assert payload["summary"]["source_truth_mutation_allowed_count"] == 0
    assert (tmp_path / "out" / "trace_net_fishnet_retry_engine_v1.json").exists()
    assert (tmp_path / "out" / "trace_net_fishnet_retry_engine_v1_actions.jsonl").exists()
    assert (tmp_path / "out" / "trace_net_fishnet_retry_engine_v1_quality.json").exists()


def test_quality_checks_fail_on_unsafe_summary() -> None:
    quality = quality_checks(
        {
            "fishnet_record_count": 3,
            "pages_with_retry_plan_count": 3,
            "extractor_family_count": 5,
            "unsafe_fishnet_record_count": 1,
            "direct_answer_allowed_count": 0,
            "claim_proof_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "final_answer_allowed_count": 0,
            "missing_page_id_count": 0,
        },
        require_page_count=3,
        min_fishnet_records=3,
        min_pages_with_retry_plan=3,
    )
    assert quality["status"] == "FAIL"
    assert any(c["name"] == "unsafe_fishnet_record_count_zero" and not c["passed"] for c in quality["checks"])


def test_source_confirmed_blank_gets_blank_review_not_answer() -> None:
    record = build_fishnet_record(
        sample_page_registry()["records"][2],
        None,
        None,
        sample_ink()["records"][2],
    )
    assert record["ocr_state"] == "source_confirmed_blank"
    assert "blank_page_review_route" in record["retry_routes"]
    assert record["can_answer_directly"] is False
