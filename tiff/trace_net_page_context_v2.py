from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

PROMPT_VERSION = "page_context_v2_query_guidance_card"
VERSION = "trace_net_page_context_v2_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/page_context_v2")
DEFAULT_CONTEXT_FILE = Path("local_data/organization/context/page_contexts.json")

PART_RE = re.compile(r"\b(?:\d{3}-\d{5}-\d{3}|[A-Z]{1,4}\d[\w.-]{2,}|\d{2,}-[A-Z0-9][A-Z0-9-]{2,})\b")
PAGE_ID_RE = re.compile(r"p(\d{6})$")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9/-]{2,}")

STOP_TERMS = {
    "the", "and", "for", "with", "this", "that", "from", "page", "pages", "manual",
    "maintenance", "illustrated", "parts", "list", "section", "subject", "date", "chapter",
    "number", "numbers", "figure", "table", "code", "codes", "aircraft", "revision",
}

GENERIC_NOT_GOOD = [
    "proving source truth without checking the cited source page",
    "answering without a source URL, TIFF path, and OCR/source evidence",
]


class ContextV2Error(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    return value


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(data), indent=2, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[Dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(jsonable(rec), ensure_ascii=False) + "\n")
            count += 1
    return count


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_list(value: Any, *, max_items: int = 30) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        if "," in value:
            items = [x.strip() for x in value.split(",")]
        elif ";" in value:
            items = [x.strip() for x in value.split(";")]
        else:
            items = [value.strip()]
    elif isinstance(value, dict):
        items = []
        for key in ("name", "label", "text", "term", "part_number", "part", "value"):
            if value.get(key):
                items.append(str(value.get(key)).strip())
        if not items:
            items = [str(v).strip() for v in value.values() if isinstance(v, (str, int, float))]
    elif isinstance(value, (list, tuple, set)):
        items = []
        for item in value:
            items.extend(normalize_list(item, max_items=max_items))
    else:
        items = [str(value).strip()]
    seen = set()
    out = []
    for item in items:
        item = re.sub(r"\s+", " ", str(item)).strip(" \t\r\n,;|")
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= max_items:
            break
    return out


def normalize_page_number(page_id: str) -> Optional[int]:
    m = PAGE_ID_RE.search(page_id or "")
    if m:
        return int(m.group(1))
    m2 = re.search(r"(\d{1,6})$", page_id or "")
    if m2:
        return int(m2.group(1))
    return None


def page_sort_key(page_id: str) -> Tuple[int, str]:
    n = normalize_page_number(page_id)
    return (n if n is not None else 10**9, page_id)


def previous_next_page_ids(page_id: str) -> Dict[str, Optional[str]]:
    n = normalize_page_number(page_id)
    if n is None:
        return {"previous": None, "next": None}
    prefix = page_id[: -6]
    return {"previous": f"{prefix}{n-1:06d}" if n > 1 else None, "next": f"{prefix}{n+1:06d}"}


def first_nonempty(*values: Any, default: str = "") -> str:
    for v in values:
        if v is None:
            continue
        if isinstance(v, str) and v.strip():
            return v.strip()
        if not isinstance(v, str):
            s = str(v).strip()
            if s:
                return s
    return default


def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.I).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        data = json.loads(stripped)
        return data if isinstance(data, dict) else None
    except Exception:
        pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(stripped[start : end + 1])
            return data if isinstance(data, dict) else None
        except Exception:
            return None
    return None


def extract_part_numbers(*texts: str, max_items: int = 40) -> List[str]:
    seen = set()
    parts = []
    for text in texts:
        for m in PART_RE.finditer(text or ""):
            part = m.group(0).strip().upper()
            # Avoid the most common index/header labels that look like part-ish tokens.
            if part in {"25-IPL", "25-LEP", "20-IFL", "40-IFL"}:
                continue
            key = part.lower()
            if key not in seen:
                seen.add(key)
                parts.append(part)
                if len(parts) >= max_items:
                    return parts
    return parts


def extract_supporting_phrases(ocr_text: str, *, max_phrases: int = 5) -> List[str]:
    if not ocr_text:
        return []
    lines = [re.sub(r"\s+", " ", line).strip() for line in ocr_text.splitlines()]
    lines = [line for line in lines if len(line) >= 8]
    scored = []
    for line in lines[:120]:
        score = 0
        low = line.lower()
        for term in ("passenger", "seat", "parts", "list", "figure", "maintenance", "applicability", "vendor", "numerical", "backrest", "armrest", "snack table"):
            if term in low:
                score += 2
        if PART_RE.search(line):
            score += 1
        score += min(len(line) / 100.0, 1.0)
        scored.append((score, line[:220]))
    scored.sort(reverse=True, key=lambda x: x[0])
    out = []
    seen = set()
    for _, phrase in scored:
        key = phrase.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(phrase)
        if len(out) >= max_phrases:
            break
    return out


