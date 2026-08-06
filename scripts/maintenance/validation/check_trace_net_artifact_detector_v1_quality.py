from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from tiff.trace_net_artifact_detector_v1_quality import (
    PASS,
    ArtifactDetectorQualityThresholds,
    evaluate_quality,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TRACE-Net Artifact Detector v1 quality")
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--min-artifact-cards", type=int, default=1)
    parser.add_argument("--min-page-artifact-cards", type=int, default=1)
    parser.add_argument("--min-source-page-cards", type=int, default=0)
    parser.add_argument("--max-unsafe-artifact-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-metadata-pages", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def thresholds_from_args(args: argparse.Namespace) -> ArtifactDetectorQualityThresholds:
    return ArtifactDetectorQualityThresholds(
        min_artifact_cards=args.min_artifact_cards,
        min_page_artifact_cards=args.min_page_artifact_cards,
        min_source_page_cards=args.min_source_page_cards,
        max_unsafe_artifact_cards=args.max_unsafe_artifact_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_metadata_pages=args.require_metadata_pages,
        require_no_answer_permission=args.require_no_answer_permission,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = json.loads(args.report_path.read_text(encoding="utf-8"))
    quality = evaluate_quality(report, thresholds_from_args(args))
    if args.write_json:
        quality_path = args.report_path.with_name("trace_net_artifact_detector_v1_quality.json")
        quality_path.write_text(json.dumps(quality, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("TRACE-Net Artifact Detector v1 quality")
    print(f" Status: {quality.get('quality_status')}")
    for key in (
        "artifact_card_count",
        "page_artifact_card_count",
        "source_page_card_count",
        "unsafe_artifact_card_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ):
        print(f" {key}: {quality.get(key)}")
    return 0 if quality.get("quality_status") == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
