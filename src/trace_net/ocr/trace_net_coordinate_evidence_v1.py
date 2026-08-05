"""TRACE-Net Coordinate Evidence Foundation v1 (Patch 6A).

This module adds coordinate-aware OCR evidence without changing the frozen
Patch-5.1 routing decision. It deliberately reuses the existing Tesseract TSV
parser and line grouper from ``trace_net_table_ocr_bbox_sidecar_generator_v1``
when available.

Outputs are derived guidance only:
- normalized word/line bounding boxes;
- coordinate-backed table row/cell candidates;
- coordinate-backed visual callout candidates;
- coordinate-backed normal-text blocks.

No output grants answer permission, proves source claims, mutates source truth,
or writes PostgreSQL, Qdrant, or OpenSearch.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "trace_net_coordinate_evidence_v1"
PART_NUMBER_RE = re.compile(r"\b\d{2,4}-\d{2,6}(?:-[A-Z0-9]{1,5})?\b", re.I)
NUMERIC_CALLOUT_RE = re.compile(r"^\d{1,4}[A-Z]?$")
LETTER_CALLOUT_RE = re.compile(r"^[A-Z](?:-[A-Z])?$")
SHORT_TECH_LABEL_RE = re.compile(r"^(?=.*[A-Z0-9])[A-Z0-9./_-]{2,12}$")
VISUAL_ROUTES = {"image_visual", "image_visual_diagram", "mixed_text_and_figure"}
TABLE_ROUTES = {"table", "table_or_index", "detailed_parts_list"}
TEXT_ROUTES = {"normal_text", "procedure_or_description", "cover_or_title_page"}
BLANK_ROUTES = {"blank_candidate"}

SAFETY_CONTRACT = {
    "artifact_authority": "derived_coordinate_guidance_not_source_truth",
    "answer_permission": False,
    "can_answer_directly": False,
    "can_prove_claims": False,
    "final_answer_allowed": False,
    "source_truth_mutation_allowed": False,
    "source_truth_mutations_performed": 0,
    "postgres_write_attempt_count": 0,
    "qdrant_write_attempt_count": 0,
    "opensearch_write_attempt_count": 0,
    "route_mutation_allowed": False,
}


def stable_id(prefix: str, *parts: Any, length: int = 16) -> str:
    payload = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}__{digest}"


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def _as_int(value: Any, default: int = 0) -> int:
    number = _as_float(value)
    return int(number) if number is not None else default


def _fallback_parse_tesseract_tsv(tsv_text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader((tsv_text or "").splitlines(), delimiter="\t")
    records: list[dict[str, Any]] = []
    for row in reader:
        text = (row.get("text") or "").strip()
        if not text:
            continue
        left = _as_int(row.get("left"))
        top = _as_int(row.get("top"))
        width = _as_int(row.get("width"))
        height = _as_int(row.get("height"))
        if width <= 0 or height <= 0:
            continue
        records.append({
            "level": _as_int(row.get("level")),
            "page_num": _as_int(row.get("page_num")),
            "block_num": _as_int(row.get("block_num")),
            "par_num": _as_int(row.get("par_num")),
            "line_num": _as_int(row.get("line_num")),
            "word_num": _as_int(row.get("word_num")),
            "text": text,
            "conf": _as_float(row.get("conf")),
            "bbox": {
                "x0": left,
                "y0": top,
                "x1": left + width,
                "y1": top + height,
                "width": width,
                "height": height,
            },
        })
    return records


def parse_tesseract_tsv_words(tsv_text: str) -> tuple[list[dict[str, Any]], str]:
    """Parse TSV through the existing TRACE-Net parser when available."""
    try:
        from src.trace_net.tables.trace_net_table_ocr_bbox_sidecar_generator_v1 import (
            parse_tesseract_tsv,
        )
    except (ModuleNotFoundError, ImportError):
        return _fallback_parse_tesseract_tsv(tsv_text), "patch6a_fallback_parser"
    return parse_tesseract_tsv(tsv_text), "trace_net_table_ocr_bbox_sidecar_generator_v1"


def _fallback_group_words_into_lines(
    words: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    buckets: dict[tuple[int, int, int, int], list[Mapping[str, Any]]] = defaultdict(list)
    for word in words:
        buckets[(
            _as_int(word.get("page_num")),
            _as_int(word.get("block_num")),
            _as_int(word.get("par_num")),
            _as_int(word.get("line_num")),
        )].append(word)

    lines: list[dict[str, Any]] = []
    for key, members in buckets.items():
        ordered = sorted(
            members,
            key=lambda row: (
                _as_int((row.get("bbox") or {}).get("x0")),
                _as_int(row.get("word_num")),
            ),
        )
        bbox = union_pixel_bboxes([row.get("bbox") or {} for row in ordered])
        if not bbox:
            continue
        confs = [
            float(row["conf"])
            for row in ordered
            if _as_float(row.get("conf")) is not None and float(row["conf"]) >= 0
        ]
        lines.append({
            "line_key": {
                "page_num": key[0],
                "block_num": key[1],
                "par_num": key[2],
                "line_num": key[3],
            },
            "text": " ".join(str(row.get("text") or "") for row in ordered).strip(),
            "word_count": len(ordered),
            "mean_conf": round(sum(confs) / len(confs), 3) if confs else None,
            "bbox": bbox,
            "words": [dict(row) for row in ordered],
        })
    lines.sort(
        key=lambda row: (
            _as_int((row.get("bbox") or {}).get("y0")),
            _as_int((row.get("bbox") or {}).get("x0")),
        )
    )
    return lines


def group_coordinate_words_into_lines(
    words: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    """Group words using the existing TRACE-Net line grouper when available."""
    try:
        from src.trace_net.tables.trace_net_table_ocr_bbox_sidecar_generator_v1 import (
            group_word_records_into_lines,
        )
    except (ModuleNotFoundError, ImportError):
        return _fallback_group_words_into_lines(words), "patch6a_fallback_line_grouper"
    return group_word_records_into_lines(words), "trace_net_table_ocr_bbox_sidecar_generator_v1"


def normalize_pixel_bbox(
    bbox: Mapping[str, Any],
    *,
    image_width: int,
    image_height: int,
) -> dict[str, Any] | None:
    """Return pixel and 0..1 normalized coordinates, rejecting out-of-bounds boxes."""
    if image_width <= 0 or image_height <= 0:
        return None
    x0 = _as_float(bbox.get("x0"))
    y0 = _as_float(bbox.get("y0"))
    x1 = _as_float(bbox.get("x1"))
    y1 = _as_float(bbox.get("y1"))
    if None in (x0, y0, x1, y1):
        return None
    assert x0 is not None and y0 is not None and x1 is not None and y1 is not None
    if x1 <= x0 or y1 <= y0:
        return None
    if x0 < 0 or y0 < 0 or x1 > image_width or y1 > image_height:
        return None
    nx0 = x0 / image_width
    ny0 = y0 / image_height
    nx1 = x1 / image_width
    ny1 = y1 / image_height
    return {
        "coordinate_system": "pixels_and_normalized_0_1",
        "pixels": {
            "x0": round(x0, 3),
            "y0": round(y0, 3),
            "x1": round(x1, 3),
            "y1": round(y1, 3),
            "width": round(x1 - x0, 3),
            "height": round(y1 - y0, 3),
        },
        "normalized": {
            "x0": round(nx0, 6),
            "y0": round(ny0, 6),
            "x1": round(nx1, 6),
            "y1": round(ny1, 6),
            "width": round(nx1 - nx0, 6),
            "height": round(ny1 - ny0, 6),
        },
        "within_page_bounds": True,
    }


def union_pixel_bboxes(boxes: Sequence[Mapping[str, Any]]) -> dict[str, int] | None:
    valid: list[tuple[int, int, int, int]] = []
    for box in boxes:
        x0 = _as_int(box.get("x0"), -1)
        y0 = _as_int(box.get("y0"), -1)
        x1 = _as_int(box.get("x1"), -1)
        y1 = _as_int(box.get("y1"), -1)
        if x0 >= 0 and y0 >= 0 and x1 > x0 and y1 > y0:
            valid.append((x0, y0, x1, y1))
    if not valid:
        return None
    x0 = min(v[0] for v in valid)
    y0 = min(v[1] for v in valid)
    x1 = max(v[2] for v in valid)
    y1 = max(v[3] for v in valid)
    return {
        "x0": x0, "y0": y0, "x1": x1, "y1": y1,
        "width": x1 - x0, "height": y1 - y0,
    }


def build_coordinate_words(
    tsv_text: str,
    *,
    image_width: int,
    image_height: int,
    page_id: str,
    page_number: int,
    source_member: str,
    source_image_sha256: str,
    psm: int,
    raw_tsv_path: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    parsed, parser_source = parse_tesseract_tsv_words(tsv_text)
    words: list[dict[str, Any]] = []
    invalid = 0
    for index, item in enumerate(parsed):
        coords = normalize_pixel_bbox(
            item.get("bbox") or {},
            image_width=image_width,
            image_height=image_height,
        )
        if not coords:
            invalid += 1
            continue
        conf = _as_float(item.get("conf"))
        words.append({
            "coordinate_word_id": stable_id(
                "coordword", page_id, psm, index, item.get("text"), coords["pixels"]
            ),
            "page_id": page_id,
            "page_number": page_number,
            "source_member": source_member,
            "source_image_sha256": source_image_sha256,
            "text": str(item.get("text") or ""),
            "confidence": conf,
            "psm": int(psm),
            "block_num": _as_int(item.get("block_num")),
            "par_num": _as_int(item.get("par_num")),
            "line_num": _as_int(item.get("line_num")),
            "word_num": _as_int(item.get("word_num")),
            "bbox": coords["pixels"],
            "normalized_bbox": coords["normalized"],
            "coordinate_system": coords["coordinate_system"],
            "within_page_bounds": True,
            "raw_tsv_path": raw_tsv_path,
            "bbox_source": "tesseract_tsv",
            "derived_coordinate_guidance": True,
        })
    return words, {
        "parser_source": parser_source,
        "parsed_word_count": len(parsed),
        "coordinate_word_count": len(words),
        "invalid_coordinate_word_count": invalid,
    }


def build_coordinate_lines(
    words: Sequence[Mapping[str, Any]],
    *,
    image_width: int,
    image_height: int,
    page_id: str,
    page_number: int,
    source_member: str,
    source_image_sha256: str,
    psm: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    grouped, grouper_source = group_coordinate_words_into_lines(words)
    by_id = {str(word.get("coordinate_word_id")): word for word in words}
    lines: list[dict[str, Any]] = []
    invalid = 0
    for index, line in enumerate(grouped):
        nested_words = line.get("words") or []
        word_ids: list[str] = []
        boxes: list[Mapping[str, Any]] = []
        for nested in nested_words:
            nested_id = nested.get("coordinate_word_id")
            if nested_id and str(nested_id) in by_id:
                word_ids.append(str(nested_id))
                boxes.append(by_id[str(nested_id)].get("bbox") or {})
                continue
            # Existing grouper copies the coordinate records, so the ID is normally present.
            text = str(nested.get("text") or "")
            bbox = nested.get("bbox") or {}
            match = next(
                (
                    word for word in words
                    if str(word.get("text") or "") == text
                    and word.get("bbox") == bbox
                ),
                None,
            )
            if match:
                word_ids.append(str(match.get("coordinate_word_id")))
                boxes.append(match.get("bbox") or {})
        pixel_bbox = union_pixel_bboxes(boxes) or line.get("bbox")
        coords = normalize_pixel_bbox(
            pixel_bbox or {},
            image_width=image_width,
            image_height=image_height,
        )
        if not coords:
            invalid += 1
            continue
        lines.append({
            "coordinate_line_id": stable_id(
                "coordline", page_id, psm, index, line.get("text"), coords["pixels"]
            ),
            "page_id": page_id,
            "page_number": page_number,
            "source_member": source_member,
            "source_image_sha256": source_image_sha256,
            "text": str(line.get("text") or ""),
            "word_count": len(word_ids),
            "word_ids": word_ids,
            "confidence": _as_float(line.get("mean_conf")),
            "psm": int(psm),
            "line_key": dict(line.get("line_key") or {}),
            "bbox": coords["pixels"],
            "normalized_bbox": coords["normalized"],
            "within_page_bounds": True,
            "reconstruction_method": "existing_tesseract_line_grouping",
            "derived_coordinate_guidance": True,
        })
    return lines, {
        "line_grouper_source": grouper_source,
        "coordinate_line_count": len(lines),
        "invalid_coordinate_line_count": invalid,
    }


def _median_word_height(words: Sequence[Mapping[str, Any]]) -> float:
    heights = sorted(
        float((word.get("bbox") or {}).get("height") or 0)
        for word in words
        if float((word.get("bbox") or {}).get("height") or 0) > 0
    )
    if not heights:
        return 10.0
    mid = len(heights) // 2
    return heights[mid] if len(heights) % 2 else (heights[mid - 1] + heights[mid]) / 2.0


def _split_line_words_into_cells(
    line_words: Sequence[Mapping[str, Any]],
) -> list[list[Mapping[str, Any]]]:
    ordered = sorted(line_words, key=lambda word: float((word.get("bbox") or {}).get("x0") or 0))
    if not ordered:
        return []
    gap_threshold = max(22.0, _median_word_height(ordered) * 2.25)
    cells: list[list[Mapping[str, Any]]] = [[ordered[0]]]
    previous = ordered[0]
    for word in ordered[1:]:
        gap = float((word.get("bbox") or {}).get("x0") or 0) - float(
            (previous.get("bbox") or {}).get("x1") or 0
        )
        if gap >= gap_threshold:
            cells.append([word])
        else:
            cells[-1].append(word)
        previous = word
    return cells


def build_table_row_candidates(
    lines: Sequence[Mapping[str, Any]],
    words: Sequence[Mapping[str, Any]],
    *,
    image_width: int,
    image_height: int,
    page_id: str,
    page_number: int,
    source_member: str,
    source_image_sha256: str,
) -> list[dict[str, Any]]:
    """Build coordinate-backed row/cell candidates without claiming source truth."""
    words_by_id = {str(word.get("coordinate_word_id")): word for word in words}
    rows: list[dict[str, Any]] = []
    for row_index, line in enumerate(lines):
        line_words = [
            words_by_id[word_id]
            for word_id in line.get("word_ids") or []
            if word_id in words_by_id
        ]
        if not line_words:
            continue
        cell_groups = _split_line_words_into_cells(line_words)
        cells: list[dict[str, Any]] = []
        for column_index, group in enumerate(cell_groups):
            box = union_pixel_bboxes([word.get("bbox") or {} for word in group])
            coords = normalize_pixel_bbox(
                box or {},
                image_width=image_width,
                image_height=image_height,
            )
            if not coords:
                continue
            cell_text = " ".join(str(word.get("text") or "") for word in group).strip()
            cells.append({
                "column_index": column_index,
                "text": cell_text,
                "word_ids": [str(word.get("coordinate_word_id")) for word in group],
                "bbox": coords["pixels"],
                "normalized_bbox": coords["normalized"],
                "coordinate_status": "valid",
                "derived_cell_candidate": True,
            })
        if not cells:
            continue
        row_bbox = union_pixel_bboxes([cell["bbox"] for cell in cells])
        row_coords = normalize_pixel_bbox(
            row_bbox or {},
            image_width=image_width,
            image_height=image_height,
        )
        if not row_coords:
            continue
        mean_conf_values = [
            float(word["confidence"])
            for word in line_words
            if _as_float(word.get("confidence")) is not None and float(word["confidence"]) >= 0
        ]
        mean_conf = (
            round(sum(mean_conf_values) / len(mean_conf_values), 3)
            if mean_conf_values else None
        )
        row_relationship_usable = len(cells) >= 2
        rows.append({
            "coordinate_row_candidate_id": stable_id(
                "coordrow", page_id, row_index, line.get("text"), row_coords["pixels"]
            ),
            "page_id": page_id,
            "page_number": page_number,
            "source_member": source_member,
            "source_image_sha256": source_image_sha256,
            "row_index": row_index,
            "text": str(line.get("text") or ""),
            "bbox": row_coords["pixels"],
            "normalized_bbox": row_coords["normalized"],
            "cells": cells,
            "cell_count": len(cells),
            "row_column_assignment": [
                {"column_index": cell["column_index"], "cell_bbox": cell["bbox"]}
                for cell in cells
            ],
            "coordinates_present": True,
            "reconstruction_method": "tesseract_tsv_line_gap_v1",
            "confidence_or_status": {
                "mean_tesseract_confidence": mean_conf,
                "status": (
                    "coordinate_row_candidate_with_columns"
                    if row_relationship_usable
                    else "coordinate_line_candidate_single_cell"
                ),
            },
            "raw_source_linkage": {
                "source_member": source_member,
                "source_image_sha256": source_image_sha256,
                "word_ids": [str(word.get("coordinate_word_id")) for word in line_words],
            },
            "row_relationship_usable": row_relationship_usable,
            "proves_item_part_nomenclature_quantity": False,
            "confirmed": False,
            "source_truth": False,
            "answer_permission": False,
        })
    return rows


def _callout_shape_reason(text: str) -> str | None:
    if NUMERIC_CALLOUT_RE.fullmatch(text):
        return "numeric_callout_label"
    if LETTER_CALLOUT_RE.fullmatch(text):
        return "letter_detail_label"
    if PART_NUMBER_RE.fullmatch(text):
        return "part_number_shaped_candidate"
    if SHORT_TECH_LABEL_RE.fullmatch(text) and any(char.isdigit() for char in text):
        return "short_technical_label"
    return None


def build_visual_callout_candidates(
    psm11_words: Sequence[Mapping[str, Any]],
    psm3_words: Sequence[Mapping[str, Any]],
    *,
    route: str,
    page_id: str,
    page_number: int,
    source_member: str,
    source_image_sha256: str,
) -> list[dict[str, Any]]:
    """Emit bbox-backed candidates only for visual routes and only when PSM11-unique."""
    if route not in VISUAL_ROUTES:
        return []
    primary_tokens = {str(word.get("text") or "").lower() for word in psm3_words}
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, float, float, float, float]] = set()
    for word in psm11_words:
        text = str(word.get("text") or "").strip()
        if not text or text.lower() in primary_tokens:
            continue
        reason = _callout_shape_reason(text)
        if not reason:
            continue
        bbox = word.get("bbox")
        normalized_bbox = word.get("normalized_bbox")
        if not isinstance(bbox, Mapping) or not isinstance(normalized_bbox, Mapping):
            continue
        key = (
            text.lower(),
            float(bbox.get("x0") or 0),
            float(bbox.get("y0") or 0),
            float(bbox.get("x1") or 0),
            float(bbox.get("y1") or 0),
        )
        if key in seen:
            continue
        seen.add(key)
        candidates.append({
            "coordinate_callout_candidate_id": stable_id(
                "coordcallout", page_id, text, bbox
            ),
            "page_id": page_id,
            "page_number": page_number,
            "source_member": source_member,
            "source_image_sha256": source_image_sha256,
            "candidate_text": text,
            "source_psm": 11,
            "source_word_id": word.get("coordinate_word_id"),
            "bbox": dict(bbox),
            "normalized_bbox": dict(normalized_bbox),
            "coordinate_status": "localized",
            "filtering_reason": reason,
            "psm11_unique_from_psm3": True,
            "confirmed": False,
            "source_truth": False,
            "answer_permission": False,
            "requires_visual_model_confirmation": True,
        })
    return candidates


def build_text_blocks(
    lines: Sequence[Mapping[str, Any]],
    *,
    image_width: int,
    image_height: int,
    page_id: str,
    page_number: int,
    source_member: str,
    source_image_sha256: str,
) -> list[dict[str, Any]]:
    """Build conservative coordinate blocks by Tesseract block number."""
    groups: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for line in lines:
        block_num = _as_int((line.get("line_key") or {}).get("block_num"))
        groups[block_num].append(line)
    blocks: list[dict[str, Any]] = []
    for block_index, (block_num, members) in enumerate(sorted(groups.items())):
        box = union_pixel_bboxes([line.get("bbox") or {} for line in members])
        coords = normalize_pixel_bbox(
            box or {},
            image_width=image_width,
            image_height=image_height,
        )
        if not coords:
            continue
        blocks.append({
            "coordinate_text_block_id": stable_id(
                "coordblock", page_id, block_num, [line.get("coordinate_line_id") for line in members]
            ),
            "page_id": page_id,
            "page_number": page_number,
            "source_member": source_member,
            "source_image_sha256": source_image_sha256,
            "block_index": block_index,
            "tesseract_block_num": block_num,
            "text": "\n".join(str(line.get("text") or "") for line in members).strip(),
            "line_ids": [str(line.get("coordinate_line_id")) for line in members],
            "bbox": coords["pixels"],
            "normalized_bbox": coords["normalized"],
            "coordinate_status": "valid",
            "confirmed": False,
            "source_truth": False,
            "answer_permission": False,
        })
    return blocks


def build_page_coordinate_evidence(
    *,
    page_id: str,
    page_number: int,
    source_member: str,
    source_image_sha256: str,
    image_width: int,
    image_height: int,
    source_manifest_route: str,
    route_tsv_payloads: Mapping[int, Mapping[str, Any]],
) -> dict[str, Any]:
    """Build one route-aware coordinate evidence record without changing route."""
    route = str(source_manifest_route)
    psm_outputs: dict[str, Any] = {}
    invalid_coordinates = 0
    all_words: dict[int, list[dict[str, Any]]] = {}
    all_lines: dict[int, list[dict[str, Any]]] = {}

    for psm, payload in sorted(route_tsv_payloads.items()):
        tsv_text = str(payload.get("tsv_text") or "")
        raw_tsv_path = payload.get("raw_tsv_path")
        words, word_meta = build_coordinate_words(
            tsv_text,
            image_width=image_width,
            image_height=image_height,
            page_id=page_id,
            page_number=page_number,
            source_member=source_member,
            source_image_sha256=source_image_sha256,
            psm=int(psm),
            raw_tsv_path=str(raw_tsv_path) if raw_tsv_path else None,
        )
        lines, line_meta = build_coordinate_lines(
            words,
            image_width=image_width,
            image_height=image_height,
            page_id=page_id,
            page_number=page_number,
            source_member=source_member,
            source_image_sha256=source_image_sha256,
            psm=int(psm),
        )
        all_words[int(psm)] = words
        all_lines[int(psm)] = lines
        invalid_coordinates += int(word_meta["invalid_coordinate_word_count"])
        invalid_coordinates += int(line_meta["invalid_coordinate_line_count"])
        psm_outputs[str(psm)] = {
            "psm": int(psm),
            "raw_tsv_path": raw_tsv_path,
            "raw_tsv_sha256": payload.get("raw_tsv_sha256"),
            "tesseract_status": payload.get("tesseract_status"),
            "tesseract_error": payload.get("tesseract_error"),
            "words": words,
            "lines": lines,
            **word_meta,
            **line_meta,
        }

    table_rows: list[dict[str, Any]] = []
    callouts: list[dict[str, Any]] = []
    text_blocks: list[dict[str, Any]] = []

    if route in TABLE_ROUTES:
        selected_psm = 6 if 6 in all_words else (3 if 3 in all_words else next(iter(all_words), None))
        if selected_psm is not None:
            table_rows = build_table_row_candidates(
                all_lines[selected_psm],
                all_words[selected_psm],
                image_width=image_width,
                image_height=image_height,
                page_id=page_id,
                page_number=page_number,
                source_member=source_member,
                source_image_sha256=source_image_sha256,
            )
    elif route in VISUAL_ROUTES:
        callouts = build_visual_callout_candidates(
            all_words.get(11, []),
            all_words.get(3, []),
            route=route,
            page_id=page_id,
            page_number=page_number,
            source_member=source_member,
            source_image_sha256=source_image_sha256,
        )
    elif route in TEXT_ROUTES:
        selected_psm = 3 if 3 in all_lines else next(iter(all_lines), None)
        if selected_psm is not None:
            text_blocks = build_text_blocks(
                all_lines[selected_psm],
                image_width=image_width,
                image_height=image_height,
                page_id=page_id,
                page_number=page_number,
                source_member=source_member,
                source_image_sha256=source_image_sha256,
            )

    total_words = sum(len(words) for words in all_words.values())
    total_lines = sum(len(lines) for lines in all_lines.values())
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "record_type": "trace_net_page_coordinate_evidence",
        "page_id": page_id,
        "page_number": page_number,
        "source_member": source_member,
        "source_image_sha256": source_image_sha256,
        "image_width": image_width,
        "image_height": image_height,
        "source_manifest_route": route,
        "coordinate_processing_route": route,
        "route_preserved": True,
        "route_mutation_performed": False,
        "psm_outputs": psm_outputs,
        "coordinate_word_count": total_words,
        "coordinate_line_count": total_lines,
        "invalid_coordinate_count": invalid_coordinates,
        "table_row_candidates": table_rows,
        "table_row_candidate_count": len(table_rows),
        "coordinate_row_relationship_usable_count": sum(
            1 for row in table_rows if row.get("row_relationship_usable")
        ),
        "visual_callout_candidates": callouts,
        "visual_callout_candidate_count": len(callouts),
        "normal_text_blocks": text_blocks,
        "normal_text_block_count": len(text_blocks),
        "blank_page_no_word_boxes": route in BLANK_ROUTES and total_words == 0,
        "derived_layout_guidance": True,
        "requires_source_truth_confirmation": True,
        **SAFETY_CONTRACT,
    }
    return evidence


def summarize_coordinate_evidence(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    route_counts: dict[str, int] = defaultdict(int)
    for record in records:
        route_counts[str(record.get("source_manifest_route") or "missing")] += 1

    callouts = [
        candidate
        for record in records
        for candidate in (record.get("visual_callout_candidates") or [])
        if isinstance(candidate, Mapping)
    ]
    rows = [
        row
        for record in records
        for row in (record.get("table_row_candidates") or [])
        if isinstance(row, Mapping)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "selected_page_count": len(records),
        "route_counts": dict(sorted(route_counts.items())),
        "source_hash_present_count": sum(1 for record in records if record.get("source_image_sha256")),
        "route_preserved_count": sum(1 for record in records if record.get("route_preserved") is True),
        "route_mutation_count": sum(1 for record in records if record.get("route_mutation_performed") is True),
        "nonblank_page_count": sum(
            1 for record in records if record.get("source_manifest_route") not in BLANK_ROUTES
        ),
        "nonblank_page_with_word_boxes_count": sum(
            1 for record in records
            if record.get("source_manifest_route") not in BLANK_ROUTES
            and int(record.get("coordinate_word_count") or 0) > 0
        ),
        "blank_page_count": sum(
            1 for record in records if record.get("source_manifest_route") in BLANK_ROUTES
        ),
        "blank_page_with_word_boxes_count": sum(
            1 for record in records
            if record.get("source_manifest_route") in BLANK_ROUTES
            and int(record.get("coordinate_word_count") or 0) > 0
        ),
        "coordinate_word_count": sum(int(record.get("coordinate_word_count") or 0) for record in records),
        "coordinate_line_count": sum(int(record.get("coordinate_line_count") or 0) for record in records),
        "invalid_coordinate_count": sum(int(record.get("invalid_coordinate_count") or 0) for record in records),
        "table_page_count": sum(1 for record in records if record.get("source_manifest_route") in TABLE_ROUTES),
        "table_page_with_row_candidate_count": sum(
            1 for record in records
            if record.get("source_manifest_route") in TABLE_ROUTES
            and int(record.get("table_row_candidate_count") or 0) > 0
        ),
        "table_row_candidate_count": len(rows),
        "table_row_missing_coordinate_count": sum(
            1 for row in rows
            if not row.get("coordinates_present") or not row.get("bbox")
        ),
        "coordinate_row_relationship_usable_count": sum(
            1 for row in rows if row.get("row_relationship_usable")
        ),
        "table_row_claim_proof_count": sum(
            1 for row in rows if row.get("proves_item_part_nomenclature_quantity")
        ),
        "visual_page_count": sum(1 for record in records if record.get("source_manifest_route") in VISUAL_ROUTES),
        "visual_page_with_psm11_word_boxes_count": sum(
            1 for record in records
            if record.get("source_manifest_route") in VISUAL_ROUTES
            and int(((record.get("psm_outputs") or {}).get("11") or {}).get("coordinate_word_count") or 0) > 0
        ),
        "visual_callout_candidate_count": len(callouts),
        "callout_on_nonvisual_route_count": sum(
            1 for record in records
            if record.get("source_manifest_route") not in VISUAL_ROUTES
            for _ in (record.get("visual_callout_candidates") or [])
        ),
        "callout_missing_bbox_count": sum(
            1 for candidate in callouts
            if not candidate.get("bbox") or not candidate.get("normalized_bbox")
        ),
        "callout_confirmed_count": sum(1 for candidate in callouts if candidate.get("confirmed")),
        "callout_source_truth_count": sum(1 for candidate in callouts if candidate.get("source_truth")),
        "normal_text_page_count": sum(1 for record in records if record.get("source_manifest_route") in TEXT_ROUTES),
        "normal_text_page_with_block_count": sum(
            1 for record in records
            if record.get("source_manifest_route") in TEXT_ROUTES
            and int(record.get("normal_text_block_count") or 0) > 0
        ),
        "normal_text_block_count": sum(
            int(record.get("normal_text_block_count") or 0) for record in records
        ),
        "answer_permission_count": sum(1 for record in records if record.get("answer_permission")),
        "can_prove_claims_count": sum(1 for record in records if record.get("can_prove_claims")),
        "source_truth_mutation_allowed_count": sum(
            1 for record in records if record.get("source_truth_mutation_allowed")
        ),
        "postgres_write_attempt_count": sum(
            int(record.get("postgres_write_attempt_count") or 0) for record in records
        ),
        "qdrant_write_attempt_count": sum(
            int(record.get("qdrant_write_attempt_count") or 0) for record in records
        ),
        "opensearch_write_attempt_count": sum(
            int(record.get("opensearch_write_attempt_count") or 0) for record in records
        ),
    }
