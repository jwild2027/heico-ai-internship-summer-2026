from __future__ import annotations

from argparse import Namespace

from tiff.trace_net_table_structure_bbox_overlay_export_v1 import quality_errors


def args(**overrides):
    defaults = dict(
        require_table_structure_bbox_localizer_quality_pass=True,
        min_source_records=20,
        min_overlay_records=20,
        min_image_available_records=20,
        min_overlay_pngs=20,
        min_contact_sheets=1,
        max_unsafe_records=0,
        max_answer_permission_count=0,
        max_source_truth_mutation_allowed=0,
        require_no_answer_permission=True,
    )
    defaults.update(overrides)
    return Namespace(**defaults)


def test_quality_errors_pass_for_safe_overlay_summary() -> None:
    summary = {
        "source_table_structure_bbox_localizer_quality_status": "PASS",
        "source_record_count": 20,
        "overlay_record_count": 20,
        "image_available_record_count": 20,
        "overlay_png_written_count": 20,
        "contact_sheet_written_count": 1,
        "unsafe_table_structure_bbox_overlay_record_count": 0,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }
    assert quality_errors(summary, args()) == []


def test_quality_errors_fail_on_missing_overlays_and_unsafe_counts() -> None:
    summary = {
        "source_table_structure_bbox_localizer_quality_status": "FAIL",
        "source_record_count": 10,
        "overlay_record_count": 10,
        "image_available_record_count": 10,
        "overlay_png_written_count": 9,
        "contact_sheet_written_count": 0,
        "unsafe_table_structure_bbox_overlay_record_count": 1,
        "answer_permission_count": 1,
        "source_truth_mutation_allowed_count": 1,
        "postgres_write_attempt_count": 1,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }
    errors = quality_errors(summary, args())
    assert "source_table_structure_bbox_localizer_quality_status_not_pass" in errors
    assert "overlay_png_written_count_below_min" in errors
    assert "unsafe_table_structure_bbox_overlay_record_count_above_max" in errors
    assert "postgres_write_attempt_count_not_zero" in errors
