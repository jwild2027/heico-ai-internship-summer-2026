"""TRACE-Net visual callout to trusted OCR/table/figure evidence linker v1.

Patch B module for the image/visual route. It consumes structured LLaVA visual
summary cards and trusted OCR/table/figure-item artifacts, then links visual
figure/callout observations to proof records. LLaVA-only observations remain
LOW/unlinked and cannot prove part identity.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

MODULE_NAME = "trace_net_visual_callout_table_linker_v1"
STATUS_BUILT = "TRACE_NET_VISUAL_CALLOUT_TABLE_LINKER_BUILT"
DEFAULT_OUTPUT_DIR = "local_data/organization/trace_net/visual_callout_table_linker_v1"

FIGURE_PATTERN = re.compile(r"\b(?:FIG(?:URE)?\.?|ILLUS(?:TRATION)?\.?)\s*[-:#]?\s*([A-Z0-9]+(?:[-–][A-Z0-9]+)?)\b", re.IGNORECASE)
ITEM_PATTERN = re.compile(r"\b(?:ITEM|CALLOUT|INDEX\s+NO\.?|KEY\s+NO\.?|REF\.?\s+NO\.?|FIG(?:URE)?\.?\s+ITEM)\s*[-:#]?\s*([0-9A-Z]+)\b", re.IGNORECASE)
PART_PATTERN = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")
SIMPLE_TOKEN_PATTERN = re.compile(r"^[A-Z0-9]{1,5}(?:[-–][A-Z0-9]{1,5})?$")
DIMENSION_PATTERN = re.compile(r"(?:/|\bIN(?:CH|CHES)?\b|\bFT\b|\bMM\b|\bCM\b|\bDEG\b|°)", re.IGNORECASE)
STOP_CANDIDATE_TOKENS = {"NUMBER", "NO", "NONE", "NULL", "UNKNOWN", "N/A", "NA", "FIG", "FIGURE", "ITEM", "CALLOUT", "OR", "AND"}
PROMPT_ECHO_PHRASES = (
    "TRACE-NET",
    "LOCAL VISUAL",
    "INSPECT ONLY",
    "RETURN STRUCTURED JSON",
    "SUPPLIED PAGE IMAGE",
    "DO NOT CLAIM PART IDENTITY",
)

FIGURE_KEYS = {"figure", "fig", "figure_no", "figure_number", "figure_id", "figure_candidate", "illustration", "illus"}
ITEM_KEYS = {"item", "item_no", "item_number", "index_no", "index_number", "callout", "callout_no", "callout_number", "key_no", "ref_no"}
PART_KEYS = {"part", "part_number", "covered_part_number", "linked_part_number", "pn", "p_n", "dash_number"}
DESC_KEYS = {"description", "nomenclature", "name", "part_description", "item_description", "title"}
PAGE_ID_KEYS = ("page_id", "trace_page_id", "source_page_id", "page_key", "id")
PAGE_NUMBER_KEYS = ("page_number", "page_num", "page", "source_page_number", "physical_page_number")
CITATION_KEYS = ("citation_label", "evidence_label", "citation", "label", "record_id", "id")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
            if isinstance(value, Mapping):
                records.append(dict(value))
    return records


def normalize_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def compact_text(value: Any, max_chars: int = 1000) -> str:
    text = re.sub(r"\s+", " ", normalize_string(value)).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def safe_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = normalize_string(value)
    match = re.search(r"\d+", text)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def iter_dicts(value: Any) -> Iterator[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from iter_dicts(child)
    elif isinstance(value, list):
        for item in value:
            yield from iter_dicts(item)


def lower_key_map(record: Mapping[str, Any]) -> Dict[str, Any]:
    return {str(k).lower(): v for k, v in record.items()}


def first_from_keys(lower: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in lower and lower[key] not in (None, ""):
            return lower[key]
    return None


def parse_literal_candidate(value: Any) -> Any:
    """Best-effort parser for LLaVA strings that look like Python/JSON dicts/lists."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "[{":
        return value
    try:
        return json.loads(text)
    except Exception:
        pass
    try:
        return ast.literal_eval(text)
    except Exception:
        return value


def is_prompt_echo(text: str) -> bool:
    upper = text.upper()
    return any(phrase in upper for phrase in PROMPT_ECHO_PHRASES)


def is_dimension_like(text: str) -> bool:
    return bool(DIMENSION_PATTERN.search(text or ""))


def is_simple_candidate_token(text: str) -> bool:
    token = normalize_string(text).strip().strip("[]'\"")
    if not token or len(token) > 12:
        return False
    if token.upper() in STOP_CANDIDATE_TOKENS:
        return False
    if is_prompt_echo(token) or is_dimension_like(token):
        return False
    return bool(SIMPLE_TOKEN_PATTERN.match(token.upper()))


def flatten_candidate_strings(value: Any, role: str = "generic") -> List[str]:
    """Return normalized candidate strings without exploding dict text into fragments.

    Patch B1 split strings like ``{'component': 'battery', 'location': 'top'}``
    on commas, producing fake figure/callout records. B2 parses dict-like
    strings first and only keeps role-appropriate simple tokens or explicit
    FIG/ITEM mentions.
    """
    out: List[str] = []
    seen: set[str] = set()

    def add(text: Any, explicit: bool = False) -> None:
        raw = normalize_string(text).strip().strip("[]'\"")
        if not raw or is_prompt_echo(raw):
            return
        # Prefer explicit FIG/ITEM mentions even inside sentences.
        if role in {"figure", "generic"}:
            for match in FIGURE_PATTERN.finditer(raw):
                token = match.group(1).upper()
                key = (role, token)
                if key not in seen:
                    seen.add(key)
                    out.append(token)
        if role in {"callout", "generic"}:
            for match in ITEM_PATTERN.finditer(raw):
                token = match.group(1).upper()
                key = (role, token)
                if key not in seen:
                    seen.add(key)
                    out.append(token)
        if explicit or is_simple_candidate_token(raw):
            token = raw.upper() if raw.isalnum() else raw
            key = (role, norm_token(token))
            if norm_token(token) and key not in seen:
                seen.add(key)
                out.append(token)

    def walk(obj: Any) -> None:
        obj = parse_literal_candidate(obj)
        if isinstance(obj, Mapping):
            lower = {str(k).lower(): v for k, v in obj.items()}
            role_keys = FIGURE_KEYS if role == "figure" else ITEM_KEYS if role == "callout" else (FIGURE_KEYS | ITEM_KEYS | PART_KEYS | DESC_KEYS)
            extracted = False
            for key in role_keys:
                if key in lower:
                    walk(lower[key])
                    extracted = True
            # LLaVA often returns {'figure_id': 'fig_1'} or {'label': '1'}.
            if not extracted:
                for key in ("value", "candidate", "text", "number", "id", "label"):
                    if key in lower:
                        walk(lower[key])
                        extracted = True
            if not extracted:
                # Preserve explicit FIG/ITEM mentions in description text, but do not
                # turn arbitrary object descriptions into callouts.
                for key in ("description", "visible_text", "text"):
                    if key in lower:
                        add(lower[key], explicit=False)
            return
        if isinstance(obj, list):
            for item in obj:
                walk(item)
            return
        raw = normalize_string(obj)
        if not raw:
            return
        # Convert fig_1 only when it is explicitly being used as a figure field.
        if role == "figure":
            m = re.fullmatch(r"fig[_\- ]?([A-Z0-9]{1,5})", raw.strip(), flags=re.IGNORECASE)
            if m:
                add(m.group(1), explicit=True)
                return
        add(raw, explicit=False)

    walk(value)
    return out[:80]


def candidate_values(value: Any) -> List[str]:
    return flatten_candidate_strings(value, role="generic")


def norm_token(value: Any) -> str:
    return normalize_string(value).upper().replace(" ", "").replace(".", "").replace(":", "").replace("#", "")


def extract_page_id(record: Mapping[str, Any]) -> str:
    lower = lower_key_map(record)
    return normalize_string(first_from_keys(lower, PAGE_ID_KEYS))


def extract_page_number(record: Mapping[str, Any]) -> Optional[int]:
    lower = lower_key_map(record)
    page = safe_int(first_from_keys(lower, PAGE_NUMBER_KEYS))
    if page is not None:
        return page
    page_id = extract_page_id(record)
    match = re.search(r"p0*([0-9]{1,6})\b", page_id)
    return int(match.group(1)) if match else None


def extract_text_blob(record: Mapping[str, Any]) -> str:
    parts: List[str] = []
    for key, value in record.items():
        if isinstance(value, (str, int, float)):
            parts.append(f"{key}: {value}")
        elif isinstance(value, list) and len(value) <= 20:
            parts.append(f"{key}: {value}")
    return " ".join(parts)


def extract_figures_from_record(record: Mapping[str, Any]) -> List[str]:
    lower = lower_key_map(record)
    values: List[str] = []
    for key in FIGURE_KEYS:
        values.extend(candidate_values(lower.get(key)))
    text = extract_text_blob(record)
    values.extend(match.group(1).upper() for match in FIGURE_PATTERN.finditer(text))
    return unique_norm_values(values)


def extract_items_from_record(record: Mapping[str, Any]) -> List[str]:
    lower = lower_key_map(record)
    values: List[str] = []
    for key in ITEM_KEYS:
        values.extend(candidate_values(lower.get(key)))
    text = extract_text_blob(record)
    values.extend(match.group(1).upper() for match in ITEM_PATTERN.finditer(text))
    return unique_norm_values(values)


def extract_part_numbers_from_record(record: Mapping[str, Any]) -> List[str]:
    lower = lower_key_map(record)
    values: List[str] = []
    for key in PART_KEYS:
        values.extend(candidate_values(lower.get(key)))
    text = extract_text_blob(record)
    values.extend(match.group(0) for match in PART_PATTERN.finditer(text))
    return unique_norm_values(values)


def unique_norm_values(values: Iterable[Any]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = normalize_string(value).strip().strip("[]'\"")
        if not text or is_prompt_echo(text):
            continue
        key = norm_token(text)
        if key and key not in seen:
            seen.add(key)
            out.append(text.upper() if text.isalnum() else text)
    return out[:80]


def extract_description(record: Mapping[str, Any]) -> str:
    lower = lower_key_map(record)
    for key in DESC_KEYS:
        value = lower.get(key)
        if isinstance(value, str) and value.strip():
            return compact_text(value, 500)
    # Do not use huge OCR blobs as description; use short helpful context only.
    for key, value in lower.items():
        if any(hint in key for hint in ("description", "nomenclature", "title", "name")) and isinstance(value, str) and value.strip():
            return compact_text(value, 500)
    return ""


def extract_citation_label(record: Mapping[str, Any], fallback: str) -> str:
    lower = lower_key_map(record)
    value = first_from_keys(lower, CITATION_KEYS)
    text = normalize_string(value)
    return text[:80] if text else fallback


def looks_like_evidence_record(record: Mapping[str, Any]) -> bool:
    figures = extract_figures_from_record(record)
    items = extract_items_from_record(record)
    parts = extract_part_numbers_from_record(record)
    return bool(parts or (figures and items) or any(k.lower() in {"citation_ready", "source_trace_ready", "field", "value"} for k in record.keys()))


def extract_record_value(raw: Mapping[str, Any]) -> str:
    for key in ("normalized_value", "raw_value", "value", "text", "field_value"):
        value = raw.get(key)
        text = normalize_string(value)
        if text:
            return text
    return ""


def row_group_key(raw: Mapping[str, Any]) -> Optional[Tuple[str, str, int]]:
    source_trace = raw.get("source_trace") if isinstance(raw.get("source_trace"), Mapping) else {}
    table_id = normalize_string(raw.get("table_id") or source_trace.get("table_id"))
    row_index = safe_int(raw.get("row_index"))
    page_id = extract_page_id(raw)
    if table_id and row_index is not None:
        return (page_id, table_id, row_index)
    return None


def field_name(raw: Mapping[str, Any]) -> str:
    source_trace = raw.get("source_trace") if isinstance(raw.get("source_trace"), Mapping) else {}
    return normalize_string(raw.get("field_name") or source_trace.get("field_name")).lower()


def synthesize_table_row_evidence(payload: Any, source_path: Path, start_index: int) -> List[Dict[str, Any]]:
    """Build row-level trusted evidence from table_route_evidence_packager documents.

    The packager stores one record per table cell/value, so B1 saw an item
    value and a part number as separate evidence records. B2 groups by
    page_id/table_id/row_index so a figure-item quantity cell can link to the
    part-number and description cells from the same row.
    """
    docs = []
    if isinstance(payload, Mapping):
        docs = payload.get("evidence_documents") or payload.get("records") or payload.get("documents") or []
    if not isinstance(docs, list):
        return []

    groups: Dict[Tuple[str, str, int], List[Mapping[str, Any]]] = {}
    for raw in docs:
        if not isinstance(raw, Mapping):
            continue
        key = row_group_key(raw)
        if key is None:
            continue
        groups.setdefault(key, []).append(raw)

    records: List[Dict[str, Any]] = []
    for key, rows in groups.items():
        page_id, table_id, row_index = key
        page_number = extract_page_number(rows[0])
        figure_candidates: List[str] = []
        callout_candidates: List[str] = []
        part_numbers: List[str] = []
        descriptions: List[str] = []
        raw_preview_bits: List[str] = []
        citation_label = ""
        source_trace_ready = False
        citation_ready = False
        for raw in rows:
            fname = field_name(raw)
            value = extract_record_value(raw)
            if not value:
                continue
            raw_preview_bits.append(f"{fname}={value}")
            part_numbers.extend(PART_PATTERN.findall(value))
            if any(hint in fname for hint in ("part_number", "covered_part", "ipl_part", "pn")):
                part_numbers.extend(candidate_values(value))
            if any(hint in fname for hint in ("figure", "fig", "illustration")):
                # This field in IPL rows often means figure item or quantity. Keep
                # simple tokens as callouts; true figure numbers are only accepted
                # when explicit FIG/FIGURE text is present.
                figure_candidates.extend(match.group(1).upper() for match in FIGURE_PATTERN.finditer(value))
                callout_candidates.extend(flatten_candidate_strings(value, role="callout"))
            if any(hint in fname for hint in ("item", "callout", "index", "key", "ref")):
                callout_candidates.extend(flatten_candidate_strings(value, role="callout"))
            if any(hint in fname for hint in ("description", "nomenclature", "name")):
                descriptions.append(value)
            if not citation_label:
                citation_label = extract_citation_label(raw, f"E{start_index + len(records)}")
            source_trace_ready = source_trace_ready or bool(raw.get("source_trace_ready") or raw.get("source_trace") or page_id or page_number)
            citation_ready = citation_ready or bool(raw.get("citation_ready") or source_trace_ready)
        part_numbers = unique_norm_values(part_numbers)
        callout_candidates = [v for v in unique_norm_values(callout_candidates) if is_simple_candidate_token(v)]
        figure_candidates = [v for v in unique_norm_values(figure_candidates) if is_simple_candidate_token(v)]
        if not (callout_candidates and part_numbers):
            continue
        records.append({
            "evidence_record_id": f"trusted_table_row_evidence_{start_index + len(records):05d}",
            "source_artifact_path": str(source_path),
            "source_record_index": row_index,
            "citation_label": citation_label or f"E{start_index + len(records)}",
            "page_id": page_id,
            "page_number": page_number,
            "table_id": table_id,
            "row_index": row_index,
            "figure_candidates": figure_candidates,
            "callout_candidates": callout_candidates,
            "part_numbers": part_numbers,
            "description": compact_text("; ".join(descriptions), 500),
            "source_trace_ready": source_trace_ready,
            "citation_ready": citation_ready,
            "raw_preview": compact_text(" | ".join(raw_preview_bits), 1000),
            "evidence_shape": "table_row_group",
        })
    return records


def load_evidence_records(paths: Sequence[str]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for path_text in paths:
        if not path_text:
            continue
        path = Path(path_text)
        if not path.exists():
            continue
        payload = read_json(path)
        records.extend(synthesize_table_row_evidence(payload, path, len(records) + 1))
        for idx, raw in enumerate(iter_dicts(payload), start=1):
            # Skip container artifacts whose nested records merely make the parent
            # look like evidence; individual child records are traversed next.
            if isinstance(raw.get("records"), list) and not (extract_page_id(raw) or extract_page_number(raw) is not None):
                continue
            if isinstance(raw.get("evidence_documents"), list) and not (extract_page_id(raw) or extract_page_number(raw) is not None):
                continue
            if not looks_like_evidence_record(raw):
                continue
            figures = extract_figures_from_record(raw)
            items = [v for v in extract_items_from_record(raw) if is_simple_candidate_token(v)]
            parts = extract_part_numbers_from_record(raw)
            if not (figures or items or parts):
                continue
            page_id = extract_page_id(raw)
            page_number = extract_page_number(raw)
            source_trace_ready = bool(raw.get("source_trace_ready") or raw.get("citation_ready") or raw.get("source_trace") or page_id or page_number)
            records.append({
                "evidence_record_id": f"trusted_evidence_{len(records)+1:05d}",
                "source_artifact_path": str(path),
                "source_record_index": idx,
                "citation_label": extract_citation_label(raw, f"E{len(records)+1}"),
                "page_id": page_id,
                "page_number": page_number,
                "figure_candidates": figures,
                "callout_candidates": items,
                "part_numbers": parts,
                "description": extract_description(raw),
                "source_trace_ready": source_trace_ready,
                "citation_ready": bool(raw.get("citation_ready") or source_trace_ready),
                "raw_preview": compact_text(extract_text_blob(raw), 1000),
                "evidence_shape": "single_record",
            })
    # De-duplicate coarse repeated traversal hits.
    unique: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str, str, Optional[int], str, Any]] = set()
    for record in records:
        key = (
            ",".join(sorted(norm_token(v) for v in record.get("figure_candidates") or [])),
            ",".join(sorted(norm_token(v) for v in record.get("callout_candidates") or [])),
            ",".join(sorted(record.get("part_numbers") or [])),
            record.get("page_number"),
            record.get("source_artifact_path") or "",
            record.get("row_index"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return unique


def load_visual_records(path_text: str) -> List[Dict[str, Any]]:
    path = Path(path_text)
    if path.suffix.lower() == ".jsonl":
        return read_jsonl(path)
    payload = read_json(path)
    if isinstance(payload, Mapping):
        if isinstance(payload.get("records"), list):
            return [dict(r) for r in payload["records"] if isinstance(r, Mapping)]
        return [dict(payload)]
    if isinstance(payload, list):
        return [dict(r) for r in payload if isinstance(r, Mapping)]
    return []


def text_candidates_for_page(record: Mapping[str, Any], page_text_by_page: Optional[Mapping[Any, str]] = None) -> str:
    bits = [" ".join(flatten_candidate_strings(record.get("visible_text_candidates"), role="generic")), normalize_string(record.get("visual_summary"))]
    if page_text_by_page:
        page_id = normalize_string(record.get("page_id"))
        page_number = extract_page_number(record)
        for key in (page_id, page_number):
            if key in page_text_by_page:
                bits.append(normalize_string(page_text_by_page[key]))
    return " ".join(b for b in bits if b)


def visual_figures(record: Mapping[str, Any], page_text_by_page: Optional[Mapping[Any, str]] = None) -> List[str]:
    values = flatten_candidate_strings(record.get("figure_candidates"), role="figure")
    text = text_candidates_for_page(record, page_text_by_page)
    values.extend(match.group(1).upper() for match in FIGURE_PATTERN.finditer(text))
    return [v for v in unique_norm_values(values) if is_simple_candidate_token(v)]


def visual_callouts(record: Mapping[str, Any], page_text_by_page: Optional[Mapping[Any, str]] = None) -> List[str]:
    values = flatten_candidate_strings(record.get("callout_candidates"), role="callout")
    text = text_candidates_for_page(record, page_text_by_page)
    values.extend(match.group(1).upper() for match in ITEM_PATTERN.finditer(text))
    return [v for v in unique_norm_values(values) if is_simple_candidate_token(v)]


def load_page_text_map(paths: Sequence[str]) -> Dict[Any, str]:
    text_keys = {"ocr_text", "text", "page_text", "full_text", "raw_text", "extracted_text", "ocr_excerpt", "ocr_excerpt_preview", "content"}
    by_page: Dict[Any, List[str]] = {}
    for path_text in paths:
        if not path_text:
            continue
        path = Path(path_text)
        if not path.exists() or path.suffix.lower() != ".json":
            continue
        try:
            payload = read_json(path)
        except Exception:
            continue
        for raw in iter_dicts(payload):
            page_id = extract_page_id(raw)
            page_number = extract_page_number(raw)
            if not page_id and page_number is None:
                continue
            bits: List[str] = []
            lower = lower_key_map(raw)
            for key, value in lower.items():
                if key in text_keys or any(hint in key for hint in ("ocr", "text", "content")):
                    if isinstance(value, str) and value.strip() and len(value) < 20000:
                        bits.append(value)
            if not bits:
                continue
            blob = compact_text(" ".join(bits), 6000)
            for key in (page_id, page_number):
                if key:
                    by_page.setdefault(key, []).append(blob)
    return {key: compact_text(" ".join(values), 12000) for key, values in by_page.items()}


def evidence_unique_part_key(evidence: Mapping[str, Any]) -> Tuple[str, ...]:
    return tuple(sorted(str(p) for p in (evidence.get("part_numbers") or [])))


def choose_unique_evidence(candidates: Sequence[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    usable = [c for c in candidates if c.get("part_numbers")]
    if not usable:
        return candidates[0] if len(candidates) == 1 else None
    unique_parts = {evidence_unique_part_key(c) for c in usable}
    if len(unique_parts) == 1:
        # Prefer a row-group record because it carries item+part+description together.
        return sorted(usable, key=lambda c: 0 if c.get("evidence_shape") == "table_row_group" else 1)[0]
    return None


def match_evidence(figure: str, callout: str, visual_record: Mapping[str, Any], evidence_records: Sequence[Mapping[str, Any]], nearby_page_window: int = 2) -> Tuple[str, Optional[Mapping[str, Any]], str]:
    f = norm_token(figure)
    c = norm_token(callout)
    visual_page = extract_page_number(visual_record)
    figure_matches: List[Mapping[str, Any]] = []
    callout_same_page: List[Mapping[str, Any]] = []
    callout_nearby: List[Mapping[str, Any]] = []
    page_matches: List[Mapping[str, Any]] = []
    for evidence in evidence_records:
        evidence_figs = {norm_token(v) for v in evidence.get("figure_candidates") or []}
        evidence_calls = {norm_token(v) for v in evidence.get("callout_candidates") or []}
        ev_page = evidence.get("page_number")
        fig_ok = bool(f and f in evidence_figs)
        call_ok = bool(c and c in evidence_calls)
        page_ok = bool(visual_page is not None and ev_page == visual_page)
        nearby_ok = bool(visual_page is not None and isinstance(ev_page, int) and abs(ev_page - visual_page) <= nearby_page_window)
        if fig_ok and call_ok:
            if page_ok:
                return "HIGH", evidence, "figure_callout_and_page_match"
            figure_matches.append(evidence)
        elif call_ok and page_ok:
            callout_same_page.append(evidence)
        elif call_ok and nearby_ok:
            callout_nearby.append(evidence)
        elif fig_ok and page_ok:
            page_matches.append(evidence)
    if figure_matches:
        chosen = choose_unique_evidence(figure_matches)
        if chosen:
            return "HIGH", chosen, "figure_and_callout_match"
        return "LOW", None, "ambiguous_figure_callout_trusted_matches"
    if callout_same_page:
        chosen = choose_unique_evidence(callout_same_page)
        if chosen:
            return "MEDIUM", chosen, "callout_and_same_page_unique_trusted_row_match"
        return "LOW", None, "ambiguous_same_page_callout_trusted_matches"
    if callout_nearby:
        chosen = choose_unique_evidence(callout_nearby)
        if chosen:
            return "MEDIUM", chosen, "callout_and_nearby_unique_trusted_row_match"
        return "LOW", None, "ambiguous_nearby_callout_trusted_matches"
    if page_matches:
        chosen = choose_unique_evidence(page_matches)
        if chosen:
            return "MEDIUM", chosen, "figure_and_page_match"
        return "LOW", None, "ambiguous_figure_page_trusted_matches"
    return "LOW", None, "llava_only_no_trusted_match"


def bool_count(records: Iterable[Mapping[str, Any]], key: str) -> int:
    return sum(1 for r in records if bool(r.get(key)))


def build_link_records(visual_records: Sequence[Mapping[str, Any]], evidence_records: Sequence[Mapping[str, Any]], page_text_by_page: Optional[Mapping[Any, str]] = None, nearby_page_window: int = 2) -> List[Dict[str, Any]]:
    links: List[Dict[str, Any]] = []
    seq = 0
    for visual in visual_records:
        figures = visual_figures(visual, page_text_by_page)
        callouts = visual_callouts(visual, page_text_by_page)
        if not figures:
            figures = [""]
        if not callouts:
            callouts = [""]
        for figure in figures:
            for callout in callouts:
                if not figure and not callout:
                    continue
                seq += 1
                confidence, evidence, reason = match_evidence(figure, callout, visual, evidence_records, nearby_page_window=nearby_page_window)
                linked = evidence is not None and confidence in {"HIGH", "MEDIUM"}
                linked_parts = list(evidence.get("part_numbers") or []) if evidence else []
                description = normalize_string(evidence.get("description")) if evidence else ""
                page_number = visual.get("page_number")
                links.append({
                    "link_record_id": f"visual_callout_link_{seq:05d}",
                    "page_id": visual.get("page_id"),
                    "page_number": page_number,
                    "figure": figure,
                    "callout": callout,
                    "visual_summary_record_id": visual.get("record_id"),
                    "visual_confidence": visual.get("visual_confidence") or "unknown",
                    "visual_source": "llava",
                    "visual_observation_only": True,
                    "link_confidence": confidence,
                    "link_reason": reason,
                    "linked": linked,
                    "linked_evidence_record_id": evidence.get("evidence_record_id") if evidence else "",
                    "linked_citation_label": evidence.get("citation_label") if evidence else "",
                    "linked_page_id": evidence.get("page_id") if evidence else "",
                    "linked_page_number": evidence.get("page_number") if evidence else None,
                    "linked_part_numbers": linked_parts,
                    "linked_part_number": linked_parts[0] if linked_parts else "",
                    "linked_description": description,
                    "proof_source": "trusted_ocr_table_figure_item_evidence" if linked else "none_llava_only",
                    "proof_strength": "linked_visual_plus_table_or_ocr_proof" if confidence == "HIGH" else ("partial_visual_plus_nearby_trusted_evidence" if confidence == "MEDIUM" else "unlinked_visual_candidate"),
                    "source_trace_ready": bool(evidence.get("source_trace_ready")) if evidence else False,
                    "citation_ready": bool(evidence.get("citation_ready")) if evidence else False,
                    "requires_human_review": confidence == "LOW",
                    "unsafe": False,
                    "answer_permission": False,
                    "can_answer_directly": False,
                    "source_truth_mutation_allowed": False,
                    "postgres_write_attempt": False,
                    "qdrant_write_attempt": False,
                    "opensearch_write_attempt": False,
                    "opensearch_upload_attempt": False,
                    "write_attempt_count": 0,
                    "authority_note": "LLaVA-only observations cannot prove part number identity; linked OCR/table/figure-item evidence is required.",
                })
    return links


def evaluate_quality(records: Sequence[Mapping[str, Any]], args: argparse.Namespace) -> Tuple[str, List[Dict[str, Any]]]:
    checks: List[Dict[str, Any]] = []

    def add(name: str, passed: bool, observed: Any, expected: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "observed": observed, "expected": expected})

    add("visual_callout_link_record_count", len(records) >= args.min_visual_callout_records, len(records), f">= {args.min_visual_callout_records}")
    add("linked_callout_record_count", sum(1 for r in records if r.get("linked")) >= args.min_linked_callouts, sum(1 for r in records if r.get("linked")), f">= {args.min_linked_callouts}")
    add("source_trace_ready_count", bool_count(records, "source_trace_ready") >= args.min_source_trace_ready, bool_count(records, "source_trace_ready"), f">= {args.min_source_trace_ready}")
    add("unsafe_record_count", bool_count(records, "unsafe") <= args.max_unsafe, bool_count(records, "unsafe"), f"<= {args.max_unsafe}")
    add("answer_permission_count", bool_count(records, "answer_permission") <= args.max_answer_permission, bool_count(records, "answer_permission"), f"<= {args.max_answer_permission}")
    add("source_truth_mutation_allowed_count", bool_count(records, "source_truth_mutation_allowed") <= args.max_source_truth_mutation_allowed, bool_count(records, "source_truth_mutation_allowed"), f"<= {args.max_source_truth_mutation_allowed}")
    add("write_attempt_count", sum(int(r.get("write_attempt_count") or 0) for r in records) <= args.max_write_attempts, sum(int(r.get("write_attempt_count") or 0) for r in records), f"<= {args.max_write_attempts}")
    return ("PASS" if all(c["passed"] for c in checks) else "FAIL"), checks


def write_records_csv(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "link_record_id", "page_id", "page_number", "figure", "callout", "link_confidence", "linked", "linked_part_number", "linked_description", "linked_citation_label", "source_trace_ready", "citation_ready", "requires_human_review", "answer_permission", "source_truth_mutation_allowed",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in fields})


def build_linker(args: argparse.Namespace) -> Dict[str, Any]:
    visual_records = load_visual_records(args.llava_visual_summary_batch)
    evidence_paths = list(args.trusted_evidence_artifact or [])
    for optional_path in (args.ocr_route_scan_pack, args.table_exact_search_adapter, args.table_route_evidence_packager, args.figure_item_evidence):
        if optional_path:
            evidence_paths.append(optional_path)
    evidence_records = load_evidence_records(evidence_paths)
    page_text_by_page = load_page_text_map([args.ocr_route_scan_pack])
    link_records = build_link_records(visual_records, evidence_records, page_text_by_page=page_text_by_page, nearby_page_window=args.nearby_page_window)
    quality_status, checks = evaluate_quality(link_records, args)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    linker_path = output_dir / f"{MODULE_NAME}.json"
    qc_path = output_dir / f"{MODULE_NAME}_quality_check.json"
    records_csv_path = output_dir / f"{MODULE_NAME}_records.csv"
    links_jsonl_path = output_dir / f"{MODULE_NAME}_links.jsonl"
    unlinked_jsonl_path = output_dir / f"{MODULE_NAME}_unlinked_callouts.jsonl"
    readme_path = output_dir / "README_trace_net_visual_callout_table_linker_v1.md"

    high_count = sum(1 for r in link_records if r.get("link_confidence") == "HIGH")
    medium_count = sum(1 for r in link_records if r.get("link_confidence") == "MEDIUM")
    low_count = sum(1 for r in link_records if r.get("link_confidence") == "LOW")
    linked_count = sum(1 for r in link_records if r.get("linked"))
    linked_parts = sorted({part for r in link_records for part in (r.get("linked_part_numbers") or [])})

    summary = {
        "visual_summary_record_count": len(visual_records),
        "trusted_evidence_record_count": len(evidence_records),
        "ocr_page_text_record_count": len(page_text_by_page),
        "visual_callout_link_record_count": len(link_records),
        "linked_callout_record_count": linked_count,
        "linked_part_number_record_count": sum(1 for r in link_records if r.get("linked_part_number")),
        "unique_linked_part_number_count": len(linked_parts),
        "unlinked_callout_record_count": sum(1 for r in link_records if not r.get("linked")),
        "high_confidence_link_count": high_count,
        "medium_confidence_link_count": medium_count,
        "low_confidence_link_count": low_count,
        "source_trace_ready_count": bool_count(link_records, "source_trace_ready"),
        "citation_ready_count": bool_count(link_records, "citation_ready"),
        "requires_human_review_count": bool_count(link_records, "requires_human_review"),
        "unsafe_record_count": bool_count(link_records, "unsafe"),
        "answer_permission_count": bool_count(link_records, "answer_permission"),
        "source_truth_mutation_allowed_count": bool_count(link_records, "source_truth_mutation_allowed"),
        "postgres_write_attempt_count": bool_count(link_records, "postgres_write_attempt"),
        "qdrant_write_attempt_count": bool_count(link_records, "qdrant_write_attempt"),
        "opensearch_write_attempt_count": bool_count(link_records, "opensearch_write_attempt"),
        "opensearch_upload_attempt_count": bool_count(link_records, "opensearch_upload_attempt"),
        "write_attempt_count": sum(int(r.get("write_attempt_count") or 0) for r in link_records),
        "ready_for_visual_evidence_pack": quality_status == "PASS",
    }
    artifact_paths = {
        "linker": str(linker_path.as_posix()),
        "quality_check": str(qc_path.as_posix()),
        "records_csv": str(records_csv_path.as_posix()),
        "links_jsonl": str(links_jsonl_path.as_posix()),
        "unlinked_callouts_jsonl": str(unlinked_jsonl_path.as_posix()),
        "readme": str(readme_path.as_posix()),
    }
    linker = {
        "module_name": MODULE_NAME,
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "created_at_utc": utc_now(),
        "inputs": {
            "llava_visual_summary_batch": args.llava_visual_summary_batch,
            "trusted_evidence_artifacts": evidence_paths,
        },
        "authority_model": {
            "llava_role": "visual observation only",
            "proof_role": "trusted OCR/table/figure-item evidence proves part identity",
            "confidence_rule_high": "LLaVA figure/callout agrees with trusted figure/item evidence, preferably same page",
            "confidence_rule_medium": "partial agreement with same-page/nearby unique trusted evidence; LLaVA-only remains LOW",
            "confidence_rule_low": "LLaVA-only observation with no trusted evidence link",
        },
        "safety_contract": {
            "postgres_writes": False,
            "qdrant_writes": False,
            "opensearch_writes": False,
            "opensearch_uploads": False,
            "source_truth_mutation": False,
            "answer_permission": False,
        },
        "summary": summary,
        "quality_checks": checks,
        "artifact_paths": artifact_paths,
        "records": link_records,
    }
    qc = {
        "module_name": MODULE_NAME,
        "status": f"{STATUS_BUILT}_QUALITY_CHECKED",
        "quality_status": quality_status,
        "created_at_utc": linker["created_at_utc"],
        "summary": summary,
        "checks": checks,
        "artifact_paths": artifact_paths,
    }
    write_json(linker_path, linker)
    write_json(qc_path, qc)
    write_jsonl(links_jsonl_path, link_records)
    write_jsonl(unlinked_jsonl_path, [r for r in link_records if not r.get("linked")])
    write_records_csv(records_csv_path, link_records)
    readme_path.write_text(
        "# TRACE-Net Visual Callout Table Linker v1\n\n"
        "Links structured LLaVA visual observations to trusted OCR/table/figure-item evidence. "
        "LOW confidence records remain visual-only and cannot prove part identity.\n\n"
        f"Linker artifact: `{linker_path.as_posix()}`\n",
        encoding="utf-8",
    )
    return linker


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build TRACE-Net visual callout to table/OCR/figure linker v1.")
    p.add_argument("--llava-visual-summary-batch", required=True, help="Batch JSON or summaries JSONL from trace_net_llava_visual_summary_batch_v1.")
    p.add_argument("--trusted-evidence-artifact", action="append", default=[], help="Additional trusted evidence JSON artifact; can be repeated.")
    p.add_argument("--ocr-route-scan-pack", default="")
    p.add_argument("--table-exact-search-adapter", default="")
    p.add_argument("--table-route-evidence-packager", default="")
    p.add_argument("--figure-item-evidence", default="")
    p.add_argument("--nearby-page-window", type=int, default=2, help="Allow MEDIUM callout links to a unique trusted row within +/- this many pages.")
    p.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--min-visual-callout-records", type=int, default=1)
    p.add_argument("--min-linked-callouts", type=int, default=0)
    p.add_argument("--min-source-trace-ready", type=int, default=0)
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-answer-permission", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        linker = build_linker(args)
    except Exception as exc:
        print(f"ERROR {MODULE_NAME}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    summary = linker.get("summary", {})
    print(f"status={linker.get('status')}")
    print(f"quality_status={linker.get('quality_status')}")
    for key in (
        "visual_summary_record_count",
        "trusted_evidence_record_count",
        "visual_callout_link_record_count",
        "linked_callout_record_count",
        "linked_part_number_record_count",
        "high_confidence_link_count",
        "medium_confidence_link_count",
        "low_confidence_link_count",
        "source_trace_ready_count",
        "ready_for_visual_evidence_pack",
        "unsafe_record_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
        "write_attempt_count",
    ):
        print(f"{key}={summary.get(key)}")
    print(f"linker={linker.get('artifact_paths', {}).get('linker')}")
    return 0 if linker.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
