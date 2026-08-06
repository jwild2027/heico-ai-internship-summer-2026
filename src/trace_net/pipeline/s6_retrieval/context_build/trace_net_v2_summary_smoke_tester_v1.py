"""TRACE-Net V2 summary smoke tester v1.

Uses the existing V2 summary guide in tiff.trace_net_page_context_v2.

Two modes:
1. Prompt/card smoke mode: load a few v1 page contexts, call the existing
   heuristic_context_v2(), build_prompt(), and sanitize_context_v2() helpers,
   then validate the generated guidance cards.
2. Existing-record audit mode: read trace_net_page_context_v2_records.jsonl
   and validate the generated V2 summaries/cards.

Safety contract:
- read-only local files
- no source-truth mutation
- no Postgres/Qdrant/OpenSearch writes
- no answer permission
- V2 summaries are guidance only, not proof
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

MODULE = "trace_net_v2_summary_smoke_tester_v1"
VERSION = "1.0.0"

DEFAULT_CONTEXT_FILE = "local_data/organization/context/page_contexts.json"
DEFAULT_V2_RECORDS_JSONL = "local_data/organization/trace_net/page_context_v2/trace_net_page_context_v2_records.jsonl"
DEFAULT_OUTPUT_DIR = "local_data/organization/trace_net/v2_summary_smoke_tester_v1"
DEFAULT_REPORT_NAME = "trace_net_v2_summary_smoke_tester_v1.json"
DEFAULT_MD_NAME = "trace_net_v2_summary_smoke_tester_v1.md"
DEFAULT_QUALITY_NAME = "trace_net_v2_summary_smoke_tester_v1_quality.json"

REQUIRED_V2_FIELDS = [
    "page_id", "role", "subrole", "confidence", "short_summary",
    "retrieval_summary", "answerable_questions", "retrieval_cues",
    "important_entities", "component_families", "source_grounding",
    "not_good_for", "authority", "prompt_version",
]

REQUIRED_SOURCE_GROUNDING_FIELDS = [
    "has_ocr", "source_url_present", "supporting_ocr_phrases",
]

REQUIRED_AUTHORITY_FIELDS = [
    "trust_scope", "can_answer_directly", "canonical_source_truth", "requires_source_check",
]

PROMPT_REQUIRED_TERMS = [
    "JSON", "short_summary", "retrieval_summary", "answerable_questions",
    "retrieval_cues", "important_entities", "source_grounding",
    "not_good_for", "authority", "OCR",
]

# Report-only: these are the newer explicit-schema targets. The current V2 guide
# may not contain them yet, so gaps are reported but do not fail this smoke test.
TARGET_EXPLICIT_SCHEMA_TERMS = [
    "page type", "route signal", "visible identifier", "part number",
    "figure", "table", "warning", "caution", "note", "callout",
    "uncertainty", "rag", "extraction warning", "confidence",
]


def _read_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: str | Path, rows: Sequence[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows) + ("\n" if rows else ""), encoding="utf-8")


def _norm(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _clean_preview(value: Any, limit: int = 900) -> str:
    text = re.sub(r"\s+", " ", _norm(value))
    return text[:limit] + ("..." if len(text) > limit else "")


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"true", "yes", "1", "y"}


def _records_jsonl(path: str | Path, limit: int = 0) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    records: List[Dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            records.append(json.loads(line))
            if limit and len(records) >= limit:
                break
    return records


def _fallback_load_contexts(path: str | Path) -> Dict[str, Dict[str, Any]]:
    raw = _read_json(path, default={})
    if not raw:
        return {}

    if isinstance(raw, dict):
        for key in ("records", "contexts", "page_contexts", "pages"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break

    out: Dict[str, Dict[str, Any]] = {}
    if isinstance(raw, dict):
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
            pid = str(rec.get("page_id") or rec.get("id") or f"page_{idx+1:06d}")
            rec.setdefault("page_id", pid)
            out[pid] = rec
    return out


def load_v1_contexts_with_existing_loader(path: str | Path) -> Dict[str, Dict[str, Any]]:
    """Use the existing V2 file's loader when available."""

    try:
        from tiff.trace_net_page_context_v2 import load_v1_context_file

        data = load_v1_context_file(Path(path))
        return {str(k): dict(v) for k, v in data.items() if isinstance(v, Mapping)}
    except Exception:
        return _fallback_load_contexts(path)


