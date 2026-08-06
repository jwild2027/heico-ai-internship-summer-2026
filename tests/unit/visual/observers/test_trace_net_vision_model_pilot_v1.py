from pathlib import Path
import json

from tiff.trace_net_vision_model_pilot_v1 import (
    QualityThresholds,
    build_vision_model_pilot,
    classify_visual_task,
    collect_candidate_records,
)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def sample_inputs():
    visual_calibration = {
        "quality_status": "PASS",
        "summary": {"calibrated_page_count": 3},
        "records": [
            {
                "page_id": "t_p_120_1176_p000001",
                "calibrated_layout_class": "text_heavy",
                "calibrated_visual_type": "text_layout",
                "previous_visual_type": "chart_or_plot_candidate",
                "reclassified": True,
                "needs_vision_model": False,
            },
            {
                "page_id": "t_p_120_1176_p000048",
                "calibrated_layout_class": "figure_or_diagram",
                "calibrated_visual_type": "parts_diagram_or_illustrated_parts_list",
                "needs_vision_model": True,
            },
            {
                "page_id": "t_p_120_1176_p000002",
                "calibrated_layout_class": "blank",
                "source_confirmed_blank": True,
            },
        ],
    }
    figure_chart = {
        "quality_status": "PASS",
        "records": [
            {
                "page_id": "t_p_120_1176_p000048",
                "visual_type": "parts_diagram_or_illustrated_parts_list",
                "requires_catalog_compare": True,
                "needs_human_review": True,
                "callout_labels": ["1", "2", "A"],
                "linked_part_candidates": ["120-46137-001"],
            },
            {
                "page_id": "t_p_120_1176_p000010",
                "visual_type": "chart_or_plot_candidate",
                "requires_catalog_compare": False,
                "needs_human_review": False,
            },
        ],
    }
    return visual_calibration, figure_chart


def test_classify_visual_task_includes_catalog_and_callouts():
    calibrated = {
        "calibrated_layout_class": "figure_or_diagram",
        "calibrated_visual_type": "parts_diagram_or_illustrated_parts_list",
    }
    figure = {"visual_type": "parts_diagram_or_illustrated_parts_list", "requires_catalog_compare": True}
    tasks = classify_visual_task(calibrated, figure)
    assert "describe_figure_regions_and_callouts" in tasks
    assert "extract_visual_part_callout_candidates" in tasks


def test_collect_candidate_records_selects_visual_pages():
    visual_calibration, figure_chart = sample_inputs()
    records = collect_candidate_records(
        visual_calibration,
        figure_chart,
        audit_by_page={},
        visual_text_by_page={},
        max_pilot_pages=10,
    )
    pages = {r["page_id"] for r in records}
    assert "t_p_120_1176_p000048" in pages
    assert "t_p_120_1176_p000002" not in pages
    first = [r for r in records if r["page_id"] == "t_p_120_1176_p000048"][0]
    assert first["authority"] == "visual_model_advisory_only"
    assert first["can_answer_directly"] is False
    assert first["can_prove_claims"] is False
    assert first["requires_catalog_compare"] is True
    assert "Do not claim source truth" in first["prompt_text"]


def test_build_report_writes_safe_artifacts(tmp_path: Path):
    visual_calibration, figure_chart = sample_inputs()
    cal = tmp_path / "cal.json"
    fig = tmp_path / "fig.json"
    write_json(cal, visual_calibration)
    write_json(fig, figure_chart)

    report = build_vision_model_pilot(
        visual_ink_layout_calibrator_path=cal,
        figure_chart_understanding_path=fig,
        output_dir=tmp_path / "out",
        max_pilot_pages=5,
        thresholds=QualityThresholds(
            require_page_count=3,
            min_pilot_records=1,
            min_selected_pages=1,
            min_prompt_records=1,
            min_retrieval_only_records=1,
        ),
        write_quality=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["vision_pilot_record_count"] >= 1
    assert report["summary"]["visual_answer_allowed_count"] == 0
    assert report["summary"]["source_truth_mutation_allowed_count"] == 0
    assert Path(report["report_path"]).exists()
    assert Path(report["prompts_path"]).exists()
    assert Path(report["quality_path"]).exists()


def test_max_pilot_pages_is_respected():
    visual_calibration, figure_chart = sample_inputs()
    records = collect_candidate_records(
        visual_calibration,
        figure_chart,
        audit_by_page={},
        visual_text_by_page={},
        max_pilot_pages=1,
    )
    assert len(records) == 1


def test_text_heavy_chart_candidate_is_not_selected_without_strong_visual_signal():
    visual_calibration = {
        "quality_status": "PASS",
        "summary": {"calibrated_page_count": 2},
        "records": [
            {
                "page_id": "t_p_120_1176_p000001",
                "calibrated_layout_class": "text_heavy",
                "calibrated_visual_type": "text_layout",
                "previous_visual_type": "chart_or_plot_candidate",
                "needs_vision_model": False,
                "recommended_extraction_routes": ["source_trace_route", "ocr_text_route"],
            },
            {
                "page_id": "t_p_120_1176_p000048",
                "calibrated_layout_class": "figure_or_diagram",
                "calibrated_visual_type": "parts_diagram_or_illustrated_parts_list",
                "needs_vision_model": True,
            },
        ],
    }
    figure_chart = {
        "quality_status": "PASS",
        "records": [
            {"page_id": "t_p_120_1176_p000001", "visual_type": "chart_or_plot_candidate"},
            {"page_id": "t_p_120_1176_p000048", "visual_type": "parts_diagram_or_illustrated_parts_list", "requires_catalog_compare": True},
        ],
    }
    records = collect_candidate_records(
        visual_calibration,
        figure_chart,
        audit_by_page={},
        visual_text_by_page={},
        max_pilot_pages=10,
    )
    pages = {r["page_id"] for r in records}
    assert "t_p_120_1176_p000001" not in pages
    assert "t_p_120_1176_p000048" in pages


def test_include_pages_can_force_a_text_heavy_page_for_manual_pilot_review():
    visual_calibration, figure_chart = sample_inputs()
    records = collect_candidate_records(
        visual_calibration,
        figure_chart,
        audit_by_page={},
        visual_text_by_page={},
        max_pilot_pages=10,
        include_pages=["t_p_120_1176_p000001"],
    )
    page1 = [r for r in records if r["page_id"] == "t_p_120_1176_p000001"]
    assert page1
    assert page1[0]["forced_include"] is True
