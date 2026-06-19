from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from tiff.trace_net_table_line_geometry_v1 import (
    build_report,
    detect_table_lines_from_image,
    domain_validate_records,
    extract_table_records,
)


def _write_sample_normalizer(path: Path, image_path: Path | None = None) -> None:
    payload = {
        "quality_status": "PASS",
        "normalized_cells": [
            {
                "cell_id": "cell_1",
                "row_id": "row_1",
                "table_id": "table_A",
                "table_type": "parts_list_table",
                "page_id": "t_p_120_1176_p000003",
                "source_page_ids": ["t_p_120_1176_p000003"],
                "text": "120-50648-001",
                "bbox": {"x0": 10, "y0": 10, "x1": 110, "y1": 30},
                "citation_ids": ["cite:table_structured:t_p_120_1176_p000003:abc"],
                "image_path": str(image_path) if image_path else None,
            },
            {
                "cell_id": "cell_2",
                "row_id": "row_1",
                "table_id": "table_A",
                "table_type": "parts_list_table",
                "page_id": "t_p_120_1176_p000003",
                "source_page_ids": ["t_p_120_1176_p000003"],
                "text": "120-50648-003",
                "bbox": {"x0": 130, "y0": 10, "x1": 230, "y1": 30},
            },
            {
                "cell_id": "cell_3",
                "row_id": "row_2",
                "table_id": "table_A",
                "table_type": "parts_list_table",
                "page_id": "t_p_120_1176_p000003",
                "source_page_ids": ["t_p_120_1176_p000003"],
                "text": "APPLICABILITY",
                "bbox": {"x0": 10, "y0": 50, "x1": 230, "y1": 70},
            },
            {
                "row_id": "row_3",
                "table_id": "table_A",
                "table_type": "parts_list_table",
                "page_id": "t_p_120_1176_p000003",
                "source_page_ids": ["t_p_120_1176_p000003"],
                "text": "120-50648-001 120-50648-003",
                "document_type": "table_row_normalized",
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_table_image(path: Path) -> None:
    image = Image.new("L", (260, 100), 255)
    draw = ImageDraw.Draw(image)
    for y in (8, 35, 75):
        draw.line((5, y, 250, y), fill=0, width=2)
    for x in (5, 120, 250):
        draw.line((x, 8, x, 75), fill=0, width=2)
    image.save(path)


def test_morphological_line_detection_finds_horizontal_and_vertical_lines(tmp_path: Path) -> None:
    image_path = tmp_path / "table.png"
    _write_table_image(image_path)

    result = detect_table_lines_from_image(image_path)

    assert result["image_line_detection_available"] is True
    assert len(result["horizontal_lines"]) >= 2
    assert len(result["vertical_lines"]) >= 2
    assert result["intersection_count"] >= 4


def test_extract_records_and_domain_validation(tmp_path: Path) -> None:
    normalizer_path = tmp_path / "normalizer.json"
    _write_sample_normalizer(normalizer_path)
    payload = json.loads(normalizer_path.read_text(encoding="utf-8"))

    records = extract_table_records(payload)
    domain = domain_validate_records(records)

    assert len(records) >= 4
    assert domain["part_number_count"] >= 2
    assert "parts_list_or_ipl_table" in domain["domain_table_type_hints"]
    assert all(record["can_answer_directly"] is False for record in records)


def test_build_report_writes_pass_artifacts_with_geometry_cards(tmp_path: Path) -> None:
    image_path = tmp_path / "table.png"
    _write_table_image(image_path)
    normalizer_path = tmp_path / "normalizer.json"
    _write_sample_normalizer(normalizer_path, image_path=image_path)
    output_dir = tmp_path / "out"

    report = build_report(
        normalizer_path,
        output_dir=output_dir,
        thresholds={
            "min_table_geometry_cards": 1,
            "min_cell_records": 3,
            "max_unsafe_geometry_cards": 0,
            "require_no_answer_permission": True,
        },
        quality=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["table_geometry_card_count"] == 1
    assert report["summary"]["cell_record_count"] >= 3
    assert report["summary"]["image_line_detection_card_count"] == 1
    assert report["summary"]["can_answer_directly_count"] == 0
    assert (output_dir / "trace_net_table_line_geometry_v1.json").exists()
    assert (output_dir / "trace_net_table_line_geometry_v1_quality.json").exists()


def test_build_report_fallback_without_image_is_retrieval_only(tmp_path: Path) -> None:
    normalizer_path = tmp_path / "normalizer.json"
    _write_sample_normalizer(normalizer_path)
    report = build_report(
        normalizer_path,
        output_dir=tmp_path / "out",
        thresholds={"min_table_geometry_cards": 1, "require_no_answer_permission": True},
        quality=True,
    )

    card = report["table_geometry_cards"][0]
    assert report["quality_status"] == "PASS"
    assert card["geometry_inference_method"] == "ocr_bbox_row_column_clustering"
    assert card["retrieval_only"] is True
    assert card["can_prove_claims"] is False
    assert card["source_truth_mutation_allowed"] is False


def test_extract_records_inherits_lineage_for_nested_cells() -> None:
    payload = {
        "quality_status": "PASS",
        "tables": [
            {
                "table_id": "table_nested",
                "table_type": "parts_list_table",
                "page_id": "t_p_120_1176_p000003",
                "source_page_ids": ["t_p_120_1176_p000003"],
                "rows": [
                    {
                        "normalized_row_id": "row_nested_1",
                        "cells": [
                            {"normalized_cell_id": "cell_nested_1", "normalized_text": "120-50648-001", "column_index": 0},
                            {"normalized_cell_id": "cell_nested_2", "normalized_text": "APPLICABILITY", "column_index": 1},
                        ],
                    }
                ],
            }
        ],
    }

    records = extract_table_records(payload)
    cells = [record for record in records if record["record_type"] == "cell"]

    assert len(cells) == 2
    assert {cell["text"] for cell in cells} == {"120-50648-001", "APPLICABILITY"}
    assert all(cell["page_id"] == "t_p_120_1176_p000003" for cell in cells)
    assert all(cell["table_id"] == "table_nested" for cell in cells)
    assert all(cell["row_id"] == "row_nested_1" for cell in cells)
    assert all(cell["source_trace_present"] is True for cell in cells)


def test_extract_records_from_scalar_cell_arrays() -> None:
    payload = {
        "quality_status": "PASS",
        "normalized_tables": [
            {
                "table_id": "table_scalar",
                "page_id": "t_p_120_1176_p000003",
                "source_page_ids": ["t_p_120_1176_p000003"],
                "normalized_rows": [
                    {"row_id": "row_scalar_1", "normalized_cells": ["120-50648-001", "120-50648-003"]}
                ],
            }
        ],
    }

    records = extract_table_records(payload)
    cells = [record for record in records if record["record_type"] == "cell"]

    assert len(cells) == 2
    assert cells[0]["table_id"] == "table_scalar"
    assert cells[0]["row_id"] == "row_scalar_1"
    assert cells[0]["source_page_ids"] == ["t_p_120_1176_p000003"]