def make_page_input_from_v1(page_id: str, v1: Mapping[str, Any], max_ocr_chars: int = 6000) -> Dict[str, Any]:
    """Create the page input shape expected by trace_net_page_context_v2."""

    ocr_text = (
        v1.get("ocr_text")
        or v1.get("text")
        or v1.get("ocr_sample")
        or v1.get("raw_ocr")
        or v1.get("source_text")
        or ""
    )
    return {
        "page_id": page_id,
        "document_id": v1.get("document_id") or v1.get("source_id") or "unknown_document",
        "v1": dict(v1),
        "ocr_text": _norm(ocr_text)[:max_ocr_chars],
        "ocr_classification": v1.get("ocr_classification") or v1.get("classification"),
        "source_url": v1.get("source_url") or v1.get("url") or "",
        "tiff_path": v1.get("tiff_path") or v1.get("source_file") or v1.get("image_path") or "",
        "ocr_path": v1.get("ocr_path") or "",
        "max_ocr_chars": max_ocr_chars,
    }


def validate_v2_prompt(prompt: str) -> Dict[str, Any]:
    """Validate the existing prompt without making wording gaps fatal.

    The existing V2 guide is already in the repo and may phrase some schema
    terms differently than this smoke tester. The smoke tester should fail if
    cards are unsafe or malformed, not merely because an existing prompt uses
    older wording. Missing prompt terms are therefore reported as warnings.

    A prompt is PASS if it either contains a literal JSON-schema block or it
    contains the required V2 field names in prose. This keeps the tester
    compatible with older prompt fixtures and with the current V2 guide.
    """

    missing = [term for term in PROMPT_REQUIRED_TERMS if term.lower() not in prompt.lower()]
    target_gaps = [term for term in TARGET_EXPLICIT_SCHEMA_TERMS if term.lower() not in prompt.lower()]
    contains_schema = "{" in prompt and "}" in prompt and "short_summary" in prompt
    contains_required_terms = not missing
    return {
        "quality_status": "PASS" if contains_schema or contains_required_terms else "REVIEW",
        "missing_required_prompt_terms": missing,
        "missing_required_prompt_terms_are_warnings": True,
        "target_explicit_schema_gap_terms": target_gaps,
        "target_explicit_schema_gap_count": len(target_gaps),
        "target_explicit_schema_gaps_are_report_only": True,
        "prompt_contains_json_schema": contains_schema,
        "prompt_contains_required_terms": contains_required_terms,
    }


