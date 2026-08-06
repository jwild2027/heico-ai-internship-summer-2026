"""Quality helpers for TRACE-Net Table Structure BBox Localizer v1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from tiff.trace_net_table_structure_bbox_localizer_v1 import QUALITY_SCHEMA_VERSION, quality_checks, write_json


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evaluate_report(report: Mapping[str, Any], thresholds: Mapping[str, Any] | argparse.Namespace | None = None) -> dict[str, Any]:
    summary = report.get("summary", {}) if isinstance(report, Mapping) else {}
    status, checks = quality_checks(summary, thresholds)
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "status": status,
        "summary": summary,
        "checks": checks,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check TRACE-Net table structure bbox localizer v1 quality.")
    p.add_argument("--report-path", required=True)
    p.add_argument("--min-source-visual-records", type=int, default=1)
    p.add_argument("--min-structure-records", type=int, default=1)
    p.add_argument("--min-selected-bbox-records", type=int, default=1)
    p.add_argument("--min-visual-bbox-rejected-records", type=int, default=0)
    p.add_argument("--max-unsafe-records", type=int, default=0)
    p.add_argument("--max-answer-permission-count", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--require-table-visual-bbox-localizer-quality-pass", action="store_true")
    p.add_argument("--require-table-bbox-scoped-cell-extraction-quality-pass", action="store_true")
    p.add_argument("--require-all-records-selected-bbox-ready", action="store_true")
    p.add_argument("--write-json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report_path = Path(args.report_path)
    report = read_json(report_path)
    quality = evaluate_report(report, args)
    if args.write_json:
        out = report_path.with_name("trace_net_table_structure_bbox_localizer_v1_quality.json")
        write_json(out, quality)
    summary = quality.get("summary", {})
    print("TRACE-Net Table Structure BBox Localizer v1 quality")
    print(f" Status: {quality.get('status')}")
    for key in (
        "source_visual_record_count",
        "source_scoped_table_record_count",
        "structure_record_count",
        "structure_selected_bbox_record_count",
        "structure_visual_bbox_accepted_count",
        "structure_visual_bbox_rejected_count",
        "conservative_input_bbox_fallback_count",
        "visual_candidate_cuts_table_columns_count",
        "visual_candidate_cuts_table_rows_count",
        "visual_candidate_over_tightened_area_count",
        "visual_candidate_too_short_for_row_count",
        "split_column_visual_candidate_count",
        "split_column_visual_accepted_count",
        "unsafe_table_structure_bbox_localizer_record_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")
    return 0 if quality.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
