"""TRACE-Net Table Full-Enclosure BBox Overlay Export v1.

Read-only overlay exporter for the conservative full-table enclosure bbox stage.

This module renders page-image PNG overlays so a human can inspect whether the
final full-enclosure boxes encompass the whole table before those boxes are wired
back into row/cell extraction.

Safety contract:
- local artifact writes only
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission / claim-proof authority
"""
from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:  # Pillow is already used elsewhere in TRACE-Net image tooling.
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover - tests skip image rendering if PIL unavailable.
    Image = None  # type: ignore
    ImageDraw = None  # type: ignore
    ImageFont = None  # type: ignore

SCHEMA_VERSION = "trace_net_table_full_enclosure_bbox_overlay_export_v1"
QUALITY_SCHEMA_VERSION = "trace_net_table_full_enclosure_bbox_overlay_export_v1_quality"
STATUS_BUILT = "TABLE_FULL_ENCLOSURE_BBOX_OVERLAY_EXPORT_BUILT"
STATUS_NOT_READY = "TABLE_FULL_ENCLOSURE_BBOX_OVERLAY_EXPORT_NOT_READY"

IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".webp", ".bmp"}

GREEN = (0, 205, 90)      # final full-table enclosure bbox
AMBER = (255, 185, 0)     # upstream/structure-selected bbox
BLUE = (0, 140, 255)      # validated visual candidate when present
RED = (235, 50, 50)       # rejected/unsafe diagnostic bbox when present
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def as_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def sanitize_filename(value: Any, fallback: str = "unknown") -> str:
    text = str(value or fallback).strip() or fallback
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text)[:120]


def page_number_token(page_id: Any) -> Optional[str]:
    text = str(page_id or "")
    match = re.search(r"p(\d{6})\b", text, flags=re.IGNORECASE)
    if match:
        return f"p{match.group(1)}"
    match = re.search(r"(\d{6})", text)
    if match:
        return f"p{match.group(1)}"
    return None


def bbox_from_mapping(value: Any) -> Optional[Dict[str, float]]:
    if not isinstance(value, Mapping):
        return None
    # canonical bbox shape
    x0 = as_float(value.get("x0", value.get("left", value.get("x"))))
    y0 = as_float(value.get("y0", value.get("top", value.get("y"))))
    x1 = as_float(value.get("x1", value.get("right")))
    y1 = as_float(value.get("y1", value.get("bottom")))
    width = as_float(value.get("width", value.get("w")))
    height = as_float(value.get("height", value.get("h")))

    if x0 is not None and y0 is not None and x1 is None and width is not None:
        x1 = x0 + width
    if y0 is not None and x0 is not None and y1 is None and height is not None:
        y1 = y0 + height
    if None in (x0, y0, x1, y1):
        return None

    assert x0 is not None and y0 is not None and x1 is not None and y1 is not None
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    if x1 - x0 < 1 or y1 - y0 < 1:
        return None
    return {
        "x0": float(x0),
        "y0": float(y0),
        "x1": float(x1),
        "y1": float(y1),
        "width": float(x1 - x0),
        "height": float(y1 - y0),
        "coordinate_system": str(value.get("coordinate_system") or "pixels"),
    }


def bbox_from_value(value: Any) -> Optional[Dict[str, float]]:
    if isinstance(value, Mapping):
        return bbox_from_mapping(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) >= 4:
        x0, y0, x1, y1 = (as_float(value[0]), as_float(value[1]), as_float(value[2]), as_float(value[3]))
        if None in (x0, y0, x1, y1):
            return None
        return bbox_from_mapping({"x0": x0, "y0": y0, "x1": x1, "y1": y1})
    return None


def first_bbox(record: Mapping[str, Any], keys: Sequence[str]) -> Tuple[Optional[str], Optional[Dict[str, float]]]:
    for key in keys:
        if key in record:
            box = bbox_from_value(record.get(key))
            if box:
                return key, box
    return None, None


def normalize_path(value: Any, image_root: Optional[Path] = None) -> Optional[Path]:
    if not value:
        return None
    raw = str(value).strip().replace("\\", "/")
    if not raw:
        return None
    path = Path(raw)
    if path.exists():
        return path
    if image_root is not None:
        candidate = image_root / raw
        if candidate.exists():
            return candidate
        # Try basename under image_root for artifacts that store stale relative paths.
        matches = list(image_root.rglob(Path(raw).name)) if Path(raw).name else []
        for match in matches[:10]:
            if match.suffix.lower() in IMAGE_EXTENSIONS:
                return match
    return None


