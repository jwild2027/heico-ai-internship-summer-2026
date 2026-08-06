from __future__ import annotations

import json
from pathlib import Path

import pytest

from tiff.trace_net_scan_quality_assessment_v1 import (
    assess_scan_quality,
    assess_scan_quality_from_record,
    build_scan_quality_manifest,
    metrics_from_luma_grid,
    validate_route_labels,
    validate_route_record,
    validate_scan_quality_record,
)


def test_route_taxonomy_rejects_blurry_as_page_classification():
    with pytest.raises(ValueError):
        validate_route_labels(["table_or_index", "blurry"])
    with pytest.raises(ValueError):
        validate_route_labels(["degraded_scan"])


def test_ocr_recovery_route_is_allowed():
    result = validate_route_labels(["ocr_scan_recovery", "table_or_index"])
    assert result["quality_status"] == "PASS"


def test_query_wording_cannot_mark_a_clear_page_blurry():
    metrics = {
        "sharpness_score": 0.82,
        "edge_spread_pixels": 1.1,
        "local_contrast": 0.45,
        "width": 3205,
        "height": 4146,
        "dpi": 377,
    }
    clean = assess_scan_quality(metrics, page_route="table_or_index", query_text="clear page")
    claimed = assess_scan_quality(metrics, page_route="table_or_index", query_text="the blurry damaged page")
    assert clean == claimed
    assert claimed["quality_state"] == "clear"
    assert claimed["blur_detected"] is False
    assert claimed["query_text_influenced_assessment"] is False


def test_bad_ocr_reading_order_does_not_imply_blur():
    result = assess_scan_quality(
        {
            "layout_reading_order_conflict": True,
            "ocr_confidence": 0.32,
            "ocr_character_coverage": 0.40,
        },
        page_route="table_or_index",
    )
    assert result["quality_state"] == "uncertain"
    assert result["layout_reconstruction_issue"] is True
    assert result["blur_detected"] is False


def test_clear_diagram_with_few_ocr_words_is_not_blurry():
    record = {
        "ocr_text_word_count": 3,
        "image_features": {
            "sharpness_score": 0.76,
            "edge_spread_pixels": 1.0,
            "local_contrast": 0.39,
            "width": 2400,
            "height": 3200,
            "dpi": 300,
        },
    }
    result = assess_scan_quality_from_record(record, page_route="image_visual_diagram")
    assert result["quality_state"] == "clear"
    assert result["blur_detected"] is False


def test_blank_page_does_not_imply_blur():
    result = assess_scan_quality(
        {
            "sharpness_score": 0.0,
            "edge_spread_pixels": 0.0,
            "local_contrast": 0.0,
            "width": 2400,
            "height": 3200,
            "dpi": 300,
        },
        page_route="blank_candidate",
    )
    assert result["blur_detected"] is False
    assert "low_contrast" not in result["degradation_types"]


def test_low_contrast_is_not_automatically_blur():
    result = assess_scan_quality(
        {
            "sharpness_score": 0.55,
            "edge_spread_pixels": 1.2,
            "local_contrast": 0.05,
            "width": 2400,
            "height": 3200,
            "dpi": 300,
        },
        page_route="normal_text",
    )
    assert result["quality_state"] == "degraded"
    assert result["low_contrast_detected"] is True
    assert result["blur_detected"] is False



def test_clear_high_resolution_table_metrics_do_not_trigger_conservative_blur():
    # Representative of a crisp high-resolution table scan after safe thumbnail
    # measurement.  Downsampling may broaden edges, so uncalibrated metrics must
    # never produce a positive blur classification.
    result = assess_scan_quality(
        {
            "sharpness_score": 0.163809,
            "edge_spread_pixels": 3.26526,
            "local_contrast": 0.281937,
            "width": 3205,
            "height": 4146,
            "dpi": 377,
        },
        page_route="table_or_index",
    )
    assert result["quality_state"] == "clear"
    assert result["blur_detected"] is False
    assert result["blur_measurement_calibrated"] is False

def test_synthetic_blur_requires_two_image_signals():
    result = assess_scan_quality(
        {
            "sharpness_score": 0.03,
            "edge_spread_pixels": 6.5,
            "blur_measurement_calibrated": True,
            "local_contrast": 0.35,
            "width": 2400,
            "height": 3200,
            "dpi": 300,
        },
        page_route="normal_text",
    )
    assert result["quality_state"] == "degraded"
    assert result["blur_detected"] is True
    assert validate_scan_quality_record(result)["quality_status"] == "PASS"


def test_low_sharpness_without_edge_spread_abstains_from_blur():
    result = assess_scan_quality(
        {"sharpness_score": 0.05, "width": 2400, "height": 3200},
        page_route="normal_text",
    )
    assert result["blur_detected"] is False
    assert result["blur_assessment_complete"] is False


def test_luma_grid_metrics_distinguish_crisp_and_smoothed_edges():
    crisp = [[0 if (x // 2) % 2 == 0 else 255 for x in range(32)] for _ in range(16)]
    smooth_row = [0, 0, 20, 55, 95, 135, 175, 215, 245, 255, 255, 255, 245, 215, 175, 135, 95, 55, 20, 0, 0, 0, 20, 55, 95, 135, 175, 215, 245, 255, 255, 255]
    smooth = [smooth_row[:] for _ in range(16)]
    crisp_metrics = metrics_from_luma_grid(crisp)
    smooth_metrics = metrics_from_luma_grid(smooth)
    assert crisp_metrics["sharpness_score"] > smooth_metrics["sharpness_score"]
    assert smooth_metrics["edge_spread_pixels"] > crisp_metrics["edge_spread_pixels"]


def test_route_record_validation_checks_primary_secondary_and_candidates():
    result = validate_route_record({
        "primary_route": "table_or_index",
        "secondary_routes": ["normal_text"],
        "candidate_routes": ["blurry"],
    })
    assert result["quality_status"] == "FAIL"


def test_manifest_preserves_route_and_emits_separate_quality(tmp_path: Path):
    source = tmp_path / "input.json"
    output = tmp_path / "output.json"
    source.write_text(json.dumps({
        "records": [{
            "page_id": "p1",
            "primary_route": "table_or_index",
            "image_quality_metrics": {
                "sharpness_score": 0.8,
                "edge_spread_pixels": 1.0,
                "local_contrast": 0.4,
                "width": 2000,
                "height": 3000,
            },
        }]
    }), encoding="utf-8")
    result = build_scan_quality_manifest(input_path=source, output_path=output)
    row = result["records"][0]
    assert row["primary_route"] == "table_or_index"
    assert row["scan_quality"]["quality_state"] == "clear"
    assert row["scan_quality"]["scan_quality_is_not_page_route"] is True
