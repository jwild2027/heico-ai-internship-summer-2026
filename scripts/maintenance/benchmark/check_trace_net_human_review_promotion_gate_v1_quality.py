#!/usr/bin/env python
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_human_review_promotion_gate_v1 import DEFAULT_QUALITY_FILENAME, quality_report, read_json, write_json


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net human review promotion gate v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-review-decisions", type=int, default=1)
    parser.add_argument("--min-promotion-evaluations", type=int, default=0)
    parser.add_argument("--require-source-decision-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)

    try:
        payload = read_json(args.report_path)
        quality = quality_report(
            payload,
            min_review_decisions=args.min_review_decisions,
            min_promotion_evaluations=args.min_promotion_evaluations,
            require_source_decision_quality_pass=args.require_source_decision_quality_pass,
        )
        if args.write_json:
            out = Path(args.report_path).with_name(DEFAULT_QUALITY_FILENAME)
            write_json(out, quality)
    except Exception as exc:
        print(f"TRACE-Net human review promotion gate quality check failed: {exc}")
        return 1

    summary = quality.get("summary") or {}
    print("TRACE-Net human review promotion gate v1 quality")
    print(f" Status: {quality.get('status')}")
    for key in [
        "review_decision_count",
        "promotion_candidate_count",
        "promotion_evaluation_count",
        "promotion_approved_count",
        "promotion_denied_count",
        "promotion_review_required_count",
        "approved_without_citation_count",
        "unsafe_promotion_record_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    if args.write_json:
        print(f" quality_path: {Path(args.report_path).with_name(DEFAULT_QUALITY_FILENAME)}")
    return 0 if quality.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
