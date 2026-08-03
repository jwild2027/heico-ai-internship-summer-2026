"""TRACE-Net Table Detector Overlay Verdict Ingest v1.

Read-only ingest stage for human labels on detector overlay review cards.
It does not change source truth, does not grant answer permission, and does not
prove claims. It only normalizes review verdicts into a safe downstream artifact.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

SCHEMA_VERSION = "trace_net_table_detector_overlay_verdict_ingest_v1"
VALID_VERDICTS = (
    "UNREVIEWED",
    "ESTIMATOR_LINES_REAL_TABLE_RULES",
    "ESTIMATOR_LINES_TEXT_OR_NOISE",
    "MIXED_OR_UNCLEAR",
)
SAFE_VERDICT = "ESTIMATOR_LINES_REAL_TABLE_RULES"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return payload


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def stable_id(*parts: object, prefix: str = "verdict") -> str:
    joined = "::".join(str(p or "") for p in parts)
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def normalize_verdict(raw: object) -> str:
    value = str(raw or "UNREVIEWED").strip().upper()
    if not value:
        return "UNREVIEWED"
    aliases = {
        "REAL": "ESTIMATOR_LINES_REAL_TABLE_RULES",
        "RULES": "ESTIMATOR_LINES_REAL_TABLE_RULES",
        "TABLE_RULES": "ESTIMATOR_LINES_REAL_TABLE_RULES",
        "NOISE": "ESTIMATOR_LINES_TEXT_OR_NOISE",
        "TEXT_OR_NOISE": "ESTIMATOR_LINES_TEXT_OR_NOISE",
        "TEXT": "ESTIMATOR_LINES_TEXT_OR_NOISE",
        "MIXED": "MIXED_OR_UNCLEAR",
        "UNCLEAR": "MIXED_OR_UNCLEAR",
    }
    value = aliases.get(value, value)
    if value not in VALID_VERDICTS:
        raise ValueError(
            f"Invalid human_review_verdict {raw!r}. Expected one of: {', '.join(VALID_VERDICTS)}"
        )
    return value


def card_key(page_id: object, table_id: object) -> str:
    return f"{page_id or ''}::{table_id or ''}"


def load_verdict_rows(path: Optional[Path]) -> List[Dict[str, Any]]:
    if path is None:
        return []
    if not path.exists():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            return [dict(row) for row in csv.DictReader(fh)]
    if suffix == ".jsonl":
        rows: List[Dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError(f"JSONL row {line_no} in {path} is not an object")
                rows.append(row)
        return rows
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            rows = payload.get("verdicts") or payload.get("review_cards") or payload.get("cards") or []
        else:
            raise ValueError(f"Unsupported JSON verdict payload type: {type(payload).__name__}")
        if not isinstance(rows, list):
            raise ValueError(f"Expected a list of verdict rows in {path}")
        return [dict(row) for row in rows if isinstance(row, dict)]
    raise ValueError(f"Unsupported verdict file extension for {path}; use .csv, .json, or .jsonl")


def build_verdict_index(rows: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    index: Dict[str, Dict[str, Any]] = {}
    errors: List[str] = []
    for i, row in enumerate(rows, start=1):
        page_id = row.get("page_id")
        table_id = row.get("table_id")
        review_card_id = row.get("review_card_id")
        key_candidates = []
        if page_id or table_id:
            key_candidates.append(card_key(page_id, table_id))
        if review_card_id:
            key_candidates.append(str(review_card_id))
        if not key_candidates:
            errors.append(f"verdict_row_{i}_missing_page_table_or_review_card_id")
            continue
        try:
            row = dict(row)
            row["human_review_verdict"] = normalize_verdict(row.get("human_review_verdict"))
        except ValueError as exc:
            errors.append(f"verdict_row_{i}_invalid_verdict:{exc}")
            continue
        for key in key_candidates:
            index[key] = row
    return index, errors


def get_card_verdict(card: Mapping[str, Any], verdict_index: Mapping[str, Dict[str, Any]]) -> Tuple[str, str, str]:
    key = card_key(card.get("page_id"), card.get("table_id"))
    review_card_id = str(card.get("review_card_id") or card.get("overlay_review_card_id") or "")
    row = verdict_index.get(key) or (verdict_index.get(review_card_id) if review_card_id else None)
    if row:
        return (
            normalize_verdict(row.get("human_review_verdict")),
            "provided_verdict_file",
            str(row.get("review_notes") or row.get("notes") or ""),
        )
    return ("UNREVIEWED", "default_unreviewed", "")


def make_template_csv(path: Path, review_cards: List[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "page_id",
        "table_id",
        "table_type",
        "human_review_verdict",
        "review_notes",
        "overlay_path",
        "production_vertical_line_count",
        "production_intersection_count",
        "estimator_vertical_line_count",
        "estimator_intersection_count",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        for card in review_cards:
            prod = card.get("production_counts") or {}
            est = card.get("estimator_counts") or {}
            writer.writerow(
                {
                    "page_id": card.get("page_id") or "",
                    "table_id": card.get("table_id") or "",
                    "table_type": card.get("table_type") or "",
                    "human_review_verdict": "UNREVIEWED",
                    "review_notes": "",
                    "overlay_path": card.get("overlay_path") or "",
                    "production_vertical_line_count": prod.get("vertical_line_count", ""),
                    "production_intersection_count": prod.get("intersection_count", ""),
                    "estimator_vertical_line_count": est.get("vertical_line_count", ""),
                    "estimator_intersection_count": est.get("intersection_count", ""),
                }
            )


def build_verdict_ingest_report(
    overlay_review_pack_path: Path,
    output_dir: Path,
    verdicts_path: Optional[Path] = None,
    thresholds: Optional[Mapping[str, int]] = None,
) -> Dict[str, Any]:
    thresholds = dict(thresholds or {})
    output_dir.mkdir(parents=True, exist_ok=True)

    overlay_pack = read_json(overlay_review_pack_path)
    review_cards = overlay_pack.get("review_cards") or []
    if not isinstance(review_cards, list):
        raise ValueError("overlay review pack review_cards must be a list")

    verdict_rows = load_verdict_rows(verdicts_path)
    verdict_index, verdict_errors = build_verdict_index(verdict_rows)

    cards: List[Dict[str, Any]] = []
    for source in review_cards:
        if not isinstance(source, dict):
            continue
        verdict, verdict_source, notes = get_card_verdict(source, verdict_index)
        safe_for_crop = verdict == SAFE_VERDICT and bool(source.get("overlay_ready"))
        selection_blocked_by_verdict = not safe_for_crop
        flags = list(source.get("review_flags") or [])
        actions = list(source.get("recommended_actions") or [])
        if verdict == "UNREVIEWED":
            flags.append("overlay_verdict_unreviewed")
            actions.append("label_overlay_verdict_before_allowing_crop_selection")
        elif verdict == "ESTIMATOR_LINES_TEXT_OR_NOISE":
            flags.append("overlay_verdict_text_or_noise")
            actions.append("keep_crop_selection_blocked_for_this_table")
        elif verdict == "MIXED_OR_UNCLEAR":
            flags.append("overlay_verdict_mixed_or_unclear")
            actions.append("keep_crop_selection_blocked_until_specific_safe_region_is_verified")
        elif verdict == SAFE_VERDICT:
            flags.append("overlay_verdict_real_table_rules")
            actions.append("allow_crop_completeness_guard_to_consider_selection")

        card = {
            "schema_version": SCHEMA_VERSION,
            "verdict_ingest_card_id": stable_id(source.get("page_id"), source.get("table_id")),
            "source_review_card_id": source.get("review_card_id"),
            "page_id": source.get("page_id"),
            "table_id": source.get("table_id"),
            "table_type": source.get("table_type"),
            "overlay_ready": bool(source.get("overlay_ready")),
            "overlay_path": source.get("overlay_path"),
            "detector_disagreement": bool(source.get("detector_disagreement")),
            "estimator_exceeds_production": bool(source.get("estimator_exceeds_production")),
            "production_exceeds_estimator": bool(source.get("production_exceeds_estimator")),
            "production_counts": source.get("production_counts") or {},
            "estimator_counts": source.get("estimator_counts") or {},
            "human_review_verdict": verdict,
            "verdict_source": verdict_source,
            "review_notes": notes,
            "safe_for_crop_selection": safe_for_crop,
            "crop_selection_allowed_by_verdict": safe_for_crop,
            "crop_selection_blocked_by_verdict": selection_blocked_by_verdict,
            "requires_crop_completeness_guard_rebuild": verdict != "UNREVIEWED",
            "review_flags": sorted(set(str(x) for x in flags if x)),
            "recommended_actions": sorted(set(str(x) for x in actions if x)),
            "answer_permission": False,
            "final_answer_allowed": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "retrieval_only_answer_allowed": False,
            "source_truth_mutation_allowed": False,
            "source_truth_mutations_performed": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "unsafe_verdict_card": False,
        }
        cards.append(card)

    template_path = output_dir / "trace_net_table_detector_overlay_verdict_template_v1.csv"
    make_template_csv(template_path, review_cards)

    verdict_counts: Dict[str, int] = {v: 0 for v in VALID_VERDICTS}
    for card in cards:
        verdict_counts[card["human_review_verdict"]] = verdict_counts.get(card["human_review_verdict"], 0) + 1

    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": "TABLE_DETECTOR_OVERLAY_VERDICT_INGEST_BUILT",
        "overlay_review_pack_path": str(overlay_review_pack_path),
        "overlay_review_pack_quality_status": overlay_pack.get("quality_status"),
        "verdicts_path": str(verdicts_path) if verdicts_path else None,
        "verdict_template_path": str(template_path),
        "review_card_count": len(cards),
        "overlay_ready_card_count": sum(1 for c in cards if c.get("overlay_ready")),
        "detector_disagreement_card_count": sum(1 for c in cards if c.get("detector_disagreement")),
        "provided_verdict_row_count": len(verdict_rows),
        "provided_verdict_card_count": sum(1 for c in cards if c.get("verdict_source") == "provided_verdict_file"),
        "unreviewed_card_count": verdict_counts.get("UNREVIEWED", 0),
        "real_table_rules_verdict_card_count": verdict_counts.get("ESTIMATOR_LINES_REAL_TABLE_RULES", 0),
        "text_or_noise_verdict_card_count": verdict_counts.get("ESTIMATOR_LINES_TEXT_OR_NOISE", 0),
        "mixed_or_unclear_verdict_card_count": verdict_counts.get("MIXED_OR_UNCLEAR", 0),
        "crop_selection_allowed_by_verdict_card_count": sum(1 for c in cards if c.get("crop_selection_allowed_by_verdict")),
        "crop_selection_blocked_by_verdict_card_count": sum(1 for c in cards if c.get("crop_selection_blocked_by_verdict")),
        "invalid_verdict_row_count": len(verdict_errors),
        "invalid_verdict_errors": verdict_errors,
        "unsafe_verdict_card_count": sum(1 for c in cards if c.get("unsafe_verdict_card")),
        "answer_permission_count": sum(1 for c in cards if c.get("answer_permission")),
        "can_answer_directly_count": sum(1 for c in cards if c.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for c in cards if c.get("can_prove_claims")),
        "source_truth_mutation_allowed_count": sum(1 for c in cards if c.get("source_truth_mutation_allowed")),
        "postgres_write_attempt_count": sum(int(c.get("postgres_write_attempt_count") or 0) for c in cards),
        "qdrant_write_attempt_count": sum(int(c.get("qdrant_write_attempt_count") or 0) for c in cards),
        "opensearch_write_attempt_count": sum(int(c.get("opensearch_write_attempt_count") or 0) for c in cards),
    }

    fail_reasons: List[str] = []
    if overlay_pack.get("quality_status") != "PASS":
        fail_reasons.append("overlay_review_pack_quality_not_pass")
    if summary["review_card_count"] < int(thresholds.get("min_review_cards", 0)):
        fail_reasons.append("min_review_cards_not_met")
    if summary["overlay_ready_card_count"] < int(thresholds.get("min_overlay_ready_cards", 0)):
        fail_reasons.append("min_overlay_ready_cards_not_met")
    if summary["provided_verdict_card_count"] < int(thresholds.get("min_provided_verdict_cards", 0)):
        fail_reasons.append("min_provided_verdict_cards_not_met")
    if summary["unsafe_verdict_card_count"] > int(thresholds.get("max_unsafe_verdict_cards", 0)):
        fail_reasons.append("unsafe_verdict_cards_exceed_limit")
    if summary["answer_permission_count"] > int(thresholds.get("max_answer_permission_count", 0)):
        fail_reasons.append("answer_permission_exceeds_limit")
    if summary["source_truth_mutation_allowed_count"] > int(thresholds.get("max_source_truth_mutation_allowed", 0)):
        fail_reasons.append("source_truth_mutation_allowed_exceeds_limit")
    if verdict_errors:
        fail_reasons.append("invalid_verdict_rows_present")

    quality_status = "PASS" if not fail_reasons else "FAIL"
    summary["quality_status"] = quality_status
    summary["quality_fail_reasons"] = fail_reasons

    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "TABLE_DETECTOR_OVERLAY_VERDICT_INGEST_BUILT" if quality_status == "PASS" else "TABLE_DETECTOR_OVERLAY_VERDICT_INGEST_NOT_READY",
        "quality_status": quality_status,
        "generated_at": utc_now_iso(),
        "summary": summary,
        "verdict_options": list(VALID_VERDICTS),
        "review_cards": cards,
        "paths": {
            "report_path": str(output_dir / "trace_net_table_detector_overlay_verdict_ingest_v1.json"),
            "cards_jsonl_path": str(output_dir / "trace_net_table_detector_overlay_verdict_ingest_v1_cards.jsonl"),
            "summary_path": str(output_dir / "trace_net_table_detector_overlay_verdict_ingest_v1_summary.json"),
            "template_csv_path": str(template_path),
        },
        "safety_contract": {
            "read_only": True,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "postgres_writes": False,
            "qdrant_writes": False,
            "opensearch_writes": False,
            "review_verdicts_are_advisory_until_consumed_by_guard": True,
        },
    }

    report_path = output_dir / "trace_net_table_detector_overlay_verdict_ingest_v1.json"
    write_json(report_path, report)
    write_json(output_dir / "trace_net_table_detector_overlay_verdict_ingest_v1_summary.json", summary)
    write_jsonl(output_dir / "trace_net_table_detector_overlay_verdict_ingest_v1_cards.jsonl", cards)
    write_json(
        output_dir / "trace_net_table_detector_overlay_verdict_ingest_v1_manifest.json",
        {
            "schema_version": f"{SCHEMA_VERSION}_manifest",
            "generated_at": report["generated_at"],
            "files": report["paths"],
        },
    )
    return report


def thresholds_from_args(args: argparse.Namespace) -> Dict[str, int]:
    return {
        "min_review_cards": args.min_review_cards,
        "min_overlay_ready_cards": args.min_overlay_ready_cards,
        "min_provided_verdict_cards": args.min_provided_verdict_cards,
        "max_unsafe_verdict_cards": args.max_unsafe_verdict_cards,
        "max_answer_permission_count": args.max_answer_permission_count,
        "max_source_truth_mutation_allowed": args.max_source_truth_mutation_allowed,
    }


def print_report(report: Mapping[str, Any]) -> None:
    summary = report.get("summary", {})
    print("TRACE-Net Table Detector Overlay Verdict Ingest v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "review_card_count",
        "overlay_ready_card_count",
        "detector_disagreement_card_count",
        "provided_verdict_row_count",
        "provided_verdict_card_count",
        "unreviewed_card_count",
        "real_table_rules_verdict_card_count",
        "text_or_noise_verdict_card_count",
        "mixed_or_unclear_verdict_card_count",
        "crop_selection_allowed_by_verdict_card_count",
        "crop_selection_blocked_by_verdict_card_count",
        "invalid_verdict_row_count",
        "unsafe_verdict_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {report.get('paths', {}).get('report_path')}")
    print(f" verdict_template_path: {summary.get('verdict_template_path')}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overlay-review-pack", required=True, type=Path)
    parser.add_argument("--verdicts", type=Path, default=None, help="Optional CSV/JSON/JSONL with human_review_verdict labels")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--min-review-cards", type=int, default=1)
    parser.add_argument("--min-overlay-ready-cards", type=int, default=1)
    parser.add_argument("--min-provided-verdict-cards", type=int, default=0)
    parser.add_argument("--max-unsafe-verdict-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-overlay-review-pack-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_verdict_ingest_report(
        overlay_review_pack_path=args.overlay_review_pack,
        output_dir=args.output_dir,
        verdicts_path=args.verdicts,
        thresholds=thresholds_from_args(args),
    )
    print_report(report)
    return 0 if report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
