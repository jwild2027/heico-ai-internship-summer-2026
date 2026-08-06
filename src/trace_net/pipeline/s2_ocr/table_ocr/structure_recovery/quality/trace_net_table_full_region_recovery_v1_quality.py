"""Quality checker for TRACE-Net Table Full Region Recovery v1."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from tiff.trace_net_table_full_region_recovery_v1 import (
    QUALITY_SCHEMA_VERSION,
    SCHEMA_VERSION,
    build_quality_payload,
    evaluate_quality,
    read_json,
    write_json,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def thresholds_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "min_recovery_cards": args.min_recovery_cards,
        "min_expanded_full_table_bbox_cards": args.min_expanded_full_table_bbox_cards,
        "min_ocr_content_bbox_cards": args.min_ocr_content_bbox_cards,
        "max_unsafe_recovery_cards": args.max_unsafe_recovery_cards,
        "max_answer_permission_count": args.max_answer_permission_count,
        "max_source_truth_mutation_allowed": args.max_source_truth_mutation_allowed,
        "require_table_bbox_resolver_quality_pass": args.require_table_bbox_resolver_quality_pass,
        "require_table_ocr_bbox_enrichment_quality_pass": args.require_table_ocr_bbox_enrichment_quality_pass,
        "require_no_answer_permission": args.require_no_answer_permission,
    }


def print_quality(payload: Mapping[str, Any]) -> None:
    summary = payload.get("summary") or {}
    print("TRACE-Net Table Full Region Recovery v1 quality")
    print(f" Status: {payload.get('status')}")
    for key in (
        "recovery_card_count",
        "crop_recovery_ready_card_count",
        "crop_recovery_review_required_card_count",
        "expanded_full_table_bbox_card_count",
        "ocr_content_bbox_card_count",
        "line_projection_bbox_card_count",
        "part_number_coverage_ok_card_count",
        "detector_disagreement_card_count",
        "overlay_unreviewed_card_count",
        "recovered_bbox_too_page_like_card_count",
        "unsafe_recovery_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Table Full Region Recovery v1 quality.")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--min-recovery-cards", type=int, default=1)
    parser.add_argument("--min-expanded-full-table-bbox-cards", type=int, default=1)
    parser.add_argument("--min-ocr-content-bbox-cards", type=int, default=1)
    parser.add_argument("--max-unsafe-recovery-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-bbox-resolver-quality-pass", action="store_true")
    parser.add_argument("--require-table-ocr-bbox-enrichment-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = read_json(args.report_path)
    thresholds = thresholds_from_args(args)
    payload = build_quality_payload(report, thresholds)
    if args.write_json:
        quality_path = args.report_path.with_name("trace_net_table_full_region_recovery_v1_quality.json")
        write_json(quality_path, payload)
    print_quality(payload)
    return 0 if payload.get("quality_status") == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
