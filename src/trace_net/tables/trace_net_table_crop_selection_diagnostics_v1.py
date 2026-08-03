"""TRACE-Net Table Crop Selection Diagnostics v1.

Read-only diagnostic module for comparing whole-page morphology against table-region
crop morphology after OCR-enriched bbox routing. The module does not mutate source
truth and does not grant answer/proof authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "trace_net_table_crop_selection_diagnostics_v1"
QUALITY_SCHEMA_VERSION = "trace_net_table_crop_selection_diagnostics_v1_quality"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return payload


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, sort_keys=True) + "\n")


def stable_id(prefix: str, *parts: Any, length: int = 14) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(str(part or "").encode("utf-8"))
        h.update(b"\0")
    return f"{prefix}_{h.hexdigest()[:length]}"


def as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def as_bool(value: Any) -> bool:
    return bool(value) if value is not None else False


def as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def get_cards(payload: Mapping[str, Any], *candidate_keys: str) -> List[Dict[str, Any]]:
    for key in candidate_keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [v for v in value if isinstance(v, dict)]
    return []


def table_key(page_id: Any, table_id: Any) -> Tuple[str, str]:
    return (str(page_id or ""), str(table_id or ""))


def index_by_page_table(cards: Sequence[Mapping[str, Any]]) -> Dict[Tuple[str, str], Mapping[str, Any]]:
    out: Dict[Tuple[str, str], Mapping[str, Any]] = {}
    for card in cards:
        key = table_key(card.get("page_id"), card.get("table_id"))
        if any(key):
            out[key] = card
    return out


def counter_to_dict(counter: Counter) -> Dict[str, int]:
    return {str(k): int(v) for k, v in sorted(counter.items(), key=lambda kv: str(kv[0]))}


def quality_status(payload: Mapping[str, Any]) -> str:
    return str(payload.get("quality_status") or payload.get("summary", {}).get("quality_status") or "UNKNOWN")


def summarize_safety(records: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    return {
        "unsafe_diagnostic_card_count": sum(1 for r in records if r.get("unsafe_diagnostic_card")),
        "answer_permission_count": sum(1 for r in records if r.get("answer_permission") is True),
        "can_answer_directly_count": sum(1 for r in records if r.get("can_answer_directly") is True),
        "can_prove_claims_count": sum(1 for r in records if r.get("can_prove_claims") is True),
        "source_truth_mutation_allowed_count": sum(1 for r in records if r.get("source_truth_mutation_allowed") is True),
        "postgres_write_attempt_count": sum(as_int(r.get("postgres_write_attempt_count"), 0) for r in records),
        "qdrant_write_attempt_count": sum(as_int(r.get("qdrant_write_attempt_count"), 0) for r in records),
        "opensearch_write_attempt_count": sum(as_int(r.get("opensearch_write_attempt_count"), 0) for r in records),
    }


def classify_crop_decision(card: Mapping[str, Any], bbox: Optional[Mapping[str, Any]], ocr: Optional[Mapping[str, Any]]) -> Tuple[str, List[str], List[str]]:
    """Return decision bucket, findings, recommended actions."""
    selected_scope = card.get("selected_morphology_scope") or "unknown"
    crop_available = as_bool(card.get("table_region_crop_available"))
    crop_applied = as_bool(card.get("table_region_crop_applied"))
    crop_selected = selected_scope == "table_region_crop"
    signal = card.get("morphology_signal_strength") or "UNKNOWN"
    h = as_int(card.get("horizontal_line_count"), 0)
    v = as_int(card.get("vertical_line_count"), 0)
    intersections = as_int(card.get("intersection_count"), 0)
    review_flags = set(str(x) for x in as_list(card.get("review_flags")))

    findings: List[str] = []
    actions: List[str] = []

    if not crop_available:
        findings.append("crop_not_available")
        actions.append("resolve_or_generate_table_region_bbox")
        return "no_crop_available", findings, actions
    if crop_available and not crop_applied:
        findings.append("crop_available_but_not_applied")
        actions.append("debug_crop_application_path")
        return "crop_available_not_applied", findings, actions

    bbox_source = None
    bbox_coverage = None
    bbox_conf = None
    if bbox:
        bbox_source = bbox.get("bbox_source")
        bbox_coverage = as_float(bbox.get("bbox_coverage_ratio"))
        bbox_conf = as_float(bbox.get("bbox_confidence"))
    if ocr:
        if ocr.get("bbox_source") and not bbox_source:
            bbox_source = ocr.get("bbox_source")
        if bbox_coverage is None:
            bbox_coverage = as_float(ocr.get("bbox_coverage_ratio"))
        if bbox_conf is None:
            bbox_conf = as_float(ocr.get("bbox_confidence"))

    if bbox_coverage is not None and bbox_coverage >= 0.80:
        findings.append("bbox_is_broad_page_like")
        actions.append("tighten_ocr_bbox_crop_to_content_band")
    if bbox_conf is not None and bbox_conf < 0.70:
        findings.append("bbox_confidence_below_0_70")
        actions.append("improve_bbox_confidence_before_preferring_crop")
    if bbox_source:
        findings.append(f"bbox_source::{bbox_source}")

    if crop_selected:
        findings.append("crop_selected_over_page")
        if signal in {"GRID", "PARTIAL_GRID"} and intersections > 0:
            actions.append("keep_crop_preference_for_intersecting_grid_cases")
            return "crop_selected_strong_grid", findings, actions
        if signal in {"WEAK_LINE_SIGNAL", "NO_LINE_SIGNAL"} or v == 0 or intersections == 0:
            findings.append("crop_selected_but_still_weak_or_no_intersections")
            actions.append("tune_crop_scoring_to_require_vertical_or_intersection_gain")
            return "crop_selected_but_weak", findings, actions
        return "crop_selected_needs_review", findings, actions

    findings.append("page_selected_over_crop")
    if crop_applied:
        findings.append("crop_was_tested_but_page_won")
    if "visual_row_count_mismatch_with_ocr_fallback" in review_flags:
        findings.append("visual_row_count_mismatch_with_ocr_fallback")
        actions.append("compare_crop_and_page_row_estimates_against_ocr_rows")
    if signal == "GRID":
        actions.append("keep_page_preference_for_page_grid_cases")
        return "page_selected_grid", findings, actions
    if signal in {"PARTIAL_GRID", "WEAK_LINE_SIGNAL", "NO_LINE_SIGNAL"}:
        actions.append("improve_crop_bbox_tightness_or_line_thresholds")
        return "page_selected_weak_or_partial", findings, actions
    return "page_selected_needs_review", findings, actions


def build_diagnostic_cards(
    *,
    table_line_geometry_payload: Mapping[str, Any],
    table_bbox_resolver_payload: Optional[Mapping[str, Any]] = None,
    table_ocr_bbox_enrichment_payload: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    geometry_cards = get_cards(table_line_geometry_payload, "table_geometry_cards", "records")
    bbox_cards = get_cards(table_bbox_resolver_payload or {}, "table_bbox_cards", "records")
    ocr_cards = get_cards(table_ocr_bbox_enrichment_payload or {}, "table_ocr_bbox_enrichment_cards", "records")

    bbox_index = index_by_page_table(bbox_cards)
    ocr_index = index_by_page_table(ocr_cards)
    cards: List[Dict[str, Any]] = []

    for geom in geometry_cards:
        page_id = geom.get("page_id")
        table_id = geom.get("table_id")
        key = table_key(page_id, table_id)
        bbox = bbox_index.get(key)
        ocr = ocr_index.get(key)
        bucket, findings, actions = classify_crop_decision(geom, bbox, ocr)

        selected_scope = geom.get("selected_morphology_scope") or "unknown"
        crop_selected = selected_scope == "table_region_crop"
        crop_available = as_bool(geom.get("table_region_crop_available"))
        crop_applied = as_bool(geom.get("table_region_crop_applied"))

        record: Dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "diagnostic_card_id": stable_id("crop_diag", page_id, table_id, selected_scope),
            "page_id": page_id,
            "table_id": table_id,
            "table_type": geom.get("table_type"),
            "selected_morphology_scope": selected_scope,
            "crop_selected": crop_selected,
            "table_region_crop_available": crop_available,
            "table_region_crop_applied": crop_applied,
            "crop_decision_bucket": bucket,
            "crop_decision_findings": sorted(set(findings)),
            "recommended_actions": sorted(set(actions)),
            "table_region_bbox_source": geom.get("table_region_bbox_source"),
            "table_region_bbox": geom.get("table_region_bbox"),
            "horizontal_line_count": as_int(geom.get("horizontal_line_count"), 0),
            "vertical_line_count": as_int(geom.get("vertical_line_count"), 0),
            "intersection_count": as_int(geom.get("intersection_count"), 0),
            "morphology_signal_strength": geom.get("morphology_signal_strength"),
            "morphology_quality_score": as_float(geom.get("morphology_quality_score")),
            "geometry_confidence": as_float(geom.get("geometry_confidence")),
            "review_required": as_bool(geom.get("review_required")),
            "review_flags": as_list(geom.get("review_flags")),
            "source_geometry_card_id": geom.get("geometry_card_id"),
            "bbox_resolver_available": bbox is not None,
            "bbox_source": bbox.get("bbox_source") if bbox else None,
            "bbox_confidence": as_float(bbox.get("bbox_confidence")) if bbox else None,
            "bbox_coverage_ratio": as_float(bbox.get("bbox_coverage_ratio")) if bbox else None,
            "bbox_review_required": as_bool(bbox.get("review_required")) if bbox else False,
            "ocr_bbox_enrichment_available": ocr is not None,
            "ocr_bbox_source": ocr.get("bbox_source") if ocr else None,
            "ocr_bbox_confidence": as_float(ocr.get("bbox_confidence")) if ocr else None,
            "ocr_bbox_coverage_ratio": as_float(ocr.get("bbox_coverage_ratio")) if ocr else None,
            "ocr_matched_bbox_count": as_int(ocr.get("matched_ocr_bbox_count"), 0) if ocr else 0,
            "ocr_part_number_match_count": as_int(ocr.get("part_number_ocr_match_count"), 0) if ocr else 0,
            "unsafe_diagnostic_card": False,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "retrieval_only_answer_allowed": False,
            "source_truth_mutation_allowed": False,
            "source_truth_mutations_performed": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        }
        cards.append(record)
    return cards


def build_summary(
    *,
    cards: Sequence[Mapping[str, Any]],
    table_line_geometry_payload: Mapping[str, Any],
    table_bbox_resolver_payload: Optional[Mapping[str, Any]],
    table_ocr_bbox_enrichment_payload: Optional[Mapping[str, Any]],
    thresholds: Mapping[str, Any],
) -> Dict[str, Any]:
    safety = summarize_safety(cards)
    quality_fail_reasons: List[str] = []

    crop_selected = sum(1 for c in cards if c.get("selected_morphology_scope") == "table_region_crop")
    page_selected = sum(1 for c in cards if c.get("selected_morphology_scope") == "page")
    crop_available = sum(1 for c in cards if c.get("table_region_crop_available"))
    crop_applied = sum(1 for c in cards if c.get("table_region_crop_applied"))
    weak_selected_crop = sum(1 for c in cards if c.get("crop_decision_bucket") == "crop_selected_but_weak")
    page_grid = sum(1 for c in cards if c.get("crop_decision_bucket") == "page_selected_grid")
    broad_bbox = sum(1 for c in cards if "bbox_is_broad_page_like" in (c.get("crop_decision_findings") or []))

    min_cards = as_int(thresholds.get("min_diagnostic_cards"), 1)
    min_crop_selected = as_int(thresholds.get("min_crop_selected_cards"), 0)
    min_page_selected = as_int(thresholds.get("min_page_selected_cards"), 0)
    max_unsafe = as_int(thresholds.get("max_unsafe_diagnostic_cards"), 0)
    max_answer_permission = as_int(thresholds.get("max_answer_permission_count"), 0)
    max_source_mut = as_int(thresholds.get("max_source_truth_mutation_allowed"), 0)

    if len(cards) < min_cards:
        quality_fail_reasons.append("min_diagnostic_cards_not_met")
    if crop_selected < min_crop_selected:
        quality_fail_reasons.append("min_crop_selected_cards_not_met")
    if page_selected < min_page_selected:
        quality_fail_reasons.append("min_page_selected_cards_not_met")
    if safety["unsafe_diagnostic_card_count"] > max_unsafe:
        quality_fail_reasons.append("max_unsafe_diagnostic_cards_exceeded")
    if safety["answer_permission_count"] > max_answer_permission:
        quality_fail_reasons.append("max_answer_permission_count_exceeded")
    if safety["source_truth_mutation_allowed_count"] > max_source_mut:
        quality_fail_reasons.append("max_source_truth_mutation_allowed_exceeded")

    if thresholds.get("require_table_line_geometry_quality_pass") and quality_status(table_line_geometry_payload) != "PASS":
        quality_fail_reasons.append("table_line_geometry_quality_not_pass")
    if thresholds.get("require_table_bbox_resolver_quality_pass") and quality_status(table_bbox_resolver_payload or {}) != "PASS":
        quality_fail_reasons.append("table_bbox_resolver_quality_not_pass")
    if thresholds.get("require_table_ocr_bbox_enrichment_quality_pass") and quality_status(table_ocr_bbox_enrichment_payload or {}) != "PASS":
        quality_fail_reasons.append("table_ocr_bbox_enrichment_quality_not_pass")
    if thresholds.get("require_no_answer_permission") and safety["answer_permission_count"]:
        quality_fail_reasons.append("answer_permission_present")

    summary: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS" if not quality_fail_reasons else "FAIL",
        "quality_status": "PASS" if not quality_fail_reasons else "FAIL",
        "quality_fail_reasons": quality_fail_reasons,
        "diagnostic_card_count": len(cards),
        "crop_selected_card_count": crop_selected,
        "page_selected_card_count": page_selected,
        "crop_available_card_count": crop_available,
        "crop_applied_card_count": crop_applied,
        "crop_selected_but_weak_card_count": weak_selected_crop,
        "page_selected_grid_card_count": page_grid,
        "broad_bbox_candidate_card_count": broad_bbox,
        "review_required_card_count": sum(1 for c in cards if c.get("review_required")),
        "table_line_geometry_quality_status": quality_status(table_line_geometry_payload),
        "table_bbox_resolver_quality_status": quality_status(table_bbox_resolver_payload or {}),
        "table_ocr_bbox_enrichment_quality_status": quality_status(table_ocr_bbox_enrichment_payload or {}),
        "selected_morphology_scope_counts": counter_to_dict(Counter(c.get("selected_morphology_scope") for c in cards)),
        "crop_decision_bucket_counts": counter_to_dict(Counter(c.get("crop_decision_bucket") for c in cards)),
        "morphology_signal_strength_counts": counter_to_dict(Counter(c.get("morphology_signal_strength") for c in cards)),
        "bbox_source_counts": counter_to_dict(Counter(c.get("bbox_source") for c in cards)),
        "ocr_bbox_source_counts": counter_to_dict(Counter(c.get("ocr_bbox_source") for c in cards)),
        "review_flag_counts": counter_to_dict(Counter(flag for c in cards for flag in as_list(c.get("review_flags")))),
        "recommended_action_counts": counter_to_dict(Counter(action for c in cards for action in as_list(c.get("recommended_actions")))),
        **safety,
    }
    return summary


def build_report(
    *,
    table_line_geometry_path: Path,
    table_bbox_resolver_path: Optional[Path],
    table_ocr_bbox_enrichment_path: Optional[Path],
    thresholds: Mapping[str, Any],
) -> Dict[str, Any]:
    table_line_geometry_payload = read_json(table_line_geometry_path)
    table_bbox_resolver_payload = read_json(table_bbox_resolver_path) if table_bbox_resolver_path else None
    table_ocr_bbox_enrichment_payload = read_json(table_ocr_bbox_enrichment_path) if table_ocr_bbox_enrichment_path else None

    cards = build_diagnostic_cards(
        table_line_geometry_payload=table_line_geometry_payload,
        table_bbox_resolver_payload=table_bbox_resolver_payload,
        table_ocr_bbox_enrichment_payload=table_ocr_bbox_enrichment_payload,
    )
    summary = build_summary(
        cards=cards,
        table_line_geometry_payload=table_line_geometry_payload,
        table_bbox_resolver_payload=table_bbox_resolver_payload,
        table_ocr_bbox_enrichment_payload=table_ocr_bbox_enrichment_payload,
        thresholds=thresholds,
    )
    report: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "status": "TABLE_CROP_SELECTION_DIAGNOSTICS_BUILT" if summary["quality_status"] == "PASS" else "TABLE_CROP_SELECTION_DIAGNOSTICS_NOT_READY",
        "quality_status": summary["quality_status"],
        "summary": summary,
        "thresholds": dict(thresholds),
        "source_artifacts": {
            "table_line_geometry": str(table_line_geometry_path),
            "table_bbox_resolver": str(table_bbox_resolver_path) if table_bbox_resolver_path else None,
            "table_ocr_bbox_enrichment": str(table_ocr_bbox_enrichment_path) if table_ocr_bbox_enrichment_path else None,
        },
        "safety_contract": {
            "diagnostics_are_advisory_only": True,
            "no_answer_permission": True,
            "no_claim_proof_authority": True,
            "no_source_truth_mutation": True,
            "no_postgres_writes": True,
            "no_qdrant_writes": True,
            "no_opensearch_writes": True,
        },
        "diagnostic_cards": cards,
    }
    return report


def build_quality_payload(report: Mapping[str, Any]) -> Dict[str, Any]:
    summary = dict(report.get("summary") or {})
    checks = {
        "schema_version_ok": report.get("schema_version") == SCHEMA_VERSION,
        "quality_status_pass": report.get("quality_status") == "PASS",
        "diagnostic_cards_present": summary.get("diagnostic_card_count", 0) > 0,
        "crop_selection_observed": summary.get("crop_selected_card_count", 0) >= 0,
        "runtime_is_read_only": True,
        "answer_permission_zero": summary.get("answer_permission_count", 0) == 0,
        "can_answer_directly_zero": summary.get("can_answer_directly_count", 0) == 0,
        "can_prove_claims_zero": summary.get("can_prove_claims_count", 0) == 0,
        "source_truth_mutation_allowed_zero": summary.get("source_truth_mutation_allowed_count", 0) == 0,
        "write_attempts_zero": (
            summary.get("postgres_write_attempt_count", 0) == 0
            and summary.get("qdrant_write_attempt_count", 0) == 0
            and summary.get("opensearch_write_attempt_count", 0) == 0
        ),
    }
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "generated_at": utc_now(),
        "status": "PASS" if all(checks.values()) and report.get("quality_status") == "PASS" else "FAIL",
        "quality_status": "PASS" if all(checks.values()) and report.get("quality_status") == "PASS" else "FAIL",
        "summary": summary,
        "checks": checks,
    }


def thresholds_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "min_diagnostic_cards": args.min_diagnostic_cards,
        "min_crop_selected_cards": args.min_crop_selected_cards,
        "min_page_selected_cards": args.min_page_selected_cards,
        "max_unsafe_diagnostic_cards": args.max_unsafe_diagnostic_cards,
        "max_answer_permission_count": args.max_answer_permission_count,
        "max_source_truth_mutation_allowed": args.max_source_truth_mutation_allowed,
        "require_table_line_geometry_quality_pass": args.require_table_line_geometry_quality_pass,
        "require_table_bbox_resolver_quality_pass": args.require_table_bbox_resolver_quality_pass,
        "require_table_ocr_bbox_enrichment_quality_pass": args.require_table_ocr_bbox_enrichment_quality_pass,
        "require_no_answer_permission": args.require_no_answer_permission,
    }


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--table-line-geometry", required=True, type=Path)
    parser.add_argument("--table-bbox-resolver", type=Path)
    parser.add_argument("--table-ocr-bbox-enrichment", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--min-diagnostic-cards", type=int, default=1)
    parser.add_argument("--min-crop-selected-cards", type=int, default=0)
    parser.add_argument("--min-page-selected-cards", type=int, default=0)
    parser.add_argument("--max-unsafe-diagnostic-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-line-geometry-quality-pass", action="store_true")
    parser.add_argument("--require-table-bbox-resolver-quality-pass", action="store_true")
    parser.add_argument("--require-table-ocr-bbox-enrichment-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net table crop selection diagnostics v1")
    add_common_args(parser)
    args = parser.parse_args(argv)

    report = build_report(
        table_line_geometry_path=args.table_line_geometry,
        table_bbox_resolver_path=args.table_bbox_resolver,
        table_ocr_bbox_enrichment_path=args.table_ocr_bbox_enrichment,
        thresholds=thresholds_from_args(args),
    )

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_table_crop_selection_diagnostics_v1.json"
    cards_path = output_dir / "trace_net_table_crop_selection_diagnostics_v1_cards.jsonl"
    summary_path = output_dir / "trace_net_table_crop_selection_diagnostics_v1_summary.json"
    quality_path = output_dir / "trace_net_table_crop_selection_diagnostics_v1_quality.json"
    manifest_path = output_dir / "trace_net_table_crop_selection_diagnostics_v1_manifest.json"

    write_json(report_path, report)
    write_jsonl(cards_path, report["diagnostic_cards"])
    write_json(summary_path, report["summary"])
    quality_payload = build_quality_payload(report)
    write_json(quality_path, quality_payload)
    write_json(manifest_path, {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": utc_now(),
        "files": {
            "report": str(report_path),
            "cards_jsonl": str(cards_path),
            "summary": str(summary_path),
            "quality": str(quality_path),
        },
    })

    s = report["summary"]
    print("TRACE-Net Table Crop Selection Diagnostics v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "diagnostic_card_count", "crop_selected_card_count", "page_selected_card_count",
        "crop_available_card_count", "crop_applied_card_count", "crop_selected_but_weak_card_count",
        "page_selected_grid_card_count", "broad_bbox_candidate_card_count", "review_required_card_count",
        "unsafe_diagnostic_card_count", "answer_permission_count", "can_answer_directly_count",
        "can_prove_claims_count", "source_truth_mutation_allowed_count", "postgres_write_attempt_count",
        "qdrant_write_attempt_count", "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {s.get(key)}")
    print(f" report_path: {report_path}")
    print(f" quality_path: {quality_path}")
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
