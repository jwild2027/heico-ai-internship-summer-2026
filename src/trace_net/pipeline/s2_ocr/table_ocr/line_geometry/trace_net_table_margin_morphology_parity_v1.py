"""TRACE-Net Table Margin Morphology Parity v1.

Read-only diagnostics that compare production Table Line Geometry margin-aware
crop selection with the separate margin-expansion experiment artifact.

The purpose is to explain cases where the experiment found a margin-expanded
crop with stronger grid evidence, but production Table Line Geometry did not
select any margin-expanded crop. This module is advisory only and has no answer
or source-truth authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "trace_net_table_margin_morphology_parity_v1"
STATUS_BUILT = "TABLE_MARGIN_MORPHOLOGY_PARITY_BUILT"
STATUS_NOT_READY = "TABLE_MARGIN_MORPHOLOGY_PARITY_NOT_READY"


@dataclass(frozen=True)
class Thresholds:
    min_parity_cards: int = 1
    min_experiment_improvement_cards: int = 0
    min_parity_gap_cards: int = 0
    max_unsafe_parity_cards: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_table_line_geometry_quality_pass: bool = False
    require_margin_experiment_quality_pass: bool = False
    require_no_answer_permission: bool = False


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "::".join(str(part) for part in parts if part is not None)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:14]}"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


def signal_rank(value: Any) -> int:
    return {"NO_LINE_SIGNAL": 0, "WEAK_LINE_SIGNAL": 1, "PARTIAL_GRID": 2, "GRID": 3}.get(str(value or ""), 0)


def extract_cards(payload: Mapping[str, Any], *keys: str) -> List[Dict[str, Any]]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


def join_key(card: Mapping[str, Any]) -> Tuple[str, str]:
    return str(card.get("page_id") or "unknown_page"), str(card.get("table_id") or "unknown_table")


def index_cards(cards: Sequence[Mapping[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    indexed: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for card in cards:
        indexed[join_key(card)] = dict(card)
    return indexed


def summarize_candidate(candidate: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not candidate:
        return {
            "present": False,
            "margin_pixels": None,
            "horizontal_line_count": 0,
            "vertical_line_count": 0,
            "intersection_count": 0,
            "morphology_signal_strength": None,
            "morphology_quality_score": 0.0,
        }
    return {
        "present": True,
        "margin_pixels": candidate.get("margin_pixels"),
        "horizontal_line_count": as_int(candidate.get("horizontal_line_count")),
        "vertical_line_count": as_int(candidate.get("vertical_line_count")),
        "intersection_count": as_int(candidate.get("intersection_count")),
        "morphology_signal_strength": candidate.get("morphology_signal_strength"),
        "morphology_quality_score": as_float(candidate.get("morphology_quality_score")),
    }


def best_production_margin_candidate(tlg_card: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    comparison = tlg_card.get("table_region_crop_comparison") or {}
    candidates = comparison.get("margin_expansion_candidates") or []
    if not isinstance(candidates, list):
        return None
    normalized = [dict(candidate) for candidate in candidates if isinstance(candidate, Mapping)]
    if not normalized:
        return None
    return max(
        normalized,
        key=lambda candidate: (
            signal_rank(candidate.get("morphology_signal_strength")),
            as_int(candidate.get("intersection_count")),
            as_int(candidate.get("vertical_line_count")),
            as_float(candidate.get("morphology_quality_score")),
            -as_int(candidate.get("margin_pixels")),
        ),
    )


def build_parity_card(tlg_card: Mapping[str, Any], experiment_card: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    page_id, table_id = join_key(tlg_card)
    production_best = best_production_margin_candidate(tlg_card)
    experiment_best = dict((experiment_card or {}).get("best_margin_candidate") or {}) if experiment_card else None
    production_summary = summarize_candidate(production_best)
    experiment_summary = summarize_candidate(experiment_best)

    selected_scope = str(tlg_card.get("selected_morphology_scope") or "")
    production_selected_margin = boolish(tlg_card.get("margin_expansion_selected_for_crop_morphology"))
    experiment_improves = boolish((experiment_card or {}).get("margin_expansion_improves_grid_evidence"))
    production_candidate_count = as_int(tlg_card.get("margin_expansion_candidate_count"))
    if production_candidate_count == 0:
        comparison = tlg_card.get("table_region_crop_comparison") or {}
        production_candidate_count = as_int(comparison.get("margin_expansion_candidate_count"))

    experiment_vertical = experiment_summary["vertical_line_count"]
    experiment_intersections = experiment_summary["intersection_count"]
    production_vertical = production_summary["vertical_line_count"]
    production_intersections = production_summary["intersection_count"]
    production_rank = signal_rank(production_summary["morphology_signal_strength"])
    experiment_rank = signal_rank(experiment_summary["morphology_signal_strength"])

    parity_gap = False
    findings: List[str] = []
    actions: List[str] = []

    if experiment_card is None:
        findings.append("missing_margin_experiment_card")
        actions.append("rebuild_margin_expansion_experiment_for_this_table")
    if production_candidate_count <= 0:
        findings.append("production_margin_candidates_missing")
        actions.append("ensure_table_line_geometry_records_margin_candidate_metrics")
    if experiment_improves:
        findings.append("experiment_margin_candidate_improves_grid_evidence")
    if production_selected_margin:
        findings.append("production_selected_margin_crop")
    else:
        findings.append("production_kept_page_morphology")

    if experiment_improves and not production_selected_margin:
        parity_gap = True
        findings.append("experiment_improved_but_production_did_not_select_margin")
        actions.append("compare_production_and_experiment_morphology_implementations")
        actions.append("align_margin_candidate_scoring_with_validated_experiment_or_explain_difference")

    if experiment_rank > production_rank:
        parity_gap = True
        findings.append("experiment_signal_rank_exceeds_production_candidate")
    if experiment_vertical > production_vertical:
        findings.append("experiment_vertical_count_exceeds_production_candidate")
    if experiment_intersections > production_intersections:
        findings.append("experiment_intersection_count_exceeds_production_candidate")

    if selected_scope == "page" and experiment_improves:
        actions.append("do_not_wire_margin_selection_until_parity_gap_is_resolved")

    card = {
        "schema_version": SCHEMA_VERSION,
        "parity_card_id": stable_id("table_margin_parity", page_id, table_id),
        "page_id": page_id,
        "table_id": table_id,
        "table_type": tlg_card.get("table_type"),
        "selected_morphology_scope": selected_scope,
        "production_margin_selected": production_selected_margin,
        "production_margin_candidate_count": production_candidate_count,
        "production_best_margin_candidate": production_summary,
        "experiment_available": experiment_card is not None,
        "experiment_margin_improves_grid_evidence": experiment_improves,
        "experiment_best_margin_candidate": experiment_summary,
        "vertical_line_delta_experiment_minus_production": experiment_vertical - production_vertical,
        "intersection_delta_experiment_minus_production": experiment_intersections - production_intersections,
        "signal_rank_delta_experiment_minus_production": experiment_rank - production_rank,
        "margin_morphology_parity_gap": parity_gap,
        "parity_findings": sorted(set(findings)),
        "recommended_actions": sorted(set(actions)),
        "review_required": parity_gap,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "retrieval_only_answer_allowed": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "unsafe_parity_card": False,
    }
    return card


def summarize(cards: Sequence[Mapping[str, Any]], tlg_payload: Mapping[str, Any], experiment_payload: Mapping[str, Any]) -> Dict[str, Any]:
    def count_if(fn):
        return sum(1 for card in cards if fn(card))

    def counts(values: Iterable[Any]) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for value in values:
            key = str(value)
            out[key] = out.get(key, 0) + 1
        return dict(sorted(out.items()))

    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "quality_status": "PASS",
        "parity_card_count": len(cards),
        "experiment_improvement_card_count": count_if(lambda c: c.get("experiment_margin_improves_grid_evidence")),
        "production_margin_selected_card_count": count_if(lambda c: c.get("production_margin_selected")),
        "parity_gap_card_count": count_if(lambda c: c.get("margin_morphology_parity_gap")),
        "missing_experiment_card_count": count_if(lambda c: not c.get("experiment_available")),
        "production_margin_candidate_card_count": count_if(lambda c: as_int(c.get("production_margin_candidate_count")) > 0),
        "selected_morphology_scope_counts": counts(card.get("selected_morphology_scope") for card in cards),
        "table_line_geometry_quality_status": tlg_payload.get("quality_status"),
        "margin_experiment_quality_status": experiment_payload.get("quality_status"),
        "unsafe_parity_card_count": count_if(lambda c: c.get("unsafe_parity_card")),
        "answer_permission_count": count_if(lambda c: c.get("answer_permission")),
        "can_answer_directly_count": count_if(lambda c: c.get("can_answer_directly")),
        "can_prove_claims_count": count_if(lambda c: c.get("can_prove_claims")),
        "source_truth_mutation_allowed_count": count_if(lambda c: c.get("source_truth_mutation_allowed")),
        "postgres_write_attempt_count": sum(as_int(c.get("postgres_write_attempt_count")) for c in cards),
        "qdrant_write_attempt_count": sum(as_int(c.get("qdrant_write_attempt_count")) for c in cards),
        "opensearch_write_attempt_count": sum(as_int(c.get("opensearch_write_attempt_count")) for c in cards),
        "quality_fail_reasons": [],
    }
    summary["status"] = summary["quality_status"]
    return summary


def apply_quality(summary: Dict[str, Any], thresholds: Thresholds) -> Dict[str, Any]:
    checks = {
        "schema_version_ok": True,
        "min_parity_cards_met": as_int(summary.get("parity_card_count")) >= thresholds.min_parity_cards,
        "min_experiment_improvement_cards_met": as_int(summary.get("experiment_improvement_card_count")) >= thresholds.min_experiment_improvement_cards,
        "min_parity_gap_cards_met": as_int(summary.get("parity_gap_card_count")) >= thresholds.min_parity_gap_cards,
        "unsafe_parity_cards_within_limit": as_int(summary.get("unsafe_parity_card_count")) <= thresholds.max_unsafe_parity_cards,
        "answer_permission_within_limit": as_int(summary.get("answer_permission_count")) <= thresholds.max_answer_permission_count,
        "source_truth_mutation_allowed_within_limit": as_int(summary.get("source_truth_mutation_allowed_count")) <= thresholds.max_source_truth_mutation_allowed,
        "table_line_geometry_quality_pass": (not thresholds.require_table_line_geometry_quality_pass) or summary.get("table_line_geometry_quality_status") == "PASS",
        "margin_experiment_quality_pass": (not thresholds.require_margin_experiment_quality_pass) or summary.get("margin_experiment_quality_status") == "PASS",
        "no_answer_permission": (not thresholds.require_no_answer_permission) or as_int(summary.get("answer_permission_count")) == 0,
    }
    fail_reasons = [key for key, ok in checks.items() if not ok]
    status = "PASS" if not fail_reasons else "FAIL"
    summary["checks"] = checks
    summary["quality_fail_reasons"] = fail_reasons
    summary["quality_status"] = status
    summary["status"] = status
    return summary


def build_report(
    *,
    table_line_geometry_path: Path,
    margin_experiment_path: Path,
    output_dir: Path,
    thresholds: Thresholds,
    write_quality: bool = False,
) -> Dict[str, Any]:
    tlg_payload = load_json(table_line_geometry_path)
    experiment_payload = load_json(margin_experiment_path)
    tlg_cards = extract_cards(tlg_payload, "table_geometry_cards", "cards", "records")
    experiment_cards = extract_cards(experiment_payload, "diagnostic_cards", "cards", "records")
    experiment_by_key = index_cards(experiment_cards)

    parity_cards = [build_parity_card(card, experiment_by_key.get(join_key(card))) for card in tlg_cards]
    summary = apply_quality(summarize(parity_cards, tlg_payload, experiment_payload), thresholds)
    status = STATUS_BUILT if summary["quality_status"] == "PASS" else STATUS_NOT_READY

    report = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "quality_status": summary["quality_status"],
        "generated_at": utc_now_iso(),
        "inputs": {
            "table_line_geometry": str(table_line_geometry_path),
            "margin_experiment": str(margin_experiment_path),
        },
        "summary": summary,
        "parity_cards": parity_cards,
        "safety_contract": {
            "read_only_diagnostics": True,
            "no_postgres_writes": True,
            "no_qdrant_writes": True,
            "no_opensearch_writes": True,
            "no_source_truth_mutation": True,
            "no_answer_permission": True,
            "cannot_prove_claims": True,
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_table_margin_morphology_parity_v1.json"
    cards_path = output_dir / "trace_net_table_margin_morphology_parity_v1_cards.jsonl"
    summary_path = output_dir / "trace_net_table_margin_morphology_parity_v1_summary.json"
    manifest_path = output_dir / "trace_net_table_margin_morphology_parity_v1_manifest.json"
    write_json(report_path, report)
    write_jsonl(cards_path, parity_cards)
    write_json(summary_path, summary)
    write_json(manifest_path, {"schema_version": SCHEMA_VERSION, "generated_at": report["generated_at"], "artifacts": [str(report_path), str(cards_path), str(summary_path)]})
    if write_quality:
        write_json(output_dir / "trace_net_table_margin_morphology_parity_v1_quality.json", {"schema_version": f"{SCHEMA_VERSION}_quality", "generated_at": report["generated_at"], "quality_status": summary["quality_status"], "status": summary["quality_status"], "summary": summary, "checks": summary.get("checks", {})})
    return report


def thresholds_from_args(args: argparse.Namespace) -> Thresholds:
    return Thresholds(
        min_parity_cards=args.min_parity_cards,
        min_experiment_improvement_cards=args.min_experiment_improvement_cards,
        min_parity_gap_cards=args.min_parity_gap_cards,
        max_unsafe_parity_cards=args.max_unsafe_parity_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_table_line_geometry_quality_pass=args.require_table_line_geometry_quality_pass,
        require_margin_experiment_quality_pass=args.require_margin_experiment_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net table margin morphology parity diagnostics.")
    parser.add_argument("--table-line-geometry", type=Path, required=True)
    parser.add_argument("--margin-expansion-experiment", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--min-parity-cards", type=int, default=1)
    parser.add_argument("--min-experiment-improvement-cards", type=int, default=0)
    parser.add_argument("--min-parity-gap-cards", type=int, default=0)
    parser.add_argument("--max-unsafe-parity-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-line-geometry-quality-pass", action="store_true")
    parser.add_argument("--require-margin-experiment-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report(
        table_line_geometry_path=args.table_line_geometry,
        margin_experiment_path=args.margin_expansion_experiment,
        output_dir=args.output_dir,
        thresholds=thresholds_from_args(args),
        write_quality=args.quality,
    )
    summary = report["summary"]
    print("TRACE-Net Table Margin Morphology Parity v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in (
        "parity_card_count",
        "experiment_improvement_card_count",
        "production_margin_selected_card_count",
        "parity_gap_card_count",
        "production_margin_candidate_card_count",
        "unsafe_parity_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {args.output_dir / 'trace_net_table_margin_morphology_parity_v1.json'}")
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
