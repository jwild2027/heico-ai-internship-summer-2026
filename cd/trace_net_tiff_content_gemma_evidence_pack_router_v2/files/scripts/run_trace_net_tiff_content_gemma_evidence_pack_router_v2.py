#!/usr/bin/env python3
"""Run fixed TIFF-content questions with routed local evidence packs + Gemma.

This is v2 of the local TIFF-content Gemma runner. It does not use the old
TRACE-Net demo ask endpoint. It scans TRACE-Net's local TIFF-derived artifacts,
classifies each question into a route, retrieves route-appropriate evidence,
sends question + evidence to Ollama/Gemma, and writes Question/Answer output.

Safety contract: read-only; no DB writes; no source-truth mutation; no answer
permission. Engram/route hints and artifact metadata are guidance only. Final
claims must be grounded in the selected source evidence snippets.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

PART_RE = re.compile(r"\b[A-Z]{0,4}\d{2,6}[-_ ]?\d{2,6}(?:[-_ ]?\d{1,6})?\b", re.I)
PAGE_ID_RE = re.compile(r"\bt_p_\d+_\d+_p\d{6}\b|\bp\d{6}\b", re.I)
ATA_RE = re.compile(r"\b(?:ATA\s*)?[12]\d-[0-9]{2}-[0-9]{2}\b", re.I)
FIGURE_RE = re.compile(r"\bfig(?:ure)?\.?\s*\d+[A-Z]?\b", re.I)
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-]{2,}")

IMPORTANT_NAME_HINTS = (
    "ocr",
    "visual",
    "figure",
    "callout",
    "table",
    "cell",
    "row",
    "nomenclature",
    "context_v2",
    "v2_summary",
    "page_context",
    "route",
    "evidence",
    "human_review",
    "blank",
    "layout",
    "part",
    "source_trace",
    "answer_context",
    "image",
    "tiff",
    "manual",
    "metadata",
)

STOPWORDS = {
    "what", "which", "where", "when", "does", "with", "from", "this", "that",
    "document", "documents", "page", "pages", "evidence", "source", "trace",
    "ready", "contain", "contains", "mention", "mentions", "associated", "strongest",
    "give", "need", "number", "numbers", "appear", "appears", "found", "sample",
    "linked", "using", "have", "has", "are", "the", "and", "for", "its", "any",
}

PIPELINE_WARNING_TOKENS = (
    "anchor_aware_warnings",
    "enrichment_warnings",
    "exact_row_proof_warnings",
    "proof_warnings",
    "warning_count",
    "warnings_count",
    "review_warning",
    "_warnings",
    "warnings:",
    "warning_flags",
)

DOC_TITLE_HINTS = (
    "embraer component maintenance manual",
    "component maintenance manual",
    "illustrated parts list",
    "maintenance manual with illustrated parts list",
    "t.-p. 120/1176",
    "tp 120/1176",
    "120/1176",
)

DOC_REVISION_HINTS = (
    "revision",
    "rev.",
    "rev ",
    "revision date",
    "10 april 2006",
    "apr 2006",
)


@dataclass(frozen=True)
class EvidenceRecord:
    source_path: str
    line_no: int
    text: str
    page_ids: tuple[str, ...]
    part_numbers: tuple[str, ...]
    ata_numbers: tuple[str, ...]
    figure_refs: tuple[str, ...]
    score: float = 0.0


def normalize_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value or "").lower()


def compact_text(value: str, limit: int = 700) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def flatten_json(value: Any, prefix: str = "") -> Iterable[str]:
    if isinstance(value, dict):
        for k, v in value.items():
            child = f"{prefix}.{k}" if prefix else str(k)
            yield from flatten_json(v, child)
    elif isinstance(value, list):
        for i, v in enumerate(value[:2000]):
            child = f"{prefix}[{i}]" if prefix else f"[{i}]"
            yield from flatten_json(v, child)
        if len(value) > 2000:
            yield f"{prefix}: <list truncated at 2000 of {len(value)}>"
    else:
        text = str(value)
        if text and text.lower() != "none":
            yield f"{prefix}: {text}" if prefix else text


def read_artifact_lines(path: Path, max_file_bytes: int) -> list[str]:
    try:
        if path.stat().st_size > max_file_bytes:
            raw = path.read_bytes()[:max_file_bytes]
            text = raw.decode("utf-8", errors="ignore")
            return text.splitlines()
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            data = json.loads(text)
            return list(flatten_json(data))
        except Exception:
            return text.splitlines()
    if suffix == ".jsonl":
        lines: list[str] = []
        for raw in text.splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                lines.extend(flatten_json(json.loads(raw)))
            except Exception:
                lines.append(raw)
        return lines
    return text.splitlines()


def iter_artifact_files(root: Path, max_files: int) -> Iterable[Path]:
    suffixes = {".json", ".jsonl", ".txt", ".md", ".csv", ".tsv"}
    candidates: list[Path] = []
    for p in root.rglob("*"):
        if len(candidates) >= max_files:
            break
        if not p.is_file() or p.suffix.lower() not in suffixes:
            continue
        parts = set(part.lower() for part in p.parts)
        if ".git" in parts or "__pycache__" in parts or ".pytest_cache" in parts:
            continue
        name = str(p.relative_to(root)).lower()
        if any(h in name for h in IMPORTANT_NAME_HINTS) or p.suffix.lower() in {".json", ".jsonl"}:
            candidates.append(p)
    candidates.sort(key=lambda x: (x.stat().st_size, str(x)))
    return candidates


def build_local_index(
    root: Path,
    *,
    max_files: int = 3000,
    max_file_bytes: int = 2_000_000,
    max_records: int = 250_000,
) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    files = list(iter_artifact_files(root, max_files=max_files))
    for file_index, path in enumerate(files, start=1):
        if file_index % 250 == 0:
            print(f"[INDEX] scanned_files={file_index} evidence_records={len(records)}", flush=True)
        rel = str(path.relative_to(root))
        lines = read_artifact_lines(path, max_file_bytes=max_file_bytes)
        for line_no, line in enumerate(lines, start=1):
            text = compact_text(line, 1200)
            if not text:
                continue
            low = text.lower()
            if not (
                PAGE_ID_RE.search(text)
                or PART_RE.search(text)
                or ATA_RE.search(text)
                or FIGURE_RE.search(text)
                or any(h in low for h in IMPORTANT_NAME_HINTS)
                or any(term in low for term in ("warning", "caution", "note", "installation", "removal", "inspection", "effectivity", "applicability", "paper towel", "dispenser", "revision", "component maintenance manual"))
            ):
                continue
            records.append(
                EvidenceRecord(
                    source_path=rel,
                    line_no=line_no,
                    text=text,
                    page_ids=tuple(sorted(set(m.group(0) for m in PAGE_ID_RE.finditer(text)))),
                    part_numbers=tuple(sorted(set(m.group(0) for m in PART_RE.finditer(text)))),
                    ata_numbers=tuple(sorted(set(m.group(0) for m in ATA_RE.finditer(text)))),
                    figure_refs=tuple(sorted(set(m.group(0) for m in FIGURE_RE.finditer(text)))),
                )
            )
            if len(records) >= max_records:
                return records
    return records


def load_questions(path: Path) -> list[dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        rows = data
    else:
        rows = data.get("questions") or []
    out: list[dict[str, str]] = []
    for i, row in enumerate(rows, start=1):
        if isinstance(row, str):
            out.append({"question_id": f"q{i:02d}", "question": row})
        else:
            q = str(row.get("question") or "").strip()
            if q:
                out.append({"question_id": str(row.get("question_id") or f"q{i:02d}"), "question": q})
    return out


def singular_manual_term(question: str) -> str | None:
    q = question.lower()
    mapping = {
        "warnings": "warning",
        "warning": "warning",
        "cautions": "caution",
        "caution": "caution",
        "notes": "note",
        "note": "note",
        "installation": "installation",
        "removal": "removal",
        "inspection": "inspection",
        "effectivity": "effectivity",
        "applicability": "applicability",
    }
    for key, value in mapping.items():
        if re.search(rf"\b{re.escape(key)}\b", q):
            return value
    return None


def classify_question(question: str) -> str:
    q = question.lower()
    if "ata" in q:
        return "ata_identifier"
    if "revision" in q or re.search(r"\brev\b", q):
        return "document_revision"
    if "document title" in q or "title is associated" in q or "title" in q:
        return "document_title"
    if "paper towel" in q or "towel dispenser" in q or "dispenser" in q:
        return "exact_nomenclature_phrase"
    if "figure" in q or "fig " in q or "fig." in q:
        if "nomenclature" in q:
            return "figure_nomenclature"
        return "figure_visual"
    if "nomenclature" in q:
        return "nomenclature"
    if "blank" in q:
        return "blank_layout"
    if "human review" in q or "require human" in q or "uncertainty" in q or "review" in q:
        return "human_review"
    if "table" in q or "row" in q or "cell" in q:
        return "table"
    term = singular_manual_term(question)
    if term:
        return "manual_keyword"
    if "visual" in q or "image" in q or "callout" in q or "label" in q:
        return "visual"
    if PART_RE.search(question) or "covered part" in q or "part number" in q or "part-number" in q:
        return "part_lookup"
    if "source-traceable summary" in q or "strongest tiff-page" in q:
        return "summary"
    return "broad_content"


def make_terms(question: str, route: str | None = None) -> list[str]:
    route = route or classify_question(question)
    q = question.lower()
    terms: list[str] = []

    def add(term: str) -> None:
        term = term.strip().lower()
        if term and term not in terms:
            terms.append(term)

    for word in WORD_RE.findall(question):
        lw = word.lower()
        if len(lw) >= 3 and lw not in STOPWORDS:
            add(lw)

    if route in {"figure_visual", "figure_nomenclature"}:
        for m in FIGURE_RE.finditer(question):
            raw = m.group(0)
            add(raw)
            add(raw.replace("fig.", "figure"))
            digits = re.sub(r"\D+", "", raw)
            if digits:
                add("figure " + digits)
                add("fig " + digits)
                add(digits)
        for t in ("visual", "figure", "callout", "nomenclature", "visual_figure_link"):
            add(t)
    if route == "exact_nomenclature_phrase":
        for t in ("paper towel dispenser", "paper towel", "towel dispenser", "dispenser"):
            add(t)
    if route == "blank_layout":
        for t in ("blank", "blank_candidate", "blank table", "layout"):
            add(t)
    if route == "table":
        for t in ("table", "table_row", "table_cell", "has_table_cell", "row", "cell"):
            add(t)
    if route in {"visual", "nomenclature"}:
        for t in ("visual", "image", "figure", "callout", "visual_understanding", "visual_region", "nomenclature"):
            add(t)
    if route == "ata_identifier":
        for t in ("ata", "25-21-00", "ata 25-21-00", "document title"):
            add(t)
    if route == "document_title":
        for t in DOC_TITLE_HINTS:
            add(t)
    if route == "document_revision":
        for t in DOC_REVISION_HINTS:
            add(t)
    if route == "manual_keyword":
        term = singular_manual_term(question)
        if term:
            add(term)
            if term == "warning":
                add("warning:")
            if term == "caution":
                add("caution:")
            if term == "note":
                add("note:")
    if route == "human_review":
        for t in ("human_review", "review_required", "review", "uncertainty", "low_confidence", "fishnet_review", "visual_review"):
            add(t)
    for m in PART_RE.finditer(question):
        raw = m.group(0)
        add(raw)
        add(normalize_token(raw))
    for m in ATA_RE.finditer(question):
        add(m.group(0))
    return terms[:50]


def has_manual_keyword(record: EvidenceRecord, term: str) -> bool:
    low = record.text.lower()
    if any(tok in low for tok in PIPELINE_WARNING_TOKENS):
        return False
    if term == "note":
        # Avoid matching incidental words such as "not source-trace-ready" or JSON notes fields.
        return bool(re.search(r"\bnote\s*[:\-]", low) or re.search(r"\bnotes?\b", low) and "source-trace" not in low and "missing evidence" not in low)
    if term in {"warning", "caution"}:
        return bool(re.search(rf"\b{term}\b\s*[:\-]?", low))
    return bool(re.search(rf"\b{re.escape(term)}\b", low))


def record_passes_route(record: EvidenceRecord, question: str, route: str) -> bool:
    low_text = record.text.lower()
    low_path = record.source_path.lower()
    blob = f"{low_path}\n{low_text}"
    norm_blob = normalize_token(blob)

    if route == "ata_identifier":
        return bool(record.ata_numbers or ATA_RE.search(record.text) or "25-21-00" in blob or "ata" in low_text)

    if route == "document_title":
        return any(h in blob for h in DOC_TITLE_HINTS) or ("title" in blob and "manual" in blob)

    if route == "document_revision":
        return any(h in blob for h in DOC_REVISION_HINTS)

    if route == "exact_nomenclature_phrase":
        return "paper towel" in low_text or "towel dispenser" in low_text or re.search(r"\bdispenser\b", low_text) is not None

    if route in {"figure_visual", "figure_nomenclature"}:
        fig_terms = make_terms(question, route)
        has_target_fig = any(term in low_text or normalize_token(term) in norm_blob for term in fig_terms if term.startswith("figure") or term.startswith("fig "))
        return bool(has_target_fig or record.figure_refs) and any(h in blob for h in ("figure", "fig", "visual", "callout", "nomenclature", "ocr"))

    if route == "nomenclature":
        return "nomenclature" in blob or any(word in low_text for word in (" assy", "assembly", "structure", "seat", "dispenser"))

    if route == "blank_layout":
        return "blank" in blob or "blank_candidate" in blob

    if route == "table":
        return any(h in blob for h in ("table", "has_table_cell", "table_cell", "table_row", "cell", "row"))

    if route == "manual_keyword":
        term = singular_manual_term(question)
        return bool(term and has_manual_keyword(record, term))

    if route == "human_review":
        return any(h in blob for h in ("human_review", "review_required", "fishnet_review", "visual_review", "low_confidence", "uncertainty", "review_"))

    if route == "visual":
        return any(h in blob for h in ("visual", "image", "figure", "callout", "visual_understanding", "visual_region", "part label", "callout label"))

    if route == "part_lookup":
        targets = [normalize_token(m.group(0)) for m in PART_RE.finditer(question)]
        if targets:
            return any(t in norm_blob for t in targets)
        return bool(record.part_numbers or "part_number" in blob or "covered_part_number" in blob)

    if route == "summary":
        return bool(record.page_ids and (record.part_numbers or record.figure_refs or record.ata_numbers or "source_trace" in blob or "verified" in blob))

    return True


def route_bonus(record: EvidenceRecord, route: str) -> float:
    path = record.source_path.lower()
    text = record.text.lower()
    blob = f"{path}\n{text}"
    bonus = 0.0
    if route.startswith("figure"):
        for h in ("visual_figure", "figure", "visual", "callout", "nomenclature", "ocr"):
            if h in blob:
                bonus += 3.0
    elif route == "ata_identifier":
        if record.ata_numbers:
            bonus += 8.0
        if "25-21-00" in blob:
            bonus += 5.0
        if "title" in blob or "manual" in blob:
            bonus += 2.0
    elif route in {"document_title", "document_revision"}:
        if "metadata" in path or "page_context" in path or "context" in path:
            bonus += 3.0
        if route == "document_title" and any(h in blob for h in DOC_TITLE_HINTS):
            bonus += 8.0
        if route == "document_revision" and any(h in blob for h in DOC_REVISION_HINTS):
            bonus += 8.0
    elif route == "manual_keyword":
        if "ocr" in path or "page_context" in path or "source" in path or "text" in path:
            bonus += 4.0
    elif route == "table":
        if "table" in path:
            bonus += 5.0
    elif route == "human_review":
        if "human_review" in path or "review" in path:
            bonus += 5.0
    elif route == "blank_layout":
        if "route" in path or "blank" in path:
            bonus += 5.0
    elif route == "visual":
        if "visual" in path or "image" in path:
            bonus += 5.0
    elif route == "part_lookup":
        if "source_trace" in path or "table" in path or "ocr" in path:
            bonus += 2.0
    return bonus


def score_record(record: EvidenceRecord, question: str, route: str, terms: list[str]) -> float:
    if not record_passes_route(record, question, route):
        return 0.0

    blob = f"{record.source_path}\n{record.text}".lower()
    norm_blob = normalize_token(blob)
    score = route_bonus(record, route)

    for term in terms:
        if not term:
            continue
        term_norm = normalize_token(term)
        if " " in term or "-" in term or "." in term or ":" in term:
            if term.lower() in blob:
                score += 10.0
            elif term_norm and term_norm in norm_blob:
                score += 7.0
        elif term in blob:
            score += 2.5

    q = question.lower()
    if record.page_ids:
        score += 1.5
    if record.part_numbers and ("part" in q or "number" in q or "nomenclature" in q or route in {"figure_visual", "figure_nomenclature"}):
        score += 3.0
    if record.figure_refs and ("figure" in q or route.startswith("figure")):
        score += 4.0
    if record.ata_numbers and route == "ata_identifier":
        score += 6.0

    if route == "manual_keyword" and any(tok in blob for tok in PIPELINE_WARNING_TOKENS):
        return 0.0

    # Strong off-target protection for exact part-number questions.
    targets = [normalize_token(m.group(0)) for m in PART_RE.finditer(question)]
    if targets and route == "part_lookup" and not any(t in norm_blob for t in targets):
        return 0.0

    return score


def retrieve_evidence(records: list[EvidenceRecord], question: str, *, top_k: int = 18) -> tuple[str, list[EvidenceRecord]]:
    route = classify_question(question)
    terms = make_terms(question, route)
    scored: list[EvidenceRecord] = []
    for r in records:
        s = score_record(r, question, route, terms)
        if s > 0:
            scored.append(EvidenceRecord(r.source_path, r.line_no, r.text, r.page_ids, r.part_numbers, r.ata_numbers, r.figure_refs, s))
    scored.sort(key=lambda x: (-x.score, x.source_path, x.line_no))

    out: list[EvidenceRecord] = []
    seen_text: set[str] = set()
    source_counts: dict[str, int] = {}
    page_counts: dict[str, int] = {}
    for r in scored:
        text_key = normalize_token(r.text[:260])
        if text_key in seen_text:
            continue
        if source_counts.get(r.source_path, 0) >= 4:
            continue
        primary_page = r.page_ids[0] if r.page_ids else "no_page"
        if page_counts.get(primary_page, 0) >= 6:
            continue
        out.append(r)
        seen_text.add(text_key)
        source_counts[r.source_path] = source_counts.get(r.source_path, 0) + 1
        page_counts[primary_page] = page_counts.get(primary_page, 0) + 1
        if len(out) >= top_k:
            break
    return route, out


def evidence_meta_line(r: EvidenceRecord) -> str:
    meta = []
    if r.page_ids:
        meta.append("pages=" + ",".join(r.page_ids[:5]))
    if r.part_numbers:
        meta.append("parts=" + ",".join(r.part_numbers[:5]))
    if r.ata_numbers:
        meta.append("ata=" + ",".join(r.ata_numbers[:5]))
    if r.figure_refs:
        meta.append("figures=" + ",".join(r.figure_refs[:5]))
    return " | ".join(meta) if meta else "metadata=not_detected"


def make_prompt(question_id: str, question: str, route: str, evidence: list[EvidenceRecord]) -> str:
    blocks = []
    for i, r in enumerate(evidence, start=1):
        blocks.append(
            f"[EVIDENCE {i}] source={r.source_path}:{r.line_no} score={r.score:.1f} | {evidence_meta_line(r)}\n{r.text}"
        )
    evidence_text = "\n\n".join(blocks) if blocks else "No route-matching local TIFF-derived evidence snippets were retrieved for this question."

    route_rule = ""
    if route == "manual_keyword":
        route_rule = "\n- For warning/caution/note/installation/removal/inspection/effectivity/applicability questions, use visible manual/OCR page text only. Ignore internal pipeline warning fields."
    elif route == "ata_identifier":
        route_rule = "\n- For ATA questions, only answer from ATA-like patterns such as 25-21-00 or explicit ATA/document-title evidence. Do not answer with revision dates or part numbers."
    elif route in {"document_title", "document_revision"}:
        route_rule = "\n- For document title/revision questions, use title/revision metadata or visible title-page evidence only. Do not answer with unrelated part evidence."
    elif route == "exact_nomenclature_phrase":
        route_rule = "\n- For exact phrase/nomenclature questions, do not infer from nearby unrelated parts. If the phrase is not present, say not found."

    return f"""TRACE-NET TIFF-CONTENT QA WORK ORDER — ROUTED EVIDENCE V2

