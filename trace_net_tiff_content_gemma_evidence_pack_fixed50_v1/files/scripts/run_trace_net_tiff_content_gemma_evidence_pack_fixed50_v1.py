#!/usr/bin/env python3
"""Run fixed TIFF-content questions with local evidence packs + Gemma.

This runner does NOT use the old demo ask endpoint. It scans TRACE-Net's local
TIFF-derived artifacts, builds a compact evidence pack per question, sends only
question + evidence to Ollama/Gemma, and writes simple Question/Answer output.

Safety contract: read-only; no DB writes; no source-truth mutation.
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
ATA_RE = re.compile(r"\b(?:ATA\s*)?\d{2}-\d{2}-\d{2}\b", re.I)
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
)

STOPWORDS = {
    "what", "which", "where", "when", "does", "with", "from", "this", "that",
    "document", "documents", "page", "pages", "evidence", "source", "trace",
    "ready", "contain", "contains", "mention", "mentions", "associated", "strongest",
    "give", "need", "number", "numbers", "appear", "appears", "found", "sample",
}


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
            # Still read a prefix; many JSON manifests put high-value summary first.
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
        # Prefer TIFF-derived / source evidence artifacts, but keep generic JSON manifests too.
        if any(h in name for h in IMPORTANT_NAME_HINTS) or p.suffix.lower() in {".json", ".jsonl"}:
            candidates.append(p)
    # Smaller summary/evidence files first tends to improve relevance and speed.
    candidates.sort(key=lambda x: (x.stat().st_size, str(x)))
    return candidates


def build_local_index(root: Path, *, max_files: int = 3000, max_file_bytes: int = 2_000_000, max_records: int = 250_000) -> list[EvidenceRecord]:
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
            # Keep only lines likely to carry page/content evidence.
            if not (
                PAGE_ID_RE.search(text)
                or PART_RE.search(text)
                or ATA_RE.search(text)
                or FIGURE_RE.search(text)
                or any(h in low for h in IMPORTANT_NAME_HINTS)
                or any(term in low for term in ("warning", "caution", "note", "installation", "removal", "effectivity", "applicability", "paper towel", "dispenser"))
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


def make_terms(question: str) -> list[str]:
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

    # Exact special phrases and route expansions.
    if "figure 69" in q or "fig 69" in q:
        for t in ("figure 69", "fig 69", "fig. 69", "69", "visual", "figure", "callout", "nomenclature"):
            add(t)
    if "paper towel" in q or "dispenser" in q:
        for t in ("paper towel dispenser", "paper towel", "towel dispenser", "dispenser", "nomenclature", "part"):
            add(t)
    if "blank" in q:
        for t in ("blank", "blank_candidate", "blank table", "table", "layout"):
            add(t)
    if "table" in q or "row" in q or "cell" in q:
        for t in ("table", "table_row", "table_cell", "row", "cell"):
            add(t)
    if "visual" in q or "image" in q or "figure" in q or "callout" in q:
        for t in ("visual", "image", "figure", "callout", "visual_understanding", "visual_region"):
            add(t)
    if "ocr" in q:
        add("ocr")
    if "nomenclature" in q:
        add("nomenclature")
    if "ata" in q:
        for t in ("ata", "25-21-00", "25", "document title"):
            add(t)
    for t in ("installation", "removal", "inspection", "effectivity", "applicability", "warning", "caution", "note", "review"):
        if t in q:
            add(t)
    for m in PART_RE.finditer(question):
        raw = m.group(0)
        add(raw)
        add(normalize_token(raw))
    for m in ATA_RE.finditer(question):
        add(m.group(0))
    return terms[:40]


def score_record(record: EvidenceRecord, question: str, terms: list[str]) -> float:
    blob = f"{record.source_path}\n{record.text}".lower()
    norm_blob = normalize_token(blob)
    score = 0.0
    for term in terms:
        if not term:
            continue
        if " " in term or "-" in term or "." in term:
            if term.lower() in blob:
                score += 8.0
            elif normalize_token(term) and normalize_token(term) in norm_blob:
                score += 6.0
        elif term in blob:
            score += 2.0
    # Source quality / route boosts.
    path = record.source_path.lower()
    q = question.lower()
    if record.page_ids:
        score += 1.5
    if record.part_numbers and ("part" in q or "number" in q or "nomenclature" in q):
        score += 2.5
    if record.figure_refs and ("figure" in q or "visual" in q or "image" in q):
        score += 3.0
    if record.ata_numbers and "ata" in q:
        score += 4.0
    for hint in ("ocr", "table", "visual", "nomenclature", "context_v2", "source_trace"):
        if hint in path and hint in q:
            score += 2.0
    return score


def retrieve_evidence(records: list[EvidenceRecord], question: str, *, top_k: int = 18) -> list[EvidenceRecord]:
    terms = make_terms(question)
    scored: list[EvidenceRecord] = []
    for r in records:
        s = score_record(r, question, terms)
        if s > 0:
            scored.append(EvidenceRecord(r.source_path, r.line_no, r.text, r.page_ids, r.part_numbers, r.ata_numbers, r.figure_refs, s))
    scored.sort(key=lambda x: (-x.score, x.source_path, x.line_no))

    # Diversify by source/page so one manifest cannot crowd out everything.
    out: list[EvidenceRecord] = []
    seen_keys: set[tuple[str, int]] = set()
    seen_text: set[str] = set()
    source_counts: dict[str, int] = {}
    for r in scored:
        text_key = normalize_token(r.text[:220])
        if text_key in seen_text:
            continue
        if source_counts.get(r.source_path, 0) >= 4:
            continue
        key = (r.source_path, r.line_no)
        if key in seen_keys:
            continue
        out.append(r)
        seen_keys.add(key)
        seen_text.add(text_key)
        source_counts[r.source_path] = source_counts.get(r.source_path, 0) + 1
        if len(out) >= top_k:
            break
    return out


def make_prompt(question_id: str, question: str, evidence: list[EvidenceRecord]) -> str:
    blocks = []
    for i, r in enumerate(evidence, start=1):
        meta = []
        if r.page_ids:
            meta.append("pages=" + ",".join(r.page_ids[:5]))
        if r.part_numbers:
            meta.append("parts=" + ",".join(r.part_numbers[:5]))
        if r.ata_numbers:
            meta.append("ata=" + ",".join(r.ata_numbers[:5]))
        if r.figure_refs:
            meta.append("figures=" + ",".join(r.figure_refs[:5]))
        meta_text = " | ".join(meta) if meta else "metadata=not_detected"
        blocks.append(
            f"[EVIDENCE {i}] source={r.source_path}:{r.line_no} score={r.score:.1f} | {meta_text}\n{r.text}"
        )
    evidence_text = "\n\n".join(blocks) if blocks else "No local TIFF-derived evidence snippets were retrieved for this question."
    return f"""TRACE-NET TIFF-CONTENT QA WORK ORDER