def infer_role_and_subrole(v1: Dict[str, Any], ocr_text: str) -> Tuple[str, str]:
    role = first_nonempty(v1.get("role"), v1.get("page_role"), v1.get("type"), default="unknown").lower().replace(" ", "_")
    text = f"{v1.get('summary','')} {ocr_text[:4000]}".lower()
    subrole = "general"
    if "empty ocr" in text or role == "blank":
        return "blank", "empty_or_blank_page"
    if "vendor" in text:
        subrole = "vendor_list"
    elif "numerical index" in text or "numerical" in text:
        subrole = "numerical_index"
    elif "effective page" in text or "list of effective pages" in text or "revision" in text:
        subrole = "effective_pages_or_revision_history"
    elif "applicability" in text:
        subrole = "applicability_part_list"
    elif "passenger seat" in text and any(t in text for t in ("armrest", "backrest", "snack table", "seat bottom")):
        subrole = "passenger_seat_overview"
    elif "figure" in text or role == "figure":
        subrole = "illustration_or_figure"
    elif "procedure" in text or role == "procedure":
        subrole = "maintenance_procedure"
    elif "parts list" in text or role == "parts_list":
        subrole = "parts_list"
    return role or "unknown", subrole


def infer_component_families(text: str) -> List[str]:
    low = (text or "").lower()
    candidates = []
    mapping = [
        ("passenger seat", ["passenger seat", "seat assembly"]),
        ("backrest", ["backrest", "seat back"]),
        ("seat bottom", ["seat bottom", "seat cushion", "seat pan"]),
        ("armrest", ["armrest"]),
        ("snack table", ["snack table", "tray table"]),
        ("upholstery", ["upholstery", "cover", "cushion"]),
        ("frame", ["frame", "structure", "support"]),
        ("fastener", ["fastener", "bolt", "screw", "washer", "nut"]),
        ("vendor", ["vendor", "supplier", "manufacturer"]),
        ("applicability", ["applicability", "effectivity"]),
    ]
    for family, terms in mapping:
        if any(t in low for t in terms):
            candidates.append(family)
    return normalize_list(candidates, max_items=12)


def build_retrieval_cues(v1: Dict[str, Any], ocr_text: str, role: str, subrole: str) -> List[str]:
    cues: List[str] = []
    summary = first_nonempty(v1.get("summary"), v1.get("short_summary"))
    cues.extend(normalize_list(v1.get("topics"), max_items=30))
    cues.extend(normalize_list(v1.get("tags"), max_items=20))
    cues.extend(normalize_list(v1.get("retrieval_cues"), max_items=30))
    cues.extend([role.replace("_", " "), subrole.replace("_", " ")])
    text = f"{summary} {ocr_text[:6000]}".lower()
    if "passenger" in text or "seat" in text:
        cues.extend(["passenger seat", "seat assembly", "seat bottom", "backrest", "armrest", "snack table", "seat frame", "upholstery"])
    if "applicability" in text:
        cues.extend(["applicability", "effectivity", "covered part numbers", "publication covers part numbers"])
    if "vendor" in text:
        cues.extend(["vendor list", "supplier", "manufacturer", "vendor code"])
    if "numerical" in text:
        cues.extend(["numerical index", "part number index", "index lookup"])
    if "effective page" in text or "revision" in text:
        cues.extend(["list of effective pages", "revision history", "page date", "manual update"])
    # Add a few distinctive OCR words/phrases without flooding the card.
    words = [w.lower() for w in WORD_RE.findall(text[:3000])]
    counts: Dict[str, int] = {}
    for w in words:
        if len(w) < 4 or w in STOP_TERMS:
            continue
        counts[w] = counts.get(w, 0) + 1
    top_words = [w for w, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:10]]
    cues.extend(top_words)
    return normalize_list(cues, max_items=40)


def answerable_questions(role: str, subrole: str, cues: Sequence[str]) -> List[str]:
    questions: List[str] = []
    if role == "blank":
        return []
    cue_text = " ".join(cues).lower()
    if "passenger seat" in cue_text or "seat" in cue_text:
        questions.extend([
            "Which pages discuss passenger seat components or assemblies?",
            "Which pages discuss the seat bottom, backrest, armrest, or snack table?",
            "Where does the manual describe passenger seat construction or design context?",
        ])
    if "applicability" in cue_text or "part" in cue_text:
        questions.extend([
            "Which part numbers are listed or referenced on this page?",
            "Where does the manual list applicability or covered part numbers?",
        ])
    if "vendor" in cue_text:
        questions.append("Where does the manual list vendor or supplier information?")
    if "numerical index" in cue_text:
        questions.append("Where can a part number be looked up in the numerical index?")
    if "effective pages" in cue_text or "revision" in cue_text:
        questions.append("Where does the manual show effective pages or revision history?")
    if not questions:
        questions.extend([
            "What is this page about in the manual?",
            "Which source page should be checked for details related to this topic?",
        ])
    return normalize_list(questions, max_items=8)


def not_good_for(role: str, subrole: str) -> List[str]:
    out = list(GENERIC_NOT_GOOD)
    if role == "blank":
        out.append("answering content questions because OCR is empty or the page is likely blank")
    if subrole in {"effective_pages_or_revision_history", "numerical_index", "vendor_list"}:
        out.append("proving detailed maintenance procedure steps without checking nearby/source pages")
    if "parts" in subrole:
        out.append("proving installation/removal procedure details without procedure evidence")
    return normalize_list(out, max_items=8)


def default_authority() -> Dict[str, Any]:
    return {
        "trust_scope": "page_context_summary",
        "rag_role": "retrieval_helper",
        "can_answer_directly": False,
        "can_support_answer": True,
        "canonical_source_truth": False,
        "requires_citation": True,
        "source_truth_mutation_allowed": False,
    }


