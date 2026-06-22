"""TRACE-Net Table Visual BBox Overlay Export v1.

Read-only PNG overlay exporter for the visual table bbox localizer.

This module consumes ``trace_net_table_visual_bbox_localizer_v1`` JSON output and
renders inspectable PNG overlays plus a contact sheet. It is intentionally a QA
and inspection artifact: it does not change source truth and does not grant any
answer authority.

Authority and safety contract:
- read local JSON/image artifacts only;
- write local PNG/JSON/JSONL reports only;
- no Postgres writes;
- no Qdrant writes;
- no OpenSearch writes;
- no source-truth mutation;
- no answer permission or claim-proof authority.
"""
from __future__ import annotations

import argparse
import json
import math
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover - only exercised when Pillow is unavailable.
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]
    ImageFont = None  # type: ignore[assignment]

SCHEMA_VERSION = "trace_net_table_visual_bbox_overlay_export_v1"
QUALITY_SCHEMA_VERSION = "trace_net_table_visual_bbox_overlay_export_v1_quality"
STATUS_BUILT = "TABLE_VISUAL_BBOX_OVERLAY_EXPORT_BUILT"
STATUS_NOT_READY = "TABLE_VISUAL_BBOX_OVERLAY_EXPORT_NOT_READY"

IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".webp", ".bmp"}
PAGE_ID_KEYS = ("page_id", "source_page_id")
TABLE_ID_KEYS = ("table_id", "normalized_table_id", "source_table_id")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "||".join("" if part is None else str(part) for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:14]
    return f"{prefix}__{digest}"


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        f = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            f = float(text)
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(f):
        return None
    return f


def first_present(mapping: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\\", "/").split())


def safe_filename(value: Any, fallback: str = "record") -> str:
    text = str(value or fallback)
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in text)
    cleaned = cleaned.strip("._-")
    return cleaned or fallback


def page_suffix(page_id: str | None) -> str | None:
    text = str(page_id or "")
    idx = text.rfind("p")
    if idx >= 0:
        tail = text[idx + 1 :]
        if tail.isdigit():
            return f"p{int(tail):06d}"
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits:
        return f"p{int(digits[-6:]):06d}"
    return None


def source_records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    for key in ("table_visual_bbox_localizer_records", "visual_localization_records", "records"):
        value = payload.get(key)
        if isinstance(value, list):
            return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


def normalize_path(value: Any, image_root: Path | None = None) -> Path | None:
    text = normalize_text(value)
    if not text:
        return None
    path = Path(text)
    candidates = [path]
    if image_root and not path.is_absolute():
        candidates.append(image_root / path)
    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_file():
                return candidate
        except OSError:
            continue
    return candidates[-1] if candidates else None


def build_image_index(image_root: Path | None, max_files_scanned: int = 25000) -> dict[str, Path]:
    if not image_root or not image_root.exists():
        return {}
    index: dict[str, Path] = {}
    scanned = 0
    for path in image_root.rglob("*"):
        if scanned >= max_files_scanned:
            break
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        scanned += 1
        stem = path.stem.lower()
        index.setdefault(stem, path)
        suffix = page_suffix(stem)
        if suffix:
            index.setdefault(suffix.lower(), path)
    return index


def resolve_image_path(record: Mapping[str, Any], image_root: Path | None, image_index: Mapping[str, Path]) -> tuple[Path | None, str]:
    candidate = normalize_path(record.get("image_path"), image_root)
    if candidate and candidate.exists() and candidate.is_file():
        return candidate, "record_image_path"
    page_id = first_present(record, PAGE_ID_KEYS)
    keys = [normalize_text(page_id).lower()]
    suffix = page_suffix(str(page_id or ""))
    if suffix:
        keys.append(suffix.lower())
    for key in keys:
        if key and key in image_index:
            return image_index[key], "image_index_page_id"
    return None, "not_found"


