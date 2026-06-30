"""TRACE-Net visual callout to trusted evidence linker v2.

Patch B3 upgrade. It consumes:
- LLaVA visual summary cards (visual observations only)
- OCR figure/callout extractor records (exact visible labels)
- trusted OCR/table/figure evidence (proof rows)

It upgrades confidence only when trusted evidence supports the visual/OCR label.
LLaVA-only observations remain LOW and cannot prove part identity.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

MODULE_NAME = "trace_net_visual_callout_table_linker_v2"
STATUS_BUILT = "TRACE_NET_VISUAL_CALLOUT_TABLE_LINKER_V2_BUILT"
DEFAULT_OUTPUT_DIR = "local_data/organization/trace_net/visual_callout_table_linker_v2"

FIGURE_PATTERN = re.compile(r"\b(?:FIG(?:URE)?\.?|ILLUS(?:TRATION)?\.?)\s*[-:#]?\s*([A-Z0-9]+(?:[-–][A-Z0-9]+)?)\b", re.IGNORECASE)
ITEM_PATTERN = re.compile(r"\b(?:ITEM|CALLOUT|INDEX\s+NO\.?|KEY\s+NO\.?|REF\.?\s+NO\.?|FIG(?:URE)?\.?\s+ITEM)\s*[-:#]?\s*([0-9A-Z]{1,5})\b", re.IGNORECASE)
PART_PATTERN = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")
SIMPLE_TOKEN_PATTERN = re.compile(r"^[A-Z0-9]{1,5}(?:[-–][A-Z0-9]{1,5})?$")
DIMENSION_PATTERN = re.compile(r"(?:/|\bIN(?:CH|CHES)?\b|\bFT\b|\bMM\b|\bCM\b|\bDEG\b|°)", re.IGNORECASE)
PAGE_ID_KEYS = ("page_id", "trace_page_id", "source_page_id", "page_key", "id")
PAGE_NUMBER_KEYS = ("page_number", "page_num", "page", "source_page_number", "physical_page_number")
STOP_CANDIDATE_TOKENS = {"NUMBER", "NO", "NONE", "NULL", "UNKNOWN", "N/A", "NA", "FIG", "FIGURE", "ITEM", "CALLOUT", "OR", "AND"}
PROMPT_ECHO_PHRASES = ("TRACE-NET", "LOCAL VISUAL", "INSPECT ONLY", "RETURN STRUCTURED JSON", "SUPPLIED PAGE IMAGE", "DO NOT CLAIM PART IDENTITY")
DESC_FIELD_HINTS = ("nomenclature", "description", "desc", "part_name", "item_name", "part_description", "item_description")
BAD_DESC_HINTS = ("source_member", "member", "filename", "file_name", "path", "page_id", "source_page")
PART_FIELD_HINTS = ("part_number", "covered_part", "ipl_part", "pn", "p_n")
ITEM_FIELD_HINTS = ("figure_item", "item", "callout", "index", "key", "ref")


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


def extract_page_id(record: Mapping[str, Any]) -> str:
    return normalize_string(first_from_keys(lower_key_map(record), PAGE_ID_KEYS))


def extract_page_number(record: Mapping[str, Any]) -> Optional[int]:
    lower = lower_key_map(record)
    page = safe_int(first_from_keys(lower, PAGE_NUMBER_KEYS))
    if page is not None:
        return page
    page_id = extract_page_id(record)
    match = re.search(r"p0*([0-9]{1,6})\b", page_id)
    return int(match.group(1)) if match else None


def norm_token(value: Any) -> str:
    return normalize_string(value).upper().replace(" ", "").replace(".", "").replace(":", "").replace("#", "")


def is_prompt_echo(text: str) -> bool:
    upper = text.upper()
    return any(phrase in upper for phrase in PROMPT_ECHO_PHRASES)


def is_dimension_like(text: str) -> bool:
    return bool(DIMENSION_PATTERN.search(text or ""))


def is_simple_candidate_token(text: str) -> bool:
    token = normalize_string(text).strip().strip("[]'\"")
    if not token or len(token) > 12 or token.upper() in STOP_CANDIDATE_TOKENS:
        return False
    if is_prompt_echo(token) or is_dimension_like(token):
        return False
    return bool(SIMPLE_TOKEN_PATTERN.match(token.upper()))


def unique_norm_values(values: Iterable[Any]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = normalize_string(value).strip().strip("[]'\"")
        if not text or not is_simple_candidate_token(text):
            continue
        key = norm_token(text)
        if key and key not in seen:
            seen.add(key)
            out.append(text.upper() if text.isalnum() else text)
    return out[:80]




def unique_text_values(values: Iterable[Any]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = normalize_string(value).strip().strip("[]'\"")
        if not text:
            continue
        key = norm_token(text)
        if key and key not in seen:
            seen.add(key)
            out.append(text.upper() if text.isalnum() else text)
    return out[:80]

def flatten_candidates(value: Any) -> List[str]:
    out: List[str] = []
    if isinstance(value, list):
        for item in value:
            out.extend(flatten_candidates(item))
    elif isinstance(value, Mapping):
        for key in ("figure", "fig", "figure_number", "figure_id", "item", "callout", "number", "label", "value", "text", "candidate"):
            if key in value:
                out.extend(flatten_candidates(value[key]))
    else:
        text = normalize_string(value)
        if text:
            for m in FIGURE_PATTERN.finditer(text):
                out.append(m.group(1))
            for m in ITEM_PATTERN.finditer(text):
                out.append(m.group(1))
            if is_simple_candidate_token(text):
                out.append(text)
            elif re.fullmatch(r"fig[_\- ]?([A-Z0-9]{1,5})", text, flags=re.IGNORECASE):
                out.append(re.sub(r"(?i)^fig[_\- ]?", "", text))
    return unique_norm_values(out)


def extract_text_blob(record: Mapping[str, Any]) -> str:
    parts: List[str] = []
    for key, value in record.items():
        if isinstance(value, (str, int, float)):
            parts.append(f"{key}: {value}")
        elif isinstance(value, list) and len(value) <= 20:
            parts.append(f"{key}: {value}")
    return " ".join(parts)


def extract_figures_from_record(record: Mapping[str, Any]) -> List[str]:
    values: List[str] = []
    for key in ("figure_candidates", "ocr_figure_candidates", "llava_figure_candidates", "figure", "figure_number", "figure_id"):
        if key in record:
            values.extend(flatten_candidates(record.get(key)))
    text = extract_text_blob(record)
    values.extend(m.group(1) for m in FIGURE_PATTERN.finditer(text))
    return unique_norm_values(values)


def extract_callouts_from_record(record: Mapping[str, Any]) -> List[str]:
    values: List[str] = []
    for key in ("callout_candidates", "ocr_callout_candidates", "llava_callout_candidates", "item", "item_number", "callout", "callout_number"):
        if key in record:
            values.extend(flatten_candidates(record.get(key)))
    text = extract_text_blob(record)
    values.extend(m.group(1) for m in ITEM_PATTERN.finditer(text))
    return unique_norm_values(values)


def extract_record_value(raw: Mapping[str, Any]) -> str:
    for key in ("normalized_value", "raw_value", "value", "text", "field_value"):
        text = normalize_string(raw.get(key))
        if text:
            return text
    return ""


def source_trace_of(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    return raw.get("source_trace") if isinstance(raw.get("source_trace"), Mapping) else {}


def field_name(raw: Mapping[str, Any]) -> str:
    trace = source_trace_of(raw)
    return normalize_string(raw.get("field_name") or trace.get("field_name")).lower()


def row_group_key(raw: Mapping[str, Any]) -> Optional[Tuple[str, str, int]]:
    trace = source_trace_of(raw)
    table_id = normalize_string(raw.get("table_id") or trace.get("table_id"))
    row_index = safe_int(raw.get("row_index"))
    page_id = extract_page_id(raw)
    if table_id and row_index is not None:
        return (page_id, table_id, row_index)
    return None


def looks_like_bad_description(value: str) -> bool:
    text = normalize_string(value)
    lower = text.lower()
    if not text or PART_PATTERN.fullmatch(text) or is_simple_candidate_token(text):
        return True
    if any(lower.endswith(ext) for ext in (".tif", ".tiff", ".png", ".jpg", ".jpeg", ".json", ".zip")):
        return True
    if re.fullmatch(r"0*\d{1,8}\.(?:tif|tiff|png|jpg|jpeg)", lower):
        return True
    if lower.startswith("t_p_") or "/" in text or "\\" in text:
        return True
    return False


def choose_description(descriptions: Iterable[str]) -> Tuple[str, bool]:
    suppressed = False
    for value in descriptions:
        text = compact_text(value, 500)
        if looks_like_bad_description(text):
            suppressed = True
            continue
        return text, suppressed
    return "", suppressed


def load_page_text_map(path_text: str) -> Dict[Any, str]:
    if not path_text or not Path(path_text).exists():
        return {}
    payload = read_json(Path(path_text))
    page_text: Dict[Any, str] = {}
    for record in iter_dicts(payload):
        page_id = extract_page_id(record)
        page_number = extract_page_number(record)
        texts: List[str] = []
        for key, value in record.items():
            key_l = str(key).lower()
            if isinstance(value, str) and any(hint in key_l for hint in ("ocr", "text", "content", "preview")):
                if value.strip() and len(value) > 5:
                    texts.append(value)
        if not texts:
            continue
        blob = compact_text("\n".join(texts), 4000)
        for key in (page_id, page_number):
            if key not in (None, "") and len(blob) > len(page_text.get(key, "")):
                page_text[key] = blob
    return page_text


def figures_from_page_text(page_text_by_key: Mapping[Any, str], page_id: str, page_number: Optional[int]) -> List[str]:
    text = page_text_by_key.get(page_id, "") or (page_text_by_key.get(page_number, "") if page_number is not None else "")
    return unique_norm_values(m.group(1) for m in FIGURE_PATTERN.finditer(text or ""))


def synthesize_table_row_evidence(payload: Any, source_path: Path, start_index: int, page_text_by_key: Mapping[Any, str]) -> List[Dict[str, Any]]:
    docs = []
    if isinstance(payload, Mapping):
        docs = payload.get("evidence_documents") or payload.get("records") or payload.get("documents") or payload.get("exact_search_documents") or []
    elif isinstance(payload, list):
        docs = payload
    if not isinstance(docs, list):
        return []

    groups: Dict[Tuple[str, str, int], List[Mapping[str, Any]]] = {}
    for raw in docs:
        if not isinstance(raw, Mapping):
            continue
        key = row_group_key(raw)
        if key:
            groups.setdefault(key, []).append(raw)

    records: List[Dict[str, Any]] = []
    for (page_id, table_id, row_index), rows in groups.items():
        page_number = extract_page_number(rows[0])
        part_numbers: List[str] = []
        callouts: List[str] = []
        figures: List[str] = figures_from_page_text(page_text_by_key, page_id, page_number)
        descriptions: List[str] = []
        raw_bits: List[str] = []
        source_trace_ready = False
        citation_ready = False
        citation_label = ""
        filename_desc_suppressed = False
        for raw in rows:
            fname = field_name(raw)
            value = extract_record_value(raw)
            if not value:
                continue
            raw_bits.append(f"{fname}={value}")
            if PART_PATTERN.search(value) or any(h in fname for h in PART_FIELD_HINTS):
                part_numbers.extend(PART_PATTERN.findall(value))
            if any(h in fname for h in ITEM_FIELD_HINTS):
                callouts.extend(flatten_candidates(value))
                figures.extend(m.group(1) for m in FIGURE_PATTERN.finditer(value))
            if any(h in fname for h in DESC_FIELD_HINTS) and not any(h in fname for h in BAD_DESC_HINTS):
                descriptions.append(value)
            if not citation_label:
                citation_label = normalize_string(raw.get("citation_label") or raw.get("citation") or raw.get("evidence_id") or raw.get("source_value_id"))
            source_trace_ready = source_trace_ready or bool(raw.get("source_trace_ready") or raw.get("source_trace") or page_id or page_number)
            citation_ready = citation_ready or bool(raw.get("citation_ready") or source_trace_ready)
        part_numbers = unique_text_values(part_numbers)
        callouts = unique_norm_values(callouts)
        figures = unique_norm_values(figures)
        desc, suppressed = choose_description(descriptions)
        filename_desc_suppressed = filename_desc_suppressed or suppressed
        if not part_numbers:
            continue
        records.append({
            "evidence_record_id": f"trusted_table_row_evidence_v2_{start_index + len(records):05d}",
            "source_artifact_path": source_path.as_posix(),
            "page_id": page_id,
            "page_number": page_number,
            "table_id": table_id,
            "row_index": row_index,
            "figure_candidates": figures,
            "callout_candidates": callouts,
            "part_numbers": part_numbers,
            "description": desc,
            "description_quality": "trusted_nomenclature" if desc else "missing_not_filename",
            "filename_description_suppressed": filename_desc_suppressed,
            "citation_label": citation_label or f"E{start_index + len(records)}",
            "source_trace_ready": source_trace_ready,
            "citation_ready": citation_ready,
            "raw_preview": compact_text(" | ".join(raw_bits), 1000),
            "evidence_shape": "table_row_group_v2",
        })
    return records


def looks_like_evidence_record(record: Mapping[str, Any]) -> bool:
    text = extract_text_blob(record)
    return bool(PART_PATTERN.search(text) or record.get("source_trace_ready") or record.get("citation_ready"))


def load_evidence_records(paths: Sequence[str], page_text_by_key: Mapping[Any, str]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for path_text in paths:
        if not path_text:
            continue
        path = Path(path_text)
        if not path.exists():
            continue
        payload = read_json(path)
        records.extend(synthesize_table_row_evidence(payload, path, len(records) + 1, page_text_by_key))
        # Preserve already-row-shaped figure/item evidence if present.
        for raw in iter_dicts(payload):
            if not isinstance(raw, Mapping) or not looks_like_evidence_record(raw):
                continue
            part_numbers = unique_text_values(PART_PATTERN.findall(extract_text_blob(raw)))
            if not part_numbers:
                continue
            page_id = extract_page_id(raw)
            page_number = extract_page_number(raw)
            figures = unique_norm_values(extract_figures_from_record(raw) + figures_from_page_text(page_text_by_key, page_id, page_number))
            callouts = unique_norm_values(extract_callouts_from_record(raw))
            desc, suppressed = choose_description([normalize_string(raw.get(k)) for k in raw if any(h in str(k).lower() for h in DESC_FIELD_HINTS)])
            records.append({
                "evidence_record_id": f"trusted_nested_evidence_v2_{len(records)+1:05d}",
                "source_artifact_path": path.as_posix(),
                "page_id": page_id,
                "page_number": page_number,
                "figure_candidates": figures,
                "callout_candidates": callouts,
                "part_numbers": part_numbers,
                "description": desc,
                "description_quality": "trusted_nomenclature" if desc else "missing_not_filename",
                "filename_description_suppressed": suppressed,
                "citation_label": normalize_string(raw.get("citation_label") or raw.get("citation") or raw.get("evidence_id") or f"E{len(records)+1}"),
                "source_trace_ready": bool(raw.get("source_trace_ready") or raw.get("source_trace") or page_id or page_number),
                "citation_ready": bool(raw.get("citation_ready") or raw.get("source_trace_ready") or raw.get("source_trace")),
                "raw_preview": compact_text(extract_text_blob(raw), 1000),
                "evidence_shape": "nested_record_v2",
            })
    # Deduplicate by page/figure/callout/part/row.
    out: List[Dict[str, Any]] = []
    seen: set[Tuple[Any, ...]] = set()
    for rec in records:
        key = (rec.get("page_id"), rec.get("page_number"), tuple(rec.get("figure_candidates") or []), tuple(rec.get("callout_candidates") or []), tuple(rec.get("part_numbers") or []), rec.get("row_index"))
        if key not in seen:
            seen.add(key)
            out.append(rec)
    return out


def load_visual_records(path_text: str) -> List[Dict[str, Any]]:
    if not path_text or not Path(path_text).exists():
        return []
    payload = read_json(Path(path_text))
    if isinstance(payload, Mapping):
        raw = payload.get("records") or payload.get("visual_summary_records") or payload.get("summaries") or []
    elif isinstance(payload, list):
        raw = payload
    else:
        raw = []
    return [dict(r) for r in raw if isinstance(r, Mapping)]


def load_extractor_records(path_text: str) -> Dict[Tuple[str, Optional[int]], Dict[str, Any]]:
    if not path_text or not Path(path_text).exists():
        return {}
    payload = read_json(Path(path_text))
    raw = payload.get("records") if isinstance(payload, Mapping) else payload if isinstance(payload, list) else []
    out: Dict[Tuple[str, Optional[int]], Dict[str, Any]] = {}
    for rec in raw:
        if not isinstance(rec, Mapping):
            continue
        page_id = extract_page_id(rec)
        page_number = extract_page_number(rec)
        out[(page_id, page_number)] = dict(rec)
    return out


def get_extractor_for_visual(visual: Mapping[str, Any], by_key: Mapping[Tuple[str, Optional[int]], Mapping[str, Any]]) -> Mapping[str, Any]:
    page_id = extract_page_id(visual)
    page_number = extract_page_number(visual)
    return by_key.get((page_id, page_number)) or by_key.get(("", page_number)) or {}


def visual_candidates(visual: Mapping[str, Any], extractor: Mapping[str, Any], page_text_by_key: Mapping[Any, str]) -> Tuple[List[str], List[str], str]:
    page_id = extract_page_id(visual)
    page_number = extract_page_number(visual)
    figures: List[str] = []
    callouts: List[str] = []
    source_bits: List[str] = []
    for key in ("figure_candidates", "visible_text_candidates", "visual_summary"):
        vals = flatten_candidates(visual.get(key))
        if vals:
            figures.extend(vals)
            source_bits.append(f"llava:{key}")
    for key in ("callout_candidates",):
        vals = flatten_candidates(visual.get(key))
        if vals:
            callouts.extend(vals)
            source_bits.append(f"llava:{key}")
    for key in ("ocr_figure_candidates", "figure_candidates"):
        vals = flatten_candidates(extractor.get(key))
        if vals:
            figures.extend(vals)
            source_bits.append(f"ocr_extractor:{key}")
    for key in ("ocr_callout_candidates", "callout_candidates"):
        vals = flatten_candidates(extractor.get(key))
        if vals:
            callouts.extend(vals)
            source_bits.append(f"ocr_extractor:{key}")
    figures.extend(figures_from_page_text(page_text_by_key, page_id, page_number))
    return unique_norm_values(figures), unique_norm_values(callouts), ";".join(sorted(set(source_bits)))


def page_distance(a: Optional[int], b: Optional[int]) -> Optional[int]:
    if a is None or b is None:
        return None
    return abs(a - b)


def evidence_matches(e: Mapping[str, Any], figure: str, callout: str, visual_page: Optional[int], nearby_page_window: int) -> Tuple[str, str]:
    e_figs = {norm_token(v) for v in (e.get("figure_candidates") or [])}
    e_calls = {norm_token(v) for v in (e.get("callout_candidates") or [])}
    fig_match = bool(figure and norm_token(figure) in e_figs)
    call_match = bool(callout and norm_token(callout) in e_calls)
    distance = page_distance(visual_page, safe_int(e.get("page_number")))
    same_or_near = distance is not None and distance <= nearby_page_window
    same_page = distance == 0
    if fig_match and call_match and same_or_near:
        return "HIGH", "figure_callout_and_page_match"
    if fig_match and same_page and not callout:
        return "MEDIUM", "figure_and_page_match"
    if fig_match and same_or_near and not callout:
        return "MEDIUM", "figure_and_nearby_page_match"
    if call_match and same_page:
        return "MEDIUM", "callout_and_page_match"
    return "", ""


def evidence_part_key(evidence: Mapping[str, Any]) -> Tuple[str, ...]:
    return tuple(sorted(str(p) for p in (evidence.get("part_numbers") or []) if p))


def evidence_rank(evidence: Mapping[str, Any]) -> Tuple[int, int, int, int]:
    """Prefer row-group/source-traced evidence with usable descriptions.

    Multiple artifacts can describe the same page/figure/part. Treat those as
    one unique trusted match instead of declaring ambiguity just because the
    same proof was seen through OCR and table artifacts.
    """
    shape = normalize_string(evidence.get("evidence_shape"))
    has_desc = bool(evidence.get("description"))
    return (
        0 if shape.startswith("table_row_group") else 1,
        0 if evidence.get("source_trace_ready") else 1,
        0 if evidence.get("citation_ready") else 1,
        0 if has_desc else 1,
    )


def choose_unique_evidence(matches: Sequence[Tuple[Mapping[str, Any], str, str]]) -> Optional[Tuple[Mapping[str, Any], str, str]]:
    if not matches:
        return None
    usable = [m for m in matches if evidence_part_key(m[0])]
    if not usable:
        return matches[0] if len(matches) == 1 else None
    unique_parts = {evidence_part_key(m[0]) for m in usable}
    if len(unique_parts) != 1:
        return None
    return sorted(usable, key=lambda m: evidence_rank(m[0]))[0]


def choose_best_match(matches: Sequence[Tuple[Mapping[str, Any], str, str]]) -> Optional[Tuple[Mapping[str, Any], str, str]]:
    if not matches:
        return None
    high = [m for m in matches if m[1] == "HIGH"]
    if high:
        return choose_unique_evidence(high)
    medium = [m for m in matches if m[1] == "MEDIUM"]
    if medium:
        return choose_unique_evidence(medium)
    return None


def make_link_record(idx: int, visual: Mapping[str, Any], figure: str, callout: str, match: Optional[Tuple[Mapping[str, Any], str, str]], candidate_source: str) -> Dict[str, Any]:
    page_id = extract_page_id(visual)
    page_number = extract_page_number(visual)
    if match:
        evidence, confidence, reason = match
        parts = list(evidence.get("part_numbers") or [])
        linked_part = parts[0] if parts else ""
        description = normalize_string(evidence.get("description"))
        source_trace_ready = bool(evidence.get("source_trace_ready"))
        citation_ready = bool(evidence.get("citation_ready") or source_trace_ready)
        return {
            "link_record_id": f"visual_callout_link_v2_{idx:05d}",
            "page_id": page_id,
            "page_number": page_number,
            "figure": figure,
            "callout": callout,
            "candidate_source": candidate_source,
            "linked": True,
            "link_confidence": confidence,
            "link_reason": reason,
            "linked_part_number": linked_part,
            "linked_part_numbers": parts,
            "linked_description": description,
            "linked_description_quality": evidence.get("description_quality") or ("trusted_nomenclature" if description else "missing_not_filename"),
            "linked_citation_label": evidence.get("citation_label", ""),
            "linked_evidence_record_id": evidence.get("evidence_record_id", ""),
            "proof_source": "trusted_ocr_table_figure_item_evidence",
            "source_trace_ready": source_trace_ready,
            "citation_ready": citation_ready,
            "requires_human_review": confidence != "HIGH",
            "unsafe": False,
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "opensearch_upload_attempt": False,
            "write_attempt_count": 0,
        }
    return {
        "link_record_id": f"visual_callout_link_v2_{idx:05d}",
        "page_id": page_id,
        "page_number": page_number,
        "figure": figure,
        "callout": callout,
        "candidate_source": candidate_source,
        "linked": False,
        "link_confidence": "LOW",
        "link_reason": "visual_or_ocr_label_no_unique_trusted_match",
        "linked_part_number": "",
        "linked_part_numbers": [],
        "linked_description": "",
        "linked_description_quality": "none",
        "linked_citation_label": "",
        "linked_evidence_record_id": "",
        "proof_source": "none_visual_or_ocr_label_only",
        "source_trace_ready": False,
        "citation_ready": False,
        "requires_human_review": True,
        "unsafe": False,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
        "opensearch_upload_attempt": False,
        "write_attempt_count": 0,
    }


def build_link_records(visual_records: Sequence[Mapping[str, Any]], extractor_by_key: Mapping[Tuple[str, Optional[int]], Mapping[str, Any]], evidence_records: Sequence[Mapping[str, Any]], page_text_by_key: Mapping[Any, str], nearby_page_window: int) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for visual in visual_records:
        extractor = get_extractor_for_visual(visual, extractor_by_key)
        figures, callouts, source = visual_candidates(visual, extractor, page_text_by_key)
        if not figures:
            continue
        combos: List[Tuple[str, str]] = []
        if callouts:
            combos.extend((f, c) for f in figures for c in callouts)
        else:
            combos.extend((f, "") for f in figures)
        for figure, callout in combos[:50]:
            matches: List[Tuple[Mapping[str, Any], str, str]] = []
            visual_page = extract_page_number(visual)
            for e in evidence_records:
                confidence, reason = evidence_matches(e, figure, callout, visual_page, nearby_page_window)
                if confidence:
                    matches.append((e, confidence, reason))
            best = choose_best_match(matches)
            records.append(make_link_record(len(records) + 1, visual, figure, callout, best, source))
    return records


def bool_count(records: Sequence[Mapping[str, Any]], key: str) -> int:
    return sum(1 for r in records if bool(r.get(key)))


def evaluate_quality(records: Sequence[Mapping[str, Any]], args: argparse.Namespace) -> Tuple[str, List[Dict[str, Any]]]:
    summary = {
        "visual_callout_link_record_count": len(records),
        "linked_callout_record_count": bool_count(records, "linked"),
        "source_trace_ready_count": bool_count(records, "source_trace_ready"),
        "high_confidence_link_count": sum(1 for r in records if r.get("link_confidence") == "HIGH"),
        "medium_confidence_link_count": sum(1 for r in records if r.get("link_confidence") == "MEDIUM"),
        "low_confidence_link_count": sum(1 for r in records if r.get("link_confidence") == "LOW"),
        "unsafe_record_count": bool_count(records, "unsafe"),
        "answer_permission_count": bool_count(records, "answer_permission"),
        "source_truth_mutation_allowed_count": bool_count(records, "source_truth_mutation_allowed"),
        "write_attempt_count": sum(int(r.get("write_attempt_count") or 0) for r in records),
    }
    checks: List[Dict[str, Any]] = []

    def add(name: str, passed: bool, observed: Any, expected: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "observed": observed, "expected": expected})

    add("min_visual_callout_records", summary["visual_callout_link_record_count"] >= args.min_visual_callout_records, summary["visual_callout_link_record_count"], f">= {args.min_visual_callout_records}")
    add("min_linked_callouts", summary["linked_callout_record_count"] >= args.min_linked_callouts, summary["linked_callout_record_count"], f">= {args.min_linked_callouts}")
    add("min_source_trace_ready", summary["source_trace_ready_count"] >= args.min_source_trace_ready, summary["source_trace_ready_count"], f">= {args.min_source_trace_ready}")
    add("max_unsafe", summary["unsafe_record_count"] <= args.max_unsafe, summary["unsafe_record_count"], f"<= {args.max_unsafe}")
    add("max_answer_permission", summary["answer_permission_count"] <= args.max_answer_permission, summary["answer_permission_count"], f"<= {args.max_answer_permission}")
    add("max_source_truth_mutation_allowed", summary["source_truth_mutation_allowed_count"] <= args.max_source_truth_mutation_allowed, summary["source_truth_mutation_allowed_count"], f"<= {args.max_source_truth_mutation_allowed}")
    add("max_write_attempts", summary["write_attempt_count"] <= args.max_write_attempts, summary["write_attempt_count"], f"<= {args.max_write_attempts}")
    return ("PASS" if all(c["passed"] for c in checks) else "FAIL"), checks


def write_records_csv(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["link_record_id", "page_id", "page_number", "figure", "callout", "link_confidence", "linked", "linked_part_number", "linked_description", "linked_description_quality", "linked_citation_label", "source_trace_ready", "citation_ready", "requires_human_review", "answer_permission", "source_truth_mutation_allowed"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in records:
            writer.writerow({field: r.get(field, "") for field in fields})


def build_linker(args: argparse.Namespace) -> Dict[str, Any]:
    visual_records = load_visual_records(args.llava_visual_summary_batch)
    extractor_by_key = load_extractor_records(args.ocr_figure_callout_extractor)
    page_text_by_key = load_page_text_map(args.ocr_route_scan_pack)
    evidence_paths: List[str] = list(args.trusted_evidence_artifact or [])
    # B3.1: keep the OCR route scan pack in the trusted-evidence scan, not just
    # in the page-text map. B2 found useful page/figure/part proof there; v2
    # accidentally dropped that artifact and regressed to zero links.
    for p in (args.ocr_route_scan_pack, args.table_exact_search_adapter, args.table_route_evidence_packager, args.figure_item_evidence):
        if p:
            evidence_paths.append(p)
    evidence_records = load_evidence_records(evidence_paths, page_text_by_key)
    link_records = build_link_records(visual_records, extractor_by_key, evidence_records, page_text_by_key, args.nearby_page_window)
    quality_status, checks = evaluate_quality(link_records, args)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    linker_path = output_dir / f"{MODULE_NAME}.json"
    qc_path = output_dir / f"{MODULE_NAME}_quality_check.json"
    jsonl_path = output_dir / f"{MODULE_NAME}_links.jsonl"
    unlinked_path = output_dir / f"{MODULE_NAME}_unlinked_callouts.jsonl"
    csv_path = output_dir / f"{MODULE_NAME}_records.csv"
    readme_path = output_dir / "README_trace_net_visual_callout_table_linker_v2.md"

    linked_parts = sorted({r.get("linked_part_number") for r in link_records if r.get("linked_part_number")})
    summary = {
        "visual_summary_record_count": len(visual_records),
        "ocr_extractor_record_count": len(extractor_by_key),
        "trusted_evidence_record_count": len(evidence_records),
        "visual_callout_link_record_count": len(link_records),
        "linked_callout_record_count": bool_count(link_records, "linked"),
        "linked_part_number_record_count": sum(1 for r in link_records if r.get("linked_part_number")),
        "unique_linked_part_number_count": len(linked_parts),
        "high_confidence_link_count": sum(1 for r in link_records if r.get("link_confidence") == "HIGH"),
        "medium_confidence_link_count": sum(1 for r in link_records if r.get("link_confidence") == "MEDIUM"),
        "low_confidence_link_count": sum(1 for r in link_records if r.get("link_confidence") == "LOW"),
        "description_available_count": sum(1 for r in link_records if r.get("linked_description")),
        "description_missing_not_filename_count": sum(1 for r in link_records if r.get("linked_description_quality") == "missing_not_filename"),
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
    paths = {"linker": linker_path.as_posix(), "quality_check": qc_path.as_posix(), "links_jsonl": jsonl_path.as_posix(), "unlinked_callouts_jsonl": unlinked_path.as_posix(), "records_csv": csv_path.as_posix(), "readme": readme_path.as_posix()}
    payload = {
        "module_name": MODULE_NAME,
        "status": STATUS_BUILT,
        "quality_status": quality_status,
        "created_at_utc": utc_now(),
        "inputs": {"llava_visual_summary_batch": args.llava_visual_summary_batch, "ocr_figure_callout_extractor": args.ocr_figure_callout_extractor, "trusted_evidence_artifacts": evidence_paths},
        "authority_model": {
            "llava_role": "visual observation only",
            "ocr_label_role": "read visible figure/item labels, not final part proof",
            "proof_role": "trusted table/OCR/figure-item evidence proves part identity",
            "confidence_rule_high": "figure + callout/item + page/nearby trusted evidence unique match",
            "confidence_rule_medium": "figure/page or callout/page unique trusted match, but partial label alignment",
            "confidence_rule_low": "visual/OCR label only or ambiguous/no trusted evidence match",
        },
        "safety_contract": {"postgres_writes": False, "qdrant_writes": False, "opensearch_writes": False, "opensearch_uploads": False, "source_truth_mutation": False, "answer_permission": False},
        "summary": summary,
        "quality_checks": checks,
        "artifact_paths": paths,
        "records": link_records,
    }
    qc = {"module_name": MODULE_NAME, "status": f"{STATUS_BUILT}_QUALITY_CHECKED", "quality_status": quality_status, "created_at_utc": payload["created_at_utc"], "summary": summary, "checks": checks, "artifact_paths": paths}
    write_json(linker_path, payload)
    write_json(qc_path, qc)
    write_jsonl(jsonl_path, link_records)
    write_jsonl(unlinked_path, [r for r in link_records if not r.get("linked")])
    write_records_csv(csv_path, link_records)
    readme_path.write_text("# TRACE-Net Visual Callout Table Linker v2\n\nUses OCR figure/callout labels plus LLaVA visual observations to link to trusted table/figure evidence. LLaVA-only observations remain LOW.\n\n", encoding="utf-8")
    return payload


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build TRACE-Net visual callout table linker v2.")
    p.add_argument("--llava-visual-summary-batch", required=True)
    p.add_argument("--ocr-figure-callout-extractor", required=True)
    p.add_argument("--ocr-route-scan-pack", default="")
    p.add_argument("--trusted-evidence-artifact", action="append", default=[])
    p.add_argument("--table-exact-search-adapter", default="")
    p.add_argument("--table-route-evidence-packager", default="")
    p.add_argument("--figure-item-evidence", default="")
    p.add_argument("--nearby-page-window", type=int, default=2)
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
        artifact = build_linker(args)
    except Exception as exc:
        print(f"ERROR {MODULE_NAME}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    summary = artifact.get("summary", {})
    print(f"status={artifact.get('status')}")
    print(f"quality_status={artifact.get('quality_status')}")
    for key in ("visual_summary_record_count", "ocr_extractor_record_count", "trusted_evidence_record_count", "visual_callout_link_record_count", "linked_callout_record_count", "linked_part_number_record_count", "high_confidence_link_count", "medium_confidence_link_count", "low_confidence_link_count", "description_available_count", "source_trace_ready_count", "ready_for_visual_evidence_pack", "unsafe_record_count", "answer_permission_count", "source_truth_mutation_allowed_count", "write_attempt_count"):
        print(f"{key}={summary.get(key)}")
    print(f"linker={artifact.get('artifact_paths', {}).get('linker')}")
    return 0 if artifact.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
