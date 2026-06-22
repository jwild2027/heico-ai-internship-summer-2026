from __future__ import annotations

import argparse

from tiff.trace_net_table_visual_bbox_localizer_v1 import quality_errors


def _args() -> argparse.Namespace:
    return argparse.Namespace(
        min_source_cards=20,
        min_localized_records=20,
        min_image_available_records=20,
        min_visual_refined_records=1,
        min_localization_ready_records=20,
        min_localization_quality_pass_records=0,
        max_unsafe_records=0,
        max_answer_permission_count=0,
        max_source_truth_mutation_allowed=0,
        require_table_ocr_bbox_enrichment_quality_pass=True,
        require_no_answer_permission=True,
    )


def test_quality_errors_pass_for_safe_visual_localizer_summary() -> None:
    summary = {
        "source_table_ocr_bbox_enrichment_quality_status": "PASS",
        "source_card_count": 20,
        "localized_record_count": 20,
        "image_available_record_count": 20,
        "visual_refined_bbox_record_count": 12,
        "table_localization_ready_record_count": 20,
        "table_localization_quality_pass_record_count": 8,
        "unsafe_table_visual_bbox_localizer_record_count": 0,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }

    assert quality_errors(summary, _args()) == []


def test_quality_errors_rejects_missing_visual_refinement_and_writes() -> None:
    summary = {
        "source_table_ocr_bbox_enrichment_quality_status": "PASS",
        "source_card_count": 20,
        "localized_record_count": 20,
        "image_available_record_count": 20,
        "visual_refined_bbox_record_count": 0,
        "table_localization_ready_record_count": 20,
        "unsafe_table_visual_bbox_localizer_record_count": 0,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 1,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }

    errors = quality_errors(summary, _args())

    assert "visual_refined_bbox_record_count_below_min" in errors
    assert "postgres_write_attempt_count_not_zero" in errors


def test_quality_errors_rejects_authority_leaks() -> None:
    summary = {
        "source_table_ocr_bbox_enrichment_quality_status": "PASS",
        "source_card_count": 20,
        "localized_record_count": 20,
        "image_available_record_count": 20,
        "visual_refined_bbox_record_count": 20,
        "table_localization_ready_record_count": 20,
        "unsafe_table_visual_bbox_localizer_record_count": 0,
        "answer_permission_count": 1,
        "source_truth_mutation_allowed_count": 1,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }

    errors = quality_errors(summary, _args())

    assert "answer_permission_count_above_max" in errors
    assert "answer_permission_count_not_zero" in errors
    assert "source_truth_mutation_allowed_count_above_max" in errors