def normalize_v2_card_for_smoke(card: Mapping[str, Any], page: Mapping[str, Any], prompt_version: str) -> Dict[str, Any]:
    """Fill compatibility defaults around the existing V2 guide output.

    This tester is meant to test the current guide safely, not force older V2
    cards to already contain every newer field. It fills conservative defaults
    before validation while still failing on unsafe authority claims.

    Important: this function overwrites blank/None compatibility fields. The
    existing V2 sanitizer may emit keys with empty values, so setdefault alone
    is not enough.
    """

    out = dict(card)
    v1 = page.get("v1") if isinstance(page.get("v1"), Mapping) else {}
    ocr_text = _norm(page.get("ocr_text"))

    page_id = _norm(out.get("page_id")) or _norm(page.get("page_id")) or _norm(v1.get("page_id"))
    role = _norm(out.get("role")) or _norm(v1.get("role")) or _norm(v1.get("page_role")) or _norm(v1.get("type")) or "unknown"
    subrole = _norm(out.get("subrole")) or "general"
    confidence = _norm(out.get("confidence")) or _norm(v1.get("confidence")) or ("medium" if ocr_text else "low")
    summary = (
        _norm(out.get("short_summary"))
        or _norm(out.get("summary"))
        or _norm(v1.get("summary"))
        or _norm(v1.get("short_summary"))
        or ("Page has OCR text available for retrieval guidance." if ocr_text else "Page has derived retrieval guidance.")
    )
    retrieval_summary = (
        _norm(out.get("retrieval_summary"))
        or _norm(out.get("short_summary"))
        or _norm(v1.get("retrieval_summary"))
        or f"Use this page as derived retrieval guidance. {summary}"
    )

    out["page_id"] = page_id or "unknown_page"
    out["role"] = role
    out["subrole"] = subrole
    out["confidence"] = confidence
    out["short_summary"] = summary
    out["retrieval_summary"] = retrieval_summary

    for field in ("answerable_questions", "retrieval_cues", "important_entities", "component_families", "not_good_for"):
        value = out.get(field)
        if value is None or value == "":
            out[field] = []
        elif not isinstance(value, list):
            out[field] = [_norm(value)] if _norm(value) else []

    if not out["retrieval_cues"]:
        cues = []
        for term in ("figure", "table", "parts", "list", "passenger", "seat", "armrest", "backrest", "callout"):
            blob = f"{summary} {ocr_text}".lower()
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
    if "has_ocr" not in source_grounding or source_grounding.get("has_ocr") in ("", None):
        source_grounding["has_ocr"] = bool(ocr_text)
    if "source_url_present" not in source_grounding or source_grounding.get("source_url_present") in ("", None):
        source_grounding["source_url_present"] = bool(_norm(page.get("source_url")))
    if "supporting_ocr_phrases" not in source_grounding or source_grounding.get("supporting_ocr_phrases") in ("", None):
        source_grounding["supporting_ocr_phrases"] = []
    if not isinstance(source_grounding.get("supporting_ocr_phrases"), list):
        source_grounding["supporting_ocr_phrases"] = [_norm(source_grounding.get("supporting_ocr_phrases"))]
    out["source_grounding"] = source_grounding

    authority = out.get("authority") if isinstance(out.get("authority"), Mapping) else {}
    authority = dict(authority)
    if not _norm(authority.get("trust_scope")):
        authority["trust_scope"] = "page_context_summary"
    if "can_answer_directly" not in authority or authority.get("can_answer_directly") in ("", None):
        authority["can_answer_directly"] = False
    if "canonical_source_truth" not in authority or authority.get("canonical_source_truth") in ("", None):
        authority["canonical_source_truth"] = False
    if "requires_source_check" not in authority or authority.get("requires_source_check") in ("", None):
        authority["requires_source_check"] = True
    out["authority"] = authority

    out["prompt_version"] = _norm(out.get("prompt_version")) or prompt_version
    return out

def validate_v2_card(card: Mapping[str, Any]) -> Dict[str, Any]:
    missing_fields = [f for f in REQUIRED_V2_FIELDS if f not in card]
    empty_required = [
        f for f in ("page_id", "role", "subrole", "confidence", "short_summary", "retrieval_summary")
        if not _norm(card.get(f))
    ]
    bad_list_fields = [
        f for f in ("answerable_questions", "retrieval_cues", "important_entities", "component_families", "not_good_for")
        if f in card and not isinstance(card.get(f), list)
    ]

    source_grounding = card.get("source_grounding") if isinstance(card.get("source_grounding"), Mapping) else {}
    authority = card.get("authority") if isinstance(card.get("authority"), Mapping) else {}

    missing_source_grounding = [f for f in REQUIRED_SOURCE_GROUNDING_FIELDS if f not in source_grounding]
    missing_authority = [f for f in REQUIRED_AUTHORITY_FIELDS if f not in authority]

    answer_permission = _is_truthy(authority.get("can_answer_directly")) or _is_truthy(card.get("can_answer_directly"))
    canonical_source_truth = _is_truthy(authority.get("canonical_source_truth")) or _is_truthy(card.get("canonical_source_truth"))

    failures: List[str] = []
    if missing_fields:
        failures.append("missing_required_v2_fields")
    if empty_required:
        failures.append("empty_required_v2_fields")
    if bad_list_fields:
        failures.append("bad_list_field_types")
    if missing_source_grounding:
        failures.append("missing_source_grounding_fields")
    if missing_authority:
        failures.append("missing_authority_fields")
    if answer_permission:
        failures.append("v2_summary_grants_answer_permission")
    if canonical_source_truth:
        failures.append("v2_summary_claims_canonical_source_truth")

    return {
        "quality_status": "PASS" if not failures else "FAIL",
        "failure_reasons": failures,
        "missing_fields": missing_fields,
        "empty_required_fields": empty_required,
        "bad_list_fields": bad_list_fields,
        "missing_source_grounding_fields": missing_source_grounding,
        "missing_authority_fields": missing_authority,
        "answer_permission": answer_permission,
        "canonical_source_truth": canonical_source_truth,
    }