def build_image_index(image_root: Optional[Path], max_files_scanned: int) -> Dict[str, List[Path]]:
    index: Dict[str, List[Path]] = {}
    if image_root is None or not image_root.exists():
        return index
    scanned = 0
    for path in image_root.rglob("*"):
        if scanned >= max_files_scanned:
            break
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        scanned += 1
        lower = path.name.lower()
        for match in re.finditer(r"p\d{6}|\d{6}", lower):
            token = match.group(0)
            if token.isdigit():
                token = f"p{token}"
            index.setdefault(token, []).append(path)
    return index


def resolve_image_path(record: Mapping[str, Any], image_root: Optional[Path], image_index: Mapping[str, List[Path]]) -> Tuple[Optional[Path], str]:
    for key in ("image_path", "source_image_path", "page_image_path", "tiff_path", "source_page_image_path"):
        path = normalize_path(record.get(key), image_root)
        if path and path.exists():
            return path, key
    token = page_number_token(record.get("page_id"))
    if token:
        matches = image_index.get(token.lower()) or image_index.get(token)
        if matches:
            return matches[0], "image_root_page_token_scan"
    return None, "not_found"


def scale_bbox(box: Mapping[str, float], sx: float, sy: float) -> Tuple[float, float, float, float]:
    return (box["x0"] * sx, box["y0"] * sy, box["x1"] * sx, box["y1"] * sy)


def draw_labeled_box(draw: Any, box: Tuple[float, float, float, float], color: Tuple[int, int, int], label: str, width: int = 5) -> None:
    x0, y0, x1, y1 = box
    for offset in range(width):
        draw.rectangle((x0 - offset, y0 - offset, x1 + offset, y1 + offset), outline=color)
    label_text = f" {label} "
    try:
        font = ImageFont.load_default() if ImageFont else None
        # Pillow >=10 path.
        bbox = draw.textbbox((x0, max(0, y0 - 14)), label_text, font=font)
        draw.rectangle(bbox, fill=color)
        draw.text((bbox[0], bbox[1]), label_text, fill=BLACK if color != RED else WHITE, font=font)
    except Exception:  # pragma: no cover - label is optional convenience only.
        pass


def render_overlay(
    *,
    image_path: Path,
    overlay_path: Path,
    record: Mapping[str, Any],
    max_overlay_dimension: int,
) -> Tuple[bool, Optional[str]]:
    if Image is None or ImageDraw is None:
        return False, "Pillow not available"
    try:
        with Image.open(image_path) as img:
            base = img.convert("RGB")
    except Exception as exc:
        return False, f"image_read_error: {exc}"

    original_width, original_height = base.size
    max_dim = max(original_width, original_height)
    scale = 1.0
    if max_dim > max_overlay_dimension > 0:
        scale = max_overlay_dimension / max_dim
        new_size = (max(1, int(original_width * scale)), max(1, int(original_height * scale)))
        base = base.resize(new_size)
    sx = base.size[0] / original_width
    sy = base.size[1] / original_height

    draw = ImageDraw.Draw(base)

    input_key, input_box = first_bbox(record, (
        "input_table_bbox",
        "structure_input_table_bbox",
        "source_input_table_bbox",
        "input_bbox",
        "upstream_input_bbox",
        "structure_selected_table_bbox",
    ))
    visual_key, visual_box = first_bbox(record, (
        "visual_candidate_table_bbox",
        "visual_candidate_bbox",
        "localized_table_bbox",
    ))
    final_key, final_box = first_bbox(record, (
        "final_table_bbox",
        "full_enclosure_table_bbox",
        "reconstructed_table_bbox",
    ))

    if input_box:
        draw_labeled_box(draw, scale_bbox(input_box, sx, sy), AMBER, "input", width=4)
    if visual_box and record.get("structure_visual_candidate_accepted") is True:
        draw_labeled_box(draw, scale_bbox(visual_box, sx, sy), BLUE, "accepted visual", width=4)
    elif visual_box and record.get("structure_visual_candidate_rejected") is True:
        draw_labeled_box(draw, scale_bbox(visual_box, sx, sy), RED, "rejected visual", width=4)
    if final_box:
        draw_labeled_box(draw, scale_bbox(final_box, sx, sy), GREEN, "final enclosure", width=6)

    header_lines = [
        f"{record.get('page_id', '')}",
        f"presence={record.get('table_presence_label', '')} source={record.get('final_table_bbox_source', '')}",
        f"reconstructed={record.get('full_table_enclosure_reconstructed', False)} ready={record.get('full_table_enclosure_bbox_ready', False)}",
    ]
    try:
        font = ImageFont.load_default() if ImageFont else None
        y = 8
        for line in header_lines:
            bbox = draw.textbbox((8, y), line, font=font)
            draw.rectangle((bbox[0] - 2, bbox[1] - 1, bbox[2] + 2, bbox[3] + 1), fill=WHITE)
            draw.text((8, y), line, fill=BLACK, font=font)
            y += 14
    except Exception:  # pragma: no cover
        pass

    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    base.save(overlay_path)
    return True, None


