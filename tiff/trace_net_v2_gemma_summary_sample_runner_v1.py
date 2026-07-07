"""TRACE-Net V2 Gemma summary sample runner v1.

Small laptop-safe runner that makes V2 summaries with Gemma4 through the
existing V2 summary guide in `tiff.trace_net_page_context_v2`.

This is the real small-sample path for V2 LLM summaries:

page context/OCR sample
-> existing V2 build_prompt()
-> local Ollama Gemma4 call
-> existing V2 JSON parser/sanitizer
-> safe V2 guidance card
-> report/quality gate

Safety contract:
- no source-truth mutation
- no Postgres/Qdrant/OpenSearch writes
- no answer permission
- V2 summaries are retrieval/query guidance only, not proof
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

MODULE = "trace_net_v2_gemma_summary_sample_runner_v1"
VERSION = "1.0.0"

DEFAULT_CONTEXT_FILE = "local_data/organization/context/page_contexts.json"
DEFAULT_OCR_RECORDS = "local_data/organization/trace_net/fishnet_ocr_grid/trace_net_fishnet_ocr_grid_v1.json"
DEFAULT_OCR_RECORDS_CARDS = "local_data/organization/trace_net/fishnet_ocr_grid/trace_net_fishnet_ocr_grid_v1_cards.jsonl"
DEFAULT_OUTPUT_DIR = "local_data/organization/trace_net/v2_gemma_summary_sample_runner_v1/sample_5"
DEFAULT_MODEL = "gemma4:26b"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

REPORT_NAME = "trace_net_v2_gemma_summary_sample_runner_v1.json"
RECORDS_NAME = "trace_net_v2_gemma_summary_sample_runner_v1_records.jsonl"
PROMPTS_NAME = "trace_net_v2_gemma_summary_sample_runner_v1_prompts.jsonl"
QUALITY_NAME = "trace_net_v2_gemma_summary_sample_runner_v1_quality.json"

PART_RE = re.compile(r"\b(?:\d{3}-\d{5}-\d{3}|[A-Z]{1,4}\d[\w.-]{2,}|\d{2,}-[A-Z0-9][A-Z0-9-]{2,})\b")

REQUIRED_CARD_FIELDS = [
    "page_id",
    "role",
    "subrole",
    "confidence",
    "short_summary",
    "retrieval_summary",
    "answerable_questions",
    "retrieval_cues",
    "important_entities",
    "component_families",
    "source_grounding",
    "not_good_for",
    "authority",
    "prompt_version",
    "generation_provider",
    "generation_model",
    "llm_called",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def norm(value: Any) -> str:
    return "" if value is None else re.sub(r"\s+", " ", str(value)).strip()


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def as_list(value: Any, *, max_items: int = 30) -> List[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value[:max_items]
    if isinstance(value, tuple):
        return list(value)[:max_items]
    if isinstance(value, set):
        return list(value)[:max_items]
    return [value]


def read_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def page_number_from_page_id(page_id: str) -> Optional[int]:
    m = re.search(r"p(\d{6})$", page_id or "")
    if m:
        return int(m.group(1))
    m = re.search(r"(\d{1,6})$", page_id or "")
    return int(m.group(1)) if m else None


def page_id_from_number(page_number: int) -> str:
    return f"t_p_120_1176_p{int(page_number):06d}"


def load_contexts(context_file: str | Path) -> Dict[str, Dict[str, Any]]:
    """Load context records with the existing V2 loader when possible."""

    p = Path(context_file)
    try:
        from tiff.trace_net_page_context_v2 import load_v1_context_file

        loaded = load_v1_context_file(p)
        if isinstance(loaded, Mapping):
            return {str(k): dict(v) for k, v in loaded.items() if isinstance(v, Mapping)}
    except Exception:
        pass

    raw = read_json(p, default={})
    if isinstance(raw, Mapping):
        for key in ("records", "contexts", "page_contexts", "pages"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break

    out: Dict[str, Dict[str, Any]] = {}
    if isinstance(raw, Mapping):
        for key, value in raw.items():
            if isinstance(value, Mapping):
                rec = dict(value)
                rec.setdefault("page_id", key)
                out[str(rec.get("page_id") or key)] = rec
    elif isinstance(raw, list):
        for idx, value in enumerate(raw):
            if not isinstance(value, Mapping):
                continue
            rec = dict(value)
            pid = str(rec.get("page_id") or rec.get("id") or f"page_{idx + 1:06d}")
            rec.setdefault("page_id", pid)
            out[pid] = rec
    return out


def iter_mapping_records(value: Any) -> Iterable[Mapping[str, Any]]:
    """Yield nested dictionaries from JSON/JSONL artifacts."""

    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from iter_mapping_records(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_mapping_records(child)


def load_json_or_jsonl(path: Path) -> Any:
    if path.suffix.lower() == ".jsonl":
        rows = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        continue
        return rows
    return read_json(path, default={})


def candidate_page_ids_from_record(rec: Mapping[str, Any]) -> List[str]:
    """Extract page ids from many possible OCR artifact shapes."""

    ids: List[str] = []
    for key in (
        "page_id",
        "source_page_id",
        "resolved_page_id",
        "canonical_page_id",
        "page",
        "page_ref",
        "page_key",
        "id",
        "source_id",
    ):
        value = norm(rec.get(key))
        if value:
            ids.append(value)

    for key in (
        "page_number",
        "page_num",
        "page_index",
        "source_page_number",
        "source_page_num",
        "tiff_page_number",
        "image_page_number",
        "manual_page_number",
    ):
        value = rec.get(key)
        try:
            if value is not None and str(value).strip() != "":
                ids.append(page_id_from_number(int(value)))
        except Exception:
            pass

    for parent_key in ("source_trace", "source", "metadata", "payload", "page_metadata"):
        nested = rec.get(parent_key)
        if isinstance(nested, Mapping):
            ids.extend(candidate_page_ids_from_record(nested))

    # Scan string fields for source_p000123, p000123, 000001.tif, or rescarta URLs.
    for value in rec.values():
        if isinstance(value, str):
            s = value
            for m in re.finditer(r"(?:source_)?p(\d{6})", s, flags=re.I):
                ids.append(page_id_from_number(int(m.group(1))))
            for m in re.finditer(r"(?:^|[/_\\-])(\d{6})(?:\.tiff?|$|[/_\\-])", s, flags=re.I):
                ids.append(page_id_from_number(int(m.group(1))))
            for m in re.finditer(r"/(\d{6})(?:$|[/?#])", s, flags=re.I):
                ids.append(page_id_from_number(int(m.group(1))))
        elif isinstance(value, Mapping):
            ids.extend(candidate_page_ids_from_record(value))

    out: List[str] = []
    seen = set()
    for value in ids:
        value = norm(value)
        if not value:
            continue
        aliases = {value}
        n = page_number_from_page_id(value)
        if n is not None:
            aliases.add(page_id_from_number(n))
            aliases.add(str(n))
        elif value.isdigit():
            try:
                aliases.add(page_id_from_number(int(value)))
            except Exception:
                pass
        for alias in aliases:
            if alias and alias not in seen:
                seen.add(alias)
                out.append(alias)
    return out

def _is_text_like_key(key: str) -> bool:
    low = key.lower()
    if any(bad in low for bad in ("path", "url", "file", "status", "module", "version", "hash", "id")):
        return False
    return any(good in low for good in ("text", "ocr", "line", "phrase", "word", "token", "content", "transcript", "value"))


def _collect_text_candidates(value: Any, *, parent_key: str = "", limit: int = 4000) -> List[str]:
    candidates: List[str] = []
    if isinstance(value, str):
        s = norm(value)
        if s and (_is_text_like_key(parent_key) or len(s.split()) >= 4):
            candidates.append(s)
    elif isinstance(value, (int, float)):
        return []
    elif isinstance(value, Mapping):
        for key, child in list(value.items())[:limit]:
            candidates.extend(_collect_text_candidates(child, parent_key=str(key), limit=limit))
    elif isinstance(value, list):
        pieces: List[str] = []
        for child in value[:limit]:
            if isinstance(child, str):
                if norm(child):
                    pieces.append(norm(child))
            elif isinstance(child, Mapping):
                child_candidates = _collect_text_candidates(child, parent_key=parent_key, limit=limit)
                candidates.extend(child_candidates)
            elif isinstance(child, (int, float)):
                continue
        joined = " ".join(pieces)
        if joined and (_is_text_like_key(parent_key) or len(joined.split()) >= 4):
            candidates.append(joined)
    return candidates


def text_from_ocr_record(rec: Mapping[str, Any], max_chars: int) -> str:
    candidates: List[str] = []

    # Preferred explicit fields first.
    for key in (
        "ocr_text",
        "text",
        "raw_text",
        "source_text",
        "recognized_text",
        "combined_text",
        "best_text",
        "line_text",
        "transcript",
        "content",
        "value",
    ):
        value = rec.get(key)
        candidates.extend(_collect_text_candidates(value, parent_key=key))

    # Then nested OCR/cell/line structures.
    for key in (
        "lines",
        "ocr_lines",
        "records",
        "cells",
        "grid_cells",
        "text_blocks",
        "blocks",
        "tokens",
        "words",
        "payload",
        "metadata",
    ):
        if key in rec:
            candidates.extend(_collect_text_candidates(rec.get(key), parent_key=key))

    # Last resort: scan all text-like keys in the record.
    if not candidates:
        candidates.extend(_collect_text_candidates(rec, parent_key="record"))

    cleaned: List[str] = []
    seen = set()
    for candidate in candidates:
        candidate = norm(candidate)
        if not candidate:
            continue
        # Avoid treating pure file paths or JSON metadata as OCR.
        alpha_count = sum(ch.isalpha() for ch in candidate)
        if alpha_count < 4:
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(candidate)

    if not cleaned:
        return ""
    cleaned.sort(key=lambda s: (len(s.split()), len(s)), reverse=True)
    return cleaned[0][:max_chars]

def load_ocr_records(paths: Sequence[str | Path], max_chars: int) -> Dict[str, str]:
    """Load OCR text from optional local JSON/JSONL artifacts.

    This is intentionally read-only and shape-tolerant. It lets the laptop
    sample runner hydrate page text from existing OCR artifacts instead of
    sending empty context pages to Gemma.
    """

    ocr_by_page: Dict[str, str] = {}
    for raw_path in paths:
        if not raw_path:
            continue
        path = Path(raw_path)
        if not path.exists() or not path.is_file():
            continue
        try:
            payload = load_json_or_jsonl(path)
        except Exception:
            continue
        for rec in iter_mapping_records(payload):
            page_ids = candidate_page_ids_from_record(rec)
            if not page_ids:
                continue
            text = text_from_ocr_record(rec, max_chars=max_chars)
            if not text:
                continue
            for pid in page_ids:
                existing = ocr_by_page.get(pid, "")
                if len(text) > len(existing):
                    ocr_by_page[pid] = text[:max_chars]
                n = page_number_from_page_id(pid)
                if n is not None:
                    canonical = page_id_from_number(n)
                    existing = ocr_by_page.get(canonical, "")
                    if len(text) > len(existing):
                        ocr_by_page[canonical] = text[:max_chars]
    return ocr_by_page


def hydrated_text_for_page(page_id: str, rec: Mapping[str, Any], ocr_by_page: Mapping[str, str], max_chars: int) -> str:
    direct = text_from_context(rec, max_chars)
    aliases = {page_id, str(rec.get("page_id") or "")}
    n = page_number_from_page_id(page_id) or page_number_from_page_id(str(rec.get("page_id") or ""))
    if n is not None:
        aliases.add(page_id_from_number(n))
        aliases.add(str(n))
    hydrated = ""
    for alias in aliases:
        if alias and norm(ocr_by_page.get(alias)):
            value = norm(ocr_by_page.get(alias))[:max_chars]
            if len(value) > len(hydrated):
                hydrated = value
    return hydrated if len(hydrated) > len(direct) else direct


def text_from_context(rec: Mapping[str, Any], max_chars: int) -> str:
    for key in ("ocr_text", "text", "ocr_sample", "source_text", "raw_ocr", "content"):
        value = norm(rec.get(key))
        if value:
            return value[:max_chars]
    return ""


def make_page_input(
    page_id: str,
    rec: Mapping[str, Any],
    max_ocr_chars: int,
    ocr_by_page: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    ocr_by_page = ocr_by_page or {}
    direct_text = text_from_context(rec, max_ocr_chars)
    hydrated_text = hydrated_text_for_page(page_id, rec, ocr_by_page, max_ocr_chars)
    return {
        "page_id": page_id,
        "document_id": rec.get("document_id") or rec.get("source_id") or "unknown_document",
        "v1": dict(rec),
        "ocr_text": hydrated_text,
        "ocr_text_hydrated_from_records": bool(hydrated_text and hydrated_text != direct_text),
        "ocr_classification": rec.get("ocr_classification") or rec.get("classification"),
        "source_url": rec.get("source_url") or rec.get("url") or "",
        "tiff_path": rec.get("tiff_path") or rec.get("source_file") or rec.get("image_path") or "",
        "ocr_path": rec.get("ocr_path") or "",
        "max_ocr_chars": max_ocr_chars,
    }


def select_pages(
    contexts: Mapping[str, Mapping[str, Any]],
    *,
    page_ids: Sequence[str],
    page_numbers: Sequence[int],
    max_pages: int,
    require_text: bool,
    require_ocr_text: bool = False,
    ocr_by_page: Optional[Mapping[str, str]] = None,
) -> List[Tuple[str, Mapping[str, Any]]]:
    ocr_by_page = ocr_by_page or {}
    wanted = {str(x).strip() for x in page_ids if str(x).strip()}
    wanted.update(page_id_from_number(n) for n in page_numbers)

    def rec_aliases(key: str, rec: Mapping[str, Any]) -> set[str]:
        rec_pid = str(rec.get("page_id") or key)
        aliases = {key, rec_pid}
        n = page_number_from_page_id(rec_pid) or page_number_from_page_id(key)
        if n is not None:
            aliases.add(str(n))
            aliases.add(page_id_from_number(n))
        return aliases

    def has_content(key: str, rec: Mapping[str, Any]) -> bool:
        rec_pid = str(rec.get("page_id") or key)
        text = hydrated_text_for_page(rec_pid, rec, ocr_by_page, max_chars=6000)
        if require_ocr_text:
            return bool(text)
        blob = " ".join(
            norm(rec.get(k))
            for k in ("ocr_text", "text", "ocr_sample", "summary", "short_summary", "retrieval_summary")
        )
        return bool(text or blob)

    selected: List[Tuple[str, Mapping[str, Any]]] = []
    if wanted:
        for key, rec in contexts.items():
            rec_pid = str(rec.get("page_id") or key)
            if rec_aliases(key, rec) & wanted:
                if require_text and not has_content(key, rec):
                    continue
                selected.append((rec_pid, rec))
                if len(selected) >= max_pages:
                    return selected
        return selected

    # Prefer OCR/text-hydrated records first, not generic blank cover pages.
    for key, rec in contexts.items():
        rec_pid = str(rec.get("page_id") or key)
        if require_text and not has_content(key, rec):
            continue
        if has_content(key, rec):
            selected.append((rec_pid, rec))
        if len(selected) >= max_pages:
            return selected

    if not selected and not require_text and not require_ocr_text:
        for key, rec in contexts.items():
            selected.append((str(rec.get("page_id") or key), rec))
            if len(selected) >= max_pages:
                return selected

    return selected[:max_pages]

def extract_part_numbers(*texts: Any, max_items: int = 25) -> List[str]:
    seen = set()
    out: List[str] = []
    for text in texts:
        for m in PART_RE.finditer(norm(text).upper()):
            value = m.group(0)
            if value not in seen:
                seen.add(value)
                out.append(value)
                if len(out) >= max_items:
                    return out
    return out


def safe_card_defaults(card: Mapping[str, Any], page: Mapping[str, Any], *, prompt_version: str, model: str, llm_called: bool, raw_response: str = "") -> Dict[str, Any]:
    out = dict(card)
    v1 = page.get("v1") if isinstance(page.get("v1"), Mapping) else {}
    ocr_text = norm(page.get("ocr_text"))

    summary = (
        norm(out.get("short_summary"))
        or norm(out.get("summary"))
        or norm(v1.get("summary"))
        or norm(v1.get("short_summary"))
        or ("Gemma generated retrieval guidance from OCR/context." if llm_called else "Heuristic V2 retrieval guidance.")
    )

    out["page_id"] = norm(out.get("page_id")) or norm(page.get("page_id")) or norm(v1.get("page_id")) or "unknown_page"
    out["role"] = norm(out.get("role")) or norm(v1.get("role")) or norm(v1.get("page_role")) or norm(v1.get("type")) or "unknown"
    out["subrole"] = norm(out.get("subrole")) or "general"
    out["confidence"] = norm(out.get("confidence")) or norm(v1.get("confidence")) or ("medium" if ocr_text else "low")
    out["short_summary"] = summary
    out["retrieval_summary"] = norm(out.get("retrieval_summary")) or f"Use this page as V2 retrieval/query guidance. {summary}"

    for field in ("answerable_questions", "retrieval_cues", "important_entities", "component_families", "not_good_for"):
        values = [x for x in as_list(out.get(field)) if norm(x)]
        out[field] = values

    if not out["retrieval_cues"]:
        blob = f"{summary} {out.get('retrieval_summary')} {ocr_text}".lower()
        cues = []
        for term in ("figure", "table", "parts", "list", "passenger", "seat", "armrest", "backrest", "callout", "vendor", "applicability"):
            if term in blob:
                cues.append(term)
        out["retrieval_cues"] = cues[:8] or ["page context"]
    if not out["answerable_questions"]:
        out["answerable_questions"] = ["Which source page may be relevant to this query?"]
    if not out["not_good_for"]:
        out["not_good_for"] = [
            "proving source truth without checking the cited source page",
            "answering without source URL, TIFF path, and OCR/source evidence",
        ]

    source_grounding = out.get("source_grounding") if isinstance(out.get("source_grounding"), Mapping) else {}
    source_grounding = dict(source_grounding)
    source_grounding["has_ocr"] = bool(source_grounding.get("has_ocr")) or bool(ocr_text)
    source_grounding["source_url_present"] = bool(source_grounding.get("source_url_present")) or bool(norm(page.get("source_url")))
    source_grounding["supporting_ocr_phrases"] = as_list(source_grounding.get("supporting_ocr_phrases"))[:8]
    out["source_grounding"] = source_grounding

    authority = out.get("authority") if isinstance(out.get("authority"), Mapping) else {}
    authority = dict(authority)
    authority["trust_scope"] = norm(authority.get("trust_scope")) or "page_context_summary"
    authority["rag_role"] = norm(authority.get("rag_role")) or "retrieval_helper"
    authority["can_answer_directly"] = False
    authority["can_support_answer"] = bool(authority.get("can_support_answer", True))
    authority["canonical_source_truth"] = False
    authority["requires_citation"] = True
    authority["requires_source_check"] = True
    authority["source_truth_mutation_allowed"] = False
    out["authority"] = authority

    out["prompt_version"] = norm(out.get("prompt_version")) or prompt_version
    out["generation_provider"] = "ollama" if llm_called else "heuristic"
    out["generation_model"] = model if llm_called else "heuristic_context_v2"
    out["llm_called"] = bool(llm_called)
    out["llm_response_preview"] = raw_response[:700] if raw_response else ""
    out["guidance_only"] = True
    out["can_prove_claims"] = False
    out["source_truth_mutation_allowed"] = False

    out["v3_preview"] = {
        "page_type": out["role"],
        "route_signals": out["retrieval_cues"][:10],
        "part_numbers": extract_part_numbers(
            out.get("short_summary"),
            out.get("retrieval_summary"),
            " ".join(str(x) for x in as_list(out.get("important_entities"))),
            page.get("ocr_text"),
        ),
        "candidate_evidence_usefulness_for_rag": "guidance_only_candidate; requires proof_context/source_trace before factual use",
        "engram_guidance": "behavior/proof-boundary guidance only; not factual proof",
        "leiden_community_guidance": "not joined in this V2 Gemma sample runner",
        "dublin_core": {
            "type": "PageContextGuidance",
            "format": "application/json",
            "identifier": out["page_id"],
            "source": norm(page.get("source_url")) or norm(page.get("tiff_path")) or "unknown",
        },
    }
    return out


def validate_card(card: Mapping[str, Any], *, require_llm_called: bool) -> Dict[str, Any]:
    missing = [f for f in REQUIRED_CARD_FIELDS if f not in card]
    empty = [f for f in ("page_id", "role", "subrole", "confidence", "short_summary", "retrieval_summary") if not norm(card.get(f))]
    bad_list = [f for f in ("answerable_questions", "retrieval_cues", "important_entities", "component_families", "not_good_for") if not isinstance(card.get(f), list)]

    authority = card.get("authority") if isinstance(card.get("authority"), Mapping) else {}
    answer_permission = truthy(authority.get("can_answer_directly")) or truthy(card.get("can_answer_directly"))
    canonical_truth = truthy(authority.get("canonical_source_truth")) or truthy(card.get("canonical_source_truth"))
    source_mutation = truthy(authority.get("source_truth_mutation_allowed")) or truthy(card.get("source_truth_mutation_allowed"))
    llm_called = truthy(card.get("llm_called"))

    failures: List[str] = []
    if missing:
        failures.append("missing_required_fields")
    if empty:
        failures.append("empty_required_fields")
    if bad_list:
        failures.append("bad_list_fields")
    if answer_permission:
        failures.append("answer_permission_true")
    if canonical_truth:
        failures.append("canonical_source_truth_true")
    if source_mutation:
        failures.append("source_truth_mutation_allowed_true")
    if require_llm_called and not llm_called:
        failures.append("required_gemma_llm_not_called")

    return {
        "quality_status": "PASS" if not failures else "FAIL",
        "failure_reasons": failures,
        "missing_fields": missing,
        "empty_required_fields": empty,
        "bad_list_fields": bad_list,
        "answer_permission": answer_permission,
        "canonical_source_truth": canonical_truth,
        "source_truth_mutation_allowed": source_mutation,
        "llm_called": llm_called,
    }


def build_gemma_card_for_page(
    page: Mapping[str, Any],
    *,
    model: str,
    ollama_url: str,
    timeout_seconds: int,
    temperature: float,
    allow_heuristic_fallback: bool,
    dry_run: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Build one V2 card using the existing prompt and Gemma through Ollama."""

    from tiff.trace_net_page_context_v2 import (
        PROMPT_VERSION,
        build_prompt,
        call_ollama,
        extract_json_from_text,
        heuristic_context_v2,
        sanitize_context_v2,
    )

    page_dict = dict(page)
    heuristic = heuristic_context_v2(page_dict)
    prompt = build_prompt(page_dict, heuristic)

    raw_response = ""
    parsed: Optional[Dict[str, Any]] = None
    llm_called = False
    llm_status = "DRY_RUN_HEURISTIC_ONLY" if dry_run else "NOT_CALLED"
    warnings: List[str] = []

    if dry_run:
        parsed = heuristic
    else:
        try:
            raw_response = call_ollama(
                prompt,
                model=model,
                url=ollama_url,
                timeout=timeout_seconds,
                temperature=temperature,
            )
            llm_called = True
            parsed = extract_json_from_text(raw_response)
            if parsed is None:
                llm_status = "GEMMA_RESPONSE_NOT_VALID_JSON"
                warnings.append("gemma_response_not_valid_json")
                if not allow_heuristic_fallback:
                    raise RuntimeError("Gemma response was not valid JSON")
                parsed = heuristic
            else:
                llm_status = "GEMMA_JSON_SUMMARY_SUCCEEDED"
        except Exception as exc:
            llm_status = f"GEMMA_CALL_FAILED:{type(exc).__name__}"
            warnings.append(f"gemma_error:{type(exc).__name__}:{str(exc)[:180]}")
            if not allow_heuristic_fallback:
                raise
            parsed = heuristic

    sanitized = sanitize_context_v2(parsed or heuristic, heuristic)
    card = safe_card_defaults(
        sanitized,
        page_dict,
        prompt_version=PROMPT_VERSION,
        model=model,
        llm_called=llm_called,
        raw_response=raw_response,
    )
    card["llm_status"] = llm_status
    card["generation_warnings"] = warnings
    meta = {
        "page_id": card.get("page_id"),
        "prompt_version": PROMPT_VERSION,
        "prompt_length": len(prompt),
        "prompt_preview": prompt[:3000],
        "llm_status": llm_status,
        "llm_called": llm_called,
        "raw_response_preview": raw_response[:1200],
        "warnings": warnings,
    }
    return card, meta


