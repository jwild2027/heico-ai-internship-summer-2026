#!/usr/bin/env python3
"""Layout-aware OCR reconstruction for TRACE-Net H30.

This module separates three different things that flat OCR often mixes together:

* literal OCR text;
* reconstructed table/column relationships; and
* scan-quality measurements.

The reconstruction is deterministic and read-only.  It may organize tokens that
are already present in OCR, but it never creates source truth, grants engineering
authority, changes a route, or infers blur from OCR quality.
"""
from __future__ import annotations

import json
import re
import statistics
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

MODULE = "trace_net_h30_layout_aware_ocr_v1"
VERSION = "v1"
STATUS = "TRACE_NET_H30_LAYOUT_AWARE_OCR_V1"
SCHEMA_VERSION = "trace_net_layout_aware_ocr_v1"

MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
DATE_RE = re.compile(rf"\b{MONTH}\s+\d{{1,2}}/\d{{2}}\b", re.I)
SECTION_RE = re.compile(r"\b\d{2}-(?:LEP|\d{2}-\d{2})\b", re.I)
ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
LEP_RE = re.compile(r"\b\d{2}-LEP\b", re.I)
PAGE_WORD_RE = re.compile(r"\bPAGE\s+(\d{1,4})\b", re.I)

SAFETY_CONTRACT = {
    "read_only": True,
    "derived_layout_is_not_source_truth": True,
    "derived_layout_is_not_engineering_authority": True,
    "scan_quality_inferred_from_ocr": False,
    "blur_inferred_from_ocr": False,
    "query_wording_can_set_layout": False,
    "query_wording_can_set_scan_quality": False,
    "answer_permission": False,
    "final_answer_allowed": False,
    "can_prove_claims": False,
    "source_truth_mutation_allowed": False,
    "write_attempt_count": 0,
}


