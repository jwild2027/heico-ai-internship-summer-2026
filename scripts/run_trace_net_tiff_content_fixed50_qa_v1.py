#!/usr/bin/env python3
"""Run a fixed 50-question QA pass over TIFF-derived TRACE-Net content artifacts.

This runner is intentionally about *page/image content* extracted from TIFF pages:
OCR text, visual/page summaries, table signals, nomenclature, part numbers, ATA
numbers, and page/document references. It does not ask questions about ZIP byte
sizes, TIFF compression, endian values, or metadata.xml implementation details.

The runner is read-only. It scans existing artifacts under local_data and writes
simple Question/Answer outputs for human review.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

MODULE = "trace_net_tiff_content_fixed50_qa_v1"
VERSION = "v1"

TEXT_FILE_SUFFIXES = {".json", ".jsonl", ".txt"}
SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "tmp",
}
CONTENT_KEY_HINTS = (
    "text",
    "ocr",
    "summary",
    "caption",
    "title",
    "label",
    "nomenclature",
    "part",
    "figure",
    "route",
    "page_type",
    "warning",
    "caution",
    "note",
    "field_name",
    "normalized_value",
    "value",
)

ATA_RE = re.compile(r"\b(?:ATA\s*)?(2\d)[\s\-–_]*(\d{2})[\s\-–_]*(\d{2})\b", re.IGNORECASE)
FIGURE_RE = re.compile(r"\b(?:FIG(?:URE)?\.?\s*)(\d{1,4})\b", re.IGNORECASE)
PART_RE = re.compile(r"\b(?:[A-Z]{1,4})?\d{2,6}[- ][A-Z0-9]{2,8}(?:[- ][A-Z0-9]{2,8})?\b")
PAGE_NUM_RE = re.compile(r"(?:^|[_\-./\\])p(?:age)?0*(\d{1,5})(?:\D|$)", re.IGNORECASE)


@dataclass
class ContentRecord:
    source_path: str
    source_kind: str
    page_id: str = ""
    page_number: int | None = None
    document_id: str = ""
    route: str = ""
    text: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContentIndex:
    artifact_root: Path
    sample_zip: Path | None
    records: list[ContentRecord]
    tiff_names: list[str]
    by_page: dict[str, list[ContentRecord]]
    all_text: str
    page_text: dict[str, str]
    metrics: dict[str, Any]


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _shorten(text: str, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _norm_token(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def _infer_page_number(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        if value.isdigit():
            return int(value)
        match = PAGE_NUM_RE.search(value)
        if match:
            return int(match.group(1))
    return None


def _first_present(data: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def _flatten_content(data: Any, key_path: str = "") -> list[tuple[str, str]]:
    """Collect readable strings likely to describe TIFF page content."""
    out: list[tuple[str, str]] = []
    if isinstance(data, dict):
        for key, value in data.items():
            kp = f"{key_path}.{key}" if key_path else str(key)
            key_l = str(key).lower()
            if isinstance(value, (dict, list)):
                out.extend(_flatten_content(value, kp))
            else:
                value_s = _safe_str(value)
                if not value_s:
                    continue
                if any(hint in key_l for hint in CONTENT_KEY_HINTS):
                    out.append((kp, value_s))
                elif ATA_RE.search(value_s) or FIGURE_RE.search(value_s) or PART_RE.search(value_s):
                    out.append((kp, value_s))
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            out.extend(_flatten_content(item, f"{key_path}[{idx}]"))
    elif isinstance(data, str):
        if ATA_RE.search(data) or FIGURE_RE.search(data) or PART_RE.search(data):
            out.append((key_path, data))
    return out


def _iter_objects_from_json_file(path: Path) -> Iterable[Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if not text.strip():
        return []
    if path.suffix.lower() == ".jsonl":
        objects = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                objects.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return objects
    try:
        return [json.loads(text)]
    except json.JSONDecodeError:
        return []


def _walk_json_objects(obj: Any) -> Iterable[dict[str, Any]]:
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _walk_json_objects(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_json_objects(item)


def _infer_source_kind(path: Path, data: dict[str, Any] | None = None) -> str:
    joined = f"{path.as_posix()} {json.dumps(data or {}, ensure_ascii=False)[:600]}".lower()
    if "visual" in joined or "figure" in joined or "callout" in joined:
        return "visual"
    if "table" in joined or "cell" in joined or "row" in joined:
        return "table"
    if "ocr" in joined:
        return "ocr"
    if "context_v2" in joined or "v2_summary" in joined or "page_context" in joined:
        return "page_context"
    if "route" in joined:
        return "route"
    return "artifact"


def _record_from_dict(path: Path, data: dict[str, Any]) -> ContentRecord | None:
    content_pairs = _flatten_content(data)
    if not content_pairs:
        return None
    text_parts = []
    for key, value in content_pairs:
        if value:
            text_parts.append(f"{key}: {value}")
    text = "\n".join(text_parts)
    if not text.strip():
        return None

    page_id = _safe_str(
        _first_present(
            data,
            (
                "page_id",
                "source_page_id",
                "pageId",
                "page",
                "source_page",
                "trace_page_id",
            ),
        )
    )
    page_number = None
    for key in ("page_number", "page_num", "page_index", "page", "page_id", "source_page_id", "file_id", "tiff_name"):
        if key in data:
            page_number = _infer_page_number(data[key])
            if page_number is not None:
                break
    if not page_id:
        page_id = _safe_str(_first_present(data, ("file_id", "tiff_name", "source_tiff", "image_name")))
    if not page_id:
        page_id = path.stem

    document_id = _safe_str(
        _first_present(data, ("document_id", "doc_id", "manual_id", "source_document", "title"))
    )
    route = _safe_str(_first_present(data, ("route", "primary_route", "page_route", "route_type", "page_type")))

    return ContentRecord(
        source_path=path.as_posix(),
        source_kind=_infer_source_kind(path, data),
        page_id=page_id,
        page_number=page_number,
        document_id=document_id,
        route=route,
        text=text,
        raw=data,
    )


def _records_from_txt(path: Path) -> list[ContentRecord]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if not text.strip():
        return []
    if not (ATA_RE.search(text) or FIGURE_RE.search(text) or PART_RE.search(text) or any(w in text.lower() for w in ("nomenclature", "warning", "caution", "note", "table"))):
        return []
    return [
        ContentRecord(
            source_path=path.as_posix(),
            source_kind=_infer_source_kind(path),
            page_id=path.stem,
            page_number=_infer_page_number(path.name),
            text=text,
        )
    ]


def _iter_artifact_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            rel_parts = set(path.relative_to(root).parts)
        except ValueError:
            rel_parts = set(path.parts)
        if rel_parts & SKIP_DIR_NAMES:
            continue
        if path.suffix.lower() in TEXT_FILE_SUFFIXES:
            files.append(path)
    return files


def _read_tiff_names(sample_zip: Path | None) -> list[str]:
    if not sample_zip or not sample_zip.exists():
        return []
    names: list[str] = []
    try:
        with zipfile.ZipFile(sample_zip) as zf:
            for name in zf.namelist():
                if name.lower().endswith((".tif", ".tiff")):
                    names.append(name)
    except zipfile.BadZipFile:
        return []
    return sorted(names)


def build_content_index(artifact_root: Path, sample_zip: Path | None = None, max_files: int = 20000) -> ContentIndex:
    records: list[ContentRecord] = []
    files = list(_iter_artifact_files(artifact_root))[:max_files]
    for path in files:
        if path.suffix.lower() in {".json", ".jsonl"}:
            for obj in _iter_objects_from_json_file(path):
                for data in _walk_json_objects(obj):
                    rec = _record_from_dict(path, data)
                    if rec is not None:
                        records.append(rec)
        elif path.suffix.lower() == ".txt":
            records.extend(_records_from_txt(path))

    by_page: dict[str, list[ContentRecord]] = defaultdict(list)
    page_text: dict[str, str] = defaultdict(str)
    for rec in records:
        page_key = rec.page_id or f"page_{rec.page_number or 'unknown'}"
        by_page[page_key].append(rec)
        page_text[page_key] += "\n" + rec.text

    all_text = "\n".join(rec.text for rec in records)
    tiff_names = _read_tiff_names(sample_zip)
    metrics = {
        "artifact_file_count_scanned": len(files),
        "content_record_count": len(records),
        "content_page_count": len(by_page),
        "zip_tiff_count": len(tiff_names),
        "sample_zip": sample_zip.as_posix() if sample_zip else "",
        "artifact_root": artifact_root.as_posix(),
    }
    return ContentIndex(
        artifact_root=artifact_root,
        sample_zip=sample_zip,
        records=records,
        tiff_names=tiff_names,
        by_page=dict(by_page),
        all_text=all_text,
        page_text=dict(page_text),
        metrics=metrics,
    )


def _page_sort_key(page_id: str) -> tuple[int, str]:
    pn = _infer_page_number(page_id)
    return (pn if pn is not None else 999999, page_id)


def _page_label(page_id: str, index: ContentIndex) -> str:
    records = index.by_page.get(page_id, [])
    page_nums = [r.page_number for r in records if r.page_number is not None]
    if page_nums:
        return f"page {min(page_nums)} ({page_id})"
    return page_id


def _find_pages(index: ContentIndex, patterns: list[str | re.Pattern[str]], kinds: set[str] | None = None, limit: int = 10) -> list[tuple[str, str]]:
    compiled: list[re.Pattern[str]] = []
    for pattern in patterns:
        if isinstance(pattern, str):
            compiled.append(re.compile(re.escape(pattern), re.IGNORECASE))
        else:
            compiled.append(pattern)
    matches: list[tuple[str, str]] = []
    for page_id in sorted(index.by_page.keys(), key=_page_sort_key):
        records = index.by_page[page_id]
        if kinds and not any(r.source_kind in kinds for r in records):
            continue
        text = "\n".join(r.text for r in records)
        if any(p.search(text) for p in compiled):
            snippet = ""
            for p in compiled:
                m = p.search(text)
                if m:
                    start = max(0, m.start() - 90)
                    end = min(len(text), m.end() + 140)
                    snippet = _shorten(text[start:end], 260)
                    break
            matches.append((_page_label(page_id, index), snippet))
            if len(matches) >= limit:
                break
    return matches


def _format_page_matches(matches: list[tuple[str, str]], empty: str) -> str:
    if not matches:
        return empty
    parts = []
    for page, snippet in matches:
        if snippet:
            parts.append(f"{page}: {_shorten(snippet, 220)}")
        else:
            parts.append(page)
    return "; ".join(parts)


def _extract_ata_numbers(index: ContentIndex) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for page_id, text in index.page_text.items():
        for match in ATA_RE.finditer(text):
            ata = f"ATA {match.group(1)}-{match.group(2)}-{match.group(3)}"
            out[ata].add(_page_label(page_id, index))
    return dict(out)


def _extract_figures(index: ContentIndex) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for page_id, text in index.page_text.items():
        for match in FIGURE_RE.finditer(text):
            out[f"Figure {match.group(1)}"].add(_page_label(page_id, index))
    return dict(out)


def _extract_parts(index: ContentIndex) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for page_id, text in index.page_text.items():
        for match in PART_RE.finditer(text):
            token = match.group(0).strip(" .,:;()[]{}")
            if len(_norm_token(token)) < 6:
                continue
            out[token.upper()].add(_page_label(page_id, index))
    return dict(out)


def _extract_nomenclature(index: ContentIndex, visual_only: bool = False, limit: int = 25) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for rec in index.records:
        if visual_only and rec.source_kind != "visual":
            continue
        if "nomenclature" not in rec.text.lower() and "normalized_value" not in rec.text.lower():
            continue
        lines = [ln.strip() for ln in rec.text.splitlines() if ln.strip()]
        for line in lines:
            if "nomenclature" in line.lower() or "normalized_value" in line.lower():
                value = re.sub(r"^[A-Za-z0-9_.\[\]-]+:\s*", "", line).strip()
                value = _shorten(value, 120)
                if len(value) < 3:
                    continue
                key = (value.lower(), rec.page_id)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append((_page_label(rec.page_id, index), value))
                if len(candidates) >= limit:
                    return candidates
    return candidates


def _answer_nomenclatures(index: ContentIndex) -> str:
    visual = _extract_nomenclature(index, visual_only=True, limit=20)
    label = "visual/image nomenclature"
    rows = visual
    if not rows:
        rows = _extract_nomenclature(index, visual_only=False, limit=20)
        label = "nomenclature"
    if not rows:
        return "No nomenclature values were found in the scanned TIFF-derived content artifacts."
    return f"Found {len(rows)} {label} candidates: " + "; ".join(f"{page}: {value}" for page, value in rows)


def _answer_ata_starting_with_2(index: ContentIndex) -> str:
    atas = _extract_ata_numbers(index)
    if not atas:
        return "No ATA number starting with 2 was found in the scanned TIFF-derived content artifacts."
    first_items = sorted(atas.items())[:10]
    return "; ".join(f"{ata} appears on {', '.join(sorted(pages)[:5])}" for ata, pages in first_items)


def _answer_blank_table(index: ContentIndex) -> str:
    patterns = [re.compile(r"\bblank\b.{0,80}\btable\b|\btable\b.{0,80}\bblank\b", re.IGNORECASE)]
    matches = _find_pages(index, patterns, kinds={"table", "route", "page_context", "ocr", "artifact"}, limit=10)
    if matches:
        return _format_page_matches(matches, "")

    # Fallback: table-routed pages with sparse table text.
    sparse: list[tuple[str, str]] = []
    for page_id in sorted(index.by_page.keys(), key=_page_sort_key):
        records = index.by_page[page_id]
        table_like = [r for r in records if r.source_kind == "table" or "table" in (r.route or "").lower() or "table" in r.text.lower()]
        if not table_like:
            continue
        combined = " ".join(r.text for r in table_like)
        has_cell_value = bool(re.search(r"cell|row|part|nomenclature|\d{2,}", combined, re.IGNORECASE))
        if not has_cell_value or len(combined.strip()) < 180:
            sparse.append((_page_label(page_id, index), _shorten(combined, 180)))
        if len(sparse) >= 10:
            break
    if sparse:
        return "No explicit 'blank table' label was found, but these table-like pages have sparse extracted content and may need review: " + _format_page_matches(sparse, "")
    return "No blank-table evidence was found in the scanned TIFF-derived content artifacts."


def _answer_figures(index: ContentIndex, figure_num: str | None = None) -> str:
    if figure_num:
        matches = _find_pages(index, [re.compile(rf"\b(?:FIG(?:URE)?\.?\s*){re.escape(figure_num)}\b", re.IGNORECASE)], limit=10)
        return _format_page_matches(matches, f"Figure {figure_num} was not found in the scanned TIFF-derived content artifacts.")
    figures = _extract_figures(index)
    if not figures:
        return "No figure references were found in the scanned TIFF-derived content artifacts."
    top = sorted(figures.items(), key=lambda kv: (int(re.search(r"\d+", kv[0]).group(0)), kv[0]))[:20]
    return "; ".join(f"{fig}: {', '.join(sorted(pages)[:4])}" for fig, pages in top)


def _answer_part_numbers(index: ContentIndex) -> str:
    parts = _extract_parts(index)
    if not parts:
        return "No part-number-like values were found in the scanned TIFF-derived content artifacts."
    ranked = sorted(parts.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:25]
    return "; ".join(f"{part}: {', '.join(sorted(pages)[:4])}" for part, pages in ranked)


def _answer_table_pages(index: ContentIndex) -> str:
    pages = []
    for page_id, records in sorted(index.by_page.items(), key=lambda kv: _page_sort_key(kv[0])):
        if any(r.source_kind == "table" or "table" in (r.route or "").lower() or "table" in r.text.lower() for r in records):
            pages.append(_page_label(page_id, index))
        if len(pages) >= 25:
            break
    if not pages:
        return "No table-related pages were found in the scanned TIFF-derived content artifacts."
    return f"Found table-related content on these pages, first {len(pages)} shown: " + ", ".join(pages)


def _answer_visual_pages(index: ContentIndex) -> str:
    pages = []
    for page_id, records in sorted(index.by_page.items(), key=lambda kv: _page_sort_key(kv[0])):
        if any(r.source_kind == "visual" or "figure" in r.text.lower() or "visual" in r.text.lower() for r in records):
            pages.append(_page_label(page_id, index))
        if len(pages) >= 25:
            break
    if not pages:
        return "No visual/figure-related pages were found in the scanned TIFF-derived content artifacts."
    return f"Found visual/figure content on these pages, first {len(pages)} shown: " + ", ".join(pages)


def _answer_keyword(index: ContentIndex, keyword: str, label: str | None = None, limit: int = 10) -> str:
    matches = _find_pages(index, [keyword], limit=limit)
    return _format_page_matches(matches, f"No {label or keyword} evidence was found in the scanned TIFF-derived content artifacts.")


def _answer_regex(index: ContentIndex, pattern: str, empty: str, limit: int = 10) -> str:
    matches = _find_pages(index, [re.compile(pattern, re.IGNORECASE)], limit=limit)
    return _format_page_matches(matches, empty)


def _answer_page_sample(index: ContentIndex, ordinal: int) -> str:
    page_ids = sorted(index.by_page.keys(), key=_page_sort_key)
    if not page_ids:
        return "No page-level content artifacts were found."
    if ordinal < 1 or ordinal > len(page_ids):
        return f"Only {len(page_ids)} page-level content entries were found; page sample {ordinal} is outside that range."
    page_id = page_ids[ordinal - 1]
    text = _shorten(index.page_text.get(page_id, ""), 420)
    return f"{_page_label(page_id, index)} content sample: {text or 'No readable text captured.'}"


def _answer_content_summary(index: ContentIndex) -> str:
    kinds = Counter(r.source_kind for r in index.records)
    return (
        f"Scanned {index.metrics['artifact_file_count_scanned']} artifact files under {index.artifact_root}; "
        f"found {len(index.records)} TIFF-derived content records across {len(index.by_page)} page keys. "
        f"Record types: " + ", ".join(f"{k}={v}" for k, v in sorted(kinds.items()))
    )


def _fixed_questions() -> list[tuple[str, Callable[[ContentIndex], str]]]:
    return [
        ("What TIFF-derived content artifacts were searched?", _answer_content_summary),
        ("What ATA number starting with 2 appears in the scanned page content, and what page/document is it on?", _answer_ata_starting_with_2),
        ("What are the nomenclatures of the images in this document?", _answer_nomenclatures),
        ("What page has a blank table or table-like blank candidate?", _answer_blank_table),
        ("Which pages contain table-related content?", _answer_table_pages),
        ("Which pages contain visual/image/figure-related content?", _answer_visual_pages),
        ("Which figure references appear in the scanned page content?", lambda idx: _answer_figures(idx)),
        ("Which page contains Figure 69?", lambda idx: _answer_figures(idx, "69")),
        ("What pages mention paper towel dispenser?", lambda idx: _answer_keyword(idx, "paper towel dispenser", "paper towel dispenser")),
        ("What part numbers are found in the scanned page content?", _answer_part_numbers),
        ("Which pages mention warning content?", lambda idx: _answer_keyword(idx, "warning", "warning")),
        ("Which pages mention caution content?", lambda idx: _answer_keyword(idx, "caution", "caution")),
        ("Which pages mention note content?", lambda idx: _answer_keyword(idx, "note", "note")),
        ("Which pages mention installation?", lambda idx: _answer_keyword(idx, "installation", "installation")),
        ("Which pages mention removal?", lambda idx: _answer_keyword(idx, "removal", "removal")),
        ("Which pages mention effectivity?", lambda idx: _answer_keyword(idx, "effectivity", "effectivity")),
        ("Which pages mention applicability?", lambda idx: _answer_keyword(idx, "applicability", "applicability")),
        ("Which pages mention eligibility?", lambda idx: _answer_keyword(idx, "eligibility", "eligibility")),
        ("Which pages mention approved replacement?", lambda idx: _answer_regex(idx, r"approved.{0,80}replacement|replacement.{0,80}approved", "No approved-replacement wording was found.")),
        ("Which pages mention interchangeability?", lambda idx: _answer_keyword(idx, "interchangeability", "interchangeability")),
        ("Which pages mention aircraft model A319?", lambda idx: _answer_keyword(idx, "A319", "A319")),
        ("Which pages mention aircraft model A320?", lambda idx: _answer_keyword(idx, "A320", "A320")),
        ("Which pages mention aircraft model A321?", lambda idx: _answer_keyword(idx, "A321", "A321")),
        ("Which pages mention Boeing 737?", lambda idx: _answer_keyword(idx, "737", "Boeing 737 / 737")),
        ("Which pages mention Boeing 787?", lambda idx: _answer_keyword(idx, "787", "Boeing 787 / 787")),
        ("Which pages mention ATA 25-21-00?", lambda idx: _answer_regex(idx, r"ATA\s*25[-\s_]*21[-\s_]*00|25[-\s_]*21[-\s_]*00", "ATA 25-21-00 was not found.")),
        ("Which pages mention CMM content?", lambda idx: _answer_keyword(idx, "CMM", "CMM")),
        ("Which pages mention illustrated parts list or IPL?", lambda idx: _answer_regex(idx, r"illustrated parts list|\bIPL\b", "No IPL / illustrated parts list wording was found.")),
        ("Which pages mention a dispenser?", lambda idx: _answer_keyword(idx, "dispenser", "dispenser")),
        ("Which pages mention towel?", lambda idx: _answer_keyword(idx, "towel", "towel")),
        ("Which pages mention a door?", lambda idx: _answer_keyword(idx, "door", "door")),
        ("Which pages mention a latch?", lambda idx: _answer_keyword(idx, "latch", "latch")),
        ("Which pages mention screws?", lambda idx: _answer_keyword(idx, "screw", "screw")),
        ("Which pages mention bracket content?", lambda idx: _answer_keyword(idx, "bracket", "bracket")),
        ("Which pages mention assembly content?", lambda idx: _answer_keyword(idx, "assembly", "assembly")),
        ("Which pages mention item numbers?", lambda idx: _answer_regex(idx, r"\bitem\b.{0,40}\b\d+\b|\bitem number\b", "No item-number wording was found.")),
        ("Which pages mention manual page references?", lambda idx: _answer_regex(idx, r"manual page|page reference|\bpg\.?\b", "No manual page reference wording was found.")),
        ("Which pages mention source trace or citation-ready evidence?", lambda idx: _answer_regex(idx, r"source[_ -]?trace|citation[_ -]?ready|source_trace_ready", "No source-trace/citation-ready wording was found.")),
        ("Which scanned page content sample is available for the first page?", lambda idx: _answer_page_sample(idx, 1)),
        ("Which scanned page content sample is available around page 25?", lambda idx: _answer_page_sample(idx, 25)),
        ("Which scanned page content sample is available around page 50?", lambda idx: _answer_page_sample(idx, 50)),
        ("Which scanned page content sample is available around page 100?", lambda idx: _answer_page_sample(idx, 100)),
        ("Which scanned page content sample is available around page 150?", lambda idx: _answer_page_sample(idx, 150)),
        ("Which scanned page content sample is available around page 200?", lambda idx: _answer_page_sample(idx, 200)),
        ("Which scanned page content sample is available around page 250?", lambda idx: _answer_page_sample(idx, 250)),
        ("Which scanned page content sample is available around page 300?", lambda idx: _answer_page_sample(idx, 300)),
        ("Which scanned page content sample is available around page 350?", lambda idx: _answer_page_sample(idx, 350)),
        ("Which scanned page content sample is available around page 400?", lambda idx: _answer_page_sample(idx, 400)),
        ("Which scanned page content sample is available around page 450?", lambda idx: _answer_page_sample(idx, 450)),
        ("Which scanned page content sample is available around page 509?", lambda idx: _answer_page_sample(idx, 509)),
    ]


def run_fixed50(index: ContentIndex, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    questions = _fixed_questions()
    assert len(questions) == 50, len(questions)
    records = []
    for idx, (question, answer_fn) in enumerate(questions, start=1):
        qid = f"q{idx:02d}"
        print(f"[{idx:03d}/050] START {qid}: {question}", flush=True)
        try:
            answer = answer_fn(index)
            status = "ok"
        except Exception as exc:  # defensive so one answer does not kill the run
            answer = f"ERROR while answering from TIFF-derived content artifacts: {exc}"
            status = "error"
        print(f"[{idx:03d}/050] DONE  {qid}", flush=True)
        records.append({"question_id": qid, "question": question, "answer": answer, "status": status})

    answers_jsonl = output_dir / "answers.jsonl"
    answers_txt = output_dir / "answers_question_answer.txt"
    summary_path = output_dir / "summary.json"

    with answers_jsonl.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    with answers_txt.open("w", encoding="utf-8") as f:
        for idx, record in enumerate(records, start=1):
            f.write(f"Question {idx:02d}: {record['question']}\n")
            f.write(f"Answer {idx:02d}: {record['answer']}\n\n")

    status_counts = Counter(r["status"] for r in records)
    quality_failures = []
    if len(records) != 50:
        quality_failures.append("question_count_not_50")
    if status_counts.get("error", 0):
        quality_failures.append("answer_errors_present")
    if index.metrics["content_record_count"] == 0:
        quality_failures.append("no_tiff_derived_content_records_found")

    summary = {
        "module": MODULE,
        "version": VERSION,
        "status": "TRACE_NET_TIFF_CONTENT_FIXED50_QA_DONE",
        "quality_status": "PASS" if not quality_failures else "FAIL",
        "quality_failures": quality_failures,
        "question_count": len(records),
        "answered_count": sum(1 for r in records if r["status"] == "ok"),
        "answer_error_count": status_counts.get("error", 0),
        **index.metrics,
        "answers": answers_jsonl.as_posix(),
        "question_answer_output": answers_txt.as_posix(),
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    print("\n" + answers_txt.read_text(encoding="utf-8"), flush=True)
    for key in [
        "status",
        "quality_status",
        "question_count",
        "answered_count",
        "content_record_count",
        "content_page_count",
        "zip_tiff_count",
        "answers",
        "question_answer_output",
        "summary",
    ]:
        value = summary_path.as_posix() if key == "summary" else summary.get(key)
        print(f"{key}={value}", flush=True)
    return summary


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run fixed 50 QA over TIFF-derived TRACE-Net content artifacts.")
    parser.add_argument("--sample-zip", type=Path, default=None, help="Optional ZIP containing TIFF pages; used only to report TIFF count, not XML byte metadata.")
    parser.add_argument("--artifact-root", type=Path, default=Path("local_data/organization/trace_net"), help="TRACE-Net artifact root containing OCR/table/visual/page-summary content extracted from TIFF pages.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Output directory for answers and summary.")
    parser.add_argument("--max-artifact-files", type=int, default=20000, help="Safety cap for scanned text/json artifact files.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    index = build_content_index(args.artifact_root, args.sample_zip, max_files=args.max_artifact_files)
    summary = run_fixed50(index, args.output_dir)
    return 0 if summary["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
