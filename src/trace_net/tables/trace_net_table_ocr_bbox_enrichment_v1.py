"""TRACE-Net Table OCR BBox Enrichment v1.

Read-only enrichment layer that looks for OCR word/line bounding boxes near
TRACE-Net table geometry cards and proposes advisory table-region crop boxes.

This module does not mutate source truth and does not write to Postgres,
Qdrant, or OpenSearch. Its output is advisory crop metadata for later table
geometry/bbox resolver passes.
"""
from __future__ import annotations

import argparse
import csv
import html
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "trace_net_table_ocr_bbox_enrichment_v1"
QUALITY_SCHEMA_VERSION = "trace_net_table_ocr_bbox_enrichment_v1_quality"
STATUS_BUILT = "TABLE_OCR_BBOX_ENRICHMENT_BUILT"
STATUS_NOT_READY = "TABLE_OCR_BBOX_ENRICHMENT_NOT_READY"

OCR_EXTENSIONS = {".tsv", ".hocr", ".html", ".htm", ".xml", ".json", ".jsonl"}
PART_NUMBER_RE = re.compile(r"\b\d{2,4}-\d{3,6}(?:-[A-Z0-9]{1,4})?\b")
PAGE_RE = re.compile(r"p(\d{6})|page[_-]?(\d{6})|zip_page[_-]?(\d{6})", re.I)
BBOX_KEYS = (
    "bbox", "bounding_box", "bounds", "box", "ocr_bbox", "word_bbox", "text_bbox",
    "cell_bbox", "row_bbox", "table_bbox", "table_region_bbox",
)
EXTRACTION_BBOX_KEYS = (
    "table_extraction_bbox",
    "selected_table_extraction_bbox",
    "paddle_style_table_extraction_bbox",
    "extraction_bbox",
)
EXTRACTION_BBOX_SOURCE_KEYS = (
    "table_extraction_bbox_source",
    "selected_table_extraction_bbox_source",
    "paddle_style_table_extraction_bbox_source",
    "extraction_bbox_source",
    "bbox_source",
)
EXTRACTION_BBOX_CONFIDENCE_KEYS = (
    "table_extraction_bbox_confidence",
    "selected_table_extraction_bbox_confidence",
    "paddle_style_table_extraction_bbox_confidence",
    "extraction_bbox_confidence",
    "bbox_confidence",
)
TEXT_KEYS = ("text", "normalized_text", "normalized_value", "value", "word", "content", "line_text")
X0_KEYS = ("x0", "x_min", "xmin", "left")
Y0_KEYS = ("y0", "y_min", "ymin", "top")
X1_KEYS = ("x1", "x_max", "xmax", "right")
Y1_KEYS = ("y1", "y_max", "ymax", "bottom")
WIDTH_KEYS = ("width", "w")
HEIGHT_KEYS = ("height", "h")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_id(prefix: str, *parts: Any) -> str:
    digest = hashlib.sha256("::".join(str(p) for p in parts if p is not None).encode("utf-8")).hexdigest()[:14]
    return f"{prefix}_{digest}"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
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
        if isinstance(value, str) and not value.strip():
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def token_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9-]+", "", normalize_text(value))


def first_present(mapping: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in mapping and mapping.get(key) is not None:
            return mapping.get(key)
    return None


def clamp_bbox(x0: float, y0: float, x1: float, y1: float, width: Optional[int] = None, height: Optional[int] = None) -> Optional[Dict[str, Any]]:
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    if width and height:
        if 0 <= x0 <= 1 and 0 <= x1 <= 1 and 0 <= y0 <= 1 and 0 <= y1 <= 1:
            x0, x1 = x0 * width, x1 * width
            y0, y1 = y0 * height, y1 * height
        x0 = max(0.0, min(float(width), x0))
        x1 = max(0.0, min(float(width), x1))
        y0 = max(0.0, min(float(height), y0))
        y1 = max(0.0, min(float(height), y1))
    if x1 - x0 < 1 or y1 - y0 < 1:
        return None
    return {
        "x0": round(x0, 3),
        "y0": round(y0, 3),
        "x1": round(x1, 3),
        "y1": round(y1, 3),
        "width": round(x1 - x0, 3),
        "height": round(y1 - y0, 3),
        "coordinate_system": "pixels" if width and height else "source_units",
    }


def bbox_from_mapping(mapping: Mapping[str, Any], width: Optional[int] = None, height: Optional[int] = None) -> Optional[Dict[str, Any]]:
    x0 = as_float(first_present(mapping, X0_KEYS))
    y0 = as_float(first_present(mapping, Y0_KEYS))
    x1 = as_float(first_present(mapping, X1_KEYS))
    y1 = as_float(first_present(mapping, Y1_KEYS))
    if x0 is not None and y0 is not None and x1 is not None and y1 is not None:
        return clamp_bbox(x0, y0, x1, y1, width, height)
    left = as_float(first_present(mapping, ("x", "left")))
    top = as_float(first_present(mapping, ("y", "top")))
    w = as_float(first_present(mapping, WIDTH_KEYS))
    h = as_float(first_present(mapping, HEIGHT_KEYS))
    if left is not None and top is not None and w is not None and h is not None:
        return clamp_bbox(left, top, left + w, top + h, width, height)
    return None


def bbox_from_value(value: Any, width: Optional[int] = None, height: Optional[int] = None) -> Optional[Dict[str, Any]]:
    if isinstance(value, Mapping):
        return bbox_from_mapping(value, width, height)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) >= 4:
        nums = [as_float(v) for v in list(value)[:4]]
        if all(v is not None for v in nums):
            return clamp_bbox(nums[0], nums[1], nums[2], nums[3], width, height)  # type: ignore[arg-type]
    return None


def bbox_area(box: Mapping[str, Any]) -> float:
    return float(box.get("width") or 0) * float(box.get("height") or 0)


def union_bboxes(boxes: Sequence[Mapping[str, Any]], *, pad_ratio: float = 0.035, width: Optional[int] = None, height: Optional[int] = None) -> Optional[Dict[str, Any]]:
    if not boxes:
        return None
    x0 = min(float(b["x0"]) for b in boxes)
    y0 = min(float(b["y0"]) for b in boxes)
    x1 = max(float(b["x1"]) for b in boxes)
    y1 = max(float(b["y1"]) for b in boxes)
    pad_x = max(2.0, (x1 - x0) * pad_ratio)
    pad_y = max(2.0, (y1 - y0) * pad_ratio)
    return clamp_bbox(x0 - pad_x, y0 - pad_y, x1 + pad_x, y1 + pad_y, width, height)


