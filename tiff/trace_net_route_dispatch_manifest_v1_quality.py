from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping

SCHEMA_VERSION = "trace_net_route_dispatch_manifest_v1"
QUALITY_SCHEMA_VERSION = "trace_net_route_dispatch_manifest_v1_quality"
PASS = "PASS"
FAIL = "FAIL"


@dataclass(frozen=True)
class RouteDispatchQualityThresholds:
    min_dispatch_cards: int = 1
    min_source_page_dispatch_cards: int = 0
    min_primary_route_cards: int = 1
    max_unsafe_dispatch_cards: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_page_route_manifest_quality_pass: bool = False
    require_no_answer_permission: bool = False


def _int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def evaluate_quality(
    report: Mapping[str, Any],
    thresholds: RouteDispatchQualityThresholds | None = None,
) -> Dict[str, Any]:
    thresholds = thresholds or RouteDispatchQualityThresholds()
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else report

    dispatch_card_count = _int(summary.get("route_dispatch_card_count"))
    source_page_dispatch_card_count = _int(summary.get("source_page_dispatch_card_count"))
    primary_route_dispatch_card_count = _int(summary.get("primary_route_dispatch_card_count"))
    unsafe_dispatch_card_count = _int(summary.get("unsafe_dispatch_card_count"))
    answer_permission_count = _int(summary.get("answer_permission_count"))
    source_truth_mutation_allowed_count = _int(summary.get("source_truth_mutation_allowed_count"))
    page_route_manifest_quality_status = summary.get("page_route_manifest_quality_status")

    checks: Dict[str, bool] = {
        "schema_version_ok": report.get("schema_version") == SCHEMA_VERSION,
        "min_dispatch_cards_met": dispatch_card_count >= thresholds.min_dispatch_cards,
        "min_source_page_dispatch_cards_met": source_page_dispatch_card_count >= thresholds.min_source_page_dispatch_cards,
        "min_primary_route_cards_met": primary_route_dispatch_card_count >= thresholds.min_primary_route_cards,
        "unsafe_dispatch_cards_within_limit": unsafe_dispatch_card_count <= thresholds.max_unsafe_dispatch_cards,
        "answer_permission_within_limit": answer_permission_count <= thresholds.max_answer_permission_count,
        "source_truth_mutation_allowed_within_limit": source_truth_mutation_allowed_count <= thresholds.max_source_truth_mutation_allowed,
    }
    if thresholds.require_page_route_manifest_quality_pass:
        checks["page_route_manifest_quality_pass"] = page_route_manifest_quality_status == PASS
    if thresholds.require_no_answer_permission:
        checks["no_answer_permission"] = answer_permission_count == 0

    quality_fail_reasons = [name for name, ok in checks.items() if not ok]
    quality_status = PASS if not quality_fail_reasons else FAIL

    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "source_schema_version": report.get("schema_version"),
        "quality_status": quality_status,
        "status": quality_status,
        "checks": checks,
        "quality_fail_reasons": quality_fail_reasons,
        "route_dispatch_card_count": dispatch_card_count,
        "source_page_dispatch_card_count": source_page_dispatch_card_count,
        "primary_route_dispatch_card_count": primary_route_dispatch_card_count,
        "table_dispatch_card_count": _int(summary.get("table_dispatch_card_count")),
        "image_visual_dispatch_card_count": _int(summary.get("image_visual_dispatch_card_count")),
        "normal_text_dispatch_card_count": _int(summary.get("normal_text_dispatch_card_count")),
        "blank_candidate_dispatch_card_count": _int(summary.get("blank_candidate_dispatch_card_count")),
        "review_dispatch_card_count": _int(summary.get("review_dispatch_card_count")),
        "unsafe_dispatch_card_count": unsafe_dispatch_card_count,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "page_route_manifest_quality_status": page_route_manifest_quality_status,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Route Dispatch Manifest v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-dispatch-cards", type=int, default=1)
    parser.add_argument("--min-source-page-dispatch-cards", type=int, default=0)
    parser.add_argument("--min-primary-route-cards", type=int, default=1)
    parser.add_argument("--max-unsafe-dispatch-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-page-route-manifest-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> Dict[str, Any]:
    args = parse_args(argv)
    report_path = Path(args.report_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    thresholds = RouteDispatchQualityThresholds(
        min_dispatch_cards=args.min_dispatch_cards,
        min_source_page_dispatch_cards=args.min_source_page_dispatch_cards,
        min_primary_route_cards=args.min_primary_route_cards,
        max_unsafe_dispatch_cards=args.max_unsafe_dispatch_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_page_route_manifest_quality_pass=args.require_page_route_manifest_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    quality = evaluate_quality(report, thresholds)
    if args.write_json:
        quality_path = report_path.with_name(report_path.stem + "_quality.json")
        quality_path.write_text(json.dumps(quality, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("TRACE-Net Route Dispatch Manifest v1 quality")
    print(f" Status: {quality['quality_status']}")
    for key in [
        "route_dispatch_card_count",
        "source_page_dispatch_card_count",
        "primary_route_dispatch_card_count",
        "table_dispatch_card_count",
        "image_visual_dispatch_card_count",
        "normal_text_dispatch_card_count",
        "blank_candidate_dispatch_card_count",
        "review_dispatch_card_count",
        "unsafe_dispatch_card_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
        "page_route_manifest_quality_status",
    ]:
        print(f" {key}: {quality.get(key)}")
    return quality


if __name__ == "__main__":
    main()
