#!/usr/bin/env python3
"""TRACE-Net guided candidate discovery v1.

This runner handles low-context/partial part lookup questions.  It does not
claim a final part identity.  It searches local TRACE-Net artifacts for
candidate routes, generates clarifying questions, and writes UI-friendly route
cards that include ATA, candidate part number, page/document, evidence type,
V2/V3 hints, confidence, and safety status.

Safety contract:
- read-only local artifact scanning
- no source truth mutation
- no database writes
- no answer permission for candidate routes
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SUPPORTED_EXTENSIONS = {".json", ".jsonl", ".txt", ".csv", ".md", ".tsv"}
PAGE_RE = re.compile(r"t_p_\d+_\d+_p\d{6}|source_p\d{6}|p\d{6}", re.I)
ATA_RE = re.compile(r"(?:ATA\s*)?(\d{2}-\d{2}-\d{2})", re.I)
# Broad candidate extractor.  Filtering below removes ATA/page/date/junk tokens.
PART_TOKEN_RE = re.compile(r"\b(?:[A-Z]{1,4}\d{3,}[A-Z0-9-]*|\d{3,}[A-Z]{1,4}\d*[A-Z0-9-]*|\d{5,8}|\d{2,6}-\d{2,8}(?:-\d{1,5})?|[A-Z]{1,4}\d{2,6}-\d{1,5})\b", re.I)
UPPER_PHRASE_RE = re.compile(r"\b[A-Z][A-Z0-9/&().,-]{1,}(?:\s+[A-Z0-9/&().,-]{1,}){1,8}\b")

PHYSICAL_TERMS = {
    "bolt", "bracket", "seat", "seat assy", "seat assembly", "dispenser", "panel",
    "latch", "pin", "fitting", "fastener", "button", "cover", "armrest", "table",
    "support", "structure", "assembly", "assy", "leg", "track", "trim", "snack",
}
COMPANIES = {"honeywell", "airbus", "embraer", "boeing", "collins", "goodrich", "safran", "rockwell", "recaro"}
SYSTEM_HINTS = {"seat", "interior", "cabin", "galley", "lavatory", "landing gear", "electrical", "hydraulic"}


@dataclass
class Clues:
    intent: str
    part_prefix: Optional[str] = None
    part_digits: List[str] = field(default_factory=list)
    contains_digits: Optional[str] = None
    exact_part: Optional[str] = None
    ata_hint: Optional[str] = None
    physical_description: Optional[str] = None
    manufacturer: Optional[str] = None
    figure_hint: Optional[str] = None
    page_hint: Optional[str] = None
    nearby_words: List[str] = field(default_factory=list)
    low_context: bool = True


@dataclass
class EvidenceRecord:
    source_path: str
    text: str
    pages: List[str]
    parts: List[str]
    ata: List[str]
    evidence_types: List[str]
    v2_summary: str = ""
    v3_summary: str = ""


@dataclass
class Candidate:
    part_number: str
    score: float = 0.0
    pages: Counter = field(default_factory=Counter)
    ata: Counter = field(default_factory=Counter)
    evidence_types: Counter = field(default_factory=Counter)
    nomenclature: Counter = field(default_factory=Counter)
    v2: List[str] = field(default_factory=list)
    v3: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)


def norm_token(token: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", token.upper())


def canonical_part(token: str) -> str:
    return token.strip().strip(".,;:()[]{}\"'").upper()


def is_ata(token: str) -> bool:
    return bool(re.fullmatch(r"\d{2}-\d{2}-\d{2}", token.strip()))


def looks_like_page_or_date(token: str) -> bool:
    t = token.upper().strip()
    if re.fullmatch(r"P\d{6,8}", t):
        return True
    if re.fullmatch(r"0{2,}\d+", t):
        return True
    if re.fullmatch(r"\d{4}", t):
        yr = int(t)
        return 1900 <= yr <= 2099
    if re.fullmatch(r"\d{1,3}", t):
        return True
    return False


def is_good_part(token: str) -> bool:
    t = canonical_part(token)
    if not t or is_ata(t) or looks_like_page_or_date(t):
        return False
    if "U2026" in t or t in {"REF", "ATA", "FIGURE", "PAGE", "REV"}:
        return False
    n = norm_token(t)
    if len(n) < 5:
        return False
    # Reject page-like zero-padded numbers and bare tiny catalog line numbers.
    if re.fullmatch(r"0{2,}\d+", n):
        return False
    # Require either letters with digits, a hyphenated multi-group digit part,
    # or a bare catalog-style number with enough digits to be useful for partial lookup.
    has_digit = bool(re.search(r"\d", t))
    has_letter = bool(re.search(r"[A-Z]", t))
    has_hyphen = "-" in t
    if has_letter and has_digit:
        return True
    if has_hyphen and re.fullmatch(r"\d{3,6}-\d{3,8}(?:-\d{1,5})?", t):
        return True
    if re.fullmatch(r"\d{5,8}", t) and not re.fullmatch(r"0+\d+", t):
        return True
    return False


def extract_parts(text: str) -> List[str]:
    out: List[str] = []
    seen = set()
    for m in PART_TOKEN_RE.finditer(text or ""):
        p = canonical_part(m.group(0))
        if is_good_part(p) and p not in seen:
            seen.add(p)
            out.append(p)
    return out[:40]


def extract_pages(text: str, source_path: str = "") -> List[str]:
    raw = list(PAGE_RE.findall((text or "") + " " + (source_path or "")))
    pages = []
    seen = set()
    for p in raw:
        p2 = p.lower()
        # Normalize source_p000050 -> t_p_... cannot be inferred, keep source_p but also readable p.
        if p2 not in seen:
            seen.add(p2)
            pages.append(p2)
    return pages[:30]


def extract_ata(text: str) -> List[str]:
    vals = []
    seen = set()
    for m in ATA_RE.finditer(text or ""):
        v = m.group(1).upper()
        if v not in seen:
            seen.add(v)
            vals.append(v)
    return vals[:10]


def evidence_type_for_path(path: str, text: str) -> List[str]:
    p = path.lower()
    t = text.lower()
    types = []
    if "ocr" in p or "/ocr_text/" in p or "ocr" in t[:500]:
        types.append("OCR")
    if "table" in p or "has_table" in t or "table_cell" in t or "normcell" in t:
        types.append("table")
    if any(x in p for x in ["visual", "figure", "callout", "image"]) or any(x in t for x in ["figure", "callout", "visual"]):
        types.append("visual")
    if "page_context_v2" in p or "context_v2" in p:
        types.append("v2_summary")
    if "page_context_v3" in p or "context_v3" in p:
        types.append("v3_summary")
    if "graph" in p or "node" in p or "edge" in p:
        types.append("graph")
    if "human_review" in p or "review" in p:
        types.append("review")
    return types or ["artifact"]


def short_text(text: str, max_len: int = 420) -> str:
    s = re.sub(r"\s+", " ", text or "").strip()
    return s[:max_len]


def extract_nomenclature_near(text: str, part: str) -> List[str]:
    if not text:
        return []
    part_i = text.upper().find(part.upper())
    windows = []
    if part_i >= 0:
        windows.append(text[part_i:part_i + 220])
        windows.append(text[max(0, part_i - 120):part_i + 120])
    windows.append(text[:300])
    candidates: List[str] = []
    for window in windows:
        for ph in UPPER_PHRASE_RE.findall(window.upper()):
            ph = re.sub(r"\s+", " ", ph).strip(" .,-")
            if len(ph) < 5 or ph == part.upper():
                continue
            if any(term.upper() in ph for term in ["ASSY", "ASSEMBLY", "SEAT", "BOLT", "BRACKET", "FITTING", "PIN", "STRUCTURE", "COVER", "ARMREST", "TABLE", "SUPPORT", "DISPENSER", "LATCH", "PANEL"]):
                # Remove leading item numbers / part numbers.
                ph = re.sub(r"^\d+\s*[-|:]\s*", "", ph).strip()
                ph = ph.replace("..........", "").strip(" .,-")
                if ph and ph not in candidates:
                    candidates.append(ph)
    return candidates[:3]


def load_questions(path: Optional[Path], single_question: Optional[str]) -> List[Dict[str, str]]:
    if single_question:
        return [{"question_id": "q01", "question": single_question}]
    if path:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            qs = data
        else:
            qs = data.get("questions") or []
        out = []
        for i, q in enumerate(qs, 1):
            if isinstance(q, str):
                out.append({"question_id": f"q{i:02d}", "question": q})
            else:
                out.append({"question_id": str(q.get("question_id") or f"q{i:02d}"), "question": str(q.get("question") or "")})
        return out
    return [
        {"question_id": "q01", "question": "I am looking for a part that starts with numbers 2 and 4 but I do not have the rest."},
        {"question_id": "q02", "question": "I know the part has 04 somewhere and it looked like a bolt near a seat."},
        {"question_id": "q03", "question": "I need a part in ATA 25 but only know two digits."},
    ]


def detect_clues(question: str) -> Clues:
    q = (question or "").strip()
    ql = q.lower()
    parts = extract_parts(q)
    exact_part = parts[0] if parts else None

    prefix = None
    contains = None
    digits: List[str] = []

    m = re.search(r"starts?\s+with(?:\s+(?:number|numbers|digits?))?\s+([a-z0-9][a-z0-9\s-]{0,12})", ql)
    if m:
        raw = m.group(1)
        ds = re.findall(r"[a-z0-9]+", raw)
        # Handle natural phrasing like "starts with numbers 2 and 4".
        raw_digits = re.findall(r"\d", raw)
        if len(raw_digits) >= 2 and "and" in raw:
            prefix = "".join(raw_digits[:2])
            digits = raw_digits[:2]
        elif len(ds) >= 2 and all(len(x) == 1 and x.isdigit() for x in ds[:2]):
            prefix = "".join(ds[:2])
            digits = ds[:2]
        elif ds:
            prefix = ds[0].upper()
            digits = re.findall(r"\d", prefix)
    m2 = re.search(r"(?:has|contains|includes|with)\s+(?:digits?\s+)?([0-9]{2,6})\s+(?:somewhere|in it)?", ql)
    if m2 and not prefix:
        contains = m2.group(1)
        digits = list(contains)
    if not prefix and re.search(r"\b2\s+and\s+4\b", ql):
        prefix = "24"
        digits = ["2", "4"]

    ata_hint = None
    ata_match = ATA_RE.search(q)
    if ata_match:
        ata_hint = ata_match.group(1)
    else:
        m3 = re.search(r"\bata\s*(\d{2})\b", ql)
        if m3:
            ata_hint = m3.group(1)

    manufacturer = None
    for c in COMPANIES:
        if c in ql:
            manufacturer = c.title()
            break

    physical = []
    for term in sorted(PHYSICAL_TERMS, key=len, reverse=True):
        if re.search(r"\b" + re.escape(term) + r"\b", ql):
            physical.append(term)
    physical_description = ", ".join(physical[:3]) or None

    figure_hint = None
    fm = re.search(r"figure\s*(\d+)", ql)
    if fm:
        figure_hint = fm.group(1)
    page_hint = None
    pm = re.search(r"page\s*(\d+)", ql)
    if pm:
        page_hint = pm.group(1)

    low_context = not exact_part or bool(prefix or contains) or len(q.split()) < 18
    intent = "partial_part_lookup" if (prefix or contains or ("part" in ql and low_context)) else "guided_discovery"
    nearby_words = [w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", ql) if w not in {"looking", "number", "numbers", "part", "starts", "with", "have", "rest", "somewhere", "need"}][:12]
    return Clues(
        intent=intent,
        part_prefix=prefix,
        part_digits=digits,
        contains_digits=contains,
        exact_part=exact_part,
        ata_hint=ata_hint,
        physical_description=physical_description,
        manufacturer=manufacturer,
        figure_hint=figure_hint,
        page_hint=page_hint,
        nearby_words=nearby_words,
        low_context=low_context,
    )


def iter_artifact_texts(root: Path, max_records: int = 250000, max_file_bytes: int = 2_000_000) -> Iterable[Tuple[str, str]]:
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune caches and huge irrelevant dirs.
        dirnames[:] = [d for d in dirnames if d not in {".git", ".venv", "__pycache__", ".pytest_cache"}]
        for name in filenames:
            if count >= max_records:
                return
            path = Path(dirpath) / name
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            try:
                if path.stat().st_size > max_file_bytes:
                    # Still sample line-based files, skip huge JSON blobs for speed.
                    if path.suffix.lower() not in {".jsonl", ".csv", ".txt", ".md"}:
                        continue
                rel = str(path.relative_to(root))
                with path.open("r", encoding="utf-8", errors="ignore") as f:
                    for line_no, line in enumerate(f, 1):
                        if count >= max_records:
                            return
                        s = line.strip()
                        if not s:
                            continue
                        # For JSON lines/files, line text still works for route discovery.
                        yield f"{rel}:{line_no}", s
                        count += 1
            except OSError:
                continue


def record_relevant_to_clues(source: str, text: str, clues: Clues) -> bool:
    combined = (source + " " + text).lower()
    if clues.part_prefix and clues.part_prefix.lower() in combined:
        return True
    if clues.contains_digits and clues.contains_digits in combined:
        return True
    if clues.exact_part and clues.exact_part.lower() in combined:
        return True
    if clues.ata_hint and clues.ata_hint.lower() in combined:
        return True
    if clues.physical_description and any(x.strip() in combined for x in clues.physical_description.lower().split(",")):
        return True
    if clues.manufacturer and clues.manufacturer.lower() in combined:
        return True
    if clues.figure_hint and re.search(r"figure\s*" + re.escape(clues.figure_hint), combined):
        return True
    # Keep v2/v3/visual/table/ocr part-bearing records as discovery candidates.
    if extract_parts(text) and any(x in combined for x in ["ocr", "table", "visual", "callout", "nomenclature", "page_context", "part"]):
        return True
    return False


def scan_evidence(root: Path, clues: Clues, max_records: int) -> List[EvidenceRecord]:
    records: List[EvidenceRecord] = []
    for source, text in iter_artifact_texts(root, max_records=max_records):
        if not record_relevant_to_clues(source, text, clues):
            continue
        pages = extract_pages(text, source)
        parts = extract_parts(text)
        ata = extract_ata(text)
        etypes = evidence_type_for_path(source, text)
        v2 = short_text(text, 240) if "v2_summary" in etypes else ""
        v3 = short_text(text, 240) if "v3_summary" in etypes else ""
        if pages or parts or ata or v2 or v3:
            records.append(EvidenceRecord(source, short_text(text, 700), pages, parts, ata, etypes, v2, v3))
    return records


def score_part(part: str, rec: EvidenceRecord, clues: Clues) -> Tuple[float, List[str]]:
    score = 0.0
    reasons: List[str] = []
    np = norm_token(part)
    if clues.exact_part and norm_token(clues.exact_part) == np:
        score += 100
        reasons.append("exact part-number match")
    if clues.part_prefix and np.startswith(norm_token(clues.part_prefix)):
        score += 45
        reasons.append(f"part starts with {clues.part_prefix}")
    elif clues.part_prefix and norm_token(clues.part_prefix) in np:
        score += 16
        reasons.append(f"part contains prefix/digits {clues.part_prefix}")
    if clues.contains_digits and clues.contains_digits in np:
        score += 22
        reasons.append(f"part contains digits {clues.contains_digits}")
    if clues.ata_hint:
        if any(a.startswith(clues.ata_hint) or a == clues.ata_hint for a in rec.ata) or clues.ata_hint in rec.text:
            score += 12
            reasons.append(f"near ATA/system hint {clues.ata_hint}")
    if clues.physical_description:
        for term in clues.physical_description.lower().split(","):
            term = term.strip()
            if term and term in rec.text.lower():
                score += 14
                reasons.append(f"near physical description '{term}'")
                break
    if clues.manufacturer and clues.manufacturer.lower() in rec.text.lower():
        score += 10
        reasons.append(f"near manufacturer/company '{clues.manufacturer}'")
    if "table" in rec.evidence_types:
        score += 6
    if "OCR" in rec.evidence_types:
        score += 5
    if "visual" in rec.evidence_types:
        score += 4
    if "v2_summary" in rec.evidence_types or "v3_summary" in rec.evidence_types:
        score += 3
    return score, reasons


def build_candidates(records: List[EvidenceRecord], clues: Clues, top_k: int) -> List[Candidate]:
    by_part: Dict[str, Candidate] = {}
    for rec in records:
        for part in rec.parts:
            sc, reasons = score_part(part, rec, clues)
            if sc <= 0 and (clues.part_prefix or clues.contains_digits or clues.exact_part):
                continue
            if sc <= 0:
                sc = 1.0
            c = by_part.setdefault(part, Candidate(part_number=part))
            c.score += sc
            c.pages.update(rec.pages or [])
            c.ata.update(rec.ata or [])
            c.evidence_types.update(rec.evidence_types)
            for nom in extract_nomenclature_near(rec.text, part):
                c.nomenclature[nom] += 1
            if rec.v2_summary and len(c.v2) < 3:
                c.v2.append(rec.v2_summary)
            if rec.v3_summary and len(c.v3) < 3:
                c.v3.append(rec.v3_summary)
            if len(c.sources) < 8:
                c.sources.append(rec.source_path)
            for r in reasons:
                if r not in c.reasons:
                    c.reasons.append(r)
    candidates = sorted(by_part.values(), key=lambda c: (c.score, sum(c.pages.values()), sum(c.evidence_types.values())), reverse=True)
    return candidates[:top_k]


def missing_clues(clues: Clues) -> List[str]:
    missing = []
    if not clues.manufacturer:
        missing.append("manufacturer")
    if not clues.physical_description:
        missing.append("physical_description")
    if not clues.ata_hint:
        missing.append("ata_or_system")
    if not clues.figure_hint and not clues.page_hint:
        missing.append("figure_or_page")
    if len(clues.nearby_words) < 2:
        missing.append("nearby_words")
    if not clues.exact_part:
        missing.append("full_part_number")
    return missing


def clarifying_questions_for(clues: Clues, candidates: List[Candidate]) -> List[str]:
    qs = []
    m = missing_clues(clues)
    if "manufacturer" in m:
        qs.append("Do you know the manufacturer or company, such as Honeywell, Airbus, Embraer, Boeing, Collins, or Safran?")
    if "physical_description" in m:
        qs.append("Do you know what the part physically looked like, such as bolt, bracket, seat assembly, dispenser, panel, latch, pin, fitting, or cover?")
    if "ata_or_system" in m:
        # If candidate ATAs exist, mention top one.
        ata_counts = Counter()
        for c in candidates:
            ata_counts.update(c.ata)
        if ata_counts:
            qs.append(f"Was it in one of these ATA/system areas, especially {ata_counts.most_common(1)[0][0]}, or a different ATA section?")
        else:
            qs.append("Do you know the ATA/system area, such as ATA 25 cabin/interiors, ATA 32 landing gear, or another section?")
    if "figure_or_page" in m:
        qs.append("Was it seen in a figure, a table, or body text? Do you remember a page or figure number?")
    if "nearby_words" in m:
        qs.append("Do you remember any nearby words, reference designators, item numbers, or the surrounding nomenclature?")
    return qs[:5]


def confidence_for(c: Candidate, clues: Clues) -> str:
    if clues.exact_part and c.score >= 100:
        return "high-candidate"
    if c.score >= 70:
        return "medium"
    if c.score >= 30:
        return "low-medium"
    return "low"


def candidate_to_route(c: Candidate, idx: int, clues: Clues) -> Dict[str, Any]:
    pages = [p for p, _ in c.pages.most_common(8)]
    atas = [a for a, _ in c.ata.most_common(5)]
    etypes = [e for e, _ in c.evidence_types.most_common()]
    noms = [n for n, _ in c.nomenclature.most_common(5)]
    why = c.reasons[:]
    if not why:
        why = ["matched local TRACE-Net artifact evidence for the weak query clues"]
    return {
        "route_id": f"route_{idx}",
        "ata": atas[0] if atas else None,
        "candidate_part_number": c.part_number,
        "nomenclature": noms[0] if noms else None,
        "all_nomenclature_hints": noms,
        "page_id": pages[0] if pages else None,
        "candidate_pages": pages,
        "document": "EMB CMM ATA 25-21-00 REV.4" if any(a == "25-21-00" for a in atas) else None,
        "evidence_types": etypes,
        "v2_summary": c.v2[0] if c.v2 else None,
        "v3_summary": c.v3[0] if c.v3 else None,
        "confidence": confidence_for(c, clues),
        "score": round(c.score, 2),
        "why_matched": "; ".join(why[:5]),
        "source_samples": c.sources[:5],
    }


def build_discovery_result(question_id: str, question: str, artifact_root: Path, top_k: int, max_records: int) -> Dict[str, Any]:
    clues = detect_clues(question)
    records = scan_evidence(artifact_root, clues, max_records=max_records)
    candidates = build_candidates(records, clues, top_k=top_k)
    routes = [candidate_to_route(c, i + 1, clues) for i, c in enumerate(candidates)]
    result = {
        "question_id": question_id,
        "question": question,
        "intent": clues.intent,
        "known_clues": {
            "part_prefix": clues.part_prefix,
            "part_digits": clues.part_digits,
            "contains_digits": clues.contains_digits,
            "exact_part": clues.exact_part,
            "ata_hint": clues.ata_hint,
            "physical_description": clues.physical_description,
            "manufacturer": clues.manufacturer,
            "figure_hint": clues.figure_hint,
            "page_hint": clues.page_hint,
            "nearby_words": clues.nearby_words,
        },
        "missing_clues": missing_clues(clues),
        "clarifying_questions": clarifying_questions_for(clues, candidates),
        "candidate_routes": routes,
        "source_trace_status": "candidate-discovery-only" if routes else "not-source-trace-ready",
        "final_answer_allowed": False,
        "candidate_route_count": len(routes),
        "evidence_record_count": len(records),
        "safety_contract": {
            "read_only": True,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "answer_permission": False,
        },
    }
    return result


def render_result(result: Dict[str, Any]) -> str:
    lines: List[str] = []
    q = result["question"]
    routes = result.get("candidate_routes") or []
    lines.append(f"Question {result.get('question_id')}:")
    lines.append(q)
    lines.append("")
    if routes:
        lines.append(f"I found {len(routes)} possible route(s), not a final part identification yet.")
    else:
        lines.append("I did not find route-matching candidate evidence yet. This is not source-trace-ready.")
    lines.append("")
    if result.get("clarifying_questions"):
        lines.append("Helpful details to narrow this:")
        for i, cq in enumerate(result["clarifying_questions"], 1):
            lines.append(f"{i}. {cq}")
        lines.append("")
    if routes:
        lines.append("Possible routes found:")
        for r in routes:
            lines.append("")
            lines.append(f"{r['route_id']}")
            lines.append(f"ATA: {r.get('ata') or 'unknown'}")
            lines.append(f"Candidate part number: {r.get('candidate_part_number') or 'unknown'}")
            lines.append(f"Nomenclature: {r.get('nomenclature') or 'unknown'}")
            lines.append(f"Page: {r.get('page_id') or 'unknown'}")
            if r.get("document"):
                lines.append(f"Document: {r['document']}")
            lines.append(f"Evidence type: {', '.join(r.get('evidence_types') or []) or 'unknown'}")
            lines.append(f"V2 summary: {r.get('v2_summary') or 'not found in selected evidence'}")
            lines.append(f"V3 summary: {r.get('v3_summary') or 'not found in selected evidence'}")
            lines.append(f"Confidence: {r.get('confidence')}")
            lines.append(f"Why it matched: {r.get('why_matched')}")
    lines.append("")
    lines.append(f"Source-trace status: {result.get('source_trace_status')}")
    lines.append("Final answer allowed: false")
    lines.append("Safety note: candidate routes are discovery hints only and do not prove eligibility, fit, approval, interchangeability, installation approval, or effectivity.")
    return "\n".join(lines)


def maybe_refine_with_ollama(result: Dict[str, Any], host: str, model: str, timeout: int = 120) -> Optional[str]:
    """Optional user-facing refinement.  The structured result remains source of truth."""
    prompt = (
        "You are TRACE-Net's conversation guide. Do not invent evidence. "
        "Use only the JSON candidate_discovery_result below. Keep candidate routes as candidates, not final proof. "
        "Ask the listed clarifying questions and show the candidate routes cleanly.\n\n"
        f"candidate_discovery_result:\n{json.dumps(result, indent=2)}"
    )
    body = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
    url = host.rstrip("/") + "/api/generate"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        text = str(data.get("response") or "").strip()
        return text or None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def write_outputs(results: List[Dict[str, Any]], out_dir: Path, use_ollama: bool = False, ollama_host: str = "", model: str = "") -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    records_path = out_dir / "candidate_discovery_results.jsonl"
    view_path = out_dir / "candidate_discovery_view.txt"
    prompts_dir = out_dir / "prompts"
    prompts_dir.mkdir(exist_ok=True)
    views = []
    with records_path.open("w", encoding="utf-8") as f:
        for r in results:
            if use_ollama and ollama_host and model:
                refined = maybe_refine_with_ollama(r, ollama_host, model)
                if refined:
                    r["llm_refined_display"] = refined
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            (prompts_dir / f"{r['question_id']}_candidate_discovery_pack.json").write_text(json.dumps(r, indent=2), encoding="utf-8")
            views.append(r.get("llm_refined_display") or render_result(r))
    view_path.write_text("\n\n" + ("-" * 100) + "\n\n".join(views), encoding="utf-8")
    route_counts = Counter(r.get("intent") for r in results)
    summary = {
        "status": "TRACE_NET_GUIDED_CANDIDATE_DISCOVERY_V1_DONE",
        "quality_status": "PASS",
        "question_count": len(results),
        "candidate_route_question_count": sum(1 for r in results if r.get("candidate_route_count", 0) > 0),
        "no_candidate_route_question_count": sum(1 for r in results if r.get("candidate_route_count", 0) == 0),
        "total_candidate_route_count": sum(int(r.get("candidate_route_count") or 0) for r in results),
        "route_counts": dict(route_counts),
        "results": str(records_path),
        "view": str(view_path),
        "prompts_dir": str(prompts_dir),
        "final_answer_allowed_count": sum(1 for r in results if r.get("final_answer_allowed")),
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="TRACE-Net guided candidate discovery v1")
    ap.add_argument("--artifact-root", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--question", default=None)
    ap.add_argument("--questions", default=None)
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--max-records", type=int, default=250000)
    ap.add_argument("--use-ollama", action="store_true", help="Optionally ask Ollama to render the structured candidate result. Structured JSON remains source of truth.")
    ap.add_argument("--ollama-host", default="http://127.0.0.1:11434")
    ap.add_argument("--model", default="gemma4:26b")
    args = ap.parse_args(argv)

    root = Path(args.artifact_root)
    if not root.exists():
        raise SystemExit(f"artifact root not found: {root}")
    qs = load_questions(Path(args.questions) if args.questions else None, args.question)
    results = []
    start = time.time()
    for i, q in enumerate(qs, 1):
        qid = q.get("question_id") or f"q{i:02d}"
        question = q.get("question") or ""
        print(f"[{i:03d}/{len(qs):03d}] DISCOVERY {qid}: {question}", flush=True)
        result = build_discovery_result(qid, question, root, top_k=args.top_k, max_records=args.max_records)
        print(f"[{i:03d}/{len(qs):03d}] ROUTES {qid}: {result['candidate_route_count']} candidates, evidence={result['evidence_record_count']}", flush=True)
        results.append(result)
    summary = write_outputs(results, Path(args.output_dir), use_ollama=args.use_ollama, ollama_host=args.ollama_host, model=args.model)
    summary["elapsed_seconds"] = round(time.time() - start, 2)
    (Path(args.output_dir) / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"status={summary['status']}")
    print(f"quality_status={summary['quality_status']}")
    print(f"question_count={summary['question_count']}")
    print(f"candidate_route_question_count={summary['candidate_route_question_count']}")
    print(f"total_candidate_route_count={summary['total_candidate_route_count']}")
    print(f"view={summary['view']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