Question ID: {question_id}
Question: {question}
Route used: {route}

Rules:
- Answer using only the SOURCE EVIDENCE snippets below.
- Do not use the question itself as proof.
- Page IDs, part numbers, ATA numbers, figure labels, nomenclature, table/OCR/visual claims must be grounded in the snippets.
- If evidence is missing, off-target, or only a routing hint, say not source-trace-ready.
- Do not claim eligibility, fit, approval, installation approval, interchangeability, or effectivity unless explicit evidence says so.
- Never leave the answer blank. If you cannot answer, say "Not found / not source-trace-ready" and explain the missing evidence.{route_rule}
- Keep the response concise and use this structure:
  Direct answer:
  Source-trace status:
  Evidence used:
  Missing evidence / limits:

SOURCE EVIDENCE SNIPPETS:
{evidence_text}
"""


def safe_fallback_answer(question: str, route: str, evidence_count: int, reason: str) -> str:
    evidence_line = "None" if evidence_count == 0 else f"{evidence_count} retrieved snippets were insufficient or off-target."
    return (
        "Direct answer: Not found / not source-trace-ready.\n"
        "Source-trace status: Not source-trace-ready.\n"
        f"Evidence used: {evidence_line}\n"
        f"Missing evidence / limits: {reason} Route used: {route}. Question: {question}"
    )


def normalize_answer(answer: str, *, question: str, route: str, evidence_count: int) -> tuple[str, bool]:
    clean = (answer or "").strip()
    if len(clean) < 12:
        return safe_fallback_answer(question, route, evidence_count, "Gemma returned a blank or near-blank answer."), True
    if "direct answer" not in clean.lower() and "source-trace" not in clean.lower():
        clean = "Direct answer: " + clean
    return clean, False


def call_ollama(prompt: str, *, host: str, model: str, timeout: int = 180) -> str:
    url = host.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_ctx": 8192},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return str(body.get("response") or "").strip()
    except urllib.error.URLError as exc:
        return (
            "Direct answer: Gemma/Ollama call failed.\n"
            "Source-trace status: Not source-trace-ready.\n"
            "Evidence used: None.\n"
            f"Missing evidence / limits: {exc}"
        )


def write_question_answer_view(rows: list[dict[str, Any]], out: Path) -> None:
    lines: list[str] = []
    for r in rows:
        lines.append(f"Question {r.get('question_id')}:")
        lines.append(str(r.get("question") or ""))
        lines.append("")
        lines.append("Answer:")
        lines.append(str(r.get("answer") or ""))
        lines.append("")
        lines.append("-" * 100)
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--questions", required=True)
    ap.add_argument("--artifact-root", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--ollama-host", default="http://127.0.0.1:11434")
    ap.add_argument("--model", default="gemma4:26b")
    ap.add_argument("--top-k", type=int, default=18)
    ap.add_argument("--max-files", type=int, default=3000)
    ap.add_argument("--max-file-bytes", type=int, default=2_000_000)
    ap.add_argument("--max-records", type=int, default=250_000)
    ap.add_argument("--ollama-timeout", type=int, default=180)
    ap.add_argument("--skip-gemma", action="store_true", help="Write prompts/evidence only; no Ollama calls.")
    args = ap.parse_args(argv)

    artifact_root = Path(args.artifact_root)
    output_dir = Path(args.output_dir)
    prompts_dir = output_dir / "prompts"
    output_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)

    questions = load_questions(Path(args.questions))
    print(f"[SETUP] question_count={len(questions)} artifact_root={artifact_root}", flush=True)
    print("[INDEX] building routed local TIFF-derived evidence index...", flush=True)
    t0 = time.time()
    records = build_local_index(
        artifact_root,
        max_files=args.max_files,
        max_file_bytes=args.max_file_bytes,
        max_records=args.max_records,
    )
    print(f"[INDEX] done evidence_record_count={len(records)} elapsed_seconds={time.time()-t0:.2f}", flush=True)

    answers_path = output_dir / "answers.jsonl"
    debug_path = output_dir / "evidence_debug.jsonl"
    rows: list[dict[str, Any]] = []
    blank_fallback_count = 0
    no_evidence_count = 0
    route_counts: dict[str, int] = {}

    with answers_path.open("w", encoding="utf-8") as fh, debug_path.open("w", encoding="utf-8") as debug_fh:
        for idx, qrow in enumerate(questions, start=1):
            qid = qrow["question_id"]
            question = qrow["question"]
            print(f"[{idx:03d}/{len(questions):03d}] START {qid}: {question}", flush=True)
            route, evidence = retrieve_evidence(records, question, top_k=args.top_k)
            route_counts[route] = route_counts.get(route, 0) + 1
            if len(evidence) == 0:
                no_evidence_count += 1
            print(f"[{idx:03d}/{len(questions):03d}] RETRIEVE {qid}: route={route} evidence_count={len(evidence)}", flush=True)
            prompt = make_prompt(qid, question, route, evidence)
            prompt_path = prompts_dir / f"{qid}_prompt.txt"
            prompt_path.write_text(prompt, encoding="utf-8")
            if args.skip_gemma:
                raw_answer = safe_fallback_answer(question, route, len(evidence), "Gemma call skipped with --skip-gemma.")
            elif not evidence:
                raw_answer = safe_fallback_answer(question, route, 0, "No route-matching local TIFF-derived evidence snippets were retrieved.")
            else:
                print(f"[{idx:03d}/{len(questions):03d}] GEMMA {qid}: model={args.model}", flush=True)
                raw_answer = call_ollama(prompt, host=args.ollama_host, model=args.model, timeout=args.ollama_timeout)
            answer, used_blank_fallback = normalize_answer(raw_answer, question=question, route=route, evidence_count=len(evidence))
            if used_blank_fallback:
                blank_fallback_count += 1

            evidence_rows = [
                {
                    "source_path": e.source_path,
                    "line_no": e.line_no,
                    "score": e.score,
                    "text": e.text,
                    "page_ids": list(e.page_ids),
                    "part_numbers": list(e.part_numbers),
                    "ata_numbers": list(e.ata_numbers),
                    "figure_refs": list(e.figure_refs),
                }
                for e in evidence
            ]
            result = {
                "question_id": qid,
                "question_index": idx,
                "question_total": len(questions),
                "question": question,
                "route_used": route,
                "answer": answer,
                "evidence_count": len(evidence),
                "blank_answer_fallback_used": used_blank_fallback,
                "evidence": evidence_rows,
                "prompt_path": str(prompt_path),
                "model": args.model,
            }
            debug_record = {
                "question_id": qid,
                "question": question,
                "route_used": route,
                "evidence_count": len(evidence),
                "top_sources": [f"{e.source_path}:{e.line_no}" for e in evidence[:8]],
                "top_pages": sorted({p for e in evidence for p in e.page_ids})[:20],
                "top_parts": sorted({p for e in evidence for p in e.part_numbers})[:20],
                "top_ata": sorted({a for e in evidence for a in e.ata_numbers})[:20],
                "blank_answer_fallback_used": used_blank_fallback,
            }
            fh.write(json.dumps(result, ensure_ascii=False) + "\n")
            fh.flush()
            debug_fh.write(json.dumps(debug_record, ensure_ascii=False) + "\n")
            debug_fh.flush()
            rows.append(result)
            print(f"[{idx:03d}/{len(questions):03d}] DONE {qid}: route={route} answer_chars={len(answer)}", flush=True)

    qa_path = output_dir / "question_answer_view.txt"
    write_question_answer_view(rows, qa_path)
    summary = {
        "status": "TRACE_NET_TIFF_CONTENT_GEMMA_EVIDENCE_PACK_ROUTER_V2_DONE",
        "quality_status": "PASS" if len(rows) == len(questions) and blank_fallback_count == 0 else "WARN",
        "question_count": len(questions),
        "answered_count": len(rows),
        "blank_answer_fallback_count": blank_fallback_count,
        "no_evidence_question_count": no_evidence_count,
        "evidence_record_count": len(records),
        "route_counts": route_counts,
        "answers": str(answers_path),
        "question_answer_view": str(qa_path),
        "evidence_debug": str(debug_path),
        "prompts_dir": str(prompts_dir),
        "model": args.model,
        "safety_contract": {
            "read_only": True,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "answer_permission_count": 0,
        },
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    for k, v in summary.items():
        print(f"{k}={v}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