def bbox_from_mapping(value: Any) -> dict[str, float] | None:
    if not isinstance(value, Mapping):
        return None
    x0, y0, x1, y1 = (as_float(value.get(k)) for k in ("x0", "y0", "x1", "y1"))
    if x0 is None or y0 is None or x1 is None or y1 is None:
        return None
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    if x1 - x0 < 1 or y1 - y0 < 1:
        return None
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "width": x1 - x0, "height": y1 - y0}


def scaled_bbox(box: Mapping[str, float], scale: float) -> tuple[int, int, int, int]:
    return (
        int(round(float(box["x0"]) * scale)),
        int(round(float(box["y0"]) * scale)),
        int(round(float(box["x1"]) * scale)),
        int(round(float(box["y1"]) * scale)),
    )


def draw_rect(draw: Any, xy: tuple[int, int, int, int], color: tuple[int, int, int], width: int = 5) -> None:
    for offset in range(max(1, width)):
        draw.rectangle((xy[0] - offset, xy[1] - offset, xy[2] + offset, xy[3] + offset), outline=color)


def font(size: int = 18) -> Any:
    if ImageFont is None:
        return None
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()


def draw_label(draw: Any, text: str, xy: tuple[int, int], fill: tuple[int, int, int], bg: tuple[int, int, int] = (255, 255, 255)) -> None:
    fnt = font(18)
    x, y = xy
    try:
        box = draw.textbbox((x, y), text, font=fnt)
        draw.rectangle((box[0] - 3, box[1] - 3, box[2] + 3, box[3] + 3), fill=bg)
    except Exception:
        draw.rectangle((x - 3, y - 3, x + 10 * len(text), y + 24), fill=bg)
    draw.text((x, y), text, fill=fill, font=fnt)


def render_overlay(record: Mapping[str, Any], image_path: Path, output_path: Path, max_dimension: int = 1800) -> dict[str, Any]:
    if Image is None or ImageDraw is None:
        return {"overlay_written": False, "overlay_error": "pillow_unavailable"}
    input_box = bbox_from_mapping(record.get("input_bbox"))
    localized_box = bbox_from_mapping(record.get("localized_table_bbox"))
    if not localized_box:
        return {"overlay_written": False, "overlay_error": "missing_localized_table_bbox"}

    try:
        with Image.open(image_path) as source_image:
            image = source_image.convert("RGB")
    except Exception as exc:
        return {"overlay_written": False, "overlay_error": f"image_error:{type(exc).__name__}"}

    original_w, original_h = image.size
    scale = min(1.0, float(max_dimension) / max(original_w, original_h)) if max_dimension > 0 else 1.0
    if scale < 1.0:
        image = image.resize((int(round(original_w * scale)), int(round(original_h * scale))))
    draw = ImageDraw.Draw(image)

    # Amber = upstream/input bbox. Green = localized visual bbox. Red label means fallback/not quality pass.
    if input_box:
        draw_rect(draw, scaled_bbox(input_box, scale), (255, 191, 0), width=5)
        draw_label(draw, "input bbox", (10, 10), (120, 82, 0))
    local_color = (0, 190, 70) if record.get("table_localization_quality_pass") else (220, 30, 30)
    draw_rect(draw, scaled_bbox(localized_box, scale), local_color, width=6)
    draw_label(draw, "localized bbox", (10, 38), local_color)

    caption = " | ".join(
        item
        for item in [
            str(record.get("page_id") or ""),
            str(record.get("localized_bbox_source") or ""),
            f"quality={record.get('table_localization_quality_pass')}",
            f"coverage={record.get('localized_bbox_coverage_ratio')}",
        ]
        if item
    )
    draw_label(draw, caption[:170], (10, max(66, image.height - 28)), (0, 0, 0))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return {
        "overlay_written": True,
        "overlay_path": str(output_path),
        "overlay_width": image.width,
        "overlay_height": image.height,
        "overlay_scale": round(scale, 6),
    }


