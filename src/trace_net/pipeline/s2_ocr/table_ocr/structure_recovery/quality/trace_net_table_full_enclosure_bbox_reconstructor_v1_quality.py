"""Quality helpers for TRACE-Net Table Full Enclosure BBox Reconstructor v1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from tiff.trace_net_table_full_enclosure_bbox_reconstructor_v1 import QUALITY_SCHEMA_VERSION, quality_checks, write_json


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evaluate_report(report: Mapping[str, Any], thresholds: Mapping[str, Any] | argparse.Namespace | None = None) -> dict[str, Any]:
    summary = report.get("summary", {}) if isinstance(report, Mapping) else {}
    status, checks = quality_checks(summary, thresholds)
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "status": status,
        "summary": summary,
        "checks": checks,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check TRACE-Net table full enclosure bbox reconstructor v1 quality.")
    p.add_argument("--report-path", required=True)
    p.add_argument("--min-source-structure-records", type=int, default=1)
    p.add_argument("--min-source-presence-records", type=int, default=1)
    p.add_argument("--min-reconstructor-records", type=int, default=1)
    p.add_argument("--min-final-bbox-ready-records", type=int, default=1)
    p.add_argument("--min-full-enclosure-reconstructed-records", type=int, default=0)
    p.add_argument("--min-diagram-or-image-review-only-records", type=int, default=0)
    p.add_argument("--min-bounded-content-band-records", type=int, default=0)
    p.add_argument("--min-full-page-bbox-records", type=int, default=0)
    p.add_argument("--max-unsafe-records", type=int, default=0)
    p.add_argument("--max-answer-permission-count", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--require-table-structure-bbox-localizer-quality-pass", action="store_true")
    p.add_argument("--require-table-presence-verifier-quality-pass", action="store_true")
    p.add_argument("--require-all-final-bboxes-ready", action="store_true")
    p.add_argument("--require-all-recommended-reconstructed", action="store_true")
    p.add_argument("--write-json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report_path = Path(args.report_path)
    report = read_json(report_path)
    quality = evaluate_report(report, args)
    if args.write_json:
        out = report_path.with_name("trace_net_table_full_enclosure_bbox_reconstructor_v1_quality.json")
        write_json(out, quality)
    summary = quality.get("summary", {})
    print("TRACE-Net Table Full Enclosure BBox Reconstructor v1 quality")
    print(f" Status: {quality.get('status')}")
    for key in (
        "source_structure_record_count",
        "source_presence_record_count",
        "full_enclosure_reconstructor_record_count",
        "final_table_bbox_ready_record_count",
        "full_table_enclosure_recommended_record_count",
        "full_table_enclosure_reconstructed_record_count",
        "full_table_boundary_reconstructed_record_count",
        "full_page_bbox_applied_record_count",
        "full_page_bbox_unresolved_record_count",
        "split_column_boundary_reconstructed_record_count",
        "boundary_expanded_x_record_count",
        "boundary_expanded_y_record_count",
        "bounded_table_content_band_record_count",
        "boundary_content_band_capped_record_count",
        "diagram_or_image_review_only_record_count",
        "structure_selected_passthrough_record_count",
        "weak_table_reconstructed_record_count",
        "confirmed_table_passthrough_record_count",
        "table_route_challenged_reconstructed_count",
        "unsafe_table_full_enclosure_bbox_record_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")
    return 0 if quality.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
