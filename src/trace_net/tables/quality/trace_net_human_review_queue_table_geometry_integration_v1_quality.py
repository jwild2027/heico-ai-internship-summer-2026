"""Quality checker for TRACE-Net Human Review Queue Table Geometry Integration v1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tiff.trace_net_human_review_queue_table_geometry_integration_v1 import compute_quality, utc_now, write_json


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Human Review Queue table geometry integration quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-review-tasks", type=int, default=1)
    parser.add_argument("--min-table-geometry-review-tasks", type=int, default=1)
    parser.add_argument("--require-table-geometry-bridge-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report_path = Path(args.report_path)
    report = read_json(report_path)
    quality = compute_quality(
        report,
        min_review_tasks=args.min_review_tasks,
        min_table_geometry_review_tasks=args.min_table_geometry_review_tasks,
        require_table_geometry_bridge_quality_pass=args.require_table_geometry_bridge_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    quality["generated_at"] = utc_now()
    report["quality_status"] = quality["quality_status"]
    if isinstance(report.get("summary"), dict):
        report["summary"]["quality_status"] = quality["quality_status"]
        report["summary"]["quality_fail_reasons"] = [key for key, passed in quality["checks"].items() if not passed]
        quality["summary"] = report["summary"]
    if args.write_json:
        write_json(report_path, report)
        write_json(report_path.with_name("trace_net_human_review_queue_v1_quality.json"), quality)
        write_json(report_path.with_name("trace_net_human_review_queue_table_geometry_integration_v1_quality.json"), quality)
    summary = quality.get("summary", {})
    print("TRACE-Net Human Review Queue Table Geometry Integration v1 quality")
    print(f" Status: {quality['quality_status']}")
    for key in [
        "review_task_count",
        "table_geometry_review_task_count",
        "table_geometry_high_priority_task_count",
        "unsafe_review_task_count",
        "answer_permission_count",
        "review_task_can_answer_directly_count",
        "review_task_can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    return 0 if quality["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