def make_contact_sheet(overlay_records: Sequence[Mapping[str, Any]], output_path: Path, columns: int = 2, thumb_width: int = 720) -> dict[str, Any]:
    if Image is None or ImageDraw is None:
        return {"contact_sheet_written": False, "contact_sheet_error": "pillow_unavailable"}
    usable = [record for record in overlay_records if record.get("overlay_written") and record.get("overlay_path")]
    if not usable:
        return {"contact_sheet_written": False, "contact_sheet_error": "no_overlay_pngs"}
    columns = max(1, int(columns or 1))
    thumbs: list[tuple[Image.Image, str]] = []
    label_h = 44
    for record in usable:
        path = Path(str(record["overlay_path"]))
        try:
            with Image.open(path) as image:
                img = image.convert("RGB")
        except Exception:
            continue
        scale = float(thumb_width) / max(1, img.width)
        thumb_h = max(1, int(round(img.height * scale)))
        img = img.resize((thumb_width, thumb_h))
        label = f"{record.get('page_id')} | pass={record.get('table_localization_quality_pass')} | {record.get('localized_bbox_source')}"
        thumbs.append((img, label[:110]))
    if not thumbs:
        return {"contact_sheet_written": False, "contact_sheet_error": "no_readable_overlay_pngs"}

    rows = int(math.ceil(len(thumbs) / columns))
    cell_w = thumb_width
    cell_h = max(img.height for img, _ in thumbs) + label_h
    sheet = Image.new("RGB", (cell_w * columns, cell_h * rows), "white")
    draw = ImageDraw.Draw(sheet)
    fnt = font(20)
    for idx, (img, label) in enumerate(thumbs):
        row = idx // columns
        col = idx % columns
        x = col * cell_w
        y = row * cell_h
        sheet.paste(img, (x, y + label_h))
        draw.text((x + 8, y + 8), label, fill=(0, 0, 0), font=fnt)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)
    return {
        "contact_sheet_written": True,
        "contact_sheet_path": str(output_path),
        "contact_sheet_overlay_count": len(thumbs),
        "contact_sheet_columns": columns,
        "contact_sheet_width": sheet.width,
        "contact_sheet_height": sheet.height,
    }


def overlay_filename(record: Mapping[str, Any], index: int) -> str:
    page = safe_filename(record.get("page_id"), f"page_{index:03d}")
    table = safe_filename(record.get("table_id"), "table")
    return f"{index:03d}_{page}_{table}_visual_bbox_overlay.png"


def build_overlay_record(record: Mapping[str, Any], *, index: int, image_root: Path | None, image_index: Mapping[str, Path], overlays_dir: Path, max_dimension: int) -> dict[str, Any]:
    page_id = first_present(record, PAGE_ID_KEYS)
    table_id = first_present(record, TABLE_ID_KEYS)
    image_path, image_resolution = resolve_image_path(record, image_root, image_index)
    output_path = overlays_dir / overlay_filename(record, index)
    result: dict[str, Any] = {
        "overlay_export_id": stable_id("tblvisoverlay", page_id, table_id, index),
        "schema_version": SCHEMA_VERSION,
        "page_id": page_id,
        "table_id": table_id,
        "source_visual_bbox_localizer_id": record.get("visual_bbox_localizer_id"),
        "image_path": str(image_path) if image_path else None,
        "image_resolution_confidence": image_resolution,
        "image_available": bool(image_path and image_path.exists()),
        "input_bbox": record.get("input_bbox"),
        "localized_table_bbox": record.get("localized_table_bbox"),
        "localized_bbox_source": record.get("localized_bbox_source"),
        "localized_bbox_coverage_ratio": record.get("localized_bbox_coverage_ratio"),
        "visual_refinement_applied": record.get("visual_refinement_applied"),
        "table_localization_quality_pass": record.get("table_localization_quality_pass"),
        "review_flags": list(record.get("review_flags") or []),
        "overlay_path": str(output_path),
        "routing_only": True,
        "retrieval_only": True,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
        "postgres_write_attempted": False,
        "qdrant_write_attempted": False,
        "opensearch_write_attempted": False,
        "unsafe_table_visual_bbox_overlay_record": False,
    }
    if image_path and image_path.exists():
        result.update(render_overlay(record, image_path, output_path, max_dimension=max_dimension))
    else:
        result.update({"overlay_written": False, "overlay_error": "image_not_found"})
    return result