def make_contact_sheet(
    overlay_paths: Sequence[Path],
    contact_sheet_path: Path,
    *,
    columns: int,
    thumb_width: int,
) -> bool:
    if Image is None or not overlay_paths:
        return False
    thumbs: List[Image.Image] = []  # type: ignore[name-defined]
    for path in overlay_paths:
        try:
            with Image.open(path) as img:
                rgb = img.convert("RGB")
                scale = thumb_width / max(1, rgb.size[0])
                thumb_size = (thumb_width, max(1, int(rgb.size[1] * scale)))
                thumbs.append(rgb.resize(thumb_size))
        except Exception:
            continue
    if not thumbs:
        return False
    columns = max(1, int(columns))
    rows = math.ceil(len(thumbs) / columns)
    gutter = 16
    cell_w = thumb_width
    cell_h = max(t.size[1] for t in thumbs)
    sheet = Image.new("RGB", (columns * cell_w + (columns + 1) * gutter, rows * cell_h + (rows + 1) * gutter), WHITE)
    for idx, thumb in enumerate(thumbs):
        row = idx // columns
        col = idx % columns
        x = gutter + col * (cell_w + gutter)
        y = gutter + row * (cell_h + gutter)
        sheet.paste(thumb, (x, y))
    contact_sheet_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(contact_sheet_path)
    return True


def extract_records(payload: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    for key in (
        "table_full_enclosure_bbox_reconstructor_records",
        "full_enclosure_reconstructor_records",
        "records",
    ):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, Mapping)]
    return []




def is_full_enclosure_reconstructed(record: Mapping[str, Any]) -> bool:
    """Return True for both v1 and v2 reconstructor source names.

    v1 emitted the boolean ``full_table_enclosure_reconstructed`` and often
    used ``final_table_bbox_source == "full_table_enclosure_reconstructed"``.
    The boundary v2 fix emits the safer final source
    ``full_table_boundary_reconstructed`` for records whose bbox was rebuilt
    from full-table boundary evidence. Overlay QA should count both shapes as
    reconstructed full-enclosure outputs.
    """
    if bool(record.get("full_table_enclosure_reconstructed")):
        return True
    source = str(record.get("final_table_bbox_source") or "")
    return source in {
        "full_table_enclosure_reconstructed",
        "full_table_boundary_reconstructed",
        "full_page_table_bbox",
    }


def is_structure_passthrough(record: Mapping[str, Any]) -> bool:
    source = str(record.get("final_table_bbox_source") or "")
    return source in {
        "structure_selected_bbox_passthrough",
        "structure_selected_passthrough",
    }


