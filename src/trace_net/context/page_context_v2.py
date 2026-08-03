"""TRACE-Net Page Context v2 / Query Guidance Overlay.

This module turns existing page context + OCR/source metadata into structured
retrieval guidance cards.  The cards are derived helpers, not source truth.
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

DEFAULT_CONTEXT_FILE = Path("local_data/organization/context/page_contexts.json")
DEFAULT_OUTPUT_DIR = Path("local_data/organization/context")
DEFAULT_OUTPUT_JSON = DEFAULT_OUTPUT_DIR / "page_contexts_v2.json"
DEFAULT_OUTPUT_JSONL = DEFAULT_OUTPUT_DIR / "page_contexts_v2.jsonl"
DEFAULT_SUMMARY = DEFAULT_OUTPUT_DIR / "page_contexts_v2_summary.json"
DEFAULT_REPORT = DEFAULT_OUTPUT_DIR / "page_contexts_v2_report.html"

AUTHORITY = {
    "trust_scope": "page_context_summary_v2",
    "rag_role": "retrieval_helper",
    "can_answer_directly": False,
    "can_support_answer": True,
    "canonical_source_truth": False,
    "requires_citation": True,
    "source_truth_mutation_allowed": False,
    "authority_note": "Derived context helps retrieval and routing; final answers must cite source text/citations.",
}

ROLE_CUE_MAP = {
    "blank": ["blank page", "no visible OCR", "empty OCR"],
    "front_matter": ["manual introduction", "revision notice", "title block", "front matter"],
    "parts_list": ["parts list", "part number", "illustrated parts", "applicability", "component list"],
    "procedure": ["maintenance procedure", "assembly", "disassembly", "inspection", "repair"],
    "table": ["table", "index", "effective pages", "list of effective pages", "tabular data"],
    "figure": ["figure", "illustration", "diagram", "drawing", "callout", "exploded view"],
}

COMPONENT_TERMS = [
    "passenger seat", "seat bottom", "backrest", "armrest", "snack table", "seat assembly",
    "seat frame", "upholstery", "cushion", "support", "bracket", "fastener", "track", "leg",
    "single passenger seat", "double passenger seat", "seat structure", "component maintenance manual",
]

PART_RE = re.compile(r"\b(?:\d{2,3}[- ][A-Z0-9]{2,6}[- ][A-Z0-9]{2,6}|\d{3}-\d{5}-\d{3}|[A-Z]{1,3}\d{2,5}[-A-Z0-9]*)\b", re.I)
PAGE_ID_RE = re.compile(r"p(\d{6})")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any = None) -> Any:
    if not path or not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, str):
        # split comma/newline only when it looks like a list
        if "," in value:
            return [v.strip() for v in value.split(",") if v.strip()]
        return [value] if value.strip() else []
    return [value]


def clean_text(value: Any, max_len: int = 5000) -> str:
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def page_num(page_id: str) -> int:
    m = PAGE_ID_RE.search(page_id or "")
    return int(m.group(1)) if m else 10**9


def normalize_contexts(raw: Any) -> List[Dict[str, Any]]:
    """Support several likely page_contexts.json shapes."""
    if raw is None:
        return []
    if isinstance(raw, dict):
        if isinstance(raw.get("contexts"), list):
            items = raw["contexts"]
        elif isinstance(raw.get("records"), list):
            items = raw["records"]
        elif isinstance(raw.get("pages"), list):
            items = raw["pages"]
        else:
            # likely mapping page_id -> record
            items = []
            for key, value in raw.items():
                if isinstance(value, dict):
                    rec = dict(value)
                    rec.setdefault("page_id", key)
                    items.append(rec)
    elif isinstance(raw, list):
        items = raw
    else:
        items = []

    out: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rec = dict(item)
        page_id = rec.get("page_id") or rec.get("id") or rec.get("page") or rec.get("node_id")
        if page_id:
            rec["page_id"] = str(page_id)
            out.append(rec)
    return sorted(out, key=lambda r: page_num(str(r.get("page_id", ""))))


def extract_topics(ctx: Dict[str, Any]) -> List[str]:
    candidates = []
    for key in ("topics", "tags", "retrieval_topics", "topic_terms"):
        candidates.extend(as_list(ctx.get(key)))
    # Sometimes topics are dicts
    out = []
    for item in candidates:
        if isinstance(item, dict):
            val = item.get("topic") or item.get("label") or item.get("name")
        else:
            val = item
        val = clean_text(val, 120)
        if val and val.lower() not in {x.lower() for x in out}:
            out.append(val)
    return out[:20]


def extract_parts(ctx: Dict[str, Any]) -> List[str]:
    keys = [
        "highlighted_parts", "highlighted_part_numbers", "part_numbers", "detected_parts",
        "important_parts", "catalog_supported_parts", "mentioned_parts", "parts",
    ]
    parts: List[str] = []
    for key in keys:
        for item in as_list(ctx.get(key)):
            if isinstance(item, dict):
                val = item.get("part_number") or item.get("part") or item.get("value") or item.get("label")
            else:
                val = item
            val = clean_text(val, 80)
            if val and val.upper() not in {p.upper() for p in parts}:
                parts.append(val)
    # Scan summary too, but keep limited.
    text = " ".join(clean_text(ctx.get(k), 3000) for k in ("summary", "short_summary", "text", "ocr_sample"))
    for m in PART_RE.finditer(text):
        val = m.group(0).replace(" ", "-")
        if val and val.upper() not in {p.upper() for p in parts}:
            parts.append(val)
    return parts[:40]


def load_ocr_from_postgres(database_url: Optional[str], max_chars: int = 5000) -> Dict[str, str]:
    if not database_url:
        return {}
    try:
        import psycopg  # type: ignore
    except Exception:
        return {}
    ocr: Dict[str, str] = {}
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("select page_id, text from ocr_records")
            for page_id, text in cur.fetchall():
                if page_id:
                    ocr[str(page_id)] = clean_text(text or "", max_chars)
                    # also support zip_page alias -> t_p_120_1176_p000001
                    m = re.search(r"(\d{6})", str(page_id))
                    if m:
                        ocr[f"t_p_120_1176_p{m.group(1)}"] = clean_text(text or "", max_chars)
    return ocr


def make_prompt(ctx: Dict[str, Any], ocr_text: str, prev_ctx: Optional[Dict[str, Any]], next_ctx: Optional[Dict[str, Any]]) -> str:
    page_id = ctx.get("page_id")
    role = ctx.get("role", "unknown")
    summary = ctx.get("summary") or ctx.get("short_summary") or ""
    topics = extract_topics(ctx)
    parts = extract_parts(ctx)
    prev_desc = f"{prev_ctx.get('page_id')} role={prev_ctx.get('role')} summary={clean_text(prev_ctx.get('summary') or prev_ctx.get('short_summary'), 300)}" if prev_ctx else "none"
    next_desc = f"{next_ctx.get('page_id')} role={next_ctx.get('role')} summary={clean_text(next_ctx.get('summary') or next_ctx.get('short_summary'), 300)}" if next_ctx else "none"
    return f"""