def bbox_coverage(box: Optional[Mapping[str, Any]], width: Optional[int], height: Optional[int]) -> Optional[float]:
    if not box or not width or not height:
        return None
    page_area = float(width * height)
    if page_area <= 0:
        return None
    return round(bbox_area(box) / page_area, 6)


def percentile(values: Sequence[float], q: float) -> Optional[float]:
    """Return a simple percentile without pulling in numpy."""
    if not values:
        return None
    ordered = sorted(float(v) for v in values if math.isfinite(float(v)))
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    q = max(0.0, min(1.0, q))
    pos = q * (len(ordered) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def tighten_ocr_bbox_to_content_band(
    records: Sequence[Mapping[str, Any]],
    broad_box: Optional[Mapping[str, Any]],
    *,
    width: Optional[int],
    height: Optional[int],
    table_type: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Tighten broad OCR unions to the dense content band.

    Tesseract sidecars often match text across headers, footers, and page
    furniture. A raw union of all matched OCR boxes can therefore become an
    almost full-page crop. This keeps the original crop available for audit, but
    trims the candidate to OCR boxes inside a central percentile band when the
    original is broad. The output remains advisory; downstream crop scoring can
    still reject it if morphology does not improve.
    """
    diagnostics: Dict[str, Any] = {
        "ocr_content_band_tightening_available": False,
        "ocr_content_band_tightening_applied": False,
        "ocr_content_band_tightening_reason": None,
        "ocr_content_band_source_record_count": 0,
        "ocr_content_band_selected_record_count": 0,
        "ocr_content_band_original_coverage_ratio": bbox_coverage(broad_box, width, height),
        "ocr_content_band_tightened_coverage_ratio": None,
        "ocr_content_band_bbox": None,
        "ocr_original_inferred_table_region_bbox": broad_box,
    }
    if not broad_box or not width or not height:
        diagnostics["ocr_content_band_tightening_reason"] = "missing_bbox_or_image_dimensions"
        return broad_box if broad_box else None, diagnostics

    page_area = float(width * height)
    if page_area <= 0:
        diagnostics["ocr_content_band_tightening_reason"] = "invalid_image_dimensions"
        return dict(broad_box), diagnostics

    coverage = bbox_area(broad_box) / page_area
    if coverage < 0.72:
        diagnostics["ocr_content_band_tightening_reason"] = "bbox_not_broad_enough_for_content_band_tightening"
        return dict(broad_box), diagnostics

    boxes: List[Mapping[str, Any]] = []
    for record in records:
        box = record.get("bbox") if isinstance(record, Mapping) else None
        if isinstance(box, Mapping) and bbox_valid_dimensions(box):
            boxes.append(box)
    diagnostics["ocr_content_band_source_record_count"] = len(boxes)
    if len(boxes) < 8:
        diagnostics["ocr_content_band_tightening_reason"] = "insufficient_ocr_records_for_content_band_tightening"
        return dict(broad_box), diagnostics

    x_centers = [(float(b["x0"]) + float(b["x1"])) / 2.0 for b in boxes]
    y_centers = [(float(b["y0"]) + float(b["y1"])) / 2.0 for b in boxes]
    # Trim outlier headers/footers and stray marginal tokens. Keep enough margin
    # to preserve row labels and table headings while avoiding full-page unions.
    y_low = percentile(y_centers, 0.06)
    y_high = percentile(y_centers, 0.94)
    x_low = percentile(x_centers, 0.03)
    x_high = percentile(x_centers, 0.97)
    if y_low is None or y_high is None or x_low is None or x_high is None or y_high <= y_low or x_high <= x_low:
        diagnostics["ocr_content_band_tightening_reason"] = "content_band_percentiles_invalid"
        return dict(broad_box), diagnostics

    selected = []
    for box in boxes:
        xc = (float(box["x0"]) + float(box["x1"])) / 2.0
        yc = (float(box["y0"]) + float(box["y1"])) / 2.0
        if x_low <= xc <= x_high and y_low <= yc <= y_high:
            selected.append(box)
    diagnostics["ocr_content_band_selected_record_count"] = len(selected)
    if len(selected) < 6:
        diagnostics["ocr_content_band_tightening_reason"] = "content_band_selected_too_few_records"
        return dict(broad_box), diagnostics

    tightened = union_bboxes(selected, pad_ratio=0.025, width=width, height=height)
    tightened_coverage = bbox_coverage(tightened, width, height)
    diagnostics["ocr_content_band_bbox"] = tightened
    diagnostics["ocr_content_band_tightened_coverage_ratio"] = tightened_coverage
    diagnostics["ocr_content_band_tightening_available"] = True

    if not tightened or tightened_coverage is None:
        diagnostics["ocr_content_band_tightening_reason"] = "tightened_bbox_invalid"
        return dict(broad_box), diagnostics
    if tightened_coverage >= coverage - 0.02:
        diagnostics["ocr_content_band_tightening_reason"] = "tightened_bbox_did_not_reduce_coverage"
        return dict(broad_box), diagnostics
    if tightened_coverage < 0.01:
        diagnostics["ocr_content_band_tightening_reason"] = "tightened_bbox_too_small"
        return dict(broad_box), diagnostics

    diagnostics["ocr_content_band_tightening_applied"] = True
    diagnostics["ocr_content_band_tightening_reason"] = "tightened_broad_ocr_bbox_to_content_band"
    return tightened, diagnostics


def bbox_valid_dimensions(box: Mapping[str, Any]) -> bool:
    try:
        return float(box.get("width") or 0) >= 1 and float(box.get("height") or 0) >= 1
    except Exception:
        return False


def image_dimensions(path: Optional[Path]) -> Tuple[Optional[int], Optional[int]]:
    if path is None or not path.exists() or not path.is_file():
        return None, None
    try:
        from PIL import Image  # type: ignore
        with Image.open(path) as image:
            return int(image.width), int(image.height)
    except Exception:
        return None, None


def normalize_path(value: Any, image_root: Optional[Path] = None) -> Optional[Path]:
    if not value:
        return None
    raw = str(value).replace("\\", "/")
    path = Path(raw)
    candidates: List[Path] = []
    if path.is_absolute():
        candidates.append(path)
    else:
        candidates.append(Path(raw))
        if image_root is not None:
            candidates.append(image_root / raw)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1] if candidates else None


def page_number_tokens(page_id: Any, image_path: Any = None) -> List[str]:
    tokens: List[str] = []
    for value in (page_id, image_path):
        if not value:
            continue
        text = str(value).replace("\\", "/")
        for match in PAGE_RE.finditer(text):
            number = next((g for g in match.groups() if g), None)
            if number:
                tokens.extend([number, f"p{number}", f"page_{number}", f"zip_page_{number}"])
    # Also support page ids ending p000003.
    if page_id:
        m = re.search(r"p(\d{6})$", str(page_id))
        if m:
            number = m.group(1)
            tokens.extend([number, f"p{number}", f"page_{number}", f"zip_page_{number}"])
    seen = set()
    result = []
    for token in tokens:
        if token not in seen:
            result.append(token)
            seen.add(token)
    return result


def find_candidate_ocr_files(ocr_root: Optional[Path], resolved_image_path: Any, page_id: Any, max_files: int) -> List[Path]:
    candidates: List[Path] = []
    seen = set()
    image_path = normalize_path(resolved_image_path, None)
    stems: List[str] = []
    if image_path:
        stems.append(image_path.stem)
        for suffix in OCR_EXTENSIONS:
            for parent in [image_path.parent, image_path.parent.parent if image_path.parent else image_path.parent]:
                if parent:
                    candidate = parent / f"{image_path.stem}{suffix}"
                    if candidate.exists() and candidate.is_file():
                        resolved = candidate.resolve()
                        if resolved not in seen:
                            candidates.append(candidate)
                            seen.add(resolved)
    page_tokens = page_number_tokens(page_id, resolved_image_path)
    if ocr_root and ocr_root.exists():
        scanned = 0
        for path in ocr_root.rglob("*"):
            if scanned >= max_files:
                break
            if not path.is_file() or path.suffix.lower() not in OCR_EXTENSIONS:
                continue
            scanned += 1
            name = path.name.lower()
            if any(token.lower() in name for token in page_tokens + stems):
                resolved = path.resolve()
                if resolved not in seen:
                    candidates.append(path)
                    seen.add(resolved)
    return candidates


def parse_tsv(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
            sample = handle.read(4096)
            handle.seek(0)
            delimiter = "\t" if "\t" in sample else ","
            reader = csv.DictReader(handle, delimiter=delimiter)
            for row in reader:
                text = row.get("text") or row.get("word") or row.get("content") or ""
                box = bbox_from_mapping(row)
                if box and text.strip():
                    records.append({"text": text.strip(), "bbox": box, "ocr_record_type": "tsv_word", "source_file": str(path).replace("\\", "/")})
    except Exception:
        return []
    return records


def strip_tags(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", fragment)
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def parse_hocr(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    pattern = re.compile(r"<(?P<tag>span|div|p)[^>]*title=[\"'][^\"']*bbox\s+(?P<x0>\d+)\s+(?P<y0>\d+)\s+(?P<x1>\d+)\s+(?P<y1>\d+)[^\"']*[\"'][^>]*>(?P<body>.*?)</(?P=tag)>", re.I | re.S)
    for match in pattern.finditer(text):
        word = strip_tags(match.group("body"))
        if not word:
            continue
        box = clamp_bbox(float(match.group("x0")), float(match.group("y0")), float(match.group("x1")), float(match.group("y1")))
        if box:
            records.append({"text": word, "bbox": box, "ocr_record_type": "hocr_bbox", "source_file": str(path).replace("\\", "/")})
    return records


def parse_json_records(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    try:
        if path.suffix.lower() == ".jsonl":
            payloads = [json.loads(line) for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
        else:
            payloads = [json.loads(path.read_text(encoding="utf-8", errors="ignore"))]
    except Exception:
        return []

    def visit(obj: Any) -> None:
        if isinstance(obj, Mapping):
            text = first_present(obj, TEXT_KEYS)
            box = None
            for key in BBOX_KEYS:
                if key in obj:
                    box = bbox_from_value(obj.get(key))
                    if box:
                        break
            if box is None:
                box = bbox_from_mapping(obj)
            if box and text:
                records.append({"text": str(text), "bbox": box, "ocr_record_type": "json_bbox", "source_file": str(path).replace("\\", "/")})
            for child in obj.values():
                visit(child)
        elif isinstance(obj, list):
            for child in obj:
                visit(child)
    for payload in payloads:
        visit(payload)
    return records


def parse_ocr_file(path: Path) -> List[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".tsv":
        return parse_tsv(path)
    if suffix in {".hocr", ".html", ".htm", ".xml"}:
        return parse_hocr(path)
    if suffix in {".json", ".jsonl"}:
        return parse_json_records(path)
    return []


def collect_text_tokens(obj: Any, page_id: Any, table_id: Any, limit: int = 5000) -> List[str]:
    tokens: List[str] = []
    part_numbers: List[str] = []

    def in_scope(mapping: Mapping[str, Any]) -> bool:
        p = mapping.get("page_id") or mapping.get("source_page_id")
        t = mapping.get("table_id") or mapping.get("normalized_table_id")
        page_match = not page_id or not p or p == page_id
        table_match = not table_id or not t or t == table_id
        return page_match and table_match

    def visit(value: Any, depth: int = 0) -> None:
        if len(tokens) >= limit or depth > 30:
            return
        if isinstance(value, Mapping):
            if in_scope(value):
                for key in TEXT_KEYS:
                    raw = value.get(key)
                    if raw:
                        text = normalize_text(raw)
                        if text and len(text) <= 160:
                            tokens.extend(token_key(piece) for piece in re.split(r"\s+", text) if token_key(piece))
                            part_numbers.extend(PART_NUMBER_RE.findall(str(raw)))
            for child in value.values():
                visit(child, depth + 1)
        elif isinstance(value, list):
            for child in value:
                visit(child, depth + 1)
    visit(obj)
    compact = []
    seen = set()
    for token in part_numbers + tokens:
        key = token_key(token)
        if key and len(key) >= 2 and key not in seen:
            compact.append(key)
            seen.add(key)
    return compact[:limit]


def target_tokens_from_card(card: Mapping[str, Any], normalizer_payload: Mapping[str, Any]) -> Tuple[List[str], List[str]]:
    page_id = card.get("page_id")
    table_id = card.get("table_id")
    tokens: List[str] = []
    part_numbers: List[str] = []
    domain = card.get("domain_validation") if isinstance(card.get("domain_validation"), Mapping) else {}
    for value in domain.get("part_numbers_sample") or card.get("part_numbers") or []:
        key = token_key(value)
        if key:
            tokens.append(key)
            part_numbers.append(key)
    collected = collect_text_tokens(normalizer_payload, page_id, table_id)
    tokens.extend(collected)
    # Reduce overbroad noise: keep part numbers plus reasonably informative tokens.
    filtered = []
    seen = set()
    for token in tokens:
        if token in seen:
            continue
        if len(token) >= 4 or PART_NUMBER_RE.search(token):
            filtered.append(token)
            seen.add(token)
    part_unique = []
    seen_part = set()
    for token in part_numbers:
        if token not in seen_part:
            part_unique.append(token)
            seen_part.add(token)
    return filtered[:1000], part_unique[:200]


def match_ocr_records(ocr_records: Sequence[Mapping[str, Any]], target_tokens: Sequence[str], part_tokens: Sequence[str]) -> Tuple[List[Mapping[str, Any]], int]:
    target_set = {token_key(t) for t in target_tokens if token_key(t)}
    part_set = {token_key(t) for t in part_tokens if token_key(t)}
    matches: List[Mapping[str, Any]] = []
    part_hits = 0
    for record in ocr_records:
        text_key = token_key(record.get("text"))
        if not text_key:
            continue
        match_reason = None
        if text_key in part_set or any(part in text_key or text_key in part for part in part_set):
            part_hits += 1
            match_reason = "part_number"
        elif text_key in target_set:
            match_reason = "table_text"
        if match_reason:
            enriched_record = dict(record)
            enriched_record["match_reason"] = match_reason
            matches.append(enriched_record)
    return matches, part_hits


def build_image_resolver_index(payload: Optional[Mapping[str, Any]]) -> Dict[Tuple[Any, Any], Mapping[str, Any]]:
    index: Dict[Tuple[Any, Any], Mapping[str, Any]] = {}
    if not payload:
        return index
    for card in payload.get("table_image_resolution_cards") or []:
        if not isinstance(card, Mapping):
            continue
        index[(card.get("page_id"), card.get("table_id"))] = card
        index[(card.get("page_id"), None)] = card
    return index


def build_bbox_resolver_index(payload: Optional[Mapping[str, Any]]) -> Dict[Tuple[Any, Any], Mapping[str, Any]]:
    index: Dict[Tuple[Any, Any], Mapping[str, Any]] = {}
    if not payload:
        return index
    for card in payload.get("table_bbox_cards") or []:
        if not isinstance(card, Mapping):
            continue
        index[(card.get("page_id"), card.get("table_id"))] = card
        index[(card.get("page_id"), None)] = card
    return index


def valid_crop_candidate(box: Optional[Mapping[str, Any]], width: Optional[int], height: Optional[int]) -> bool:
    if not box or not width or not height:
        return False
    if float(box.get("width") or 0) < 50 or float(box.get("height") or 0) < 30:
        return False
    coverage = bbox_coverage(box, width, height)
    if coverage is None or coverage < 0.0005 or coverage > 0.95:
        return False
    return True


def select_preferred_table_extraction_bbox(
    card: Mapping[str, Any],
    bbox_resolver_card: Optional[Mapping[str, Any]],
    *,
    width: Optional[int],
    height: Optional[int],
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Return a safe upstream table_extraction_bbox candidate when available.

    The bbox exposed by table_line_geometry is the current route-approved table
    crop. This enrichment layer should prefer that explicit crop over a fresh
    OCR-token union, while still retaining OCR-derived fields for audit and
    fallback. The result is advisory crop metadata only.
    """
    diagnostics: Dict[str, Any] = {
        "table_extraction_bbox_available": False,
        "table_extraction_bbox_valid": False,
        "table_extraction_bbox_preferred": False,
        "table_extraction_bbox_source_container": None,
        "table_extraction_bbox_source_key": None,
        "table_extraction_bbox_source": None,
        "table_extraction_bbox_confidence": None,
        "table_extraction_bbox_candidate": None,
        "table_extraction_bbox_rejection_reason": None,
        "table_extraction_bbox_coverage_ratio": None,
    }
    sources: List[Tuple[str, Optional[Mapping[str, Any]]]] = [
        ("table_line_geometry", card),
        ("table_bbox_resolver", bbox_resolver_card),
    ]
    for source_container, source in sources:
        if not isinstance(source, Mapping):
            continue
        for key in EXTRACTION_BBOX_KEYS:
            if key not in source or source.get(key) is None:
                continue
            diagnostics["table_extraction_bbox_available"] = True
            diagnostics["table_extraction_bbox_source_container"] = source_container
            diagnostics["table_extraction_bbox_source_key"] = key
            box = bbox_from_value(source.get(key), width, height)
            diagnostics["table_extraction_bbox_candidate"] = box
            diagnostics["table_extraction_bbox_source"] = first_present(source, EXTRACTION_BBOX_SOURCE_KEYS) or key
            confidence = as_float(first_present(source, EXTRACTION_BBOX_CONFIDENCE_KEYS))
            diagnostics["table_extraction_bbox_confidence"] = confidence
            diagnostics["table_extraction_bbox_coverage_ratio"] = bbox_coverage(box, width, height)
            if not box:
                diagnostics["table_extraction_bbox_rejection_reason"] = "table_extraction_bbox_invalid_or_unparseable"
                return None, diagnostics
            if not valid_crop_candidate(box, width, height):
                diagnostics["table_extraction_bbox_rejection_reason"] = "table_extraction_bbox_not_valid_crop_candidate"
                return None, diagnostics
            diagnostics["table_extraction_bbox_valid"] = True
            diagnostics["table_extraction_bbox_preferred"] = True
            diagnostics["table_extraction_bbox_rejection_reason"] = None
            return box, diagnostics
    diagnostics["table_extraction_bbox_rejection_reason"] = "table_extraction_bbox_not_available"
    return None, diagnostics


def build_enrichment_card(
    card: Mapping[str, Any],
    *,
    normalizer_payload: Mapping[str, Any],
    image_resolver_card: Optional[Mapping[str, Any]],
    bbox_resolver_card: Optional[Mapping[str, Any]],
    ocr_root: Optional[Path],
    image_root: Optional[Path],
    max_ocr_files_scanned: int,
) -> Dict[str, Any]:
    page_id = card.get("page_id")
    table_id = card.get("table_id")
    resolved_image_path = card.get("resolved_image_path") or (image_resolver_card or {}).get("resolved_image_path")
    image_path = normalize_path(resolved_image_path, image_root)
    image_width = card.get("image_width") or (image_resolver_card or {}).get("image_width") or (bbox_resolver_card or {}).get("image_width")
    image_height = card.get("image_height") or (image_resolver_card or {}).get("image_height") or (bbox_resolver_card or {}).get("image_height")
    if not image_width or not image_height:
        width, height = image_dimensions(image_path)
        image_width = image_width or width
        image_height = image_height or height
    image_width = int(image_width) if image_width else None
    image_height = int(image_height) if image_height else None

    ocr_files = find_candidate_ocr_files(ocr_root, resolved_image_path, page_id, max_ocr_files_scanned) if ocr_root else []
    ocr_records: List[Dict[str, Any]] = []
    for path in ocr_files[:50]:
        ocr_records.extend(parse_ocr_file(path))
        if len(ocr_records) > 100_000:
            break

    target_tokens, part_tokens = target_tokens_from_card(card, normalizer_payload)
    matched_records, part_hits = match_ocr_records(ocr_records, target_tokens, part_tokens)
    matched_boxes = [r["bbox"] for r in matched_records if r.get("bbox")]
    raw_inferred = union_bboxes(matched_boxes, pad_ratio=0.045, width=image_width, height=image_height)
    ocr_inferred, content_band_diag = tighten_ocr_bbox_to_content_band(
        matched_records,
        raw_inferred,
        width=image_width,
        height=image_height,
        table_type=card.get("table_type"),
    )

    ocr_bbox_source = "unresolved"
    ocr_confidence = 0.0
    if ocr_inferred and part_hits >= 1:
        ocr_bbox_source = "ocr_part_number_token_match"
        ocr_confidence = min(0.92, 0.72 + min(part_hits, 10) * 0.02)
    elif ocr_inferred and len(matched_records) >= 5:
        ocr_bbox_source = "ocr_table_text_token_match"
        ocr_confidence = min(0.84, 0.58 + min(len(matched_records), 25) * 0.01)
    elif ocr_inferred:
        ocr_bbox_source = "ocr_low_match_token_bbox"
        ocr_confidence = 0.46

    extraction_bbox, extraction_bbox_diag = select_preferred_table_extraction_bbox(
        card,
        bbox_resolver_card,
        width=image_width,
        height=image_height,
    )

    inferred = ocr_inferred
    bbox_source = ocr_bbox_source
    confidence = ocr_confidence
    if extraction_bbox is not None and extraction_bbox_diag.get("table_extraction_bbox_preferred"):
        inferred = extraction_bbox
        bbox_source = "table_extraction_bbox_preferred"
        upstream_confidence = extraction_bbox_diag.get("table_extraction_bbox_confidence")
        confidence = max(0.9, float(upstream_confidence) if upstream_confidence is not None else 0.9)

    crop_ready = valid_crop_candidate(inferred, image_width, image_height)
    ocr_crop_ready = valid_crop_candidate(ocr_inferred, image_width, image_height)
    review_flags: List[str] = []
    recommended_actions: List[str] = []
    if not ocr_files:
        review_flags.append("ocr_bbox_sidecar_not_found")
        recommended_actions.append("provide_or_generate_ocr_bbox_sidecars_for_table_pages")
    elif not ocr_records:
        review_flags.append("ocr_bbox_records_not_parseable")
        recommended_actions.append("inspect_ocr_bbox_sidecar_schema")
    elif not matched_records:
        review_flags.append("ocr_bbox_token_match_not_found")
        recommended_actions.append("improve_table_text_to_ocr_token_matching")
    elif not crop_ready:
        review_flags.append("ocr_bbox_crop_candidate_not_ready")
        recommended_actions.append("confirm_ocr_match_bbox_against_source_page")
    if content_band_diag.get("ocr_content_band_tightening_applied"):
        review_flags.append("ocr_bbox_content_band_tightened")
        recommended_actions.append("verify_tightened_ocr_content_band_against_source_page")
    elif content_band_diag.get("ocr_content_band_tightening_available") and not content_band_diag.get("ocr_content_band_tightening_applied"):
        review_flags.append("ocr_bbox_content_band_tightening_not_applied")
    if extraction_bbox_diag.get("table_extraction_bbox_available") and not extraction_bbox_diag.get("table_extraction_bbox_valid"):
        review_flags.append("table_extraction_bbox_available_but_not_valid")
        recommended_actions.append("inspect_table_extraction_bbox_before_downstream_consumption")
    if extraction_bbox_diag.get("table_extraction_bbox_preferred"):
        recommended_actions.append("use_table_extraction_bbox_for_downstream_table_ocr_crop")
    if bbox_source in {"ocr_low_match_token_bbox", "unresolved"}:
        review_flags.append("ocr_bbox_enrichment_low_confidence")
    if bbox_resolver_card and bbox_resolver_card.get("review_required"):
        review_flags.append("upstream_bbox_resolver_review_required")

    coverage = bbox_coverage(inferred, image_width, image_height)
    return {
        "ocr_bbox_enrichment_card_id": stable_id("table_ocr_bbox", page_id, table_id, bbox_source, len(matched_records), part_hits),
        "schema_version": SCHEMA_VERSION,
        "page_id": page_id,
        "table_id": table_id,
        "table_type": card.get("table_type"),
        "source_geometry_card_id": card.get("geometry_card_id"),
        "resolved_image_path": str(resolved_image_path).replace("\\", "/") if resolved_image_path else None,
        "image_width": image_width,
        "image_height": image_height,
        "ocr_source_file_count": len(ocr_files),
        "ocr_source_files_sample": [str(p).replace("\\", "/") for p in ocr_files[:8]],
        "ocr_bbox_record_count": len(ocr_records),
        "table_target_token_count": len(target_tokens),
        "part_number_target_count": len(part_tokens),
        "matched_ocr_bbox_count": len(matched_records),
        "part_number_ocr_match_count": part_hits,
        "inferred_table_region_bbox": inferred,
        "bbox_source": bbox_source,
        "bbox_confidence": round(confidence, 4),
        "bbox_coverage_ratio": coverage,
        "ocr_inferred_table_region_bbox": ocr_inferred,
        "ocr_bbox_source": ocr_bbox_source,
        "ocr_bbox_confidence": round(ocr_confidence, 4),
        "ocr_crop_candidate_ready": bool(ocr_crop_ready),
        "table_extraction_bbox_candidate": extraction_bbox_diag.get("table_extraction_bbox_candidate"),
        "table_extraction_bbox_available": extraction_bbox_diag.get("table_extraction_bbox_available"),
        "table_extraction_bbox_valid": extraction_bbox_diag.get("table_extraction_bbox_valid"),
        "table_extraction_bbox_preferred": extraction_bbox_diag.get("table_extraction_bbox_preferred"),
        "table_extraction_bbox_source_container": extraction_bbox_diag.get("table_extraction_bbox_source_container"),
        "table_extraction_bbox_source_key": extraction_bbox_diag.get("table_extraction_bbox_source_key"),
        "table_extraction_bbox_source": extraction_bbox_diag.get("table_extraction_bbox_source"),
        "table_extraction_bbox_confidence": extraction_bbox_diag.get("table_extraction_bbox_confidence"),
        "table_extraction_bbox_coverage_ratio": extraction_bbox_diag.get("table_extraction_bbox_coverage_ratio"),
        "table_extraction_bbox_rejection_reason": extraction_bbox_diag.get("table_extraction_bbox_rejection_reason"),
        "bbox_preference_order": ["table_extraction_bbox", "ocr_token_union"],
        "original_inferred_table_region_bbox": content_band_diag.get("ocr_original_inferred_table_region_bbox"),
        "original_bbox_coverage_ratio": content_band_diag.get("ocr_content_band_original_coverage_ratio"),
        "content_band_bbox": content_band_diag.get("ocr_content_band_bbox"),
        "content_band_bbox_coverage_ratio": content_band_diag.get("ocr_content_band_tightened_coverage_ratio"),
        "content_band_tightening_available": content_band_diag.get("ocr_content_band_tightening_available"),
        "content_band_tightening_applied": content_band_diag.get("ocr_content_band_tightening_applied"),
        "content_band_tightening_reason": content_band_diag.get("ocr_content_band_tightening_reason"),
        "content_band_source_record_count": content_band_diag.get("ocr_content_band_source_record_count"),
        "content_band_selected_record_count": content_band_diag.get("ocr_content_band_selected_record_count"),
        "crop_candidate_ready": bool(crop_ready),
        "bbox_resolver_bbox_source": (bbox_resolver_card or {}).get("bbox_source"),
        "bbox_resolver_bbox_confidence": (bbox_resolver_card or {}).get("bbox_confidence"),
        "bbox_resolver_review_required": bool((bbox_resolver_card or {}).get("review_required")),
        "review_required": bool(review_flags),
        "review_flags": sorted(set(review_flags)),
        "recommended_actions": sorted(set(recommended_actions)),
        "retrieval_only": True,
        "routing_only": True,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "retrieval_only_answer_allowed": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
        "can_mutate_source_truth": False,
        "unsafe_ocr_bbox_enrichment_card": False,
    }


def summarize(cards: Sequence[Mapping[str, Any]], source_cards: Sequence[Mapping[str, Any]], source_quality_statuses: Mapping[str, Any], inputs: Mapping[str, Any]) -> Dict[str, Any]:
    def count(pred) -> int:
        return sum(1 for card in cards if pred(card))
    return {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "source_table_geometry_card_count": len(source_cards),
        "ocr_bbox_enrichment_card_count": len(cards),
        "crop_candidate_ready_card_count": count(lambda c: c.get("crop_candidate_ready")),
        "table_extraction_bbox_available_card_count": count(lambda c: c.get("table_extraction_bbox_available")),
        "table_extraction_bbox_valid_card_count": count(lambda c: c.get("table_extraction_bbox_valid")),
        "table_extraction_bbox_preferred_card_count": count(lambda c: c.get("table_extraction_bbox_preferred")),
        "table_extraction_bbox_consumed_card_count": count(lambda c: c.get("table_extraction_bbox_preferred")),
        "ocr_fallback_used_card_count": count(lambda c: not c.get("table_extraction_bbox_preferred") and c.get("ocr_crop_candidate_ready")),
        "content_band_tightening_available_card_count": count(lambda c: c.get("content_band_tightening_available")),
        "content_band_tightening_applied_card_count": count(lambda c: c.get("content_band_tightening_applied")),
        "broad_ocr_bbox_card_count": count(lambda c: (c.get("original_bbox_coverage_ratio") or 0) > 0.75),
        "tightened_ocr_bbox_card_count": count(lambda c: c.get("content_band_tightening_applied") and (c.get("bbox_coverage_ratio") or 1) < (c.get("original_bbox_coverage_ratio") or 0)),
        "ocr_source_file_card_count": count(lambda c: int(c.get("ocr_source_file_count") or 0) > 0),
        "ocr_bbox_record_card_count": count(lambda c: int(c.get("ocr_bbox_record_count") or 0) > 0),
        "matched_ocr_bbox_card_count": count(lambda c: int(c.get("matched_ocr_bbox_count") or 0) > 0),
        "part_number_ocr_match_card_count": count(lambda c: int(c.get("part_number_ocr_match_count") or 0) > 0),
        "unresolved_ocr_bbox_card_count": count(lambda c: not c.get("crop_candidate_ready")),
        "review_required_card_count": count(lambda c: c.get("review_required")),
        "unsafe_ocr_bbox_enrichment_card_count": count(lambda c: c.get("unsafe_ocr_bbox_enrichment_card")),
        "answer_permission_count": count(lambda c: c.get("answer_permission") or c.get("can_answer_directly") or c.get("can_prove_claims")),
        "can_answer_directly_count": count(lambda c: c.get("can_answer_directly")),
        "can_prove_claims_count": count(lambda c: c.get("can_prove_claims")),
        "retrieval_only_answer_allowed_count": count(lambda c: c.get("retrieval_only_answer_allowed")),
        "source_truth_mutation_allowed_count": count(lambda c: c.get("source_truth_mutation_allowed") or c.get("can_mutate_source_truth")),
        "source_truth_mutations_performed": sum(int(c.get("source_truth_mutations_performed") or 0) for c in cards),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "source_quality_statuses": dict(source_quality_statuses),
        "ocr_root": str(inputs.get("ocr_root")) if inputs.get("ocr_root") else None,
        "image_root": str(inputs.get("image_root")) if inputs.get("image_root") else None,
    }


def evaluate_quality(summary: Mapping[str, Any], thresholds: Mapping[str, Any]) -> Tuple[str, List[str]]:
    failures: List[str] = []
    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    require(summary.get("source_table_geometry_card_count", 0) >= thresholds.get("min_source_cards", 1), "min_source_cards_not_met")
    require(summary.get("ocr_bbox_enrichment_card_count", 0) >= thresholds.get("min_enrichment_cards", 1), "min_enrichment_cards_not_met")
    require(summary.get("crop_candidate_ready_card_count", 0) >= thresholds.get("min_crop_candidate_cards", 0), "min_crop_candidate_cards_not_met")
    require(summary.get("unsafe_ocr_bbox_enrichment_card_count", 0) <= thresholds.get("max_unsafe_enrichment_cards", 0), "unsafe_enrichment_cards_exceeded")
    require(summary.get("answer_permission_count", 0) <= thresholds.get("max_answer_permission_count", 0), "answer_permission_count_exceeded")
    require(summary.get("source_truth_mutation_allowed_count", 0) <= thresholds.get("max_source_truth_mutation_allowed", 0), "source_truth_mutation_allowed_exceeded")
    if thresholds.get("require_table_line_geometry_quality_pass"):
        require(summary.get("source_quality_statuses", {}).get("table_line_geometry") == "PASS", "table_line_geometry_quality_not_pass")
    if thresholds.get("require_table_image_resolver_quality_pass"):
        require(summary.get("source_quality_statuses", {}).get("table_image_resolver") == "PASS", "table_image_resolver_quality_not_pass")
    if thresholds.get("require_table_bbox_resolver_quality_pass"):
        require(summary.get("source_quality_statuses", {}).get("table_bbox_resolver") == "PASS", "table_bbox_resolver_quality_not_pass")
    if thresholds.get("require_no_answer_permission"):
        require(summary.get("answer_permission_count", 0) == 0, "answer_permission_not_zero")
        require(summary.get("can_answer_directly_count", 0) == 0, "can_answer_directly_not_zero")
        require(summary.get("can_prove_claims_count", 0) == 0, "can_prove_claims_not_zero")
    return ("PASS" if not failures else "FAIL"), failures


def build_report(
    *,
    table_line_geometry_path: Path,
    table_cell_normalizer_path: Path,
    table_image_resolver_path: Optional[Path],
    table_bbox_resolver_path: Optional[Path],
    ocr_root: Optional[Path],
    image_root: Optional[Path],
    output_dir: Path,
    max_ocr_files_scanned: int,
    thresholds: Mapping[str, Any],
) -> Dict[str, Any]:
    table_line_geometry = load_json(table_line_geometry_path)
    normalizer = load_json(table_cell_normalizer_path)
    image_resolver = load_json(table_image_resolver_path) if table_image_resolver_path and table_image_resolver_path.exists() else None
    bbox_resolver = load_json(table_bbox_resolver_path) if table_bbox_resolver_path and table_bbox_resolver_path.exists() else None

    source_cards = table_line_geometry.get("table_geometry_cards") or []
    image_index = build_image_resolver_index(image_resolver)
    bbox_index = build_bbox_resolver_index(bbox_resolver)
    source_quality_statuses = {
        "table_line_geometry": table_line_geometry.get("quality_status"),
        "table_cell_normalizer": normalizer.get("quality_status"),
        "table_image_resolver": (image_resolver or {}).get("quality_status"),
        "table_bbox_resolver": (bbox_resolver or {}).get("quality_status"),
    }

    cards = []
    for card in source_cards:
        if not isinstance(card, Mapping):
            continue
        key = (card.get("page_id"), card.get("table_id"))
        image_card = image_index.get(key) or image_index.get((card.get("page_id"), None))
        bbox_card = bbox_index.get(key) or bbox_index.get((card.get("page_id"), None))
        cards.append(build_enrichment_card(
            card,
            normalizer_payload=normalizer,
            image_resolver_card=image_card,
            bbox_resolver_card=bbox_card,
            ocr_root=ocr_root,
            image_root=image_root,
            max_ocr_files_scanned=max_ocr_files_scanned,
        ))

    summary = summarize(cards, source_cards, source_quality_statuses, {"ocr_root": ocr_root, "image_root": image_root})
    quality_status, fail_reasons = evaluate_quality(summary, thresholds)
    summary["quality_status"] = quality_status
    summary["quality_fail_reasons"] = fail_reasons
    status = STATUS_BUILT if quality_status == "PASS" else STATUS_NOT_READY
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "quality_status": quality_status,
        "generated_at": utc_now(),
        "inputs": {
            "table_line_geometry": str(table_line_geometry_path),
            "table_cell_normalizer": str(table_cell_normalizer_path),
            "table_image_resolver": str(table_image_resolver_path) if table_image_resolver_path else None,
            "table_bbox_resolver": str(table_bbox_resolver_path) if table_bbox_resolver_path else None,
            "ocr_root": str(ocr_root) if ocr_root else None,
            "image_root": str(image_root) if image_root else None,
        },
        "summary": summary,
        "table_ocr_bbox_enrichment_cards": cards,
        "safety_contract": {
            "read_only": True,
            "no_postgres_writes": True,
            "no_qdrant_writes": True,
            "no_opensearch_writes": True,
            "no_source_truth_mutation": True,
            "no_answer_permission": True,
            "no_claim_proof_authority": True,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_table_ocr_bbox_enrichment_v1.json"
    write_json(report_path, report)
    write_jsonl(output_dir / "trace_net_table_ocr_bbox_enrichment_v1_cards.jsonl", cards)
    write_json(output_dir / "trace_net_table_ocr_bbox_enrichment_v1_summary.json", summary)
    quality_payload = build_quality_payload(report, thresholds)
    write_json(output_dir / "trace_net_table_ocr_bbox_enrichment_v1_quality.json", quality_payload)
    write_json(output_dir / "trace_net_table_ocr_bbox_enrichment_v1_manifest.json", {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": report["generated_at"],
        "report_path": str(report_path),
        "quality_path": str(output_dir / "trace_net_table_ocr_bbox_enrichment_v1_quality.json"),
        "quality_status": quality_status,
    })
    return report


def build_quality_payload(report: Mapping[str, Any], thresholds: Mapping[str, Any]) -> Dict[str, Any]:
    summary = report.get("summary") or {}
    quality_status, fail_reasons = evaluate_quality(summary, thresholds)
    checks = {
        "schema_version_ok": report.get("schema_version") == SCHEMA_VERSION,
        "min_source_cards_met": summary.get("source_table_geometry_card_count", 0) >= thresholds.get("min_source_cards", 1),
        "min_enrichment_cards_met": summary.get("ocr_bbox_enrichment_card_count", 0) >= thresholds.get("min_enrichment_cards", 1),
        "min_crop_candidate_cards_met": summary.get("crop_candidate_ready_card_count", 0) >= thresholds.get("min_crop_candidate_cards", 0),
        "unsafe_cards_within_limit": summary.get("unsafe_ocr_bbox_enrichment_card_count", 0) <= thresholds.get("max_unsafe_enrichment_cards", 0),
        "answer_permission_zero": summary.get("answer_permission_count", 0) == 0,
        "can_answer_directly_zero": summary.get("can_answer_directly_count", 0) == 0,
        "can_prove_claims_zero": summary.get("can_prove_claims_count", 0) == 0,
        "source_truth_mutation_allowed_zero": summary.get("source_truth_mutation_allowed_count", 0) == 0,
        "write_attempts_zero": summary.get("postgres_write_attempt_count", 0) == 0 and summary.get("qdrant_write_attempt_count", 0) == 0 and summary.get("opensearch_write_attempt_count", 0) == 0,
    }
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "status": quality_status,
        "quality_status": quality_status,
        "generated_at": utc_now(),
        "summary": summary,
        "checks": checks,
        "quality_errors": fail_reasons,
    }


def thresholds_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "min_source_cards": args.min_source_cards,
        "min_enrichment_cards": args.min_enrichment_cards,
        "min_crop_candidate_cards": args.min_crop_candidate_cards,
        "max_unsafe_enrichment_cards": args.max_unsafe_enrichment_cards,
        "max_answer_permission_count": args.max_answer_permission_count,
        "max_source_truth_mutation_allowed": args.max_source_truth_mutation_allowed,
        "require_table_line_geometry_quality_pass": args.require_table_line_geometry_quality_pass,
        "require_table_image_resolver_quality_pass": args.require_table_image_resolver_quality_pass,
        "require_table_bbox_resolver_quality_pass": args.require_table_bbox_resolver_quality_pass,
        "require_no_answer_permission": args.require_no_answer_permission,
    }


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-source-cards", type=int, default=1)
    parser.add_argument("--min-enrichment-cards", type=int, default=1)
    parser.add_argument("--min-crop-candidate-cards", type=int, default=0)
    parser.add_argument("--max-unsafe-enrichment-cards", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-line-geometry-quality-pass", action="store_true")
    parser.add_argument("--require-table-image-resolver-quality-pass", action="store_true")
    parser.add_argument("--require-table-bbox-resolver-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Table OCR BBox Enrichment v1")
    parser.add_argument("--table-line-geometry", required=True, type=Path)
    parser.add_argument("--table-cell-normalizer", required=True, type=Path)
    parser.add_argument("--table-image-resolver", type=Path)
    parser.add_argument("--table-bbox-resolver", type=Path)
    parser.add_argument("--ocr-root", type=Path, default=Path("local_data/ocr"))
    parser.add_argument("--image-root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-ocr-files-scanned", type=int, default=25000)
    parser.add_argument("--quality", action="store_true")
    add_common_args(parser)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report(
        table_line_geometry_path=args.table_line_geometry,
        table_cell_normalizer_path=args.table_cell_normalizer,
        table_image_resolver_path=args.table_image_resolver,
        table_bbox_resolver_path=args.table_bbox_resolver,
        ocr_root=args.ocr_root,
        image_root=args.image_root,
        output_dir=args.output_dir,
        max_ocr_files_scanned=args.max_ocr_files_scanned,
        thresholds=thresholds_from_args(args),
    )
    summary = report["summary"]
    print("TRACE-Net Table OCR BBox Enrichment v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {report['quality_status']}")
    for key in [
        "source_table_geometry_card_count", "ocr_bbox_enrichment_card_count", "ocr_source_file_card_count",
        "ocr_bbox_record_card_count", "matched_ocr_bbox_card_count", "part_number_ocr_match_card_count",
        "crop_candidate_ready_card_count", "table_extraction_bbox_available_card_count", "table_extraction_bbox_valid_card_count",
        "table_extraction_bbox_preferred_card_count", "table_extraction_bbox_consumed_card_count", "ocr_fallback_used_card_count",
        "content_band_tightening_available_card_count", "content_band_tightening_applied_card_count",
        "broad_ocr_bbox_card_count", "tightened_ocr_bbox_card_count", "review_required_card_count", "unsafe_ocr_bbox_enrichment_card_count",
        "answer_permission_count", "can_answer_directly_count", "can_prove_claims_count",
        "source_truth_mutation_allowed_count", "postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {args.output_dir / 'trace_net_table_ocr_bbox_enrichment_v1.json'}")
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
