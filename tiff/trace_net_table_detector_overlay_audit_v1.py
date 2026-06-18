"""TRACE-Net Table Detector Overlay Audit v1.

Read-only diagnostic module that creates audit cards and optional PNG overlays for
margin detector disagreements.  It is intentionally advisory: it never grants
answer authority and never mutates source truth.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_table_detector_overlay_audit_v1"
QUALITY_SCHEMA_VERSION = "trace_net_table_detector_overlay_audit_v1_quality"

SAFETY_CONTRACT = {
    "read_only_diagnostic": True,
    "no_postgres_writes": True,
    "no_qdrant_writes": True,
    "no_opensearch_writes": True,
    "no_source_truth_mutation": True,
    "no_answer_permission": True,
    "can_answer_directly": False,
    "can_prove_claims": False,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True))
            f.write("\n")


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def stable_id(*parts: Any) -> str:
    import hashlib

    text = "::".join(str(p) for p in parts if p is not None)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def normalize_path(path_value: str | None, image_root: Path) -> Path | None:
    if not path_value:
        return None
    raw = Path(str(path_value).replace("\\", "/"))
    if raw.is_absolute():
        return raw
    return image_root / raw


def card_key(card: dict[str, Any]) -> tuple[str | None, str | None]:
    return card.get("page_id"), card.get("table_id")


def index_bbox_cards(bbox_payload: dict[str, Any]) -> dict[tuple[str | None, str | None], dict[str, Any]]:
    out: dict[tuple[str | None, str | None], dict[str, Any]] = {}
    for card in as_list(bbox_payload.get("table_bbox_cards")):
        if isinstance(card, dict):
            out[card_key(card)] = card
    return out


def clip_bbox(bbox: dict[str, Any] | None, width: int, height: int) -> tuple[int, int, int, int] | None:
    if not isinstance(bbox, dict):
        return None
    x0 = max(0, min(width, int(round(safe_float(bbox.get("x0"))))))
    y0 = max(0, min(height, int(round(safe_float(bbox.get("y0"))))))
    x1 = max(0, min(width, int(round(safe_float(bbox.get("x1"))))))
    y1 = max(0, min(height, int(round(safe_float(bbox.get("y1"))))))
    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1, y1


def signal_rank(signal: str | None) -> int:
    return {
        "NO_LINE_SIGNAL": 0,
        "WEAK_LINE_SIGNAL": 1,
        "PARTIAL_GRID": 2,
        "GRID": 3,
    }.get(str(signal or ""), 0)


def best_candidate(card: dict[str, Any], key: str) -> dict[str, Any]:
    candidate = card.get(key)
    return candidate if isinstance(candidate, dict) else {}


def choose_overlay_candidate(card: dict[str, Any]) -> dict[str, Any]:
    """Prefer the experiment-best candidate when present, else production-best."""
    experiment = best_candidate(card, "estimator_best_candidate")
    production = best_candidate(card, "production_best_candidate")
    if experiment.get("expanded_bbox"):
        return experiment
    return production


def try_import_pillow() -> tuple[Any, Any, Any] | tuple[None, None, None]:
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore

        return Image, ImageDraw, ImageFont
    except Exception:
        return None, None, None


def detect_projection_lines(image: Any, bbox: tuple[int, int, int, int]) -> dict[str, Any]:
    """Lightweight audit-only line detector for overlay visualization.

    This detector is not source truth and is intentionally separate from the
    production route.  It only helps reviewers see where dense ink projections
    occur inside a candidate crop.
    """
    x0, y0, x1, y1 = bbox
    crop = image.crop((x0, y0, x1, y1)).convert("L")
    width, height = crop.size
    if width <= 2 or height <= 2:
        return {"horizontal_positions": [], "vertical_positions": []}

    try:
        import numpy as np  # type: ignore

        arr = np.asarray(crop) < 128
        row_density = arr.sum(axis=1) / max(1, width)
        col_density = arr.sum(axis=0) / max(1, height)
        horizontal_positions = group_positions([i for i, v in enumerate(row_density) if float(v) >= 0.45])
        vertical_positions = group_positions([i for i, v in enumerate(col_density) if float(v) >= 0.22])
    except Exception:
        pixels = list(crop.getdata())
        horizontal_hits: list[int] = []
        for y in range(height):
            row = pixels[y * width : (y + 1) * width]
            black = sum(1 for p in row if p < 128)
            if black / max(1, width) >= 0.45:
                horizontal_hits.append(y)
        vertical_hits: list[int] = []
        for x in range(width):
            black = 0
            for y in range(height):
                if pixels[y * width + x] < 128:
                    black += 1
            if black / max(1, height) >= 0.22:
                vertical_hits.append(x)
        horizontal_positions = group_positions(horizontal_hits)
        vertical_positions = group_positions(vertical_hits)

    return {
        "horizontal_positions": horizontal_positions[:200],
        "vertical_positions": vertical_positions[:200],
    }


def group_positions(positions: list[int], min_group_len: int = 2) -> list[int]:
    if not positions:
        return []
    groups: list[list[int]] = []
    current = [positions[0]]
    for pos in positions[1:]:
        if pos <= current[-1] + 1:
            current.append(pos)
        else:
            if len(current) >= min_group_len:
                groups.append(current)
            current = [pos]
    if len(current) >= min_group_len:
        groups.append(current)
    return [int(round(sum(g) / len(g))) for g in groups]


def draw_overlay(
    *,
    image_path: Path,
    output_path: Path,
    card: dict[str, Any],
    max_side: int,
) -> dict[str, Any]:
    Image, ImageDraw, ImageFont = try_import_pillow()
    if Image is None or ImageDraw is None:
        return {"overlay_ready": False, "overlay_error": "pillow_unavailable"}
    if not image_path.exists():
        return {"overlay_ready": False, "overlay_error": "image_not_found"}

    try:
        with Image.open(image_path) as im_raw:
            image = im_raw.convert("RGB")
    except Exception as exc:
        return {"overlay_ready": False, "overlay_error": f"image_open_failed:{exc.__class__.__name__}"}

    width, height = image.size
    prod = best_candidate(card, "production_best_candidate")
    est = best_candidate(card, "estimator_best_candidate")
    prod_bbox = clip_bbox(prod.get("expanded_bbox"), width, height)
    est_bbox = clip_bbox(est.get("expanded_bbox"), width, height)
    chosen = est_bbox or prod_bbox
    if chosen is None:
        return {"overlay_ready": False, "overlay_error": "candidate_bbox_missing"}

    projection = detect_projection_lines(image, chosen)

    scale = min(1.0, max_side / max(width, height)) if max_side else 1.0
    display = image.resize((int(width * scale), int(height * scale))) if scale < 1 else image.copy()
    draw = ImageDraw.Draw(display)

    def sx(v: float) -> int:
        return int(round(v * scale))

    def draw_box(box: tuple[int, int, int, int] | None, color: str, label: str) -> None:
        if box is None:
            return
        x0, y0, x1, y1 = box
        draw.rectangle([sx(x0), sx(y0), sx(x1), sx(y1)], outline=color, width=max(2, int(3 * scale)))
        draw.text((sx(x0) + 4, sx(y0) + 4), label, fill=color)

    draw_box(prod_bbox, "red", "production candidate")
    draw_box(est_bbox, "blue", "estimator candidate")

    x0, y0, x1, y1 = chosen
    for yy in projection.get("horizontal_positions", [])[:80]:
        draw.line([sx(x0), sx(y0 + yy), sx(x1), sx(y0 + yy)], fill="orange", width=max(1, int(2 * scale)))
    for xx in projection.get("vertical_positions", [])[:80]:
        draw.line([sx(x0 + xx), sx(y0), sx(x0 + xx), sx(y1)], fill="cyan", width=max(1, int(2 * scale)))

    header = (
        f"{card.get('page_id')} / {card.get('table_id')} | "
        f"prod V/I={prod.get('production_vertical_line_count')}/{prod.get('production_intersection_count')} | "
        f"est V/I={est.get('estimator_vertical_line_count')}/{est.get('estimator_intersection_count')}"
    )
    draw.rectangle([0, 0, display.size[0], 28], fill="white")
    draw.text((6, 6), header[:220], fill="black")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    display.save(output_path)
    return {
        "overlay_ready": True,
        "overlay_path": str(output_path.as_posix()),
        "overlay_projection_horizontal_count": len(projection.get("horizontal_positions", [])),
        "overlay_projection_vertical_count": len(projection.get("vertical_positions", [])),
        "overlay_candidate_bbox": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
    }


@dataclass(frozen=True)
class Thresholds:
    min_audit_cards: int = 1
    min_detector_disagreement_cards: int = 0
    min_overlay_ready_cards: int = 0
    max_unsafe_audit_cards: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_margin_detector_parity_quality_pass: bool = False
    require_table_bbox_resolver_quality_pass: bool = False
    require_no_answer_permission: bool = False


def make_audit_card(
    *,
    parity_card: dict[str, Any],
    bbox_card: dict[str, Any] | None,
    image_root: Path,
    overlay_dir: Path,
    make_overlays: bool,
    max_overlay_side: int,
    index: int,
) -> dict[str, Any]:
    page_id, table_id = card_key(parity_card)
    production = best_candidate(parity_card, "production_best_candidate")
    estimator = best_candidate(parity_card, "estimator_best_candidate")

    image_path_value = None
    if bbox_card:
        image_path_value = (
            bbox_card.get("resolved_image_path")
            or bbox_card.get("image_path")
            or bbox_card.get("source_image_path")
        )
    image_path = normalize_path(str(image_path_value), image_root) if image_path_value else None

    vertical_delta = safe_int(parity_card.get("best_vertical_delta_estimator_minus_production"))
    intersection_delta = safe_int(parity_card.get("best_intersection_delta_estimator_minus_production"))
    signal_delta = safe_int(parity_card.get("best_signal_rank_delta_estimator_minus_production"))
    detector_disagreement = bool(parity_card.get("detector_disagreement"))
    estimator_exceeds = bool(parity_card.get("estimator_exceeds_production")) or vertical_delta > 0 or intersection_delta > 0 or signal_delta > 0
    production_exceeds = bool(parity_card.get("production_exceeds_estimator"))

    overlay_result: dict[str, Any] = {"overlay_ready": False, "overlay_error": "overlay_generation_disabled"}
    if make_overlays and image_path is not None:
        safe_name = f"{index:03d}_{str(page_id or 'unknown').replace('/', '_')}_{stable_id(page_id, table_id)}.png"
        overlay_result = draw_overlay(
            image_path=image_path,
            output_path=overlay_dir / safe_name,
            card=parity_card,
            max_side=max_overlay_side,
        )

    review_flags: list[str] = []
    recommended_actions: list[str] = []
    if detector_disagreement:
        review_flags.append("detector_outputs_disagree_on_same_crop")
        recommended_actions.append("inspect_detector_line_overlay")
    if estimator_exceeds:
        review_flags.append("estimator_counts_more_grid_evidence")
        recommended_actions.append("verify_estimator_lines_are_table_rules_not_text_strokes")
    if production_exceeds:
        review_flags.append("production_counts_more_grid_evidence_on_some_candidates")
        recommended_actions.append("compare_candidate_selection_rules")
    if not overlay_result.get("overlay_ready"):
        review_flags.append("line_overlay_not_available")
        recommended_actions.append("resolve_overlay_image_path_or_pillow_dependency")

    return {
        "schema_version": SCHEMA_VERSION,
        "audit_card_id": f"detector_overlay_audit::{stable_id(page_id, table_id)}",
        "page_id": page_id,
        "table_id": table_id,
        "table_type": parity_card.get("table_type"),
        "bbox_source": parity_card.get("bbox_source"),
        "selected_morphology_scope": parity_card.get("selected_morphology_scope"),
        "resolved_image_path": str(image_path.as_posix()) if image_path else None,
        "detector_disagreement": detector_disagreement,
        "estimator_exceeds_production": estimator_exceeds,
        "production_exceeds_estimator": production_exceeds,
        "best_vertical_delta_estimator_minus_production": vertical_delta,
        "best_intersection_delta_estimator_minus_production": intersection_delta,
        "best_signal_rank_delta_estimator_minus_production": signal_delta,
        "production_best_candidate": production,
        "estimator_best_candidate": estimator,
        "overlay_ready": bool(overlay_result.get("overlay_ready")),
        "overlay_path": overlay_result.get("overlay_path"),
        "overlay_error": overlay_result.get("overlay_error"),
        "overlay_projection_horizontal_count": overlay_result.get("overlay_projection_horizontal_count", 0),
        "overlay_projection_vertical_count": overlay_result.get("overlay_projection_vertical_count", 0),
        "overlay_candidate_bbox": overlay_result.get("overlay_candidate_bbox"),
        "review_required": True,
        "review_flags": sorted(set(review_flags)),
        "recommended_actions": sorted(set(recommended_actions)),
        "unsafe_audit_card": False,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "retrieval_only_answer_allowed": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "safety_contract": SAFETY_CONTRACT,
    }


def summarize(cards: list[dict[str, Any]], *, parity_payload: dict[str, Any], bbox_payload: dict[str, Any]) -> dict[str, Any]:
    def count(field: str) -> int:
        return sum(1 for c in cards if c.get(field))

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "quality_status": "PASS",
        "audit_card_count": len(cards),
        "detector_disagreement_card_count": count("detector_disagreement"),
        "estimator_exceeds_production_card_count": count("estimator_exceeds_production"),
        "production_exceeds_estimator_card_count": count("production_exceeds_estimator"),
        "overlay_ready_card_count": count("overlay_ready"),
        "overlay_missing_card_count": sum(1 for c in cards if not c.get("overlay_ready")),
        "line_overlay_candidate_card_count": sum(
            1
            for c in cards
            if safe_int(c.get("overlay_projection_horizontal_count")) > 0
            or safe_int(c.get("overlay_projection_vertical_count")) > 0
        ),
        "review_required_card_count": count("review_required"),
        "unsafe_audit_card_count": count("unsafe_audit_card"),
        "answer_permission_count": count("answer_permission"),
        "can_answer_directly_count": count("can_answer_directly"),
        "can_prove_claims_count": count("can_prove_claims"),
        "source_truth_mutation_allowed_count": count("source_truth_mutation_allowed"),
        "postgres_write_attempt_count": sum(safe_int(c.get("postgres_write_attempt_count")) for c in cards),
        "qdrant_write_attempt_count": sum(safe_int(c.get("qdrant_write_attempt_count")) for c in cards),
        "opensearch_write_attempt_count": sum(safe_int(c.get("opensearch_write_attempt_count")) for c in cards),
        "source_quality_statuses": {
            "margin_detector_parity": parity_payload.get("quality_status"),
            "table_bbox_resolver": bbox_payload.get("quality_status"),
        },
        "quality_fail_reasons": [],
    }


def evaluate_quality(summary: dict[str, Any], thresholds: Thresholds) -> tuple[str, list[str], dict[str, bool]]:
    checks = {
        "min_audit_cards_met": safe_int(summary.get("audit_card_count")) >= thresholds.min_audit_cards,
        "min_detector_disagreement_cards_met": safe_int(summary.get("detector_disagreement_card_count")) >= thresholds.min_detector_disagreement_cards,
        "min_overlay_ready_cards_met": safe_int(summary.get("overlay_ready_card_count")) >= thresholds.min_overlay_ready_cards,
        "unsafe_audit_cards_within_limit": safe_int(summary.get("unsafe_audit_card_count")) <= thresholds.max_unsafe_audit_cards,
        "answer_permission_within_limit": safe_int(summary.get("answer_permission_count")) <= thresholds.max_answer_permission_count,
        "source_truth_mutation_allowed_within_limit": safe_int(summary.get("source_truth_mutation_allowed_count")) <= thresholds.max_source_truth_mutation_allowed,
        "margin_detector_parity_quality_pass": (not thresholds.require_margin_detector_parity_quality_pass)
        or summary.get("source_quality_statuses", {}).get("margin_detector_parity") == "PASS",
        "table_bbox_resolver_quality_pass": (not thresholds.require_table_bbox_resolver_quality_pass)
        or summary.get("source_quality_statuses", {}).get("table_bbox_resolver") == "PASS",
        "no_answer_permission": (not thresholds.require_no_answer_permission)
        or safe_int(summary.get("answer_permission_count")) == 0,
        "schema_version_ok": summary.get("schema_version") == SCHEMA_VERSION,
    }
    fail_reasons = [name for name, ok in checks.items() if not ok]
    return ("PASS" if not fail_reasons else "FAIL", fail_reasons, checks)


def build_report(
    *,
    margin_detector_parity_path: Path,
    table_bbox_resolver_path: Path,
    image_root: Path,
    output_dir: Path,
    make_overlays: bool = True,
    max_overlay_cards: int = 20,
    max_overlay_side: int = 1600,
    thresholds: Thresholds = Thresholds(),
) -> dict[str, Any]:
    parity_payload = read_json(margin_detector_parity_path)
    bbox_payload = read_json(table_bbox_resolver_path)
    bbox_index = index_bbox_cards(bbox_payload)
    parity_cards = [c for c in as_list(parity_payload.get("parity_cards")) if isinstance(c, dict)]

    overlay_dir = output_dir / "overlays"
    cards: list[dict[str, Any]] = []
    for index, parity_card in enumerate(parity_cards, start=1):
        bbox_card = bbox_index.get(card_key(parity_card))
        card_make_overlay = make_overlays and index <= max_overlay_cards
        cards.append(
            make_audit_card(
                parity_card=parity_card,
                bbox_card=bbox_card,
                image_root=image_root,
                overlay_dir=overlay_dir,
                make_overlays=card_make_overlay,
                max_overlay_side=max_overlay_side,
                index=index,
            )
        )

    summary = summarize(cards, parity_payload=parity_payload, bbox_payload=bbox_payload)
    quality_status, fail_reasons, checks = evaluate_quality(summary, thresholds)
    summary["quality_status"] = quality_status
    summary["status"] = "PASS" if quality_status == "PASS" else "TABLE_DETECTOR_OVERLAY_AUDIT_NOT_READY"
    summary["quality_fail_reasons"] = fail_reasons

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_table_detector_overlay_audit_v1.json"
    cards_path = output_dir / "trace_net_table_detector_overlay_audit_v1_cards.jsonl"
    summary_path = output_dir / "trace_net_table_detector_overlay_audit_v1_summary.json"
    quality_path = output_dir / "trace_net_table_detector_overlay_audit_v1_quality.json"
    manifest_path = output_dir / "trace_net_table_detector_overlay_audit_v1_manifest.json"

    report = {
        "schema_version": SCHEMA_VERSION,
        "status": summary["status"],
        "quality_status": quality_status,
        "generated_at": utc_now(),
        "inputs": {
            "margin_detector_parity": str(margin_detector_parity_path),
            "table_bbox_resolver": str(table_bbox_resolver_path),
            "image_root": str(image_root),
        },
        "output_paths": {
            "report": str(report_path),
            "cards_jsonl": str(cards_path),
            "summary": str(summary_path),
            "quality": str(quality_path),
            "manifest": str(manifest_path),
            "overlays": str(overlay_dir),
        },
        "summary": summary,
        "checks": checks,
        "audit_cards": cards,
        "safety_contract": SAFETY_CONTRACT,
    }

    quality_payload = {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "status": quality_status,
        "quality_status": quality_status,
        "generated_at": utc_now(),
        "summary": summary,
        "checks": checks,
        "quality_fail_reasons": fail_reasons,
    }
    manifest = {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": utc_now(),
        "files": [
            str(report_path),
            str(cards_path),
            str(summary_path),
            str(quality_path),
            str(manifest_path),
        ],
        "overlay_dir": str(overlay_dir),
        "safety_contract": SAFETY_CONTRACT,
    }

    write_json(report_path, report)
    write_jsonl(cards_path, cards)
    write_json(summary_path, summary)
    write_json(quality_path, quality_payload)
    write_json(manifest_path, manifest)
    return report


def thresholds_from_args(args: argparse.Namespace) -> Thresholds:
    return Thresholds(
        min_audit_cards=args.min_audit_cards,
        min_detector_disagreement_cards=args.min_detector_disagreement_cards,
        min_overlay_ready_cards=args.min_overlay_ready_cards,
        max_unsafe_audit_cards=args.max_unsafe_audit_cards,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_margin_detector_parity_quality_pass=args.require_margin_detector_parity_quality_pass,
        require_table_bbox_resolver_quality_pass=args.require_table_bbox_resolver_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net table detector overlay audit v1")
    parser.add_argument("--margin-detector-parity", required=True, type=Path)
    parser.add_argument("--table-bbox-resolver", required=True, type=Path)
    parser.add_argument("--image-root", default=".", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-overlay-cards", default=20, type=int)
    parser.add_argument("--max-overlay-side", default=1600, type=int)
    parser.add_argument("--no-overlays", action="store_true")
    parser.add_argument("--min-audit-cards", default=1, type=int)
    parser.add_argument("--min-detector-disagreement-cards", default=0, type=int)
    parser.add_argument("--min-overlay-ready-cards", default=0, type=int)
    parser.add_argument("--max-unsafe-audit-cards", default=0, type=int)
    parser.add_argument("--max-answer-permission-count", default=0, type=int)
    parser.add_argument("--max-source-truth-mutation-allowed", default=0, type=int)
    parser.add_argument("--require-margin-detector-parity-quality-pass", action="store_true")
    parser.add_argument("--require-table-bbox-resolver-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def print_summary(report: dict[str, Any]) -> None:
    summary = report.get("summary", {})
    print("TRACE-Net Table Detector Overlay Audit v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "audit_card_count",
        "detector_disagreement_card_count",
        "estimator_exceeds_production_card_count",
        "production_exceeds_estimator_card_count",
        "overlay_ready_card_count",
        "line_overlay_candidate_card_count",
        "unsafe_audit_card_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {report.get('output_paths', {}).get('report')}")
    print(f" overlays: {report.get('output_paths', {}).get('overlays')}")


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = build_report(
        margin_detector_parity_path=args.margin_detector_parity,
        table_bbox_resolver_path=args.table_bbox_resolver,
        image_root=args.image_root,
        output_dir=args.output_dir,
        make_overlays=not args.no_overlays,
        max_overlay_cards=args.max_overlay_cards,
        max_overlay_side=args.max_overlay_side,
        thresholds=thresholds_from_args(args),
    )
    print_summary(report)
    return 0 if report.get("quality_status") == "PASS" or not args.quality else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