You are creating a TRACE-Net Page Context v2 retrieval-guidance card for an aircraft maintenance manual page.
Return ONLY valid JSON. Do not use markdown.

Rules:
- Use only the provided OCR/context. Do not invent facts.
- The context is a retrieval helper, not source truth.
- Mark can_answer_directly=false, canonical_source_truth=false, requires_citation=true.
- Include useful user-query language, not just generic topics.
- If the page is blank or OCR is empty, say so and provide minimal cues.
- Keep lists concise.

Required JSON schema:
{{
  "page_id": "{page_id}",
  "role": "...",
  "subrole": "...",
  "confidence": "high|medium|low",
  "short_summary": "one sentence",
  "retrieval_summary": "what this page can help retrieve",
  "answerable_questions": ["..."],
  "retrieval_cues": ["..."],
  "important_entities": ["..."],
  "component_families": ["..."],
  "supporting_ocr_phrases": ["short exact-ish phrases from OCR"],
  "nearby_context": {{"previous": "...", "next": "..."}},
  "not_good_for": ["..."],
  "authority": {{
    "rag_role": "retrieval_helper",
    "can_answer_directly": false,
    "can_support_answer": true,
    "canonical_source_truth": false,
    "requires_citation": true,
    "source_truth_mutation_allowed": false
  }}
}}

Existing v1 context:
page_id: {page_id}
role: {role}
summary: {clean_text(summary, 900)}
topics: {topics[:12]}
parts/entities from existing context: {parts[:20]}
previous page: {prev_desc}
next page: {next_desc}

