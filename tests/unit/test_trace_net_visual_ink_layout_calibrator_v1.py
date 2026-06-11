from pathlib import Path
import json

import pytest

from tiff import trace_net_visual_ink_layout_calibrator_v1 as mod


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def sample_page_registry():
    return {
        "records": [
            {
                "page_id": "t_p_120_1176_p000001",
                "page_traits": ["source_trace_present", "ocr_text_present", "revision_block_candidate"],
                "detected_elements": [{"element_type": "source_text"}],
                "candidate_bucket_counts": {"source_text_evidence": 1},
            },
            {
                "page_id": "t_p_120_1176_p000002",
                "page_traits": ["blank_page"],
                "detected_elements": [{"element_type": "blank"}],
                "candidate_bucket_counts": {},
            },
            {
                "page_id": "t_p_120_1176_p000003",
                "page_traits": ["parts_list", "table_candidate"],
                "detected_elements": [{"element_type": "table"}, {"element_type": "parts_list"}],
                "candidate_bucket_counts": {"verified_part_evidence": 2, "source_text_evidence": 1},
            },
        ]
    }


def sample_audit():
    return {
        "summary": {"status": "OK", "pages_checked": 3, "blank_pages": 1},
        "records": [
            {
                "page_id": "t_p_120_1176_p000001",
                "role": "front_matter",
                "classification": "likely_figure_or_diagram",
                "context_summary": "revision notice and title block",
                "ink_ratio": 0.043,
                "dark_pixel_count": 19623,
                "horizontal_line_rows": 2,
                "vertical_line_cols": 0,
                "large_component_count": 72,
                "largest_component_pixels": 358,
                "table_grid_score": 1.4,
                "visual_score": 9.4,
                "likely_blank": False,
                "likely_text_heavy": True,
            },
            {
                "page_id": "t_p_120_1176_p000002",
                "role": "blank",
                "classification": "likely_blank",
                "context_summary": "empty OCR text",
                "ink_ratio": 0.0,
                "dark_pixel_count": 0,
                "horizontal_line_rows": 0,
                "vertical_line_cols": 0,
                "large_component_count": 0,
                "largest_component_pixels": 0,
                "table_grid_score": 0.0,
                "visual_score": 0.0,
                "likely_blank": True,
            },
            {
                "page_id": "t_p_120_1176_p000003",
                "role": "parts_list",
                "classification": "likely_table_or_grid",
                "context_summary": "parts list figure and table",
                "ink_ratio": 0.114,
                "dark_pixel_count": 52240,
                "horizontal_line_rows": 0,
                "vertical_line_cols": 63,
                "large_component_count": 51,
                "largest_component_pixels": 566,
                "table_grid_score": 56.7,
                "visual_score": 14.2,
                "likely_blank": False,
                "likely_table_grid": True,
            },
        ],
    }


def sample_figure():
    return {
        "summary": {"quality_status": "PASS"},
        "records": [
            {"page_id": "t_p_120_1176_p000001", "visual_type": "chart_or_plot_candidate"},
            {"page_id": "t_p_120_1176_p000003", "visual_type": "parts_diagram_or_illustrated_parts_list"},
        ],
    }


def sample_table_normalizer():
    return {
        "records": [
            {
                "page_id": "t_p_120_1176_p000003",
                "table_type": "parts_list_table",
                "normalized_row_count": 75,
                "normalized_cell_count": 140,
                "answer_support_row_count": 12,
                "repair_count": 2,
            }
        ]
    }


def test_scores_are_math_based_and_front_matter_chart_is_demoted():
    page = sample_page_registry()["records"][0]
    audit = sample_audit()["records"][0]
    figure = sample_figure()["records"][0]
    record = mod.build_calibrated_record(page, audit, figure, [])

    assert record["previous_visual_type"] == "chart_or_plot_candidate"
    assert record["calibrated_layout_class"] in {"text_heavy", "figure_or_diagram"}
    assert record["calibrated_layout_class"] != "chart_or_plot"
    assert record["reclassified"] is True
    assert record["can_answer_directly"] is False
    assert record["can_prove_claims"] is False
    assert "ink_score" in record["calibrated_scores"]