def _compact(value: Any, limit: int = 12000) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            text = str(value)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _clean_token(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _box_from_word(raw: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    text = _clean_token(raw.get("text") or raw.get("word") or raw.get("token") or raw.get("value"))
    if not text:
        return None
    left = _float(raw.get("left") if raw.get("left") is not None else raw.get("x"))
    top = _float(raw.get("top") if raw.get("top") is not None else raw.get("y"))
    width = _float(raw.get("width") if raw.get("width") is not None else raw.get("w"))
    height = _float(raw.get("height") if raw.get("height") is not None else raw.get("h"))
    bbox = raw.get("bbox")
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        left = left if left is not None else _float(bbox[0])
        top = top if top is not None else _float(bbox[1])
        if width is None:
            right = _float(bbox[2])
            width = None if right is None or left is None else right - left
        if height is None:
            bottom = _float(bbox[3])
            height = None if bottom is None or top is None else bottom - top
    if left is None or top is None:
        return None
    width = max(1.0, width or 1.0)
    height = max(1.0, height or 1.0)
    return {
        "text": text,
        "left": left,
        "top": top,
        "width": width,
        "height": height,
        "x_center": left + width / 2.0,
        "y_center": top + height / 2.0,
    }


def _normalize_word_boxes(word_boxes: Any) -> List[Dict[str, Any]]:
    if not isinstance(word_boxes, list):
        return []
    output: List[Dict[str, Any]] = []
    for raw in word_boxes:
        if not isinstance(raw, Mapping):
            continue
        box = _box_from_word(raw)
        if box is not None:
            output.append(box)
    return output


def _cluster_lines(boxes: Sequence[Mapping[str, Any]]) -> List[List[Dict[str, Any]]]:
    if not boxes:
        return []
    heights = [float(row.get("height") or 1.0) for row in boxes]
    tolerance = max(2.0, statistics.median(heights) * 0.65)
    ordered = sorted((dict(row) for row in boxes), key=lambda row: (float(row["y_center"]), float(row["left"])))
    lines: List[List[Dict[str, Any]]] = []
    line_centers: List[float] = []
    for box in ordered:
        y = float(box["y_center"])
        best_index = -1
        best_distance = float("inf")
        for index, center in enumerate(line_centers):
            distance = abs(y - center)
            if distance <= tolerance and distance < best_distance:
                best_index = index
                best_distance = distance
        if best_index < 0:
            lines.append([box])
            line_centers.append(y)
        else:
            lines[best_index].append(box)
            line_centers[best_index] = statistics.mean(float(item["y_center"]) for item in lines[best_index])
    return [sorted(line, key=lambda row: float(row["left"])) for line in lines]


def _line_text(line: Sequence[Mapping[str, Any]]) -> str:
    return " ".join(_clean_token(row.get("text")) for row in line if _clean_token(row.get("text")))


def _row_key(row: Mapping[str, Any]) -> Tuple[str, str, str, str]:
    return (
        str(row.get("section") or "").upper(),
        str(row.get("page") or ""),
        str(row.get("date") or "").upper(),
        str(row.get("text") or "").upper(),
    )


def _dedupe_rows(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    seen = set()
    for raw in rows:
        row = dict(raw)
        key = _row_key(row)
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def _parse_standard_rows(text: str, *, basis: str) -> Tuple[List[Dict[str, Any]], List[Tuple[int, int]]]:
    rows: List[Dict[str, Any]] = []
    consumed: List[Tuple[int, int]] = []
    patterns = (
        re.compile(rf"(?P<section>\d{{2}}-\d{{2}}-\d{{2}})\s+(?P<page>\d{{1,4}})\s+(?P<date>{MONTH}\s+\d{{1,2}}/\d{{2}})", re.I),
        re.compile(rf"(?P<date>{MONTH}\s+\d{{1,2}}/\d{{2}})\s+(?P<section>\d{{2}}-\d{{2}}-\d{{2}})\s+(?P<page>\d{{1,4}})", re.I),
    )
    for pattern in patterns:
        for match in pattern.finditer(text):
            # Do not reinterpret a token span that is already part of a stronger
            # section-page-date row. This prevents the left-column date of a
            # flattened two-column LEP table from being attached to the right row.
            if _overlaps(match.span(), consumed):
                continue
            section = match.group("section").upper()
            row = {
                "row_type": "effective_page_entry",
                "section": section,
                "ata": section,
                "page": match.group("page"),
                "date": re.sub(r"\s+", " ", match.group("date")).title(),
                "text": re.sub(r"\s+", " ", match.group(0)).strip(),
                "basis": basis,
                "confidence": "high" if basis == "word_coordinates" else "medium",
            }
            rows.append(row)
            consumed.append(match.span())
    return _dedupe_rows(rows), consumed


def _overlaps(span: Tuple[int, int], consumed: Sequence[Tuple[int, int]]) -> bool:
    return any(span[0] < other[1] and other[0] < span[1] for other in consumed)


def _nearest_unconsumed_date(text: str, position: int, consumed: Sequence[Tuple[int, int]]) -> Optional[re.Match[str]]:
    candidates = [match for match in DATE_RE.finditer(text) if not _overlaps(match.span(), consumed)]
    if not candidates:
        return None
    return min(candidates, key=lambda match: abs(((match.start() + match.end()) // 2) - position))


def _parse_lep_rows(text: str, consumed: Sequence[Tuple[int, int]], *, basis: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    page_match = PAGE_WORD_RE.search(text)
    for section_match in LEP_RE.finditer(text):
        date_match = _nearest_unconsumed_date(text, (section_match.start() + section_match.end()) // 2, consumed)
        row = {
            "row_type": "effective_page_header_entry",
            "section": section_match.group(0).upper(),
            "date": re.sub(r"\s+", " ", date_match.group(0)).title() if date_match else "",
            "page": page_match.group(1) if page_match else "",
            "text": section_match.group(0).upper(),
            "basis": basis,
            "confidence": "high" if basis == "word_coordinates" and date_match else "medium" if date_match else "low",
        }
        rows.append(row)
    return _dedupe_rows(rows)


def _detect_table_kind(text: str, rows: Sequence[Mapping[str, Any]]) -> str:
    upper = text.upper()
    if "LIST OF EFFECTIVE PAGES" in upper or LEP_RE.search(upper):
        return "list_of_effective_pages"
    if len(rows) >= 2 or (SECTION_RE.search(upper) and DATE_RE.search(upper)):
        return "table_or_index"
    return ""


def _coordinate_reconstruction(word_boxes: Any) -> Dict[str, Any]:
    boxes = _normalize_word_boxes(word_boxes)
    if not boxes:
        return {"available": False, "lines": [], "rows": []}
    lines = _cluster_lines(boxes)
    line_texts = [_line_text(line) for line in lines]
    rows: List[Dict[str, Any]] = []
    for line_text in line_texts:
        parsed, consumed = _parse_standard_rows(line_text, basis="word_coordinates")
        rows.extend(parsed)
        rows.extend(_parse_lep_rows(line_text, consumed, basis="word_coordinates"))
    return {
        "available": True,
        "lines": line_texts,
        "rows": _dedupe_rows(rows),
        "word_count": len(boxes),
        "line_count": len(line_texts),
    }


def _flattened_order_detected(text: str, rows: Sequence[Mapping[str, Any]]) -> bool:
    if len(rows) < 2:
        return False
    lep = LEP_RE.search(text)
    standard = ATA_RE.search(text)
    dates = list(DATE_RE.finditer(text))
    if lep and standard and len(dates) >= 2:
        # A common multi-column flattening signature is left-column date, then a
        # complete right-column row, followed later by the left-column section.
        return dates[0].start() < standard.start() < dates[-1].end() < lep.end()
    return False


def reconstruct_layout_aware_ocr(
    text: Any,
    *,
    word_boxes: Any = None,
    page_route: Any = None,
) -> Dict[str, Any]:
    """Return a conservative, typed reconstruction of table relationships.

    ``page_route`` is metadata only.  It never changes scan quality and cannot
    cause text to be classified as blurry.  The function prefers word-coordinate
    rows when available and falls back to token-order patterns otherwise.
    """
    source_text = _compact(text)
    coordinate = _coordinate_reconstruction(word_boxes)
    rows = list(coordinate.get("rows") or [])
    basis = "word_coordinates" if rows else "text_pattern"
    consumed: List[Tuple[int, int]] = []
    if not rows and source_text:
        rows, consumed = _parse_standard_rows(source_text, basis=basis)
        rows.extend(_parse_lep_rows(source_text, consumed, basis=basis))
        rows = _dedupe_rows(rows)

    table_kind = _detect_table_kind(source_text, rows)
    available = bool(rows and table_kind)
    flattened = bool(available and basis == "text_pattern" and _flattened_order_detected(source_text, rows))
    confidence = "none"
    if available:
        confidence = "high" if basis == "word_coordinates" else "medium"
        if any(row.get("confidence") == "low" for row in rows):
            confidence = "low"

    return {
        "module": MODULE,
        "version": VERSION,
        "schema_version": SCHEMA_VERSION,
        "status": STATUS,
        "reconstruction_available": available,
        "table_kind": table_kind,
        "rows": rows,
        "reconstructed_lines": list(coordinate.get("lines") or []),
        "reconstruction_basis": basis if available else "none",
        "reconstruction_confidence": confidence,
        "flattened_multi_column_reading_order": flattened,
        "layout_issue_detected": bool(flattened),
        "layout_issue_type": "flattened_multi_column_reading_order" if flattened else "",
        "page_route_observed": _compact(page_route, 120),
        "requires_image_verification": bool(available and basis != "word_coordinates"),
        "guidance_only": True,
        "derived_from_ocr": True,
        "claim_support_allowed": False,
        "scan_quality_inferred": False,
        "blur_detected": False,
        "blur_claim_allowed": False,
        **SAFETY_CONTRACT,
    }


def format_layout_row(row: Mapping[str, Any]) -> str:
    section = _clean_token(row.get("section"))
    page = _clean_token(row.get("page"))
    date = _clean_token(row.get("date"))
    parts: List[str] = []
    if section:
        label = "ATA" if ATA_RE.fullmatch(section) else "Section"
        parts.append(f"{label} {section}")
    if page:
        parts.append(f"manual page {page}")
    if date:
        parts.append(f"dated {date}")
    return " — ".join(parts)


def render_layout_reconstruction(reconstruction: Mapping[str, Any], *, maximum_rows: int = 8) -> str:
    if not reconstruction.get("reconstruction_available"):
        return ""
    rows = [row for row in reconstruction.get("rows") or [] if isinstance(row, Mapping)]
    rendered = [format_layout_row(row) for row in rows[: max(1, maximum_rows)]]
    rendered = [value for value in rendered if value]
    title = "List of Effective Pages table" if reconstruction.get("table_kind") == "list_of_effective_pages" else "table/index content"
    if not rendered:
        return title
    return f"{title}: " + "; ".join(rendered)


def health() -> Dict[str, Any]:
    return {
        "layout_aware_ocr_enabled": True,
        "layout_aware_ocr_status": STATUS,
        "coordinate_first_reconstruction": True,
        "text_pattern_fallback": True,
        "derived_layout_is_guidance_only": True,
        "scan_quality_inferred_from_ocr": False,
        "blur_inferred_from_ocr": False,
        "adds_gemma_call": False,
        "changes_retrieval": False,
        **SAFETY_CONTRACT,
    }


__all__ = [
    "MODULE",
    "VERSION",
    "STATUS",
    "SCHEMA_VERSION",
    "SAFETY_CONTRACT",
    "reconstruct_layout_aware_ocr",
    "render_layout_reconstruction",
    "format_layout_row",
    "health",
]