OCR excerpt:
{clean_text(ocr_text, 6000)}
""".strip()


def call_ollama(prompt: str, model: str, url: str, timeout: int) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False, "format": "json"}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec - local user-configured URL
            data = json.loads(resp.read().decode("utf-8"))
        text = data.get("response") or ""
        return parse_json_response(text), None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        return None, str(exc)


def parse_json_response(text: str) -> Dict[str, Any]:
    text = text.strip()
    if not text:
        raise ValueError("empty model response")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


def supporting_phrases(ocr_text: str) -> List[str]:
    if not ocr_text:
        return []
    # pick phrase-like lines from OCR; conservative and short.
    lines = [re.sub(r"\s+", " ", line).strip() for line in ocr_text.splitlines()]
    lines = [line for line in lines if 8 <= len(line) <= 120]
    seen = []
    for line in lines:
        if line.lower() not in {s.lower() for s in seen}:
            seen.append(line)
        if len(seen) >= 5:
            break
    if not seen:
        words = clean_text(ocr_text, 300).split()
        if words:
            seen = [" ".join(words[:16])]
    return seen[:5]


def infer_subrole(role: str, topics: List[str], summary: str, ocr_text: str) -> str:
    blob = " ".join([role or "", summary or "", " ".join(topics), ocr_text[:1000]]).lower()
    if "vendor" in blob:
        return "vendor_list"
    if "numerical" in blob:
        return "numerical_index"
    if "effective page" in blob or "revision" in blob:
        return "effective_pages_or_revision_history"
    if "applicability" in blob:
        return "applicability_parts_list"
    if "passenger seat" in blob or "armrest" in blob or "backrest" in blob:
        return "passenger_seat_components"
    if "figure" in blob or "illustration" in blob:
        return "illustration_or_figure"
    return role or "unknown"


def build_fallback_card(ctx: Dict[str, Any], ocr_text: str, prev_ctx: Optional[Dict[str, Any]], next_ctx: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    page_id = str(ctx.get("page_id"))
    role = clean_text(ctx.get("role") or "unknown", 80) or "unknown"
    confidence = clean_text(ctx.get("confidence") or ("low" if not ocr_text else "medium"), 20)
    topics = extract_topics(ctx)
    parts = extract_parts(ctx)
    summary = clean_text(ctx.get("summary") or ctx.get("short_summary") or ctx.get("retrieval_summary") or "", 500)
    if not summary:
        summary = f"Page {page_id} has {'empty OCR text' if not ocr_text else 'OCR text available for retrieval guidance'}."
    subrole = infer_subrole(role, topics, summary, ocr_text)

    cues: List[str] = []
    for item in topics + ROLE_CUE_MAP.get(role, []):
        if item and item.lower() not in {c.lower() for c in cues}:
            cues.append(item)
    blob = f"{summary} {ocr_text[:3000]}".lower()
    for term in COMPONENT_TERMS:
        if term in blob and term.lower() not in {c.lower() for c in cues}:
            cues.append(term)
    for part in parts[:12]:
        if part and part.lower() not in {c.lower() for c in cues}:
            cues.append(part)
    if not cues and role:
        cues.append(role.replace("_", " "))

    families = [term for term in COMPONENT_TERMS if term in blob][:10]
    if not families and "part" in role:
        families = ["parts list"]
    questions = []
    if role == "blank" or not ocr_text:
        questions = []
        not_good = ["answering content questions", "proving part claims", "describing procedures"]
    else:
        topic_phrase = cues[0] if cues else role.replace("_", " ")
        questions = [
            f"Which page discusses {topic_phrase}?",
            f"What source page should be checked for {topic_phrase}?",
            "Which source-backed page can support this manual topic?",
        ]
        not_good = ["uncited final answers", "canonical source truth by itself"]

    return enforce_card_schema({
        "page_id": page_id,
        "role": role,
        "subrole": subrole,
        "confidence": confidence if confidence in {"high", "medium", "low"} else "medium",
        "short_summary": summary,
        "retrieval_summary": f"Use this page as a retrieval helper for queries about {', '.join(cues[:8])}." if cues else summary,
        "answerable_questions": questions[:6],
        "retrieval_cues": cues[:30],
        "important_entities": (families + parts)[:25],
        "component_families": families[:12],
        "supporting_ocr_phrases": supporting_phrases(ocr_text),
        "nearby_context": {
            "previous": describe_neighbor(prev_ctx),
            "next": describe_neighbor(next_ctx),
        },
        "not_good_for": not_good,
        "authority": dict(AUTHORITY),
    }, ctx)


def describe_neighbor(ctx: Optional[Dict[str, Any]]) -> str:
    if not ctx:
        return "none"
    return clean_text(f"{ctx.get('page_id')} role={ctx.get('role')} summary={ctx.get('summary') or ctx.get('short_summary') or ''}", 240)


def enforce_card_schema(card: Dict[str, Any], original_ctx: Dict[str, Any]) -> Dict[str, Any]:
    page_id = str(original_ctx.get("page_id") or card.get("page_id") or "")
    role = clean_text(card.get("role") or original_ctx.get("role") or "unknown", 80) or "unknown"
    confidence = clean_text(card.get("confidence") or original_ctx.get("confidence") or "medium", 20).lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "medium"
    authority = dict(AUTHORITY)
    # Hard override unsafe authority fields even if model tried otherwise.
    out = {
        "page_id": page_id,
        "role": role,
        "subrole": clean_text(card.get("subrole") or infer_subrole(role, extract_topics(original_ctx), clean_text(card.get("short_summary"), 500), ""), 120),
        "confidence": confidence,
        "short_summary": clean_text(card.get("short_summary") or card.get("summary") or original_ctx.get("summary") or "", 700),
        "retrieval_summary": clean_text(card.get("retrieval_summary") or card.get("short_summary") or original_ctx.get("summary") or "", 1000),
        "answerable_questions": [clean_text(x, 220) for x in as_list(card.get("answerable_questions")) if clean_text(x, 220)][:8],
        "retrieval_cues": unique_clean_list(card.get("retrieval_cues"), 60, 40),
        "important_entities": unique_clean_list(card.get("important_entities"), 80, 40),
        "component_families": unique_clean_list(card.get("component_families"), 80, 20),
        "supporting_ocr_phrases": unique_clean_list(card.get("supporting_ocr_phrases"), 160, 8),
        "nearby_context": card.get("nearby_context") if isinstance(card.get("nearby_context"), dict) else {"previous": "none", "next": "none"},
        "not_good_for": unique_clean_list(card.get("not_good_for"), 160, 12),
        "authority": authority,
        "context_version": "page_context_v2",
        "created_at": now_iso(),
    }
    if not out["short_summary"]:
        out["short_summary"] = f"Page {page_id} has derived retrieval context."
    if not out["retrieval_summary"]:
        out["retrieval_summary"] = out["short_summary"]
    return out


def unique_clean_list(value: Any, max_len: int, max_items: int) -> List[str]:
    out: List[str] = []
    for item in as_list(value):
        if isinstance(item, dict):
            val = item.get("label") or item.get("name") or item.get("value") or item.get("text") or item.get("part_number")
        else:
            val = item
        val = clean_text(val, max_len)
        if val and val.lower() not in {x.lower() for x in out}:
            out.append(val)
        if len(out) >= max_items:
            break
    return out


def generate_contexts_v2(
    context_file: Path = DEFAULT_CONTEXT_FILE,
    output_json: Path = DEFAULT_OUTPUT_JSON,
    output_jsonl: Path = DEFAULT_OUTPUT_JSONL,
    database_url: Optional[str] = None,
    provider: str = "heuristic",
    model: str = "gemma3:12B",
    ollama_url: str = "http://localhost:11434/api/generate",
    limit: Optional[int] = None,
    force: bool = False,
    missing_only: bool = False,
    progress: bool = False,
    max_ocr_chars: int = 6000,
    timeout: int = 240,
) -> Dict[str, Any]:
    raw = read_json(context_file, {})
    contexts = normalize_contexts(raw)
    if limit:
        selected = contexts[:limit]
    else:
        selected = contexts

    existing_raw = read_json(output_json, {}) if output_json.exists() and not force else {}
    existing = {r.get("page_id"): r for r in normalize_contexts(existing_raw)}
    ocr_map = load_ocr_from_postgres(database_url, max_chars=max_ocr_chars)

    all_by_page = {ctx.get("page_id"): ctx for ctx in contexts}
    ordered_pages = [ctx.get("page_id") for ctx in contexts]
    records = dict(existing)
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    generated = 0
    skipped = 0
    llm_used = 0
    start_all = time.time()

    for idx, ctx in enumerate(selected, start=1):
        page_id = str(ctx.get("page_id"))
        if missing_only and page_id in existing:
            skipped += 1
            if progress:
                print(f"[{idx}/{len(selected)}] skipped existing page={page_id}")
            continue
        if page_id in existing and not force:
            records[page_id] = existing[page_id]
            skipped += 1
            if progress:
                print(f"[{idx}/{len(selected)}] cached page={page_id} role={existing[page_id].get('role')} cues={len(existing[page_id].get('retrieval_cues') or [])}")
            continue

        page_i = ordered_pages.index(page_id) if page_id in ordered_pages else -1
        prev_ctx = all_by_page.get(ordered_pages[page_i - 1]) if page_i > 0 else None
        next_ctx = all_by_page.get(ordered_pages[page_i + 1]) if 0 <= page_i < len(ordered_pages) - 1 else None
        ocr_text = ocr_map.get(page_id, "") or clean_text(ctx.get("ocr_text") or ctx.get("text") or "", max_ocr_chars)

        card: Optional[Dict[str, Any]] = None
        err: Optional[str] = None
        if provider.lower() in {"ollama", "llm", "gemma"}:
            prompt = make_prompt(ctx, ocr_text, prev_ctx, next_ctx)
            model_card, err = call_ollama(prompt, model=model, url=ollama_url, timeout=timeout)
            if model_card:
                card = enforce_card_schema(model_card, ctx)
                llm_used += 1
        if card is None:
            card = build_fallback_card(ctx, ocr_text, prev_ctx, next_ctx)
            if err:
                warnings.append({"page_id": page_id, "warning": "llm_failed_used_fallback", "detail": err[:300]})

        if not card.get("retrieval_cues") and card.get("role") != "blank":
            warnings.append({"page_id": page_id, "warning": "missing_retrieval_cues"})
        if card.get("authority", {}).get("can_answer_directly"):
            errors.append({"page_id": page_id, "error": "context_can_answer_directly"})
        if card.get("authority", {}).get("canonical_source_truth"):
            errors.append({"page_id": page_id, "error": "context_canonical_source_truth"})
        records[page_id] = card
        generated += 1
        if progress:
            elapsed = time.time() - start_all
            print(f"[{idx}/{len(selected)}] generated page={page_id} role={card.get('role')} subrole={card.get('subrole')} cues={len(card.get('retrieval_cues') or [])} elapsed={elapsed:.1f}s")

    final_records = [records[p] for p in sorted(records, key=page_num) if p]
    output_payload = {
        "status": "OK" if not errors else "NEEDS_ATTENTION",
        "version": "trace_net_page_context_v2",
        "source_context_file": str(context_file),
        "provider": provider,
        "model": model,
        "created_at": now_iso(),
        "contexts": final_records,
    }
    write_json(output_json, output_payload)
    write_jsonl(output_jsonl, final_records)

    summary = summarize_records(final_records)
    summary.update({
        "status": output_payload["status"],
        "version": "trace_net_page_context_v2",
        "source_context_file": str(context_file),
        "output_json": str(output_json),
        "output_jsonl": str(output_jsonl),
        "provider": provider,
        "model": model,
        "selected_records": len(selected),
        "generated_records": generated,
        "skipped_existing_records": skipped,
        "llm_used_records": llm_used,
        "warning_records": len(warnings),
        "error_records": len(errors),
        "warnings": warnings[:50],
        "errors": errors[:50],
        "elapsed_seconds": round(time.time() - start_all, 3),
    })
    write_json(DEFAULT_SUMMARY, summary)
    write_report(DEFAULT_REPORT, summary, final_records[:60])
    return summary


def summarize_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    def count_if(fn) -> int:
        return sum(1 for r in records if fn(r))
    role_counts: Dict[str, int] = {}
    for r in records:
        role_counts[r.get("role", "unknown")] = role_counts.get(r.get("role", "unknown"), 0) + 1
    return {
        "context_records": len(records),
        "contexts_with_retrieval_cues": count_if(lambda r: bool(r.get("retrieval_cues"))),
        "contexts_with_answerable_questions": count_if(lambda r: bool(r.get("answerable_questions"))),
        "contexts_with_supporting_ocr_phrases": count_if(lambda r: bool(r.get("supporting_ocr_phrases"))),
        "blank_context_records": count_if(lambda r: r.get("role") == "blank"),
        "direct_answer_context_records": count_if(lambda r: bool(r.get("authority", {}).get("can_answer_directly"))),
        "canonical_source_truth_context_records": count_if(lambda r: bool(r.get("authority", {}).get("canonical_source_truth"))),
        "source_truth_mutation_records": count_if(lambda r: bool(r.get("authority", {}).get("source_truth_mutation_allowed"))),
        "role_counts": role_counts,
    }


def write_report(path: Path, summary: Dict[str, Any], samples: List[Dict[str, Any]]) -> None:
    rows = []
    for r in samples:
        rows.append(
            "<tr>"
            f"<td>{html_escape(r.get('page_id'))}</td>"
            f"<td>{html_escape(r.get('role'))}</td>"
            f"<td>{html_escape(r.get('subrole'))}</td>"
            f"<td>{html_escape(', '.join(r.get('retrieval_cues') or []))}</td>"
            f"<td>{html_escape(r.get('retrieval_summary'))}</td>"
            "</tr>"
        )
    html = f"""<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Page Context v2</title>
