"""UI helper utilities for TIFF API trace and feedback views.

These functions are intentionally pure and dependency-free so the Streamlit
layout can stay thin and the behavior can be unit-tested without Streamlit.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping


PART_RE = re.compile(r"\b(?:[A-Z]{1,4}\d{2,6}-\d{1,4}|\d{3}-\d{4,6}-\d{1,4}|\d{2,6}-\d{2,6}-\d{1,4})\b", re.I)
PAGE_RE = re.compile(r"\bt_p_\d+_\d+_p\d{6}\b", re.I)
ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")


FEEDBACK_CATEGORIES = [
    "useful",
    "wrong_answer",
    "wrong_source",
    "missing_source",
    "incomplete",
    "too_verbose",
    "ocr_issue",
    "part_number_issue",
    "trace_unclear",
    "other",
]


RATINGS = ["up", "down", "neutral", "1", "2", "3", "4", "5"]


def first_string(*values: Any) -> str:
    """Return the first non-empty string among values."""

    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def compact_text(value: Any, *, max_chars: int = 180) -> str:
    """Return a compact one-line text preview."""

    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    if max_chars > 0 and len(text) > max_chars:
        return text[: max_chars - 1].rstrip() + "…"
    return text


def find_first_part(text: str) -> str | None:
    match = PART_RE.search(text or "")
    return match.group(0).upper() if match else None


def find_first_page_id(text: str) -> str | None:
    match = PAGE_RE.search(text or "")
    return match.group(0) if match else None


def find_first_ata(text: str) -> str | None:
    match = ATA_RE.search(text or "")
    return match.group(0) if match else None


def infer_trace_target(question: str, answer: str = "") -> dict[str, str]:
    combined = f"{question or ''}\n{answer or ''}"
    page_id = find_first_page_id(combined)
    if page_id:
        return {"type": "page", "value": page_id}
    ata_code = find_first_ata(combined)
    if ata_code:
        return {"type": "ata", "value": ata_code}
    part_number = find_first_part(combined)
    if part_number:
        return {"type": "part", "value": part_number}
    return {"type": None, "value": None}
def payload_summary(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Extract the fields most useful for top-level UI summaries."""

    if not isinstance(payload, Mapping):
        return {}
    wanted = (
        "status",
        "part_number",
        "nomenclature",
        "page_id",
        "document",
        "ata",
        "ata_code",
        "source_link_present",
        "context_present",
        "context_score",
        "total_pages_found",
        "sample_pages_with_context",
        "sample_pages_with_source_links",
        "pages",
        "parts",
        "page_context_nodes",
        "source_link_nodes",
    )
    out: dict[str, Any] = {}
    for key in wanted:
        value = payload.get(key)
        if value is not None and not isinstance(value, (dict, list)):
            out[key] = value
    nested = payload.get("summary")
    if isinstance(nested, Mapping):
        for key in wanted:
            value = nested.get(key)
            if value is not None and not isinstance(value, (dict, list)):
                out.setdefault(key, value)
    trace = payload.get("trace")
    if isinstance(trace, Mapping):
        nested_summary = trace.get("summary")
        if isinstance(nested_summary, Mapping):
            for key in wanted:
                value = nested_summary.get(key)
                if value is not None and not isinstance(value, (dict, list)):
                    out.setdefault(key, value)
    return out


def trace_steps(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Normalize trace path entries from several API/script payload shapes."""

    if not isinstance(payload, Mapping):
        return []
    candidates: list[Any] = []
    for key in ("path", "steps"):
        candidates.append(payload.get(key))
    trace = payload.get("trace")
    if isinstance(trace, Mapping):
        for key in ("path", "steps"):
            candidates.append(trace.get(key))
    report = payload.get("report")
    if isinstance(report, Mapping):
        for key in ("path", "steps"):
            candidates.append(report.get(key))

    for value in candidates:
        if isinstance(value, list):
            normalized: list[dict[str, Any]] = []
            for idx, item in enumerate(value, start=1):
                if isinstance(item, Mapping):
                    normalized.append(dict(item))
                else:
                    normalized.append({"index": idx, "label": str(item)})
            return normalized
    return []


def step_title(step: Mapping[str, Any], index: int) -> str:
    """Return a concise title for a trace step."""

    label = first_string(step.get("label"), step.get("description"), step.get("relationship"), step.get("edge_type"))
    source = first_string(step.get("source_label"), step.get("from_label"), step.get("source"), step.get("from"))
    target = first_string(step.get("target_label"), step.get("to_label"), step.get("target"), step.get("to"), step.get("node"))
    if label and target:
        return f"{index}. {label} → {compact_text(target, max_chars=90)}"
    if target:
        return f"{index}. {compact_text(target, max_chars=110)}"
    if source and label:
        return f"{index}. {compact_text(source, max_chars=70)} — {label}"
    return f"{index}. {compact_text(step, max_chars=120)}"


def step_body(step: Mapping[str, Any]) -> dict[str, Any]:
    """Return useful non-title details from a trace step."""

    omit = {
        "label",
        "description",
        "relationship",
        "edge_type",
        "source_label",
        "from_label",
        "source",
        "from",
        "target_label",
        "to_label",
        "target",
        "to",
        "node",
    }
    return {k: v for k, v in step.items() if k not in omit and v not in (None, "", [])}


def flatten_feedback_items(payload: Mapping[str, Any] | None, *, limit: int = 10) -> list[dict[str, Any]]:
    """Extract recent feedback rows from compatible summary payloads."""

    if not isinstance(payload, Mapping):
        return []
    for key in ("recent", "recent_feedback", "items", "feedback", "records"):
        value = payload.get(key)
        if isinstance(value, list):
            rows = [dict(item) if isinstance(item, Mapping) else {"value": item} for item in value]
            return rows[:limit]
    nested = payload.get("summary")
    if isinstance(nested, Mapping):
        return flatten_feedback_items(nested, limit=limit)
    return []


def feedback_stats(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Extract count-like feedback fields for display."""

    if not isinstance(payload, Mapping):
        return {}
    wanted = (
        "total",
        "total_feedback",
        "count",
        "up",
        "down",
        "neutral",
        "positive",
        "negative",
        "useful",
        "wrong_answer",
        "wrong_source",
        "missing_source",
        "incomplete",
        "too_verbose",
        "ocr_issue",
    )
    out: dict[str, Any] = {}
    for key in wanted:
        value = payload.get(key)
        if isinstance(value, (int, float, str)):
            out[key] = value
    by_rating = payload.get("by_rating") or payload.get("ratings")
    if isinstance(by_rating, Mapping):
        for key, value in by_rating.items():
            out[f"rating:{key}"] = value
    by_category = payload.get("by_category") or payload.get("categories")
    if isinstance(by_category, Mapping):
        for key, value in by_category.items():
            out[f"category:{key}"] = value
    nested = payload.get("summary")
    if isinstance(nested, Mapping):
        out.update({k: v for k, v in feedback_stats(nested).items() if k not in out})
    return out


def answer_quality_hint(rating: str, category: str) -> str:
    rating_norm = (rating or "").strip().lower()
    category_norm = (category or "").strip().lower()
    if rating_norm in {"up", "4", "5"}:
        return "Positive feedback will help identify strong answer/source patterns."
    if category_norm in {"wrong_source", "missing_source"}:
        return "This should create a source-trace review candidate."
    if category_norm in {"wrong_answer", "part_number_issue", "ocr_issue"}:
        return "This should create a QA/eval review candidate."
    if category_norm == "too_verbose":
        return "This should inform answer-format and UI-collapsing improvements."
    return "Feedback is stored for review; it does not automatically change source facts."
