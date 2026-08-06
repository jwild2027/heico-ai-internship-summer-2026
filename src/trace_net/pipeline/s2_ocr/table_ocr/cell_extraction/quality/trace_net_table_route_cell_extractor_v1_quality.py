"""Quality checks for TRACE-Net Table Route Cell Extractor v1."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from tiff.trace_net_table_route_cell_extractor_v1 import (
    QUALITY_SCHEMA_VERSION,
    SCHEMA_VERSION,
    evaluate_quality,
    thresholds_from_args,
    write_json,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_quality_payload(report: Mapping[str, Any], thresholds: Mapping[str, Any]) -> dict[str, Any]:
    summary = report.get("summary") or {}
    quality_status, failures = evaluate_quality(summary, thresholds)
    checks = {
        "schema_version_ok": report.get("schema_version") == SCHEMA_VERSION,
        "min_source_table_bbox_records_met": summary.get("source_table_bbox_record_count", 0) >= thresholds.get("min_source_table_bbox_records", 1),
        "min_extraction_records_met": summary.get("table_route_cell_extraction_record_count", 0) >= thresholds.get("min_extraction_records", 1),
        "min_extraction_ready_tables_met": summary.get("extraction_ready_table_count", 0) >= thresholds.get("min_extraction_ready_tables", 1),
        "min_review_only_skipped_met": summary.get("review_only_skipped_count", 0) >= thresholds.get("min_review_only_skipped", 0),
        "min_cell_extraction_attempted_met": summary.get("cell_extraction_attempted_count", 0) >= thresholds.get("min_cell_extraction_attempted", 1),
        "min_cell_extraction_success_records_met": summary.get("cell_extraction_success_record_count", 0) >= thresholds.get("min_cell_extraction_success_records", 1),
        "min_row_records_met": summary.get("table_row_record_count", 0) >= thresholds.get("min_row_records", 1),
        "min_cell_records_met": summary.get("table_cell_record_count", 0) >= thresholds.get("min_cell_records", 1),
        "min_value_records_met": summary.get("table_value_record_count", 0) >= thresholds.get("min_value_records", 1),
        "min_part_number_candidates_met": summary.get("part_number_candidate_count", 0) >= thresholds.get("min_part_number_candidates", 0),
        "min_template_detected_tables_met": (thresholds.get("min_template_detected_tables") is None or summary.get("template_detected_table_count", 0) >= thresholds.get("min_template_detected_tables")),
        "min_part_number_coverage_template_tables_met": (thresholds.get("min_part_number_coverage_template_tables") is None or summary.get("part_number_coverage_template_count", 0) >= thresholds.get("min_part_number_coverage_template_tables")),
        "min_template_role_assigned_values_met": (thresholds.get("min_template_role_assigned_values") is None or summary.get("template_role_assigned_value_count", 0) >= thresholds.get("min_template_role_assigned_values")),
        "ocr_best_file_selection_active": summary.get("ocr_best_file_selected_table_count", 0) > 0,
        "token_level_raw_selected_min_met": (thresholds.get("min_token_level_raw_selected_tables") is None or summary.get("ocr_token_level_raw_file_selected_table_count", 0) >= thresholds.get("min_token_level_raw_selected_tables")),
        "line_raw_selected_max_met": (thresholds.get("max_line_raw_selected_tables") is None or summary.get("ocr_line_raw_file_selected_table_count", 0) <= thresholds.get("max_line_raw_selected_tables")),
        "unsafe_records_within_limit": summary.get("unsafe_table_route_cell_extraction_record_count", 0) <= thresholds.get("max_unsafe_records", 0),
        "answer_permission_within_limit": summary.get("answer_permission_count", 0) <= thresholds.get("max_answer_permission_count", 0),
        "source_truth_mutation_allowed_within_limit": summary.get("source_truth_mutation_allowed_count", 0) <= thresholds.get("max_source_truth_mutation_allowed", 0),
        "write_attempts_zero": summary.get("postgres_write_attempt_count", 0) == 0 and summary.get("qdrant_write_attempt_count", 0) == 0 and summary.get("opensearch_write_attempt_count", 0) == 0,
    }
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "status": quality_status,
        "quality_status": quality_status,
        "generated_at": utc_now(),
        "source_schema_version": report.get("schema_version"),
        "summary": summary,
        "checks": checks,
        "quality_fail_reasons": failures,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net table route cell extractor quality.")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-source-table-bbox-records", type=int, default=1)
    parser.add_argument("--min-extraction-records", type=int, default=1)
    parser.add_argument("--min-extraction-ready-tables", type=int, default=1)
    parser.add_argument("--min-review-only-skipped", type=int, default=0)
    parser.add_argument("--min-cell-extraction-attempted", type=int, default=1)
    parser.add_argument("--min-cell-extraction-success-records", type=int, default=1)
    parser.add_argument("--min-row-records", type=int, default=1)
    parser.add_argument("--min-cell-records", type=int, default=1)
    parser.add_argument("--min-value-records", type=int, default=1)
    parser.add_argument("--min-part-number-candidates", type=int, default=0)
    parser.add_argument("--min-template-detected-tables", type=int)
    parser.add_argument("--min-part-number-coverage-template-tables", type=int)
    parser.add_argument("--min-template-role-assigned-values", type=int)
    parser.add_argument("--max-ocr-selected-files-per-table-average", type=float)
    parser.add_argument("--min-token-level-raw-selected-tables", type=int)
    parser.add_argument("--max-line-raw-selected-tables", type=int)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-full-enclosure-bbox-reconstructor-quality-pass", action="store_true")
    parser.add_argument("--require-table-ocr-bbox-enrichment-quality-pass", action="store_true")
    parser.add_argument("--require-table-bbox-scoped-cell-extraction-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = read_json(args.report_path)
    thresholds = thresholds_from_args(args)
    payload = build_quality_payload(report, thresholds)
    if args.write_json:
        quality_path = args.report_path.with_name("trace_net_table_route_cell_extractor_v1_quality.json")
        write_json(quality_path, payload)
    print("TRACE-Net Table Route Cell Extractor v1 quality")
    print(f" Status: {payload['quality_status']}")
    for key in (
        "source_table_bbox_record_count",
        "table_route_cell_extraction_record_count",
        "extraction_ready_table_count",
        "review_only_skipped_count",
        "cell_extraction_attempted_count",
        "cell_extraction_success_record_count",
        "ocr_source_file_table_count",
        "ocr_candidate_file_count_total",
        "ocr_selected_file_count_total",
        "ocr_best_file_selected_table_count",
        "ocr_token_level_raw_file_selected_table_count",
        "ocr_line_raw_file_selected_table_count",
        "ocr_raw_token_count_before_dedup",
        "ocr_duplicate_token_removed_count",
        "ocr_token_table_count",
        "legacy_fallback_table_count",
        "table_row_record_count",
        "table_cell_record_count",
        "table_value_record_count",
        "header_cell_count",
        "part_number_candidate_count",
        "template_detected_table_count",
        "list_effective_pages_template_count",
        "part_number_coverage_template_count",
        "ipl_split_column_template_count",
        "generic_table_template_count",
        "template_role_assigned_value_count",
        "unsafe_table_route_cell_extraction_record_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {payload['summary'].get(key)}")
    return 0 if payload["quality_status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