<style>body{{font-family:Arial,sans-serif;margin:24px;line-height:1.35}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:6px;vertical-align:top}}pre{{background:#f6f8fa;padding:12px;overflow:auto}}</style></head><body>
<h1>TRACE-Net Page Context v2</h1>
<p>Status: <b>{html_escape(summary.get('status'))}</b> Version: <code>{html_escape(summary.get('version'))}</code></p>
<h2>Summary</h2><pre>{html_escape(json.dumps({k:v for k,v in summary.items() if k not in {'warnings','errors'}}, indent=2, ensure_ascii=False))}</pre>
<h2>Sample context cards</h2><table><tr><th>Page</th><th>Role</th><th>Subrole</th><th>Retrieval cues</th><th>Retrieval summary</th></tr>{''.join(rows)}</table>
</body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def html_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate TRACE-Net Page Context v2 retrieval guidance cards.")
    parser.add_argument("--context-file", default=str(DEFAULT_CONTEXT_FILE))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-jsonl", default=str(DEFAULT_OUTPUT_JSONL))
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--provider", choices=["heuristic", "ollama"], default="heuristic")
    parser.add_argument("--model", default="gemma3:12B")
    parser.add_argument("--ollama-url", default="http://localhost:11434/api/generate")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--missing-only", action="store_true")
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--max-ocr-chars", type=int, default=6000)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args(argv)

    summary = generate_contexts_v2(
        context_file=Path(args.context_file),
        output_json=Path(args.output_json),
        output_jsonl=Path(args.output_jsonl),
        database_url=args.database_url,
        provider=args.provider,
        model=args.model,
        ollama_url=args.ollama_url,
        limit=args.limit,
        force=args.force,
        missing_only=args.missing_only,
        progress=args.progress,
        max_ocr_chars=args.max_ocr_chars,
        timeout=args.timeout,
    )

    print("TRACE-Net Page Context v2")
    print(f"  Status: {summary.get('status')}")
    print(f"  Provider: {summary.get('provider')}")
    print(f"  Model: {summary.get('model')}")
    print(f"  Context records: {summary.get('context_records')}")
    print(f"  With retrieval cues: {summary.get('contexts_with_retrieval_cues')}")
    print(f"  With answerable questions: {summary.get('contexts_with_answerable_questions')}")
    print(f"  Direct-answer contexts: {summary.get('direct_answer_context_records')}")
    print(f"  Canonical source truth contexts: {summary.get('canonical_source_truth_context_records')}")
    print("Files written:")
    print(f"  json: {DEFAULT_OUTPUT_JSON}")
    print(f"  jsonl: {DEFAULT_OUTPUT_JSONL}")
    print(f"  summary: {DEFAULT_SUMMARY}")
    print(f"  report_html: {DEFAULT_REPORT}")

    if args.open:
        import webbrowser
        webbrowser.open(DEFAULT_REPORT.resolve().as_uri())
    return 0 if summary.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
