import json
from pathlib import Path

from tiff.trace_net_table_bbox_resolver_v1 import (
    bbox_from_value,
    extract_bbox_records,
    build_report,
)


def test_bbox_from_normalized_coordinates_scales_to_pixels():
    box = bbox_from_value([0.1, 0.2, 0.5, 0.7], 1000, 2000)
    assert box["x0"] == 100
    assert box["y0"] == 400
    assert box["x1"] == 500
    assert box["y1"] == 1400


def test_extract_nested_cell_bboxes_inherits_context():
    payload = {
        "page_id": "page_1",
        "table_id": "table_1",
        "rows": [
            {
                "row_id": "row_1",
                "cells": [
                    {"cell_id": "cell_1", "bbox": {"x": 10, "y": 20, "width": 50, "height": 12}},
                    {"cell_id": "cell_2", "bounding_box": [70, 20, 120, 32]},
                ],
            }
        ],
    }
    records = extract_bbox_records(payload, width=200, height=100)
    cell_records = [r for r in records if r["record_kind"] == "cell"]
    assert len(cell_records) == 2
    assert {r["page_id"] for r in cell_records} == {"page_1"}
    assert {r["table_id"] for r in cell_records} == {"table_1"}


def test_build_report_uses_heuristic_when_no_record_bboxes(tmp_path):
    tlg = {
        "quality_status": "PASS",
        "table_geometry_cards": [
            {"geometry_card_id": "g1", "page_id": "p1", "table_id": "t1", "table_type": "parts_list_table"}
        ],
    }
    tir = {
        "quality_status": "PASS",
        "table_image_resolution_cards": [
            {
                "page_id": "p1",
                "table_id": "t1",
                "resolved_image_path": str(tmp_path / "page.tif"),
                "image_width": 1000,
                "image_height": 2000,
                "image_resolution_confidence": 1.0,
            }
        ],
    }
    # No real image is needed because resolver card provides dimensions.
    tlg_path = tmp_path / "tlg.json"
    tir_path = tmp_path / "tir.json"
    tcn_path = tmp_path / "tcn.json"
    (tmp_path / "page.tif").write_bytes(b"not-a-real-image-but-path-exists")
    (tmp_path / "page.tif").write_bytes(b"not-a-real-image-but-path-exists")
    tlg_path.write_text(json.dumps(tlg), encoding="utf-8")
    tir_path.write_text(json.dumps(tir), encoding="utf-8")
    tcn_path.write_text(json.dumps({"quality_status": "PASS"}), encoding="utf-8")
    report = build_report(
        table_line_geometry_path=tlg_path,
        table_cell_normalizer_path=tcn_path,
        table_image_resolver_path=tir_path,
        table_ocr_bbox_enrichment_path=None,
        image_root=tmp_path,
        output_dir=tmp_path / "out",
        thresholds={
            "min_source_cards": 1,
            "min_bbox_cards": 1,
            "min_crop_ready_cards": 0,
            "max_unsafe_bbox_cards": 0,
            "max_answer_permission_count": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_table_line_geometry_quality_pass": True,
            "require_table_image_resolver_quality_pass": True,
            "require_no_answer_permission": True,
        },
    )
    assert report["quality_status"] == "PASS"
    card = report["table_bbox_cards"][0]
    assert card["bbox_source"] == "page_content_heuristic_bbox"
    assert card["table_region_bbox"] is not None
    assert card["answer_permission"] is False