def build_v2_gemma_summary_sample(
    *,
    context_file: str | Path = DEFAULT_CONTEXT_FILE,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    max_pages: int = 5,
    page_ids: Sequence[str] = (),
    page_numbers: Sequence[int] = (),
    max_ocr_chars: int = 6000,
    require_text: bool = False,
    require_ocr_text: bool = False,
    ocr_records_paths: Sequence[str | Path] = (),
    max_candidate_pages: int = 25,
    model: str = DEFAULT_MODEL,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    timeout_seconds: int = 240,
    temperature: float = 0.0,
    allow_heuristic_fallback: bool = False,
    dry_run: bool = False,
    require_gemma: bool = True,
) -> Dict[str, Any]:
    context_path = Path(context_file)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    contexts = load_contexts(context_path)

    # Hydrate OCR from optional local artifacts. If the default OCR artifact
    # exists, use it automatically; otherwise continue with context_file only.
    ocr_paths = list(ocr_records_paths or [])
    if not ocr_paths:
        for default_path in (DEFAULT_OCR_RECORDS, DEFAULT_OCR_RECORDS_CARDS):
            if Path(default_path).exists():
                ocr_paths.append(default_path)
        # Also include any nearby OCR JSONL records that are clearly under fishnet_ocr_grid.
        fishnet_dir = Path("local_data/organization/trace_net/fishnet_ocr_grid")
        if fishnet_dir.exists():
            for extra in sorted(fishnet_dir.glob("*ocr*jsonl")):
                if str(extra) not in {str(x) for x in ocr_paths}:
                    ocr_paths.append(str(extra))
    ocr_by_page = load_ocr_records(ocr_paths, max_chars=max_ocr_chars) if ocr_paths else {}

    candidate_limit = max(max_candidate_pages, max_pages)
    selected = select_pages(
        contexts,
        page_ids=page_ids,
        page_numbers=page_numbers,
        max_pages=candidate_limit,
        require_text=require_text or require_ocr_text,
        require_ocr_text=require_ocr_text,
        ocr_by_page=ocr_by_page,
    )

    records: List[Dict[str, Any]] = []
    prompt_records: List[Dict[str, Any]] = []
    validations: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    attempted_page_count = 0
    for page_id, rec in selected:
        if len(records) >= max_pages:
            break
        attempted_page_count += 1
        page = make_page_input(page_id, rec, max_ocr_chars=max_ocr_chars, ocr_by_page=ocr_by_page)
        if require_ocr_text and not norm(page.get("ocr_text")):
            errors.append({"page_id": page_id, "error_type": "MissingOCRText", "error": "No OCR/text available after hydration."})
            continue
        try:
            card, prompt_meta = build_gemma_card_for_page(
                page,
                model=model,
                ollama_url=ollama_url,
                timeout_seconds=timeout_seconds,
                temperature=temperature,
                allow_heuristic_fallback=allow_heuristic_fallback,
                dry_run=dry_run,
            )
            validation = validate_card(card, require_llm_called=require_gemma and not dry_run)
            records.append(card)
            prompt_records.append(prompt_meta)
            validations.append({"page_id": card.get("page_id"), "validation": validation})
        except Exception as exc:
            errors.append({"page_id": page_id, "error_type": type(exc).__name__, "error": str(exc)[:700]})

    validation_failure_count = sum(1 for v in validations if (v.get("validation") or {}).get("quality_status") != "PASS")
    llm_called_count = sum(1 for r in records if truthy(r.get("llm_called")))
    gemma_success_count = sum(1 for r in records if r.get("llm_status") == "GEMMA_JSON_SUMMARY_SUCCEEDED")
    answer_permission_count = sum(1 for r in records if truthy((r.get("authority") or {}).get("can_answer_directly")) or truthy(r.get("can_answer_directly")))
    source_mutation_count = sum(1 for r in records if truthy((r.get("authority") or {}).get("source_truth_mutation_allowed")) or truthy(r.get("source_truth_mutation_allowed")))

    failures: List[str] = []
    if len(records) < max_pages:
        failures.append(f"sample_record_count_below_requested:{len(records)}<{max_pages}")
    if errors:
        failures.append(f"error_count_nonzero:{len(errors)}")
    if validation_failure_count:
        failures.append(f"validation_failure_count_nonzero:{validation_failure_count}")
    if require_gemma and not dry_run and llm_called_count < max_pages:
        failures.append(f"llm_called_count_below_requested:{llm_called_count}<{max_pages}")
    if require_gemma and not dry_run and gemma_success_count < max_pages:
        failures.append(f"gemma_success_count_below_requested:{gemma_success_count}<{max_pages}")
    if answer_permission_count:
        failures.append("answer_permission_count_nonzero")
    if source_mutation_count:
        failures.append("source_truth_mutation_allowed_count_nonzero")

    records_path = output / RECORDS_NAME
    prompts_path = output / PROMPTS_NAME
    report_path = output / REPORT_NAME
    write_jsonl(records_path, records)
    write_jsonl(prompts_path, prompt_records)

    report: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "created_at": utc_now(),
        "status": "TRACE_NET_V2_GEMMA_SUMMARY_SAMPLE_BUILT",
        "quality_status": "PASS" if not failures else "FAIL",
        "failure_reasons": failures,
        "summary": {
            "context_file": str(context_path),
            "context_file_exists": context_path.exists(),
            "context_record_count": len(contexts),
            "ocr_records_path_count": len(ocr_paths),
            "ocr_records_paths": [str(x) for x in ocr_paths],
            "ocr_hydrated_page_key_count": len(ocr_by_page),
            "ocr_hydrated_page_key_sample": sorted(list(ocr_by_page.keys()))[:12],
            "requested_max_pages": max_pages,
            "max_candidate_pages": candidate_limit,
            "candidate_page_count": len(selected),
            "attempted_page_count": attempted_page_count,
            "require_ocr_text": require_ocr_text,
            "sample_record_count": len(records),
            "prompt_record_count": len(prompt_records),
            "validation_failure_count": validation_failure_count,
            "error_count": len(errors),
            "llm_called_count": llm_called_count,
            "gemma_success_count": gemma_success_count,
            "generation_model": model,
            "ollama_url": ollama_url,
            "dry_run": dry_run,
            "allow_heuristic_fallback": allow_heuristic_fallback,
            "require_gemma": require_gemma,
            "answer_permission_count": answer_permission_count,
            "source_truth_mutation_allowed_count": source_mutation_count,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "v3_preview_attached": True,
        },
        "records_path": records_path.as_posix(),
        "prompts_path": prompts_path.as_posix(),
        "records": records,
        "prompt_records": prompt_records,
        "validations": validations,
        "errors": errors,
        "safety_contract": {
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "v2_summary_is_proof": False,
            "v2_summary_role": "retrieval_guidance_only",
            "gemma4_makes_summaries": True,
        },
    }
    write_json(report_path, report)
    return report


