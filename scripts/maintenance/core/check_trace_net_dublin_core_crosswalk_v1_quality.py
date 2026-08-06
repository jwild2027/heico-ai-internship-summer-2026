from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_dublin_core_crosswalk_v1 import quality_report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Dublin Core Crosswalk v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--require-page-count", type=int, default=0)
    parser.add_argument("--min-page-records", type=int, default=0)
    parser.add_argument("--min-document-records", type=int, default=1)
    parser.add_argument("--min-pages-with-element-counts", type=int, default=0)
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    quality = quality_report(
        report_path=args.report_path,
        quality_config={
            "require_page_count": args.require_page_count,
            "min_page_records": args.min_page_records,
            "min_document_records": args.min_document_records,
            "min_pages_with_element_counts": args.min_pages_with_element_counts,
        },
        write_json_report=args.write_json,
    )
    print("TRACE-Net Dublin Core Crosswalk v1 quality")
    print(f" Status: {quality['status']}")
    for key in [
        "page_dc_record_count",
        "document_dc_record_count",
        "page_records_with_element_counts",
        "missing_dc_identifier_count",
        "missing_dc_source_count",
        "missing_dc_format_count",
        "missing_trace_net_element_count",
        "missing_trace_net_element_type_count",
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
