from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

SCHEMA_VERSION = "trace_net_page_ink_route_evidence_v1"
QUALITY_SCHEMA_VERSION = "trace_net_page_ink_route_evidence_v1_quality"
PASS = "PASS"
FAIL = "FAIL"


@dataclass
class InkRouteEvidenceQualityThresholds:
    min_ink_evidence_cards: int = 1
    min_source_page_ink_evidence_cards: int = 1
    min_image_analyzed_cards: int = 1
    max_image_read_error_cards: int = 0
    max_unsafe_ink_cards: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_page_route_manifest_quality_pass: bool = False
    require_no_answer_permission: bool = False


def _int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except Exception:
        return 0


def load_report(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def evaluate_quality(
    report: Mapping[str, Any],
    thresholds: Optional[InkRouteEvidenceQualityThresholds] = None,
) -> Dict[str, Any]:
    thresholds = thresholds or InkRouteEvidenceQualityThresholds()
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else report

    ink_evidence_card_count = _int(summary.get("ink_evidence_card_count"))
    source_page_ink_evidence_card_count = _int(summary.get("source_page_ink_evidence_card_count"))
    image_analyzed_card_count = _int(summary.get("image_analyzed_card_count"))
    image_read_error_card_count = _int(summary.get("image_read_error_card_count"))
    unsafe_ink_card_count = _int(summary.get("unsafe_ink_card_count"))
    answer_permission_count = _int(summary.get("answer_permission_count"))
    source_truth_mutation_allowed_count = _int(summary.get("source_truth_mutation_allowed_count"))
    page_route_manifest_quality_status = summary.get("page_route_manifest_quality_status")

    checks: Dict[str, bool] = {
        "schema_version_ok": report.get("schema_version") == SCHEMA_VERSION,
        "min_ink_evidence_cards_met": ink_evidence_card_count >= thresholds.min_ink_evidence_cards,
        "min_source_page_ink_evidence_cards_met": source_page_ink_evidence_card_count >= thresholds.min_source_page_ink_evidence_cards,
        "min_image_analyzed_cards_met": image_analyzed_card_count >= thresholds.min_image_analyzed_cards,
        "image_read_error_cards_within_limit": image_read_error_card_count <= thresholds.max_image_read_error_cards,
        "unsafe_ink_cards_within_limit": unsafe_ink_card_count <= thresholds.max_unsafe_ink_cards,
        "answer_permission_within_limit": answer_permission_count <= thresholds.max_answer_permission_count,
        "source_truth_mutation_allowed_within_limit": source_truth_mutation_allowed_count <= thresholds.max_source_truth_mutation_allowed,
    }
    if thresholds.require_page_route_manifest_quality_pass:
        checks["page_route_manifest_quality_pass"] = page_route_manifest_quality_status == PASS
    if thresholds.require_no_answer_permission:
        checks["no_answer_permission"] = answer_permission_count == 0

    quality_fail_reasons = [name for name, ok in checks.items() if not ok]
    quality_status = PASS if not quality_fail_reasons else FAIL
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "source_schema_version": report.get("schema_version"),
        "quality_status": quality_status,
        "status": quality_status,
        "checks": checks,
        "quality_fail_reasons": quality_fail_reasons,
        "ink_evidence_card_count": ink_evidence_card_count,
        "source_page_ink_evidence_card_count": source_page_ink_evidence_card_count,
        "image_analyzed_card_count": image_analyzed_card_count,
        "image_read_error_card_count": image_read_error_card_count,
        "unsafe_ink_card_count": unsafe_ink_card_count,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "page_route_manifest_quality_status": page_route_manifest_quality_status,
    }


def _thresholds_from_args(args: argparse.Namespace) -> InkRouteEvidenceQualityThresholds:
    return InkRouteEvidenceQualityThresholds(
        min_ink_evidence_cards=args.min_ink_evidence_cards,
        min_source_page_ink_evidence_cards=args.min_source_page_ink_evidence_cards,
        min_image_analyzed_cards=args.min_image_analyzed_cards,
        max_image_read_error_cards=args.max_image_read_error_cards,
        max_unsafe_ink_cards=args.max_unsafe_ink_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_page_route_manifest_quality_pass=args.require_page_route_manifest_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check TRACE-Net Page Ink Route Evidence v1 quality")
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--min-ink-evidence-cards", type=int, default=1)
    parser.add_argument("--min-source-page-ink-evidence-cards", type=int, default=1)
    parser.add_argument("--min-image-analyzed-cards", type=int, default=1)
    parser.add_argument("--max-image-read-error-cards", type=int, default=0)
    parser.add_argument("--max-unsafe-ink-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-page-route-manifest-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = load_report(args.report_path)
    quality = evaluate_quality(report, _thresholds_from_args(args))
    if args.write_json:
        quality_path = args.report_path.with_name("trace_net_page_ink_route_evidence_v1_quality.json")
        write_json(quality_path, quality)
    print("TRACE-Net Page Ink Route Evidence v1 quality")
    print(f" Status: {quality.get('quality_status')}")
    for key in [
        "ink_evidence_card_count",
        "source_page_ink_evidence_card_count",
        "image_analyzed_card_count",
        "image_read_error_card_count",
        "unsafe_ink_card_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
        "page_route_manifest_quality_status",
    ]:
        print(f" {key}: {quality.get(key)}")
    return quality


if __name__ == "__main__":  # pragma: no cover
    main()