def check_v2_gemma_summary_sample_report(
    *,
    report_path: str | Path,
    output: str | Path = "",
    min_records: int = 5,
    min_gemma_successes: int = 5,
    require_quality_pass: bool = True,
    require_no_answer_permission: bool = True,
    require_no_source_truth_mutation: bool = True,
) -> Dict[str, Any]:
    report = read_json(report_path, default={}) or {}
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    failures: List[str] = []

    if require_quality_pass and report.get("quality_status") != "PASS":
        failures.append("source_report_quality_status_not_pass")
    if int(summary.get("sample_record_count") or 0) < min_records:
        failures.append("sample_record_count_below_min")
    if int(summary.get("gemma_success_count") or 0) < min_gemma_successes:
        failures.append("gemma_success_count_below_min")
    if int(summary.get("validation_failure_count") or 0) != 0:
        failures.append("validation_failure_count_nonzero")
    if int(summary.get("error_count") or 0) != 0:
        failures.append("error_count_nonzero")
    if require_no_answer_permission and int(summary.get("answer_permission_count") or 0) != 0:
        failures.append("answer_permission_count_nonzero")
    if require_no_source_truth_mutation and int(summary.get("source_truth_mutation_allowed_count") or 0) != 0:
        failures.append("source_truth_mutation_allowed_count_nonzero")

    quality = {
        "module": MODULE,
        "version": VERSION,
        "created_at": utc_now(),
        "status": "TRACE_NET_V2_GEMMA_SUMMARY_SAMPLE_QUALITY_CHECKED",
        "quality_status": "PASS" if not failures else "FAIL",
        "failure_reasons": failures,
        "summary": summary,
        "source_report_path": Path(report_path).as_posix(),
    }
    if output:
        write_json(output, quality)
    return quality


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build 5 V2 summaries using the existing V2 guide and local Ollama/Gemma4.")
    p.add_argument("--context-file", default=DEFAULT_CONTEXT_FILE)
    p.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--max-pages", type=int, default=5)
    p.add_argument("--page-id", action="append", default=[])
    p.add_argument("--page-number", type=int, action="append", default=[])
    p.add_argument("--max-ocr-chars", type=int, default=6000)
    p.add_argument("--require-text", action="store_true")
    p.add_argument("--require-ocr-text", action="store_true")
    p.add_argument("--ocr-records", action="append", default=[], help="Optional OCR JSON/JSONL artifact used to hydrate page text. If omitted, the default fishnet OCR artifact is used when present.")
    p.add_argument("--max-candidate-pages", type=int, default=25, help="Try this many candidate pages to get max-pages successful Gemma summaries.")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    p.add_argument("--timeout-seconds", type=int, default=240)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--allow-heuristic-fallback", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="Do not call Gemma; scaffold test only.")
    p.add_argument("--no-require-gemma", action="store_true", help="Do not hard-fail if Gemma is not called/successful.")
    return p


