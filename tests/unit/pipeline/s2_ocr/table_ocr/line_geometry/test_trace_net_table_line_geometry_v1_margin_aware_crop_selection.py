from tiff.trace_net_table_line_geometry_v1 import (
    choose_region_or_page_morphology,
    expand_bbox_by_margin,
)


def test_expand_bbox_by_margin_keeps_origin_safe():
    expanded = expand_bbox_by_margin({"x0": 10, "y0": 5, "x1": 110, "y1": 55}, 25)
    assert expanded == {"x0": 0.0, "y0": 0.0, "x1": 135.0, "y1": 80.0}


def test_margin_expanded_crop_selected_when_grid_evidence_improves():
    page = {
        "horizontal_lines": [{"y0": 1, "y1": 1, "x0": 0, "x1": 100}],
        "vertical_lines": [],
        "intersection_count": 0,
        "morphology_signal_strength": "WEAK_LINE_SIGNAL",
        "morphology_quality_score": 1.0,
    }
    region = {
        "horizontal_lines": [{"y0": 1, "y1": 1, "x0": 0, "x1": 100}] * 8,
        "vertical_lines": [{"x0": 1, "x1": 1, "y0": 0, "y1": 100}] * 4,
        "intersection_count": 24,
        "morphology_signal_strength": "GRID",
        "morphology_quality_score": 260.0,
        "table_region_crop_applied": True,
        "crop_margin_pixels": 50,
        "margin_expansion_selected_candidate": True,
        "margin_expansion_candidate_count": 6,
        "margin_expansion_candidates": [{"margin_pixels": 50, "intersection_count": 24}],
    }

    selected, comparison = choose_region_or_page_morphology(page, region, {})

    assert selected["selected_morphology_scope"] == "table_region_crop"
    assert selected["margin_expansion_selected_for_crop_morphology"] is True
    assert selected["crop_margin_pixels"] == 50
    assert selected["margin_expansion_candidate_count"] == 6
    assert comparison["crop_vertical_line_gain"] == 4
    assert comparison["crop_intersection_gain"] == 24
    assert comparison["selected_crop_margin_pixels"] == 50


def test_margin_expanded_crop_rejected_without_vertical_or_intersection_gain():
    page = {
        "horizontal_lines": [{"y0": 1, "y1": 1, "x0": 0, "x1": 100}],
        "vertical_lines": [],
        "intersection_count": 0,
        "morphology_signal_strength": "WEAK_LINE_SIGNAL",
        "morphology_quality_score": 1.0,
    }
    region = {
        "horizontal_lines": [{"y0": 1, "y1": 1, "x0": 0, "x1": 100}] * 2,
        "vertical_lines": [],
        "intersection_count": 0,
        "morphology_signal_strength": "WEAK_LINE_SIGNAL",
        "morphology_quality_score": 2.0,
        "table_region_crop_applied": True,
        "crop_margin_pixels": 50,
        "margin_expansion_selected_candidate": True,
        "margin_expansion_candidate_count": 6,
    }

    selected, comparison = choose_region_or_page_morphology(page, region, {})

    assert selected["selected_morphology_scope"] == "page"
    assert selected["margin_expansion_selected_for_crop_morphology"] is False
    assert comparison["crop_selection_rejected_no_vertical_or_intersection_gain"] is True
    assert comparison["crop_selection_rejection_reason"] == "crop_did_not_improve_grid_evidence"
