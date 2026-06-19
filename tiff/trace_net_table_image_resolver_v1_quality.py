"""Quality checker for TRACE-Net Table Image Resolver v1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from tiff.trace_net_table_image_resolver_v1 import (
    QUALITY_SCHEMA_VERSION,
    evaluate_checks,
    write_json,
)


def load_report(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def thresholds_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "min_source_cards": args.min_source_cards,
        "min_resolver_cards": args.min_resolver_cards,
        "min_resolved_image_cards": args.min_resolved_image_cards,
        "max_unsafe_resolution_cards": args.max_unsafe_resolution_cards,
        "max_answer_permission_count": args.max_answer_permission_count,
        "max_source_truth_mutation_allowed": args.max_source_truth_mutation_allowed,
        "require_table_line_geometry_quality_pass": args.require_table_line_geometry_quality_pass,
        "require_no_answer_permission": args.require_no_answer_permission,
    }


def check_report(report: Mapping[str, Any], thresholds: Mapping[str, Any]) -> Dict[str, Any]:
    summary = dict(report.get("summary") or {})
    checks, errors = evaluate_checks(summary, thresholds)
    qstatus = "PASS" if not errors else "FAIL"
    summary["quality_status"] = qstatus
    summary["quality_fail_reasons"] = errors
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "status": qstatus,
        "quality_status": qstatus,
        "summary": summary,
        "checks": checks,
        "quality_errors": errors,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Table Image Resolver v1 quality")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--min-source-cards", type=int, default=1)
    parser.add_argument("--min-resolver-cards", type=int, default=1)
    parser.add_argument("--min-resolved-image-cards", type=int, default=0)
    parser.add_argument("--max-unsafe-resolution-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-line-geometry-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def print_quality(payload: Mapping[str, Any]) -> None:
    summary = payload.get("summary") or {}
    print("TRACE-Net Table Image Resolver v1 quality")
    print(" Status:", payload.get("status"))
    for key in [
        "source_table_geometry_card_count",
        "resolver_card_count",
        "resolved_image_card_count",
        "unresolved_image_card_count",
        "scanned_image_file_count",
        "review_required_card_count",
        "unsafe_resolution_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}:", summary.get(key))
    if payload.get("quality_errors"):
        print(" quality_errors:", payload.get("quality_errors"))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = load_report(args.report_path)
    quality = check_report(report, thresholds_from_args(args))
    if args.write_json:
        output_path = args.report_path.with_name("trace_net_table_image_resolver_v1_quality.json")
        write_json(output_path, quality)
    print_quality(quality)
    return 0 if quality.get("quality_status") == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
