#!/usr/bin/env python
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_leiden_category_summary_hydrator_v1 import (
    DEFAULT_QUALITY_NAME,
    QualityThresholds,
    check_quality,
    load_json,
    write_json,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check TRACE-Net Leiden Category Summary Hydrator v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--require-page-count", type=int, default=None)
    parser.add_argument("--min-communities", type=int, default=1)
    parser.add_argument("--min-hydrated-communities", type=int, default=1)
    parser.add_argument("--max-missing-page-membership", type=int, default=None)
    parser.add_argument("--max-missing-category-summary", type=int, default=None)
    parser.add_argument("--max-community-as-proof", type=int, default=0)
    parser.add_argument("--max-category-as-proof", type=int, default=0)
    parser.add_argument("--max-retrieval-only-answer-allowed", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-leiden-quality-pass", action="store_true")
    parser.add_argument("--require-category-overlay-quality-pass", action="store_true")
    parser.add_argument("--require-dublin-core-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)

    report_path = Path(args.report_path)
    report = load_json(report_path)
    thresholds = QualityThresholds(
        require_page_count=args.require_page_count,
        min_communities=args.min_communities,
        min_hydrated_communities=args.min_hydrated_communities,
        max_missing_page_membership=args.max_missing_page_membership,
        max_missing_category_summary=args.max_missing_category_summary,
        max_community_as_proof=args.max_community_as_proof,
        max_category_as_proof=args.max_category_as_proof,
        max_retrieval_only_answer_allowed=args.max_retrieval_only_answer_allowed,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_leiden_quality_pass=args.require_leiden_quality_pass,
        require_category_overlay_quality_pass=args.require_category_overlay_quality_pass,
        require_dublin_core_quality_pass=args.require_dublin_core_quality_pass,
    )
    quality = check_quality(report, thresholds)

    if args.write_json:
        write_json(report_path.with_name(DEFAULT_QUALITY_NAME), quality)

    summary = quality.get("summary") or {}
    print("TRACE-Net Leiden Category Summary Hydrator v1 quality")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {quality.get('quality_status')}")
    for key in (
        "community_hydration_record_count",
        "category_summary_hydrated_count",
        "missing_category_summary_count",
        "missing_page_membership_count",
        "low_category_coherence_count",
        "review_recommended_community_count",
        "effective_page_count",
        "community_as_proof_count",
        "category_as_proof_count",
        "retrieval_only_answer_allowed_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")
    if quality.get("issues"):
        print(" Issues:")
        for issue in quality["issues"]:
            print(f"  - {issue}")
    return 0 if quality.get("quality_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
