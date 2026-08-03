"""TRACE-Net Table Route Cell Extractor v1.

Read-only first-pass table-route data extraction stage for TRACE-Net.

This module consumes the current step-0 full-page table bbox artifact and
attempts to build auditable row/cell/value records from OCR token geometry. It
is intentionally conservative:

- only records with ``full_table_enclosure_bbox_ready`` are processed;
- records marked ``table_bbox_review_only`` are skipped;
- OCR sidecars are parsed locally from enrichment metadata and/or ``--ocr-root``;
- rows and cells are derived from token geometry inside ``final_table_bbox``;
- legacy scoped-cell records may be used only as an explicit fallback;
- output is retrieval/evidence input only and grants no answer authority.

Safety contract:
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no direct answer permission
- no claim-proof authority
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

SCHEMA_VERSION = "trace_net_table_route_cell_extractor_v1"
QUALITY_SCHEMA_VERSION = "trace_net_table_route_cell_extractor_v1_quality"
STATUS_BUILT = "TABLE_ROUTE_CELL_EXTRACTOR_BUILT"
STATUS_NOT_READY = "TABLE_ROUTE_CELL_EXTRACTOR_NOT_READY"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/table_route_cell_extractor")

OCR_EXTENSIONS = {".tsv", ".json", ".jsonl", ".hocr", ".html", ".htm", ".xml"}
RAW_OCR_EXTENSIONS = {".tsv", ".csv", ".hocr", ".html", ".htm", ".xml"}
DERIVED_OCR_NAME_RE = re.compile(r"(?:part[_-]?number[_-]?matches|matches|match[_-]?card|candidate|enrichment|bbox[_-]?record)", re.I)
RAW_OCR_NAME_RE = re.compile(r"(?:\.tsv$|\.csv$|hocr|ocr[_-]?tokens|ocr[_-]?words|zip[_-]?page)", re.I)
LINE_OCR_NAME_RE = re.compile(r"(?:ocr[_-]?lines|line[_-]?ocr|_lines\.jsonl$|lines\.jsonl$)", re.I)
TOKEN_LEVEL_OCR_NAME_RE = re.compile(r"(?:\.tsv$|\.csv$|hocr|ocr[_-]?tokens|ocr[_-]?words|word[_-]?boxes|zip[_-]?page)", re.I)
PAGE_TOKEN_RE = re.compile(r"p(\d{6})|page[_-]?(\d{6})|zip_page[_-]?(\d{6})", re.I)
PART_NUMBER_RE = re.compile(r"\b\d{2,4}-\d{2,6}(?:-[A-Z0-9]{1,5})?\b", re.I)
FIG_ITEM_RE = re.compile(r"\b(?:fig(?:ure)?\.?|item|ipl|ipc)\b", re.I)
HEADER_WORDS = {
    "fig", "figure", "item", "part", "number", "partnumber", "nomenclature", "units", "assy",
    "effectivity", "date", "rev", "revision", "page", "qty", "description", "code", "serial",
}
NON_TABLE_FURNITURE_WORDS = {
    "honeywell", "copyright", "proprietary", "confidential", "chapter", "section", "subject",
}

TEMPLATE_UNKNOWN = "unknown_table_template"
TEMPLATE_GENERIC = "generic_table"
TEMPLATE_LIST_EFFECTIVE_PAGES = "list_of_effective_pages"
TEMPLATE_PART_NUMBER_COVERAGE = "part_number_coverage_list"
TEMPLATE_IPL_SPLIT_COLUMN = "ipl_split_column_table"
LEP_COMPACT_HINTS = ("listofeffectivepages", "effectivepages", "loep")
PART_LIST_COMPACT_HINTS = ("thispublicationcoversthefollowingpartnumbers", "followingpartnumbers")
IPL_COMPACT_HINTS = ("nomenclature", "unitsperassy", "figitem", "figureitem")

SAFETY_FALSE_KEYS = (
    "answer_permission",
    "can_answer_directly",
    "can_prove_claims",
    "final_answer_allowed",
    "llm_freeform_answer_allowed",
    "source_truth_mutation_allowed",
    "can_mutate_source_truth",
    "postgres_write_attempted",
    "qdrant_write_attempted",
    "opensearch_write_attempted",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_id(prefix: str, *parts: Any, length: int = 14) -> str:
    data = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(data.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}__{digest}"


def read_json(path: str | Path | None, default: Any = None) -> Any:
    if not path:
        return default
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(dict(record), sort_keys=True, ensure_ascii=False) + "\n")


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def as_int(value: Any, default: int = 0) -> int:
    if value is None or isinstance(value, bool):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", html.unescape(str(value)).strip())


def compact_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9-]+", "", normalize_text(value).lower())


def payload_quality_status(payload: Any) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    quality = payload.get("quality")
    if isinstance(quality, Mapping) and quality.get("status"):
        return str(quality.get("status"))
    if payload.get("quality_status"):
        return str(payload.get("quality_status"))
    if payload.get("status") in {"PASS", "FAIL"}:
        return str(payload.get("status"))
    return None


def normalize_bbox(value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        if all(k in value for k in ("x0", "y0", "x1", "y1")):
            x0, y0, x1, y1 = (as_float(value.get(k)) for k in ("x0", "y0", "x1", "y1"))
        elif all(k in value for k in ("left", "top", "right", "bottom")):
            x0, y0, x1, y1 = (as_float(value.get(k)) for k in ("left", "top", "right", "bottom"))
        elif all(k in value for k in ("x", "y", "width", "height")):
            x = as_float(value.get("x")); y = as_float(value.get("y")); w = as_float(value.get("width")); h = as_float(value.get("height"))
            if x is None or y is None or w is None or h is None:
                return None
            x0, y0, x1, y1 = x, y, x + w, y + h
        else:
            return None
        coord = str(value.get("coordinate_system") or "pixels")
    elif isinstance(value, (list, tuple)) and len(value) >= 4:
        x0, y0, x1, y1 = (as_float(v) for v in value[:4])
        coord = "pixels"
    else:
        return None
    if None in (x0, y0, x1, y1):
        return None
    assert x0 is not None and y0 is not None and x1 is not None and y1 is not None
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    width = x1 - x0
    height = y1 - y0
    if width <= 1 or height <= 1:
        return None
    return {
        "x0": round(x0, 3), "y0": round(y0, 3), "x1": round(x1, 3), "y1": round(y1, 3),
        "width": round(width, 3), "height": round(height, 3), "coordinate_system": coord,
    }


def bbox_center(box: Mapping[str, Any]) -> tuple[float, float]:
    return (float(box["x0"]) + float(box["x1"])) / 2.0, (float(box["y0"]) + float(box["y1"])) / 2.0


def bbox_inside(inner: Mapping[str, Any], outer: Mapping[str, Any], *, tolerance: float = 2.0) -> bool:
    cx, cy = bbox_center(inner)
    return (
        cx >= float(outer["x0"]) - tolerance
        and cx <= float(outer["x1"]) + tolerance
        and cy >= float(outer["y0"]) - tolerance
        and cy <= float(outer["y1"]) + tolerance
    )


def union_bboxes(boxes: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    valid = [normalize_bbox(b) for b in boxes]
    valid = [b for b in valid if b]
    if not valid:
        return None
    x0 = min(float(b["x0"]) for b in valid)
    y0 = min(float(b["y0"]) for b in valid)
    x1 = max(float(b["x1"]) for b in valid)
    y1 = max(float(b["y1"]) for b in valid)
    return normalize_bbox({"x0": x0, "y0": y0, "x1": x1, "y1": y1})


def page_token(page_id: Any) -> str | None:
    text = str(page_id or "")
    match = PAGE_TOKEN_RE.search(text)
    if not match:
        return None
    number = next((g for g in match.groups() if g), None)
    return f"p{number}" if number else None


def load_reconstructor_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, Mapping):
        return []
    for key in ("table_full_enclosure_bbox_reconstructor_records", "records", "reconstructor_records"):
        value = payload.get(key)
        if isinstance(value, list):
            return [r for r in value if isinstance(r, dict)]
    return []


def load_enrichment_cards(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, Mapping):
        return []
    for key in ("table_ocr_bbox_enrichment_cards", "records", "cards", "bbox_enrichment_cards"):
        value = payload.get(key)
        if isinstance(value, list):
            return [r for r in value if isinstance(r, dict)]
    return []


def load_scoped_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, Mapping):
        return []
    for key in ("scoped_table_records", "records", "table_bbox_scoped_cell_extraction_records"):
        value = payload.get(key)
        if isinstance(value, list):
            return [r for r in value if isinstance(r, dict)]
    return []


def build_index_by_page_and_table(records: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Mapping[str, Any]], dict[str, list[Mapping[str, Any]]]]:
    by_table: dict[str, Mapping[str, Any]] = {}
    by_page: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        table_id = str(record.get("table_id") or "")
        page_id = str(record.get("page_id") or "")
        if table_id:
            by_table[table_id] = record
        if page_id:
            by_page[page_id].append(record)
    return by_table, by_page


def match_aux_record(record: Mapping[str, Any], by_table: Mapping[str, Mapping[str, Any]], by_page: Mapping[str, list[Mapping[str, Any]]]) -> Mapping[str, Any] | None:
    table_id = str(record.get("table_id") or "")
    page_id = str(record.get("page_id") or "")
    if table_id and table_id in by_table:
        return by_table[table_id]
    page_records = by_page.get(page_id) or []
    if len(page_records) == 1:
        return page_records[0]
    if page_records:
        return page_records[0]
    return None


def normalize_ocr_bbox(mapping: Mapping[str, Any]) -> dict[str, Any] | None:
    box = None
    for key in ("bbox", "bounding_box", "bounds", "box", "ocr_bbox", "word_bbox", "text_bbox"):
        if key in mapping:
            box = normalize_bbox(mapping.get(key))
            if box:
                return box
    box = normalize_bbox(mapping)
    if box:
        return box
    return None


def text_from_ocr_mapping(mapping: Mapping[str, Any]) -> str:
    for key in ("text", "word", "content", "value", "line_text", "normalized_text"):
        if key in mapping and normalize_text(mapping.get(key)):
            return normalize_text(mapping.get(key))
    return ""


def parse_json_ocr(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path, default=None)
    records: list[dict[str, Any]] = []

    def visit(obj: Any) -> None:
        if isinstance(obj, Mapping):
            text = text_from_ocr_mapping(obj)
            box = normalize_ocr_bbox(obj)
            if text and box:
                records.append({"text": text, "bbox": box, "source_path": str(path)})
            for key in ("words", "tokens", "lines", "blocks", "pages", "records", "ocr_records", "items"):
                if key in obj:
                    visit(obj.get(key))
        elif isinstance(obj, list):
            for item in obj:
                visit(item)

    visit(payload)
    return records


def parse_jsonl_ocr(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, Mapping):
                text = text_from_ocr_mapping(obj)
                box = normalize_ocr_bbox(obj)
                if text and box:
                    records.append({"text": text, "bbox": box, "source_path": str(path)})
    return records


def parse_tsv_ocr(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        delimiter = "\t" if "\t" in sample else ","
        reader = csv.DictReader(handle, delimiter=delimiter)
        for row in reader:
            text = normalize_text(row.get("text") or row.get("word") or row.get("value"))
            if not text:
                continue
            left = as_float(row.get("left") or row.get("x0") or row.get("x"))
            top = as_float(row.get("top") or row.get("y0") or row.get("y"))
            width = as_float(row.get("width") or row.get("w"))
            height = as_float(row.get("height") or row.get("h"))
            right = as_float(row.get("right") or row.get("x1"))
            bottom = as_float(row.get("bottom") or row.get("y1"))
            if left is not None and top is not None and width is not None and height is not None:
                box = normalize_bbox({"x0": left, "y0": top, "x1": left + width, "y1": top + height})
            elif left is not None and top is not None and right is not None and bottom is not None:
                box = normalize_bbox({"x0": left, "y0": top, "x1": right, "y1": bottom})
            else:
                box = None
            if box:
                records.append({"text": text, "bbox": box, "source_path": str(path)})
    return records


def parse_hocr(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    records: list[dict[str, Any]] = []
    # Typical hOCR: <span class='ocrx_word' title='bbox 12 34 56 78; x_wconf 91'>text</span>
    pattern = re.compile(r"<[^>]+title=[\"'][^\"']*bbox\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)[^\"']*[\"'][^>]*>(.*?)</[^>]+>", re.I | re.S)
    for match in pattern.finditer(text):
        x0, y0, x1, y1 = (float(v) for v in match.groups()[:4])
        raw = re.sub(r"<[^>]+>", " ", match.group(5))
        value = normalize_text(raw)
        if not value:
            continue
        box = normalize_bbox({"x0": x0, "y0": y0, "x1": x1, "y1": y1})
        if box:
            records.append({"text": value, "bbox": box, "source_path": str(path)})
    return records


def parse_ocr_file(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    try:
        if suffix == ".jsonl":
            return parse_jsonl_ocr(path)
        if suffix == ".json":
            return parse_json_ocr(path)
        if suffix == ".tsv" or suffix == ".csv":
            return parse_tsv_ocr(path)
        if suffix in {".hocr", ".html", ".htm", ".xml"}:
            return parse_hocr(path)
    except Exception:
        return []
    return []


def normalize_existing_path(raw: Any, root: Path | None = None) -> Path | None:
    if not raw:
        return None
    value = str(raw).strip().replace("\\", "/")
    if not value:
        return None
    p = Path(value)
    if p.exists():
        return p
    if root:
        candidate = root / value
        if candidate.exists():
            return candidate
        basename = Path(value).name
        if basename:
            direct = root / basename
            if direct.exists():
                return direct
    return None


def find_ocr_files(enrichment_card: Mapping[str, Any] | None, page_id: Any, ocr_root: Path | None, max_files: int) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for raw in as_list((enrichment_card or {}).get("ocr_source_files_sample")):
        p = normalize_existing_path(raw, ocr_root)
        if p and p.suffix.lower() in OCR_EXTENSIONS and str(p) not in seen:
            out.append(p); seen.add(str(p))
    if out:
        return out[:max_files]
    token = page_token(page_id)
    if ocr_root and ocr_root.exists() and token:
        token_lower = token.lower()
        for p in ocr_root.rglob("*"):
            if len(out) >= max_files:
                break
            if not p.is_file() or p.suffix.lower() not in OCR_EXTENSIONS:
                continue
            name = p.name.lower().replace("-", "_")
            if token_lower in name or token_lower.replace("p", "page_") in name:
                if str(p) not in seen:
                    out.append(p); seen.add(str(p))
    return out[:max_files]


def token_signature(token: Mapping[str, Any]) -> tuple[str, int, int, int, int]:
    box = token.get("bbox") or {}
    text = compact_text(token.get("text"))
    # OCR sidecars often repeat the same page/crop pass with tiny coordinate drift.
    # Quantize box coordinates so repeated tokens from overlapping sidecars collapse.
    return (
        text,
        int(round(float(box.get("x0") or 0) / 3.0)),
        int(round(float(box.get("y0") or 0) / 3.0)),
        int(round(float(box.get("x1") or 0) / 3.0)),
        int(round(float(box.get("y1") or 0) / 3.0)),
    )


def dedupe_ocr_tokens(tokens: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    seen: set[tuple[str, int, int, int, int]] = set()
    out: list[dict[str, Any]] = []
    removed = 0
    for token in tokens:
        sig = token_signature(token)
        if sig[0] and sig in seen:
            removed += 1
            continue
        seen.add(sig)
        out.append(dict(token))
    return out, removed



def classify_ocr_source_file(path: Path | str | None) -> str:
    """Classify OCR sidecars as raw OCR or derived matcher outputs.

    Derived matcher files often contain repeated row-level match text projected
    onto several boxes. They are useful evidence, but poor primary input for
    row/cell reconstruction. Prefer TSV/hOCR/raw OCR when it has enough table
    signal; fall back to derived files only when raw OCR is unavailable/weak.
    """
    if path is None:
        return "unknown"
    p = Path(str(path))
    name = p.name.lower()
    if DERIVED_OCR_NAME_RE.search(name):
        return "derived_match_sidecar"
    if p.suffix.lower() in RAW_OCR_EXTENSIONS or RAW_OCR_NAME_RE.search(name):
        return "raw_ocr_sidecar"
    return "unknown"


def classify_ocr_source_detail(path: Path | str | None) -> str:
    """Return a finer-grained OCR source type for selection diagnostics.

    The table extractor needs word/token geometry for row and cell splitting.
    Line-level OCR sidecars are useful fallback evidence, but they collapse a
    whole text row into one box and produce sparse cells. Prefer token-level raw
    OCR such as TSV/CSV/hOCR/word sidecars whenever available.
    """
    if path is None:
        return "unknown"
    p = Path(str(path))
    name = p.name.lower()
    if DERIVED_OCR_NAME_RE.search(name):
        return "derived_match_sidecar"
    if LINE_OCR_NAME_RE.search(name):
        return "raw_line_ocr_sidecar"
    if p.suffix.lower() in {".tsv", ".csv"}:
        return "raw_tsv_word_ocr_sidecar"
    if p.suffix.lower() in {".hocr", ".html", ".htm", ".xml"}:
        return "raw_hocr_word_ocr_sidecar"
    if TOKEN_LEVEL_OCR_NAME_RE.search(name):
        return "raw_token_ocr_sidecar"
    if p.suffix.lower() in RAW_OCR_EXTENSIONS or RAW_OCR_NAME_RE.search(name):
        return "raw_unknown_granularity_ocr_sidecar"
    return "unknown"


def ocr_source_is_usable_raw(score: Mapping[str, Any]) -> bool:
    return (
        score.get("ocr_source_kind") == "raw_ocr_sidecar"
        and as_int(score.get("token_count_inside_bbox"), 0) >= 20
        and as_int(score.get("candidate_line_count"), 0) >= 3
    )


def ocr_source_is_usable_token_level_raw(score: Mapping[str, Any]) -> bool:
    return (
        ocr_source_is_usable_raw(score)
        and score.get("ocr_source_detail")
        in {
            "raw_tsv_word_ocr_sidecar",
            "raw_hocr_word_ocr_sidecar",
            "raw_token_ocr_sidecar",
            "raw_unknown_granularity_ocr_sidecar",
        }
    )

def score_ocr_tokens_for_table(tokens: Sequence[Mapping[str, Any]], final_bbox: Mapping[str, Any] | None = None, source_path: Path | str | None = None) -> dict[str, Any]:
    scoped = [t for t in tokens if isinstance(t.get("bbox"), Mapping) and (not final_bbox or bbox_inside(t.get("bbox"), final_bbox))]
    texts = [normalize_text(t.get("text")) for t in scoped if normalize_text(t.get("text"))]
    joined = " ".join(texts)
    compact = compact_text(joined)
    part_count = len(PART_NUMBER_RE.findall(joined))
    header_hits = sum(1 for word in HEADER_WORDS if word in compact)
    lines = group_tokens_into_lines(scoped) if scoped else []
    candidate_lines = filter_candidate_lines(lines) if lines else []
    unique_texts = {compact_text(t) for t in texts if compact_text(t)}
    unique_ratio = (len(unique_texts) / len(texts)) if texts else 0.0
    source_kind = classify_ocr_source_file(source_path)
    source_detail = classify_ocr_source_detail(source_path)
    # Prefer true/raw OCR sidecars over derived matcher sidecars. The matcher
    # sidecars are usually high in part-number evidence, but can repeat an
    # entire matched row into several boxes, causing duplicated cells. Among
    # raw OCR sidecars, prefer token/word-level TSV/hOCR over line-level JSONL
    # because row/cell reconstruction needs word geometry, not only line boxes.
    raw_bonus = 85.0 if source_kind == "raw_ocr_sidecar" else 0.0
    token_level_bonus = 95.0 if source_detail in {"raw_tsv_word_ocr_sidecar", "raw_hocr_word_ocr_sidecar", "raw_token_ocr_sidecar"} else 0.0
    line_level_penalty = 70.0 if source_detail == "raw_line_ocr_sidecar" else 0.0
    derived_penalty = 0.45 if source_kind == "derived_match_sidecar" else 1.0
    repeated_text_penalty = 0.0
    if texts:
        counts = Counter(compact_text(t) for t in texts if compact_text(t))
        repeated_text_penalty = min(120.0, sum(max(0, count - 1) for count in counts.values()) * 3.0)
    base_score = (
        min(len(scoped), 3000) * 0.05
        + min(len(candidate_lines), 250) * 1.75
        + min(part_count, 200) * 2.0
        + min(header_hits, 12) * 3.0
        + unique_ratio * 25.0
        + raw_bonus
        + token_level_bonus
        - line_level_penalty
        - repeated_text_penalty
    )
    score = max(0.0, base_score * derived_penalty)
    return {
        "score": round(score, 3),
        "ocr_source_kind": source_kind,
        "ocr_source_detail": source_detail,
        "token_count": len(tokens),
        "token_count_inside_bbox": len(scoped),
        "line_count_inside_bbox": len(lines),
        "candidate_line_count": len(candidate_lines),
        "part_number_count": part_count,
        "header_hit_count": header_hits,
        "unique_text_ratio": round(unique_ratio, 4),
        "raw_ocr_bonus_applied": bool(raw_bonus),
        "token_level_ocr_bonus_applied": bool(token_level_bonus),
        "line_level_ocr_penalty_applied": bool(line_level_penalty),
        "derived_match_sidecar_penalty_applied": source_kind == "derived_match_sidecar",
        "repeated_text_penalty": round(repeated_text_penalty, 3),
    }

def load_ocr_tokens(
    enrichment_card: Mapping[str, Any] | None,
    page_id: Any,
    ocr_root: Path | None,
    max_files: int,
    *,
    final_bbox: Mapping[str, Any] | None = None,
    ocr_file_selection: str = "best",
    deduplicate_tokens: bool = True,
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    files = find_ocr_files(enrichment_card, page_id, ocr_root, max_files)
    parsed: list[tuple[Path, list[dict[str, Any]], dict[str, Any]]] = []
    for path in files:
        file_tokens = parse_ocr_file(path)
        if not file_tokens:
            continue
        parsed.append((path, file_tokens, score_ocr_tokens_for_table(file_tokens, final_bbox, path)))

    selected = parsed
    selection_reason = "all_candidate_ocr_files"
    raw_candidates = [item for item in parsed if ocr_source_is_usable_raw(item[2])]
    token_level_raw_candidates = [item for item in parsed if ocr_source_is_usable_token_level_raw(item[2])]
    if ocr_file_selection == "best" and parsed:
        if token_level_raw_candidates:
            candidate_pool = token_level_raw_candidates
            selection_reason = "best_token_level_raw_ocr_file_by_table_score"
        elif raw_candidates:
            candidate_pool = raw_candidates
            selection_reason = "best_raw_ocr_file_by_table_score"
        else:
            candidate_pool = parsed
            selection_reason = "best_single_ocr_file_by_table_score"
        selected = [max(candidate_pool, key=lambda item: (item[2].get("score", 0), item[2].get("candidate_line_count", 0), item[2].get("token_count_inside_bbox", 0)))]

    tokens: list[dict[str, Any]] = []
    for _, file_tokens, _ in selected:
        tokens.extend(file_tokens)
        if len(tokens) > 150000:
            break
    raw_token_count = len(tokens)
    removed = 0
    if deduplicate_tokens:
        tokens, removed = dedupe_ocr_tokens(tokens)

    diagnostics = {
        "ocr_candidate_file_count": len(files),
        "ocr_parsed_file_count": len(parsed),
        "ocr_raw_candidate_file_count": sum(1 for _, _, score in parsed if score.get("ocr_source_kind") == "raw_ocr_sidecar"),
        "ocr_token_level_raw_candidate_file_count": sum(1 for _, _, score in parsed if ocr_source_is_usable_token_level_raw(score)),
        "ocr_line_raw_candidate_file_count": sum(1 for _, _, score in parsed if score.get("ocr_source_detail") == "raw_line_ocr_sidecar"),
        "ocr_derived_match_candidate_file_count": sum(1 for _, _, score in parsed if score.get("ocr_source_kind") == "derived_match_sidecar"),
        "ocr_selected_file_count": len(selected),
        "ocr_selected_source_kind": selected[0][2].get("ocr_source_kind") if selected else None,
        "ocr_selected_source_detail": selected[0][2].get("ocr_source_detail") if selected else None,
        "ocr_file_selection": ocr_file_selection,
        "ocr_file_selection_reason": selection_reason,
        "ocr_raw_token_count_before_dedup": raw_token_count,
        "ocr_duplicate_token_removed_count": removed,
        "ocr_selected_file_scores_sample": [
            {"path": str(path).replace("\\", "/"), **score}
            for path, _, score in sorted(parsed, key=lambda item: item[2].get("score", 0), reverse=True)[:5]
        ],
    }
    return tokens, [str(p).replace("\\", "/") for p, _, _ in selected], diagnostics


def row_sort_key(token: Mapping[str, Any]) -> tuple[float, float]:
    box = token.get("bbox") or {}
    cx, cy = bbox_center(box)
    return cy, cx


def group_tokens_into_lines(tokens: Sequence[Mapping[str, Any]], *, y_tolerance: float | None = None) -> list[list[Mapping[str, Any]]]:
    if not tokens:
        return []
    heights = [float((t.get("bbox") or {}).get("height") or 0) for t in tokens if (t.get("bbox") or {}).get("height")]
    median_height = sorted(heights)[len(heights) // 2] if heights else 12.0
    tolerance = y_tolerance if y_tolerance is not None else max(6.0, min(28.0, median_height * 0.75))
    lines: list[list[Mapping[str, Any]]] = []
    line_centers: list[float] = []
    for token in sorted(tokens, key=row_sort_key):
        _, cy = bbox_center(token.get("bbox") or {})
        if not lines or abs(cy - line_centers[-1]) > tolerance:
            lines.append([token])
            line_centers.append(cy)
        else:
            lines[-1].append(token)
            line_centers[-1] = (line_centers[-1] * (len(lines[-1]) - 1) + cy) / len(lines[-1])
    for line in lines:
        line.sort(key=lambda t: bbox_center(t.get("bbox") or {})[0])
    return lines


def split_line_into_cells(line: Sequence[Mapping[str, Any]]) -> list[list[Mapping[str, Any]]]:
    if not line:
        return []
    widths = [float((t.get("bbox") or {}).get("width") or 0) for t in line if (t.get("bbox") or {}).get("width")]
    median_width = sorted(widths)[len(widths) // 2] if widths else 25.0
    gap_threshold = max(24.0, min(120.0, median_width * 1.65))
    cells: list[list[Mapping[str, Any]]] = []
    current: list[Mapping[str, Any]] = []
    last_x1: float | None = None
    for token in line:
        box = token.get("bbox") or {}
        x0 = float(box.get("x0") or 0)
        x1 = float(box.get("x1") or x0)
        gap = (x0 - last_x1) if last_x1 is not None else 0
        if current and gap > gap_threshold:
            cells.append(current)
            current = [token]
        else:
            current.append(token)
        last_x1 = x1
    if current:
        cells.append(current)
    return cells


def line_features(line: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    texts = [normalize_text(t.get("text")) for t in line if normalize_text(t.get("text"))]
    joined = " ".join(texts)
    compact = compact_text(joined)
    part_numbers = PART_NUMBER_RE.findall(joined)
    header_hits = [w for w in HEADER_WORDS if w in compact]
    furniture_hits = [w for w in NON_TABLE_FURNITURE_WORDS if w in compact]
    return {
        "text": joined,
        "token_count": len(texts),
        "part_number_count": len(part_numbers),
        "part_numbers": part_numbers,
        "header_word_hits": sorted(set(header_hits)),
        "furniture_word_hits": sorted(set(furniture_hits)),
        "looks_like_header": len(header_hits) >= 2 or bool(FIG_ITEM_RE.search(joined)),
        "looks_like_table_row": len(texts) >= 3 or bool(part_numbers) or len(header_hits) >= 2,
    }


def filter_candidate_lines(lines: Sequence[Sequence[Mapping[str, Any]]]) -> list[list[Mapping[str, Any]]]:
    candidate: list[list[Mapping[str, Any]]] = []
    for line in lines:
        features = line_features(line)
        if not features["looks_like_table_row"]:
            continue
        # Keep Honeywell/manual furniture only if it has true table evidence.
        if features["furniture_word_hits"] and not features["part_number_count"] and not features["looks_like_header"]:
            continue
        candidate.append(list(line))
    return candidate



def cell_text_signature(cell_tokens: Sequence[Mapping[str, Any]]) -> str:
    text = normalize_text(" ".join(normalize_text(t.get("text")) for t in cell_tokens if normalize_text(t.get("text"))))
    parts = sorted(PART_NUMBER_RE.findall(text))
    if parts and len(parts) >= 2:
        return "parts:" + "|".join(parts)
    return compact_text(text)


def collapse_repeated_cell_groups(cells: Sequence[Sequence[Mapping[str, Any]]]) -> tuple[list[list[Mapping[str, Any]]], int]:
    """Collapse repeated derived-sidecar cell groups within one row.

    Some derived matcher sidecars emit the same row-level text at several x
    positions. Gap splitting then creates multiple identical cells. Keep the
    leftmost representative and count the collapsed duplicates for diagnostics.
    """
    out: list[list[Mapping[str, Any]]] = []
    seen: set[str] = set()
    removed = 0
    for cell in cells:
        sig = cell_text_signature(cell)
        if sig and sig in seen:
            removed += 1
            continue
        seen.add(sig)
        out.append(list(cell))
    return out, removed

def build_table_records_from_tokens(
    *,
    page_id: Any,
    table_id: Any,
    source_record_id: str,
    tokens: Sequence[Mapping[str, Any]],
    final_bbox: Mapping[str, Any],
    max_rows: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    in_bbox = [dict(t) for t in tokens if isinstance(t.get("bbox"), Mapping) and bbox_inside(t.get("bbox"), final_bbox)]
    lines = group_tokens_into_lines(in_bbox)
    candidate_lines = filter_candidate_lines(lines)
    if len(candidate_lines) < 3 and len(lines) > len(candidate_lines):
        # Weak OCR/table vocab fallback: keep multi-token lines rather than emitting nothing.
        candidate_lines = [list(line) for line in lines if len(line) >= 2]
    candidate_lines = candidate_lines[:max_rows]

    row_records: list[dict[str, Any]] = []
    cell_records: list[dict[str, Any]] = []
    value_records: list[dict[str, Any]] = []
    header_row_count = 0
    part_number_count = 0
    repeated_cell_text_collapsed_count = 0

    for row_index, line in enumerate(candidate_lines):
        features = line_features(line)
        row_bbox = union_bboxes([t["bbox"] for t in line if t.get("bbox")])
        row_id = stable_id("table_route_row", page_id, table_id, row_index, features.get("text"))
        if features["looks_like_header"]:
            header_row_count += 1
        part_number_count += int(features["part_number_count"] or 0)
        row_record = {
            "row_id": row_id,
            "schema_version": SCHEMA_VERSION,
            "page_id": page_id,
            "table_id": table_id,
            "source_reconstructor_record_id": source_record_id,
            "row_index": row_index,
            "row_text": features["text"],
            "row_bbox": row_bbox,
            "row_token_count": features["token_count"],
            "row_cell_count": 0,
            "looks_like_header": features["looks_like_header"],
            "part_number_count": features["part_number_count"],
            "part_numbers": features["part_numbers"],
            "header_word_hits": features["header_word_hits"],
            "retrieval_only": True,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "unsafe_table_route_row": False,
        }
        cells = split_line_into_cells(line)
        cells, collapsed_cells = collapse_repeated_cell_groups(cells)
        repeated_cell_text_collapsed_count += collapsed_cells
        row_record["row_cell_count"] = len(cells)
        row_records.append(row_record)
        for column_index, cell_tokens in enumerate(cells):
            cell_text = normalize_text(" ".join(normalize_text(t.get("text")) for t in cell_tokens if normalize_text(t.get("text"))))
            if not cell_text:
                continue
            cell_bbox = union_bboxes([t["bbox"] for t in cell_tokens if t.get("bbox")])
            cell_id = stable_id("table_route_cell", page_id, table_id, row_index, column_index, cell_text)
            part_candidates = PART_NUMBER_RE.findall(cell_text)
            value_kind = classify_value(cell_text, row_record)
            cell_record = {
                "cell_id": cell_id,
                "schema_version": SCHEMA_VERSION,
                "page_id": page_id,
                "table_id": table_id,
                "row_id": row_id,
                "row_index": row_index,
                "column_index": column_index,
                "cell_text": cell_text,
                "normalized_text": cell_text,
                "cell_bbox": cell_bbox,
                "cell_token_count": len(cell_tokens),
                "value_kind": value_kind,
                "part_number_candidates": part_candidates,
                "is_header_cell": bool(row_record["looks_like_header"]),
                "retrieval_only": True,
                "answer_permission": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
                "unsafe_table_route_cell": False,
            }
            value_record = {
                "value_record_id": stable_id("table_route_value", cell_id),
                "schema_version": SCHEMA_VERSION,
                "page_id": page_id,
                "table_id": table_id,
                "row_id": row_id,
                "cell_id": cell_id,
                "row_index": row_index,
                "column_index": column_index,
                "value_text": cell_text,
                "normalized_value": cell_text,
                "value_kind": value_kind,
                "part_number_candidates": part_candidates,
                "cell_bbox": cell_bbox,
                "bbox_source": "ocr_token_geometry_inside_final_table_bbox",
                "retrieval_only": True,
                "answer_permission": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
                "unsafe_table_route_value": False,
            }
            cell_records.append(cell_record)
            value_records.append(value_record)

    diagnostics = {
        "ocr_token_count_inside_bbox": len(in_bbox),
        "ocr_line_count_inside_bbox": len(lines),
        "candidate_table_row_count": len(candidate_lines),
        "header_row_count": header_row_count,
        "part_number_candidate_count": part_number_count + sum(len(v.get("part_number_candidates") or []) for v in value_records),
        "repeated_cell_text_collapsed_count": repeated_cell_text_collapsed_count,
    }
    return row_records, cell_records, value_records, diagnostics



def table_text_bundle(
    row_records: Sequence[Mapping[str, Any]],
    cell_records: Sequence[Mapping[str, Any]],
    value_records: Sequence[Mapping[str, Any]],
) -> tuple[str, str]:
    texts: list[str] = []
    for row in row_records:
        if row.get("row_text"):
            texts.append(normalize_text(row.get("row_text")))
    for cell in cell_records:
        if cell.get("cell_text"):
            texts.append(normalize_text(cell.get("cell_text")))
    for value in value_records:
        if value.get("normalized_value"):
            texts.append(normalize_text(value.get("normalized_value")))
    joined = " ".join(t for t in texts if t)
    return joined, compact_text(joined)


def detect_table_template(
    row_records: Sequence[Mapping[str, Any]],
    cell_records: Sequence[Mapping[str, Any]],
    value_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Classify recurring table templates without granting extraction authority.

    This is an advisory parser layer over the raw row/cell/value extraction. It
    does not change source truth or answer permission. The goal is to identify
    the table family so later normalizers can apply template-specific field
    rules instead of treating every page as a generic grid.
    """
    joined, compact = table_text_bundle(row_records, cell_records, value_records)
    value_texts = [normalize_text(v.get("normalized_value")) for v in value_records if normalize_text(v.get("normalized_value"))]
    part_values = sum(1 for value in value_records if value.get("value_kind") == "part_number" or PART_NUMBER_RE.search(str(value.get("normalized_value") or "")))
    header_values = sum(1 for value in value_records if value.get("value_kind") == "header")
    numeric_values = sum(1 for value in value_records if value.get("value_kind") == "numeric")
    short_code_values = sum(1 for value in value_records if value.get("value_kind") == "short_code")
    row_count = len(row_records)
    cell_count = len(cell_records)
    value_count = len(value_records)

    signals: list[str] = []
    lep_score = 0
    part_list_score = 0
    ipl_score = 0

    if any(hint in compact for hint in LEP_COMPACT_HINTS):
        lep_score += 8; signals.append("lep_title_hint")
    if "page" in compact and any(term in compact for term in ("date", "rev", "revision", "effectivity")):
        lep_score += 4; signals.append("lep_page_date_rev_vocab")
    if row_count >= 20 and numeric_values + short_code_values >= 10 and part_values <= max(4, value_count // 8):
        lep_score += 3; signals.append("lep_dense_page_numeric_rows")

    if any(hint in compact for hint in PART_LIST_COMPACT_HINTS):
        part_list_score += 8; signals.append("part_list_title_hint")
    if part_values >= 12 and part_values >= max(6, value_count // 3):
        part_list_score += 6; signals.append("part_list_many_part_numbers")
    if part_values >= 25 and header_values <= max(6, value_count // 6):
        part_list_score += 2; signals.append("part_list_low_header_ratio")

    if any(hint in compact for hint in IPL_COMPACT_HINTS):
        ipl_score += 7; signals.append("ipl_header_vocab")
    if ("fig" in compact or "figure" in compact) and "item" in compact and ("part" in compact or part_values >= 5):
        ipl_score += 4; signals.append("ipl_fig_item_part_vocab")
    if part_values >= 5 and any(term in compact for term in ("nomenclature", "assy", "units", "effectivity")):
        ipl_score += 4; signals.append("ipl_part_metadata_mix")

    scored = [
        (TEMPLATE_LIST_EFFECTIVE_PAGES, lep_score),
        (TEMPLATE_PART_NUMBER_COVERAGE, part_list_score),
        (TEMPLATE_IPL_SPLIT_COLUMN, ipl_score),
    ]
    template_type, score = max(scored, key=lambda item: item[1])
    if score <= 0:
        template_type = TEMPLATE_GENERIC if value_count else TEMPLATE_UNKNOWN
        confidence = 0.2 if value_count else 0.0
        if value_count:
            signals.append("generic_values_present")
    else:
        confidence = min(0.99, 0.45 + score / 20.0)
    return {
        "table_template_type": template_type,
        "table_template_confidence": round(confidence, 3),
        "table_template_score": score,
        "table_template_signals": sorted(set(signals)),
        "template_value_count": value_count,
        "template_row_count": row_count,
        "template_cell_count": cell_count,
        "template_part_number_value_count": part_values,
        "template_header_value_count": header_values,
        "template_numeric_value_count": numeric_values,
        "template_short_code_value_count": short_code_values,
    }


def infer_template_value_role(template_type: str, text: str, value_kind: str | None, row_record: Mapping[str, Any] | None = None) -> str:
    compact = compact_text(text)
    if template_type == TEMPLATE_PART_NUMBER_COVERAGE:
        if value_kind == "part_number" or PART_NUMBER_RE.search(text):
            return "covered_part_number"
        if "publication" in compact or "partnumber" in compact:
            return "part_number_list_context"
        return "part_number_list_other"
    if template_type == TEMPLATE_LIST_EFFECTIVE_PAGES:
        if "listofeffectivepages" in compact or "effectivepages" in compact:
            return "table_title"
        if "page" in compact and any(term in compact for term in ("date", "rev", "revision")):
            return "header"
        if PART_NUMBER_RE.search(text) or re.search(r"\b\d{2}-\d{2}-\d{2}\b", text):
            return "manual_page_reference"
        if value_kind in {"numeric", "short_code"}:
            return "page_rev_or_sequence_value"
        if value_kind == "header":
            return "header"
        return "lep_other"
    if template_type == TEMPLATE_IPL_SPLIT_COLUMN:
        if value_kind == "part_number" or PART_NUMBER_RE.search(text):
            return "part_number"
        if value_kind == "numeric" or compact in {"fig", "item", "qty"}:
            return "fig_item_or_quantity"
        if any(term in compact for term in ("nomenclature", "assy", "effectivity", "units")):
            return "ipl_header_or_metadata"
        return "ipl_text"
    if value_kind == "header":
        return "header"
    if value_kind == "part_number":
        return "part_number"
    return "generic_value"


def annotate_template_metadata(
    row_records: list[dict[str, Any]],
    cell_records: list[dict[str, Any]],
    value_records: list[dict[str, Any]],
    template: Mapping[str, Any],
) -> int:
    template_type = str(template.get("table_template_type") or TEMPLATE_UNKNOWN)
    assigned = 0
    row_lookup = {row.get("row_id"): row for row in row_records}
    cell_lookup = {cell.get("cell_id"): cell for cell in cell_records}
    for row in row_records:
        row["table_template_type"] = template_type
        row["table_template_confidence"] = template.get("table_template_confidence")
        if row.get("looks_like_header"):
            row["template_row_role"] = "header"
        elif template_type == TEMPLATE_PART_NUMBER_COVERAGE and row.get("part_number_count"):
            row["template_row_role"] = "part_number_row"
        elif template_type == TEMPLATE_LIST_EFFECTIVE_PAGES:
            row["template_row_role"] = "effective_page_row"
        elif template_type == TEMPLATE_IPL_SPLIT_COLUMN:
            row["template_row_role"] = "ipl_row"
        else:
            row["template_row_role"] = "generic_row"
    for cell in cell_records:
        text = normalize_text(cell.get("normalized_text") or cell.get("cell_text"))
        role = infer_template_value_role(template_type, text, cell.get("value_kind"), row_lookup.get(cell.get("row_id")))
        cell["table_template_type"] = template_type
        cell["table_template_confidence"] = template.get("table_template_confidence")
        cell["template_cell_role"] = role
        if role != "generic_value":
            assigned += 1
    for value in value_records:
        text = normalize_text(value.get("normalized_value") or value.get("value_text"))
        role = infer_template_value_role(template_type, text, value.get("value_kind"), row_lookup.get(value.get("row_id")))
        value["table_template_type"] = template_type
        value["table_template_confidence"] = template.get("table_template_confidence")
        value["template_value_role"] = role
        if role != "generic_value":
            assigned += 1
    return assigned


def classify_value(text: str, row_record: Mapping[str, Any]) -> str:
    compact = compact_text(text)
    if row_record.get("looks_like_header"):
        return "header"
    if PART_NUMBER_RE.search(text):
        return "part_number"
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", compact or ""):
        return "numeric"
    if any(word in compact for word in ("ref", "eff", "effectivity", "assy", "units")):
        return "table_metadata"
    if len(text) <= 4 and re.search(r"\d", text):
        return "short_code"
    return "text"


def legacy_fallback_records(scoped_record: Mapping[str, Any] | None, page_id: Any, table_id: Any, source_record_id: str, max_rows: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if not scoped_record:
        return [], [], [], {"legacy_fallback_used": False, "legacy_value_count": 0}
    raw_values = as_list(scoped_record.get("value_records"))
    if not raw_values:
        return [], [], [], {"legacy_fallback_used": False, "legacy_value_count": 0}
    rows: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for idx, value in enumerate(raw_values[: max_rows * 25]):
        if not isinstance(value, Mapping):
            continue
        row_index = as_int(value.get("row_index"), idx)
        rows[row_index].append(value)
    row_records: list[dict[str, Any]] = []
    cell_records: list[dict[str, Any]] = []
    value_records: list[dict[str, Any]] = []
    for out_row_index, row_index in enumerate(sorted(rows)[:max_rows]):
        values = rows[row_index]
        row_text = " | ".join(normalize_text(v.get("normalized_text") or v.get("value_text") or v.get("text")) for v in values)
        row_id = stable_id("table_route_legacy_row", page_id, table_id, row_index, row_text)
        row_records.append({
            "row_id": row_id,
            "schema_version": SCHEMA_VERSION,
            "page_id": page_id,
            "table_id": table_id,
            "source_reconstructor_record_id": source_record_id,
            "row_index": out_row_index,
            "source_row_index": row_index,
            "row_text": row_text,
            "row_bbox": None,
            "row_cell_count": len(values),
            "row_token_count": 0,
            "looks_like_header": False,
            "part_number_count": len(PART_NUMBER_RE.findall(row_text)),
            "part_numbers": PART_NUMBER_RE.findall(row_text),
            "extraction_fallback_source": "legacy_bbox_scoped_cell_extraction",
            "retrieval_only": True,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "unsafe_table_route_row": False,
        })
        for col_idx, raw in enumerate(values):
            text = normalize_text(raw.get("normalized_text") or raw.get("value_text") or raw.get("text"))
            if not text:
                continue
            cell_id = stable_id("table_route_legacy_cell", page_id, table_id, out_row_index, col_idx, text)
            box = normalize_bbox(raw.get("cell_bbox") or raw.get("bbox"))
            kind = classify_value(text, {"looks_like_header": False})
            cell_records.append({
                "cell_id": cell_id,
                "schema_version": SCHEMA_VERSION,
                "page_id": page_id,
                "table_id": table_id,
                "row_id": row_id,
                "row_index": out_row_index,
                "column_index": col_idx,
                "cell_text": text,
                "normalized_text": text,
                "cell_bbox": box,
                "value_kind": kind,
                "part_number_candidates": PART_NUMBER_RE.findall(text),
                "extraction_fallback_source": "legacy_bbox_scoped_cell_extraction",
                "retrieval_only": True,
                "answer_permission": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
                "unsafe_table_route_cell": False,
            })
            value_records.append({
                "value_record_id": stable_id("table_route_legacy_value", cell_id),
                "schema_version": SCHEMA_VERSION,
                "page_id": page_id,
                "table_id": table_id,
                "row_id": row_id,
                "cell_id": cell_id,
                "row_index": out_row_index,
                "column_index": col_idx,
                "value_text": text,
                "normalized_value": text,
                "value_kind": kind,
                "part_number_candidates": PART_NUMBER_RE.findall(text),
                "cell_bbox": box,
                "bbox_source": "legacy_bbox_scoped_cell_extraction",
                "retrieval_only": True,
                "answer_permission": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
                "unsafe_table_route_value": False,
            })
    return row_records, cell_records, value_records, {"legacy_fallback_used": True, "legacy_value_count": len(value_records)}


def build_extraction_record(
    source_record: Mapping[str, Any],
    *,
    enrichment_card: Mapping[str, Any] | None,
    scoped_record: Mapping[str, Any] | None,
    ocr_root: Path | None,
    max_ocr_files_per_table: int,
    max_rows_per_table: int,
    allow_legacy_fallback: bool,
    ocr_file_selection: str = "best",
    deduplicate_ocr_tokens: bool = True,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    page_id = source_record.get("page_id")
    table_id = source_record.get("table_id")
    record_id = str(source_record.get("full_enclosure_record_id") or source_record.get("record_id") or source_record.get("id") or stable_id("source", page_id, table_id))
    final_bbox = normalize_bbox(source_record.get("final_table_bbox"))
    ready = bool(source_record.get("full_table_enclosure_bbox_ready"))
    review_only = bool(source_record.get("table_bbox_review_only"))
    extraction_allowed = bool(ready and not review_only and final_bbox)
    review_flags = set(as_list(source_record.get("review_flags")))
    row_records: list[dict[str, Any]] = []
    cell_records: list[dict[str, Any]] = []
    value_records: list[dict[str, Any]] = []
    ocr_tokens: list[dict[str, Any]] = []
    ocr_files: list[str] = []
    extraction_method = "skipped"
    extraction_status = "TABLE_ROUTE_CELL_EXTRACTION_SKIPPED"
    skip_reason = None
    diagnostics: dict[str, Any] = {}

    if not extraction_allowed:
        skip_reason = "review_only_or_bbox_not_ready"
        review_flags.add("table_route_cell_extraction_skipped_review_only_or_bbox_not_ready")
    else:
        ocr_tokens, ocr_files, ocr_diag = load_ocr_tokens(
            enrichment_card,
            page_id,
            ocr_root,
            max_ocr_files_per_table,
            final_bbox=final_bbox,
            ocr_file_selection=ocr_file_selection,
            deduplicate_tokens=deduplicate_ocr_tokens,
        )
        diagnostics.update(ocr_diag)
        if ocr_tokens:
            row_records, cell_records, value_records, table_diag = build_table_records_from_tokens(
                page_id=page_id,
                table_id=table_id,
                source_record_id=record_id,
                tokens=ocr_tokens,
                final_bbox=final_bbox,
                max_rows=max_rows_per_table,
            )
            diagnostics.update(table_diag)
            extraction_method = "ocr_token_geometry_inside_final_table_bbox"
            extraction_status = "TABLE_ROUTE_CELL_EXTRACTION_BUILT"
        if not value_records and allow_legacy_fallback:
            row_records, cell_records, value_records, legacy_diag = legacy_fallback_records(scoped_record, page_id, table_id, record_id, max_rows_per_table)
            diagnostics.update(legacy_diag)
            if value_records:
                extraction_method = "legacy_bbox_scoped_cell_extraction_fallback"
                extraction_status = "TABLE_ROUTE_CELL_EXTRACTION_BUILT"
                review_flags.add("legacy_scoped_cell_fallback_used")
        if not value_records:
            extraction_status = "TABLE_ROUTE_CELL_EXTRACTION_REVIEW"
            extraction_method = "unresolved"
            review_flags.add("table_route_cell_extraction_no_values_emitted")

    template_diag = detect_table_template(row_records, cell_records, value_records)
    template_role_assigned_count = annotate_template_metadata(row_records, cell_records, value_records, template_diag)
    part_number_candidates = sorted({p for value in value_records for p in as_list(value.get("part_number_candidates")) if p})
    header_cell_count = sum(1 for cell in cell_records if cell.get("is_header_cell") or cell.get("value_kind") == "header")
    unsafe = False
    record = {
        "table_route_cell_extraction_record_id": stable_id("table_route_extract", page_id, table_id, extraction_method, len(value_records)),
        "schema_version": SCHEMA_VERSION,
        "status": extraction_status,
        "page_id": page_id,
        "table_id": table_id,
        "source_reconstructor_record_id": record_id,
        "final_table_bbox": final_bbox,
        "final_table_bbox_source": source_record.get("final_table_bbox_source"),
        "full_table_enclosure_bbox_ready": ready,
        "table_bbox_review_only": review_only,
        "table_extraction_allowed": extraction_allowed,
        "skip_reason": skip_reason,
        "extraction_method": extraction_method,
        "ocr_source_file_count": len(ocr_files),
        "ocr_source_files_sample": ocr_files[:8],
        "ocr_candidate_file_count": diagnostics.get("ocr_candidate_file_count", 0),
        "ocr_parsed_file_count": diagnostics.get("ocr_parsed_file_count", 0),
        "ocr_raw_candidate_file_count": diagnostics.get("ocr_raw_candidate_file_count", 0),
        "ocr_derived_match_candidate_file_count": diagnostics.get("ocr_derived_match_candidate_file_count", 0),
        "ocr_selected_file_count": diagnostics.get("ocr_selected_file_count", len(ocr_files)),
        "ocr_selected_source_kind": diagnostics.get("ocr_selected_source_kind"),
        "ocr_selected_source_detail": diagnostics.get("ocr_selected_source_detail"),
        "ocr_token_level_raw_candidate_file_count": diagnostics.get("ocr_token_level_raw_candidate_file_count", 0),
        "ocr_line_raw_candidate_file_count": diagnostics.get("ocr_line_raw_candidate_file_count", 0),
        "ocr_file_selection": diagnostics.get("ocr_file_selection"),
        "ocr_file_selection_reason": diagnostics.get("ocr_file_selection_reason"),
        "ocr_raw_token_count_before_dedup": diagnostics.get("ocr_raw_token_count_before_dedup", len(ocr_tokens)),
        "ocr_duplicate_token_removed_count": diagnostics.get("ocr_duplicate_token_removed_count", 0),
        "ocr_selected_file_scores_sample": diagnostics.get("ocr_selected_file_scores_sample", []),
        "ocr_token_count": len(ocr_tokens),
        "ocr_token_inside_final_bbox_count": diagnostics.get("ocr_token_count_inside_bbox", 0),
        "ocr_line_count_inside_final_bbox": diagnostics.get("ocr_line_count_inside_bbox", 0),
        "table_row_record_count": len(row_records),
        "table_cell_record_count": len(cell_records),
        "table_value_record_count": len(value_records),
        "header_cell_count": header_cell_count,
        "part_number_candidate_count": len(part_number_candidates),
        "table_template_type": template_diag.get("table_template_type"),
        "table_template_confidence": template_diag.get("table_template_confidence"),
        "table_template_score": template_diag.get("table_template_score"),
        "table_template_signals": template_diag.get("table_template_signals", []),
        "template_role_assigned_value_count": template_role_assigned_count,
        "template_part_number_value_count": template_diag.get("template_part_number_value_count", 0),
        "template_header_value_count": template_diag.get("template_header_value_count", 0),
        "template_numeric_value_count": template_diag.get("template_numeric_value_count", 0),
        "repeated_cell_text_collapsed_count": diagnostics.get("repeated_cell_text_collapsed_count", 0),
        "part_number_candidates_sample": part_number_candidates[:25],
        "table_has_extracted_values": bool(value_records),
        "legacy_fallback_used": bool(diagnostics.get("legacy_fallback_used")),
        "review_required": bool(review_flags) or not value_records,
        "review_flags": sorted(review_flags),
        "retrieval_only": True,
        "routing_only": False,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "retrieval_only_answer_allowed": False,
        "source_truth_mutation_allowed": False,
        "source_truth_mutations_performed": 0,
        "can_mutate_source_truth": False,
        "postgres_write_attempted": False,
        "qdrant_write_attempted": False,
        "opensearch_write_attempted": False,
        "unsafe_table_route_cell_extraction_record": unsafe,
    }
    return record, row_records, cell_records, value_records


def summarize(records: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]], cells: Sequence[Mapping[str, Any]], values: Sequence[Mapping[str, Any]], source_records: Sequence[Mapping[str, Any]], source_quality_statuses: Mapping[str, Any]) -> dict[str, Any]:
    def count(pred) -> int:
        return sum(1 for record in records if pred(record))
    return {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "source_table_bbox_record_count": len(source_records),
        "table_route_cell_extraction_record_count": len(records),
        "extraction_ready_table_count": count(lambda r: r.get("table_extraction_allowed")),
        "review_only_skipped_count": count(lambda r: r.get("table_bbox_review_only") and not r.get("table_extraction_allowed")),
        "bbox_not_ready_skipped_count": count(lambda r: not r.get("table_bbox_review_only") and not r.get("table_extraction_allowed")),
        "cell_extraction_attempted_count": count(lambda r: r.get("table_extraction_allowed")),
        "cell_extraction_success_record_count": count(lambda r: r.get("table_has_extracted_values")),
        "ocr_source_file_table_count": count(lambda r: int(r.get("ocr_source_file_count") or 0) > 0),
        "ocr_candidate_file_count_total": sum(as_int(r.get("ocr_candidate_file_count"), 0) for r in records),
        "ocr_selected_file_count_total": sum(as_int(r.get("ocr_selected_file_count"), 0) for r in records),
        "ocr_raw_candidate_file_count_total": sum(as_int(r.get("ocr_raw_candidate_file_count"), 0) for r in records),
        "ocr_token_level_raw_candidate_file_count_total": sum(as_int(r.get("ocr_token_level_raw_candidate_file_count"), 0) for r in records),
        "ocr_line_raw_candidate_file_count_total": sum(as_int(r.get("ocr_line_raw_candidate_file_count"), 0) for r in records),
        "ocr_derived_match_candidate_file_count_total": sum(as_int(r.get("ocr_derived_match_candidate_file_count"), 0) for r in records),
        "ocr_raw_file_selected_table_count": count(lambda r: r.get("ocr_selected_source_kind") == "raw_ocr_sidecar"),
        "ocr_token_level_raw_file_selected_table_count": count(lambda r: r.get("ocr_selected_source_detail") in {"raw_tsv_word_ocr_sidecar", "raw_hocr_word_ocr_sidecar", "raw_token_ocr_sidecar", "raw_unknown_granularity_ocr_sidecar"}),
        "ocr_line_raw_file_selected_table_count": count(lambda r: r.get("ocr_selected_source_detail") == "raw_line_ocr_sidecar"),
        "ocr_derived_match_file_selected_table_count": count(lambda r: r.get("ocr_selected_source_kind") == "derived_match_sidecar"),
        "ocr_best_file_selected_table_count": count(lambda r: r.get("ocr_file_selection") == "best" and int(r.get("ocr_selected_file_count") or 0) == 1),
        "ocr_raw_token_count_before_dedup": sum(as_int(r.get("ocr_raw_token_count_before_dedup"), 0) for r in records),
        "ocr_duplicate_token_removed_count": sum(as_int(r.get("ocr_duplicate_token_removed_count"), 0) for r in records),
        "ocr_token_table_count": count(lambda r: int(r.get("ocr_token_count") or 0) > 0),
        "legacy_fallback_table_count": count(lambda r: r.get("legacy_fallback_used")),
        "table_row_record_count": len(rows),
        "table_cell_record_count": len(cells),
        "table_value_record_count": len(values),
        "header_cell_count": sum(1 for cell in cells if cell.get("is_header_cell") or cell.get("value_kind") == "header"),
        "part_number_candidate_count": sum(len(as_list(value.get("part_number_candidates"))) for value in values),
        "template_detected_table_count": count(lambda r: r.get("table_extraction_allowed") and r.get("table_template_type") not in {None, TEMPLATE_UNKNOWN}),
        "list_effective_pages_template_count": count(lambda r: r.get("table_template_type") == TEMPLATE_LIST_EFFECTIVE_PAGES),
        "part_number_coverage_template_count": count(lambda r: r.get("table_template_type") == TEMPLATE_PART_NUMBER_COVERAGE),
        "ipl_split_column_template_count": count(lambda r: r.get("table_template_type") == TEMPLATE_IPL_SPLIT_COLUMN),
        "generic_table_template_count": count(lambda r: r.get("table_template_type") == TEMPLATE_GENERIC),
        "template_role_assigned_value_count": sum(as_int(r.get("template_role_assigned_value_count"), 0) for r in records),
        "template_part_number_value_count": sum(as_int(r.get("template_part_number_value_count"), 0) for r in records),
        "template_header_value_count": sum(as_int(r.get("template_header_value_count"), 0) for r in records),
        "repeated_cell_text_collapsed_count": sum(as_int(r.get("repeated_cell_text_collapsed_count"), 0) for r in records),
        "unsafe_table_route_cell_extraction_record_count": count(lambda r: r.get("unsafe_table_route_cell_extraction_record")),
        "answer_permission_count": count(lambda r: r.get("answer_permission") or r.get("can_answer_directly") or r.get("can_prove_claims")),
        "can_answer_directly_count": count(lambda r: r.get("can_answer_directly")),
        "can_prove_claims_count": count(lambda r: r.get("can_prove_claims")),
        "retrieval_only_answer_allowed_count": count(lambda r: r.get("retrieval_only_answer_allowed")),
        "source_truth_mutation_allowed_count": count(lambda r: r.get("source_truth_mutation_allowed") or r.get("can_mutate_source_truth")),
        "source_truth_mutations_performed": sum(as_int(r.get("source_truth_mutations_performed"), 0) for r in records),
        "postgres_write_attempt_count": count(lambda r: r.get("postgres_write_attempted")),
        "qdrant_write_attempt_count": count(lambda r: r.get("qdrant_write_attempted")),
        "opensearch_write_attempt_count": count(lambda r: r.get("opensearch_write_attempted")),
        "source_quality_statuses": dict(source_quality_statuses),
    }


def evaluate_quality(summary: Mapping[str, Any], thresholds: Mapping[str, Any]) -> tuple[str, list[str]]:
    failures: list[str] = []

    def require(condition: bool, reason: str) -> None:
        if not condition:
            failures.append(reason)

    require(summary.get("source_table_bbox_record_count", 0) >= thresholds.get("min_source_table_bbox_records", 1), "min_source_table_bbox_records_not_met")
    require(summary.get("table_route_cell_extraction_record_count", 0) >= thresholds.get("min_extraction_records", 1), "min_extraction_records_not_met")
    require(summary.get("extraction_ready_table_count", 0) >= thresholds.get("min_extraction_ready_tables", 1), "min_extraction_ready_tables_not_met")
    require(summary.get("review_only_skipped_count", 0) >= thresholds.get("min_review_only_skipped", 0), "min_review_only_skipped_not_met")
    require(summary.get("cell_extraction_attempted_count", 0) >= thresholds.get("min_cell_extraction_attempted", 1), "min_cell_extraction_attempted_not_met")
    require(summary.get("cell_extraction_success_record_count", 0) >= thresholds.get("min_cell_extraction_success_records", 1), "min_cell_extraction_success_records_not_met")
    require(summary.get("table_row_record_count", 0) >= thresholds.get("min_row_records", 1), "min_row_records_not_met")
    require(summary.get("table_cell_record_count", 0) >= thresholds.get("min_cell_records", 1), "min_cell_records_not_met")
    require(summary.get("table_value_record_count", 0) >= thresholds.get("min_value_records", 1), "min_value_records_not_met")
    require(summary.get("part_number_candidate_count", 0) >= thresholds.get("min_part_number_candidates", 0), "min_part_number_candidates_not_met")
    if thresholds.get("min_template_detected_tables") is not None:
        require(summary.get("template_detected_table_count", 0) >= thresholds.get("min_template_detected_tables"), "min_template_detected_tables_not_met")
    if thresholds.get("min_part_number_coverage_template_tables") is not None:
        require(summary.get("part_number_coverage_template_count", 0) >= thresholds.get("min_part_number_coverage_template_tables"), "min_part_number_coverage_template_tables_not_met")
    if thresholds.get("min_template_role_assigned_values") is not None:
        require(summary.get("template_role_assigned_value_count", 0) >= thresholds.get("min_template_role_assigned_values"), "min_template_role_assigned_values_not_met")
    if thresholds.get("max_ocr_selected_files_per_table_average") is not None:
        attempted = max(1, int(summary.get("ocr_source_file_table_count") or 0))
        average_selected = float(summary.get("ocr_selected_file_count_total") or 0) / attempted
        require(average_selected <= float(thresholds.get("max_ocr_selected_files_per_table_average")), "ocr_selected_files_average_exceeded")
    if thresholds.get("min_token_level_raw_selected_tables") is not None:
        require(summary.get("ocr_token_level_raw_file_selected_table_count", 0) >= thresholds.get("min_token_level_raw_selected_tables"), "min_token_level_raw_selected_tables_not_met")
    if thresholds.get("max_line_raw_selected_tables") is not None:
        require(summary.get("ocr_line_raw_file_selected_table_count", 0) <= thresholds.get("max_line_raw_selected_tables"), "line_raw_selected_tables_exceeded")
    require(summary.get("unsafe_table_route_cell_extraction_record_count", 0) <= thresholds.get("max_unsafe_records", 0), "unsafe_records_exceeded")
    require(summary.get("answer_permission_count", 0) <= thresholds.get("max_answer_permission_count", 0), "answer_permission_count_exceeded")
    require(summary.get("source_truth_mutation_allowed_count", 0) <= thresholds.get("max_source_truth_mutation_allowed", 0), "source_truth_mutation_allowed_exceeded")
    if thresholds.get("require_table_full_enclosure_bbox_reconstructor_quality_pass"):
        require(summary.get("source_quality_statuses", {}).get("table_full_enclosure_bbox_reconstructor") == "PASS", "table_full_enclosure_bbox_reconstructor_quality_not_pass")
    if thresholds.get("require_table_ocr_bbox_enrichment_quality_pass"):
        require(summary.get("source_quality_statuses", {}).get("table_ocr_bbox_enrichment") == "PASS", "table_ocr_bbox_enrichment_quality_not_pass")
    if thresholds.get("require_table_bbox_scoped_cell_extraction_quality_pass"):
        require(summary.get("source_quality_statuses", {}).get("table_bbox_scoped_cell_extraction") == "PASS", "table_bbox_scoped_cell_extraction_quality_not_pass")
    if thresholds.get("require_no_answer_permission"):
        require(summary.get("answer_permission_count", 0) == 0, "answer_permission_not_zero")
        require(summary.get("can_answer_directly_count", 0) == 0, "can_answer_directly_not_zero")
        require(summary.get("can_prove_claims_count", 0) == 0, "can_prove_claims_not_zero")
        require(summary.get("retrieval_only_answer_allowed_count", 0) == 0, "retrieval_only_answer_allowed_not_zero")
    return ("PASS" if not failures else "FAIL"), failures


def build_quality_payload(report: Mapping[str, Any], thresholds: Mapping[str, Any]) -> dict[str, Any]:
    summary = report.get("summary") or {}
    status, failures = evaluate_quality(summary, thresholds)
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "status": status,
        "quality_status": status,
        "generated_at": utc_now(),
        "summary": summary,
        "checks": {
            "schema_version_ok": report.get("schema_version") == SCHEMA_VERSION,
            "min_source_table_bbox_records_met": summary.get("source_table_bbox_record_count", 0) >= thresholds.get("min_source_table_bbox_records", 1),
            "min_extraction_ready_tables_met": summary.get("extraction_ready_table_count", 0) >= thresholds.get("min_extraction_ready_tables", 1),
            "min_row_records_met": summary.get("table_row_record_count", 0) >= thresholds.get("min_row_records", 1),
            "min_cell_records_met": summary.get("table_cell_record_count", 0) >= thresholds.get("min_cell_records", 1),
            "min_value_records_met": summary.get("table_value_record_count", 0) >= thresholds.get("min_value_records", 1),
            "min_template_detected_tables_met": (thresholds.get("min_template_detected_tables") is None or summary.get("template_detected_table_count", 0) >= thresholds.get("min_template_detected_tables")),
            "min_part_number_coverage_template_tables_met": (thresholds.get("min_part_number_coverage_template_tables") is None or summary.get("part_number_coverage_template_count", 0) >= thresholds.get("min_part_number_coverage_template_tables")),
            "min_template_role_assigned_values_met": (thresholds.get("min_template_role_assigned_values") is None or summary.get("template_role_assigned_value_count", 0) >= thresholds.get("min_template_role_assigned_values")),
            "ocr_best_file_selection_active": summary.get("ocr_best_file_selected_table_count", 0) > 0,
            "unsafe_records_within_limit": summary.get("unsafe_table_route_cell_extraction_record_count", 0) <= thresholds.get("max_unsafe_records", 0),
            "answer_permission_zero": summary.get("answer_permission_count", 0) == 0,
            "source_truth_mutation_allowed_zero": summary.get("source_truth_mutation_allowed_count", 0) == 0,
            "write_attempts_zero": summary.get("postgres_write_attempt_count", 0) == 0 and summary.get("qdrant_write_attempt_count", 0) == 0 and summary.get("opensearch_write_attempt_count", 0) == 0,
        },
        "quality_errors": failures,
    }


def build_report(
    *,
    table_full_enclosure_bbox_reconstructor_path: Path,
    table_ocr_bbox_enrichment_path: Path | None,
    table_bbox_scoped_cell_extraction_path: Path | None,
    ocr_root: Path | None,
    output_dir: Path,
    max_ocr_files_per_table: int,
    max_rows_per_table: int,
    allow_legacy_fallback: bool,
    thresholds: Mapping[str, Any],
    ocr_file_selection: str = "best",
    deduplicate_ocr_tokens: bool = True,
) -> dict[str, Any]:
    reconstructor = read_json(table_full_enclosure_bbox_reconstructor_path, default={})
    enrichment = read_json(table_ocr_bbox_enrichment_path, default={}) if table_ocr_bbox_enrichment_path else {}
    scoped = read_json(table_bbox_scoped_cell_extraction_path, default={}) if table_bbox_scoped_cell_extraction_path else {}

    source_records = load_reconstructor_records(reconstructor)
    enrichment_cards = load_enrichment_cards(enrichment)
    scoped_records = load_scoped_records(scoped)
    enrich_by_table, enrich_by_page = build_index_by_page_and_table(enrichment_cards)
    scoped_by_table, scoped_by_page = build_index_by_page_and_table(scoped_records)

    source_quality_statuses = {
        "table_full_enclosure_bbox_reconstructor": payload_quality_status(reconstructor),
        "table_ocr_bbox_enrichment": payload_quality_status(enrichment),
        "table_bbox_scoped_cell_extraction": payload_quality_status(scoped),
    }

    records: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    cells: list[dict[str, Any]] = []
    values: list[dict[str, Any]] = []
    for source_record in source_records:
        enrichment_card = match_aux_record(source_record, enrich_by_table, enrich_by_page)
        scoped_record = match_aux_record(source_record, scoped_by_table, scoped_by_page)
        record, row_records, cell_records, value_records = build_extraction_record(
            source_record,
            enrichment_card=enrichment_card,
            scoped_record=scoped_record,
            ocr_root=ocr_root,
            max_ocr_files_per_table=max_ocr_files_per_table,
            max_rows_per_table=max_rows_per_table,
            allow_legacy_fallback=allow_legacy_fallback,
            ocr_file_selection=ocr_file_selection,
            deduplicate_ocr_tokens=deduplicate_ocr_tokens,
        )
        records.append(record)
        rows.extend(row_records)
        cells.extend(cell_records)
        values.extend(value_records)

    summary = summarize(records, rows, cells, values, source_records, source_quality_statuses)
    quality_status, fail_reasons = evaluate_quality(summary, thresholds)
    summary["quality_status"] = quality_status
    summary["quality_fail_reasons"] = fail_reasons
    status = STATUS_BUILT if quality_status == "PASS" else STATUS_NOT_READY
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_table_route_cell_extractor_v1.json"
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "quality_status": quality_status,
        "generated_at": utc_now(),
        "inputs": {
            "table_full_enclosure_bbox_reconstructor": str(table_full_enclosure_bbox_reconstructor_path),
            "table_ocr_bbox_enrichment": str(table_ocr_bbox_enrichment_path) if table_ocr_bbox_enrichment_path else None,
            "table_bbox_scoped_cell_extraction": str(table_bbox_scoped_cell_extraction_path) if table_bbox_scoped_cell_extraction_path else None,
            "ocr_root": str(ocr_root) if ocr_root else None,
            "max_ocr_files_per_table": max_ocr_files_per_table,
            "max_rows_per_table": max_rows_per_table,
            "allow_legacy_fallback": allow_legacy_fallback,
            "ocr_file_selection": ocr_file_selection,
            "deduplicate_ocr_tokens": deduplicate_ocr_tokens,
        },
        "summary": summary,
        "table_route_cell_extraction_records": records,
        "table_route_row_records": rows,
        "table_route_cell_records": cells,
        "table_route_value_records": values,
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
    write_json(report_path, report)
    write_jsonl(output_dir / "trace_net_table_route_cell_extractor_v1_records.jsonl", records)
    write_jsonl(output_dir / "trace_net_table_route_cell_extractor_v1_rows.jsonl", rows)
    write_jsonl(output_dir / "trace_net_table_route_cell_extractor_v1_cells.jsonl", cells)
    write_jsonl(output_dir / "trace_net_table_route_cell_extractor_v1_values.jsonl", values)
    write_json(output_dir / "trace_net_table_route_cell_extractor_v1_summary.json", summary)
    quality_payload = build_quality_payload(report, thresholds)
    write_json(output_dir / "trace_net_table_route_cell_extractor_v1_quality.json", quality_payload)
    write_json(output_dir / "trace_net_table_route_cell_extractor_v1_manifest.json", {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": report["generated_at"],
        "report_path": str(report_path),
        "quality_path": str(output_dir / "trace_net_table_route_cell_extractor_v1_quality.json"),
        "records_jsonl_path": str(output_dir / "trace_net_table_route_cell_extractor_v1_records.jsonl"),
        "rows_jsonl_path": str(output_dir / "trace_net_table_route_cell_extractor_v1_rows.jsonl"),
        "cells_jsonl_path": str(output_dir / "trace_net_table_route_cell_extractor_v1_cells.jsonl"),
        "values_jsonl_path": str(output_dir / "trace_net_table_route_cell_extractor_v1_values.jsonl"),
        "quality_status": quality_status,
    })
    return report


def thresholds_from_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "min_source_table_bbox_records": args.min_source_table_bbox_records,
        "min_extraction_records": args.min_extraction_records,
        "min_extraction_ready_tables": args.min_extraction_ready_tables,
        "min_review_only_skipped": args.min_review_only_skipped,
        "min_cell_extraction_attempted": args.min_cell_extraction_attempted,
        "min_cell_extraction_success_records": args.min_cell_extraction_success_records,
        "min_row_records": args.min_row_records,
        "min_cell_records": args.min_cell_records,
        "min_value_records": args.min_value_records,
        "min_part_number_candidates": args.min_part_number_candidates,
        "min_template_detected_tables": args.min_template_detected_tables,
        "min_part_number_coverage_template_tables": args.min_part_number_coverage_template_tables,
        "min_template_role_assigned_values": args.min_template_role_assigned_values,
        "max_ocr_selected_files_per_table_average": args.max_ocr_selected_files_per_table_average,
        "min_token_level_raw_selected_tables": args.min_token_level_raw_selected_tables,
        "max_line_raw_selected_tables": args.max_line_raw_selected_tables,
        "max_unsafe_records": args.max_unsafe_records,
        "max_answer_permission_count": args.max_answer_permission_count,
        "max_source_truth_mutation_allowed": args.max_source_truth_mutation_allowed,
        "require_table_full_enclosure_bbox_reconstructor_quality_pass": args.require_table_full_enclosure_bbox_reconstructor_quality_pass,
        "require_table_ocr_bbox_enrichment_quality_pass": args.require_table_ocr_bbox_enrichment_quality_pass,
        "require_table_bbox_scoped_cell_extraction_quality_pass": args.require_table_bbox_scoped_cell_extraction_quality_pass,
        "require_no_answer_permission": args.require_no_answer_permission,
    }


def print_summary(report: Mapping[str, Any]) -> None:
    summary = report.get("summary") or {}
    print("TRACE-Net Table Route Cell Extractor v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in (
        "source_table_bbox_record_count",
        "table_route_cell_extraction_record_count",
        "extraction_ready_table_count",
        "review_only_skipped_count",
        "cell_extraction_attempted_count",
        "cell_extraction_success_record_count",
        "ocr_source_file_table_count",
        "ocr_candidate_file_count_total",
        "ocr_selected_file_count_total",
        "ocr_raw_candidate_file_count_total",
        "ocr_token_level_raw_candidate_file_count_total",
        "ocr_line_raw_candidate_file_count_total",
        "ocr_derived_match_candidate_file_count_total",
        "ocr_raw_file_selected_table_count",
        "ocr_token_level_raw_file_selected_table_count",
        "ocr_line_raw_file_selected_table_count",
        "ocr_derived_match_file_selected_table_count",
        "ocr_best_file_selected_table_count",
        "ocr_raw_token_count_before_dedup",
        "ocr_duplicate_token_removed_count",
        "ocr_token_table_count",
        "legacy_fallback_table_count",
        "table_row_record_count",
        "table_cell_record_count",
        "table_value_record_count",
        "header_cell_count",
        "part_number_candidate_count",
        "template_detected_table_count",
        "list_effective_pages_template_count",
        "part_number_coverage_template_count",
        "ipl_split_column_template_count",
        "generic_table_template_count",
        "template_role_assigned_value_count",
        "repeated_cell_text_collapsed_count",
        "unsafe_table_route_cell_extraction_record_count",
        "answer_permission_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        print(f" {key}: {summary.get(key)}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net table route cell extraction artifact.")
    parser.add_argument("--table-full-enclosure-bbox-reconstructor", required=True, type=Path)
    parser.add_argument("--table-ocr-bbox-enrichment", type=Path)
    parser.add_argument("--table-bbox-scoped-cell-extraction", type=Path)
    parser.add_argument("--ocr-root", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-ocr-files-per-table", type=int, default=50)
    parser.add_argument("--ocr-file-selection", choices=("best", "all"), default="best")
    parser.add_argument("--disable-ocr-token-dedup", action="store_true")
    parser.add_argument("--max-rows-per-table", type=int, default=250)
    parser.add_argument("--allow-legacy-fallback", action="store_true")
    parser.add_argument("--min-source-table-bbox-records", type=int, default=1)
    parser.add_argument("--min-extraction-records", type=int, default=1)
    parser.add_argument("--min-extraction-ready-tables", type=int, default=1)
    parser.add_argument("--min-review-only-skipped", type=int, default=0)
    parser.add_argument("--min-cell-extraction-attempted", type=int, default=1)
    parser.add_argument("--min-cell-extraction-success-records", type=int, default=1)
    parser.add_argument("--min-row-records", type=int, default=1)
    parser.add_argument("--min-cell-records", type=int, default=1)
    parser.add_argument("--min-value-records", type=int, default=1)
    parser.add_argument("--min-part-number-candidates", type=int, default=0)
    parser.add_argument("--min-template-detected-tables", type=int)
    parser.add_argument("--min-part-number-coverage-template-tables", type=int)
    parser.add_argument("--min-template-role-assigned-values", type=int)
    parser.add_argument("--max-ocr-selected-files-per-table-average", type=float)
    parser.add_argument("--min-token-level-raw-selected-tables", type=int)
    parser.add_argument("--max-line-raw-selected-tables", type=int)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--max-answer-permission-count", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-table-full-enclosure-bbox-reconstructor-quality-pass", action="store_true")
    parser.add_argument("--require-table-ocr-bbox-enrichment-quality-pass", action="store_true")
    parser.add_argument("--require-table-bbox-scoped-cell-extraction-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    thresholds = thresholds_from_args(args)
    report = build_report(
        table_full_enclosure_bbox_reconstructor_path=args.table_full_enclosure_bbox_reconstructor,
        table_ocr_bbox_enrichment_path=args.table_ocr_bbox_enrichment,
        table_bbox_scoped_cell_extraction_path=args.table_bbox_scoped_cell_extraction,
        ocr_root=args.ocr_root,
        output_dir=args.output_dir,
        max_ocr_files_per_table=args.max_ocr_files_per_table,
        max_rows_per_table=args.max_rows_per_table,
        allow_legacy_fallback=args.allow_legacy_fallback,
        ocr_file_selection=args.ocr_file_selection,
        deduplicate_ocr_tokens=not args.disable_ocr_token_dedup,
        thresholds=thresholds,
    )
    print_summary(report)
    print(f" report_path: {args.output_dir / 'trace_net_table_route_cell_extractor_v1.json'}")
    if args.quality and report.get("quality_status") != "PASS":
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