def build_overlay_export(
    *,
    table_full_enclosure_bbox_reconstructor: Path,
    image_root: Optional[Path],
    output_dir: Path,
    max_image_files_scanned: int = 25000,
    max_overlay_dimension: int = 1800,
    contact_sheet_columns: int = 2,
    contact_sheet_thumb_width: int = 720,
) -> Dict[str, Any]:
    source_payload = load_json(table_full_enclosure_bbox_reconstructor)
    source_quality_status = source_payload.get("quality_status")
    records = extract_records(source_payload if isinstance(source_payload, Mapping) else {})

    output_dir.mkdir(parents=True, exist_ok=True)
    overlay_dir = output_dir / "overlays"
    image_index = build_image_index(image_root, max_image_files_scanned)

    overlay_records: List[Dict[str, Any]] = []
    overlay_paths: List[Path] = []

    for idx, record in enumerate(records, start=1):
        page_id = record.get("page_id")
        table_id = record.get("table_id")
        image_path, image_resolution_method = resolve_image_path(record, image_root, image_index)
        final_key, final_box = first_bbox(record, ("final_table_bbox", "full_enclosure_table_bbox", "reconstructed_table_bbox"))
        input_key, input_box = first_bbox(record, ("input_table_bbox", "structure_input_table_bbox", "source_input_table_bbox", "input_bbox", "upstream_input_bbox", "structure_selected_table_bbox"))
        visual_key, visual_box = first_bbox(record, ("visual_candidate_table_bbox", "visual_candidate_bbox", "localized_table_bbox"))

        name = f"{idx:03d}_{sanitize_filename(page_id)}_{sanitize_filename(table_id)}.png"
        overlay_path = overlay_dir / name
        overlay_written = False
        overlay_error = None
        if image_path and final_box:
            overlay_written, overlay_error = render_overlay(
                image_path=image_path,
                overlay_path=overlay_path,
                record=record,
                max_overlay_dimension=max_overlay_dimension,
            )
            if overlay_written:
                overlay_paths.append(overlay_path)

        overlay_record = {
            "schema_version": SCHEMA_VERSION,
            "overlay_record_id": f"table_full_enclosure_overlay__{idx:06d}",
            "source_record_index": idx - 1,
            "page_id": page_id,
            "table_id": table_id,
            "image_available": bool(image_path),
            "image_resolution_method": image_resolution_method,
            "image_path": str(image_path) if image_path else None,
            "overlay_written": overlay_written,
            "overlay_error": overlay_error,
            "overlay_path": str(overlay_path) if overlay_written else None,
            "input_bbox_key": input_key,
            "visual_candidate_bbox_key": visual_key,
            "final_table_bbox_key": final_key,
            "input_table_bbox": input_box,
            "visual_candidate_table_bbox": visual_box,
            "final_table_bbox": final_box,
            "final_table_bbox_source": record.get("final_table_bbox_source"),
            "full_table_enclosure_bbox_ready": bool(record.get("full_table_enclosure_bbox_ready")),
            "full_table_enclosure_recommended": bool(record.get("full_table_enclosure_recommended")),
            "full_table_enclosure_reconstructed": is_full_enclosure_reconstructed(record),
            "structure_selected_passthrough_overlay": is_structure_passthrough(record),
            "table_presence_label": record.get("table_presence_label"),
            "table_route_challenged": bool(record.get("table_route_challenged")),
            "review_flags": list(record.get("review_flags") or []),
            "unsafe_table_full_enclosure_overlay_record": False,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempted": False,
            "qdrant_write_attempted": False,
            "opensearch_write_attempted": False,
        }
        overlay_records.append(overlay_record)

    contact_sheet_path = output_dir / "trace_net_table_full_enclosure_bbox_overlay_contact_sheet_v1.png"
    contact_sheet_written = make_contact_sheet(
        overlay_paths,
        contact_sheet_path,
        columns=contact_sheet_columns,
        thumb_width=contact_sheet_thumb_width,
    )

    summary: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "source_table_full_enclosure_bbox_reconstructor_path": str(table_full_enclosure_bbox_reconstructor),
        "source_table_full_enclosure_bbox_reconstructor_quality_status": source_quality_status,
        "source_record_count": len(records),
        "overlay_record_count": len(overlay_records),
        "image_available_record_count": sum(1 for row in overlay_records if row["image_available"]),
        "overlay_png_written_count": sum(1 for row in overlay_records if row["overlay_written"]),
        "contact_sheet_written_count": 1 if contact_sheet_written else 0,
        "contact_sheet_path": str(contact_sheet_path) if contact_sheet_written else None,
        "final_bbox_ready_overlay_count": sum(1 for row in overlay_records if row["full_table_enclosure_bbox_ready"]),
        "full_enclosure_reconstructed_overlay_count": sum(1 for row in overlay_records if row["full_table_enclosure_reconstructed"]),
        "full_enclosure_recommended_overlay_count": sum(1 for row in overlay_records if row["full_table_enclosure_recommended"]),
        "structure_passthrough_overlay_count": sum(1 for row in overlay_records if row["structure_selected_passthrough_overlay"]),
        "full_table_boundary_reconstructed_overlay_count": sum(1 for row in overlay_records if row["final_table_bbox_source"] == "full_table_boundary_reconstructed"),
        "full_page_bbox_overlay_count": sum(1 for row in overlay_records if row["final_table_bbox_source"] == "full_page_table_bbox"),
        "weak_table_overlay_count": sum(1 for row in overlay_records if row["table_presence_label"] == "weak_table"),
        "confirmed_table_overlay_count": sum(1 for row in overlay_records if row["table_presence_label"] == "confirmed_table"),
        "unsafe_table_full_enclosure_overlay_record_count": sum(1 for row in overlay_records if row["unsafe_table_full_enclosure_overlay_record"]),
        "answer_permission_count": sum(1 for row in overlay_records if row["answer_permission"]),
        "can_answer_directly_count": sum(1 for row in overlay_records if row["can_answer_directly"]),
        "can_prove_claims_count": sum(1 for row in overlay_records if row["can_prove_claims"]),
        "source_truth_mutation_allowed_count": sum(1 for row in overlay_records if row["source_truth_mutation_allowed"]),
        "postgres_write_attempt_count": sum(1 for row in overlay_records if row["postgres_write_attempted"]),
        "qdrant_write_attempt_count": sum(1 for row in overlay_records if row["qdrant_write_attempted"]),
        "opensearch_write_attempt_count": sum(1 for row in overlay_records if row["opensearch_write_attempted"]),
    }

    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "created_at_utc": utc_now(),
        "quality_status": "UNKNOWN",
        "summary": summary,
        "table_full_enclosure_bbox_overlay_export_records": overlay_records,
    }
    return payload


