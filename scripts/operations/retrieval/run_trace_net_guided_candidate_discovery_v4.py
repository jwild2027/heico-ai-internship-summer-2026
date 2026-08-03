#!/usr/bin/env python3
"""
TRACE-Net guided candidate discovery v4.

Purpose:
  Low-context / partial part-number lookup that returns candidate routes instead of a final answer.

Key v4 behavior:
  - strict prefix matches are separated from loose contains matches
  - if user says "starts with 24", main candidates must start with 24
  - loose candidates are clearly labeled as weaker related candidates
  - route output is UI-friendly and source-trace cautious
  - final_answer_allowed is always false for candidate discovery

Safety contract:
  - read-only artifact scanning
  - no DB writes
  - no source-truth mutation
  - no final answer permission
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

TEXT_SUFFIXES = {
    ".json",
    ".jsonl",
    ".csv",
    ".txt",
    ".md",
    ".yaml",
    ".yml",
    ".tsv",
}

ATA_RE = re.compile(r"\b(?:ATA\s*)?(\d{2}-\d{2}-\d{2})\b", re.IGNORECASE)
PAGE_ID_RE = re.compile(r"\bt_p_\d+_\d+_p\d{6}\b")
SOURCE_PAGE_RE = re.compile(r"\bsource_p(\d{6})\b")
BARE_PAGE_RE = re.compile(r"(?<![A-Za-z0-9])p(\d{6})(?![A-Za-z0-9])")
DOC_RE = re.compile(r"\bEMB\s+CMM\s+ATA\s+\d{2}-\d{2}-\d{2}\s+REV\.?\s*\d+\b", re.IGNORECASE)

# A deliberately conservative part-like pattern. It captures aviation-style mixed alnum,
# hyphenated, and dotted identifiers while letting downstream filters remove page ids,
# ATA codes, years, and tiny numbers.
PART_TOKEN_RE = re.compile(
    r"\b(?:[A-Z]{0,6}\d{2,}[A-Z0-9]*(?:[-.][A-Z0-9]{1,10}){0,4}|\d{2,}[A-Z][A-Z0-9]*(?:[-.][A-Z0-9]{1,10}){0,4})\b",
    re.IGNORECASE,
)

HEXISH_RE = re.compile(r"^[0-9a-f]{10,}$", re.IGNORECASE)
DECIMAL_NOISE_RE = re.compile(r"^\d+\.\d+$")
UUIDISH_HYPHEN_RE = re.compile(r"^(?:[0-9a-f]{4,}-){1,}[0-9a-f]{4,}$", re.IGNORECASE)
FILE_TOKEN_RE = re.compile(r"\.(?:tif|tiff|png|jpg|jpeg|json|jsonl|csv|txt|md)$", re.IGNORECASE)
LONG_HEX_GROUP_RE = re.compile(r"^[0-9a-f-]{12,}$", re.IGNORECASE)
EXPLICIT_PART_CONTEXT_RE = re.compile(
    r"\b(part\s*(?:number|no\.?|num\.?|#)?|part_number|covered_part_number|ipl_part_number|pn|p/n)\b",
    re.IGNORECASE,
)
VALID_PART_PREFIX_RE = re.compile(r"^(?:MS|NAS|AN|PE|AM|DF|Z|VS|BAC|D|E|120TP|120|429|345)", re.IGNORECASE)

JUNK_TOKENS = {
    "u2026",
    "u00a0",
    "none",
    "null",
    "true",
    "false",
    "figure",
    "source",
    "record",
}

META_PATH_HINTS = (
    "prompt",
    "answer_draft",
    "answer_writer",
    "fast_chat_runner",
    "samples",
    "smoke",
)

BAD_NOMENCLATURE_VALUES = {
    "HIGH_NAVIGATION_CONFIDENCE",
    "SOURCE_BOUND_RESPONSE_SHOULD_SUMMARIZE_SOURCE_LINKED_PAGE_ON",
    "HAS_TABLE_ROW",
    "HAS_TABLE_CELL",
    "HAS_CONTEXT_V2",
    "PAGE_CONTEXT_V2",
    "UNKNOWN",
}
BAD_NOMENCLATURE_PREFIXES = (
    "EMB CMM ATA",
    "MAINTENANCE MANUAL WITH",
    "SOURCE_BOUND_RESPONSE",
    "HIGH_NAVIGATION",
    "HAS_",
    "TRACE_NET_",
    "PAGE_CONTEXT",
)

V2_HINTS = ("page_context_v2", "v2_summary", "context_v2")
V3_HINTS = ("page_context_v3", "v3_summary", "context_v3")


@dataclass
class QueryClues:
    question: str
    intent: str
    part_prefix: Optional[str] = None
    contains_digits: Optional[str] = None
    raw_digits: List[str] = field(default_factory=list)
    strict_prefix_requested: bool = False
    low_context: bool = True
    missing_clues: List[str] = field(default_factory=list)
    clarifying_questions: List[str] = field(default_factory=list)
    description_terms: List[str] = field(default_factory=list)


@dataclass
class EvidenceHit:
    part_number: str
    match_type: str
    match_reason: str
    page_id: Optional[str]
    document: Optional[str]
    ata: Optional[str]
    nomenclature: Optional[str]
    evidence_types: List[str]
    source_path: str
    snippet: str
    v2_summary: Optional[str] = None
    v3_summary: Optional[str] = None
    candidate_quality: str = "valid_part_like"
    quality_reason: str = "valid part-like token"
    score: int = 0


@dataclass
class CandidateRoute:
    route_id: str
    route_group: str
    candidate_part_number: str
    ata: str
    nomenclature: str
    page_id: str
    document: str
    evidence_types: List[str]
    v2_summary: str
    v3_summary: str
    confidence: str
    why_matched: str
    candidate_quality: str = "valid_part_like"
    quality_reason: str = "valid part-like token"
    source_trace_status: str = "candidate-discovery-only"
    final_answer_allowed: bool = False
    evidence_count: int = 0
    source_examples: List[str] = field(default_factory=list)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_part_token(token: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", token.upper())


def is_ata_code(token: str) -> bool:
    return bool(re.fullmatch(r"\d{2}-\d{2}-\d{2}", token.strip()))


def is_probable_part_token(token: str) -> bool:
    """Fast token-level screen before context-aware quality classification."""
    t = token.strip().strip(",;:()[]{}'")
    t = t.rstrip(".")
    if not t:
        return False
    low = t.lower()
    if low in JUNK_TOKENS:
        return False
    if FILE_TOKEN_RE.search(t) or low.endswith((".tif", ".tiff")):
        return False
    if PAGE_ID_RE.search(t) or SOURCE_PAGE_RE.search(t):
        return False
    if is_ata_code(t):
        return False
    if DECIMAL_NOISE_RE.fullmatch(t):
        return False
    norm = normalize_part_token(t)
    if len(norm) < 4:
        return False
    if HEXISH_RE.fullmatch(norm) and len(norm) >= 10 and not re.search(r"[-.]", t):
        return False
    if UUIDISH_HYPHEN_RE.fullmatch(t):
        return False
    if LONG_HEX_GROUP_RE.fullmatch(t) and re.search(r"[a-f]", t, re.IGNORECASE) and not VALID_PART_PREFIX_RE.search(norm):
        return False
    if norm.isdigit():
        if len(norm) < 6:
            return False
        if norm.startswith("000"):
            return False
        if 1900 <= int(norm[:4]) <= 2099 and len(norm) == 4:
            return False
    if re.fullmatch(r"0{2,}\d+", norm):
        return False
    digit_count = sum(ch.isdigit() for ch in norm)
    if digit_count < 2:
        return False
    if len(norm) >= 5:
        return True
    return bool(re.search(r"[A-Z]", norm) and re.search(r"\d", norm))


def classify_candidate_quality(token: str, snippet: str = "", source_path: str = "") -> Tuple[str, str]:
    """Return valid_part_like, weak_token, or rejected_noise with a short reason.

    This is deliberately stricter than PART_TOKEN_RE. It prevents OCR floats,
    hashes, graph ids, and random short numbers from becoming user-facing routes.
    """
    t = token.strip().strip(",;:()[]{}'").rstrip(".")
    norm = normalize_part_token(t)
    hay = f"{source_path} {snippet}"
    if FILE_TOKEN_RE.search(t) or t.lower().endswith((".tif", ".tiff")):
        return "rejected_noise", "file/page artifact token, not a part number"
    if DECIMAL_NOISE_RE.fullmatch(t):
        return "rejected_noise", "decimal/OCR numeric noise, not a part-number shape"
    if re.fullmatch(r"\d+\.\d+[A-Za-z]?", t):
        return "rejected_noise", "decimal/measurement OCR noise"
    if re.fullmatch(r"\d{5,}[A-Fa-f]-\d{2}", t):
        return "rejected_noise", "scientific-notation/OCR artifact"
    if re.fullmatch(r"[nN]\d{2,3}-\d{4,6}(?:-\d{3})?", t):
        return "rejected_noise", "OCR-prefixed duplicate"
    if HEXISH_RE.fullmatch(norm) and len(norm) >= 10 and not re.search(r"[-.]", t):
        return "rejected_noise", "hash-like or graph-id-like token"
    if UUIDISH_HYPHEN_RE.fullmatch(t):
        return "rejected_noise", "UUID/hash-like hyphenated artifact identifier"
    if LONG_HEX_GROUP_RE.fullmatch(t) and re.search(r"[a-f]", t, re.IGNORECASE) and not VALID_PART_PREFIX_RE.search(norm):
        return "rejected_noise", "UUID/hash-like hyphenated artifact identifier"
    if re.fullmatch(r"[0-9a-f]{8,}", norm, re.IGNORECASE) and not re.search(r"[-.]", t):
        return "rejected_noise", "hex-like artifact identifier"
    explicit_part_context = bool(EXPLICIT_PART_CONTEXT_RE.search(hay))
    if norm.isdigit():
        if 4 <= len(norm) < 7:
            return "weak_token", "plain short numeric token; not user-facing without stronger part context"
    if not is_probable_part_token(t):
        return "rejected_noise", "failed fast part-token screen"
    if norm.isdigit():
        if len(norm) < 7:
            return "weak_token", "plain short numeric token; not user-facing without stronger part context"
        if explicit_part_context:
            return "valid_part_like", "plain numeric token with explicit part-number context"
        return "weak_token", "plain numeric token without explicit part-number context"
    if re.search(r"[-.]", t) and sum(ch.isdigit() for ch in norm) >= 2 and len(norm) >= 5:
        return "valid_part_like", "structured hyphen/dot part-like token"
    if VALID_PART_PREFIX_RE.search(norm) and len(norm) >= 5 and re.search(r"\d", norm):
        return "valid_part_like", "recognized aviation-style alphanumeric prefix"
    if len(norm) >= 7 and re.search(r"[A-Z]", norm) and re.search(r"\d", norm) and explicit_part_context:
        return "valid_part_like", "mixed alphanumeric token with explicit part-number context"
    return "weak_token", "weak part-like token; kept out of primary candidate routes"


def parse_query_clues(question: str) -> QueryClues:
    q = question.lower()
    strict = bool(re.search(r"\b(starts?|begins?|prefix(?:ed)?|first)\b", q))
    prefix = None
    raw_digits: List[str] = []
    m = re.search(r"(?:starts?|begins?|prefix(?:ed)?|first).{0,35}?(?:with\s+)?([a-z0-9][a-z0-9.-]{1,15})", q, re.I)
    if m:
        candidate = m.group(1).strip(" .,:;")
        if candidate.lower() not in {"with","number","numbers","digits","part","item"}:
            prefix = re.sub(r"[^A-Z0-9]", "", candidate.upper())[:16]
            raw_digits = re.findall(r"\d", prefix)
    contains_digits = None
    cm = re.search(r"(?:contains?|has|with).{0,30}?([0-9]{2,})", q)
    if cm and not strict:
        contains_digits = cm.group(1)
    vocab=("hinge","bracket","latch","locking ring","ring","seat leg","leg","armrest","ashtray","panel","cover","pin","bolt","fastener","spring","washer","bearing","support rail","rail","buckle","actuator","switch","valve","hose","fitting","screw","clip","assembly")
    description_terms=[term for term in vocab if re.search(r"\b"+re.escape(term)+r"\b",q)]
    missing=["manufacturer_or_company","physical_description_or_nomenclature","ata_or_system_area","figure_table_or_text_context","nearby_words_page_or_figure_number"]
    questions=["Do you remember any possible part-number characters, prefix, suffix, digits, or dash number?","Do you know the manufacturer or company, such as Honeywell, Embraer, Collins, Safran, Boeing, or Airbus?","Which ATA chapter, aircraft system, cabin area, or manual section was the part associated with?","Can you narrow the description—for example its location, material, shape, size, function, or connected assembly?","Was it seen in an illustrated parts list, a figure callout, a drawing, a page, or nearby text?"]
    intent="partial_part_prefix_lookup" if prefix else "partial_part_contains_lookup" if contains_digits else "descriptive_part_discovery" if description_terms else "low_context_part_discovery"
    return QueryClues(question=question,intent=intent,part_prefix=prefix,contains_digits=contains_digits,raw_digits=raw_digits,strict_prefix_requested=bool(prefix and strict),low_context=True,missing_clues=missing,clarifying_questions=questions,description_terms=description_terms)


def iter_text_files(root: Path, max_files: int = 250000) -> Iterable[Path]:
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip common caches and hidden dirs.
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in {"__pycache__", ".pytest_cache"}]
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() not in TEXT_SUFFIXES:
                continue
            count += 1
            if count > max_files:
                return
            yield p


def read_limited_text(path: Path, max_bytes: int = 750_000) -> str:
    try:
        with path.open("rb") as f:
            data = f.read(max_bytes)
        return data.decode("utf-8", errors="replace")
    except OSError:
        return ""


def extract_page_id(text: str, source_path: str = "") -> Optional[str]:
    for hay in (text, source_path):
        m = PAGE_ID_RE.search(hay)
        if m:
            return m.group(0)
        m = SOURCE_PAGE_RE.search(hay)
        if m:
            return f"t_p_120_1176_p{m.group(1)}"
        m = BARE_PAGE_RE.search(hay)
        if m:
            return f"t_p_120_1176_p{m.group(1)}"
    return None


def extract_ata(text: str, source_path: str = "") -> Optional[str]:
    for hay in (text, source_path):
        m = ATA_RE.search(hay)
        if m:
            return m.group(1)
    return None


def extract_document(text: str, source_path: str = "") -> Optional[str]:
    for hay in (text, source_path):
        m = DOC_RE.search(hay)
        if m:
            return clean_text(m.group(0)).upper().replace("REV .", "REV.")
    ata = extract_ata(text, source_path)
    if ata == "25-21-00":
        return "EMB CMM ATA 25-21-00 REV.4"
    return None


def detect_evidence_types(source_path: str, snippet: str) -> List[str]:
    hay = f"{source_path} {snippet}".lower()
    types: List[str] = []
    for label, needles in [
        ("table", ["table", "has_table_cell", "cell", "row"]),
        ("OCR", ["ocr", "tesseract", "line_text", "text"]),
        ("visual", ["visual", "figure", "callout", "llava", "image"]),
        ("graph", ["graph", "node", "edge", "part_on_page", "mentions_part"]),
        ("review", ["review", "human_review", "warning", "uncertainty"]),
        ("summary", ["summary", "page_context_v2", "page_context_v3"]),
    ]:
        if any(n in hay for n in needles):
            types.append(label)
    return sorted(set(types)) or ["artifact"]


def clean_nomenclature_value(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = clean_text(value).strip(" .,:;-_")
    if not v:
        return None
    upper = v.upper()
    if upper in BAD_NOMENCLATURE_VALUES:
        return None
    if any(upper.startswith(prefix) for prefix in BAD_NOMENCLATURE_PREFIXES):
        return None
    if "USER_QUERY" in upper or "QUERY_PLAN" in upper or "CATEGORY_COUNTS" in upper:
        return None
    if re.fullmatch(r"[A-Z_]{8,}", upper) and not any(word in upper for word in ["ASSY", "ASSEMBLY", "FASTENER", "BOLT", "SCREW", "RING", "PIN", "FITTING", "COVER", "BRACKET", "SEAT", "TABLE", "LATCH", "PANEL", "TRIM", "STRUCTURE"]):
        return None
    if len(v) > 120:
        v = v[:120].rstrip()
    return v


def extract_nomenclature_near_part(snippet: str, part: str) -> Optional[str]:
    # Prefer explicit nomenclature/description fields when present.
    explicit = re.search(r"(?:nomenclature|description|desc|name)\s*[:=]\s*['\"]?([^'\"\n\r,;{}\[\]]{3,90})", snippet, re.IGNORECASE)
    if explicit:
        value = clean_text(explicit.group(1))
        if value and not value.lower().startswith(("not ", "none", "unknown")):
            return value[:90]

    idx = snippet.upper().find(part.upper())
    if idx >= 0:
        after = snippet[idx + len(part): idx + len(part) + 120]
        # Capture uppercase nomenclature words after the part number.
        m = re.search(r"([A-Z][A-Z0-9 /,_-]{5,80})", after)
        if m:
            value = clean_text(m.group(1).strip(" .,:;-_"))
            # Remove obvious reference suffixes.
            value = re.sub(r"\.{2,}.*$", "", value).strip()
            value = clean_nomenclature_value(value)
            if value and len(value) >= 4 and not re.fullmatch(r"[A-Z0-9-]+", value):
                return value[:90]
    return None


def snippet_around(text: str, start: int, end: int, radius: int = 260) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return clean_text(text[left:right])[:900]


def build_clean_summary_snippet(text: str) -> Optional[str]:
    snippet = clean_text(text[:1800])
    if not snippet:
        return None
    lowered = snippet.lower()
    polluted_markers = (
        '"user_query"',
        '"query_plan"',
        '"category_counts"',
        '"can_answer_directly"',
        'source_bound_response_should',
        'answer_permission',
        'prompt_context',
    )
    if any(m in lowered for m in polluted_markers):
        # These are usually generated plans/prompts, not page summaries useful for a user route card.
        return None
    if len(PAGE_ID_RE.findall(snippet)) > 6:
        # Page-id lists are navigation dumps, not useful human summaries.
        return None
    if snippet.count("{") + snippet.count("[") > 6 and len(snippet) > 250:
        return None
    return snippet[:500]


def classify_match(part: str, clues: QueryClues) -> Tuple[Optional[str], Optional[str], int]:
    norm = normalize_part_token(part)
    if clues.part_prefix:
        prefix = clues.part_prefix.upper()
        if norm.startswith(prefix):
            return "strict_prefix", f"part starts with prefix {clues.part_prefix}", 100
        return None, None, 0
    if clues.contains_digits:
        needle = clues.contains_digits.upper()
        if needle in norm:
            return "contains_digits", f"part contains digits {clues.contains_digits}", 75
        return None, None, 0
    return "broad_candidate", "part-like token found for low-context discovery", 25


def collect_evidence(root: Path, clues: QueryClues, max_files: int = 250000) -> Tuple[List[EvidenceHit], int, int, int]:
    hits: List[EvidenceHit] = []
    evidence_scan_count = 0
    rejected_noise_count = 0
    weak_token_count = 0
    page_summary_by_page: Dict[str, Dict[str, str]] = defaultdict(dict)

    for path in iter_text_files(root, max_files=max_files):
        source_path = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
        text = read_limited_text(path)
        if not text:
            continue
        lower_path = source_path.lower()
        is_v2 = any(h in lower_path for h in V2_HINTS)
        is_v3 = any(h in lower_path for h in V3_HINTS)
        if is_v2 or is_v3:
            page = extract_page_id(text, source_path)
            summary_snippet = build_clean_summary_snippet(text)
            if page and summary_snippet:
                if is_v2 and "v2" not in page_summary_by_page[page]:
                    page_summary_by_page[page]["v2"] = summary_snippet
                if is_v3 and "v3" not in page_summary_by_page[page]:
                    page_summary_by_page[page]["v3"] = summary_snippet

        # Skip prompt/answer-heavy files unless they contain direct page/part evidence. This reduces self-answer contamination.
        meta_penalty = -20 if any(h in lower_path for h in META_PATH_HINTS) else 0

        for m in PART_TOKEN_RE.finditer(text):
            part = m.group(0).strip()
            match_type, reason, base_score = classify_match(part, clues)
            if not match_type:
                continue
            snip = snippet_around(text, m.start(), m.end())
            if clues.description_terms:
                matched=[term for term in clues.description_terms if term in snip.lower()]
                if not matched: continue
                match_type="broad_candidate";reason="source-near description match: "+", ".join(matched);base_score=80
            candidate_quality, quality_reason = classify_candidate_quality(part, snip, source_path)
            if candidate_quality == "rejected_noise":
                rejected_noise_count += 1
                continue
            if candidate_quality != "valid_part_like":
                weak_token_count += 1
                continue
            evidence_scan_count += 1
            # Penalize snippets that are clearly prior generated answers rather than source-like evidence.
            if "direct answer:" in snip.lower() or "answer_text" in snip.lower():
                meta_penalty -= 15
            page = extract_page_id(snip, source_path)
            ata = extract_ata(snip, source_path)
            doc = extract_document(snip, source_path)
            nomenclature = extract_nomenclature_near_part(snip, part)
            etypes = detect_evidence_types(source_path, snip)
            score = base_score + meta_penalty
            if page:
                score += 12
            if ata:
                score += 8
            if doc:
                score += 6
            if nomenclature:
                score += 15
            if "table" in etypes:
                score += 8
            if "OCR" in etypes:
                score += 8
            if "visual" in etypes:
                score += 5
            hits.append(
                EvidenceHit(
                    part_number=part,
                    match_type=match_type,
                    match_reason=reason,
                    page_id=page,
                    document=doc,
                    ata=ata,
                    nomenclature=nomenclature,
                    evidence_types=etypes,
                    source_path=source_path,
                    snippet=snip,
                    candidate_quality=candidate_quality,
                    quality_reason=quality_reason,
                    score=score,
                )
            )

    # Attach page summaries after initial scan.
    for h in hits:
        if h.page_id and h.page_id in page_summary_by_page:
            h.v2_summary = page_summary_by_page[h.page_id].get("v2")
            h.v3_summary = page_summary_by_page[h.page_id].get("v3")
    return hits, evidence_scan_count, rejected_noise_count, weak_token_count


def merge_candidate_routes(hits: Sequence[EvidenceHit], top_k: int = 8, loose_top_k: int = 8) -> List[CandidateRoute]:
    grouped: Dict[str, List[EvidenceHit]] = defaultdict(list)
    for h in hits:
        key = normalize_part_token(h.part_number)
        grouped[key].append(h)

    routes: List[CandidateRoute] = []
    for _, group in grouped.items():
        best = sorted(group, key=lambda h: h.score, reverse=True)[0]
        all_pages = [h.page_id for h in group if h.page_id]
        page_id = Counter(all_pages).most_common(1)[0][0] if all_pages else "unknown"
        all_atas = [h.ata for h in group if h.ata]
        ata = Counter(all_atas).most_common(1)[0][0] if all_atas else "unknown"
        all_docs = [h.document for h in group if h.document]
        doc = Counter(all_docs).most_common(1)[0][0] if all_docs else "unknown"
        all_nom = [h.nomenclature for h in group if h.nomenclature]
        nom = Counter(all_nom).most_common(1)[0][0] if all_nom else "unknown"
        etypes = sorted(set(t for h in group for t in h.evidence_types))
        v2 = next((h.v2_summary for h in group if h.v2_summary), None) or "not found in selected evidence"
        v3 = next((h.v3_summary for h in group if h.v3_summary), None) or "not found in selected evidence"
        # Confidence is intentionally conservative.
        if best.match_type == "strict_prefix" and best.score >= 120:
            conf = "high"
        elif best.match_type == "strict_prefix":
            conf = "medium"
        elif best.match_type in {"loose_contains", "contains_digits"} and best.score >= 65:
            conf = "medium"
        else:
            conf = "low"
        examples = []
        for h in sorted(group, key=lambda x: x.score, reverse=True)[:3]:
            examples.append(h.source_path)
        routes.append(
            CandidateRoute(
                route_id="pending",
                route_group=best.match_type,
                candidate_part_number=best.part_number,
                ata=ata,
                nomenclature=nom,
                page_id=page_id,
                document=doc,
                evidence_types=etypes,
                v2_summary=v2[:500],
                v3_summary=v3[:500],
                confidence=conf,
                why_matched=best.match_reason,
                candidate_quality=best.candidate_quality,
                quality_reason=best.quality_reason,
                evidence_count=len(group),
                source_examples=examples,
            )
        )

    order = {"strict_prefix": 0, "contains_digits": 1, "loose_contains": 2, "weak_digit_overlap": 3, "broad_candidate": 4}
    routes.sort(key=lambda r: (order.get(r.route_group, 9), {"high": 0, "medium": 1, "low": 2}.get(r.confidence, 9), -r.evidence_count, r.candidate_part_number))

    strict = [r for r in routes if r.route_group == "strict_prefix"][:top_k]
    contains = [r for r in routes if r.route_group == "contains_digits"][:top_k]
    loose = [r for r in routes if r.route_group in {"loose_contains", "weak_digit_overlap", "broad_candidate"}][:loose_top_k]
    selected = strict + contains + loose
    for i, r in enumerate(selected, 1):
        r.route_id = f"route_{i}"
    return selected


def build_result(question: str, routes: Sequence[CandidateRoute], clues: QueryClues, evidence_count: int, rejected_noise_count: int = 0, weak_token_count: int = 0) -> Dict[str, Any]:
    strict_count = sum(1 for r in routes if r.route_group == "strict_prefix")
    loose_count = sum(1 for r in routes if r.route_group in {"loose_contains", "weak_digit_overlap"})
    contains_count = sum(1 for r in routes if r.route_group == "contains_digits")
    return {
        "question_id": "q01",
        "question": question,
        "intent": clues.intent,
        "known_clues": {
            "part_prefix": clues.part_prefix,
            "contains_digits": clues.contains_digits,
            "raw_digits": clues.raw_digits,
            "strict_prefix_requested": clues.strict_prefix_requested,
            "description_terms": clues.description_terms,
        },
        "ranking_policy": "exact clue satisfaction, candidate quality, source-trace completeness, evidence count",
        "result_coverage_note": "top representative candidates only; drill down for more",
        "missing_clues": clues.missing_clues,
        "clarifying_questions": clues.clarifying_questions,
        "candidate_routes": [asdict(r) for r in routes],
        "strict_prefix_candidate_count": strict_count,
        "contains_candidate_count": contains_count,
        "loose_candidate_count": loose_count,
        "total_candidate_route_count": len(routes),
        "evidence_record_count": evidence_count,
        "rejected_noise_token_count": rejected_noise_count,
        "weak_token_count": weak_token_count,
        "source_trace_status": "candidate-discovery-only",
        "final_answer_allowed": False,
        "safety_contract": {
            "read_only": True,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "answer_permission_count": 0,
        },
    }


def render_view(results: Sequence[Dict[str, Any]]) -> str:
    chunks: List[str] = []
    for result in results:
        qid = result.get("question_id", "q01")
        question = result.get("question", "")
        clues = result.get("known_clues", {})
        routes = result.get("candidate_routes", [])
        strict_routes = [r for r in routes if r.get("route_group") == "strict_prefix"]
        contains_routes = [r for r in routes if r.get("route_group") == "contains_digits"]
        loose_routes = [r for r in routes if r.get("route_group") in {"loose_contains", "weak_digit_overlap", "broad_candidate"}]
        chunks.append("-" * 100)
        chunks.append(f"Question {qid}:")
        chunks.append(question)
        chunks.append("")
        chunks.append("I found possible candidate routes, not a final part identification yet.")
        chunks.append("Source-trace status: candidate-discovery-only")
        chunks.append("Final answer allowed: false")
        chunks.append("")
        chunks.append("Known clues:")
        prefix = clues.get("part_prefix")
        contains = clues.get("contains_digits")
        if prefix:
            chunks.append(f"- Requested part prefix: {prefix}")
            chunks.append("- Strict interpretation: only candidates that start with this prefix count as primary matches.")
        elif contains:
            chunks.append(f"- Requested contained digits: {contains}")
        else:
            chunks.append("- Low-context part lookup with no exact part number.")
        chunks.append("")
        chunks.append("Helpful details to narrow this:")
        for i, cq in enumerate(result.get("clarifying_questions", []), 1):
            chunks.append(f"{i}. {cq}")
        chunks.append("")

        if prefix:
            chunks.append(f"Strict prefix matches for {prefix}:")
            if not strict_routes:
                chunks.append(f"No source-traceable selected candidates starting exactly with {prefix} were found.")
            else:
                chunks.extend(render_routes(strict_routes))
            chunks.append("")
            if loose_routes:
                chunks.append("Weaker related candidates:")
                chunks.append(f"These do not start with {prefix}; they only contain or overlap the clue and should not be treated as exact matches.")
                chunks.extend(render_routes(loose_routes))
        elif contains:
            chunks.append(f"Candidates containing {contains}:")
            if contains_routes:
                chunks.extend(render_routes(contains_routes))
            elif loose_routes:
                chunks.extend(render_routes(loose_routes))
            else:
                chunks.append("No selected candidates found for the contained-digit clue.")
        else:
            chunks.append("Candidate routes found:")
            chunks.extend(render_routes(routes))

        chunks.append("")
        chunks.append("Safety note: candidate routes are discovery hints only and do not prove eligibility, fit, approval, interchangeability, installation approval, or effectivity.")
    return "\n".join(chunks).strip() + "\n"


def render_routes(routes: Sequence[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    for r in routes:
        lines.append("")
        lines.append(str(r.get("route_id", "route")))
        lines.append(f"Match group: {r.get('route_group', 'unknown')}")
        lines.append(f"ATA: {r.get('ata') or 'unknown'}")
        lines.append(f"Candidate part number: {r.get('candidate_part_number') or 'unknown'}")
        lines.append(f"Nomenclature: {r.get('nomenclature') or 'unknown'}")
        lines.append(f"Page: {r.get('page_id') or 'unknown'}")
        doc = r.get("document") or "unknown"
        if doc != "unknown":
            lines.append(f"Document: {doc}")
        lines.append(f"Evidence type: {', '.join(r.get('evidence_types') or ['artifact'])}")
        lines.append(f"V2 summary: {r.get('v2_summary') or 'not found in selected evidence'}")
        lines.append(f"V3 summary: {r.get('v3_summary') or 'not found in selected evidence'}")
        lines.append(f"Confidence: {r.get('confidence') or 'low'}")
        lines.append(f"Candidate quality: {r.get('candidate_quality') or 'valid_part_like'}")
        lines.append(f"Why it matched: {r.get('why_matched') or 'matched local TRACE-Net artifact evidence for weak query clues'}")
        lines.append(f"Evidence count for this candidate: {r.get('evidence_count', 0)}")
    return lines


def load_questions(args: argparse.Namespace) -> List[Tuple[str, str]]:
    if args.question:
        return [("q01", args.question)]
    if args.questions:
        p = Path(args.questions)
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            items = data
        else:
            items = data.get("questions", [])
        questions: List[Tuple[str, str]] = []
        for i, item in enumerate(items, 1):
            if isinstance(item, str):
                questions.append((f"q{i:02d}", item))
            else:
                questions.append((str(item.get("question_id") or f"q{i:02d}"), str(item.get("question") or "")))
        return [(qid, q) for qid, q in questions if q.strip()]
    return [("q01", "I am looking for a part that starts with numbers 2 and 4 but I do not have the rest")]


def write_jsonl(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TRACE-Net guided candidate discovery v4")
    parser.add_argument("--artifact-root", required=True, help="TRACE-Net local artifact root")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--question", help="Single low-context discovery question")
    parser.add_argument("--questions", help="Optional JSON questions file")
    parser.add_argument("--top-k", type=int, default=8, help="Max strict/primary candidates")
    parser.add_argument("--loose-top-k", type=int, default=8, help="Max loose related candidates")
    parser.add_argument("--max-files", type=int, default=250000, help="Max text artifacts to scan")
    # Kept for CLI continuity with v1. v4 source-of-truth output is deterministic JSON/view.
    parser.add_argument("--use-ollama", action="store_true", help="Accepted for compatibility; deterministic output remains source of truth")
    parser.add_argument("--ollama-host", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="gemma4:26b")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    start = time.time()
    args = build_arg_parser().parse_args(argv)
    artifact_root = Path(args.artifact_root)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if not artifact_root.exists():
        raise SystemExit(f"Artifact root does not exist: {artifact_root}")

    results: List[Dict[str, Any]] = []
    questions = load_questions(args)
    for idx, (qid, question) in enumerate(questions, 1):
        print(f"[{idx:03d}/{len(questions):03d}] DISCOVERY {qid}: {question}", flush=True)
        clues = parse_query_clues(question)
        hits, evidence_count, rejected_noise_count, weak_token_count = collect_evidence(artifact_root, clues, max_files=args.max_files)
        routes = merge_candidate_routes(hits, top_k=args.top_k, loose_top_k=args.loose_top_k)
        result = build_result(question, routes, clues, evidence_count, rejected_noise_count, weak_token_count)
        result["question_id"] = qid
        results.append(result)
        strict_count = result["strict_prefix_candidate_count"]
        loose_count = result["loose_candidate_count"]
        print(
            f"[{idx:03d}/{len(questions):03d}] ROUTES {qid}: "
            f"strict={strict_count}, loose={loose_count}, total={len(routes)}, evidence={evidence_count}, rejected_noise={rejected_noise_count}, weak_tokens={weak_token_count}",
            flush=True,
        )

    results_path = output_dir / "candidate_discovery_results.jsonl"
    view_path = output_dir / "candidate_discovery_view.txt"
    summary_path = output_dir / "summary.json"
    write_jsonl(results_path, results)
    view_path.write_text(render_view(results), encoding="utf-8")

    total_routes = sum(r.get("total_candidate_route_count", 0) for r in results)
    strict_total = sum(r.get("strict_prefix_candidate_count", 0) for r in results)
    loose_total = sum(r.get("loose_candidate_count", 0) for r in results)
    no_route = sum(1 for r in results if not r.get("candidate_routes"))
    rejected_total = sum(r.get("rejected_noise_token_count", 0) for r in results)
    weak_total = sum(r.get("weak_token_count", 0) for r in results)
    summary = {
        "status": "TRACE_NET_GUIDED_CANDIDATE_DISCOVERY_V4_DONE",
        "quality_status": "PASS" if len(results) == len(questions) else "FAIL",
        "question_count": len(questions),
        "candidate_route_question_count": sum(1 for r in results if r.get("candidate_routes")),
        "no_candidate_route_question_count": no_route,
        "total_candidate_route_count": total_routes,
        "strict_prefix_candidate_count": strict_total,
        "loose_candidate_count": loose_total,
        "rejected_noise_token_count": rejected_total,
        "weak_token_count": weak_total,
        "results": str(results_path),
        "view": str(view_path),
        "final_answer_allowed_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "elapsed_seconds": round(time.time() - start, 2),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"status={summary['status']}")
    print(f"quality_status={summary['quality_status']}")
    print(f"question_count={summary['question_count']}")
    print(f"strict_prefix_candidate_count={summary['strict_prefix_candidate_count']}")
    print(f"loose_candidate_count={summary['loose_candidate_count']}")
    print(f"rejected_noise_token_count={summary['rejected_noise_token_count']}")
    print(f"weak_token_count={summary['weak_token_count']}")
    print(f"total_candidate_route_count={summary['total_candidate_route_count']}")
    print(f"view={view_path}")
    return 0 if summary["quality_status"] == "PASS" else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