def sanitize_context_v2(data: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    page_id = first_nonempty(data.get("page_id"), fallback.get("page_id"))
    role = first_nonempty(data.get("role"), fallback.get("role"), default="unknown").lower().replace(" ", "_")
    subrole = first_nonempty(data.get("subrole"), fallback.get("subrole"), default="general").lower().replace(" ", "_")
    confidence = first_nonempty(data.get("confidence"), fallback.get("confidence"), default="medium").lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "medium"
    auth = default_authority()
    auth.update(data.get("authority") if isinstance(data.get("authority"), dict) else {})
    # Hard safety overrides.
    auth["rag_role"] = "retrieval_helper"
    auth["can_answer_directly"] = False
    auth["can_support_answer"] = True
    auth["canonical_source_truth"] = False
    auth["requires_citation"] = True
    auth["source_truth_mutation_allowed"] = False

    result = {
        "page_id": page_id,
        "role": role,
        "subrole": subrole,
        "confidence": confidence,
        "short_summary": first_nonempty(data.get("short_summary"), data.get("summary"), fallback.get("short_summary"), default="No summary available."),
        "retrieval_summary": first_nonempty(data.get("retrieval_summary"), fallback.get("retrieval_summary"), data.get("short_summary"), default="Use this page as derived retrieval context only."),
        "answerable_questions": normalize_list(data.get("answerable_questions") or fallback.get("answerable_questions"), max_items=10),
        "retrieval_cues": normalize_list(data.get("retrieval_cues") or data.get("query_aliases") or fallback.get("retrieval_cues"), max_items=50),
        "important_entities": normalize_list(data.get("important_entities") or fallback.get("important_entities"), max_items=30),
        "component_families": normalize_list(data.get("component_families") or fallback.get("component_families"), max_items=20),
        "important_parts": normalize_list(data.get("important_parts") or data.get("part_numbers") or fallback.get("important_parts"), max_items=40),
        "nearby_context": data.get("nearby_context") if isinstance(data.get("nearby_context"), dict) else fallback.get("nearby_context", {}),
        "source_grounding": data.get("source_grounding") if isinstance(data.get("source_grounding"), dict) else fallback.get("source_grounding", {}),
        "not_good_for": normalize_list(data.get("not_good_for") or fallback.get("not_good_for"), max_items=10),
        "authority": auth,
    }
    if not result["answerable_questions"] and role != "blank":
        result["answerable_questions"] = answerable_questions(role, subrole, result["retrieval_cues"])
    if not result["retrieval_cues"]:
        result["retrieval_cues"] = [role.replace("_", " "), subrole.replace("_", " ")]
    return result


def heuristic_context_v2(page: Dict[str, Any]) -> Dict[str, Any]:
    v1 = page.get("v1_context") or {}
    ocr_text = page.get("ocr_text") or ""
    role, subrole = infer_role_and_subrole(v1, ocr_text)
    summary = first_nonempty(v1.get("summary"), v1.get("short_summary"), default="This page has source-backed OCR/context available for retrieval.")
    confidence = first_nonempty(v1.get("confidence"), default="medium").lower()
    if not ocr_text.strip() or role == "blank":
        confidence = "low"
    cues = build_retrieval_cues(v1, ocr_text, role, subrole)
    families = infer_component_families(f"{summary} {ocr_text[:5000]} {' '.join(cues)}")
    parts = normalize_list(v1.get("highlighted_parts") or v1.get("parts") or v1.get("important_parts"), max_items=40)
    if not parts:
        parts = extract_part_numbers(ocr_text, summary, max_items=40)
    phrases = extract_supporting_phrases(ocr_text)
    source_url_present = bool(first_nonempty(page.get("source_url"), v1.get("source_url")))
    fallback = {
        "page_id": page.get("page_id"),
        "role": role,
        "subrole": subrole,
        "confidence": confidence,
        "short_summary": summary,
        "retrieval_summary": f"Use this page as derived retrieval guidance for queries about {', '.join(cues[:8])}.",
        "answerable_questions": answerable_questions(role, subrole, cues),
        "retrieval_cues": cues,
        "important_entities": normalize_list(families + normalize_list(v1.get("topics"), max_items=15), max_items=25),
        "component_families": families,
        "important_parts": parts,
        "nearby_context": previous_next_page_ids(page.get("page_id", "")),
        "source_grounding": {
            "has_ocr": bool(ocr_text.strip()),
            "source_url_present": source_url_present,
            "ocr_classification": page.get("ocr_classification"),
            "supporting_ocr_phrases": phrases,
            "source_url": first_nonempty(page.get("source_url"), default=""),
        },
        "not_good_for": not_good_for(role, subrole),
        "authority": default_authority(),
    }
    return sanitize_context_v2({}, fallback)


def build_prompt(page: Dict[str, Any], heuristic: Dict[str, Any]) -> str:
    v1 = page.get("v1_context") or {}
    ocr_text = (page.get("ocr_text") or "")[: page.get("max_ocr_chars", 6000)]
    parts = normalize_list(heuristic.get("important_parts"), max_items=25)
    prompt = f"""
You are creating a TRACE-Net Page Context v2 query-guidance card for a scanned aircraft maintenance manual page.

Write a structured retrieval helper card, not a final answer. The card helps RAG find the right source page later.
Do not invent facts. Use only the OCR/source/context below. If unsure, say so using conservative wording.
The context is derived retrieval context only: it is not canonical source truth and cannot answer directly without source citation.

Return ONLY valid JSON with this exact shape:
{{
  "page_id": "{page.get('page_id')}",
  "role": "parts_list|figure|table|procedure|front_matter|blank|unknown",
  "subrole": "short_snake_case_subrole",
  "confidence": "high|medium|low",
  "short_summary": "1 sentence: what is on this page",
  "retrieval_summary": "1-2 sentences: what user queries this page should help retrieve",
  "answerable_questions": ["question this page can help route toward"],
  "retrieval_cues": ["phrases users may search for, including synonyms and manual terms"],
  "important_entities": ["component or concept names, not just topics"],
  "component_families": ["higher level part/component families"],
  "important_parts": ["part numbers only when present in OCR/context"],
  "nearby_context": {{"previous": "...", "next": "...", "same_section_hint": "..."}},
  "source_grounding": {{"has_ocr": true, "source_url_present": true, "supporting_ocr_phrases": ["short source-backed phrases"]}},
  "not_good_for": ["what this page should not be used to answer directly"],
  "authority": {{
    "rag_role": "retrieval_helper",
    "can_answer_directly": false,
    "can_support_answer": true,
    "canonical_source_truth": false,
    "requires_citation": true
  }}
}}

Example style:
Page: t_p_120_1176_p000015
Role: passenger seat overview / parts list / design description
What this page can help answer:
- What passenger seat components are shown or described?
- Which pages discuss the seat bottom, backrest, armrest, or snack table?
- Where does the manual describe general passenger seat construction?
Retrieval cues: passenger seat, seat bottom, backrest, armrest, snack table, seat assembly, upholstery, design, frame, component maintenance manual
Important entities: passenger seat, armrest, snack table, seat bottom, backrest
Authority: derived retrieval context only, not canonical source truth, requires source citation

Current page inputs:
page_id: {page.get('page_id')}
existing_role: {v1.get('role') or v1.get('page_role') or ''}
existing_confidence: {v1.get('confidence') or ''}
existing_summary: {v1.get('summary') or v1.get('short_summary') or ''}
existing_topics: {normalize_list(v1.get('topics'), max_items=20)}
existing_highlighted_parts: {parts}
source_url_present: {bool(page.get('source_url'))}
ocr_classification: {page.get('ocr_classification') or ''}
OCR excerpt:
{ocr_text}
""".strip()
    return prompt


def call_ollama(prompt: str, model: str, url: str, timeout: int = 240, temperature: float = 0.0) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    parsed = json.loads(body)
    return str(parsed.get("response") or "")


def db_connect(database_url: str):
    try:
        import psycopg
    except Exception as exc:  # pragma: no cover
        raise ContextV2Error("psycopg is required. Install with: pip install 'psycopg[binary]'") from exc
    return psycopg.connect(database_url)


def table_exists(cur, table: str) -> bool:
    cur.execute("select to_regclass(%s)", (f"public.{table}",))
    return bool(cur.fetchone()[0])


def load_v1_context_file(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    data = load_json(path)
    records: List[Dict[str, Any]] = []
    if isinstance(data, list):
        records = [x for x in data if isinstance(x, dict)]
    elif isinstance(data, dict):
        for key in ("contexts", "records", "pages", "items"):
            if isinstance(data.get(key), list):
                records = [x for x in data[key] if isinstance(x, dict)]
                break
        if not records:
            # Map form: page_id -> context object
            for key, value in data.items():
                if isinstance(value, dict):
                    rec = dict(value)
                    rec.setdefault("page_id", key)
                    records.append(rec)
    out: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        pid = first_nonempty(rec.get("page_id"), rec.get("id"), rec.get("page"))
        if pid:
            out[pid] = rec
    return out


def collect_page_inputs(database_url: str, context_file: Path, *, max_ocr_chars: int = 6000) -> List[Dict[str, Any]]:
    v1_file = load_v1_context_file(context_file)
    pages: Dict[str, Dict[str, Any]] = {}
    with db_connect(database_url) as conn:
        with conn.cursor() as cur:
            # Primary page set: candidates/citations/context table give canonical t_p page ids.
            for sql in [
                "select distinct page_id from rag_candidate_chunks where page_id is not null and page_id <> ''",
                "select distinct page_id from source_citations where page_id is not null and page_id <> ''",
                "select distinct page_id from page_context_records where page_id is not null and page_id <> ''" if table_exists(cur, "page_context_records") else None,
            ]:
                if not sql:
                    continue
                cur.execute(sql)
                for (pid,) in cur.fetchall():
                    pages.setdefault(pid, {"page_id": pid})

            if not pages and table_exists(cur, "pages"):
                cur.execute("select page_id from pages")
                for (pid,) in cur.fetchall():
                    pages.setdefault(pid, {"page_id": pid})

            # Add source text evidence as the safest OCR text candidate for canonical page ids.
            if table_exists(cur, "rag_candidate_chunks"):
                cur.execute("""
                    select page_id, text, source_url, tiff_path, ocr_path, usable_confidence, trust_tier
                    from rag_candidate_chunks
                    where rag_bucket='source_text_evidence'
                    order by page_id, candidate_id
                """)
                for row in cur.fetchall():
                    pid = row[0]
                    rec = pages.setdefault(pid, {"page_id": pid})
                    if not rec.get("ocr_text"):
                        rec.update({
                            "ocr_text": row[1] or "",
                            "source_url": row[2] or "",
                            "tiff_path": row[3] or "",
                            "ocr_path": row[4] or "",
                            "usable_confidence": row[5],
                            "trust_tier": row[6] or "",
                        })

            # Add OCR classifications by matching page number when page ids differ (zip_page vs t_p id).
            if table_exists(cur, "ocr_records"):
                cur.execute("select page_id, text, classification, ocr_path from ocr_records")
                ocr_by_num: Dict[int, Tuple[str, str, str, str]] = {}
                for row in cur.fetchall():
                    n = normalize_page_number(str(row[0]))
                    if n is not None:
                        ocr_by_num[n] = row
                for pid, rec in pages.items():
                    n = normalize_page_number(pid)
                    if n is not None and n in ocr_by_num:
                        _, text, classification, ocr_path = ocr_by_num[n]
                        rec.setdefault("ocr_text", text or "")
                        rec["ocr_classification"] = classification
                        rec.setdefault("ocr_path", ocr_path or "")

            # Existing v1 page_context_records in Postgres can fill summary/role/topics.
            if table_exists(cur, "page_context_records"):
                cur.execute("select page_id, role, confidence, summary, topics, highlighted_parts, payload from page_context_records")
                for row in cur.fetchall():
                    pid = row[0]
                    rec = pages.setdefault(pid, {"page_id": pid})
                    v1 = dict(v1_file.get(pid) or {})
                    v1.setdefault("role", row[1])
                    v1.setdefault("confidence", row[2])
                    v1.setdefault("summary", row[3])
                    v1.setdefault("topics", row[4] or [])
                    v1.setdefault("highlighted_parts", row[5] or [])
                    if isinstance(row[6], dict):
                        for k, v in row[6].items():
                            v1.setdefault(k, v)
                    rec["v1_context"] = v1

    for pid, rec in pages.items():
        rec.setdefault("v1_context", v1_file.get(pid) or {})
        rec["max_ocr_chars"] = max_ocr_chars
        if rec.get("ocr_text") and len(rec["ocr_text"]) > max_ocr_chars:
            rec["ocr_text"] = rec["ocr_text"][:max_ocr_chars]
    return [pages[k] for k in sorted(pages, key=page_sort_key)]


def ensure_schema(cur) -> None:
    cur.execute(
        """
        create table if not exists page_context_v2_records(
            context_id text primary key,
            page_id text not null,
            document_id text,
            role text,
            subrole text,
            confidence text,
            short_summary text,
            retrieval_summary text,
            answerable_questions jsonb,
            retrieval_cues jsonb,
            important_entities jsonb,
            component_families jsonb,
            important_parts jsonb,
            nearby_context jsonb,
            source_grounding jsonb,
            authority jsonb,
            not_good_for jsonb,
            generation_provider text,
            generation_model text,
            prompt_version text,
            status text,
            payload jsonb,
            updated_at timestamptz default now()
        )
        """
    )
    cur.execute("create index if not exists idx_page_context_v2_page_id on page_context_v2_records(page_id)")
    cur.execute("create index if not exists idx_page_context_v2_role on page_context_v2_records(role)")
    cur.execute("create index if not exists idx_page_context_v2_confidence on page_context_v2_records(confidence)")


def existing_v2_page_ids(database_url: str) -> set[str]:
    with db_connect(database_url) as conn:
        with conn.cursor() as cur:
            if not table_exists(cur, "page_context_v2_records"):
                return set()
            cur.execute("select page_id from page_context_v2_records")
            return {str(r[0]) for r in cur.fetchall()}


def upsert_context_v2_records(database_url: str, records: Sequence[Dict[str, Any]]) -> None:
    with db_connect(database_url) as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            for rec in records:
                pid = rec["page_id"]
                context_id = f"page_context_v2:{pid}"
                payload = dict(rec)
                cur.execute(
                    """
                    insert into page_context_v2_records(
                        context_id, page_id, document_id, role, subrole, confidence, short_summary,
                        retrieval_summary, answerable_questions, retrieval_cues, important_entities,
                        component_families, important_parts, nearby_context, source_grounding, authority,
                        not_good_for, generation_provider, generation_model, prompt_version, status, payload, updated_at
                    ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s::jsonb,now())
                    on conflict(context_id) do update set
                        page_id=excluded.page_id,
                        document_id=excluded.document_id,
                        role=excluded.role,
                        subrole=excluded.subrole,
                        confidence=excluded.confidence,
                        short_summary=excluded.short_summary,
                        retrieval_summary=excluded.retrieval_summary,
                        answerable_questions=excluded.answerable_questions,
                        retrieval_cues=excluded.retrieval_cues,
                        important_entities=excluded.important_entities,
                        component_families=excluded.component_families,
                        important_parts=excluded.important_parts,
                        nearby_context=excluded.nearby_context,
                        source_grounding=excluded.source_grounding,
                        authority=excluded.authority,
                        not_good_for=excluded.not_good_for,
                        generation_provider=excluded.generation_provider,
                        generation_model=excluded.generation_model,
                        prompt_version=excluded.prompt_version,
                        status=excluded.status,
                        payload=excluded.payload,
                        updated_at=now()
                    """,
                    (
                        context_id,
                        pid,
                        rec.get("document_id") or "t_p_120_1176",
                        rec.get("role"),
                        rec.get("subrole"),
                        rec.get("confidence"),
                        rec.get("short_summary"),
                        rec.get("retrieval_summary"),
                        json.dumps(jsonable(rec.get("answerable_questions") or [])),
                        json.dumps(jsonable(rec.get("retrieval_cues") or [])),
                        json.dumps(jsonable(rec.get("important_entities") or [])),
                        json.dumps(jsonable(rec.get("component_families") or [])),
                        json.dumps(jsonable(rec.get("important_parts") or [])),
                        json.dumps(jsonable(rec.get("nearby_context") or {})),
                        json.dumps(jsonable(rec.get("source_grounding") or {})),
                        json.dumps(jsonable(rec.get("authority") or {})),
                        json.dumps(jsonable(rec.get("not_good_for") or [])),
                        rec.get("generation_provider"),
                        rec.get("generation_model"),
                        rec.get("prompt_version") or PROMPT_VERSION,
                        rec.get("status") or "ok",
                        json.dumps(jsonable(payload)),
                    ),
                )
                # Graph overlay node and edge. Page graph node naming convention is page:<page_id>.
                node_payload = {
                    "page_id": pid,
                    "role": rec.get("role"),
                    "subrole": rec.get("subrole"),
                    "confidence": rec.get("confidence"),
                    "retrieval_summary": rec.get("retrieval_summary"),
                    "authority": rec.get("authority"),
                }
                cur.execute(
                    """
                    insert into graph_nodes(node_id, node_type, label, payload, updated_at)
                    values (%s,%s,%s,%s::jsonb,now())
                    on conflict(node_id) do update set node_type=excluded.node_type, label=excluded.label, payload=excluded.payload, updated_at=now()
                    """,
                    (context_id, "page_context_v2", f"Context v2 {pid}", json.dumps(jsonable(node_payload))),
                )
                edge_id = f"has_context_v2:{pid}"
                cur.execute(
                    """
                    insert into graph_edges(edge_id, source_id, target_id, edge_type, payload, updated_at)
                    values (%s,%s,%s,%s,%s::jsonb,now())
                    on conflict(edge_id) do update set source_id=excluded.source_id, target_id=excluded.target_id, edge_type=excluded.edge_type, payload=excluded.payload, updated_at=now()
                    """,
                    (edge_id, f"page:{pid}", context_id, "HAS_CONTEXT_V2", json.dumps({"page_id": pid, "prompt_version": PROMPT_VERSION})),
                )
            conn.commit()


def collect_postgres_summary(database_url: str) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    with db_connect(database_url) as conn:
        with conn.cursor() as cur:
            def one(sql: str) -> int:
                try:
                    cur.execute(sql)
                    return int(cur.fetchone()[0] or 0)
                except Exception:
                    conn.rollback()
                    return 0
            summary["postgres_page_context_v2_records"] = one("select count(*) from page_context_v2_records")
            summary["postgres_pages_with_context_v2"] = one("select count(distinct page_id) from page_context_v2_records")
            summary["postgres_context_v2_with_retrieval_cues"] = one("select count(*) from page_context_v2_records where jsonb_array_length(coalesce(retrieval_cues,'[]'::jsonb)) > 0")
            summary["postgres_context_v2_with_answerable_questions"] = one("select count(*) from page_context_v2_records where jsonb_array_length(coalesce(answerable_questions,'[]'::jsonb)) > 0")
            summary["postgres_direct_answer_context_v2_records"] = one("select count(*) from page_context_v2_records where coalesce((authority->>'can_answer_directly')::boolean,false) = true")
            summary["postgres_canonical_source_truth_context_v2_records"] = one("select count(*) from page_context_v2_records where coalesce((authority->>'canonical_source_truth')::boolean,false) = true")
            summary["postgres_context_v2_graph_nodes"] = one("select count(*) from graph_nodes where node_type='page_context_v2'")
            summary["postgres_has_context_v2_edges"] = one("select count(*) from graph_edges where edge_type='HAS_CONTEXT_V2'")
    return summary


def generate_context_v2(
    page: Dict[str, Any],
    *,
    provider: str,
    model: str,
    ollama_url: str,
    timeout_seconds: int,
    temperature: float,
) -> Dict[str, Any]:
    heuristic = heuristic_context_v2(page)
    rec = heuristic
    raw_response = ""
    status = "ok"
    warnings: List[str] = []
    if provider == "ollama" and (page.get("ocr_text") or "").strip():
        prompt = build_prompt(page, heuristic)
        try:
            raw_response = call_ollama(prompt, model=model, url=ollama_url, timeout=timeout_seconds, temperature=temperature)
            parsed = extract_json_from_text(raw_response)
            if parsed:
                rec = sanitize_context_v2(parsed, heuristic)
            else:
                warnings.append("llm_response_not_valid_json_fallback_heuristic")
        except Exception as exc:
            status = "warning"
            warnings.append(f"llm_error_fallback_heuristic:{type(exc).__name__}:{str(exc)[:120]}")
    elif provider == "ollama":
        warnings.append("empty_ocr_skipped_llm_fallback_heuristic")
        status = "warning" if rec.get("role") == "blank" else "ok"
    else:
        provider = "heuristic"
    rec["generation_provider"] = provider
    rec["generation_model"] = model if provider == "ollama" else "heuristic-page-context-v2"
    rec["prompt_version"] = PROMPT_VERSION
    rec["status"] = status
    rec["warnings"] = warnings
    if raw_response:
        rec["llm_response_preview"] = raw_response[:500]
    return rec


def build_page_context_v2(
    database_url: str,
    *,
    context_file: Path = DEFAULT_CONTEXT_FILE,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    limit: Optional[int] = None,
    page_ids: Optional[List[str]] = None,
    missing_only: bool = False,
    force: bool = False,
    provider: str = "ollama",
    model: str = "gemma3:12B",
    ollama_url: str = "http://localhost:11434/api/generate",
    max_ocr_chars: int = 6000,
    timeout_seconds: int = 240,
    temperature: float = 0.0,
    progress: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    started = time.time()
    output_dir.mkdir(parents=True, exist_ok=True)
    pages = collect_page_inputs(database_url, context_file=context_file, max_ocr_chars=max_ocr_chars)
    if page_ids:
        requested = set(page_ids)
        pages = [p for p in pages if p.get("page_id") in requested]
    existing = set()
    if missing_only and not force:
        existing = existing_v2_page_ids(database_url)
        pages = [p for p in pages if p.get("page_id") not in existing]
    if limit is not None:
        pages = pages[:limit]

    records: List[Dict[str, Any]] = []
    total = len(pages)
    for idx, page in enumerate(pages, start=1):
        t0 = time.time()
        rec = generate_context_v2(page, provider=provider, model=model, ollama_url=ollama_url, timeout_seconds=timeout_seconds, temperature=temperature)
        records.append(rec)
        if progress:
            elapsed = time.time() - t0
            print(f"[{idx}/{total}] page={rec.get('page_id')} role={rec.get('role')} subrole={rec.get('subrole')} cues={len(rec.get('retrieval_cues') or [])} questions={len(rec.get('answerable_questions') or [])} status={rec.get('status')} elapsed={elapsed:.2f}s", flush=True)

    if not dry_run:
        upsert_context_v2_records(database_url, records)

    records_path = output_dir / "trace_net_page_context_v2_records.jsonl"
    write_jsonl(records_path, records)
    with_questions = sum(1 for r in records if r.get("answerable_questions"))
    with_cues = sum(1 for r in records if r.get("retrieval_cues"))
    direct = sum(1 for r in records if (r.get("authority") or {}).get("can_answer_directly"))
    canonical = sum(1 for r in records if (r.get("authority") or {}).get("canonical_source_truth"))
    source_mut = sum(1 for r in records if (r.get("authority") or {}).get("source_truth_mutation_allowed"))
    blank_no_answer = sum(1 for r in records if r.get("role") == "blank" and not r.get("answerable_questions"))
    warning_records = sum(1 for r in records if r.get("warnings"))
    summary = {
        "status": "OK",
        "version": VERSION,
        "prompt_version": PROMPT_VERSION,
        "context_file": str(context_file),
        "database_url_present": bool(database_url),
        "dry_run": dry_run,
        "provider": provider,
        "model": model,
        "pages_selected": total,
        "context_v2_records_generated": len(records),
        "records_with_retrieval_cues": with_cues,
        "records_with_answerable_questions": with_questions,
        "blank_no_answer_records": blank_no_answer,
        "direct_answer_context_records": direct,
        "canonical_source_truth_context_records": canonical,
        "source_truth_mutation_records": source_mut,
        "warning_records": warning_records,
        "elapsed_seconds": round(time.time() - started, 3),
        "created_at": utc_now(),
        "records_path": str(records_path),
    }
    if not dry_run:
        summary.update(collect_postgres_summary(database_url))
    summary_path = output_dir / "trace_net_page_context_v2_summary.json"
    write_json(summary_path, summary)
    write_report(output_dir / "trace_net_page_context_v2_report.html", summary, records[:60])
    write_report_md(output_dir / "trace_net_page_context_v2_report.md", summary, records[:60])
    # Tiny graph overlay artifact for review.
    graph_nodes = []
    graph_edges = []
    for r in records:
        pid = r.get("page_id")
        cid = f"page_context_v2:{pid}"
        graph_nodes.append({"id": cid, "type": "page_context_v2", "label": f"Context v2 {pid}", "payload": r})
        graph_edges.append({"id": f"has_context_v2:{pid}", "source": f"page:{pid}", "target": cid, "type": "HAS_CONTEXT_V2"})
    write_json(output_dir / "trace_net_page_context_v2_graph_nodes.json", graph_nodes)
    write_json(output_dir / "trace_net_page_context_v2_graph_edges.json", graph_edges)
    return summary


def html_escape(s: Any) -> str:
    import html
    return html.escape(str(s) if s is not None else "")


def write_report(path: Path, summary: Dict[str, Any], records: Sequence[Dict[str, Any]]) -> None:
    rows = []
    for r in records:
        rows.append(
            "<tr>"
            f"<td>{html_escape(r.get('page_id'))}</td>"
            f"<td>{html_escape(r.get('role'))}</td>"
            f"<td>{html_escape(r.get('subrole'))}</td>"
            f"<td>{html_escape(r.get('confidence'))}</td>"
            f"<td>{html_escape(', '.join((r.get('retrieval_cues') or [])[:8]))}</td>"
            f"<td>{html_escape(r.get('retrieval_summary'))}</td>"
            "</tr>"
        )
    html_doc = f"""<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Page Context v2</title>
<style>body{{font-family:Arial,sans-serif;margin:24px;background:#f8fafc;color:#0f172a}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #cbd5e1;padding:6px;vertical-align:top}}th{{background:#e2e8f0}}code,pre{{background:#e2e8f0;padding:2px 4px}}</style></head><body>
<h1>TRACE-Net Page Context v2 / Query Guidance Overlay</h1>
<p>Status: <b>{html_escape(summary.get('status'))}</b> Version: <code>{html_escape(summary.get('version'))}</code></p>
<h2>Summary</h2><pre>{html_escape(json.dumps(jsonable(summary), indent=2))}</pre>
<h2>Sample context cards</h2><table><thead><tr><th>Page</th><th>Role</th><th>Subrole</th><th>Confidence</th><th>Retrieval cues</th><th>Retrieval summary</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
</body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_doc, encoding="utf-8")


def write_report_md(path: Path, summary: Dict[str, Any], records: Sequence[Dict[str, Any]]) -> None:
    lines = ["# TRACE-Net Page Context v2 / Query Guidance Overlay", "", f"Status: **{summary.get('status')}**", "", "## Summary", ""]
    for key in ["context_v2_records_generated", "records_with_retrieval_cues", "records_with_answerable_questions", "direct_answer_context_records", "canonical_source_truth_context_records", "source_truth_mutation_records"]:
        lines.append(f"- **{key}**: {summary.get(key)}")
    lines.extend(["", "## Samples", ""])
    for r in records[:20]:
        lines.append(f"### {r.get('page_id')} / {r.get('role')} / {r.get('subrole')}")
        lines.append("")
        lines.append(str(r.get("retrieval_summary") or ""))
        lines.append("")
        lines.append("Retrieval cues: " + ", ".join((r.get("retrieval_cues") or [])[:12]))
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def open_file(path: Path) -> None:
    try:
        webbrowser.open(path.resolve().as_uri())
    except Exception:
        pass


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate TRACE-Net Page Context v2 query-guidance cards.")
    p.add_argument("--database-url", default=os.environ.get("TRACE_NET_DATABASE_URL"))
    p.add_argument("--context-file", default=str(DEFAULT_CONTEXT_FILE))
    p.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--page-id", action="append", default=[])
    p.add_argument("--missing-only", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--provider", choices=["ollama", "heuristic"], default="ollama")
    p.add_argument("--model", default="gemma3:12B")
    p.add_argument("--ollama-url", default="http://localhost:11434/api/generate")
    p.add_argument("--max-ocr-chars", type=int, default=6000)
    p.add_argument("--timeout-seconds", type=int, default=240)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--progress", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--open", action="store_true")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if not args.database_url and not args.dry_run:
        print("ERROR: --database-url or TRACE_NET_DATABASE_URL is required unless --dry-run is used", file=sys.stderr)
        return 2
    provider = args.provider
    if args.force:
        # force means regenerate selected pages, not skip existing.
        missing_only = False
    else:
        missing_only = args.missing_only
    summary = build_page_context_v2(
        args.database_url or "",
        context_file=Path(args.context_file),
        output_dir=Path(args.output_dir),
        limit=args.limit,
        page_ids=args.page_id,
        missing_only=missing_only,
        force=args.force,
        provider=provider,
        model=args.model,
        ollama_url=args.ollama_url,
        max_ocr_chars=args.max_ocr_chars,
        timeout_seconds=args.timeout_seconds,
        temperature=args.temperature,
        progress=args.progress,
        dry_run=args.dry_run,
    )
    print("TRACE-Net Page Context v2 / query guidance")
    print(f"  Status: {summary.get('status')}")
    print(f"  Version: {summary.get('version')}")
    print(f"  Output dir: {Path(args.output_dir)}")
    print("  Summary:")
    for key in [
        "pages_selected",
        "context_v2_records_generated",
        "records_with_retrieval_cues",
        "records_with_answerable_questions",
        "blank_no_answer_records",
        "direct_answer_context_records",
        "canonical_source_truth_context_records",
        "source_truth_mutation_records",
        "postgres_page_context_v2_records",
        "postgres_context_v2_graph_nodes",
        "postgres_has_context_v2_edges",
    ]:
        if key in summary:
            print(f"    {key}: {summary.get(key)}")
    print("Files written:")
    print(f"  summary: {Path(args.output_dir) / 'trace_net_page_context_v2_summary.json'}")
    print(f"  records: {Path(args.output_dir) / 'trace_net_page_context_v2_records.jsonl'}")
    print(f"  report_html: {Path(args.output_dir) / 'trace_net_page_context_v2_report.html'}")
    if args.open:
        open_file(Path(args.output_dir) / "trace_net_page_context_v2_report.html")
    return 0 if summary.get("status") == "OK" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
