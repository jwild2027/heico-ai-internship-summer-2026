"""Quality checker for TRACE-Net Table Line Geometry v1."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple, List

from tiff.trace_net_table_line_geometry_v1 import QUALITY_SCHEMA_VERSION, SCHEMA_VERSION, evaluate_quality, quality_checks, write_json


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def thresholds_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "min_table_geometry_cards": args.min_table_geometry_cards,
        "min_cell_records": args.min_cell_records,
        "min_row_records": args.min_row_records,
        "max_unsafe_geometry_cards": args.max_unsafe_geometry_cards,
        "max_answer_permission_count": args.max_answer_permission_count,
        "max_source_truth_mutation_allowed": args.max_source_truth_mutation_allowed,
        "require_no_answer_permission": args.require_no_answer_permission,
        "require_source_quality_pass": args.require_source_quality_pass,
        "require_image_line_detection": args.require_image_line_detection,
        "min_image_line_detection_cards": args.min_image_line_detection_cards,
        "require_table_image_resolver_quality_pass": args.require_table_image_resolver_quality_pass,
        "require_table_bbox_resolver_quality_pass": args.require_table_bbox_resolver_quality_pass,
        "require_table_crop_completeness_guard_quality_pass": args.require_table_crop_completeness_guard_quality_pass,
        "require_table_full_region_recovery_quality_pass": args.require_table_full_region_recovery_quality_pass,
        "min_table_full_region_recovery_used_for_crop_cards": args.min_table_full_region_recovery_used_for_crop_cards,
        "min_table_region_crop_available_cards": args.min_table_region_crop_available_cards,
        "min_table_region_crop_applied_cards": args.min_table_region_crop_applied_cards,
    }


def check_report(report_path: Path, thresholds: Mapping[str, Any], write_json_flag: bool = False) -> Dict[str, Any]:
    report = read_json(report_path)
    summary = dict(report.get("summary") or {})
    quality_status, fail_reasons = evaluate_quality(summary, thresholds)
    summary["quality_status"] = quality_status
    summary["quality_fail_reasons"] = fail_reasons
    payload = {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "status": quality_status,
        "quality_status": quality_status,
        "report_path": str(report_path),
        "summary": summary,
        "checks": quality_checks(summary),
        "quality_errors": fail_reasons,
    }
    if write_json_flag:
        write_json(report_path.with_name("trace_net_table_line_geometry_v1_quality.json"), payload)
    return payload


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Table Line Geometry v1 quality.")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--min-table-geometry-cards", type=int, default=1)
    parser.add_argument("--min-cell-records", type=int, default=0)
    parser.add_argument("--min-row-records", type=int, default=0)
    parser.add_argument("--min-image-line-detection-cards", type=int, default=0)
    parser.add_argument("--min-table-region-crop-available-cards", type=int, default=0)
    parser.add_argument("--min-table-region-crop-applied-cards", type=int, default=0)
    parser.add_argument("--min-table-full-region-recovery-used-for-crop-cards", type=int, default=0)
    parser.add_argument("--max-unsafe-geometry-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-table-image-resolver-quality-pass", action="store_true")
    parser.add_argument("--require-table-bbox-resolver-quality-pass", action="store_true")
    parser.add_argument("--require-table-crop-completeness-guard-quality-pass", action="store_true")
    parser.add_argument("--require-table-full-region-recovery-quality-pass", action="store_true")
    parser.add_argument("--require-image-line-detection", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    payload = check_report(args.report_path, thresholds_from_args(args), write_json_flag=args.write_json)
    summary = payload.get("summary") or {}
    print("TRACE-Net Table Line Geometry v1 quality")
    print(f" Status: {payload.get('quality_status')}")
    for key in (
        "table_geometry_card_count",
        "cell_record_count",
        "row_record_count",
        "image_line_detection_card_count",
        "image_morphology_card_count",
        "morphology_grid_card_count",
        "morphology_partial_grid_card_count",
        "morphology_weak_signal_card_count",
        "morphology_no_signal_card_count",
        "morphology_needs_calibration_card_count",
        "table_region_crop_available_card_count",
        "table_region_crop_applied_card_count",
        "table_region_crop_selected_card_count",
        "margin_expansion_candidate_card_count",
        "margin_expansion_candidate_evaluation_count",
        "margin_expansion_selected_card_count",
        "margin_expansion_selected_grid_card_count",
        "crop_completeness_guard_available_card_count",
        "crop_completeness_guard_selection_allowed_card_count",
        "crop_completeness_guard_selection_blocked_card_count",
        "crop_selection_blocked_by_completeness_guard_count",
        "crop_completeness_guard_review_required_card_count",
        "crop_completeness_guard_pass_card_count",
        "table_crop_completeness_guard_quality_status",
        "table_crop_completeness_guard_card_count",
        "table_full_region_recovery_quality_status",
        "table_full_region_recovery_card_count",
        "table_full_region_recovery_available_card_count",
        "table_full_region_recovery_ready_card_count",
        "table_full_region_recovery_used_for_crop_card_count",
        "table_full_region_recovery_crop_rejected_card_count",
        "table_full_region_recovery_too_page_like_card_count",
        "crop_selection_rejected_no_vertical_or_intersection_gain_count",
        "broad_crop_candidate_kept_page_morphology_count",
        "table_bbox_resolver_card_count",
        "table_bbox_resolver_quality_status",
        "table_bbox_resolver_crop_ready_card_count",
        "table_bbox_resolver_crop_used_card_count",
        "table_bbox_resolver_crop_rejected_card_count",
        "table_bbox_resolver_low_specificity_card_count",
        "page_morphology_selected_card_count",
        "resolved_image_input_card_count",
        "table_image_resolver_quality_status",
        "ocr_clustering_fallback_card_count",
        "merged_cell_candidate_count",
        "review_required_card_count",
        "unsafe_geometry_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")
    if payload.get("quality_errors"):
        print(" quality_errors:")
        for error in payload["quality_errors"]:
            print(f"  - {error}")
    return 1 if payload.get("quality_status") == "FAIL" else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
