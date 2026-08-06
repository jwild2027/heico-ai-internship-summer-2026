#!/usr/bin/env python
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_leiden_representative_label_tightening_v1 import (
    add_common_threshold_args,
    check_quality,
    thresholds_from_args,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Leiden Representative Label Tightening v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    add_common_threshold_args(parser)
    args = parser.parse_args(argv)
    report = check_quality(
        report_path=args.report_path,
        thresholds=thresholds_from_args(args),
        write_json_report=args.write_json,
    )
    summary = report.get("summary", {})
    print("TRACE-Net Leiden Representative Label Tightening v1 quality")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "community_profile_record_count",
        "refined_label_count",
        "communities_with_representative_pages_count",
        "missing_page_membership_count",
        "missing_category_summary_count",
        "low_navigation_confidence_count",
        "review_recommended_community_count",
        "community_as_proof_count",
        "category_as_proof_count",
        "retrieval_only_answer_allowed_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    failures = report.get("failures") or []
    for failure in failures:
        print(f" FAILURE: {failure}")
    return 0 if report.get("quality_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
