from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from tiff.trace_net_route_dispatch_warning_triage_v1_quality import (
    PASS,
    SCHEMA_VERSION,
    RouteDispatchWarningTriageQualityThresholds,
    evaluate_quality,
)

STATUS_BUILT = "TRACE_NET_ROUTE_DISPATCH_WARNING_TRIAGE_BUILT"
QUALITY_SCHEMA_VERSION = "trace_net_route_dispatch_warning_triage_v1_quality"

WARNING_CLASSIFICATION = {
    "blank_candidate_has_heavy_processing_evidence": {
        "warning_family": "blank_candidate_heavy_processing",
        "severity": "review_cleanup",
        "triage_label": "blank_candidate_heavy_processing_cleanup_needed",
        "recommended_action": "inspect_blank_candidate_heavy_artifacts_or_route_backfill",
    },
    "ocr_text_artifact_without_explicit_text_dispatch": {
        "warning_family": "ocr_text_dispatch_policy",
        "severity": "policy_advisory",
        "triage_label": "ocr_text_embedded_in_specialized_route",
        "recommended_action": "consider_text_secondary_dispatch_or_keep_as_embedded_text_evidence",
    },
    "retrieval_answer_artifact_without_explicit_text_dispatch": {
        "warning_family": "retrieval_answer_legacy_overlap",
        "severity": "legacy_advisory",
        "triage_label": "retrieval_answer_legacy_text_overlap",
        "recommended_action": "no_dispatch_change_required_until_answer_artifacts_are_rebuilt_from_dispatch",
    },
}


def _safe_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _classify_warning(warning: str) -> Dict[str, str]:
    fallback = {
        "warning_family": "unclassified_route_dispatch_warning",
        "severity": "review_advisory",
        "triage_label": "unclassified_route_dispatch_warning",
        "recommended_action": "inspect_warning_and_add_triage_policy",
    }
    return dict(WARNING_CLASSIFICATION.get(warning, fallback))


def _build_triage_card(card: Mapping[str, Any], warning: str) -> Dict[str, Any]:
    classification = _classify_warning(warning)
    page_id = card.get("page_id")
    page_number = card.get("page_number")
    triage_id = f"route_warning_triage::{page_id or 'unknown'}::{warning}"
    counts = card.get("artifact_evidence_category_counts") if isinstance(card.get("artifact_evidence_category_counts"), Mapping) else {}

    return {
        "schema_version": SCHEMA_VERSION,
        "warning_triage_card_id": triage_id,
        "page_id": page_id,
        "page_number": page_number,
        "primary_dispatch_route": card.get("primary_dispatch_route"),
        "allowed_dispatch_routes": list(card.get("allowed_dispatch_routes") or []),
        "review_processing_required": bool(card.get("review_processing_required")),
        "source_warning": warning,
        "warning_family": classification["warning_family"],
        "triage_label": classification["triage_label"],
        "triage_severity": classification["severity"],
        "recommended_action": classification["recommended_action"],
        "route_dispatch_coverage_status": card.get("route_dispatch_coverage_status"),
        "route_dispatch_warnings": list(card.get("route_dispatch_warnings") or []),
        "route_dispatch_advisory_flags": list(card.get("route_dispatch_advisory_flags") or []),
        "artifact_evidence_category_counts": dict(sorted((str(k), _safe_int(v)) for k, v in counts.items())),
        "table_evidence_artifact_count": _safe_int(card.get("table_evidence_artifact_count")),
        "image_visual_evidence_artifact_count": _safe_int(card.get("image_visual_evidence_artifact_count")),
        "ocr_text_evidence_artifact_count": _safe_int(card.get("ocr_text_evidence_artifact_count")),
        "retrieval_answer_evidence_artifact_count": _safe_int(card.get("retrieval_answer_evidence_artifact_count")),
        "blank_candidate_processing_allowed": bool(card.get("blank_candidate_processing_allowed")),
        "table_processing_allowed": bool(card.get("table_processing_allowed")),
        "image_visual_processing_allowed": bool(card.get("image_visual_processing_allowed")),
        "normal_text_processing_allowed": bool(card.get("normal_text_processing_allowed")),
        "unsafe_triage_card": False,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
    }


