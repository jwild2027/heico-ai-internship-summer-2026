"""Model-comparison helpers for the local TIFF RAG system.

This module intentionally runs the existing ``scripts/operations/ingestion/ask_tiff_rag.py`` command
as a subprocess instead of importing deep RAG internals. That keeps model eval
stable while the retriever/answer code continues to evolve.
"""

from __future__ import annotations

import csv
import html
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class ModelEvalQuestion:
    id: str
    question: str
    answer_mode: str = "auto"
    retrieval_mode: str = "auto"
    top_k: int = 8
    expected_terms: tuple[str, ...] = ()
    expected_sources: tuple[str, ...] = ()
    notes: str = ""


@dataclass
class ModelEvalResult:
    question_id: str
    question: str
    model: str
    answer_mode: str
    retrieval_mode: str
    top_k: int
    status: str
    elapsed_seconds: float
    llm_used: bool | None
    embeddings_used: bool | None
    source_count: int
    missing_terms: list[str] = field(default_factory=list)
    missing_sources: list[str] = field(default_factory=list)
    return_code: int = 0
    answer: str = ""
    raw_output: str = ""
    stderr: str = ""


def default_model_eval_questions() -> list[ModelEvalQuestion]:
    """Return a broader pilot eval set for model comparison.

    These questions intentionally mix deterministic lookups and LLM summaries so
    that a model comparison report shows where the model was actually used and
    where code answered safely from structured catalog data.
    """

    return [
        ModelEvalQuestion(
            id="part_lookup_120_37313_001",
            question="What is part number 120-37313-001?",
            expected_terms=("120-37313-001", "HOLDER, MAGAZINE"),
            expected_sources=("Page 1056",),
        ),
        ModelEvalQuestion(
            id="part_lookup_120_36843_001",
            question="What is part number 120-36843-001?",
            expected_terms=("120-36843-001", "HOLDER, MAGAZINE"),
            expected_sources=("Page 1082",),
        ),
        ModelEvalQuestion(
            id="nomenclature_locate_magazine_holder",
            question="Where is magazine holder shown?",
            expected_terms=("120-36843-001", "120-37313-001", "120-37313-535"),
        ),
        ModelEvalQuestion(
            id="structured_summary_magazine_holder",
            question="Summarize the sources related to magazine holder parts.",
            answer_mode="summarize",
            retrieval_mode="hybrid",
            expected_terms=("120-36843-001", "120-37313-001", "120-37313-535", "HOLDER, MAGAZINE"),
        ),
        ModelEvalQuestion(
            id="compare_magazine_holder_parts",
            question="Compare the magazine holder part numbers.",
            answer_mode="compare",
            retrieval_mode="hybrid",
            expected_terms=("120-36843-001", "120-37313-001"),
        ),
        ModelEvalQuestion(
            id="part_lookup_am03078_22",
            question="What is part number AM03078-22?",
            expected_terms=("AM03078-22", "ASHTRAY"),
        ),
        ModelEvalQuestion(
            id="locate_am03078_22",
            question="Which pages mention AM03078-22?",
            expected_terms=("AM03078-22",),
        ),
        ModelEvalQuestion(
            id="summary_passenger_seat_back_crack_reinforcement",
            question="Which pages discuss passenger seat back crack reinforcement, and what do they say?",
            answer_mode="summarize",
            retrieval_mode="hybrid",
            top_k=12,
            expected_terms=("Page 621", "passenger seat back"),
            notes="LLM summary; usually needs manual review even when expected terms are present.",
        ),
        ModelEvalQuestion(
            id="summary_passenger_seat_back",
            question="Summarize the available source information about passenger seat back.",
            answer_mode="summarize",
            retrieval_mode="hybrid",
            top_k=12,
            expected_terms=("passenger", "seat", "back"),
            notes="Broad LLM summary; review source quality manually.",
        ),
        ModelEvalQuestion(
            id="ata_summary_25_21_00",
            question="Summarize the source evidence for ATA 25-21-00.",
            answer_mode="summarize",
            retrieval_mode="hybrid",
            top_k=12,
            expected_terms=("25-21-00",),
        ),
    ]


