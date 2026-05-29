#!/usr/bin/env python3
"""Build a read-only first-pass / real-server intake plan from a source ZIP sample."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.real_scale_intake import build_intake_plan_report, write_json_report


def _bytes_from_tb(tb: float) -> int:
    return int(tb * 1024 ** 4)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan real-scale TIFF intake from a source-package sample.")
    parser.add_argument("--source-zip", required=True, help="Path to source metadata/TIFF ZIP.")
    parser.add_argument("--export-dir", default="local_data/organization/export", help="Organization export directory.")
    parser.add_argument("--target-total-tb", type=float, default=5.0, help="Target archive size in TiB for estimate.")
    parser.add_argument("--batch-size", type=int, default=5000, help="Suggested baseline batch size in pages.")
    parser.add_argument(
        "--context-seconds-per-page",
        type=float,
        default=12.0,
        help="Observed/assumed page-context LLM seconds per page for rough estimate.",
    )
    parser.add_argument("--write-json", action="store_true", help="Write JSON report.")
    parser.add_argument(
        "--json-output",
        default="local_data/batch_audit/real_server_intake_plan.json",
        help="JSON output path.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_intake_plan_report(
        zip_path=args.source_zip,
        export_dir=args.export_dir,
        target_total_bytes=_bytes_from_tb(args.target_total_tb),
        batch_size_pages=args.batch_size,
        context_seconds_per_page=args.context_seconds_per_page,
    )

    print("Real-scale TIFF intake plan")
    print(f"  Status: {report.status.upper()}")
    print(f"  Source ZIP: {report.source_package.zip_path}")
    print(f"  Export dir: {args.export_dir}")
    print()
    print("Source package sample:")
    print(f"  TIFF files: {report.source_package.tiff_files}")
    print(f"  OCR text files in ZIP: {report.source_package.ocr_text_files}")
    print(f"  metadata.xml present: {report.source_package.metadata_xml_present}")
    print(f"  TIFF bytes: {report.source_package.tiff_total_bytes}")
    print(f"  Avg TIFF bytes/page: {report.source_package.avg_tiff_bytes:.1f}")
    print(f"  Median TIFF bytes/page: {report.source_package.median_tiff_bytes:.1f}")

    if report.traceability:
        trace = report.traceability
        print()
        print("ZIP -> organization traceability:")
        print(f"  Status: {trace.status.upper()}")
        print(f"  Matched pages: {trace.matched_pages_by_number}/{trace.organization_pages}")
        print(f"  ZIP-only pages: {trace.zip_tiffs_without_organization_page}")
        print(f"  Organization-only pages: {trace.organization_pages_without_zip_tiff}")

    if report.scale_estimate:
        estimate = report.scale_estimate
        print()
        print(f"Rough scale estimate for {args.target_total_tb:g} TiB archive:")
        print(f"  Estimated pages: {estimate.estimated_pages_at_target_size:,}")
        print(f"  Batch size: {estimate.batch_size_pages:,} pages")
        print(f"  Estimated batches: {estimate.estimated_inventory_batches:,}")
        print(
            f"  Page-context LLM time at {estimate.assumed_context_seconds_per_page:.1f}s/page, one worker: "
            f"{estimate.estimated_context_hours_one_worker:,.1f} hours"
        )

    print()
    print("Recommended first-pass stages:")
    for stage in report.stages:
        print(f"  {stage['stage']}. {stage['name']}: {stage['goal']}")

    print()
    print("Readiness notes:")
    for note in report.readiness_notes:
        print(f"  - {note}")

    warnings = list(report.source_package.warnings)
    if report.traceability:
        warnings.extend(report.traceability.warnings)
    if report.scale_estimate:
        warnings.extend(report.scale_estimate.warnings)
    unique_warnings = []
    for warning in warnings:
        if warning not in unique_warnings:
            unique_warnings.append(warning)
    if unique_warnings:
        print()
        print("Warnings / planning risks:")
        for warning in unique_warnings:
            print(f"  - {warning}")

    if args.write_json:
        path = write_json_report(report, args.json_output)
        print()
        print(f"JSON: {path}")

    return 0 if report.status == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
