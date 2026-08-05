"""Quality gates for TRACE-Net Coordinate Evidence Foundation v1."""
from __future__ import annotations

from typing import Any, Mapping

QUALITY_SCHEMA_VERSION = "trace_net_coordinate_evidence_v1_quality"


def evaluate_coordinate_evidence_quality(
    report: Mapping[str, Any],
    *,
    expected_pages: int,
    expected_nonblank_pages: int,
    expected_blank_pages: int,
) -> dict[str, Any]:
    summary = report.get("summary") or {}
    checks = {
        "selected_pages_exact": int(summary.get("selected_page_count") or 0) == expected_pages,
        "source_hashes_all_present": int(summary.get("source_hash_present_count") or 0) == expected_pages,
        "routing_frozen_all_pages": (
            int(summary.get("route_preserved_count") or 0) == expected_pages
            and int(summary.get("route_mutation_count") or 0) == 0
        ),
        "nonblank_word_boxes_all_pages": (
            int(summary.get("nonblank_page_count") or 0) == expected_nonblank_pages
            and int(summary.get("nonblank_page_with_word_boxes_count") or 0) == expected_nonblank_pages
        ),
        "blank_pages_exact": int(summary.get("blank_page_count") or 0) == expected_blank_pages,
        "blank_pages_no_invented_words": int(summary.get("blank_page_with_word_boxes_count") or 0) == 0,
        "all_coordinates_inside_page": int(summary.get("invalid_coordinate_count") or 0) == 0,
        "table_pages_have_coordinate_rows": (
            int(summary.get("table_page_count") or 0) > 0
            and int(summary.get("table_page_with_row_candidate_count") or 0)
            == int(summary.get("table_page_count") or 0)
        ),
        "table_rows_have_coordinates": int(summary.get("table_row_missing_coordinate_count") or 0) == 0,
        "table_rows_do_not_prove_claims": int(summary.get("table_row_claim_proof_count") or 0) == 0,
        "visual_pages_have_psm11_boxes": (
            int(summary.get("visual_page_count") or 0) > 0
            and int(summary.get("visual_page_with_psm11_word_boxes_count") or 0)
            == int(summary.get("visual_page_count") or 0)
        ),
        "callouts_only_on_visual_routes": int(summary.get("callout_on_nonvisual_route_count") or 0) == 0,
        "callout_bboxes_complete": int(summary.get("callout_missing_bbox_count") or 0) == 0,
        "callouts_unconfirmed": int(summary.get("callout_confirmed_count") or 0) == 0,
        "callouts_not_source_truth": int(summary.get("callout_source_truth_count") or 0) == 0,
        "normal_text_pages_have_blocks": (
            int(summary.get("normal_text_page_count") or 0) > 0
            and int(summary.get("normal_text_page_with_block_count") or 0)
            == int(summary.get("normal_text_page_count") or 0)
        ),
        "answer_permission_zero": int(summary.get("answer_permission_count") or 0) == 0,
        "can_prove_claims_zero": int(summary.get("can_prove_claims_count") or 0) == 0,
        "source_truth_mutation_zero": int(summary.get("source_truth_mutation_allowed_count") or 0) == 0,
        "postgres_writes_zero": int(summary.get("postgres_write_attempt_count") or 0) == 0,
        "qdrant_writes_zero": int(summary.get("qdrant_write_attempt_count") or 0) == 0,
        "opensearch_writes_zero": int(summary.get("opensearch_write_attempt_count") or 0) == 0,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "quality_status": "PASS" if not failures else "FAIL",
        "checks": checks,
        "failures": failures,
        "summary": dict(summary),
        "expected": {
            "page_count": expected_pages,
            "nonblank_page_count": expected_nonblank_pages,
            "blank_page_count": expected_blank_pages,
        },
    }