def load_questions(path: Path) -> list[ModelEvalQuestion]:
    data = json.loads(path.read_text(encoding="utf-8"))
    questions: list[ModelEvalQuestion] = []
    for row in data:
        questions.append(
            ModelEvalQuestion(
                id=str(row["id"]),
                question=str(row["question"]),
                answer_mode=str(row.get("answer_mode", "auto")),
                retrieval_mode=str(row.get("retrieval_mode", "auto")),
                top_k=int(row.get("top_k", 8)),
                expected_terms=tuple(str(x) for x in row.get("expected_terms", [])),
                expected_sources=tuple(str(x) for x in row.get("expected_sources", [])),
                notes=str(row.get("notes", "")),
            )
        )
    return questions


def write_questions(path: Path, questions: Sequence[ModelEvalQuestion]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for q in questions:
        row = asdict(q)
        row["expected_terms"] = list(q.expected_terms)
        row["expected_sources"] = list(q.expected_sources)
        rows.append(row)
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def _parse_bool_line(label: str, text: str) -> bool | None:
    match = re.search(rf"^{re.escape(label)}:\s*(True|False)\s*$", text, flags=re.MULTILINE)
    if not match:
        return None
    return match.group(1) == "True"


def parse_ask_tiff_rag_output(text: str) -> tuple[bool | None, bool | None, str, int]:
    """Parse the standard ask_tiff_rag.py text output."""

    llm_used = _parse_bool_line("LLM used", text)
    embeddings_used = _parse_bool_line("Embeddings used", text)

    answer = text
    marker = "Answer:\n"
    if marker in text:
        answer = text.split(marker, 1)[1]
        if "\nSources:\n" in answer:
            answer = answer.split("\nSources:\n", 1)[0].strip()
        else:
            answer = answer.strip()

    source_count = 0
    if "\nSources:\n" in text:
        tail = text.split("\nSources:\n", 1)[1]
        source_count = len(re.findall(r"(?m)^\d+\.\s+", tail))
    else:
        # Structured deterministic answers may not have a trailing Sources block.
        source_count = len(re.findall(r"(?m)^\s*-\s+T\.P\.\s+", text))

    return llm_used, embeddings_used, answer, source_count


def evaluate_text(answer_text: str, expected_terms: Iterable[str], expected_sources: Iterable[str], return_code: int) -> tuple[str, list[str], list[str]]:
    haystack = answer_text.lower()
    missing_terms = [term for term in expected_terms if term.lower() not in haystack]
    missing_sources = [src for src in expected_sources if src.lower() not in haystack]
    if return_code != 0:
        return "fail", missing_terms, missing_sources
    if missing_terms or missing_sources:
        return "fail", missing_terms, missing_sources
    return "pass", missing_terms, missing_sources


def build_ask_command(
    *,
    repo_root: Path,
    config_path: Path,
    model: str,
    question: ModelEvalQuestion,
    embed_model: str | None = None,
    force_llm: bool = False,
) -> list[str]:
    cmd = [
        sys.executable,
        str(repo_root / "scripts/operations/ingestion/ask_tiff_rag.py"),
        "--config",
        str(config_path),
        "--llm-model",
        model,
        "--answer-mode",
        question.answer_mode,
        "--retrieval-mode",
        question.retrieval_mode,
        "--top-k",
        str(question.top_k),
    ]
    if embed_model:
        cmd.extend(["--embed-model", embed_model])
    if force_llm:
        cmd.append("--force-llm")
    cmd.append(question.question)
    return cmd


def run_model_eval_question(
    *,
    repo_root: Path,
    config_path: Path,
    model: str,
    question: ModelEvalQuestion,
    embed_model: str | None = None,
    timeout_seconds: int = 180,
    force_llm: bool = False,
) -> ModelEvalResult:
    started = time.perf_counter()
    cmd = build_ask_command(
        repo_root=repo_root,
        config_path=config_path,
        model=model,
        question=question,
        embed_model=embed_model,
        force_llm=force_llm,
    )
    proc = subprocess.run(
        cmd,
        cwd=str(repo_root),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_seconds,
    )
    elapsed = time.perf_counter() - started
    raw = proc.stdout or ""
    llm_used, embeddings_used, answer, source_count = parse_ask_tiff_rag_output(raw)
    status, missing_terms, missing_sources = evaluate_text(raw, question.expected_terms, question.expected_sources, proc.returncode)
    # Broad LLM summaries with no expected-source failures are marked review by default.
    if status == "pass" and llm_used and question.answer_mode in {"summarize", "compare", "auto"}:
        status = "manual_review"
    return ModelEvalResult(
        question_id=question.id,
        question=question.question,
        model=model,
        answer_mode=question.answer_mode,
        retrieval_mode=question.retrieval_mode,
        top_k=question.top_k,
        status=status,
        elapsed_seconds=elapsed,
        llm_used=llm_used,
        embeddings_used=embeddings_used,
        source_count=source_count,
        missing_terms=missing_terms,
        missing_sources=missing_sources,
        return_code=proc.returncode,
        answer=answer,
        raw_output=raw,
        stderr=proc.stderr or "",
    )


def summarize_results(results: Sequence[ModelEvalResult]) -> dict[str, object]:
    by_status: dict[str, int] = {}
    by_model: dict[str, dict[str, object]] = {}
    for r in results:
        by_status[r.status] = by_status.get(r.status, 0) + 1
        model_row = by_model.setdefault(r.model, {"count": 0, "pass": 0, "fail": 0, "manual_review": 0, "llm_used": 0, "embeddings_used": 0, "elapsed_seconds": 0.0})
        model_row["count"] = int(model_row["count"]) + 1
        model_row[r.status] = int(model_row.get(r.status, 0)) + 1
        if r.llm_used:
            model_row["llm_used"] = int(model_row["llm_used"]) + 1
        if r.embeddings_used:
            model_row["embeddings_used"] = int(model_row["embeddings_used"]) + 1
        model_row["elapsed_seconds"] = float(model_row["elapsed_seconds"]) + r.elapsed_seconds
    return {"total": len(results), "by_status": by_status, "by_model": by_model}


def write_result_files(output_dir: Path, results: Sequence[ModelEvalResult]) -> Mapping[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "rag_model_eval_results.csv"
    json_path = output_dir / "rag_model_eval_results.json"
    html_path = output_dir / "rag_model_eval_results.html"

    fieldnames = [
        "question_id",
        "question",
        "model",
        "answer_mode",
        "retrieval_mode",
        "top_k",
        "status",
        "elapsed_seconds",
        "llm_used",
        "embeddings_used",
        "source_count",
        "missing_terms",
        "missing_sources",
        "return_code",
        "answer",
        "stderr",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            row = asdict(r)
            row["missing_terms"] = "; ".join(r.missing_terms)
            row["missing_sources"] = "; ".join(r.missing_sources)
            row["elapsed_seconds"] = f"{r.elapsed_seconds:.3f}"
            row.pop("raw_output", None)
            writer.writerow({name: row.get(name, "") for name in fieldnames})

    json_path.write_text(
        json.dumps({"summary": summarize_results(results), "results": [asdict(r) for r in results]}, indent=2),
        encoding="utf-8",
    )

    summary = summarize_results(results)
    rows = []
    for r in results:
        rows.append(
            "<tr>"
            f"<td>{html.escape(r.model)}</td>"
            f"<td>{html.escape(r.question_id)}</td>"
            f"<td>{html.escape(r.status)}</td>"
            f"<td>{r.elapsed_seconds:.2f}s</td>"
            f"<td>{html.escape(str(r.llm_used))}</td>"
            f"<td>{html.escape(str(r.embeddings_used))}</td>"
            f"<td>{r.source_count}</td>"
            f"<td><pre>{html.escape(r.answer)}</pre></td>"
            "</tr>"
        )
    html_path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'><title>TIFF RAG Model Eval</title>"
        "<style>body{font-family:Arial,sans-serif;margin:24px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:6px;vertical-align:top}pre{white-space:pre-wrap}</style>"
        "</head><body>"
        "<h1>TIFF RAG Model Evaluation</h1>"
        f"<pre>{html.escape(json.dumps(summary, indent=2))}</pre>"
        "<table><thead><tr><th>Model</th><th>Question ID</th><th>Status</th><th>Elapsed</th><th>LLM</th><th>Embeddings</th><th>Sources</th><th>Answer</th></tr></thead><tbody>"
        + "\n".join(rows)
        + "</tbody></table></body></html>",
        encoding="utf-8",
    )
    return {"csv": csv_path, "json": json_path, "html": html_path}
