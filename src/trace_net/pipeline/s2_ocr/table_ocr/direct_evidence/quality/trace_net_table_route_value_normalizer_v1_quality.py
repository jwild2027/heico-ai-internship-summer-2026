"""Quality checks for TRACE-Net Table Route Value Normalizer v1."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from tiff.trace_net_table_route_value_normalizer_v1 import (
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
        "source_quality_pass": summary.get("source_table_route_cell_extractor_quality_status") == "PASS",
        "min_source_cell_extraction_records_met": summary.get("source_table_route_cell_extraction_record_count", 0) >= thresholds.get("min_source_cell_extraction_records", 1),
        "min_source_value_records_met": summary.get("source_table_value_record_count", 0) >= thresholds.get("min_source_value_records", 1),
        "min_normalizer_records_met": summary.get("table_route_value_normalizer_record_count", 0) >= thresholds.get("min_normalizer_records", 1),
        "min_normalized_records_met": summary.get("normalized_table_value_record_count", 0) >= thresholds.get("min_normalized_records", 1),
        "min_normalized_tables_met": summary.get("normalized_table_count", 0) >= thresholds.get("min_normalized_tables", 1),
        "min_covered_part_numbers_met": summary.get("covered_part_number_record_count", 0) >= thresholds.get("min_covered_part_number_records", 0),
        "min_manual_page_refs_met": summary.get("manual_page_reference_record_count", 0) >= thresholds.get("min_manual_page_reference_records", 0),
        "min_lep_row_derived_manual_page_refs_met": summary.get("lep_row_derived_manual_page_reference_record_count", 0) >= thresholds.get("min_lep_row_derived_manual_page_reference_records", 0),
        "lep_context_within_optional_max": thresholds.get("max_lep_context_records") is None or summary.get("lep_context_record_count", 0) <= thresholds.get("max_lep_context_records"),
        "min_ipl_part_numbers_met": summary.get("ipl_part_number_record_count", 0) >= thresholds.get("min_ipl_part_number_records", 0),
        "unsafe_records_within_limit": summary.get("unsafe_table_route_value_normalizer_record_count", 0) <= thresholds.get("max_unsafe_records", 0),
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
    parser = argparse.ArgumentParser(description="Check TRACE-Net table route value normalizer quality.")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-source-cell-extraction-records", type=int, default=1)
    parser.add_argument("--min-source-value-records", type=int, default=1)
    parser.add_argument("--min-normalizer-records", type=int, default=1)
    parser.add_argument("--min-normalized-records", type=int, default=1)
    parser.add_argument("--min-normalized-tables", type=int, default=1)
    parser.add_argument("--min-covered-part-number-records", type=int, default=0)
    parser.add_argument("--min-manual-page-reference-records", type=int, default=0)
    parser.add_argument("--min-lep-row-derived-manual-page-reference-records", type=int, default=0)
    parser.add_argument("--max-lep-context-records", type=int, default=None)
    parser.add_argument("--min-ipl-part-number-records", type=int, default=0)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-route-cell-extractor-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = read_json(args.report_path)
    thresholds = thresholds_from_args(args)
    payload = build_quality_payload(report, thresholds)
    if args.write_json:
        write_json(args.report_path.with_name("trace_net_table_route_value_normalizer_v1_quality.json"), payload)
    print("TRACE-Net Table Route Value Normalizer v1 quality")
    print(f" Status: {payload['quality_status']}")
    for key in (
        "source_table_route_cell_extraction_record_count",
        "source_table_value_record_count",
        "source_template_detected_table_count",
        "table_route_value_normalizer_record_count",
        "normalized_table_value_record_count",
        "normalized_table_count",
        "review_only_source_skipped_count",
        "covered_part_number_record_count",
        "manual_page_reference_record_count",
        "page_rev_or_sequence_value_record_count",
        "lep_context_record_count",
        "lep_context_suppressed_record_count",
        "lep_row_derived_manual_page_reference_record_count",
        "lep_row_derived_page_rev_or_sequence_value_record_count",
        "ipl_part_number_record_count",
        "ipl_figure_item_or_quantity_record_count",
        "ipl_text_record_count",
        "unsafe_table_route_value_normalizer_record_count",
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
