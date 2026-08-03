from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from tiff.trace_net_page_route_manifest_v1_quality import (
    PASS,
    PageRouteManifestQualityThresholds,
    evaluate_quality,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TRACE-Net Page Route Manifest v1 quality")
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--min-page-route-cards", type=int, default=1)
    parser.add_argument("--min-source-page-route-cards", type=int, default=0)
    parser.add_argument("--min-table-route-cards", type=int, default=0)
    parser.add_argument("--min-safe-for-routing-cards", type=int, default=1)
    parser.add_argument("--min-page-ink-route-evidence-cards", type=int, default=0)
    parser.add_argument("--max-unsafe-route-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-artifact-detector-quality-pass", action="store_true")
    parser.add_argument("--require-page-ink-route-evidence-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def thresholds_from_args(args: argparse.Namespace) -> PageRouteManifestQualityThresholds:
    return PageRouteManifestQualityThresholds(
        min_page_route_cards=args.min_page_route_cards,
        min_source_page_route_cards=args.min_source_page_route_cards,
        min_table_route_cards=args.min_table_route_cards,
        min_safe_for_routing_cards=args.min_safe_for_routing_cards,
        max_unsafe_route_cards=args.max_unsafe_route_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_artifact_detector_quality_pass=args.require_artifact_detector_quality_pass,
        require_page_ink_route_evidence_quality_pass=args.require_page_ink_route_evidence_quality_pass,
        min_page_ink_route_evidence_cards=args.min_page_ink_route_evidence_cards,
        require_no_answer_permission=args.require_no_answer_permission,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    with args.report_path.open("r", encoding="utf-8") as f:
        report = json.load(f)
    quality = evaluate_quality(report, thresholds_from_args(args))
    if args.write_json:
        quality_path = args.report_path.with_name("trace_net_page_route_manifest_v1_quality.json")
        with quality_path.open("w", encoding="utf-8") as f:
            json.dump(quality, f, indent=2, sort_keys=True)
            f.write("\n")
    print("TRACE-Net Page Route Manifest v1 quality")
    print(f" Status: {quality.get('quality_status')}")
    for key in (
        "page_route_card_count",
        "source_page_route_card_count",
        "table_primary_route_count",
        "safe_for_routing_route_card_count",
        "unsafe_route_card_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
        "artifact_detector_quality_status",
        "page_ink_route_evidence_quality_status",
        "page_ink_route_evidence_available_card_count",
    ):
        print(f" {key}: {quality.get(key)}")
    return 0 if quality.get("quality_status") == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