def evaluate_quality(payload: Mapping[str, Any], *, args: Optional[argparse.Namespace] = None) -> Dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    assert isinstance(summary, Mapping)

    def get_int(name: str) -> int:
        value = summary.get(name, 0)
        return int(value or 0)

    def arg(name: str, default: Any) -> Any:
        return getattr(args, name, default) if args is not None else default

    checks = {
        "schema_version_ok": payload.get("schema_version") == SCHEMA_VERSION,
        "source_quality_pass": summary.get("source_table_full_enclosure_bbox_reconstructor_quality_status") == "PASS" or not arg("require_table_full_enclosure_bbox_reconstructor_quality_pass", False),
        "min_source_records_met": get_int("source_record_count") >= int(arg("min_source_records", 0)),
        "min_overlay_records_met": get_int("overlay_record_count") >= int(arg("min_overlay_records", 0)),
        "min_image_available_records_met": get_int("image_available_record_count") >= int(arg("min_image_available_records", 0)),
        "min_overlay_pngs_met": get_int("overlay_png_written_count") >= int(arg("min_overlay_pngs", 0)),
        "min_contact_sheets_met": get_int("contact_sheet_written_count") >= int(arg("min_contact_sheets", 0)),
        "min_final_bbox_ready_overlays_met": get_int("final_bbox_ready_overlay_count") >= int(arg("min_final_bbox_ready_overlays", 0)),
        "min_full_enclosure_reconstructed_overlays_met": get_int("full_enclosure_reconstructed_overlay_count") >= int(arg("min_full_enclosure_reconstructed_overlays", 0)),
        "unsafe_records_within_limit": get_int("unsafe_table_full_enclosure_overlay_record_count") <= int(arg("max_unsafe_records", 0)),
        "answer_permission_within_limit": get_int("answer_permission_count") <= int(arg("max_answer_permission_count", 0)),
        "source_truth_mutation_allowed_within_limit": get_int("source_truth_mutation_allowed_count") <= int(arg("max_source_truth_mutation_allowed", 0)),
        "no_answer_permission": get_int("answer_permission_count") == 0 or not arg("require_no_answer_permission", False),
    }
    quality_fail_reasons = [name for name, passed in checks.items() if not passed]
    quality_status = "PASS" if not quality_fail_reasons else "FAIL"
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "source_schema_version": payload.get("schema_version"),
        "status": "TABLE_FULL_ENCLOSURE_BBOX_OVERLAY_EXPORT_QUALITY_BUILT",
        "quality_status": quality_status,
        "quality_fail_reasons": quality_fail_reasons,
        "checks": checks,
        **{key: summary.get(key) for key in summary.keys() if key.endswith("_count") or key in {"contact_sheet_path", "source_table_full_enclosure_bbox_reconstructor_quality_status"}},
    }


