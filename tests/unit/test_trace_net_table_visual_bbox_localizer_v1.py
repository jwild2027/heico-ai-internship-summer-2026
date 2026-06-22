from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

from tiff.trace_net_table_visual_bbox_localizer_v1 import build_report, refine_bbox_with_visual_signal


def _draw_table_image(path: Path) -> None:
    image = Image.new("L", (1000, 1000), 255)
    draw = ImageDraw.Draw(image)
    # Real table is much tighter than the input bbox.
    left, top, right, bottom = 220, 310, 790, 720
    for x in range(left, right + 1, 95):
        draw.line((x, top, x, bottom), fill=0, width=3)
    for y in range(top, bottom + 1, 41):
        draw.line((left, y, right, y), fill=0, width=3)
    # Add text-like marks inside cells.
    for row in range(8):
        for col in range(5):
            x = left + 15 + col * 95
            y = top + 12 + row * 41
            draw.rectangle((x, y, x + 35, y + 6), fill=0)
    # Header/footer noise outside table but inside broad input bbox.
    draw.rectangle((120, 120, 700, 135), fill=0)
    draw.rectangle((150, 880, 860, 895), fill=0)
    image.save(path)


def _write_enrichment_report(path: Path, image_path: Path) -> None:
    payload = {
        "schema_version": "trace_net_table_ocr_bbox_enrichment_v1",
        "quality_status": "PASS",
        "table_ocr_bbox_enrichment_cards": [
            {
                "ocr_bbox_enrichment_id": "ocrbbox__001",
                "page_id": "t_p_120_1176_p000003",
                "table_id": "table__p3",
                "image_path": str(image_path),
                "bbox_source": "table_extraction_bbox_preferred",
                "table_extraction_bbox_source": "table_paddle_style_bbox_resolver",
                "inferred_table_region_bbox": {"x0": 100, "y0": 100, "x1": 900, "y1": 920},
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _args(tmp_path: Path, enrichment: Path) -> argparse.Namespace:
    return argparse.Namespace(
        table_ocr_bbox_enrichment=str(enrichment),
        image_root=str(tmp_path),
        output_dir=str(tmp_path / "out"),
        max_image_files_scanned=25000,
        min_source_cards=1,
        min_localized_records=1,
        min_image_available_records=1,
        min_visual_refined_records=1,
        min_localization_ready_records=1,
        min_localization_quality_pass_records=1,
        max_unsafe_records=0,
        max_answer_permission_count=0,
        max_source_truth_mutation_allowed=0,
        require_table_ocr_bbox_enrichment_quality_pass=True,
        require_no_answer_permission=True,
        quality=True,
        write_json=False,
    )


def test_visual_refinement_tightens_broad_table_bbox(tmp_path: Path) -> None:
    image_path = tmp_path / "t_p_120_1176_p000003.png"
    _draw_table_image(image_path)
    input_bbox = {"x0": 100, "y0": 100, "x1": 900, "y1": 920}

    refined, diag = refine_bbox_with_visual_signal(image_path, input_bbox)

    assert refined is not None
    assert diag["visual_refinement_applied"] is True
    assert refined["x0"] > 150
    assert refined["y0"] > 250
    assert refined["x1"] < 850
    assert refined["y1"] < 780
    assert diag["refined_to_input_area_ratio"] < 0.75
    assert diag["horizontal_line_run_count"] >= 2


def test_build_report_writes_visual_localizer_outputs(tmp_path: Path) -> None:
    image_path = tmp_path / "t_p_120_1176_p000003.png"
    report_path = tmp_path / "enrichment.json"
    _draw_table_image(image_path)
    _write_enrichment_report(report_path, image_path)

    payload = build_report(_args(tmp_path, report_path))
    summary = payload["summary"]

    assert payload["quality_status"] == "PASS"
    assert summary["source_card_count"] == 1
    assert summary["image_available_record_count"] == 1
    assert summary["visual_refined_bbox_record_count"] == 1
    assert summary["table_localization_quality_pass_record_count"] == 1
    assert summary["answer_permission_count"] == 0
    assert summary["source_truth_mutation_allowed_count"] == 0

    record = payload["table_visual_bbox_localizer_records"][0]
    assert record["localized_bbox_source"] == "visual_dark_pixel_line_refined"
    assert record["table_localization_ready"] is True
    assert record["answer_permission"] is False
    assert record["can_prove_claims"] is False

    assert (tmp_path / "out" / "trace_net_table_visual_bbox_localizer_v1.json").exists()
    assert (tmp_path / "out" / "trace_net_table_visual_bbox_localizer_v1_records.jsonl").exists()


def test_missing_image_falls_back_safely_and_fails_strict_quality(tmp_path: Path) -> None:
    report_path = tmp_path / "enrichment.json"
    payload = {
        "quality_status": "PASS",
        "table_ocr_bbox_enrichment_cards": [
            {
                "page_id": "t_p_120_1176_p000004",
                "table_id": "table__p4",
                "inferred_table_region_bbox": {"x0": 10, "y0": 10, "x1": 90, "y1": 90},
            }
        ],
    }
    report_path.write_text(json.dumps(payload), encoding="utf-8")
    args = _args(tmp_path, report_path)
    args.min_image_available_records = 1
    args.min_visual_refined_records = 1
    args.min_localization_quality_pass_records = 1

    result = build_report(args)

    assert result["quality_status"] == "FAIL"
    record = result["table_visual_bbox_localizer_records"][0]
    assert record["localized_bbox_source"] == "input_bbox_fallback"
    assert record["answer_permission"] is False
    assert record["source_truth_mutation_allowed"] is False


def _draw_split_column_table_image(path: Path) -> None:
    image = Image.new("L", (1200, 1200), 255)
    draw = ImageDraw.Draw(image)
    top, bottom = 240, 760
    left_a, right_a = 150, 450
    left_b, right_b = 620, 930
    for left, right in ((left_a, right_a), (left_b, right_b)):
        for x in range(left, right + 1, 75):
            draw.line((x, top, x, bottom), fill=0, width=3)
        for y in range(top, bottom + 1, 52):
            draw.line((left, y, right, y), fill=0, width=3)
        for row in range(8):
            for col in range(3):
                x = left + 12 + col * 75
                y = top + 16 + row * 52
                draw.rectangle((x, y, x + 34, y + 5), fill=0)
    # Page furniture that should not extend the crop.
    draw.rectangle((80, 80, 700, 96), fill=0)
    draw.rectangle((250, 1015, 990, 1032), fill=0)
    draw.rectangle((980, 1045, 1090, 1060), fill=0)
    image.save(path)


def test_split_column_table_localization_merges_columns_and_suppresses_footer(tmp_path: Path) -> None:
    image_path = tmp_path / "t_p_120_1176_p000321.png"
    _draw_split_column_table_image(image_path)
    input_bbox = {"x0": 60, "y0": 60, "x1": 1120, "y1": 1080}

    refined, diag = refine_bbox_with_visual_signal(image_path, input_bbox)

    assert refined is not None
    assert diag["visual_refinement_applied"] is True
    assert diag["multi_column_vertical_merge_applied"] is True
    assert refined["x0"] < 180
    assert refined["x1"] > 900
    assert refined["y0"] > 180
    assert refined["y1"] < 900
    assert diag["refined_to_input_area_ratio"] < 0.75
