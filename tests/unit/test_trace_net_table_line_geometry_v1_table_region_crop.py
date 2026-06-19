from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from tiff.trace_net_table_line_geometry_v1 import build_report, detect_table_lines_from_image


def test_detect_table_lines_from_image_supports_table_region_crop(tmp_path: Path) -> None:
    image_path = tmp_path / "page_with_table_crop.tif"
    image = Image.new("L", (500, 500), 255)
    draw = ImageDraw.Draw(image)
    # Page-level distraction: one long border outside the table region.
    draw.line((10, 30, 490, 30), fill=0, width=3)
    # Table grid in a lower region.
    for y in (220, 270, 320, 370):
        draw.line((120, y, 420, y), fill=0, width=3)
    for x in (120, 220, 320, 420):
        draw.line((x, 220, x, 370), fill=0, width=3)
    image.save(image_path)

    page_result = detect_table_lines_from_image(image_path)
    crop_result = detect_table_lines_from_image(image_path, crop_bbox={"x0": 100, "y0": 200, "x1": 440, "y1": 390})

    assert page_result["image_line_detection_available"] is True
    assert crop_result["image_line_detection_available"] is True
    assert crop_result["table_region_crop_applied"] is True
    assert crop_result["table_region_bbox"]["x0"] == 100
    assert crop_result["morphology_signal_strength"] == "GRID"
    assert len(crop_result["horizontal_lines"]) >= 3
    assert len(crop_result["vertical_lines"]) >= 3
    # Lines are reported in page coordinates after crop offset is reapplied.
    assert min(line["x0"] for line in crop_result["horizontal_lines"]) >= 100
    assert min(line["y0"] for line in crop_result["vertical_lines"]) >= 200


def _write_table_page(path: Path) -> None:
    image = Image.new("L", (500, 500), 255)
    draw = ImageDraw.Draw(image)
    for y in (220, 270, 320, 370):
        draw.line((120, y, 420, y), fill=0, width=3)
    for x in (120, 220, 320, 420):
        draw.line((x, 220, x, 370), fill=0, width=3)
    image.save(path)


def test_build_report_uses_bbox_table_region_crop_when_available(tmp_path: Path) -> None:
    image_path = tmp_path / "zip_page_000003_00000003.tif"
    _write_table_page(image_path)
    normalizer_path = tmp_path / "normalizer.json"
    normalizer_payload = {
        "quality_status": "PASS",
        "tables": [
            {
                "table_id": "normtable__crop",
                "table_type": "parts_list_table",
                "page_id": "t_p_120_1176_p000003",
                "source_page_ids": ["t_p_120_1176_p000003"],
                "rows": [
                    {
                        "row_id": "row_1",
                        "cells": [
                            {"cell_id": "cell_1", "text": "120-50648-001", "column_index": 0, "bbox": {"x0": 125, "y0": 225, "x1": 210, "y1": 255}},
                            {"cell_id": "cell_2", "text": "REF", "column_index": 1, "bbox": {"x0": 225, "y0": 225, "x1": 310, "y1": 255}},
                        ],
                    },
                    {
                        "row_id": "row_2",
                        "cells": [
                            {"cell_id": "cell_3", "text": "120-50648-003", "column_index": 0, "bbox": {"x0": 125, "y0": 275, "x1": 210, "y1": 305}},
                            {"cell_id": "cell_4", "text": "AR", "column_index": 1, "bbox": {"x0": 225, "y0": 275, "x1": 310, "y1": 305}},
                        ],
                    },
                ],
            }
        ],
    }
    normalizer_path.write_text(json.dumps(normalizer_payload), encoding="utf-8")
    resolver_path = tmp_path / "resolver.json"
    resolver_path.write_text(
        json.dumps(
            {
                "quality_status": "PASS",
                "table_image_resolution_cards": [
                    {
                        "page_id": "t_p_120_1176_p000003",
                        "table_id": "normtable__crop",
                        "image_resolution_status": "RESOLVED",
                        "image_resolution_confidence": 1.0,
                        "resolved_image_path": str(image_path),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = build_report(
        normalizer_path,
        table_image_resolver_path=resolver_path,
        image_root=tmp_path,
        output_dir=tmp_path / "out",
        thresholds={
            "min_table_geometry_cards": 1,
            "min_cell_records": 4,
            "min_image_line_detection_cards": 1,
            "require_image_line_detection": True,
            "require_table_image_resolver_quality_pass": True,
            "max_unsafe_geometry_cards": 0,
            "require_no_answer_permission": True,
        },
        quality=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["table_region_crop_available_card_count"] == 1
    assert report["summary"]["table_region_crop_applied_card_count"] == 1
    card = report["table_geometry_cards"][0]
    assert card["table_region_crop_available"] is True
    assert card["table_region_crop_applied"] is True
    assert card["selected_morphology_scope"] in {"table_region_crop", "page"}
    assert card["table_region_bbox"] is not None
    assert card["can_answer_directly"] is False
    assert card["can_prove_claims"] is False
    assert card["source_truth_mutation_allowed"] is False
