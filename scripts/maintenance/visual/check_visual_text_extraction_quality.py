#!/usr/bin/env python3
"""Check model-assisted visual text extraction quality."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.visual_text_extraction_quality import (  # noqa: E402
    VisualTextQualityPaths,
    build_visual_text_extraction_quality,
    format_visual_text_extraction_quality,
    write_visual_text_extraction_quality,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Quality gate for visual OCR / vision-model text extraction.")
    parser.add_argument("--output-dir", type=Path, default=Path("local_data/organization/visual_text"))
    parser.add_argument("--min-records", type=int, default=1)
    parser.add_argument("--min-pages-with-visual-text", type=int, default=1)
    parser.add_argument("--max-error-records", type=int, default=0)
    parser.add_argument(
        "--allow-partial-status",
        action="store_true",
        help="Allow a PARTIAL/FAIL run summary to pass when accepted records meet thresholds and error count is <= --max-error-records.",
    )
    parser.add_argument("--disallow-planned", action="store_true", help="Require real model output instead of planned dry-run records.")
    parser.add_argument("--require-v2", action="store_true", help="Require accepted records to use the strict visual_text_v2 prompt/output format.")
    parser.add_argument("--require-v2-2", action="store_true", help="Require accepted records to use the visual_text_v2_2 prompt/output format.")
    parser.add_argument("--require-v2-4", action="store_true", help="Require accepted records to use the visual_text_v2_4 compact anti-leak prompt/output format.")
    parser.add_argument("--min-required-section-records", type=int, default=0, help="Minimum records with every required v2 section present.")
    parser.add_argument("--max-summary-heavy-records", type=int, default=None, help="Maximum records flagged as summary-heavy.")
    parser.add_argument("--max-hallucination-risk-records", type=int, default=None, help="Maximum records flagged with hallucination-risk wording.")
    parser.add_argument("--max-refusal-like-records", type=int, default=None, help="Maximum records containing refusal-like output such as unable to transcribe images.")
    parser.add_argument("--max-metadata-leakage-records", type=int, default=None, help="Maximum records where metadata/context leaked into visible-text sections.")
    parser.add_argument("--write-json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = VisualTextQualityPaths(output_dir=args.output_dir)
    kwargs = {
        "min_records": args.min_records,
        "min_pages_with_visual_text": args.min_pages_with_visual_text,
        "max_error_records": args.max_error_records,
        "allow_planned": not args.disallow_planned,
        "allow_partial_status": args.allow_partial_status,
        "require_v2": args.require_v2,
        "require_v2_2": args.require_v2_2,
        "require_v2_4": args.require_v2_4,
        "min_required_section_records": args.min_required_section_records,
        "max_summary_heavy_records": args.max_summary_heavy_records,
        "max_hallucination_risk_records": args.max_hallucination_risk_records,
        "max_refusal_like_records": args.max_refusal_like_records,
        "max_metadata_leakage_records": args.max_metadata_leakage_records,
    }
    report = write_visual_text_extraction_quality(paths, **kwargs) if args.write_json else build_visual_text_extraction_quality(paths, **kwargs)
    print(format_visual_text_extraction_quality(report))
    if args.write_json:
        print(f"\nJSON: {paths.quality_path}")
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
