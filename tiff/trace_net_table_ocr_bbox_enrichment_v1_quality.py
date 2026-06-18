"""Quality checker for TRACE-Net Table OCR BBox Enrichment v1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from tiff.trace_net_table_ocr_bbox_enrichment_v1 import build_quality_payload, add_common_args, thresholds_from_args, write_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Table OCR BBox Enrichment v1 quality")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--write-json", action="store_true")
    add_common_args(parser)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    report = json.loads(args.report_path.read_text(encoding="utf-8"))
    quality = build_quality_payload(report, thresholds_from_args(args))
    if args.write_json:
        write_json(args.report_path.with_name("trace_net_table_ocr_bbox_enrichment_v1_quality.json"), quality)
    summary = quality.get("summary") or {}
    print("TRACE-Net Table OCR BBox Enrichment v1 quality")
    print(f" Status: {quality.get('quality_status')}")
    for key in [
        "source_table_geometry_card_count", "ocr_bbox_enrichment_card_count", "ocr_source_file_card_count",
        "ocr_bbox_record_card_count", "matched_ocr_bbox_card_count", "part_number_ocr_match_card_count",
        "crop_candidate_ready_card_count", "content_band_tightening_available_card_count", "content_band_tightening_applied_card_count",
        "broad_ocr_bbox_card_count", "tightened_ocr_bbox_card_count", "review_required_card_count", "unsafe_ocr_bbox_enrichment_card_count",
        "answer_permission_count", "can_answer_directly_count", "can_prove_claims_count",
        "source_truth_mutation_allowed_count", "postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    return 0 if quality.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
