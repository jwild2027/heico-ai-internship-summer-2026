from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from tiff.trace_net_table_line_geometry_v1 import build_report


def _write_table_image(path: Path) -> None:
    image = Image.new("L", (320, 140), 255)
    draw = ImageDraw.Draw(image)
    for y in (10, 45, 85, 125):
        draw.line((10, y, 300, y), fill=0, width=3)
    for x in (10, 110, 210, 300):
        draw.line((x, 10, x, 125), fill=0, width=3)
    image.save(path)


def _write_normalizer(path: Path) -> None:
    payload = {
        "quality_status": "PASS",
        "tables": [
            {
                "table_id": "normtable__image_resolver",
                "table_type": "parts_list_table",
                "page_id": "t_p_120_1176_p000003",
                "source_page_ids": ["t_p_120_1176_p000003"],
                "rows": [
                    {
                        "row_id": "row_1",
                        "cells": [
                            {"cell_id": "cell_1", "text": "120-50648-001", "column_index": 0},
                            {"cell_id": "cell_2", "text": "APPLICABILITY", "column_index": 1},
                        ],
                    },
                    {
                        "row_id": "row_2",
                        "cells": [
                            {"cell_id": "cell_3", "text": "120-50648-003", "column_index": 0},
                            {"cell_id": "cell_4", "text": "REF", "column_index": 1},
                        ],
                    },
                ],
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_resolver(path: Path, image_path: Path) -> None:
    payload = {
        "quality_status": "PASS",
        "schema_version": "trace_net_table_image_resolver_v1",
        "table_image_resolution_cards": [
            {
                "resolver_card_id": "resolver_1",
                "page_id": "t_p_120_1176_p000003",
                "table_id": "normtable__image_resolver",
                "table_type": "parts_list_table",
                "image_resolution_status": "RESOLVED",
                "image_resolution_confidence": 1.0,
                "resolved_image_path": str(image_path),
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_report_uses_table_image_resolver_for_morphology(tmp_path: Path) -> None:
    image_path = tmp_path / "zip_page_000003_00000003.tif"
    _write_table_image(image_path)
    normalizer_path = tmp_path / "normalizer.json"
    resolver_path = tmp_path / "resolver.json"
    _write_normalizer(normalizer_path)
    _write_resolver(resolver_path, image_path)

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
    assert report["summary"]["table_image_resolver_quality_status"] == "PASS"
    assert report["summary"]["image_line_detection_card_count"] == 1
    assert report["summary"]["image_morphology_card_count"] == 1
    card = report["table_geometry_cards"][0]
    assert card["geometry_inference_method"] == "image_morphology_with_ocr_fallback"
    assert card["table_image_resolver_available"] is True
    assert card["image_line_detection_available"] is True
    assert card["horizontal_line_count"] >= 3
    assert card["vertical_line_count"] >= 3
    assert card["can_answer_directly"] is False
    assert card["can_prove_claims"] is False
    assert card["source_truth_mutation_allowed"] is False
