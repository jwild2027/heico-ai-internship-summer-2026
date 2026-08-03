"""Quality checker for TRACE-Net Table Crop Selection Diagnostics v1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from tiff.trace_net_table_crop_selection_diagnostics_v1 import QUALITY_SCHEMA_VERSION, SCHEMA_VERSION, build_quality_payload, write_json


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return payload


def check_report(report: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    summary = dict(report.get("summary") or {})
    fail_reasons = list(summary.get("quality_fail_reasons") or [])

    if report.get("schema_version") != SCHEMA_VERSION:
        fail_reasons.append("schema_version_invalid")
    if summary.get("diagnostic_card_count", 0) < args.min_diagnostic_cards:
        fail_reasons.append("min_diagnostic_cards_not_met")
    if summary.get("crop_selected_card_count", 0) < args.min_crop_selected_cards:
        fail_reasons.append("min_crop_selected_cards_not_met")
    if summary.get("page_selected_card_count", 0) < args.min_page_selected_cards:
        fail_reasons.append("min_page_selected_cards_not_met")
    if summary.get("unsafe_diagnostic_card_count", 0) > args.max_unsafe_diagnostic_cards:
        fail_reasons.append("max_unsafe_diagnostic_cards_exceeded")
    if summary.get("answer_permission_count", 0) > args.max_answer_permission_count:
        fail_reasons.append("max_answer_permission_count_exceeded")
    if summary.get("source_truth_mutation_allowed_count", 0) > args.max_source_truth_mutation_allowed:
        fail_reasons.append("max_source_truth_mutation_allowed_exceeded")
    if args.require_table_line_geometry_quality_pass and summary.get("table_line_geometry_quality_status") != "PASS":
        fail_reasons.append("table_line_geometry_quality_not_pass")
    if args.require_table_bbox_resolver_quality_pass and summary.get("table_bbox_resolver_quality_status") != "PASS":
        fail_reasons.append("table_bbox_resolver_quality_not_pass")
    if args.require_table_ocr_bbox_enrichment_quality_pass and summary.get("table_ocr_bbox_enrichment_quality_status") != "PASS":
        fail_reasons.append("table_ocr_bbox_enrichment_quality_not_pass")
    if args.require_no_answer_permission and summary.get("answer_permission_count", 0) != 0:
        fail_reasons.append("answer_permission_present")

    fail_reasons = sorted(set(str(r) for r in fail_reasons))
    summary["quality_fail_reasons"] = fail_reasons
    summary["quality_status"] = "PASS" if not fail_reasons else "FAIL"
    report = dict(report)
    report["summary"] = summary
    report["quality_status"] = summary["quality_status"]
    report["status"] = "TABLE_CROP_SELECTION_DIAGNOSTICS_BUILT" if not fail_reasons else "TABLE_CROP_SELECTION_DIAGNOSTICS_NOT_READY"
    quality_payload = build_quality_payload(report)
    if fail_reasons:
        quality_payload["status"] = "FAIL"
        quality_payload["quality_status"] = "FAIL"
        quality_payload["summary"] = summary
    return quality_payload


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net table crop selection diagnostics v1 quality")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--min-diagnostic-cards", type=int, default=1)
    parser.add_argument("--min-crop-selected-cards", type=int, default=0)
    parser.add_argument("--min-page-selected-cards", type=int, default=0)
    parser.add_argument("--max-unsafe-diagnostic-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-line-geometry-quality-pass", action="store_true")
    parser.add_argument("--require-table-bbox-resolver-quality-pass", action="store_true")
    parser.add_argument("--require-table-ocr-bbox-enrichment-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)

    report = read_json(args.report_path)
    quality_payload = check_report(report, args)
    if args.write_json:
        write_json(args.report_path.with_name("trace_net_table_crop_selection_diagnostics_v1_quality.json"), quality_payload)

    s = quality_payload.get("summary", {})
    print("TRACE-Net Table Crop Selection Diagnostics v1 quality")
    print(f" Status: {quality_payload.get('status')}")
    for key in [
        "diagnostic_card_count", "crop_selected_card_count", "page_selected_card_count",
        "crop_available_card_count", "crop_applied_card_count", "crop_selected_but_weak_card_count",
        "page_selected_grid_card_count", "broad_bbox_candidate_card_count", "review_required_card_count",
        "unsafe_diagnostic_card_count", "answer_permission_count", "can_answer_directly_count",
        "can_prove_claims_count", "source_truth_mutation_allowed_count", "postgres_write_attempt_count",
        "qdrant_write_attempt_count", "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {s.get(key)}")
    return 0 if quality_payload.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
