"""TRACE-Net table extraction bbox overlay export v1.

Creates PNG overlays so Paddle-style table extraction bboxes can be viewed
visually instead of only as coordinates.

Read-only safety:
- no database writes
- no vector/search writes
- no source-truth mutation
- no answer permission
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = "trace_net_table_extraction_bbox_overlay_export_v1"
QUALITY_SCHEMA_VERSION = f"{SCHEMA_VERSION}_quality"
STATUS_BUILT = "TRACE_NET_TABLE_EXTRACTION_BBOX_OVERLAY_EXPORT_BUILT"
STATUS_NOT_READY = "TRACE_NET_TABLE_EXTRACTION_BBOX_OVERLAY_EXPORT_NOT_READY"

DEFAULT_TABLE_LINE_GEOMETRY = Path(
    "local_data/organization/trace_net/table_line_geometry/trace_net_table_line_geometry_v1.json"
)
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/table_extraction_bbox_overlay_export")
DEFAULT_REPORT_NAME = "trace_net_table_extraction_bbox_overlay_export_v1.json"
DEFAULT_QUALITY_NAME = "trace_net_table_extraction_bbox_overlay_export_v1_quality.json"


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}


@dataclass(frozen=True)
class OverlayThresholds:
    min_overlay_records: int = 1
    min_overlay_pngs: int = 1
    max_missing_extraction_bbox_count: int = 0
    max_unsafe_record_count: int = 0
    max_answer_permission_count: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_table_line_geometry_quality_pass: bool = True
    require_no_answer_permission: bool = True


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")


def safe_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(value)
    except Exception:
        return 0


def safe_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def safe_text(value: Any) -> str:
    return "" if value is None else str(value)


def quality_status(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    quality = payload.get("quality") if isinstance(payload.get("quality"), Mapping) else {}
    return safe_text(
        payload.get("quality_status")
        or quality.get("status")
        or quality.get("quality_status")
        or summary.get("quality_status")
        or payload.get("status")
        or "UNKNOWN"
    )


def parse_bbox(raw: Any) -> dict[str, float] | None:
    if raw is None:
        return None
    if isinstance(raw, Mapping):
        if {"x0", "y0", "x1", "y1"}.issubset(raw):
            vals = {
                "x0": safe_float(raw.get("x0")),
                "y0": safe_float(raw.get("y0")),
                "x1": safe_float(raw.get("x1")),
                "y1": safe_float(raw.get("y1")),
            }
        elif {"left", "top", "right", "bottom"}.issubset(raw):
            vals = {
                "x0": safe_float(raw.get("left")),
                "y0": safe_float(raw.get("top")),
                "x1": safe_float(raw.get("right")),
                "y1": safe_float(raw.get("bottom")),
            }
        elif {"x", "y", "width", "height"}.issubset(raw):
            x = safe_float(raw.get("x"))
            y = safe_float(raw.get("y"))
            vals = {
                "x0": x,
                "y0": y,
                "x1": x + safe_float(raw.get("width")),
                "y1": y + safe_float(raw.get("height")),
            }
        else:
            return None
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)) and len(raw) == 4:
        vals = {
            "x0": safe_float(raw[0]),
            "y0": safe_float(raw[1]),
            "x1": safe_float(raw[2]),
            "y1": safe_float(raw[3]),
        }
    else:
        return None

    x0, x1 = sorted([vals["x0"], vals["x1"]])
    y0, y1 = sorted([vals["y0"], vals["y1"]])
    if x1 <= x0 or y1 <= y0:
        return None
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}


def bbox_to_pixels(bbox: Mapping[str, float], image_width: int, image_height: int) -> tuple[int, int, int, int]:
    x0 = safe_float(bbox.get("x0"))
    y0 = safe_float(bbox.get("y0"))
    x1 = safe_float(bbox.get("x1"))
    y1 = safe_float(bbox.get("y1"))

    if max(abs(x0), abs(y0), abs(x1), abs(y1)) <= 1.5:
        x0 *= image_width
        x1 *= image_width
        y0 *= image_height
        y1 *= image_height

    return (
        max(0, min(image_width - 1, int(round(x0)))),
        max(0, min(image_height - 1, int(round(y0)))),
        max(0, min(image_width - 1, int(round(x1)))),
        max(0, min(image_height - 1, int(round(y1)))),
    )


def iter_strings(obj: Any, depth: int = 0, max_depth: int = 5) -> Iterable[str]:
    if depth > max_depth:
        return
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, Mapping):
        for value in obj.values():
            yield from iter_strings(value, depth + 1, max_depth)
    elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        for value in list(obj)[:200]:
            yield from iter_strings(value, depth + 1, max_depth)


def resolve_existing_path(candidate: str, image_root: Path) -> Path | None:
    if not candidate:
        return None
    text = candidate.strip().strip('"').strip("'")
    if not text:
        return None
    path = Path(text)
    if path.suffix.lower() not in IMAGE_SUFFIXES:
        return None

    candidates = []
    if path.is_absolute():
        candidates.append(path)
    else:
        candidates.append(Path.cwd() / path)
        candidates.append(image_root / path)

    # Common case: artifact paths are already repo-relative with backslashes.
    normalized = Path(text.replace("\\", "/"))
    if not normalized.is_absolute():
        candidates.append(Path.cwd() / normalized)
        candidates.append(image_root / normalized)

    for item in candidates:
        if item.exists() and item.is_file():
            return item
    return None


def find_image_path(card: Mapping[str, Any], image_root: Path) -> Path | None:
    preferred_keys = [
        "resolved_image_path",
        "image_path",
        "page_image_path",
        "source_image_path",
        "table_image_path",
        "crop_image_path",
        "overlay_path",
    ]
    for key in preferred_keys:
        found = resolve_existing_path(safe_text(card.get(key)), image_root)
        if found:
            return found

    for value in iter_strings(card):
        found = resolve_existing_path(value, image_root)
        if found:
            return found
    return None


def page_id_for_filename(value: Any) -> str:
    text = safe_text(value or "unknown_page")
    keep = []
    for char in text:
        keep.append(char if char.isalnum() or char in {"-", "_"} else "_")
    return "".join(keep)[:120]


def draw_overlay(
    *,
    image_path: Path | None,
    output_path: Path,
    extraction_bbox: Mapping[str, float],
    region_bbox: Mapping[str, float] | None,
    label: str,
) -> tuple[bool, str | None, int, int]:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as exc:  # pragma: no cover
        return False, f"pillow_unavailable:{exc}", 0, 0

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if image_path and image_path.exists():
        img = Image.open(image_path).convert("RGB")
    else:
        max_x = max(safe_float(extraction_bbox.get("x1")), safe_float((region_bbox or {}).get("x1")))
        max_y = max(safe_float(extraction_bbox.get("y1")), safe_float((region_bbox or {}).get("y1")))
        width = max(800, int(math.ceil(max_x + 100)))
        height = max(1000, int(math.ceil(max_y + 100)))
        img = Image.new("RGB", (width, height), "white")

    draw = ImageDraw.Draw(img)
    width, height = img.size

    if region_bbox:
        rx0, ry0, rx1, ry1 = bbox_to_pixels(region_bbox, width, height)
        draw.rectangle([rx0, ry0, rx1, ry1], outline=(255, 180, 0), width=4)

    x0, y0, x1, y1 = bbox_to_pixels(extraction_bbox, width, height)
    draw.rectangle([x0, y0, x1, y1], outline=(0, 220, 0), width=7)

    text_bg = [0, 0, min(width - 1, max(360, len(label) * 7)), 42]
    draw.rectangle(text_bg, fill=(255, 255, 255))
    draw.text((8, 8), label, fill=(0, 0, 0))

    legend_y = min(height - 70, 50)
    draw.rectangle([8, legend_y, 38, legend_y + 20], outline=(0, 220, 0), width=5)
    draw.text((48, legend_y), "table_extraction_bbox", fill=(0, 0, 0))
    if region_bbox:
        draw.rectangle([8, legend_y + 30, 38, legend_y + 50], outline=(255, 180, 0), width=4)
        draw.text((48, legend_y + 30), "table_region_bbox", fill=(0, 0, 0))

    img.save(output_path)
    return True, None, width, height


def make_contact_sheet(records: Sequence[Mapping[str, Any]], output_path: Path, thumb_width: int = 360) -> bool:
    try:
        from PIL import Image, ImageDraw
    except Exception:  # pragma: no cover
        return False

    images = []
    for record in records:
        path = Path(safe_text(record.get("overlay_png_path")))
        if path.exists():
            img = Image.open(path).convert("RGB")
            ratio = thumb_width / max(1, img.width)
            thumb = img.resize((thumb_width, max(1, int(img.height * ratio))))
            images.append((record, thumb))
    if not images:
        return False

    cols = 2
    rows = math.ceil(len(images) / cols)
    label_h = 42
    cell_w = thumb_width
    cell_h = max(img.height for _, img in images) + label_h
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), "white")
    draw = ImageDraw.Draw(sheet)

    for idx, (record, img) in enumerate(images):
        col = idx % cols
        row = idx // cols
        x = col * cell_w
        y = row * cell_h
        label = f"{record.get('page_id')} | {record.get('table_id')}"
        draw.text((x + 6, y + 6), label[:55], fill=(0, 0, 0))
        sheet.paste(img, (x, y + label_h))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)
    return True


def build_quality(summary: Mapping[str, Any], thresholds: OverlayThresholds) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(name: str, actual: Any, op: str, expected: Any, passed: bool) -> None:
        checks.append({"name": name, "actual": actual, "op": op, "expected": expected, "passed": bool(passed)})

    check("overlay_record_count", summary.get("overlay_record_count"), ">=", thresholds.min_overlay_records, safe_int(summary.get("overlay_record_count")) >= thresholds.min_overlay_records)
    check("overlay_png_count", summary.get("overlay_png_count"), ">=", thresholds.min_overlay_pngs, safe_int(summary.get("overlay_png_count")) >= thresholds.min_overlay_pngs)
    check("missing_extraction_bbox_count", summary.get("missing_extraction_bbox_count"), "<=", thresholds.max_missing_extraction_bbox_count, safe_int(summary.get("missing_extraction_bbox_count")) <= thresholds.max_missing_extraction_bbox_count)
    check("unsafe_record_count", summary.get("unsafe_record_count"), "<=", thresholds.max_unsafe_record_count, safe_int(summary.get("unsafe_record_count")) <= thresholds.max_unsafe_record_count)
    check("answer_permission_count", summary.get("answer_permission_count"), "<=", thresholds.max_answer_permission_count, safe_int(summary.get("answer_permission_count")) <= thresholds.max_answer_permission_count)
    check("source_truth_mutation_allowed_count", summary.get("source_truth_mutation_allowed_count"), "<=", thresholds.max_source_truth_mutation_allowed, safe_int(summary.get("source_truth_mutation_allowed_count")) <= thresholds.max_source_truth_mutation_allowed)

    if thresholds.require_table_line_geometry_quality_pass:
        check("table_line_geometry_quality_status", summary.get("table_line_geometry_quality_status"), "==", "PASS", summary.get("table_line_geometry_quality_status") == "PASS")
    if thresholds.require_no_answer_permission:
        check("no_answer_permission", summary.get("answer_permission_count"), "==", 0, safe_int(summary.get("answer_permission_count")) == 0)
        check("no_can_answer_directly", summary.get("can_answer_directly_count"), "==", 0, safe_int(summary.get("can_answer_directly_count")) == 0)
        check("no_can_prove_claims", summary.get("can_prove_claims_count"), "==", 0, safe_int(summary.get("can_prove_claims_count")) == 0)

    status = "PASS" if all(item["passed"] for item in checks) else "FAIL"
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "status": status,
        "quality_status": status,
        "checks": checks,
        "summary": dict(summary),
    }


def build_table_extraction_bbox_overlay_export_report(
    *,
    table_line_geometry_path: Path = DEFAULT_TABLE_LINE_GEOMETRY,
    image_root: Path = Path("."),
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    thresholds: OverlayThresholds | None = None,
    max_cards: int = 0,
    write_outputs: bool = True,
) -> dict[str, Any]:
    thresholds = thresholds or OverlayThresholds()
    payload = read_json(table_line_geometry_path)
    cards = payload.get("table_geometry_cards") or payload.get("records") or []
    if not isinstance(cards, list):
        cards = []
    if max_cards and max_cards > 0:
        cards = cards[:max_cards]

    overlays_dir = output_dir / "overlays"
    records: list[dict[str, Any]] = []

    for idx, card in enumerate(cards, start=1):
        if not isinstance(card, Mapping):
            continue

        page_id = safe_text(card.get("page_id") or f"page_{idx:06d}")
        table_id = safe_text(card.get("table_id") or f"table_{idx:06d}")
        extraction_bbox = parse_bbox(card.get("table_extraction_bbox") or card.get("table_region_bbox"))
        region_bbox = parse_bbox(card.get("table_region_bbox"))

        record = {
            "schema_version": SCHEMA_VERSION,
            "page_id": page_id,
            "table_id": table_id,
            "table_extraction_bbox_source": card.get("table_extraction_bbox_source") or card.get("table_region_bbox_source"),
            "table_extraction_bbox": extraction_bbox,
            "table_region_bbox_source": card.get("table_region_bbox_source"),
            "table_region_bbox": region_bbox,
            "table_extraction_scope": card.get("table_extraction_scope"),
            "selected_morphology_scope": card.get("selected_morphology_scope"),
            "review_required": bool(card.get("review_required")),
            "review_flags": list(card.get("review_flags") or []),
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "unsafe_record": False,
        }

        image_path = find_image_path(card, image_root)
        record["source_image_path"] = str(image_path) if image_path else None

        if extraction_bbox:
            name = f"{idx:03d}_{page_id_for_filename(page_id)}_{page_id_for_filename(table_id)}_bbox_overlay.png"
            output_path = overlays_dir / name
            ok, error, width, height = draw_overlay(
                image_path=image_path,
                output_path=output_path,
                extraction_bbox=extraction_bbox,
                region_bbox=region_bbox,
                label=f"{page_id} | {table_id} | {record['table_extraction_bbox_source']}",
            )
            record["overlay_png_path"] = str(output_path) if ok else None
            record["overlay_error"] = error
            record["image_width"] = width
            record["image_height"] = height
        else:
            record["overlay_png_path"] = None
            record["overlay_error"] = "missing_table_extraction_bbox"
            record["image_width"] = 0
            record["image_height"] = 0

        records.append(record)

    contact_sheet_path = output_dir / "trace_net_table_extraction_bbox_overlay_contact_sheet_v1.png"
    contact_sheet_created = make_contact_sheet(records, contact_sheet_path)

    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "table_line_geometry_path": str(table_line_geometry_path),
        "table_line_geometry_quality_status": quality_status(payload if isinstance(payload, Mapping) else {}),
        "overlay_record_count": len(records),
        "overlay_png_count": sum(1 for record in records if record.get("overlay_png_path")),
        "contact_sheet_created": contact_sheet_created,
        "contact_sheet_path": str(contact_sheet_path) if contact_sheet_created else None,
        "source_image_found_count": sum(1 for record in records if record.get("source_image_path")),
        "blank_canvas_overlay_count": sum(1 for record in records if record.get("overlay_png_path") and not record.get("source_image_path")),
        "missing_extraction_bbox_count": sum(1 for record in records if not record.get("table_extraction_bbox")),
        "paddle_style_extraction_bbox_count": sum(1 for record in records if record.get("table_extraction_bbox_source") == "table_paddle_style_bbox_resolver"),
        "review_required_count": sum(1 for record in records if record.get("review_required")),
        "unsafe_record_count": 0,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }

    quality = build_quality(summary, thresholds)
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": summary["generated_at_utc"],
        "status": STATUS_BUILT if quality["status"] == "PASS" else STATUS_NOT_READY,
        "quality_status": quality["status"],
        "summary": summary,
        "overlay_records": records,
        "quality": quality,
    }

    if write_outputs:
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / DEFAULT_REPORT_NAME
        quality_path = output_dir / DEFAULT_QUALITY_NAME
        jsonl_path = output_dir / "trace_net_table_extraction_bbox_overlay_export_v1_records.jsonl"
        summary_path = output_dir / "trace_net_table_extraction_bbox_overlay_export_v1_summary.json"
        write_json(report_path, report)
        write_json(quality_path, quality)
        write_json(summary_path, summary)
        with jsonl_path.open("w", encoding="utf-8", newline="\n") as handle:
            for record in records:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
        report["report_path"] = str(report_path)
        report["quality_path"] = str(quality_path)
        report["records_jsonl_path"] = str(jsonl_path)
        report["summary_path"] = str(summary_path)

    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net table extraction bbox PNG overlays v1")
    parser.add_argument("--table-line-geometry", type=Path, default=DEFAULT_TABLE_LINE_GEOMETRY)
    parser.add_argument("--image-root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-cards", type=int, default=0)
    parser.add_argument("--min-overlay-records", type=int, default=1)
    parser.add_argument("--min-overlay-pngs", type=int, default=1)
    parser.add_argument("--max-missing-extraction-bbox-count", type=int, default=0)
    parser.add_argument("--max-unsafe-record-count", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-line-geometry-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    thresholds = OverlayThresholds(
        min_overlay_records=args.min_overlay_records,
        min_overlay_pngs=args.min_overlay_pngs,
        max_missing_extraction_bbox_count=args.max_missing_extraction_bbox_count,
        max_unsafe_record_count=args.max_unsafe_record_count,
        max_answer_permission_count=args.max_answer_permission_count,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_table_line_geometry_quality_pass=args.require_table_line_geometry_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )
    report = build_table_extraction_bbox_overlay_export_report(
        table_line_geometry_path=args.table_line_geometry,
        image_root=args.image_root,
        output_dir=args.output_dir,
        thresholds=thresholds,
        max_cards=args.max_cards,
    )
    summary = report["summary"]

    print("TRACE-Net Table Extraction BBox Overlay Export v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "overlay_record_count",
        "overlay_png_count",
        "contact_sheet_created",
        "source_image_found_count",
        "blank_canvas_overlay_count",
        "missing_extraction_bbox_count",
        "paddle_style_extraction_bbox_count",
        "review_required_count",
        "unsafe_record_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {report.get('report_path')}")
    print(f" quality_path: {report.get('quality_path')}")
    print(f" contact_sheet_path: {summary.get('contact_sheet_path')}")
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
