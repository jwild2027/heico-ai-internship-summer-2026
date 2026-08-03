"""Quality checks for TRACE-Net Table Detector Overlay Verdict Ingest v1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

SCHEMA_VERSION = "trace_net_table_detector_overlay_verdict_ingest_v1_quality"
EXPECTED_REPORT_SCHEMA = "trace_net_table_detector_overlay_verdict_ingest_v1"


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return payload


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def build_quality_report(report_path: Path, thresholds: Mapping[str, int], require_overlay_review_pack_quality_pass: bool = False, require_no_answer_permission: bool = False) -> Dict[str, Any]:
    report = read_json(report_path)
    summary = dict(report.get("summary") or {})
    checks = {
        "schema_version_ok": report.get("schema_version") == EXPECTED_REPORT_SCHEMA,
        "min_review_cards_met": int(summary.get("review_card_count") or 0) >= int(thresholds.get("min_review_cards", 0)),
        "min_overlay_ready_cards_met": int(summary.get("overlay_ready_card_count") or 0) >= int(thresholds.get("min_overlay_ready_cards", 0)),
        "min_provided_verdict_cards_met": int(summary.get("provided_verdict_card_count") or 0) >= int(thresholds.get("min_provided_verdict_cards", 0)),
        "unsafe_verdict_cards_within_limit": int(summary.get("unsafe_verdict_card_count") or 0) <= int(thresholds.get("max_unsafe_verdict_cards", 0)),
        "answer_permission_within_limit": int(summary.get("answer_permission_count") or 0) <= int(thresholds.get("max_answer_permission_count", 0)),
        "source_truth_mutation_allowed_within_limit": int(summary.get("source_truth_mutation_allowed_count") or 0) <= int(thresholds.get("max_source_truth_mutation_allowed", 0)),
        "invalid_verdict_rows_zero": int(summary.get("invalid_verdict_row_count") or 0) == 0,
        "overlay_review_pack_quality_pass": summary.get("overlay_review_pack_quality_status") == "PASS",
        "no_answer_permission": int(summary.get("answer_permission_count") or 0) == 0,
    }
    if not require_overlay_review_pack_quality_pass:
        checks["overlay_review_pack_quality_pass"] = True
    if not require_no_answer_permission:
        checks["no_answer_permission"] = True

    fail_reasons: List[str] = [key for key, ok in checks.items() if not ok]
    status = "PASS" if not fail_reasons else "FAIL"
    quality = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "quality_status": status,
        "report_path": str(report_path),
        "summary": summary,
        "checks": checks,
        "quality_fail_reasons": fail_reasons,
    }
    quality_path = report_path.with_name("trace_net_table_detector_overlay_verdict_ingest_v1_quality.json")
    write_json(quality_path, quality)
    return quality


def print_quality(quality: Mapping[str, Any]) -> None:
    summary = quality.get("summary", {})
    print("TRACE-Net Table Detector Overlay Verdict Ingest v1 quality")
    print(f" Status: {quality.get('status')}")
    for key in [
        "review_card_count",
        "overlay_ready_card_count",
        "provided_verdict_card_count",
        "unreviewed_card_count",
        "real_table_rules_verdict_card_count",
        "text_or_noise_verdict_card_count",
        "mixed_or_unclear_verdict_card_count",
        "crop_selection_allowed_by_verdict_card_count",
        "crop_selection_blocked_by_verdict_card_count",
        "invalid_verdict_row_count",
        "unsafe_verdict_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--min-review-cards", type=int, default=1)
    parser.add_argument("--min-overlay-ready-cards", type=int, default=1)
    parser.add_argument("--min-provided-verdict-cards", type=int, default=0)
    parser.add_argument("--max-unsafe-verdict-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-overlay-review-pack-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    thresholds = {
        "min_review_cards": args.min_review_cards,
        "min_overlay_ready_cards": args.min_overlay_ready_cards,
        "min_provided_verdict_cards": args.min_provided_verdict_cards,
        "max_unsafe_verdict_cards": args.max_unsafe_verdict_cards,
        "max_answer_permission_count": args.max_answer_permission_count,
        "max_source_truth_mutation_allowed": args.max_source_truth_mutation_allowed,
    }
    quality = build_quality_report(
        args.report_path,
        thresholds,
        require_overlay_review_pack_quality_pass=args.require_overlay_review_pack_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    print_quality(quality)
    return 0 if quality.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
