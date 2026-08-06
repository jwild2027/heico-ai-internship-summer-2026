from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

MODULE = "trace_net_e2e_calibrated_cascade_route_brain_v35_3"
VERSION = "v35.3.1"
STATUS_READY = "E2E_CALIBRATED_CASCADE_ROUTE_BRAIN_READY"
ROUTES = ("blank_candidate", "normal_text", "table", "image_visual")
VISUAL_CONTEXT_ACTIONS = {"accept_route"}
VISUAL_REVIEW_ACTIONS = {"dual_route_text_and_visual", "dual_route_table_and_visual", "review_required", "retry_with_preprocessing"}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        raise FileNotFoundError(f"JSONL file not found: {path}")
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def _load_feature_records(feature_audit_report: Optional[Path], feature_records_jsonl: Optional[Path]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    audit_report: Dict[str, Any] = {}
    if feature_audit_report:
        if not feature_audit_report.exists():
            raise FileNotFoundError(f"feature audit report not found: {feature_audit_report}")
        audit_report = json.loads(feature_audit_report.read_text(encoding="utf-8"))
        if feature_records_jsonl is None:
            feature_records_jsonl = Path(audit_report["feature_records_jsonl_path"])
    if feature_records_jsonl is None:
        raise ValueError("Either --feature-audit-report or --feature-records-jsonl is required")
    return _read_jsonl(feature_records_jsonl), audit_report


def _ordered_scores(scores: Dict[str, Any]) -> List[Tuple[str, float]]:
    clean = {r: _safe_float(scores.get(r)) for r in ROUTES}
    return sorted(clean.items(), key=lambda kv: kv[1], reverse=True)


def _route_decision(record: Dict[str, Any]) -> Dict[str, Any]:
    scores = record.get("route_scores") or {}
    ordered = _ordered_scores(scores)
    primary, top_score = ordered[0]
    second_route, second_score = ordered[1]
    margin = round(top_score - second_score, 4)
    features = record.get("feature_summary") or {}

    image_score = _safe_float(scores.get("image_visual"))
    table_score = _safe_float(scores.get("table"))
    text_score = _safe_float(scores.get("normal_text"))
    blank_score = _safe_float(scores.get("blank_candidate"))
    ink_density = _safe_float(features.get("ink_density"))
    edge_density = _safe_float(features.get("edge_density"))

    secondary_routes: List[str] = []
    reasons: List[str] = []
    action = "accept_route"
    review_required = False
    retry_required = False

    # Preserve v35.2 high-recall image behavior, but express uncertainty as explicit fishnet actions.
    close_or_low = bool(record.get("fishnet_uncertain")) or margin < 0.12 or top_score < 0.35

    if primary == "image_visual":
        if table_score >= 0.45 and (image_score - table_score) <= 0.20:
            action = "dual_route_table_and_visual"
            secondary_routes.append("table")
            review_required = True
            reasons.append("table_score_competes_with_image_visual")
        elif text_score >= 0.50 and (image_score - text_score) <= 0.20:
            action = "dual_route_text_and_visual"
            secondary_routes.append("normal_text")
            review_required = True
            reasons.append("text_score_competes_with_image_visual")
        elif close_or_low:
            action = "review_required"
            review_required = True
            reasons.append("close_or_low_route_score_margin")
    elif primary == "table" and image_score >= 0.48 and (table_score - image_score) <= 0.20:
        action = "dual_route_table_and_visual"
        secondary_routes.append("image_visual")
        review_required = True
        reasons.append("image_visual_score_competes_with_table")
    elif primary == "normal_text" and image_score >= 0.52 and (text_score - image_score) <= 0.20:
        action = "dual_route_text_and_visual"
        secondary_routes.append("image_visual")
        review_required = True
        reasons.append("image_visual_score_competes_with_normal_text")
    elif primary == "blank_candidate" and (ink_density > 0.015 or edge_density > 0.06) and blank_score < 0.90:
        action = "retry_with_preprocessing"
        review_required = True
        retry_required = True
        reasons.append("blank_candidate_has_nontrivial_ink_or_edges")
    elif close_or_low:
        action = "review_required"
        review_required = True
        reasons.append("close_or_low_route_score_margin")

    for r, s in ordered[1:]:
        if r not in secondary_routes and s >= 0.50 and (top_score - s) <= 0.20:
            secondary_routes.append(r)

    # v35.3.1 separates operational visual context dispatch from fishnet review.
    # A page is eligible for expensive image/diagram context only when the calibrated
    # primary route is image_visual. Competing secondary image routes stay in the
    # review queue instead of inflating the image-context set.
    visual_context_eligible = primary == "image_visual"
    fishnet_visual_review_candidate = visual_context_eligible or "image_visual" in secondary_routes

    dispatch_routes = [primary]
    if visual_context_eligible and "image_visual" not in dispatch_routes:
        dispatch_routes.append("image_visual")
    # Do not add secondary image_visual to dispatch_routes unless it is the primary route.
    # Secondary image routes remain fishnet review candidates only.
    for r in secondary_routes:
        if r == "image_visual" and not visual_context_eligible:
            continue
        if r not in dispatch_routes:
            dispatch_routes.append(r)
    if review_required and "review" not in dispatch_routes:
        dispatch_routes.append("review")

    manual_is_diagram = bool(record.get("manual_diagram_page"))
    predicted_visual = visual_context_eligible
    if manual_is_diagram and not predicted_visual:
        reasons.append("audit_label_diagram_not_visual_context_eligible")
    if (not manual_is_diagram) and predicted_visual:
        reasons.append("audit_label_non_diagram_visual_context_eligible")

    route_confidence = round(top_score, 4)
    return {
        "schema_version": "trace_net_calibrated_cascade_route_brain_v35_3_decision",
        "page_id": record.get("page_id"),
        "page_number": record.get("page_number"),
        "filename": record.get("filename"),
        "source_feature_record_schema": record.get("schema_version"),
        "manual_label": record.get("manual_label"),
        "manual_diagram_page": manual_is_diagram,
        "manifest_primary_route": record.get("manifest_primary_route"),
        "manifest_routes": record.get("manifest_routes") or [],
        "feature_predicted_primary_route": record.get("predicted_primary_route"),
        "primary_route": primary,
        "secondary_routes": secondary_routes,
        "dispatch_routes": dispatch_routes,
        "visual_context_eligible": visual_context_eligible,
        "fishnet_visual_review_candidate": fishnet_visual_review_candidate,
        "route_scores": {r: round(_safe_float((record.get("route_scores") or {}).get(r)), 4) for r in ROUTES},
        "route_confidence": route_confidence,
        "route_margin": margin,
        "fishnet_action": action,
        "fishnet_reasons": reasons,
        "review_required": review_required,
        "retry_required": retry_required,
        "predicted_visual": predicted_visual,
        "prediction_matches_manual_diagram_binary": predicted_visual == manual_is_diagram,
        "feature_summary": record.get("feature_summary") or {},
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "visual_proof_authority": False,
        "database_writes_allowed": False,
    }


def _binary_metrics(decisions: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    tp = fp = tn = fn = 0
    for d in decisions:
        actual = bool(d.get("manual_diagram_page"))
        pred = bool(d.get("predicted_visual"))
        if actual and pred:
            tp += 1
        elif actual and not pred:
            fn += 1
        elif not actual and pred:
            fp += 1
        else:
            tn += 1
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    accuracy = (tp + tn) / max(1, len(decisions))
    return {
        "true_positive_diagram_predicted_visual": tp,
        "false_negative_diagram_predicted_non_visual": fn,
        "false_positive_non_diagram_predicted_visual": fp,
        "true_negative_non_diagram_predicted_non_visual": tn,
        "total": len(decisions),
        "diagram_precision": round(precision, 4),
        "diagram_recall": round(recall, 4),
        "binary_accuracy": round(accuracy, 4),
    }


def quality_checks(report: Dict[str, Any], args: Any) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []

    def add(name: str, observed: Any, expected: str, passed: bool) -> None:
        checks.append({"name": name, "observed": observed, "expected": expected, "passed": bool(passed)})

    add("source_page_count", report.get("source_page_count"), f">= {args.min_source_pages}", report.get("source_page_count", 0) >= args.min_source_pages)
    add("route_decision_count", report.get("route_decision_count"), f">= {args.min_route_decisions}", report.get("route_decision_count", 0) >= args.min_route_decisions)
    add("actual_diagram_page_count", report.get("actual_diagram_page_count"), f">= {args.min_actual_diagram_pages}", report.get("actual_diagram_page_count", 0) >= args.min_actual_diagram_pages)
    add("diagram_recall", report.get("diagram_recall"), f">= {args.min_diagram_recall}", _safe_float(report.get("diagram_recall")) >= args.min_diagram_recall)
    add("diagram_precision", report.get("diagram_precision"), f">= {args.min_diagram_precision}", _safe_float(report.get("diagram_precision")) >= args.min_diagram_precision)
    add("false_negative_diagram_count", report.get("false_negative_diagram_count"), f"<= {args.max_false_negative_diagram_count}", report.get("false_negative_diagram_count", 0) <= args.max_false_negative_diagram_count)
    add("fishnet_review_queue_count", report.get("fishnet_review_queue_count"), f">= {args.min_fishnet_review_queue_count}", report.get("fishnet_review_queue_count", 0) >= args.min_fishnet_review_queue_count)
    add("answer_permission_count", report.get("answer_permission_count"), f"<= {args.max_answer_permission_count}", report.get("answer_permission_count", 0) <= args.max_answer_permission_count)
    add("source_truth_mutation_allowed_count", report.get("source_truth_mutation_allowed_count"), f"<= {args.max_source_truth_mutation_allowed}", report.get("source_truth_mutation_allowed_count", 0) <= args.max_source_truth_mutation_allowed)
    if args.require_no_answer_permission:
        add("require_no_answer_permission", report.get("answer_permission_count"), "== 0", report.get("answer_permission_count", 0) == 0)
    return checks


def build_calibrated_route_brain(
    *,
    feature_audit_report: Optional[Path],
    feature_records_jsonl: Optional[Path],
    output_dir: Path,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    records, audit_report = _load_feature_records(feature_audit_report, feature_records_jsonl)
    decisions = [_route_decision(r) for r in records]
    metrics = _binary_metrics(decisions)

    decisions_path = output_dir / "trace_net_cascade_route_decisions_v35_3.jsonl"
    review_path = output_dir / "trace_net_fishnet_review_queue_v35_3.jsonl"
    manifest_path = output_dir / "trace_net_cascade_route_manifest_v35_3.json"
    report_path = output_dir / "trace_net_calibrated_cascade_route_brain_v35_3.json"
    inspect_md_path = output_dir / "trace_net_calibrated_cascade_route_brain_v35_3.md"

    review_rows = [d for d in decisions if d.get("review_required") or d.get("retry_required")]
    _write_jsonl(decisions_path, decisions)
    _write_jsonl(review_path, review_rows)

    route_counts = Counter(d.get("primary_route") for d in decisions)
    action_counts = Counter(d.get("fishnet_action") for d in decisions)
    dispatch_visual_count = sum(1 for d in decisions if d.get("visual_context_eligible"))
    fishnet_visual_review_candidate_count = sum(1 for d in decisions if d.get("fishnet_visual_review_candidate") and not d.get("visual_context_eligible"))
    actual_diagram_count = sum(1 for d in decisions if d.get("manual_diagram_page"))

    manifest = {
        "schema_version": "trace_net_cascade_route_manifest_v35_3",
        "module": MODULE,
        "version": VERSION,
        "source_feature_audit_report_path": str(feature_audit_report) if feature_audit_report else None,
        "source_feature_records_jsonl_path": str(feature_records_jsonl or (audit_report.get("feature_records_jsonl_path") if audit_report else "")),
        "route_decision_count": len(decisions),
        "primary_route_counts": dict(sorted(route_counts.items())),
        "fishnet_action_counts": dict(sorted(action_counts.items())),
        "dispatch_visual_count": dispatch_visual_count,
        "fishnet_visual_review_candidate_count": fishnet_visual_review_candidate_count,
        "fishnet_review_queue_count": len(review_rows),
        "decisions_jsonl_path": str(decisions_path),
        "review_queue_jsonl_path": str(review_path),
        "contract": {
            "cascade_route_manifest_only": True,
            "manual_labels_used_for_evaluation_not_proof": True,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
            "database_writes": False,
            "llava_called": False,
            "gemma_called": False,
        },
        "route_decisions": decisions,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    report = {
        "schema_version": "trace_net_calibrated_cascade_route_brain_v35_3_report",
        "module": MODULE,
        "version": VERSION,
        "status": STATUS_READY,
        "quality_status": "UNKNOWN",
        "source_page_count": len(records),
        "feature_record_count": len(records),
        "route_decision_count": len(decisions),
        "actual_diagram_page_count": actual_diagram_count,
        "primary_route_counts": dict(sorted(route_counts.items())),
        "fishnet_action_counts": dict(sorted(action_counts.items())),
        "dispatch_visual_count": dispatch_visual_count,
        "fishnet_visual_review_candidate_count": fishnet_visual_review_candidate_count,
        "fishnet_review_queue_count": len(review_rows),
        "diagram_precision": metrics["diagram_precision"],
        "diagram_recall": metrics["diagram_recall"],
        "binary_accuracy": metrics["binary_accuracy"],
        "false_negative_diagram_count": metrics["false_negative_diagram_predicted_non_visual"],
        "false_positive_non_diagram_count": metrics["false_positive_non_diagram_predicted_visual"],
        "binary_diagram_confusion_matrix": metrics,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "visual_proof_authority_violation_count": 0,
        "contract": manifest["contract"],
        "manifest_path": str(manifest_path),
        "decisions_jsonl_path": str(decisions_path),
        "fishnet_review_queue_jsonl_path": str(review_path),
        "report_path": str(report_path),
        "inspect_md_path": str(inspect_md_path),
        "sample_decisions": decisions[:10],
        "sample_review_queue": review_rows[:10],
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    inspect_md_path.write_text(_render_markdown(report), encoding="utf-8")
    return report


def _render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# TRACE-Net Calibrated Cascade Route Brain v35.3",
        "",
        f"Quality status: **{report.get('quality_status')}**",
        f"Status: `{report.get('status')}`",
        "",
        "## Summary",
    ]
    for k in [
        "source_page_count", "route_decision_count", "actual_diagram_page_count", "primary_route_counts",
        "fishnet_action_counts", "dispatch_visual_count", "fishnet_visual_review_candidate_count", "fishnet_review_queue_count",
        "diagram_precision", "diagram_recall", "binary_accuracy", "false_negative_diagram_count",
        "false_positive_non_diagram_count", "answer_permission_count", "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {k}: {report.get(k)}")
    lines += ["", "## Contract", "- This stage creates an operational route manifest from v35.2 features.", "- Manual labels are used for evaluation/calibration metrics only, not answer proof.", "- No LLaVA/Gemma calls, database writes, source-truth mutation, or answer permission.", ""]
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="TRACE-Net Calibrated Cascade Route Brain v35.3")
    p.add_argument("--feature-audit-report", type=Path, default=None)
    p.add_argument("--feature-records-jsonl", type=Path, default=None)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--min-source-pages", type=int, default=1)
    p.add_argument("--min-route-decisions", type=int, default=1)
    p.add_argument("--min-actual-diagram-pages", type=int, default=1)
    p.add_argument("--min-diagram-recall", type=float, default=0.0)
    p.add_argument("--min-diagram-precision", type=float, default=0.0)
    p.add_argument("--max-false-negative-diagram-count", type=int, default=999999)
    p.add_argument("--min-fishnet-review-queue-count", type=int, default=0)
    p.add_argument("--max-answer-permission-count", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--quality", action="store_true")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    report = build_calibrated_route_brain(
        feature_audit_report=args.feature_audit_report,
        feature_records_jsonl=args.feature_records_jsonl,
        output_dir=args.output_dir,
    )
    checks = quality_checks(report, args)
    quality_status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    report["quality_status"] = quality_status
    report["quality_checks"] = checks
    Path(report["report_path"]).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    Path(report["inspect_md_path"]).write_text(_render_markdown(report), encoding="utf-8")

    print("TRACE-Net Calibrated Cascade Route Brain v35.3")
    print(f" Status: {report['status']}")
    print(f" Quality status: {quality_status}")
    for k in [
        "source_page_count", "route_decision_count", "actual_diagram_page_count", "primary_route_counts",
        "fishnet_action_counts", "dispatch_visual_count", "fishnet_visual_review_candidate_count", "fishnet_review_queue_count",
        "diagram_precision", "diagram_recall", "binary_accuracy", "false_negative_diagram_count",
        "false_positive_non_diagram_count", "answer_permission_count", "source_truth_mutation_allowed_count",
    ]:
        print(f" {k}: {report.get(k)}")
    print(f" report_path: {report['report_path']}")
    print(f" manifest_path: {report['manifest_path']}")
    print(f" decisions_jsonl_path: {report['decisions_jsonl_path']}")
    print(f" fishnet_review_queue_jsonl_path: {report['fishnet_review_queue_jsonl_path']}")
    return 0 if (not args.quality or quality_status == "PASS") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
