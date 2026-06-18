from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from tiff.trace_net_table_line_geometry_v1 import build_report


def _write_grid_page(path: Path) -> None:
    image = Image.new("L", (600, 600), 255)
    draw = ImageDraw.Draw(image)
    # Non-table page border signal near the top.
    draw.line((20, 40, 580, 40), fill=0, width=3)
    # Actual table grid in a lower region.
    for y in (240, 290, 340, 390):
        draw.line((160, y, 500, y), fill=0, width=3)
    for x in (160, 260, 380, 500):
        draw.line((x, 240, x, 390), fill=0, width=3)
    image.save(path)


def _write_normalizer(path: Path) -> None:
    payload = {
        "quality_status": "PASS",
        "tables": [
            {
                "table_id": "normtable__bbox",
                "table_type": "parts_list_table",
                "page_id": "t_p_120_1176_p000003",
                "source_page_ids": ["t_p_120_1176_p000003"],
                "rows": [
                    {"row_id": "row_1", "cells": [{"cell_id": "cell_1", "text": "120-50648-001", "column_index": 0}]},
                    {"row_id": "row_2", "cells": [{"cell_id": "cell_2", "text": "120-50648-003", "column_index": 0}]},
                ],
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_image_resolver(path: Path, image_path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "quality_status": "PASS",
                "table_image_resolution_cards": [
                    {
                        "page_id": "t_p_120_1176_p000003",
                        "table_id": "normtable__bbox",
                        "image_resolution_status": "RESOLVED",
                        "image_resolution_confidence": 1.0,
                        "resolved_image_path": str(image_path),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_build_report_uses_crop_safe_table_bbox_resolver(tmp_path: Path) -> None:
    image_path = tmp_path / "zip_page_000003_00000003.tif"
    _write_grid_page(image_path)
    normalizer_path = tmp_path / "normalizer.json"
    _write_normalizer(normalizer_path)
    image_resolver_path = tmp_path / "image_resolver.json"
    _write_image_resolver(image_resolver_path, image_path)
    bbox_resolver_path = tmp_path / "bbox_resolver.json"
    bbox_resolver_path.write_text(
        json.dumps(
            {
                "quality_status": "PASS",
                "table_bbox_cards": [
                    {
                        "page_id": "t_p_120_1176_p000003",
                        "table_id": "normtable__bbox",
                        "bbox_resolution_status": "RESOLVED",
                        "crop_ready": True,
                        "bbox_source": "explicit_table_bbox",
                        "bbox_confidence": 0.92,
                        "bbox_coverage_ratio": 0.22,
                        "table_region_bbox": {"x0": 130, "y0": 210, "x1": 530, "y1": 420},
                        "review_flags": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = build_report(
        normalizer_path,
        table_image_resolver_path=image_resolver_path,
        table_bbox_resolver_path=bbox_resolver_path,
        image_root=tmp_path,
        output_dir=tmp_path / "out",
        thresholds={
            "min_table_geometry_cards": 1,
            "min_cell_records": 2,
            "min_image_line_detection_cards": 1,
            "min_table_region_crop_available_cards": 1,
            "min_table_region_crop_applied_cards": 1,
            "require_image_line_detection": True,
            "require_table_image_resolver_quality_pass": True,
            "require_table_bbox_resolver_quality_pass": True,
            "require_no_answer_permission": True,
            "max_unsafe_geometry_cards": 0,
        },
        quality=True,
    )

    assert report["quality_status"] == "PASS"
    summary = report["summary"]
    assert summary["table_region_crop_available_card_count"] == 1
    assert summary["table_region_crop_applied_card_count"] == 1
    assert summary["table_bbox_resolver_crop_used_card_count"] == 1
    card = report["table_geometry_cards"][0]
    assert card["table_region_bbox_source"] == "table_bbox_resolver"
    assert card["table_bbox_resolver_used_for_crop"] is True
    assert card["table_region_crop_available"] is True
    assert card["table_region_crop_applied"] is True
    assert card["can_answer_directly"] is False
    assert card["can_prove_claims"] is False
    assert card["source_truth_mutation_allowed"] is False


def test_build_report_rejects_tiny_bbox_resolver_crop(tmp_path: Path) -> None:
    image_path = tmp_path / "zip_page_000003_00000003.tif"
    _write_grid_page(image_path)
    normalizer_path = tmp_path / "normalizer.json"
    _write_normalizer(normalizer_path)
    image_resolver_path = tmp_path / "image_resolver.json"
    _write_image_resolver(image_resolver_path, image_path)
    bbox_resolver_path = tmp_path / "bbox_resolver.json"
    bbox_resolver_path.write_text(
        json.dumps(
            {
                "quality_status": "PASS",
                "table_bbox_cards": [
                    {
                        "page_id": "t_p_120_1176_p000003",
                        "table_id": "normtable__bbox",
                        "bbox_resolution_status": "RESOLVED",
                        "crop_ready": True,
                        "bbox_source": "aggregated_unknown_bboxes",
                        "bbox_confidence": 0.62,
                        "bbox_coverage_ratio": 0.0001,
                        "table_region_bbox": {"x0": 100, "y0": 100, "x1": 250, "y1": 107},
                        "review_flags": ["table_region_bbox_low_specificity"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = build_report(
        normalizer_path,
        table_image_resolver_path=image_resolver_path,
        table_bbox_resolver_path=bbox_resolver_path,
        image_root=tmp_path,
        output_dir=tmp_path / "out",
        thresholds={
            "min_table_geometry_cards": 1,
            "min_cell_records": 2,
            "min_image_line_detection_cards": 1,
            "require_image_line_detection": True,
            "require_table_image_resolver_quality_pass": True,
            "require_table_bbox_resolver_quality_pass": True,
            "require_no_answer_permission": True,
            "max_unsafe_geometry_cards": 0,
        },
        quality=True,
    )

    assert report["quality_status"] == "PASS"
    summary = report["summary"]
    assert summary["table_bbox_resolver_crop_rejected_card_count"] == 1
    assert summary["table_bbox_resolver_crop_used_card_count"] == 0
    assert summary["table_region_crop_available_card_count"] == 0
    card = report["table_geometry_cards"][0]
    assert card["table_bbox_resolver_crop_rejected"] is True
    assert card["table_bbox_resolver_rejection_reason"] == "bbox_below_minimum_crop_dimensions"
    assert "table_bbox_resolver_crop_rejected" in card["review_flags"]
