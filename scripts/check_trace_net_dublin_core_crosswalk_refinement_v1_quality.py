from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_dublin_core_crosswalk_refinement_v1 import quality_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Dublin Core Crosswalk Refinement v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--require-page-count", type=int, default=None)
    parser.add_argument("--min-page-records", type=int, default=0)
    parser.add_argument("--min-records-with-physical-counts", type=int, default=0)
    parser.add_argument("--min-records-with-operational-counts", type=int, default=0)
    parser.add_argument("--min-records-with-review-summary", type=int, default=0)
    parser.add_argument("--min-blank-pages-with-low-physical", type=int, default=0)
    parser.add_argument("--max-clean-overbroad-dc-type", type=int, default=None)
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)
    cfg = {
        "require_page_count": args.require_page_count,
        "min_page_records": args.min_page_records,
        "min_records_with_physical_counts": args.min_records_with_physical_counts,
        "min_records_with_operational_counts": args.min_records_with_operational_counts,
        "min_records_with_review_summary": args.min_records_with_review_summary,
        "min_blank_pages_with_low_physical": args.min_blank_pages_with_low_physical,
        "max_clean_overbroad_dc_type": args.max_clean_overbroad_dc_type,
    }
    quality = quality_report(report_path=args.report_path, quality_config=cfg, write_json_report=args.write_json)
    print("TRACE-Net Dublin Core Crosswalk Refinement v1 quality")
    print(f" Status: {quality['status']}")
    for key in [
        "page_record_count",
        "records_with_physical_element_counts",
        "records_with_operational_element_counts",
        "records_with_review_summary",
        "blank_pages_with_low_physical_count",
        "clean_overbroad_dc_type_count",
        "direct_answer_allowed_count",
        "claim_proof_allowed_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {quality.get(key)}")
    if args.write_json:
        print(f" quality_path: {quality.get('quality_path')}")
    return 0 if quality["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
