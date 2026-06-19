from __future__ import annotations

from pathlib import Path

from tiff.trace_net_table_line_geometry_v1 import (
    full_region_recovery_table_region_bbox,
    load_table_full_region_recovery_cards,
)


def test_load_table_full_region_recovery_cards(tmp_path: Path) -> None:
    path = tmp_path / "recovery.json"
    path.write_text(
        '{"quality_status":"PASS","recovery_cards":[{"page_id":"p1","table_id":"t1","crop_recovery_ready":true}]}',
        encoding="utf-8",
    )

    recovery_map, status = load_table_full_region_recovery_cards(path)

    assert status == "PASS"
    assert recovery_map[("p1", "t1")]["crop_recovery_ready"] is True


def test_full_region_recovery_bbox_used_when_ready_and_not_page_like() -> None:
    recovery_map = {
        ("p1", "t1"): {
            "page_id": "p1",
            "table_id": "t1",
            "crop_recovery_status": "FULL_TABLE_REGION_RECOVERY_READY",
            "crop_recovery_ready": True,
            "full_table_coverage_ratio": 0.72,
            "expanded_full_table_bbox": {"x0": 10, "y0": 20, "x1": 500, "y1": 700},
            "review_flags": ["full_table_region_recovery_ready_for_review"],
        }
    }

    bbox, metadata = full_region_recovery_table_region_bbox("p1", "t1", recovery_map)

    assert bbox == {"x0": 10.0, "y0": 20.0, "x1": 500.0, "y1": 700.0}
    assert metadata["table_full_region_recovery_used_for_crop"] is True
    assert metadata["table_full_region_recovery_crop_rejected"] is False


def test_full_region_recovery_bbox_rejected_when_too_page_like() -> None:
    recovery_map = {
        ("p1", "t1"): {
            "page_id": "p1",
            "table_id": "t1",
            "crop_recovery_status": "FULL_TABLE_REGION_RECOVERY_READY",
            "crop_recovery_ready": True,
            "full_table_coverage_ratio": 0.98,
            "expanded_full_table_bbox": {"x0": 0, "y0": 0, "x1": 3000, "y1": 4000},
            "review_flags": ["recovered_bbox_too_page_like"],
        }
    }

    bbox, metadata = full_region_recovery_table_region_bbox("p1", "t1", recovery_map)

    assert bbox is None
    assert metadata["table_full_region_recovery_crop_rejected"] is True
    assert metadata["table_full_region_recovery_rejection_reason"] == "expanded_full_table_bbox_too_page_like"

from tiff.trace_net_table_line_geometry_v1 import choose_region_or_page_morphology


def test_guard_allowed_overrides_advisory_blocked_flag_for_crop_selection() -> None:
    page = {
        "morphology_signal_strength": "GRID",
        "morphology_quality_score": 100.0,
        "horizontal_lines": [1, 2, 3, 4],
        "vertical_lines": [1, 2],
        "intersection_count": 10,
    }
    region = {
        "morphology_signal_strength": "GRID",
        "morphology_quality_score": 200.0,
        "horizontal_lines": [1, 2, 3, 4, 5],
        "vertical_lines": [1, 2, 3],
        "intersection_count": 20,
        "table_region_crop_applied": True,
        "margin_expansion_selected_candidate": False,
    }
    guard = {
        "crop_selection_allowed": True,
        # This may remain present as advisory context on older/review-heavy
        # guard cards; a positive allow decision must win for TLG selection.
        "crop_selection_blocked": True,
        "crop_completeness_status": "PASS",
        "review_flags": ["detector_disagreement_requires_overlay_review"],
    }

    selected, comparison = choose_region_or_page_morphology(page, region, crop_completeness_guard=guard)

    assert selected["selected_morphology_scope"] == "table_region_crop"
    assert selected["crop_completeness_guard_selection_allowed"] is True
    assert selected["crop_completeness_guard_selection_blocked"] is False
    assert selected["crop_selection_blocked_by_completeness_guard"] is False
    assert comparison["crop_selection_blocked_by_completeness_guard"] is False
