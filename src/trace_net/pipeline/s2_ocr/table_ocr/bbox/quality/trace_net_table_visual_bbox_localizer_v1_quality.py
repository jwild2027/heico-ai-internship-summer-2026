"""Quality checker for TRACE-Net Table Visual BBox Localizer v1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from tiff.trace_net_table_visual_bbox_localizer_v1 import QUALITY_SCHEMA_VERSION, quality_errors, utc_now, write_json


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net table visual bbox localizer v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--min-source-cards", type=int, default=1)
    parser.add_argument("--min-localized-records", type=int, default=1)
    parser.add_argument("--min-image-available-records", type=int, default=1)
    parser.add_argument("--min-visual-refined-records", type=int, default=1)
    parser.add_argument("--min-localization-ready-records", type=int, default=1)
    parser.add_argument("--min-localization-quality-pass-records", type=int, default=0)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-ocr-bbox-enrichment-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def check_report(args: argparse.Namespace) -> dict[str, Any]:
    report_path = Path(args.report_path)
    payload = load_json(report_path)
    summary: Mapping[str, Any] = payload.get("summary") or {}
    errors = quality_errors(summary, args)
    quality_status = "PASS" if not errors else "FAIL"
    quality_payload = {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "quality_status": quality_status,
        "generated_at": utc_now(),
        "report_path": str(report_path),
        "summary": dict(summary),
        "quality_errors": errors,
    }
    if args.write_json:
        write_json(report_path.with_name("trace_net_table_visual_bbox_localizer_v1_quality.json"), quality_payload)
    return quality_payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    payload = check_report(args)
    summary = payload["summary"]
    print("TRACE-Net Table Visual BBox Localizer v1 quality")
    print(f" Status: {payload['quality_status']}")
    for key in (
        "source_card_count",
        "localized_record_count",
        "image_available_record_count",
        "input_bbox_record_count",
        "visual_refinement_attempted_record_count",
        "visual_refined_bbox_record_count",
        "input_bbox_fallback_record_count",
        "table_localization_ready_record_count",
        "table_localization_quality_pass_record_count",
        "broad_input_bbox_record_count",
        "localized_bbox_still_broad_record_count",
        "weak_visual_table_signal_record_count",
        "unsafe_table_visual_bbox_localizer_record_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")
    return 0 if payload["quality_status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