def test_blank_and_parts_table_are_classified():
    registry = sample_page_registry()["records"]
    audits = {r["page_id"]: r for r in sample_audit()["records"]}
    tables = {"t_p_120_1176_p000003": sample_table_normalizer()["records"]}

    blank = mod.build_calibrated_record(registry[1], audits[registry[1]["page_id"]], {}, [])
    assert blank["calibrated_layout_class"] == "blank"
    assert "blank_page_review_route" in blank["recommended_extraction_routes"]

    table = mod.build_calibrated_record(registry[2], audits[registry[2]["page_id"]], {}, tables[registry[2]["page_id"]])
    assert table["calibrated_layout_class"] in {"parts_list_table", "table_or_grid", "mixed_table_and_diagram"}
    assert "table_cell_normalizer_route" in table["recommended_extraction_routes"]
    assert table["table_context"]["normalized_row_count"] == 75


def test_build_and_quality_pass(tmp_path: Path):
    reg = tmp_path / "registry.json"
    audit = tmp_path / "audit.json"
    fig = tmp_path / "figure.json"
    table = tmp_path / "table.json"
    out = tmp_path / "out"
    write_json(reg, sample_page_registry())
    write_json(audit, sample_audit())
    write_json(fig, sample_figure())
    write_json(table, sample_table_normalizer())

    payload = mod.build_visual_ink_layout_calibrator(
        page_registry_path=reg,
        image_recognition_audit_path=audit,
        figure_chart_understanding_path=fig,
        table_cell_normalizer_path=table,
        output_dir=out,
        require_page_count=3,
        min_calibrated_pages=3,
        min_ink_metric_pages=3,
        min_blank_pages=1,
        min_reclassified_pages=1,
        max_chart_pages=0,
        write_quality=True,
    )

    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["calibrated_page_count"] == 3
    assert payload["summary"]["blank_page_count"] == 1
    assert payload["summary"]["chart_candidate_demoted_count"] >= 1
    assert (out / "trace_net_visual_ink_layout_calibrator_v1.json").exists()
    assert (out / "trace_net_visual_ink_layout_calibrator_v1_quality.json").exists()


def test_quality_fails_when_visual_answer_allowed(tmp_path: Path):
    payload = {
        "summary": {
            "calibrated_page_count": 1,
            "ink_metric_page_count": 1,
            "blank_page_count": 0,
            "reclassified_page_count": 0,
            "visual_answer_allowed_count": 1,
            "unverified_visual_claim_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "unsafe_visual_layout_record_count": 0,
            "pages_with_recommended_routes_count": 1,
            "pages_with_fishnet_plan_count": 1,
        }
    }
    q = mod.build_quality(payload, min_calibrated_pages=1, min_ink_metric_pages=1)
    assert q["quality_status"] == "FAIL"
    assert any(c["name"] == "visual_answer_allowed_zero" and not c["passed"] for c in q["checks"])


def test_low_ink_with_source_text_is_not_confirmed_blank():
    page = {
        "page_id": "t_p_120_1176_p000099",
        "page_traits": ["source_trace_present", "ocr_text_present", "revision_block_candidate"],
        "detected_elements": [{"element_type": "source_text"}],
        "candidate_bucket_counts": {"source_text_evidence": 1},
    }
    audit = {
        "page_id": "t_p_120_1176_p000099",
        "role": "front_matter",
        "classification": "likely_blank",
        "context_summary": "small revision note in title block",
        "ink_ratio": 0.001,
        "dark_pixel_count": 50,
        "horizontal_line_rows": 0,
        "vertical_line_cols": 0,
        "large_component_count": 1,
        "largest_component_pixels": 20,
        "table_grid_score": 0,
        "visual_score": 0,
        "likely_blank": True,
        "likely_text_heavy": False,
    }
    record = mod.build_calibrated_record(page, audit, {}, [])

    assert record["ink_blank_candidate"] is True
    assert record["source_confirmed_blank"] is False
    assert record["calibrated_layout_class"] == "sparse_ink_text_or_source_trace"
    assert "sparse_ink_source_validation_route" in record["recommended_extraction_routes"]
    assert record["can_answer_directly"] is False
    assert record["can_prove_claims"] is False
