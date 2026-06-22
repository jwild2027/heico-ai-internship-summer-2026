"""Quality checks for TRACE-Net Table Route Value Audit v1."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from tiff.trace_net_table_route_value_audit_v1 import (
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
        "source_quality_pass": summary.get("source_table_route_value_normalizer_quality_status") == "PASS",
        "min_source_normalizer_records_met": summary.get("source_table_route_value_normalizer_record_count", 0) >= thresholds.get("min_source_normalizer_records", 1),
        "min_source_normalized_records_met": summary.get("source_normalized_table_value_record_count", 0) >= thresholds.get("min_source_normalized_records", 1),
        "min_audit_records_met": summary.get("table_route_value_audit_record_count", 0) >= thresholds.get("min_audit_records", 1),
        "min_audited_tables_met": summary.get("audited_table_count", 0) >= thresholds.get("min_audited_tables", 1),
        "min_promoted_evidence_records_met": summary.get("promoted_table_value_evidence_record_count", 0) >= thresholds.get("min_promoted_evidence_records", 1),
        "min_search_ready_evidence_records_met": summary.get("search_ready_evidence_record_count", 0) >= thresholds.get("min_search_ready_evidence_records", 1),
        "min_covered_part_number_promoted_met": summary.get("covered_part_number_promoted_count", 0) >= thresholds.get("min_covered_part_number_promoted", 0),
        "min_manual_page_reference_promoted_met": summary.get("manual_page_reference_promoted_count", 0) >= thresholds.get("min_manual_page_reference_promoted", 0),
        "min_ipl_part_number_promoted_met": summary.get("ipl_part_number_promoted_count", 0) >= thresholds.get("min_ipl_part_number_promoted", 0),
        "unsafe_records_within_limit": summary.get("unsafe_table_route_value_audit_record_count", 0) <= thresholds.get("max_unsafe_records", 0),
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
    parser = argparse.ArgumentParser(description="Check TRACE-Net table route value audit quality.")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-source-normalizer-records", type=int, default=1)
    parser.add_argument("--min-source-normalized-records", type=int, default=1)
    parser.add_argument("--min-audit-records", type=int, default=1)
    parser.add_argument("--min-audited-tables", type=int, default=1)
    parser.add_argument("--min-promoted-evidence-records", type=int, default=1)
    parser.add_argument("--min-search-ready-evidence-records", type=int, default=1)
    parser.add_argument("--min-covered-part-number-promoted", type=int, default=0)
    parser.add_argument("--min-manual-page-reference-promoted", type=int, default=0)
    parser.add_argument("--min-ipl-part-number-promoted", type=int, default=0)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-route-value-normalizer-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = read_json(args.report_path)
    thresholds = thresholds_from_args(args)
    payload = build_quality_payload(report, thresholds)
    if args.write_json:
        write_json(args.report_path.with_name("trace_net_table_route_value_audit_v1_quality.json"), payload)
    print("TRACE-Net Table Route Value Audit v1 quality")
    print(f" Status: {payload['quality_status']}")
    for key in (
        "source_table_route_value_normalizer_record_count",
        "source_normalized_table_value_record_count",
        "table_route_value_audit_record_count",
        "audited_table_count",
        "evidence_ready_table_count",
        "review_required_table_count",
        "unknown_template_review_count",
        "high_context_ratio_table_count",
        "promoted_table_value_evidence_record_count",
        "search_ready_evidence_record_count",
        "context_only_record_count",
        "covered_part_number_promoted_count",
        "manual_page_reference_promoted_count",
        "page_rev_or_sequence_value_promoted_count",
        "ipl_part_number_promoted_count",
        "ipl_figure_item_or_quantity_promoted_count",
        "ipl_text_promoted_count",
        "unsafe_table_route_value_audit_record_count",
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
