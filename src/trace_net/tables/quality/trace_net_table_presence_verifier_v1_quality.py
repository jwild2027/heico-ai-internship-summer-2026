"""Quality helpers for TRACE-Net Table Presence Verifier v1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from tiff.trace_net_table_presence_verifier_v1 import QUALITY_SCHEMA_VERSION, quality_checks, write_json


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
    p = argparse.ArgumentParser(description="Check TRACE-Net table presence verifier v1 quality.")
    p.add_argument("--report-path", required=True)
    p.add_argument("--min-source-structure-records", type=int, default=1)
    p.add_argument("--min-presence-records", type=int, default=1)
    p.add_argument("--min-presence-decisions", type=int, default=1)
    p.add_argument("--min-localization-allowed-records", type=int, default=0)
    p.add_argument("--min-suppressed-candidates", type=int, default=0)
    p.add_argument("--max-unsafe-records", type=int, default=0)
    p.add_argument("--max-answer-permission-count", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--require-table-structure-bbox-localizer-quality-pass", action="store_true")
    p.add_argument("--require-table-visual-bbox-localizer-quality-pass", action="store_true")
    p.add_argument("--require-table-bbox-scoped-cell-extraction-quality-pass", action="store_true")
    p.add_argument("--require-table-ocr-bbox-enrichment-quality-pass", action="store_true")
    p.add_argument("--require-all-records-have-presence-decision", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--write-json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report_path = Path(args.report_path)
    report = read_json(report_path)
    quality = evaluate_report(report, args)
    if args.write_json:
        out = report_path.with_name("trace_net_table_presence_verifier_v1_quality.json")
        write_json(out, quality)
    summary = quality.get("summary", {})
    print("TRACE-Net Table Presence Verifier v1 quality")
    print(f" Status: {quality.get('status')}")
    for key in (
        "source_structure_record_count",
        "source_visual_record_count",
        "source_scoped_table_record_count",
        "source_ocr_enrichment_card_count",
        "route_manifest_page_count",
        "table_presence_record_count",
        "confirmed_table_record_count",
        "weak_table_record_count",
        "not_table_record_count",
        "table_localization_allowed_record_count",
        "table_localization_suppressed_record_count",
        "false_positive_table_candidate_count",
        "non_table_route_suppressed_count",
        "image_visual_reroute_recommended_count",
        "normal_text_reroute_recommended_count",
        "review_table_candidate_count",
        "hybrid_ink_metrics_record_count",
        "weak_hybrid_ink_table_signal_count",
        "image_like_color_region_count",
        "unsafe_table_presence_verifier_record_count",
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