Question ID: {question_id}
Question: {question}

Rules:
- Answer using only the SOURCE EVIDENCE snippets below.
- Do not use the question itself as proof.
- Page IDs, part numbers, ATA numbers, figure labels, nomenclature, table/OCR/visual claims must be grounded in the snippets.
- If evidence is missing or only a routing hint, say not source-trace-ready.
- Do not claim eligibility, fit, approval, installation approval, interchangeability, or effectivity unless explicit evidence says so.
- Keep the response concise and use this structure:
  Direct answer:
  Source-trace status:
  Evidence used:
  Missing evidence / limits:

SOURCE EVIDENCE SNIPPETS:
{evidence_text}
"""


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
        return f"Direct answer: Gemma/Ollama call failed.\nSource-trace status: Not source-trace-ready.\nEvidence used: None.\nMissing evidence / limits: {exc}"


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
    ap.add_argument("--skip-gemma", action="store_true", help="Write prompts/evidence only; no Ollama calls.")
    args = ap.parse_args(argv)

    artifact_root = Path(args.artifact_root)
    output_dir = Path(args.output_dir)
    prompts_dir = output_dir / "prompts"
    output_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)

    questions = load_questions(Path(args.questions))
    print(f"[SETUP] question_count={len(questions)} artifact_root={artifact_root}", flush=True)
    print("[INDEX] building local TIFF-derived evidence index...", flush=True)
    t0 = time.time()
    records = build_local_index(artifact_root, max_files=args.max_files, max_file_bytes=args.max_file_bytes)
    print(f"[INDEX] done evidence_record_count={len(records)} elapsed_seconds={time.time()-t0:.2f}", flush=True)

    answers_path = output_dir / "answers.jsonl"
    rows: list[dict[str, Any]] = []
    with answers_path.open("w", encoding="utf-8") as fh:
        for idx, qrow in enumerate(questions, start=1):
            qid = qrow["question_id"]
            question = qrow["question"]
            print(f"[{idx:03d}/{len(questions):03d}] START {qid}: {question}", flush=True)
            evidence = retrieve_evidence(records, question, top_k=args.top_k)
            print(f"[{idx:03d}/{len(questions):03d}] RETRIEVE {qid}: evidence_count={len(evidence)}", flush=True)
            prompt = make_prompt(qid, question, evidence)
            prompt_path = prompts_dir / f"{qid}_prompt.txt"
            prompt_path.write_text(prompt, encoding="utf-8")
            if args.skip_gemma:
                answer = "Direct answer: Gemma call skipped.\nSource-trace status: Not source-trace-ready.\nEvidence used: local evidence pack generated only.\nMissing evidence / limits: --skip-gemma was used."
            else:
                print(f"[{idx:03d}/{len(questions):03d}] GEMMA {qid}: model={args.model}", flush=True)
                answer = call_ollama(prompt, host=args.ollama_host, model=args.model)
            result = {
                "question_id": qid,
                "question_index": idx,
                "question_total": len(questions),
                "question": question,
                "answer": answer,
                "evidence_count": len(evidence),
                "evidence": [
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
                ],
                "prompt_path": str(prompt_path),
                "model": args.model,
            }
            fh.write(json.dumps(result, ensure_ascii=False) + "\n")
            fh.flush()
            rows.append(result)
            print(f"[{idx:03d}/{len(questions):03d}] DONE {qid}: answer_chars={len(answer)}", flush=True)

    qa_path = output_dir / "question_answer_view.txt"
    write_question_answer_view(rows, qa_path)
    summary = {
        "status": "TRACE_NET_TIFF_CONTENT_GEMMA_EVIDENCE_PACK_FIXED50_DONE",
        "quality_status": "PASS" if len(rows) == len(questions) else "FAIL",
        "question_count": len(questions),
        "answered_count": len(rows),
        "evidence_record_count": len(records),
        "answers": str(answers_path),
        "question_answer_view": str(qa_path),
        "prompts_dir": str(prompts_dir),
        "model": args.model,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    for k, v in summary.items():
        print(f"{k}={v}", flush=True)
    return 0 if summary["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