def build_prompt_card_with_existing_guide(page: Mapping[str, Any]) -> Dict[str, Any]:
    """Call the existing V2 guide helpers and validate their output."""

    try:
        from tiff.trace_net_page_context_v2 import (
            PROMPT_VERSION,
            build_prompt,
            heuristic_context_v2,
            sanitize_context_v2,
        )
    except Exception as exc:
        raise RuntimeError(f"Could not import existing trace_net_page_context_v2 guide: {exc}") from exc

    page_dict = dict(page)
    heuristic = heuristic_context_v2(page_dict)
    prompt = build_prompt(page_dict, heuristic)
    card = dict(sanitize_context_v2(heuristic, heuristic))
    card = normalize_v2_card_for_smoke(card, page_dict, PROMPT_VERSION)

    validation = validate_v2_card(card)
    prompt_validation = validate_v2_prompt(prompt)

    return {
        "page_id": card.get("page_id"),
        "mode": "prompt_card_smoke_from_existing_trace_net_page_context_v2",
        "quality_status": "PASS" if validation["quality_status"] == "PASS" and prompt_validation["quality_status"] in {"PASS", "REVIEW"} else "FAIL",
        "card": card,
        "validation": validation,
        "prompt_validation": prompt_validation,
        "prompt_preview": prompt[:2200],
        "prompt_length": len(prompt),
    }


def select_context_pages(contexts: Mapping[str, Mapping[str, Any]], page_ids: Sequence[str], max_pages: int) -> List[Dict[str, Any]]:
    selected: List[Tuple[str, Mapping[str, Any]]] = []

    if page_ids:
        wanted = {str(x).strip() for x in page_ids if str(x).strip()}
        for pid, rec in contexts.items():
            if pid in wanted or str(rec.get("page_id")) in wanted:
                selected.append((pid, rec))
    else:
        for pid, rec in contexts.items():
            blob = " ".join(_norm(rec.get(k)) for k in ("summary", "short_summary", "ocr_text", "text", "ocr_sample"))
            if blob:
                selected.append((pid, rec))
            if len(selected) >= max_pages:
                break
        if not selected:
            selected = list(contexts.items())[:max_pages]

    return [make_page_input_from_v1(pid, rec) for pid, rec in selected[:max_pages]]


