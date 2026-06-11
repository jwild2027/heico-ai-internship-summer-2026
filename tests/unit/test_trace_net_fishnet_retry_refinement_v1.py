from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_fishnet_retry_refinement_v1 import (
    build_fishnet_retry_refinement,
    classify_action,
    refine_fishnet_record,
)


def sample_action(action: str, route: str, layer: int = 2) -> dict:
    return {"fishnet_layer": layer, "action": action, "retry_route": route}


def sample_report() -> dict:
    return {
        "schema_version": "trace_net_fishnet_retry_engine_v1",
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "p000001",
                "ocr_state": "ocr_present",
                "layout_class": "text_heavy",
                "visual_type": "chart_or_plot_candidate",
                "table_type": "unknown_table",
                "needs_vision_model": False,
                "retry_actions": [
                    sample_action("inventory_existing_extractor_outputs", "existing_artifact_inventory", 0),
                    sample_action("ocr_cleanup_available_if_needed", "ocr_cleanup_retry", 1),
                    sample_action("validate_table_rows_and_cells", "table_cell_normalizer_route", 2),
                    sample_action("validate_visual_regions_and_callouts", "visual_region_retry_route", 2),
                    sample_action("compare_against_source_graph_and_citations", "graph_source_citation_compare", 4),
                    sample_action("enforce_trust_authority_gate", "trust_authority_gate", 5),
                ],
            },
            {
                "page_id": "p000002",
                "ocr_state": "source_confirmed_blank",
                "layout_class": "blank",
                "visual_type": "chart_or_plot_candidate",
                "table_type": "none",
                "needs_vision_model": False,
                "retry_actions": [
                    sample_action("inventory_existing_extractor_outputs", "existing_artifact_inventory", 0),
                    sample_action("confirm_blank_without_losing_source_trace", "blank_page_review_route", 1),
                    sample_action("validate_visual_regions_and_callouts", "visual_region_retry_route", 2),
                    sample_action("compare_against_source_graph_and_citations", "graph_source_citation_compare", 4),
                    sample_action("enforce_trust_authority_gate", "trust_authority_gate", 5),
                ],
            },
            {
                "page_id": "p000003",
                "ocr_state": "ocr_present",
                "layout_class": "parts_list_table",
                "visual_type": "parts_diagram_or_illustrated_parts_list",
                "table_type": "parts_list_table",
                "needs_vision_model": True,
                "retry_actions": [
                    sample_action("inventory_existing_extractor_outputs", "existing_artifact_inventory", 0),
                    sample_action("review_repaired_table_cells", "table_repair_review_route", 2),
                    sample_action("validate_table_rows_and_cells", "table_cell_normalizer_route", 2),
                    sample_action("send_to_vision_model_pilot", "vision_model_pilot_route", 3),
                    sample_action("compare_visual_parts_against_catalog_graph", "catalog_graph_visual_compare", 4),
                    sample_action("human_review_for_unverified_visual_page", "human_review_visual_route", 5),
                    sample_action("enforce_trust_authority_gate", "trust_authority_gate", 5),
                ],
            },
        ],
    }


def write_report(tmp_path: Path) -> Path:
    path = tmp_path / "fishnet.json"
    path.write_text(json.dumps(sample_report()), encoding="utf-8")
    return path


def test_text_heavy_table_and_visual_actions_are_demoted() -> None:
    record = sample_report()["records"][0]
    refined = refine_fishnet_record(record)
    assert refined["actual_retry_action_count"] == 0
    assert "validate_table_rows_and_cells" in refined["optional_enrichment_actions"]
    assert "validate_visual_regions_and_callouts" in refined["optional_enrichment_actions"]
    assert refined["fishnet_disposition"] == "baseline_validation_plus_optional_enrichment"


def test_blank_page_has_no_actual_visual_retry() -> None:
    record = sample_report()["records"][1]
    refined = refine_fishnet_record(record)
    assert refined["source_confirmed_blank"] is True
    assert refined["actual_retry_action_count"] == 0
    assert "confirm_blank_without_losing_source_trace" in refined["blank_handling_actions"]
    assert refined["can_answer_directly"] is False


def test_visual_table_page_keeps_real_retry_and_review() -> None:
    record = sample_report()["records"][2]
    refined = refine_fishnet_record(record)
    assert refined["actual_retry_action_count"] >= 2
    assert refined["review_action_count"] >= 1
    assert refined["fishnet_disposition"] == "review_required"
    assert "send_to_vision_model_pilot" in refined["actual_retry_actions"]


def test_build_refinement_report_passes_quality(tmp_path: Path) -> None:
    path = write_report(tmp_path)
    out = tmp_path / "out"
    report = build_fishnet_retry_refinement(
        path,
        out,
        require_page_count=3,
        min_refined_records=3,
        min_baseline_validation_pages=3,
        require_actual_retry_less_than_page_count=True,
        write_quality=True,
    )
    summary = report["summary"]
    assert report["quality_status"] == "PASS"
    assert summary["refined_fishnet_record_count"] == 3
    assert summary["actual_retry_page_count"] == 1
    assert summary["confirmed_blank_pages_with_visual_retry_count"] == 0
    assert summary["text_heavy_pages_with_vision_retry_count"] == 0
    assert summary["unknown_table_pages_with_table_answer_retry_count"] == 0
    assert (out / "trace_net_fishnet_retry_refinement_v1.json").exists()
    assert (out / "trace_net_fishnet_retry_refinement_v1_actions.jsonl").exists()


def test_classify_action_keeps_baseline_as_baseline() -> None:
    category, priority, rationale = classify_action(
        {"layout_class": "text_heavy", "table_type": "unknown_table"},
        {"action": "enforce_trust_authority_gate", "retry_route": "trust_authority_gate"},
    )
    assert category == "baseline_validation"
    assert priority == "low"
    assert "safety" in rationale or "validation" in rationale