def summarize(records: Sequence[Mapping[str, Any]], source_quality: str | None, contact_sheet: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_table_visual_bbox_localizer_quality_status": source_quality,
        "source_record_count": len(records),
        "overlay_record_count": len(records),
        "image_available_record_count": sum(1 for r in records if r.get("image_available")),
        "overlay_png_written_count": sum(1 for r in records if r.get("overlay_written")),
        "quality_pass_overlay_count": sum(1 for r in records if r.get("table_localization_quality_pass")),
        "fallback_overlay_count": sum(1 for r in records if r.get("localized_bbox_source") == "input_bbox_fallback"),
        "visual_refined_overlay_count": sum(1 for r in records if r.get("visual_refinement_applied")),
        "contact_sheet_written_count": 1 if contact_sheet.get("contact_sheet_written") else 0,
        "contact_sheet_path": contact_sheet.get("contact_sheet_path"),
        "unsafe_table_visual_bbox_overlay_record_count": sum(1 for r in records if r.get("unsafe_table_visual_bbox_overlay_record")),
        "answer_permission_count": sum(1 for r in records if r.get("answer_permission")),
        "can_answer_directly_count": sum(1 for r in records if r.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for r in records if r.get("can_prove_claims")),
        "source_truth_mutation_allowed_count": sum(1 for r in records if r.get("source_truth_mutation_allowed")),
        "postgres_write_attempt_count": sum(1 for r in records if r.get("postgres_write_attempted")),
        "qdrant_write_attempt_count": sum(1 for r in records if r.get("qdrant_write_attempted")),
        "opensearch_write_attempt_count": sum(1 for r in records if r.get("opensearch_write_attempted")),
    }


