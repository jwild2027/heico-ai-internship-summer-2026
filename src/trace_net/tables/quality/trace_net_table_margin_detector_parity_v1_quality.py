"""Quality checker for TRACE-Net Table Margin Detector Parity v1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from tiff.trace_net_table_margin_detector_parity_v1 import SCHEMA_VERSION, Thresholds, as_int, quality_checks, quality_fail_reasons, write_json, utc_now_iso


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def thresholds_from_args(args: argparse.Namespace) -> Thresholds:
    return Thresholds(
        min_parity_cards=args.min_parity_cards,
        min_margin_candidate_evaluations=args.min_margin_candidate_evaluations,
        min_successful_image_cards=args.min_successful_image_cards,
        min_detector_disagreement_cards=args.min_detector_disagreement_cards,
        max_unsafe_parity_cards=args.max_unsafe_parity_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_table_line_geometry_quality_pass=args.require_table_line_geometry_quality_pass,
        require_table_bbox_resolver_quality_pass=args.require_table_bbox_resolver_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )


def build_quality_report(report: Mapping[str, Any], thresholds: Thresholds) -> Dict[str, Any]:
    checks = quality_checks(report, thresholds)
    fails = quality_fail_reasons(checks)
    status = "PASS" if not fails else "FAIL"
    summary = dict(report.get("summary") or {})
    summary["quality_status"] = status
    summary["quality_fail_reasons"] = fails
    return {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "generated_at": utc_now_iso(),
        "status": status,
        "quality_status": status,
        "summary": summary,
        "checks": checks,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net table margin detector parity quality")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--min-parity-cards", type=int, default=1)
    parser.add_argument("--min-margin-candidate-evaluations", type=int, default=1)
    parser.add_argument("--min-successful-image-cards", type=int, default=1)
    parser.add_argument("--min-detector-disagreement-cards", type=int, default=0)
    parser.add_argument("--max-unsafe-parity-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-line-geometry-quality-pass", action="store_true")
    parser.add_argument("--require-table-bbox-resolver-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = load_json(args.report_path)
    quality = build_quality_report(report, thresholds_from_args(args))
    if args.write_json:
        write_json(args.report_path.with_name("trace_net_table_margin_detector_parity_v1_quality.json"), quality)
    summary = quality.get("summary") or {}
    print("TRACE-Net Table Margin Detector Parity v1 quality")
    print(f" Status: {quality.get('status')}")
    for key in [
        "parity_card_count",
        "margin_candidate_evaluation_count",
        "successful_image_card_count",
        "production_detector_available_card_count",
        "estimator_detector_available_card_count",
        "detector_disagreement_card_count",
        "estimator_exceeds_production_card_count",
        "production_exceeds_estimator_card_count",
        "unsafe_parity_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    return 0 if quality.get("quality_status") == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
