from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from PIL import Image, ImageDraw

from tiff.trace_net_table_visual_bbox_overlay_export_v1 import build_report, make_contact_sheet, render_overlay


def make_page(path: Path) -> None:
    image = Image.new("RGB", (600, 800), "white")
    draw = ImageDraw.Draw(image)
    for x in (120, 250, 380, 510):
        draw.line((x, 120, x, 620), fill="black", width=3)
    for y in range(120, 621, 50):
        draw.line((120, y, 510, y), fill="black", width=3)
    image.save(path)


def test_render_overlay_draws_input_and_localized_boxes(tmp_path: Path) -> None:
    image_path = tmp_path / "p000001.png"
    make_page(image_path)
    record = {
        "page_id": "t_p_120_1176_p000001",
        "table_id": "table_1",
        "input_bbox": {"x0": 50, "y0": 50, "x1": 550, "y1": 700},
        "localized_table_bbox": {"x0": 120, "y0": 120, "x1": 510, "y1": 620},
        "localized_bbox_source": "visual_dark_pixel_line_refined",
        "localized_bbox_coverage_ratio": 0.4,
        "table_localization_quality_pass": True,
    }
    output_path = tmp_path / "overlay.png"
    result = render_overlay(record, image_path, output_path, max_dimension=400)
    assert result["overlay_written"] is True
    assert output_path.exists()
    with Image.open(output_path) as overlay:
        assert overlay.width <= 400


def test_build_report_writes_overlays_and_contact_sheet(tmp_path: Path) -> None:
    image_path = tmp_path / "t_p_120_1176_p000001.png"
    make_page(image_path)
    source_path = tmp_path / "localizer.json"
    source_payload = {
        "quality_status": "PASS",
        "table_visual_bbox_localizer_records": [
            {
                "visual_bbox_localizer_id": "vis1",
                "page_id": "t_p_120_1176_p000001",
                "table_id": "table_1",
                "image_path": str(image_path),
                "input_bbox": {"x0": 40, "y0": 40, "x1": 560, "y1": 720},
                "localized_table_bbox": {"x0": 120, "y0": 120, "x1": 510, "y1": 620},
                "localized_bbox_source": "visual_dark_pixel_line_refined",
                "localized_bbox_coverage_ratio": 0.4,
                "visual_refinement_applied": True,
                "table_localization_quality_pass": True,
                "review_flags": [],
            }
        ],
    }
    source_path.write_text(json.dumps(source_payload), encoding="utf-8")
    out_dir = tmp_path / "out"
    args = Namespace(
        table_visual_bbox_localizer=str(source_path),
        image_root=str(tmp_path),
        output_dir=str(out_dir),
        max_image_files_scanned=100,
        max_overlay_dimension=500,
        contact_sheet_columns=1,
        contact_sheet_thumb_width=320,
        min_source_records=1,
        min_overlay_records=1,
        min_image_available_records=1,
        min_overlay_pngs=1,
        min_contact_sheets=1,
        max_unsafe_records=0,
        max_answer_permission_count=0,
        max_source_truth_mutation_allowed=0,
        require_table_visual_bbox_localizer_quality_pass=True,
        require_no_answer_permission=True,
        quality=True,
    )
    payload = build_report(args)
    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["overlay_png_written_count"] == 1
    assert payload["summary"]["contact_sheet_written_count"] == 1
    assert Path(payload["summary"]["contact_sheet_path"]).exists()
    records = payload["table_visual_bbox_overlay_export_records"]
    assert records[0]["overlay_written"] is True
    assert records[0]["answer_permission"] is False
    assert records[0]["source_truth_mutation_allowed"] is False


def test_make_contact_sheet_reports_no_overlay_pngs(tmp_path: Path) -> None:
    result = make_contact_sheet([], tmp_path / "sheet.png")
    assert result["contact_sheet_written"] is False