def write_outputs(payload: Dict[str, Any], output_dir: Path, quality: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if quality is not None:
        payload["quality_status"] = quality["quality_status"]
        payload["summary"]["quality_status"] = quality["quality_status"]
        payload["summary"]["quality_fail_reasons"] = quality["quality_fail_reasons"]

    report_path = output_dir / f"{SCHEMA_VERSION}.json"
    records_path = output_dir / f"{SCHEMA_VERSION}_records.jsonl"
    summary_path = output_dir / f"{SCHEMA_VERSION}_summary.json"
    quality_path = output_dir / f"{SCHEMA_VERSION}_quality.json"
    manifest_path = output_dir / f"{SCHEMA_VERSION}_manifest.json"

    write_json(report_path, payload)
    write_jsonl(records_path, payload.get("table_full_enclosure_bbox_overlay_export_records", []))
    write_json(summary_path, payload["summary"])
    if quality is not None:
        write_json(quality_path, quality)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "quality_status": payload.get("quality_status"),
        "report_path": str(report_path),
        "records_jsonl_path": str(records_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path) if quality is not None else None,
        "contact_sheet_path": payload["summary"].get("contact_sheet_path"),
    }
    write_json(manifest_path, manifest)
    return manifest


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net table full-enclosure bbox overlays.")
    parser.add_argument("--table-full-enclosure-bbox-reconstructor", required=True, type=Path)
    parser.add_argument("--image-root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-image-files-scanned", type=int, default=25000)
    parser.add_argument("--max-overlay-dimension", type=int, default=1800)
    parser.add_argument("--contact-sheet-columns", type=int, default=2)
    parser.add_argument("--contact-sheet-thumb-width", type=int, default=720)

    parser.add_argument("--min-source-records", type=int, default=0)
    parser.add_argument("--min-overlay-records", type=int, default=0)
    parser.add_argument("--min-image-available-records", type=int, default=0)
    parser.add_argument("--min-overlay-pngs", type=int, default=0)
    parser.add_argument("--min-contact-sheets", type=int, default=0)
    parser.add_argument("--min-final-bbox-ready-overlays", type=int, default=0)
    parser.add_argument("--min-full-enclosure-reconstructed-overlays", type=int, default=0)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-full-enclosure-bbox-reconstructor-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def print_summary(payload: Mapping[str, Any]) -> None:
    summary = payload.get("summary", {})
    print("TRACE-Net Table Full-Enclosure BBox Overlay Export v1")
    print(f" Status: {payload.get('status')}")
    print(f" Quality status: {payload.get('quality_status')}")
    for key in (
        "source_record_count",
        "overlay_record_count",
        "image_available_record_count",
        "overlay_png_written_count",
        "contact_sheet_written_count",
        "final_bbox_ready_overlay_count",
        "full_enclosure_reconstructed_overlay_count",
        "full_enclosure_recommended_overlay_count",
        "structure_passthrough_overlay_count",
        "weak_table_overlay_count",
        "confirmed_table_overlay_count",
        "unsafe_table_full_enclosure_overlay_record_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "contact_sheet_path",
    ):
        if isinstance(summary, Mapping) and key in summary:
            print(f" {key}: {summary[key]}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    payload = build_overlay_export(
        table_full_enclosure_bbox_reconstructor=args.table_full_enclosure_bbox_reconstructor,
        image_root=args.image_root,
        output_dir=args.output_dir,
        max_image_files_scanned=args.max_image_files_scanned,
        max_overlay_dimension=args.max_overlay_dimension,
        contact_sheet_columns=args.contact_sheet_columns,
        contact_sheet_thumb_width=args.contact_sheet_thumb_width,
    )
    quality = evaluate_quality(payload, args=args) if args.quality else None
    write_outputs(payload, args.output_dir, quality)
    if quality is not None:
        payload["quality_status"] = quality["quality_status"]
    print_summary(payload)
    return 0 if payload.get("quality_status") in {"PASS", "UNKNOWN"} else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
