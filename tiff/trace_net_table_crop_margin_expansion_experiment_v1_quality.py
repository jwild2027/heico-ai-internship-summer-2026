"""Quality checker for TRACE-Net Table Crop Margin Expansion Experiment v1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from tiff.trace_net_table_crop_margin_expansion_experiment_v1 import Thresholds, as_int, evaluate_checks, utc_now_iso, write_json


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def thresholds_from_args(args: argparse.Namespace) -> Thresholds:
    return Thresholds(
        min_diagnostic_cards=args.min_diagnostic_cards,
        min_margin_candidate_cards=args.min_margin_candidate_cards,
        min_successful_image_cards=args.min_successful_image_cards,
        max_unsafe_diagnostic_cards=args.max_unsafe_diagnostic_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_table_line_geometry_quality_pass=args.require_table_line_geometry_quality_pass,
        require_table_bbox_resolver_quality_pass=args.require_table_bbox_resolver_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net table crop margin expansion diagnostics quality.")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--min-diagnostic-cards", type=int, default=1)
    parser.add_argument("--min-margin-candidate-cards", type=int, default=1)
    parser.add_argument("--min-successful-image-cards", type=int, default=1)
    parser.add_argument("--max-unsafe-diagnostic-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-line-geometry-quality-pass", action="store_true")
    parser.add_argument("--require-table-bbox-resolver-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = load_json(args.report_path)
    summary = dict(report.get("summary") or {})
    checks = evaluate_checks(summary, thresholds_from_args(args))
    quality_status = "PASS" if all(checks.values()) else "FAIL"
    summary["quality_status"] = quality_status
    summary["quality_fail_reasons"] = [name for name, ok in checks.items() if not ok]

    payload = {
        "schema_version": "trace_net_table_crop_margin_expansion_experiment_v1_quality",
        "status": quality_status,
        "quality_status": quality_status,
        "generated_at": utc_now_iso(),
        "summary": summary,
        "checks": checks,
    }

    if args.write_json:
        quality_path = args.report_path.with_name("trace_net_table_crop_margin_expansion_experiment_v1_quality.json")
        write_json(quality_path, payload)

    print("TRACE-Net Table Crop Margin Expansion Experiment v1 quality")
    print(f" Status: {quality_status}")
    for key in [
        "diagnostic_card_count",
        "margin_candidate_card_count",
        "successful_image_card_count",
        "margin_improvement_card_count",
        "margin_selected_for_recommendation_card_count",
        "unsafe_diagnostic_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    return 0 if quality_status == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
