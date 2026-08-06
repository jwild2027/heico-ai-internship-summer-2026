import json
from pathlib import Path

import pytest

from tiff.trace_net_table_full_enclosure_bbox_overlay_export_v1 import (
    bbox_from_value,
    build_overlay_export,
    evaluate_quality,
    write_outputs,
)

PIL = pytest.importorskip("PIL.Image")
from PIL import Image, ImageDraw


def make_page(path: Path) -> None:
    img = Image.new("RGB", (400, 600), "white")
    draw = ImageDraw.Draw(img)
    # Draw a simple table-like grid.
    for x in (60, 160, 260, 340):
        draw.line((x, 80, x, 520), fill="black", width=3)
    for y in range(80, 521, 40):
        draw.line((60, y, 340, y), fill="black", width=3)
    img.save(path)


def fake_reconstructor(path: Path, image_path: Path) -> None:
    payload = {
        "schema_version": "trace_net_table_full_enclosure_bbox_reconstructor_v1",
        "status": "TABLE_FULL_ENCLOSURE_BBOX_RECONSTRUCTOR_BUILT",
        "quality_status": "PASS",
        "summary": {"quality_status": "PASS"},
        "table_full_enclosure_bbox_reconstructor_records": [
            {
                "page_id": "t_p_120_1176_p000003",
                "table_id": "table_a",
                "image_path": str(image_path),
                "input_table_bbox": {"x0": 45, "y0": 70, "x1": 355, "y1": 535, "coordinate_system": "pixels"},
                "visual_candidate_table_bbox": {"x0": 150, "y0": 90, "x1": 260, "y1": 500, "coordinate_system": "pixels"},
                "structure_visual_candidate_rejected": True,
                "final_table_bbox": {"x0": 40, "y0": 65, "x1": 360, "y1": 540, "coordinate_system": "pixels"},
                "final_table_bbox_source": "full_table_boundary_reconstructed",
                "full_table_enclosure_bbox_ready": True,
                "full_table_enclosure_recommended": True,
                "table_presence_label": "weak_table",
                "table_route_challenged": True,
                "review_flags": ["full_table_enclosure_reconstruction_recommended"],
            },
            {
                "page_id": "t_p_120_1176_p000006",
                "table_id": "table_b",
                "image_path": str(image_path),
                "input_table_bbox": {"x0": 50, "y0": 75, "x1": 350, "y1": 530, "coordinate_system": "pixels"},
                "final_table_bbox": {"x0": 0, "y0": 0, "x1": 400, "y1": 600, "coordinate_system": "pixels"},
                "final_table_bbox_source": "full_page_table_bbox",
                "full_page_bbox_applied": True,
                "full_table_enclosure_bbox_ready": True,
                "full_table_enclosure_recommended": True,
                "full_table_enclosure_reconstructed": False,
                "table_presence_label": "weak_table",
                "table_route_challenged": True,
                "review_flags": ["full_page_bbox_for_step0_table_extraction"],
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_bbox_from_value_parses_dict_and_list():
    assert bbox_from_value({"x0": 1, "y0": 2, "x1": 5, "y1": 9})["width"] == 4
    assert bbox_from_value([5, 9, 1, 2])["x0"] == 1


def test_build_overlay_export_writes_pngs_and_contact_sheet(tmp_path):
    image_path = tmp_path / "page_p000003.png"
    make_page(image_path)
    report_path = tmp_path / "reconstructor.json"
    fake_reconstructor(report_path, image_path)

    output_dir = tmp_path / "out"
    payload = build_overlay_export(
        table_full_enclosure_bbox_reconstructor=report_path,
        image_root=tmp_path,
        output_dir=output_dir,
        max_image_files_scanned=100,
        max_overlay_dimension=800,
        contact_sheet_columns=1,
        contact_sheet_thumb_width=400,
    )
    quality = evaluate_quality(
        payload,
        args=type("Args", (), {
            "require_table_full_enclosure_bbox_reconstructor_quality_pass": True,
            "min_source_records": 2,
            "min_overlay_records": 2,
            "min_image_available_records": 2,
            "min_overlay_pngs": 2,
            "min_contact_sheets": 1,
            "min_final_bbox_ready_overlays": 2,
            "min_full_enclosure_reconstructed_overlays": 1,
            "max_unsafe_records": 0,
            "max_answer_permission_count": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_no_answer_permission": True,
        })(),
    )
    write_outputs(payload, output_dir, quality)

    summary = payload["summary"]
    assert quality["quality_status"] == "PASS"
    assert summary["source_record_count"] == 2
    assert summary["overlay_png_written_count"] == 2
    assert summary["contact_sheet_written_count"] == 1
    assert summary["full_enclosure_reconstructed_overlay_count"] == 2
    assert summary["full_table_boundary_reconstructed_overlay_count"] == 1
    assert summary["full_page_bbox_overlay_count"] == 1
    assert summary["structure_passthrough_overlay_count"] == 0
    assert (output_dir / "trace_net_table_full_enclosure_bbox_overlay_export_v1.json").exists()
    assert Path(summary["contact_sheet_path"]).exists()
