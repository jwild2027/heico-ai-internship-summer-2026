"""TRACE-Net Table Detector Overlay Review Pack v1.

Builds a human-review packet from detector overlay audit artifacts.

This module is intentionally read-only with respect to source truth and external
stores. It only writes derived diagnostic files under the requested output dir.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SCHEMA_VERSION = "trace_net_table_detector_overlay_review_pack_v1"
QUALITY_SCHEMA_VERSION = "trace_net_table_detector_overlay_review_pack_v1_quality"

VERDICT_OPTIONS = [
    "UNREVIEWED",
    "ESTIMATOR_LINES_REAL_TABLE_RULES",
    "ESTIMATOR_LINES_TEXT_OR_NOISE",
    "MIXED_OR_UNCLEAR",
]

REVIEW_QUESTIONS = [
    "Do the estimator/overlay lines follow actual printed table ruling lines?",
    "Are vertical detections column borders, or are they text strokes/glyph edges?",
    "Are intersections formed by real horizontal/vertical table rules?",
    "Should production morphology be relaxed for this table type?",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def as_bool(value: Any) -> bool:
    return bool(value) if value is not None else False


def as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def resolve_path(path_text: Optional[str], repo_root: Path) -> Optional[Path]:
    if not path_text:
        return None
    path = Path(path_text)
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def summarize_counts(cards: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    return {
        "review_card_count": len(cards),
        "overlay_ready_card_count": sum(1 for c in cards if c.get("overlay_ready")),
        "overlay_missing_card_count": sum(1 for c in cards if not c.get("overlay_ready")),
        "detector_disagreement_card_count": sum(1 for c in cards if c.get("detector_disagreement")),
        "estimator_exceeds_production_card_count": sum(1 for c in cards if c.get("estimator_exceeds_production")),
        "production_exceeds_estimator_card_count": sum(1 for c in cards if c.get("production_exceeds_estimator")),
        "unsafe_review_card_count": sum(1 for c in cards if c.get("unsafe_review_card")),
        "answer_permission_count": sum(1 for c in cards if c.get("answer_permission")),
        "can_answer_directly_count": sum(1 for c in cards if c.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for c in cards if c.get("can_prove_claims")),
        "source_truth_mutation_allowed_count": sum(1 for c in cards if c.get("source_truth_mutation_allowed")),
        "postgres_write_attempt_count": sum(as_int(c.get("postgres_write_attempt_count")) for c in cards),
        "qdrant_write_attempt_count": sum(as_int(c.get("qdrant_write_attempt_count")) for c in cards),
        "opensearch_write_attempt_count": sum(as_int(c.get("opensearch_write_attempt_count")) for c in cards),
    }


def make_review_card(audit_card: Dict[str, Any], index: int, repo_root: Path) -> Dict[str, Any]:
    production = audit_card.get("production_best_candidate") or {}
    estimator = audit_card.get("estimator_best_candidate") or {}
    overlay_path_text = audit_card.get("overlay_path")
    overlay_abs = resolve_path(overlay_path_text, repo_root)
    overlay_exists = bool(overlay_abs and overlay_abs.exists())
    overlay_ready = bool(audit_card.get("overlay_ready") and overlay_exists)

    estimator_exceeds = as_bool(audit_card.get("estimator_exceeds_production"))
    production_exceeds = as_bool(audit_card.get("production_exceeds_estimator"))

    recommended_actions: List[str] = [
        "open_overlay_png",
        "label_overlay_verdict",
        "verify_estimator_lines_are_table_rules_not_text_strokes",
    ]
    if estimator_exceeds:
        recommended_actions.append("inspect_before_relaxing_production_morphology")
    if production_exceeds:
        recommended_actions.append("compare_candidate_selection_rules")
    if not overlay_ready:
        recommended_actions.append("regenerate_overlay_audit_with_image_paths")

    review_flags: List[str] = []
    if audit_card.get("detector_disagreement"):
        review_flags.append("detector_outputs_disagree_on_same_crop")
    if estimator_exceeds:
        review_flags.append("estimator_counts_more_grid_evidence")
    if production_exceeds:
        review_flags.append("production_counts_more_grid_evidence_on_some_candidates")
    if not overlay_ready:
        review_flags.append("overlay_missing_or_unreadable")

    page_id = audit_card.get("page_id")
    table_id = audit_card.get("table_id")

    return {
        "schema_version": SCHEMA_VERSION,
        "review_card_id": stable_id("overlay_review", page_id, table_id, index),
        "review_status": "open",
        "human_review_verdict": "UNREVIEWED",
        "verdict_options": VERDICT_OPTIONS,
        "review_questions": REVIEW_QUESTIONS,
        "page_id": page_id,
        "table_id": table_id,
        "table_type": audit_card.get("table_type"),
        "target_type": "table_detector_overlay_audit_card",
        "target_id": audit_card.get("audit_card_id") or table_id or page_id,
        "overlay_ready": overlay_ready,
        "overlay_path": overlay_path_text,
        "overlay_exists": overlay_exists,
        "overlay_error": None if overlay_ready else (audit_card.get("overlay_error") or "overlay_file_missing_or_unreadable"),
        "detector_disagreement": as_bool(audit_card.get("detector_disagreement")),
        "estimator_exceeds_production": estimator_exceeds,
        "production_exceeds_estimator": production_exceeds,
        "production_counts": {
            "horizontal_line_count": production.get("production_horizontal_line_count"),
            "vertical_line_count": production.get("production_vertical_line_count"),
            "intersection_count": production.get("production_intersection_count"),
            "signal": production.get("production_signal"),
            "score": production.get("production_score"),
        },
        "estimator_counts": {
            "horizontal_line_count": estimator.get("estimator_horizontal_line_count"),
            "vertical_line_count": estimator.get("estimator_vertical_line_count"),
            "intersection_count": estimator.get("estimator_intersection_count"),
            "signal": estimator.get("estimator_signal"),
            "score": estimator.get("estimator_score"),
        },
        "overlay_projection_horizontal_count": audit_card.get("overlay_projection_horizontal_count"),
        "overlay_projection_vertical_count": audit_card.get("overlay_projection_vertical_count"),
        "review_flags": review_flags,
        "recommended_actions": recommended_actions,
        "requires_human_review": True,
        "review_authority": "human_overlay_review_advisory_only",
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "retrieval_only_answer_allowed": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
        "unsafe_review_card": False,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }


def try_import_pillow():
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore

        return Image, ImageDraw, ImageFont, None
    except Exception as exc:  # pragma: no cover - environment dependent
        return None, None, None, str(exc)


def create_contact_sheets(
    cards: Sequence[Dict[str, Any]],
    output_dir: Path,
    repo_root: Path,
    max_cards: int,
    columns: int,
    thumb_width: int,
) -> Tuple[List[str], Optional[str]]:
    Image, ImageDraw, ImageFont, import_error = try_import_pillow()
    if Image is None:
        return [], f"pillow_unavailable: {import_error}"

    selected = [c for c in cards if c.get("overlay_ready") and c.get("overlay_path")][:max_cards]
    if not selected:
        return [], "no_overlay_ready_cards"

    overlays_dir = output_dir / "contact_sheets"
    overlays_dir.mkdir(parents=True, exist_ok=True)

    # Keep sheets reasonably sized: 6 overlays per sheet by default for readability.
    per_sheet = max(1, columns * 3)
    font = ImageFont.load_default()
    paths: List[str] = []

    for sheet_index, start in enumerate(range(0, len(selected), per_sheet), start=1):
        batch = selected[start : start + per_sheet]
        rendered: List[Tuple[Any, str]] = []
        for card in batch:
            overlay_path = resolve_path(card.get("overlay_path"), repo_root)
            if not overlay_path or not overlay_path.exists():
                continue
            image = Image.open(overlay_path).convert("RGB")
            ratio = thumb_width / max(1, image.width)
            thumb_height = max(1, int(image.height * ratio))
            image = image.resize((thumb_width, thumb_height))
            label = (
                f"{card.get('page_id')} | {card.get('table_type')} | "
                f"prod V/I={card.get('production_counts', {}).get('vertical_line_count')}/"
                f"{card.get('production_counts', {}).get('intersection_count')} | "
                f"est V/I={card.get('estimator_counts', {}).get('vertical_line_count')}/"
                f"{card.get('estimator_counts', {}).get('intersection_count')}"
            )
            rendered.append((image, label[:180]))

        if not rendered:
            continue

        label_height = 38
        gutter = 16
        rows = (len(rendered) + columns - 1) // columns
        cell_width = thumb_width
        cell_heights: List[int] = []
        for row in range(rows):
            row_items = rendered[row * columns : (row + 1) * columns]
            cell_heights.append(max(img.height for img, _ in row_items) + label_height)
        sheet_width = columns * cell_width + (columns + 1) * gutter
        sheet_height = sum(cell_heights) + (rows + 1) * gutter
        sheet = Image.new("RGB", (sheet_width, sheet_height), "white")
        draw = ImageDraw.Draw(sheet)

        y = gutter
        for row in range(rows):
            row_items = rendered[row * columns : (row + 1) * columns]
            row_height = cell_heights[row]
            for col, (img, label) in enumerate(row_items):
                x = gutter + col * (cell_width + gutter)
                draw.text((x, y), label, fill="black", font=font)
                sheet.paste(img, (x, y + label_height))
                draw.rectangle((x, y + label_height, x + img.width - 1, y + label_height + img.height - 1), outline="black")
            y += row_height + gutter

        out_path = overlays_dir / f"trace_net_table_detector_overlay_review_contact_sheet_{sheet_index:03d}.png"
        sheet.save(out_path)
        paths.append(str(out_path.relative_to(repo_root) if out_path.is_relative_to(repo_root) else out_path))

    return paths, None


@dataclass
class Thresholds:
    min_review_cards: int = 1
    min_overlay_ready_cards: int = 1
    min_contact_sheets: int = 0
    max_unsafe_review_cards: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_overlay_audit_quality_pass: bool = False
    require_no_answer_permission: bool = False
    require_contact_sheet: bool = False


def evaluate_quality(report: Dict[str, Any], thresholds: Thresholds) -> Dict[str, Any]:
    summary = dict(report.get("summary") or {})
    checks = {
        "schema_version_ok": report.get("schema_version") == SCHEMA_VERSION,
        "min_review_cards_met": as_int(summary.get("review_card_count")) >= thresholds.min_review_cards,
        "min_overlay_ready_cards_met": as_int(summary.get("overlay_ready_card_count")) >= thresholds.min_overlay_ready_cards,
        "unsafe_review_cards_within_limit": as_int(summary.get("unsafe_review_card_count")) <= thresholds.max_unsafe_review_cards,
        "answer_permission_within_limit": as_int(summary.get("answer_permission_count")) <= thresholds.max_answer_permission_count,
        "source_truth_mutation_allowed_within_limit": as_int(summary.get("source_truth_mutation_allowed_count")) <= thresholds.max_source_truth_mutation_allowed,
        "overlay_audit_quality_pass": (summary.get("overlay_audit_quality_status") == "PASS") if thresholds.require_overlay_audit_quality_pass else True,
        "no_answer_permission": (as_int(summary.get("answer_permission_count")) == 0) if thresholds.require_no_answer_permission else True,
        "contact_sheet_present": (as_int(summary.get("contact_sheet_count")) >= 1) if thresholds.require_contact_sheet else True,
        "min_contact_sheets_met": as_int(summary.get("contact_sheet_count")) >= thresholds.min_contact_sheets,
    }
    quality_status = "PASS" if all(checks.values()) else "FAIL"
    fail_reasons = [name for name, ok in checks.items() if not ok]
    summary["quality_status"] = quality_status
    summary["quality_fail_reasons"] = fail_reasons
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "status": quality_status,
        "quality_status": quality_status,
        "generated_at": utc_now_iso(),
        "checks": checks,
        "summary": summary,
    }


def build_review_pack_report(
    overlay_audit_path: Path,
    output_dir: Path,
    repo_root: Path,
    max_review_cards: Optional[int] = None,
    max_contact_sheet_cards: int = 20,
    contact_sheet_columns: int = 2,
    contact_sheet_thumb_width: int = 700,
    write_contact_sheets: bool = True,
    thresholds: Optional[Thresholds] = None,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    audit = load_json(overlay_audit_path)
    audit_cards = list(audit.get("audit_cards") or [])
    if max_review_cards is not None:
        audit_cards = audit_cards[:max_review_cards]

    cards = [make_review_card(card, index, repo_root) for index, card in enumerate(audit_cards, start=1)]

    contact_sheet_paths: List[str] = []
    contact_sheet_error: Optional[str] = None
    if write_contact_sheets:
        contact_sheet_paths, contact_sheet_error = create_contact_sheets(
            cards,
            output_dir=output_dir,
            repo_root=repo_root,
            max_cards=max_contact_sheet_cards,
            columns=contact_sheet_columns,
            thumb_width=contact_sheet_thumb_width,
        )

    counts = summarize_counts(cards)
    summary: Dict[str, Any] = {
        **counts,
        "schema_version": SCHEMA_VERSION,
        "status": "TABLE_DETECTOR_OVERLAY_REVIEW_PACK_BUILT",
        "overlay_audit_path": str(overlay_audit_path),
        "overlay_audit_quality_status": audit.get("quality_status"),
        "contact_sheet_count": len(contact_sheet_paths),
        "contact_sheet_paths": contact_sheet_paths,
        "contact_sheet_error": contact_sheet_error,
        "verdict_options": VERDICT_OPTIONS,
        "unreviewed_card_count": sum(1 for c in cards if c.get("human_review_verdict") == "UNREVIEWED"),
        "review_required_card_count": sum(1 for c in cards if c.get("requires_human_review")),
    }

    report_path = output_dir / "trace_net_table_detector_overlay_review_pack_v1.json"
    cards_path = output_dir / "trace_net_table_detector_overlay_review_pack_v1_cards.jsonl"
    summary_path = output_dir / "trace_net_table_detector_overlay_review_pack_v1_summary.json"
    quality_path = output_dir / "trace_net_table_detector_overlay_review_pack_v1_quality.json"
    manifest_path = output_dir / "trace_net_table_detector_overlay_review_pack_v1_manifest.json"

    report: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": summary["status"],
        "quality_status": "UNKNOWN",
        "generated_at": utc_now_iso(),
        "summary": summary,
        "review_cards": cards,
        "safety_contract": {
            "read_only_diagnostic": True,
            "human_overlay_review_advisory_only": True,
            "no_postgres_writes": True,
            "no_qdrant_writes": True,
            "no_opensearch_writes": True,
            "no_source_truth_mutation": True,
            "no_answer_permission": True,
            "can_answer_directly": False,
            "can_prove_claims": False,
        },
        "artifact_paths": {
            "report_path": str(report_path),
            "cards_path": str(cards_path),
            "summary_path": str(summary_path),
            "quality_path": str(quality_path),
            "manifest_path": str(manifest_path),
            "contact_sheet_paths": contact_sheet_paths,
        },
    }

    quality = evaluate_quality(report, thresholds or Thresholds())
    report["quality_status"] = quality["quality_status"]
    report["summary"] = quality["summary"]
    report["summary"]["status"] = report["status"]

    manifest = {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": utc_now_iso(),
        "inputs": {"overlay_audit": str(overlay_audit_path)},
        "outputs": report["artifact_paths"],
        "record_counts": {"review_cards": len(cards), "contact_sheets": len(contact_sheet_paths)},
    }

    write_json(report_path, report)
    write_jsonl(cards_path, cards)
    write_json(summary_path, report["summary"])
    write_json(quality_path, quality)
    write_json(manifest_path, manifest)

    return report


def thresholds_from_args(args: argparse.Namespace) -> Thresholds:
    return Thresholds(
        min_review_cards=args.min_review_cards,
        min_overlay_ready_cards=args.min_overlay_ready_cards,
        min_contact_sheets=args.min_contact_sheets,
        max_unsafe_review_cards=args.max_unsafe_review_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_overlay_audit_quality_pass=args.require_overlay_audit_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
        require_contact_sheet=args.require_contact_sheet,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net table detector overlay review pack v1")
    parser.add_argument("--overlay-audit", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--max-review-cards", type=int, default=None)
    parser.add_argument("--max-contact-sheet-cards", type=int, default=20)
    parser.add_argument("--contact-sheet-columns", type=int, default=2)
    parser.add_argument("--contact-sheet-thumb-width", type=int, default=700)
    parser.add_argument("--no-contact-sheets", action="store_true")
    parser.add_argument("--min-review-cards", type=int, default=1)
    parser.add_argument("--min-overlay-ready-cards", type=int, default=1)
    parser.add_argument("--min-contact-sheets", type=int, default=0)
    parser.add_argument("--max-unsafe-review-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-overlay-audit-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-contact-sheet", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = build_review_pack_report(
        overlay_audit_path=args.overlay_audit,
        output_dir=args.output_dir,
        repo_root=args.repo_root,
        max_review_cards=args.max_review_cards,
        max_contact_sheet_cards=args.max_contact_sheet_cards,
        contact_sheet_columns=args.contact_sheet_columns,
        contact_sheet_thumb_width=args.contact_sheet_thumb_width,
        write_contact_sheets=not args.no_contact_sheets,
        thresholds=thresholds_from_args(args),
    )
    summary = report.get("summary") or {}
    print("TRACE-Net Table Detector Overlay Review Pack v1")
    print(" Status:", report.get("status"))
    print(" Quality status:", report.get("quality_status"))
    for key in [
        "review_card_count",
        "overlay_ready_card_count",
        "contact_sheet_count",
        "detector_disagreement_card_count",
        "estimator_exceeds_production_card_count",
        "production_exceeds_estimator_card_count",
        "unsafe_review_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}:", summary.get(key))
    print(" report_path:", report.get("artifact_paths", {}).get("report_path"))
    if summary.get("contact_sheet_paths"):
        print(" contact_sheets:")
        for path in summary["contact_sheet_paths"]:
            print("  -", path)
    return 0 if report.get("quality_status") == "PASS" or not args.quality else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