def build_route_dispatch_warning_triage_report(
    route_dispatch_coverage_audit_path: Path,
    output_dir: Path,
    thresholds: Optional[RouteDispatchWarningTriageQualityThresholds] = None,
    write_outputs: bool = True,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    coverage_audit = _read_json(route_dispatch_coverage_audit_path)

    triage_cards: List[Dict[str, Any]] = []
    unresolved_violation_cards: List[Dict[str, Any]] = []
    for coverage_card in coverage_audit.get("route_dispatch_coverage_cards") or []:
        if not isinstance(coverage_card, Mapping):
            continue
        for warning in coverage_card.get("route_dispatch_warnings") or []:
            triage_cards.append(_build_triage_card(coverage_card, str(warning)))
        violations = coverage_card.get("route_dispatch_violations") or []
        if violations:
            unresolved_violation_cards.append({
                "page_id": coverage_card.get("page_id"),
                "page_number": coverage_card.get("page_number"),
                "route_dispatch_violations": list(violations),
                "recommended_action": "resolve_dispatch_violation_before_downstream_enforcement",
                "unsafe_triage_card": False,
                "answer_permission": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
                "source_truth_mutations_performed": 0,
            })

    family_counts = Counter(card.get("warning_family") for card in triage_cards)
    severity_counts = Counter(card.get("triage_severity") for card in triage_cards)
    action_counts = Counter(card.get("recommended_action") for card in triage_cards)
    warning_counts = Counter(card.get("source_warning") for card in triage_cards)

    unsafe_count = sum(1 for card in triage_cards if card.get("unsafe_triage_card"))
    answer_permission_count = 0
    source_truth_mutation_allowed_count = 0

    coverage_summary = coverage_audit.get("summary") if isinstance(coverage_audit.get("summary"), Mapping) else {}
    summary: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "quality_status": PASS,
        "route_dispatch_coverage_audit_path": str(route_dispatch_coverage_audit_path),
        "route_dispatch_coverage_audit_quality_status": coverage_audit.get("quality_status") or coverage_summary.get("quality_status"),
        "coverage_audit_warning_card_count": _safe_int(coverage_summary.get("route_dispatch_warning_card_count")),
        "coverage_audit_violation_card_count": _safe_int(coverage_summary.get("route_dispatch_violation_card_count")),
        "warning_triage_card_count": len(triage_cards),
        "warning_instance_count": len(triage_cards),
        "blank_heavy_processing_triage_count": family_counts.get("blank_candidate_heavy_processing", 0),
        "ocr_text_dispatch_policy_triage_count": family_counts.get("ocr_text_dispatch_policy", 0),
        "retrieval_answer_legacy_overlap_triage_count": family_counts.get("retrieval_answer_legacy_overlap", 0),
        "unclassified_warning_triage_count": family_counts.get("unclassified_route_dispatch_warning", 0),
        "unresolved_violation_triage_count": len(unresolved_violation_cards),
        "warning_family_counts": dict(sorted((str(k), int(v)) for k, v in family_counts.items())),
        "warning_severity_counts": dict(sorted((str(k), int(v)) for k, v in severity_counts.items())),
        "warning_reason_counts": dict(sorted((str(k), int(v)) for k, v in warning_counts.items())),
        "recommended_action_counts": dict(sorted((str(k), int(v)) for k, v in action_counts.items())),
        "unsafe_triage_card_count": unsafe_count,
        "answer_permission_count": answer_permission_count,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "source_truth_mutations_performed": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }

    report: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "quality_status": PASS,
        "summary": summary,
        "warning_triage_cards": triage_cards,
        "unresolved_violation_triage_cards": unresolved_violation_cards,
    }

    thresholds = thresholds or RouteDispatchWarningTriageQualityThresholds()
    quality = evaluate_quality(report, thresholds)
    report["quality_status"] = quality["quality_status"]
    report["summary"]["quality_status"] = quality["quality_status"]
    report["summary"]["checks"] = quality.get("checks", {})
    report["summary"]["quality_fail_reasons"] = quality.get("quality_fail_reasons", [])

    if write_outputs:
        report_path = output_dir / "trace_net_route_dispatch_warning_triage_v1.json"
        quality_path = output_dir / "trace_net_route_dispatch_warning_triage_v1_quality.json"
        summary_path = output_dir / "trace_net_route_dispatch_warning_triage_v1_summary.json"
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        quality_path.write_text(json.dumps(quality, indent=2, sort_keys=True), encoding="utf-8")
        summary_path.write_text(json.dumps(report["summary"], indent=2, sort_keys=True), encoding="utf-8")
        report["report_path"] = str(report_path)
        report["quality_path"] = str(quality_path)

    return report


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Route Dispatch Warning Triage v1")
    parser.add_argument("--route-dispatch-coverage-audit", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--min-warning-triage-cards", type=int, default=1)
    parser.add_argument("--max-unsafe-triage-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-route-dispatch-coverage-audit-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> Dict[str, Any]:
    args = _parse_args(argv)
    thresholds = RouteDispatchWarningTriageQualityThresholds(
        min_warning_triage_cards=args.min_warning_triage_cards,
        max_unsafe_triage_cards=args.max_unsafe_triage_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_route_dispatch_coverage_audit_quality_pass=args.require_route_dispatch_coverage_audit_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    report = build_route_dispatch_warning_triage_report(
        route_dispatch_coverage_audit_path=args.route_dispatch_coverage_audit,
        output_dir=args.output_dir,
        thresholds=thresholds,
    )

    print("TRACE-Net Route Dispatch Warning Triage v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    summary = report.get("summary", {})
    for key in [
        "warning_triage_card_count",
        "warning_instance_count",
        "blank_heavy_processing_triage_count",
        "ocr_text_dispatch_policy_triage_count",
        "retrieval_answer_legacy_overlap_triage_count",
        "unresolved_violation_triage_count",
        "unsafe_triage_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    if report.get("report_path"):
        print(f" report_path: {report.get('report_path')}")
        print(f" quality_path: {report.get('quality_path')}")
    return report


if __name__ == "__main__":
    main()