def test_build_report_prefers_safe_ocr_bbox_enrichment_candidate(tmp_path):
    tlg = {
        "quality_status": "PASS",
        "table_geometry_cards": [
            {"geometry_card_id": "g1", "page_id": "p1", "table_id": "t1", "table_type": "parts_list_table"}
        ],
    }
    tir = {
        "quality_status": "PASS",
        "table_image_resolution_cards": [
            {
                "page_id": "p1",
                "table_id": "t1",
                "resolved_image_path": str(tmp_path / "page.tif"),
                "image_width": 1000,
                "image_height": 2000,
                "image_resolution_confidence": 1.0,
            }
        ],
    }
    enrich = {
        "quality_status": "PASS",
        "table_ocr_bbox_enrichment_cards": [
            {
                "page_id": "p1",
                "table_id": "t1",
                "crop_candidate_ready": True,
                "bbox_source": "ocr_part_number_token_match",
                "bbox_confidence": 0.92,
                "bbox_coverage_ratio": 0.65,
                "matched_ocr_bbox_count": 20,
                "part_number_ocr_match_count": 5,
                "inferred_table_region_bbox": {"x0": 100, "y0": 200, "x1": 800, "y1": 1600},
            }
        ],
    }
    tlg_path = tmp_path / "tlg.json"
    tir_path = tmp_path / "tir.json"
    tcn_path = tmp_path / "tcn.json"
    enrich_path = tmp_path / "enrich.json"
    (tmp_path / "page.tif").write_bytes(b"not-a-real-image-but-path-exists")
    tlg_path.write_text(json.dumps(tlg), encoding="utf-8")
    tir_path.write_text(json.dumps(tir), encoding="utf-8")
    tcn_path.write_text(json.dumps({"quality_status": "PASS"}), encoding="utf-8")
    enrich_path.write_text(json.dumps(enrich), encoding="utf-8")
    report = build_report(
        table_line_geometry_path=tlg_path,
        table_cell_normalizer_path=tcn_path,
        table_image_resolver_path=tir_path,
        table_ocr_bbox_enrichment_path=enrich_path,
        image_root=tmp_path,
        output_dir=tmp_path / "out2",
        thresholds={
            "min_source_cards": 1,
            "min_bbox_cards": 1,
            "min_crop_ready_cards": 1,
            "min_ocr_bbox_enrichment_used_cards": 1,
            "max_unsafe_bbox_cards": 0,
            "max_answer_permission_count": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_table_line_geometry_quality_pass": True,
            "require_table_image_resolver_quality_pass": True,
            "require_table_ocr_bbox_enrichment_quality_pass": True,
            "require_no_answer_permission": True,
        },
    )
    assert report["quality_status"] == "PASS"
    card = report["table_bbox_cards"][0]
    assert card["bbox_source"] == "ocr_part_number_token_match"
    assert card["ocr_bbox_enrichment_used"] is True
    assert report["summary"]["ocr_bbox_enrichment_used_card_count"] == 1


def test_build_report_rejects_full_page_ocr_enrichment_candidate(tmp_path):
    tlg = {
        "quality_status": "PASS",
        "table_geometry_cards": [
            {"geometry_card_id": "g1", "page_id": "p1", "table_id": "t1", "table_type": "parts_list_table"}
        ],
    }
    tir = {
        "quality_status": "PASS",
        "table_image_resolution_cards": [
            {"page_id": "p1", "table_id": "t1", "resolved_image_path": str(tmp_path / "page.tif"), "image_width": 1000, "image_height": 2000}
        ],
    }
    enrich = {
        "quality_status": "PASS",
        "table_ocr_bbox_enrichment_cards": [
            {
                "page_id": "p1",
                "table_id": "t1",
                "crop_candidate_ready": True,
                "bbox_source": "ocr_table_text_token_match",
                "bbox_confidence": 0.9,
                "bbox_coverage_ratio": 0.99,
                "matched_ocr_bbox_count": 20,
                "inferred_table_region_bbox": {"x0": 0, "y0": 0, "x1": 1000, "y1": 2000},
            }
        ],
    }
    tlg_path = tmp_path / "tlg3.json"
    tir_path = tmp_path / "tir3.json"
    tcn_path = tmp_path / "tcn3.json"
    enrich_path = tmp_path / "enrich3.json"
    (tmp_path / "page.tif").write_bytes(b"not-a-real-image-but-path-exists")
    tlg_path.write_text(json.dumps(tlg), encoding="utf-8")
    tir_path.write_text(json.dumps(tir), encoding="utf-8")
    tcn_path.write_text(json.dumps({"quality_status": "PASS"}), encoding="utf-8")
    enrich_path.write_text(json.dumps(enrich), encoding="utf-8")
    report = build_report(
        table_line_geometry_path=tlg_path,
        table_cell_normalizer_path=tcn_path,
        table_image_resolver_path=tir_path,
        table_ocr_bbox_enrichment_path=enrich_path,
        image_root=tmp_path,
        output_dir=tmp_path / "out3",
        thresholds={
            "min_source_cards": 1,
            "min_bbox_cards": 1,
            "min_crop_ready_cards": 0,
            "min_ocr_bbox_enrichment_used_cards": 0,
            "max_unsafe_bbox_cards": 0,
            "max_answer_permission_count": 0,
            "max_source_truth_mutation_allowed": 0,
            "require_table_line_geometry_quality_pass": True,
            "require_table_image_resolver_quality_pass": True,
            "require_table_ocr_bbox_enrichment_quality_pass": True,
            "require_no_answer_permission": True,
        },
    )
    card = report["table_bbox_cards"][0]
    assert card["ocr_bbox_enrichment_used"] is False
    assert card["ocr_bbox_enrichment_rejected"] is True
    assert card["ocr_bbox_enrichment_rejection_reason"] == "ocr_enrichment_bbox_too_close_to_full_page"
