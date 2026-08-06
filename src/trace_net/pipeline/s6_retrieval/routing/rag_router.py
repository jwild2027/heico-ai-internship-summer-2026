"""Query routing for local TIFF RAG.

Exact part lookups should stay deterministic. Broader questions should use a
hybrid evidence set: structured part catalog, nomenclature reverse lookup,
keyword OCR, and vector/semantic OCR when available.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

try:
    from tiff.search_index import is_probable_part_number, normalize_part_number
except Exception:  # pragma: no cover - isolated unit-test fallback
    def normalize_part_number(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9]", "", value or "").upper()

    def is_probable_part_number(value: str) -> bool:
        norm = normalize_part_number(value)
        return len(norm) >= 6 and any(ch.isdigit() for ch in norm)


PART_NUMBER_PATTERN = re.compile(r"[A-Za-z0-9]+(?:[-/][A-Za-z0-9]+){1,}")

SUMMARY_WORDS = {
    "ABOUT",
    "AVAILABLE",
    "DESCRIBE",
    "DISCUSS",
    "DISCUSSED",
    "DISCUSSES",
    "DISCUSSION",
    "EXPLAIN",
    "INFO",
    "INFORMATION",
    "OVERVIEW",
    "RELATED",
    "RELATES",
    "RELATING",
    "SUMMARY",
    "SUMMARIZE",
    "SUMMARISE",
    "TELL",
}

COMPARE_WORDS = {
    "COMPARE",
    "COMPARISON",
    "DIFFERENCE",
    "DIFFERENCES",
    "DIFFERENT",
    "DISTINGUISH",
    "VERSUS",
    "VS",
}

LOCATE_WORDS = {
    "APPEAR",
    "APPEARS",
    "FIND",
    "FOUND",
    "LIST",
    "LISTED",
    "LOCATE",
    "MENTION",
    "MENTIONED",
    "MENTIONS",
    "PAGE",
    "PAGES",
    "SHOW",
    "SHOWING",
    "SHOWN",
    "SHOWS",
    "SOURCE",
    "SOURCES",
    "WHERE",
    "WHICH",
}

QUESTION_FILLER_WORDS = {
    "A",
    "AN",
    "AND",
    "ARE",
    "AS",
    "AT",
    "BE",
    "BY",
    "CAN",
    "DO",
    "DOES",
    "FOR",
    "FROM",
    "GIVE",
    "HAS",
    "HAVE",
    "I",
    "IN",
    "IS",
    "IT",
    "LOCAL",
    "ME",
    "OF",
    "ON",
    "OR",
    "PART",
    "PARTS",
    "PLEASE",
    "SOURCE",
    "SOURCES",
    "THE",
    "THIS",
    "TO",
    "UP",
    "WHAT",
    "WHEN",
    "WHERE",
    "WHICH",
    "WITH",
}


@dataclass(frozen=True)
class QueryRoute:
    query: str
    answer_mode: str
    retrieval_mode: str
    part_number_display: str = ""
    part_number_normalized: str = ""
    allow_structured_answer: bool = False
    should_use_llm: bool = True
    should_try_embeddings: bool = True
    should_try_nomenclature: bool = True
    reason: str = ""


def query_words(query: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[A-Za-z0-9]+", (query or "").upper()))


def query_word_set(query: str) -> set[str]:
    return set(query_words(query))


def extract_part_number(query: str) -> tuple[str, str]:
    candidates = PART_NUMBER_PATTERN.findall(query or "")
    for candidate in candidates:
        if is_probable_part_number(candidate):
            return candidate, normalize_part_number(candidate)
    if is_probable_part_number(query or ""):
        return query, normalize_part_number(query)
    return "", ""


def has_any(words: set[str], options: set[str]) -> bool:
    return bool(words & options)


def content_tokens(query: str) -> tuple[str, ...]:
    out: list[str] = []
    for token in query_words(query):
        if token in QUESTION_FILLER_WORDS:
            continue
        if token in SUMMARY_WORDS or token in COMPARE_WORDS or token in LOCATE_WORDS:
            continue
        if token.isdigit() or len(token) <= 1:
            continue
        if len(token) > 4 and token.endswith("IES"):
            token = token[:-3] + "Y"
        elif len(token) > 3 and token.endswith("S") and not token.endswith("SS"):
            token = token[:-1]
        out.append(token)
    return tuple(out)


def classify_query(
    query: str,
    *,
    answer_mode: str = "auto",
    retrieval_mode: str = "auto",
    force_llm: bool = False,
) -> QueryRoute:
    """Classify a user question into a retrieval/answer strategy."""

    forced_answer = (answer_mode or "auto").strip().lower()
    forced_retrieval = (retrieval_mode or "auto").strip().lower()
    words = query_word_set(query)
    part_display, part_norm = extract_part_number(query)
    wants_compare = has_any(words, COMPARE_WORDS)
    wants_summary = has_any(words, SUMMARY_WORDS)
    wants_location = has_any(words, LOCATE_WORDS)
    name_tokens = content_tokens(query)

    if forced_answer in {"compare"} or (forced_answer == "auto" and wants_compare):
        route = QueryRoute(query, "compare", "hybrid", part_display, part_norm, False, True, True, True, "compare question")
    elif forced_answer in {"summarize", "summary", "broad"} or (forced_answer == "auto" and wants_summary):
        mode = "nomenclature_summary" if name_tokens else "summarize"
        route = QueryRoute(query, mode, "hybrid", part_display, part_norm, False, True, True, True, "summary question")
    elif forced_answer in {"lookup", "part_lookup"} or (forced_answer == "auto" and part_norm):
        route = QueryRoute(query, "part_lookup", "structured", part_display, part_norm, True, False, False, False, "exact part number lookup")
    elif forced_answer in {"locate", "nomenclature_locate"} or (forced_answer == "auto" and name_tokens and (wants_location or len(name_tokens) <= 4)):
        route = QueryRoute(query, "nomenclature_locate", "structured", part_display, part_norm, True, False, False, True, "nomenclature locate lookup")
    else:
        route = QueryRoute(query, "broad", "hybrid", part_display, part_norm, False, True, True, True, "broad question")

    if forced_retrieval in {"structured", "keyword", "semantic", "hybrid"}:
        route = QueryRoute(
            query=route.query,
            answer_mode=route.answer_mode,
            retrieval_mode=forced_retrieval,
            part_number_display=route.part_number_display,
            part_number_normalized=route.part_number_normalized,
            allow_structured_answer=route.allow_structured_answer and not force_llm,
            should_use_llm=route.should_use_llm or force_llm,
            should_try_embeddings=route.should_try_embeddings or forced_retrieval in {"semantic", "hybrid"},
            should_try_nomenclature=route.should_try_nomenclature,
            reason=route.reason + f"; forced retrieval={forced_retrieval}",
        )
    elif force_llm:
        route = QueryRoute(
            query=route.query,
            answer_mode=route.answer_mode,
            retrieval_mode=route.retrieval_mode,
            part_number_display=route.part_number_display,
            part_number_normalized=route.part_number_normalized,
            allow_structured_answer=False,
            should_use_llm=True,
            should_try_embeddings=route.should_try_embeddings,
            should_try_nomenclature=route.should_try_nomenclature,
            reason=route.reason + "; forced llm",
        )
    return route

# Compatibility alias used by the existing answer layer.
def route_query(
    question: str,
    *,
    answer_mode: str = "auto",
    retrieval_mode: str = "auto",
    force_llm: bool = False,
) -> QueryRoute:
    return classify_query(
        question,
        answer_mode=answer_mode,
        retrieval_mode=retrieval_mode,
        force_llm=force_llm,
    )
