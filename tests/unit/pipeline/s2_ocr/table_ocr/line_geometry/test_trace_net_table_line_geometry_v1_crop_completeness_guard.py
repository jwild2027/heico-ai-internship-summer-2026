from __future__ import annotations

from tiff.trace_net_table_line_geometry_v1 import (
    choose_region_or_page_morphology,
    load_table_crop_completeness_guard_cards,
)


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


def test_crop_completeness_guard_blocks_otherwise_winning_crop() -> None:
    page = _result(horizontal=1, vertical=0, intersections=0, signal="WEAK_LINE_SIGNAL", score=1.0)
    crop = _result(horizontal=10, vertical=7, intersections=42, signal="GRID", score=462.0)

    selected, comparison = choose_region_or_page_morphology(
        page,
        crop,
        {"table_bbox_resolver_bbox_source": "explicit_table_bbox", "table_bbox_resolver_bbox_coverage_ratio": 0.4},
        {
            "crop_completeness_status": "REVIEW_REQUIRED",
            "crop_selection_allowed": False,
            "crop_selection_blocked": True,
            "human_review_verdict": "UNREVIEWED",
            "review_flags": ["detector_disagreement_without_human_verdict"],
            "recommended_actions": ["label_detector_overlay_before_relaxing_crop_selection"],
        },
    )

    assert selected["selected_morphology_scope"] == "page"
    assert selected["crop_selection_blocked_by_completeness_guard"] is True
    assert selected["crop_completeness_guard_selection_blocked"] is True
    assert selected["crop_completeness_status"] == "REVIEW_REQUIRED"
    assert comparison["crop_selection_rejection_reason"] == "crop_selection_blocked_by_completeness_guard"
    assert comparison["crop_completeness_guard_review_flags"] == ["detector_disagreement_without_human_verdict"]


def test_crop_completeness_guard_allows_winning_crop_when_safe() -> None:
    page = _result(horizontal=1, vertical=0, intersections=0, signal="WEAK_LINE_SIGNAL", score=1.0)
    crop = _result(horizontal=10, vertical=7, intersections=42, signal="GRID", score=462.0)

    selected, comparison = choose_region_or_page_morphology(
        page,
        crop,
        {"table_bbox_resolver_bbox_source": "explicit_table_bbox", "table_bbox_resolver_bbox_coverage_ratio": 0.4},
        {
            "crop_completeness_status": "PASS",
            "crop_selection_allowed": True,
            "crop_selection_blocked": False,
            "human_review_verdict": "ESTIMATOR_LINES_REAL_TABLE_RULES",
        },
    )

    assert selected["selected_morphology_scope"] == "table_region_crop"
    assert selected["crop_selection_blocked_by_completeness_guard"] is False
    assert comparison["crop_vertical_line_gain"] == 7
    assert comparison["crop_intersection_gain"] == 42


def test_load_table_crop_completeness_guard_cards(tmp_path) -> None:
    path = tmp_path / "guard.json"
    path.write_text(
        '{"quality_status":"PASS","crop_completeness_cards":[{"page_id":"p1","table_id":"t1","crop_selection_blocked":true}]}',
        encoding="utf-8",
    )

    guard_map, status = load_table_crop_completeness_guard_cards(path)

    assert status == "PASS"
    assert guard_map[("p1", "t1")]["crop_selection_blocked"] is True
