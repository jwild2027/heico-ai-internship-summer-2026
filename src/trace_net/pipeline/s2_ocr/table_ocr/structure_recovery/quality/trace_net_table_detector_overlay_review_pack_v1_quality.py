"""Quality checker for TRACE-Net Table Detector Overlay Review Pack v1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from tiff.trace_net_table_detector_overlay_review_pack_v1 import QUALITY_SCHEMA_VERSION, SCHEMA_VERSION, Thresholds, evaluate_quality, write_json


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net table detector overlay review pack v1 quality")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--min-review-cards", type=int, default=1)
    parser.add_argument("--min-overlay-ready-cards", type=int, default=1)
    parser.add_argument("--min-contact-sheets", type=int, default=0)
    parser.add_argument("--max-unsafe-review-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-overlay-audit-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-contact-sheet", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def thresholds_from_args(args: argparse.Namespace) -> Thresholds:
    return Thresholds(
        min_review_cards=args.min_review_cards,
        min_overlay_ready_cards=args.min_overlay_ready_cards,
        min_contact_sheets=args.min_contact_sheets,
        max_unsafe_review_cards=args.max_unsafe_review_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_overlay_audit_quality_pass=args.require_overlay_audit_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
        require_contact_sheet=args.require_contact_sheet,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = load_json(args.report_path)
    quality = evaluate_quality(report, thresholds_from_args(args))
    if args.write_json:
        quality_path = args.report_path.with_name("trace_net_table_detector_overlay_review_pack_v1_quality.json")
        write_json(quality_path, quality)
    summary = quality.get("summary") or {}
    print("TRACE-Net Table Detector Overlay Review Pack v1 quality")
    print(" Status:", quality.get("status"))
    for key in [
        "review_card_count",
        "overlay_ready_card_count",
        "contact_sheet_count",
        "detector_disagreement_card_count",
        "estimator_exceeds_production_card_count",
        "production_exceeds_estimator_card_count",
        "unsafe_review_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}:", summary.get(key))
    return 0 if quality.get("quality_status") == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