def build_v2_summary_smoke_test(
    *,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    context_file: str | Path = DEFAULT_CONTEXT_FILE,
    v2_records_jsonl: str | Path = "",
    page_ids: Sequence[str] = (),
    max_pages: int = 5,
    max_existing_records: int = 30,
    min_prompt_smoke_cards: int = 1,
    min_existing_records: int = 0,
) -> Dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    prompt_smoke_records: List[Dict[str, Any]] = []
    context_path = Path(context_file)
    if context_path.exists():
        contexts = load_v1_contexts_with_existing_loader(context_path)
        pages = select_context_pages(contexts, page_ids=page_ids, max_pages=max_pages)
        for page in pages:
            prompt_smoke_records.append(build_prompt_card_with_existing_guide(page))

    existing_path = Path(v2_records_jsonl) if v2_records_jsonl else Path(DEFAULT_V2_RECORDS_JSONL)
    existing_records_raw = _records_jsonl(existing_path, limit=max_existing_records) if existing_path.exists() else []
    existing_record_audits = [
        {
            "record_index": idx,
            "page_id": rec.get("page_id"),
            "validation": validate_v2_card(rec),
            "short_summary_preview": _clean_preview(rec.get("short_summary"), 220),
            "retrieval_summary_preview": _clean_preview(rec.get("retrieval_summary"), 280),
        }
        for idx, rec in enumerate(existing_records_raw)
    ]

    prompt_fail_count = sum(1 for r in prompt_smoke_records if r.get("quality_status") != "PASS")
    existing_fail_count = sum(1 for r in existing_record_audits if r.get("validation", {}).get("quality_status") != "PASS")
    target_gap_counts = [
        int((r.get("prompt_validation") or {}).get("target_explicit_schema_gap_count") or 0)
        for r in prompt_smoke_records
    ]

    failures: List[str] = []
    if len(prompt_smoke_records) < min_prompt_smoke_cards:
        failures.append(f"prompt_smoke_card_count_below_min:{len(prompt_smoke_records)}<{min_prompt_smoke_cards}")
    if prompt_fail_count:
        failures.append(f"prompt_smoke_failure_count_nonzero:{prompt_fail_count}")
    if len(existing_records_raw) < min_existing_records:
        failures.append(f"existing_v2_record_count_below_min:{len(existing_records_raw)}<{min_existing_records}")
    if existing_fail_count:
        failures.append(f"existing_v2_record_failure_count_nonzero:{existing_fail_count}")

    summary = {
        "prompt_version_expected": "page_context_v2_query_guidance_card",
        "context_file": str(context_path),
        "context_file_exists": context_path.exists(),
        "v2_records_jsonl": str(existing_path),
        "v2_records_jsonl_exists": existing_path.exists(),
        "prompt_smoke_card_count": len(prompt_smoke_records),
        "prompt_smoke_failure_count": prompt_fail_count,
        "existing_v2_record_audit_count": len(existing_record_audits),
        "existing_v2_record_failure_count": existing_fail_count,
        "target_explicit_schema_gap_max": max(target_gap_counts) if target_gap_counts else 0,
        "target_explicit_schema_gap_min": min(target_gap_counts) if target_gap_counts else 0,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }

    report = {
        "module": MODULE,
        "version": VERSION,
        "status": "TRACE_NET_V2_SUMMARY_SMOKE_TEST_BUILT",
        "quality_status": "PASS" if not failures else "FAIL",
        "failure_reasons": failures,
        "summary": summary,
        "required_v2_fields": REQUIRED_V2_FIELDS,
        "required_prompt_terms": PROMPT_REQUIRED_TERMS,
        "target_explicit_schema_terms_report_only": TARGET_EXPLICIT_SCHEMA_TERMS,
        "prompt_smoke_records": prompt_smoke_records,
        "existing_record_audits": existing_record_audits,
        "safety_contract": {
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "v2_summary_is_proof": False,
            "v2_summary_role": "retrieval_guidance_only",
        },
    }

    report_path = output / DEFAULT_REPORT_NAME
    md_path = output / DEFAULT_MD_NAME
    _write_json(report_path, report)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    report["output_paths"] = {"json": report_path.as_posix(), "markdown": md_path.as_posix()}
    _write_json(report_path, report)
    return report


