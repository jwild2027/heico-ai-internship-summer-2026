from __future__ import annotations

from tiff.trace_net_table_line_geometry_v1 import choose_region_or_page_morphology


def _result(horizontal: int, vertical: int, intersections: int, signal: str, score: float) -> dict:
    return {
        "image_line_detection_available": bool(horizontal or vertical),
        "horizontal_lines": [{"id": f"h{i}"} for i in range(horizontal)],
        "vertical_lines": [{"id": f"v{i}"} for i in range(vertical)],
        "intersection_count": intersections,
        "morphology_signal_strength": signal,
        "morphology_quality_score": score,
        "table_region_crop_applied": True,
        "table_region_bbox": {"x0": 0, "y0": 0, "x1": 100, "y1": 100},
    }


def test_broad_horizontal_only_crop_does_not_replace_page_morphology() -> None:
    page = _result(horizontal=1, vertical=0, intersections=0, signal="WEAK_LINE_SIGNAL", score=1.0)
    # More horizontal lines alone used to win by score. It should no longer win
    # because it has no vertical line or intersection gain and comes from a broad
    # OCR crop candidate.
    crop = _result(horizontal=4, vertical=0, intersections=0, signal="WEAK_LINE_SIGNAL", score=4.0)
    selected, comparison = choose_region_or_page_morphology(
        page,
        crop,
        {
            "table_bbox_resolver_bbox_source": "ocr_table_text_token_match",
            "table_bbox_resolver_bbox_coverage_ratio": 0.86,
            "table_bbox_resolver_review_flags": ["ocr_enrichment_bbox_broad_crop_candidate"],
        },
    )

    assert selected["selected_morphology_scope"] == "page"
    assert selected["table_region_crop_applied"] is True
    assert comparison["crop_selection_rejected_no_vertical_or_intersection_gain"] is True
    assert comparison["crop_selection_rejection_reason"] == "broad_crop_without_vertical_or_intersection_gain"


def test_crop_with_real_grid_gain_can_replace_weak_page_morphology() -> None:
    page = _result(horizontal=1, vertical=0, intersections=0, signal="WEAK_LINE_SIGNAL", score=1.0)
    crop = _result(horizontal=4, vertical=3, intersections=8, signal="GRID", score=96.0)
    selected, comparison = choose_region_or_page_morphology(
        page,
        crop,
        {
            "table_bbox_resolver_bbox_source": "explicit_table_bbox",
            "table_bbox_resolver_bbox_coverage_ratio": 0.3,
            "table_bbox_resolver_review_flags": [],
        },
    )

    assert selected["selected_morphology_scope"] == "table_region_crop"
    assert comparison["crop_vertical_line_gain"] == 3
    assert comparison["crop_intersection_gain"] == 8
    assert comparison["crop_selection_rejected_no_vertical_or_intersection_gain"] is False


def test_page_grid_stays_preferred_over_weaker_crop() -> None:
    page = _result(horizontal=10, vertical=8, intersections=40, signal="GRID", score=440.0)
    crop = _result(horizontal=5, vertical=1, intersections=0, signal="PARTIAL_GRID", score=9.0)
    selected, comparison = choose_region_or_page_morphology(
        page,
        crop,
        {"table_bbox_resolver_bbox_source": "explicit_table_bbox", "table_bbox_resolver_bbox_coverage_ratio": 0.4},
    )

    assert selected["selected_morphology_scope"] == "page"
    assert comparison["crop_selection_rejection_reason"] == "page_has_stronger_full_grid"
