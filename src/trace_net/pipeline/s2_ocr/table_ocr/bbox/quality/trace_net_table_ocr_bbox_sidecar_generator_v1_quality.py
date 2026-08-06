"""Quality checks for TRACE-Net Table OCR BBox Sidecar Generator v1.

This module is intentionally stdlib-only. It validates generated OCR bbox sidecar
reports without performing OCR, mutating source truth, or writing to stores.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping

SCHEMA_VERSION = "trace_net_table_ocr_bbox_sidecar_generator_v1_quality"
EXPECTED_REPORT_SCHEMA = "trace_net_table_ocr_bbox_sidecar_generator_v1"


@dataclass(frozen=True)
class SidecarQualityThresholds:
    min_source_cards: int = 1
    min_attempted_pages: int = 1
    min_generated_sidecar_pages: int = 1
    min_ocr_word_records: int = 1
    min_part_number_matches: int = 0
    max_tesseract_error_count: int | None = None
    max_unsafe_sidecar_cards: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_table_image_resolver_quality_pass: bool = False
    require_no_answer_permission: bool = False
    require_tesseract_available: bool = False


def _summary(report: Mapping[str, Any]) -> Mapping[str, Any]:
    summary = report.get("summary")
    return summary if isinstance(summary, Mapping) else {}


def _count(summary: Mapping[str, Any], key: str) -> int:
    value = summary.get(key, 0)
    try:
        return int(value or 0)
    except Exception:
        return 0


def evaluate_sidecar_generator_quality(
    report: Mapping[str, Any],
    thresholds: SidecarQualityThresholds | None = None,
) -> Dict[str, Any]:
    """Return a PASS/FAIL quality payload for a sidecar generator report."""
    thresholds = thresholds or SidecarQualityThresholds()
    summary = _summary(report)

    checks: Dict[str, bool] = {
        "schema_version_ok": report.get("schema_version") == EXPECTED_REPORT_SCHEMA,
        "source_cards_min_met": _count(summary, "source_table_image_card_count") >= thresholds.min_source_cards,
        "attempted_pages_min_met": _count(summary, "attempted_page_count") >= thresholds.min_attempted_pages,
        "generated_sidecar_pages_min_met": _count(summary, "generated_sidecar_page_count") >= thresholds.min_generated_sidecar_pages,
        "ocr_word_records_min_met": _count(summary, "ocr_word_record_count") >= thresholds.min_ocr_word_records,
        "part_number_matches_min_met": _count(summary, "part_number_match_count") >= thresholds.min_part_number_matches,
        "unsafe_sidecar_cards_within_limit": _count(summary, "unsafe_sidecar_card_count") <= thresholds.max_unsafe_sidecar_cards,
        "answer_permission_within_limit": _count(summary, "answer_permission_count") <= thresholds.max_answer_permission_count,
        "source_truth_mutation_within_limit": _count(summary, "source_truth_mutation_allowed_count") <= thresholds.max_source_truth_mutation_allowed,
        "postgres_write_attempts_zero": _count(summary, "postgres_write_attempt_count") == 0,
        "qdrant_write_attempts_zero": _count(summary, "qdrant_write_attempt_count") == 0,
        "opensearch_write_attempts_zero": _count(summary, "opensearch_write_attempt_count") == 0,
    }

    if thresholds.max_tesseract_error_count is not None:
        checks["tesseract_errors_within_limit"] = _count(summary, "tesseract_error_count") <= thresholds.max_tesseract_error_count

    if thresholds.require_table_image_resolver_quality_pass:
        checks["table_image_resolver_quality_pass"] = summary.get("table_image_resolver_quality_status") == "PASS"

    if thresholds.require_no_answer_permission:
        checks["answer_permission_zero"] = _count(summary, "answer_permission_count") == 0
        checks["can_answer_directly_zero"] = _count(summary, "can_answer_directly_count") == 0
        checks["can_prove_claims_zero"] = _count(summary, "can_prove_claims_count") == 0
        checks["retrieval_only_answer_allowed_zero"] = _count(summary, "retrieval_only_answer_allowed_count") == 0

    if thresholds.require_tesseract_available:
        checks["tesseract_available"] = bool(summary.get("tesseract_available"))

    fail_reasons = [name for name, ok in checks.items() if not ok]
    quality_status = "PASS" if not fail_reasons else "FAIL"

    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": quality_status,
        "quality_status": quality_status,
        "checks": checks,
        "summary": dict(summary),
        "quality_fail_reasons": fail_reasons,
    }
    return payload


def thresholds_from_args(args: argparse.Namespace) -> SidecarQualityThresholds:
    return SidecarQualityThresholds(
        min_source_cards=args.min_source_cards,
        min_attempted_pages=args.min_attempted_pages,
        min_generated_sidecar_pages=args.min_generated_sidecar_pages,
        min_ocr_word_records=args.min_ocr_word_records,
        min_part_number_matches=args.min_part_number_matches,
        max_tesseract_error_count=args.max_tesseract_error_count,
        max_unsafe_sidecar_cards=args.max_unsafe_sidecar_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_table_image_resolver_quality_pass=args.require_table_image_resolver_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
        require_tesseract_available=args.require_tesseract_available,
    )


def _add_quality_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-source-cards", type=int, default=1)
    parser.add_argument("--min-attempted-pages", type=int, default=1)
    parser.add_argument("--min-generated-sidecar-pages", type=int, default=1)
    parser.add_argument("--min-ocr-word-records", type=int, default=1)
    parser.add_argument("--min-part-number-matches", type=int, default=0)
    parser.add_argument("--max-tesseract-error-count", type=int, default=None)
    parser.add_argument("--max-unsafe-sidecar-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-image-resolver-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-tesseract-available", action="store_true")
    parser.add_argument("--write-json", action="store_true")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Table OCR BBox Sidecar Generator v1 quality.")
    _add_quality_args(parser)
    args = parser.parse_args(argv)

    report_path = Path(args.report_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    quality = evaluate_sidecar_generator_quality(report, thresholds_from_args(args))

    if args.write_json:
        quality_path = report_path.with_name("trace_net_table_ocr_bbox_sidecar_generator_v1_quality.json")
        quality_path.write_text(json.dumps(quality, indent=2, sort_keys=True), encoding="utf-8")

    summary = quality.get("summary", {})
    print("TRACE-Net Table OCR BBox Sidecar Generator v1 quality")
    print(f" Status: {quality['quality_status']}")
    for key in [
        "source_table_image_card_count",
        "attempted_page_count",
        "generated_sidecar_page_count",
        "tsv_sidecar_count",
        "jsonl_sidecar_count",
        "ocr_word_record_count",
        "ocr_line_record_count",
        "part_number_match_count",
        "table_candidate_bbox_count",
        "tesseract_error_count",
        "unsafe_sidecar_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key, 0)}")

    return 0 if quality["quality_status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