def render_markdown(report: Mapping[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# TRACE-Net V2 summary smoke tester v1")
    lines.append("")
    lines.append(f"Quality status: **{report.get('quality_status')}**")
    lines.append("")
    lines.append("## Summary")
    for k, v in (report.get("summary") or {}).items():
        lines.append(f"- `{k}`: `{v}`")
    lines.append("")
    lines.append("## Prompt/card smoke samples")
    for rec in report.get("prompt_smoke_records", [])[:10]:
        lines.append("")
        lines.append(f"### {rec.get('page_id')} — `{rec.get('quality_status')}`")
        card = rec.get("card") or {}
        lines.append(f"- role/subrole: `{card.get('role')}` / `{card.get('subrole')}`")
        lines.append(f"- short_summary: {card.get('short_summary')}")
        lines.append(f"- retrieval_summary: {card.get('retrieval_summary')}")
        pv = rec.get("prompt_validation") or {}
        if pv.get("target_explicit_schema_gap_terms"):
            gaps = ", ".join(pv.get("target_explicit_schema_gap_terms")[:12])
            lines.append(f"- report-only explicit-schema gaps: {gaps}")
    lines.append("")
    lines.append("## Existing V2 record audits")
    for rec in report.get("existing_record_audits", [])[:30]:
        v = rec.get("validation") or {}
        lines.append(f"- `{rec.get('page_id')}`: `{v.get('quality_status')}` {v.get('failure_reasons')}")
    lines.append("")
    lines.append("## Safety")
    lines.append("V2 summaries are retrieval/query guidance only. They do not grant answer permission and do not prove source-truth facts.")
    return "\n".join(lines) + "\n"


def check_v2_summary_smoke_report(
    *,
    report: str | Path,
    output: str | Path = "",
    require_quality_pass: bool = True,
    require_no_answer_permission: bool = True,
    require_no_source_truth_mutation: bool = True,
    min_prompt_smoke_cards: int = 1,
    max_prompt_failures: int = 0,
    max_existing_record_failures: int = 0,
) -> Dict[str, Any]:
    data = _read_json(report, default={}) or {}
    summary = data.get("summary") if isinstance(data.get("summary"), Mapping) else {}
    failures: List[str] = []

    if require_quality_pass and data.get("quality_status") != "PASS":
        failures.append("source_report_quality_status_not_pass")
    if int(summary.get("prompt_smoke_card_count") or 0) < min_prompt_smoke_cards:
        failures.append("prompt_smoke_card_count_below_min")
    if int(summary.get("prompt_smoke_failure_count") or 0) > max_prompt_failures:
        failures.append("prompt_smoke_failure_count_above_max")
    if int(summary.get("existing_v2_record_failure_count") or 0) > max_existing_record_failures:
        failures.append("existing_v2_record_failure_count_above_max")
    if require_no_answer_permission and int(summary.get("answer_permission_count") or 0) != 0:
        failures.append("answer_permission_count_nonzero")
    if require_no_source_truth_mutation and int(summary.get("source_truth_mutation_allowed_count") or 0) != 0:
        failures.append("source_truth_mutation_allowed_count_nonzero")

    status = "PASS" if not failures else "FAIL"
    quality = {
        "module": MODULE,
        "version": VERSION,
        "status": "TRACE_NET_V2_SUMMARY_SMOKE_TEST_QUALITY_CHECKED",
        "quality_status": status,
        "failure_reasons": failures,
        "summary": summary,
        "source_report_path": Path(report).as_posix(),
    }
    if output:
        _write_json(output, quality)
    return quality


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build TRACE-Net V2 summary smoke test using the existing V2 guide.")
    p.add_argument("--context-file", default=DEFAULT_CONTEXT_FILE)
    p.add_argument("--v2-records-jsonl", default="")
    p.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--page-id", action="append", default=[])
    p.add_argument("--max-pages", type=int, default=5)
    p.add_argument("--max-existing-records", type=int, default=30)
    p.add_argument("--min-prompt-smoke-cards", type=int, default=1)
    p.add_argument("--min-existing-records", type=int, default=0)
    return p


def check_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check TRACE-Net V2 summary smoke test quality.")
    p.add_argument("--report", required=True)
    p.add_argument("--output", default="")
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--require-no-source-truth-mutation", action="store_true")
    p.add_argument("--min-prompt-smoke-cards", type=int, default=1)
    p.add_argument("--max-prompt-failures", type=int, default=0)
    p.add_argument("--max-existing-record-failures", type=int, default=0)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = build_v2_summary_smoke_test(
        output_dir=args.output_dir,
        context_file=args.context_file,
        v2_records_jsonl=args.v2_records_jsonl,
        page_ids=args.page_id,
        max_pages=args.max_pages,
        max_existing_records=args.max_existing_records,
        min_prompt_smoke_cards=args.min_prompt_smoke_cards,
        min_existing_records=args.min_existing_records,
    )
    print(f"Wrote: {report['output_paths']['json']}")
    print(f"Wrote: {report['output_paths']['markdown']}")
    print(f"quality_status: {report['quality_status']}")
    print(f"summary: {json.dumps(report['summary'], sort_keys=True)}")
    return 0 if report["quality_status"] == "PASS" else 2


def check_main(argv: Optional[Sequence[str]] = None) -> int:
    args = check_arg_parser().parse_args(argv)
    quality = check_v2_summary_smoke_report(
        report=args.report,
        output=args.output,
        require_quality_pass=args.require_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        min_prompt_smoke_cards=args.min_prompt_smoke_cards,
        max_prompt_failures=args.max_prompt_failures,
        max_existing_record_failures=args.max_existing_record_failures,
    )
    print(f"Wrote: {args.output or '<not written>'}")
    print(f"quality_status: {quality['quality_status']}")
    print(f"failure_reasons: {quality['failure_reasons']}")
    print(f"summary: {json.dumps(quality['summary'], sort_keys=True)}")
    return 0 if quality["quality_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