def quality_errors(summary: Mapping[str, Any], args: argparse.Namespace) -> list[str]:
    errors: list[str] = []

    def get_count(key: str) -> int:
        value = summary.get(key, 0)
        return int(value) if isinstance(value, (int, float)) else 0

    if args.require_table_visual_bbox_localizer_quality_pass and summary.get("source_table_visual_bbox_localizer_quality_status") != "PASS":
        errors.append("source_table_visual_bbox_localizer_quality_status_not_pass")
    if get_count("source_record_count") < args.min_source_records:
        errors.append("source_record_count_below_min")
    if get_count("overlay_record_count") < args.min_overlay_records:
        errors.append("overlay_record_count_below_min")
    if get_count("image_available_record_count") < args.min_image_available_records:
        errors.append("image_available_record_count_below_min")
    if get_count("overlay_png_written_count") < args.min_overlay_pngs:
        errors.append("overlay_png_written_count_below_min")
    if get_count("contact_sheet_written_count") < args.min_contact_sheets:
        errors.append("contact_sheet_written_count_below_min")
    if get_count("unsafe_table_visual_bbox_overlay_record_count") > args.max_unsafe_records:
        errors.append("unsafe_table_visual_bbox_overlay_record_count_above_max")
    if get_count("answer_permission_count") > args.max_answer_permission_count:
        errors.append("answer_permission_count_above_max")
    if get_count("source_truth_mutation_allowed_count") > args.max_source_truth_mutation_allowed:
        errors.append("source_truth_mutation_allowed_count_above_max")
    if args.require_no_answer_permission and get_count("answer_permission_count") != 0:
        errors.append("answer_permission_count_not_zero")
    for key in ("postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"):
        if get_count(key) != 0:
            errors.append(f"{key}_not_zero")
    return errors


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    source_path = Path(args.table_visual_bbox_localizer)
    output_dir = Path(args.output_dir)
    overlays_dir = output_dir / "overlays"
    image_root = Path(args.image_root) if args.image_root else None
    source = load_json(source_path)
    records = source_records(source)
    image_index = build_image_index(image_root, args.max_image_files_scanned)
    overlay_records = [
        build_overlay_record(
            record,
            index=index + 1,
            image_root=image_root,
            image_index=image_index,
            overlays_dir=overlays_dir,
            max_dimension=args.max_overlay_dimension,
        )
        for index, record in enumerate(records)
    ]
    contact_sheet_path = output_dir / "trace_net_table_visual_bbox_localizer_overlay_contact_sheet_v1.png"
    contact_sheet = make_contact_sheet(overlay_records, contact_sheet_path, columns=args.contact_sheet_columns, thumb_width=args.contact_sheet_thumb_width)
    summary = summarize(overlay_records, source.get("quality_status"), contact_sheet)
    errors = quality_errors(summary, args)
    quality_status = "PASS" if not errors else "FAIL"
    now = utc_now()

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT if overlay_records else STATUS_NOT_READY,
        "quality_status": quality_status,
        "generated_at": now,
        "inputs": {
            "table_visual_bbox_localizer": str(source_path),
            "image_root": str(image_root) if image_root else None,
        },
        "summary": summary,
        "quality_errors": errors,
        "contact_sheet": dict(contact_sheet),
        "table_visual_bbox_overlay_export_records": overlay_records,
        "overlay_records": overlay_records,
    }

    report_path = output_dir / "trace_net_table_visual_bbox_overlay_export_v1.json"
    records_path = output_dir / "trace_net_table_visual_bbox_overlay_export_v1_records.jsonl"
    summary_path = output_dir / "trace_net_table_visual_bbox_overlay_export_v1_summary.json"
    quality_path = output_dir / "trace_net_table_visual_bbox_overlay_export_v1_quality.json"
    manifest_path = output_dir / "trace_net_table_visual_bbox_overlay_export_v1_manifest.json"

    write_json(report_path, payload)
    write_jsonl(records_path, overlay_records)
    write_json(summary_path, summary)
    quality_payload = {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "quality_status": quality_status,
        "generated_at": now,
        "report_path": str(report_path),
        "summary": summary,
        "quality_errors": errors,
    }
    write_json(quality_path, quality_payload)
    write_json(manifest_path, {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": now,
        "report_path": str(report_path),
        "records_path": str(records_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "contact_sheet_path": contact_sheet.get("contact_sheet_path"),
        "overlay_dir": str(overlays_dir),
    })
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net table visual bbox overlay export v1")
    parser.add_argument("--table-visual-bbox-localizer", required=True)
    parser.add_argument("--image-root", default=".")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-image-files-scanned", type=int, default=25000)
    parser.add_argument("--max-overlay-dimension", type=int, default=1800)
    parser.add_argument("--contact-sheet-columns", type=int, default=2)
    parser.add_argument("--contact-sheet-thumb-width", type=int, default=720)
    parser.add_argument("--min-source-records", type=int, default=1)
    parser.add_argument("--min-overlay-records", type=int, default=1)
    parser.add_argument("--min-image-available-records", type=int, default=1)
    parser.add_argument("--min-overlay-pngs", type=int, default=1)
    parser.add_argument("--min-contact-sheets", type=int, default=1)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-visual-bbox-localizer-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    payload = build_report(args)
    summary = payload["summary"]
    print("TRACE-Net Table Visual BBox Overlay Export v1")
    print(f" Status: {payload['status']}")
    print(f" Quality status: {payload['quality_status']}")
    for key in (
        "source_record_count",
        "overlay_record_count",
        "image_available_record_count",
        "overlay_png_written_count",
        "quality_pass_overlay_count",
        "fallback_overlay_count",
        "visual_refined_overlay_count",
        "contact_sheet_written_count",
        "contact_sheet_path",
        "unsafe_table_visual_bbox_overlay_record_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {Path(args.output_dir) / 'trace_net_table_visual_bbox_overlay_export_v1.json'}")
    return 0 if payload["quality_status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
