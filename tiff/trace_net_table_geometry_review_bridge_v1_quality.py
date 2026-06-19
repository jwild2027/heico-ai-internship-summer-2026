"""Quality checker for TRACE-Net Table Geometry Review Bridge v1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from tiff.trace_net_table_geometry_review_bridge_v1 import (
    SCHEMA_VERSION,
    QualityThresholds,
    as_int,
    build_checks,
    quality_fail_reasons_for_summary,
    read_json,
    thresholds_from_args,
    write_json,
)


def check_report(report: Mapping[str, Any], thresholds: QualityThresholds) -> Dict[str, Any]:
    summary = dict(report.get("summary") or {})
    reasons = quality_fail_reasons_for_summary(summary, thresholds)
    quality_status = "PASS" if not reasons else "FAIL"
    checks = build_checks(summary, thresholds)
    return {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": quality_status,
        "quality_status": quality_status,
        "summary": summary,
        "checks": checks,
        "quality_errors": reasons,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net table geometry review bridge v1 quality")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--min-review-tasks", default=1, type=int)
    parser.add_argument("--min-source-cards", default=1, type=int)
    parser.add_argument("--max-unsafe-review-tasks", default=0, type=int)
    parser.add_argument("--max-unsafe-source-cards", default=0, type=int)
    parser.add_argument("--max-answer-permission-count", default=0, type=int)
    parser.add_argument("--max-source-truth-mutation-allowed", default=0, type=int)
    parser.add_argument("--require-source-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = read_json(args.report_path)
    quality = check_report(report, thresholds_from_args(args))
    if args.write_json:
        write_json(args.report_path.with_name("trace_net_table_geometry_review_bridge_v1_quality.json"), quality)
    summary = quality.get("summary") or {}
    print("TRACE-Net Table Geometry Review Bridge v1 quality")
    print(f" Status: {quality.get('quality_status')}")
    for key in (
        "source_table_geometry_card_count",
        "review_task_count",
        "review_required_task_count",
        "high_priority_task_count",
        "unsafe_source_card_count",
        "unsafe_review_task_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")
    return 0 if quality.get("quality_status") == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
