"""Quality checker for TRACE-Net Table BBox Resolver v1."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from tiff.trace_net_table_bbox_resolver_v1 import (
    build_quality_payload,
    evaluate_quality,
    load_json,
    thresholds_from_args,
    add_common_threshold_args,
    write_json,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Table BBox Resolver v1 quality")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--write-json", action="store_true")
    add_common_threshold_args(parser)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = load_json(args.report_path)
    summary = dict(report.get("summary") or {})
    quality_status, reasons, checks = evaluate_quality(summary, thresholds_from_args(args))
    report["quality_status"] = quality_status
    report["quality_fail_reasons"] = reasons
    report["checks"] = checks
    summary["quality_status"] = quality_status
    summary["quality_fail_reasons"] = reasons
    report["summary"] = summary
    quality_payload = build_quality_payload(report)
    if args.write_json:
        write_json(args.report_path.with_name("trace_net_table_bbox_resolver_v1_quality.json"), quality_payload)
    print("TRACE-Net Table BBox Resolver v1 quality")
    print(f" Status: {quality_status}")
    for key in (
        "source_table_geometry_card_count",
        "bbox_card_count",
        "resolved_bbox_card_count",
        "crop_ready_card_count",
        "heuristic_bbox_card_count",
        "ocr_bbox_enrichment_available_card_count",
        "ocr_bbox_enrichment_crop_candidate_ready_card_count",
        "ocr_bbox_enrichment_used_card_count",
        "ocr_bbox_enrichment_rejected_card_count",
        "ocr_bbox_enrichment_broad_crop_candidate_card_count",
        "unsafe_bbox_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")
    return 0 if quality_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
