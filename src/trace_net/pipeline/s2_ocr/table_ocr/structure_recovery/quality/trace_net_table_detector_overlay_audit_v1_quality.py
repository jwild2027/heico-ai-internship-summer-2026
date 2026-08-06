"""Quality checker for TRACE-Net Table Detector Overlay Audit v1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tiff.trace_net_table_detector_overlay_audit_v1 import (
    QUALITY_SCHEMA_VERSION,
    SCHEMA_VERSION,
    Thresholds,
    evaluate_quality,
    safe_int,
    utc_now,
    write_json,
)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return payload


def summary_from_report(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary")
    if isinstance(summary, dict):
        return dict(summary)
    cards = report.get("audit_cards") or []
    if not isinstance(cards, list):
        cards = []

    def count(field: str) -> int:
        return sum(1 for c in cards if isinstance(c, dict) and c.get(field))

    return {
        "schema_version": report.get("schema_version"),
        "audit_card_count": len(cards),
        "detector_disagreement_card_count": count("detector_disagreement"),
        "estimator_exceeds_production_card_count": count("estimator_exceeds_production"),
        "production_exceeds_estimator_card_count": count("production_exceeds_estimator"),
        "overlay_ready_card_count": count("overlay_ready"),
        "line_overlay_candidate_card_count": sum(
            1
            for c in cards
            if isinstance(c, dict)
            and (
                safe_int(c.get("overlay_projection_horizontal_count")) > 0
                or safe_int(c.get("overlay_projection_vertical_count")) > 0
            )
        ),
        "unsafe_audit_card_count": count("unsafe_audit_card"),
        "answer_permission_count": count("answer_permission"),
        "can_answer_directly_count": count("can_answer_directly"),
        "can_prove_claims_count": count("can_prove_claims"),
        "source_truth_mutation_allowed_count": count("source_truth_mutation_allowed"),
        "postgres_write_attempt_count": sum(safe_int(c.get("postgres_write_attempt_count")) for c in cards if isinstance(c, dict)),
        "qdrant_write_attempt_count": sum(safe_int(c.get("qdrant_write_attempt_count")) for c in cards if isinstance(c, dict)),
        "opensearch_write_attempt_count": sum(safe_int(c.get("opensearch_write_attempt_count")) for c in cards if isinstance(c, dict)),
        "source_quality_statuses": {},
    }


def build_quality_payload(report_path: Path, thresholds: Thresholds) -> dict[str, Any]:
    report = read_json(report_path)
    summary = summary_from_report(report)
    if summary.get("schema_version") is None:
        summary["schema_version"] = report.get("schema_version")
    quality_status, fail_reasons, checks = evaluate_quality(summary, thresholds)
    summary["quality_status"] = quality_status
    summary["status"] = "PASS" if quality_status == "PASS" else "TABLE_DETECTOR_OVERLAY_AUDIT_NOT_READY"
    summary["quality_fail_reasons"] = fail_reasons
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "status": quality_status,
        "quality_status": quality_status,
        "generated_at": utc_now(),
        "report_path": str(report_path),
        "summary": summary,
        "checks": checks,
        "quality_fail_reasons": fail_reasons,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net table detector overlay audit v1 quality")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--min-audit-cards", default=1, type=int)
    parser.add_argument("--min-detector-disagreement-cards", default=0, type=int)
    parser.add_argument("--min-overlay-ready-cards", default=0, type=int)
    parser.add_argument("--max-unsafe-audit-cards", default=0, type=int)
    parser.add_argument("--max-answer-permission-count", default=0, type=int)
    parser.add_argument("--max-source-truth-mutation-allowed", default=0, type=int)
    parser.add_argument("--require-margin-detector-parity-quality-pass", action="store_true")
    parser.add_argument("--require-table-bbox-resolver-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def thresholds_from_args(args: argparse.Namespace) -> Thresholds:
    return Thresholds(
        min_audit_cards=args.min_audit_cards,
        min_detector_disagreement_cards=args.min_detector_disagreement_cards,
        min_overlay_ready_cards=args.min_overlay_ready_cards,
        max_unsafe_audit_cards=args.max_unsafe_audit_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_margin_detector_parity_quality_pass=args.require_margin_detector_parity_quality_pass,
        require_table_bbox_resolver_quality_pass=args.require_table_bbox_resolver_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )


def print_quality(payload: dict[str, Any]) -> None:
    summary = payload.get("summary", {})
    print("TRACE-Net Table Detector Overlay Audit v1 quality")
    print(f" Status: {payload.get('quality_status')}")
    for key in [
        "audit_card_count",
        "detector_disagreement_card_count",
        "estimator_exceeds_production_card_count",
        "production_exceeds_estimator_card_count",
        "overlay_ready_card_count",
        "line_overlay_candidate_card_count",
        "unsafe_audit_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    payload = build_quality_payload(args.report_path, thresholds_from_args(args))
    if args.write_json:
        quality_path = args.report_path.with_name("trace_net_table_detector_overlay_audit_v1_quality.json")
        write_json(quality_path, payload)
    print_quality(payload)
    return 0 if payload.get("quality_status") == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
