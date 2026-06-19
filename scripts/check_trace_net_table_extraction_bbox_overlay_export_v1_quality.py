from __future__ import annotations

import argparse
import json
from pathlib import Path

from tiff.trace_net_table_extraction_bbox_overlay_export_v1 import OverlayThresholds, build_quality, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net table extraction bbox overlay export v1 quality")
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--min-overlay-records", type=int, default=1)
    parser.add_argument("--min-overlay-pngs", type=int, default=1)
    parser.add_argument("--max-missing-extraction-bbox-count", type=int, default=0)
    parser.add_argument("--max-unsafe-record-count", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-line-geometry-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args()

    payload = json.loads(args.report_path.read_text(encoding="utf-8"))
    summary = payload.get("summary") or {}
    quality = build_quality(
        summary,
        OverlayThresholds(
            min_overlay_records=args.min_overlay_records,
            min_overlay_pngs=args.min_overlay_pngs,
            max_missing_extraction_bbox_count=args.max_missing_extraction_bbox_count,
            max_unsafe_record_count=args.max_unsafe_record_count,
            max_answer_permission_count=args.max_answer_permission_count,
            max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
            require_table_line_geometry_quality_pass=args.require_table_line_geometry_quality_pass,
            require_no_answer_permission=args.require_no_answer_permission,
        ),
    )

    print("TRACE-Net Table Extraction BBox Overlay Export v1 quality")
    print(f" Status: {quality['status']}")
    for key in [
        "overlay_record_count",
        "overlay_png_count",
        "missing_extraction_bbox_count",
        "paddle_style_extraction_bbox_count",
        "unsafe_record_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")

    if args.write_json:
        quality_path = args.report_path.with_name("trace_net_table_extraction_bbox_overlay_export_v1_quality.json")
        write_json(quality_path, quality)
        print(f" quality_path: {quality_path}")

    return 0 if quality["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
