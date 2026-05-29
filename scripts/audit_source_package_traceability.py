#!/usr/bin/env python3
"""Compare a raw public TIFF ZIP to the current organization export."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.real_scale_intake import audit_source_zip_traceability, write_json_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit raw TIFF ZIP -> organization export traceability.")
    parser.add_argument("--zip", required=True, help="Path to source metadata/TIFF ZIP.")
    parser.add_argument("--export-dir", default="local_data/organization/export", help="Organization export directory.")
    parser.add_argument("--sample-limit", type=int, default=10, help="Number of sample rows to print.")
    parser.add_argument("--write-json", action="store_true", help="Write JSON report.")
    parser.add_argument(
        "--json-output",
        default="local_data/batch_audit/source_package_traceability.json",
        help="JSON output path.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = audit_source_zip_traceability(args.zip, args.export_dir, sample_limit=args.sample_limit)

    print("Source package traceability audit")
    print(f"  Status: {report.status.upper()}")
    print(f"  ZIP: {report.zip_path}")
    print(f"  Export dir: {report.export_dir}")
    print()
    print("Counts:")
    print(f"  ZIP TIFF files: {report.zip_tiff_files}")
    print(f"  Organization pages: {report.organization_pages}")
    print(f"  Organization pages with TIFF paths: {report.organization_pages_with_tiff_paths}")
    print(f"  Matched pages by normalized number: {report.matched_pages_by_number}")
    print(f"  ZIP TIFFs without organization page: {report.zip_tiffs_without_organization_page}")
    print(f"  Organization pages without ZIP TIFF: {report.organization_pages_without_zip_tiff}")
    print(f"  Duplicate ZIP page numbers: {report.duplicate_zip_page_numbers}")
    print(f"  Duplicate organization page numbers: {report.duplicate_organization_page_numbers}")
    print(f"  metadata.xml present: {report.metadata_xml_present}")

    if report.sample_matches:
        print()
        print("Sample matches:")
        for idx, row in enumerate(report.sample_matches, start=1):
            print(f"  {idx}. page_number={row['page_number']} zip={row['zip_entry']} page_id={row['page_id']}")
            print(f"     label={row.get('page_label') or '-'} ata={row.get('ata_code') or '-'}")
            print(f"     tiff={row.get('tiff_path') or '-'}")
            print(f"     source={row.get('source_url') or '-'}")

    if report.warnings:
        print()
        print("Warnings:")
        for warning in report.warnings:
            print(f"  - {warning}")

    if args.write_json:
        path = write_json_report(report, args.json_output)
        print()
        print(f"JSON: {path}")

    return 0 if report.status == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