def check_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check V2 Gemma summary sample quality.")
    p.add_argument("--report", required=True)
    p.add_argument("--output", default="")
    p.add_argument("--min-records", type=int, default=5)
    p.add_argument("--min-gemma-successes", type=int, default=5)
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--require-no-source-truth-mutation", action="store_true")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = build_v2_gemma_summary_sample(
        context_file=args.context_file,
        output_dir=args.output_dir,
        max_pages=args.max_pages,
        page_ids=args.page_id,
        page_numbers=args.page_number,
        max_ocr_chars=args.max_ocr_chars,
        require_text=args.require_text,
        require_ocr_text=args.require_ocr_text,
        ocr_records_paths=args.ocr_records,
        max_candidate_pages=args.max_candidate_pages,
        model=args.model,
        ollama_url=args.ollama_url,
        timeout_seconds=args.timeout_seconds,
        temperature=args.temperature,
        allow_heuristic_fallback=args.allow_heuristic_fallback,
        dry_run=args.dry_run,
        require_gemma=not args.no_require_gemma,
    )
    out = Path(args.output_dir)
    print(f"Wrote: {out / REPORT_NAME}")
    print(f"Wrote: {out / RECORDS_NAME}")
    print(f"Wrote: {out / PROMPTS_NAME}")
    print(f"quality_status: {report.get('quality_status')}")
    print(f"failure_reasons: {report.get('failure_reasons')}")
    print(f"summary: {json.dumps(report.get('summary') or {}, sort_keys=True)}")
    return 0 if report.get("quality_status") == "PASS" else 2


def check_main(argv: Optional[Sequence[str]] = None) -> int:
    args = check_arg_parser().parse_args(argv)
    quality = check_v2_gemma_summary_sample_report(
        report_path=args.report,
        output=args.output,
        min_records=args.min_records,
        min_gemma_successes=args.min_gemma_successes,
        require_quality_pass=args.require_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
    )
    print(f"Wrote: {args.output or '<not written>'}")
    print(f"quality_status: {quality.get('quality_status')}")
    print(f"failure_reasons: {quality.get('failure_reasons')}")
    print(f"summary: {json.dumps(quality.get('summary') or {}, sort_keys=True)}")
    return 0 if quality.get("quality_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
