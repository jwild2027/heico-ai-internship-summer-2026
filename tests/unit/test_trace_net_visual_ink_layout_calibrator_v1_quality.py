from pathlib import Path
import json

from tiff import trace_net_visual_ink_layout_calibrator_v1 as mod


def write_json(path: Path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def base_report():
    return {
        "schema_version": mod.SCHEMA_VERSION,
        "summary": {
            "calibrated_page_count": 509,
            "ink_metric_page_count": 509,
            "blank_page_count": 14,
            "text_heavy_page_count": 20,
            "table_or_grid_page_count": 200,
            "parts_list_or_diagram_page_count": 200,
            "figure_or_diagram_page_count": 100,
            "chart_or_plot_page_count": 4,
            "reclassified_page_count": 30,
            "visual_answer_allowed_count": 0,
            "unverified_visual_claim_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "unsafe_visual_layout_record_count": 0,
            "pages_with_recommended_routes_count": 509,
            "pages_with_fishnet_plan_count": 509,
        },
    }


def test_quality_passes_full_thresholds(tmp_path: Path):
    path = tmp_path / "report.json"
    write_json(path, base_report())
    quality = mod.check_quality_from_report(
        report_path=path,
        require_page_count=509,
        min_calibrated_pages=509,
        min_ink_metric_pages=509,
        min_blank_pages=14,
        min_reclassified_pages=1,
        max_chart_pages=50,
        write_json_quality=True,
    )
    assert quality["quality_status"] == "PASS"
    assert Path(quality["quality_path"]).exists()


def test_quality_fails_chart_overroute():
    report = base_report()
    report["summary"]["chart_or_plot_page_count"] = 100
    quality = mod.build_quality(report, min_calibrated_pages=509, min_ink_metric_pages=509, max_chart_pages=50)
    assert quality["quality_status"] == "FAIL"
    assert any(c["name"] == "max_chart_pages" and not c["passed"] for c in quality["checks"])


def test_public_summary_sanitizes_paths():
    text = mod.safe_public_text(r"OCR path: C:\Users\juswil\file.tif local_data\rescarta_exports\x Source URL: http://localhost")
    assert "local_data" not in text
    assert "C:\\Users" not in text
    assert "Source URL" not in text
