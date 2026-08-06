from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from tiff.trace_net_table_line_geometry_v1 import detect_table_lines_from_image


def test_calibrated_morphology_detects_gray_grid_lines(tmp_path: Path) -> None:
    image_path = tmp_path / "gray_grid.tif"
    image = Image.new("L", (360, 180), 255)
    draw = ImageDraw.Draw(image)
    for y in (20, 70, 120, 160):
        draw.line((20, y, 340, y), fill=198, width=2)
    for x in (20, 130, 240, 340):
        draw.line((x, 20, x, 160), fill=198, width=2)
    image.save(image_path)

    result = detect_table_lines_from_image(image_path)

    assert result["image_line_detection_available"] is True
    assert result["calibration_attempt_count"] >= 2
    assert result["calibrated_dark_threshold"] >= 198
    assert result["morphology_signal_strength"] == "GRID"
    assert len(result["horizontal_lines"]) >= 3
    assert len(result["vertical_lines"]) >= 3
    assert result["intersection_count"] >= 4


def test_calibrated_morphology_marks_single_border_as_weak_signal(tmp_path: Path) -> None:
    image_path = tmp_path / "single_border.tif"
    image = Image.new("L", (360, 180), 255)
    draw = ImageDraw.Draw(image)
    draw.line((20, 40, 340, 40), fill=0, width=3)
    image.save(image_path)

    result = detect_table_lines_from_image(image_path)

    assert result["image_line_detection_available"] is True
    assert result["morphology_signal_strength"] == "WEAK_LINE_SIGNAL"
    assert "weak_morphology_grid_signal" in result["line_detection_review_flags"]
