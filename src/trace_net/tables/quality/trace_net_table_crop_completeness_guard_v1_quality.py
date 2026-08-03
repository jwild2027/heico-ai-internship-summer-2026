"""Quality checks for TRACE-Net Table Crop Completeness Guard v1."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "trace_net_table_crop_completeness_guard_v1_quality"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def build_quality_report(report: dict[str, Any], thresholds: dict[str, Any] | None = None) -> dict[str, Any]:
    thresholds = thresholds or {}
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    checks = {
        "schema_version_ok": report.get("schema_version") == "trace_net_table_crop_completeness_guard_v1",
        "min_completeness_cards_met": safe_int(summary.get("crop_completeness_card_count")) >= safe_int(thresholds.get("min_completeness_cards"), 0),
        "unsafe_completeness_cards_within_limit": safe_int(summary.get("unsafe_crop_completeness_card_count")) <= safe_int(thresholds.get("max_unsafe_completeness_cards"), 0),
        "answer_permission_within_limit": safe_int(summary.get("answer_permission_count")) <= safe_int(thresholds.get("max_answer_permission_count"), 0),
        "source_truth_mutation_allowed_within_limit": safe_int(summary.get("source_truth_mutation_allowed_count")) <= safe_int(thresholds.get("max_source_truth_mutation_allowed"), 0),
        "no_answer_permission": safe_int(summary.get("answer_permission_count")) == 0,
        "table_line_geometry_quality_pass": (not thresholds.get("require_table_line_geometry_quality_pass")) or summary.get("source_quality_statuses", {}).get("table_line_geometry") == "PASS",
        "table_bbox_resolver_quality_pass": (not thresholds.get("require_table_bbox_resolver_quality_pass")) or summary.get("source_quality_statuses", {}).get("table_bbox_resolver") == "PASS",
        "overlay_review_pack_quality_pass": (not thresholds.get("require_overlay_review_pack_quality_pass")) or summary.get("source_quality_statuses", {}).get("overlay_review_pack") == "PASS",
        "table_full_region_recovery_quality_pass": (not thresholds.get("require_table_full_region_recovery_quality_pass")) or summary.get("source_quality_statuses", {}).get("table_full_region_recovery") == "PASS",
        "min_full_region_recovery_gate_allowed_cards_met": safe_int(summary.get("full_region_recovery_gate_allowed_card_count")) >= safe_int(thresholds.get("min_full_region_recovery_gate_allowed_cards"), 0),
    }
    if thresholds.get("require_no_answer_permission"):
        checks["require_no_answer_permission"] = checks["no_answer_permission"]
    quality_fail_reasons = [key for key, ok in checks.items() if not ok]
    status = "PASS" if not quality_fail_reasons else "FAIL"
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "status": status,
        "quality_status": status,
        "checks": checks,
        "quality_fail_reasons": quality_fail_reasons,
        "summary": summary,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net table crop completeness guard v1 quality")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--min-completeness-cards", type=int, default=1)
    parser.add_argument("--max-unsafe-completeness-cards", type=int, default=0)
    parser.add_argument("--min-full-region-recovery-gate-allowed-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-line-geometry-quality-pass", action="store_true")
    parser.add_argument("--require-table-bbox-resolver-quality-pass", action="store_true")
    parser.add_argument("--require-overlay-review-pack-quality-pass", action="store_true")
    parser.add_argument("--require-table-full-region-recovery-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def thresholds_from_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "min_completeness_cards": args.min_completeness_cards,
        "max_unsafe_completeness_cards": args.max_unsafe_completeness_cards,
        "min_full_region_recovery_gate_allowed_cards": args.min_full_region_recovery_gate_allowed_cards,
        "max_answer_permission_count": args.max_answer_permission_count,
        "max_source_truth_mutation_allowed": args.max_source_truth_mutation_allowed,
        "require_table_line_geometry_quality_pass": args.require_table_line_geometry_quality_pass,
        "require_table_bbox_resolver_quality_pass": args.require_table_bbox_resolver_quality_pass,
        "require_overlay_review_pack_quality_pass": args.require_overlay_review_pack_quality_pass,
        "require_table_full_region_recovery_quality_pass": args.require_table_full_region_recovery_quality_pass,
        "require_no_answer_permission": args.require_no_answer_permission,
    }


def print_quality(quality: dict[str, Any]) -> None:
    summary = quality.get("summary", {})
    print("TRACE-Net Table Crop Completeness Guard v1 quality")
    print(f" Status: {quality.get('status')}")
    for key in (
        "crop_completeness_card_count",
        "crop_completeness_pass_card_count",
        "crop_completeness_review_required_card_count",
        "crop_completeness_fail_block_selection_card_count",
        "crop_selection_allowed_card_count",
        "crop_selection_blocked_card_count",
        "overlay_review_available_card_count",
        "overlay_unreviewed_card_count",
        "detector_disagreement_card_count",
        "detector_disagreement_without_safe_verdict_card_count",
        "table_full_region_recovery_available_card_count",
        "table_full_region_recovery_ready_card_count",
        "table_full_region_recovery_used_for_crop_card_count",
        "table_full_region_recovery_too_page_like_card_count",
        "full_region_recovery_gate_allowed_card_count",
        "crop_completeness_full_region_recovery_pass_card_count",
        "unsafe_crop_completeness_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = read_json(args.report_path)
    quality = build_quality_report(report, thresholds=thresholds_from_args(args))
    if args.write_json:
        write_json(args.report_path.with_name("trace_net_table_crop_completeness_guard_v1_quality.json"), quality)
    print_quality(quality)
    return 0 if quality.get("quality_status") == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
