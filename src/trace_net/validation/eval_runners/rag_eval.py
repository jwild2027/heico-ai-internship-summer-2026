"""Repeatable evaluation helpers for local TIFF RAG questions."""

from __future__ import annotations

import csv
import html
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from tiff.rag_answer import RagAnswer, answer_question, format_source_label
from tiff.rag_retriever import RagSource

try:
    from tiff.rag_eval_questions import EXPANDED_RAG_EVAL_QUESTIONS
except Exception:  # pragma: no cover - fallback only protects partial installs.
    EXPANDED_RAG_EVAL_QUESTIONS = []


_FALLBACK_EVAL_QUESTIONS: list[dict[str, Any]] = [
    {
        "id": "part_lookup_001",
        "question": "What is part number 120-37313-001?",
        "expected_terms": ["120-37313-001", "HOLDER, MAGAZINE"],
        "expected_sources": ["Page 1056"],
        "answer_mode": "auto",
        "retrieval_mode": "auto",
        "expected_llm_used": False,
        "expected_embeddings_used": False,
    },
    {
        "id": "nomenclature_lookup_001",
        "question": "Where is magazine holder shown?",
        "expected_terms": ["120-37313-001", "120-36843-001", "120-37313-535"],
        "answer_mode": "auto",
        "retrieval_mode": "auto",
        "expected_llm_used": False,
    },
    {
        "id": "structured_summary_001",
        "question": "Summarize the sources related to magazine holder parts.",
        "expected_terms": ["HOLDER, MAGAZINE", "120-37313-001", "120-36843-001"],
        "answer_mode": "summarize",
        "retrieval_mode": "hybrid",
    },
    {
        "id": "broad_summary_001",
        "question": "Which pages discuss passenger seat back crack reinforcement, and what do they say?",
        "expected_terms": ["passenger", "seat", "back"],
        "answer_mode": "auto",
        "retrieval_mode": "hybrid",
        "manual_review": True,
    },
]

DEFAULT_EVAL_QUESTIONS: list[dict[str, Any]] = EXPANDED_RAG_EVAL_QUESTIONS or _FALLBACK_EVAL_QUESTIONS


@dataclass(frozen=True)
class EvalQuestion:
    id: str
    question: str
    expected_terms: tuple[str, ...] = ()
    expected_sources: tuple[str, ...] = ()
    expected_llm_used: bool | None = None
    expected_embeddings_used: bool | None = None
    answer_mode: str = "auto"
    retrieval_mode: str = "auto"
    top_k: int | None = None
    force_llm: bool = False
    force_embeddings: bool = False
    use_llm: bool | None = None
    use_embeddings: bool | None = None
    manual_review: bool = False
    notes: str = ""


@dataclass(frozen=True)
class EvalRecord:
    id: str
    question: str
    answer: str
    answer_mode: str
    retrieval_mode: str
    llm_model: str
    embed_model: str
    llm_used: bool
    embeddings_used: bool
    elapsed_seconds: float
    source_count: int
    expected_terms: tuple[str, ...] = ()
    missing_terms: tuple[str, ...] = ()
    expected_sources: tuple[str, ...] = ()
    missing_sources: tuple[str, ...] = ()
    expected_llm_used: bool | None = None
    expected_embeddings_used: bool | None = None
    expectation_errors: tuple[str, ...] = ()
    status: str = "manual_review"
    warnings: tuple[str, ...] = ()
    sources: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    notes: str = ""


CSV_FIELDS = [
    "id",
    "question",
    "status",
    "answer_mode",
    "retrieval_mode",
    "llm_model",
    "embed_model",
    "llm_used",
    "embeddings_used",
    "elapsed_seconds",
    "source_count",
    "expected_terms",
    "missing_terms",
    "expected_sources",
    "missing_sources",
    "expected_llm_used",
    "expected_embeddings_used",
    "expectation_errors",
    "warnings",
    "notes",
    "answer",
]


def _optional_bool(data: dict[str, Any], *keys: str) -> bool | None:
    for key in keys:
        if key not in data or data.get(key) is None:
            continue
        value = data.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y", "on"}:
            return True
        if text in {"0", "false", "no", "n", "off"}:
            return False
        return bool(value)
    return None


def question_from_dict(data: dict[str, Any], *, index: int = 0) -> EvalQuestion:
    question = str(data.get("question") or "").strip()
    if not question:
        raise ValueError(f"Eval question #{index + 1} is missing 'question'")
    qid = str(data.get("id") or f"question_{index + 1:03d}")
    return EvalQuestion(
        id=qid,
        question=question,
        expected_terms=tuple(str(x) for x in data.get("expected_terms", []) or []),
        expected_sources=tuple(str(x) for x in data.get("expected_sources", []) or []),
        expected_llm_used=_optional_bool(data, "expected_llm_used", "expect_llm_used"),
        expected_embeddings_used=_optional_bool(data, "expected_embeddings_used", "expect_embeddings_used"),
        answer_mode=str(data.get("answer_mode") or "auto"),
        retrieval_mode=str(data.get("retrieval_mode") or "auto"),
        top_k=int(data["top_k"]) if data.get("top_k") is not None else None,
        force_llm=bool(data.get("force_llm", False)),
        force_embeddings=bool(data.get("force_embeddings", False)),
        use_llm=_optional_bool(data, "use_llm"),
        use_embeddings=_optional_bool(data, "use_embeddings"),
        manual_review=bool(data.get("manual_review", False)),
        notes=str(data.get("notes") or ""),
    )


def load_eval_questions(path: str | Path | None = None) -> list[EvalQuestion]:
    """Load eval questions from JSON; return defaults if path is missing."""

    if path is None or str(path).strip() == "":
        raw = DEFAULT_EVAL_QUESTIONS
    else:
        q_path = Path(path)
        if not q_path.exists():
            raise FileNotFoundError(f"Eval question file does not exist: {q_path}")
        raw_data = json.loads(q_path.read_text(encoding="utf-8"))
        if isinstance(raw_data, dict):
            raw = raw_data.get("questions", [])
        else:
            raw = raw_data
        if not isinstance(raw, list):
            raise ValueError("Eval question file must contain a list or an object with 'questions'")
    return [question_from_dict(item, index=i) for i, item in enumerate(raw)]


def write_default_eval_questions(path: str | Path) -> Path:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"questions": DEFAULT_EVAL_QUESTIONS}, indent=2) + "\n", encoding="utf-8")
    return out_path


def source_to_eval_dict(source: RagSource, *, index: int) -> dict[str, Any]:
    return {
        "index": index,
        "label": format_source_label(source),
        "source_type": source.source_type,
        "score": source.score,
        "manual_id": source.manual_id,
        "publication_number": source.publication_number,
        "ata_code": source.ata_code,
        "page_label": source.page_label,
        "page_sequence": source.page_sequence,
        "part_number": source.matched_part_number,
        "nomenclature": source.part_nomenclature,
        "rescarta_url": getattr(source, "rescarta_url", None),
        "source_url": getattr(source, "source_url", None),
        "tiff_path": source.tiff_path,
        "ocr_text_path": source.ocr_text_path,
    }


def _haystack_for_answer(answer: RagAnswer) -> str:
    parts = [answer.answer]
    for idx, source in enumerate(answer.sources, start=1):
        parts.append(format_source_label(source))
        parts.append(source.source_type or "")
        parts.append(source.matched_part_number or "")
        parts.append(source.part_nomenclature or "")
        parts.append(source.evidence_text or "")
        parts.append(source.tiff_path or "")
        parts.append(source.ocr_text_path or "")
        parts.append(getattr(source, "rescarta_url", None) or "")
        parts.append(getattr(source, "source_url", None) or "")
        parts.append(str(idx))
    return "\n".join(parts).upper()


def _expectation_errors(answer: RagAnswer, question: EvalQuestion) -> tuple[str, ...]:
    errors: list[str] = []
    if question.expected_llm_used is not None and answer.used_llm != question.expected_llm_used:
        errors.append(f"LLM used expected {question.expected_llm_used} got {answer.used_llm}")
    if question.expected_embeddings_used is not None and answer.used_embeddings != question.expected_embeddings_used:
        errors.append(
            f"Embeddings used expected {question.expected_embeddings_used} got {answer.used_embeddings}"
        )
    return tuple(errors)


def judge_answer(answer: RagAnswer, question: EvalQuestion) -> tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    haystack = _haystack_for_answer(answer)
    missing_terms = tuple(term for term in question.expected_terms if str(term).upper() not in haystack)
    missing_sources = tuple(term for term in question.expected_sources if str(term).upper() not in haystack)
    expectation_errors = _expectation_errors(answer, question)
    if missing_terms or missing_sources or expectation_errors:
        return "fail", missing_terms, missing_sources, expectation_errors
    if question.manual_review:
        return "manual_review", missing_terms, missing_sources, expectation_errors
    has_automatic_check = bool(question.expected_terms or question.expected_sources or question.expected_llm_used is not None or question.expected_embeddings_used is not None)
    if has_automatic_check:
        return "pass", missing_terms, missing_sources, expectation_errors
    return "manual_review", missing_terms, missing_sources, expectation_errors


def evaluate_question(
    question: EvalQuestion,
    *,
    db_path: str | Path,
    embed_model: str,
    llm_model: str,
    ollama_url: str,
    top_k: int,
    use_llm: bool = True,
    use_embeddings: bool = True,
) -> EvalRecord:
    actual_top_k = question.top_k if question.top_k is not None else top_k
    actual_use_llm = use_llm if question.use_llm is None else question.use_llm
    actual_use_embeddings = use_embeddings if question.use_embeddings is None else question.use_embeddings
    start = time.perf_counter()
    answer = answer_question(
        Path(db_path),
        question.question,
        embed_model=embed_model,
        llm_model=llm_model,
        ollama_url=ollama_url,
        top_k=actual_top_k,
        use_llm=actual_use_llm,
        use_embeddings=actual_use_embeddings,
        answer_mode=question.answer_mode,
        retrieval_mode=question.retrieval_mode,
        force_llm=question.force_llm,
        force_embeddings=question.force_embeddings,
    )
    elapsed = time.perf_counter() - start
    status, missing_terms, missing_sources, expectation_errors = judge_answer(answer, question)
    return EvalRecord(
        id=question.id,
        question=question.question,
        answer=answer.answer,
        answer_mode=question.answer_mode,
        retrieval_mode=question.retrieval_mode,
        llm_model=llm_model,
        embed_model=embed_model,
        llm_used=answer.used_llm,
        embeddings_used=answer.used_embeddings,
        elapsed_seconds=elapsed,
        source_count=len(answer.sources),
        expected_terms=question.expected_terms,
        missing_terms=missing_terms,
        expected_sources=question.expected_sources,
        missing_sources=missing_sources,
        expected_llm_used=question.expected_llm_used,
        expected_embeddings_used=question.expected_embeddings_used,
        expectation_errors=expectation_errors,
        status=status,
        warnings=answer.warnings,
        sources=tuple(source_to_eval_dict(source, index=i) for i, source in enumerate(answer.sources, start=1)),
        notes=question.notes,
    )


def evaluate_questions(
    questions: Iterable[EvalQuestion],
    *,
    db_path: str | Path,
    embed_model: str,
    llm_model: str,
    ollama_url: str,
    top_k: int,
    use_llm: bool = True,
    use_embeddings: bool = True,
) -> list[EvalRecord]:
    return [
        evaluate_question(
            question,
            db_path=db_path,
            embed_model=embed_model,
            llm_model=llm_model,
            ollama_url=ollama_url,
            top_k=top_k,
            use_llm=use_llm,
            use_embeddings=use_embeddings,
        )
        for question in questions
    ]


def record_to_dict(record: EvalRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "question": record.question,
        "answer": record.answer,
        "answer_mode": record.answer_mode,
        "retrieval_mode": record.retrieval_mode,
        "llm_model": record.llm_model,
        "embed_model": record.embed_model,
        "llm_used": record.llm_used,
        "embeddings_used": record.embeddings_used,
        "elapsed_seconds": round(record.elapsed_seconds, 4),
        "source_count": record.source_count,
        "expected_terms": list(record.expected_terms),
        "missing_terms": list(record.missing_terms),
        "expected_sources": list(record.expected_sources),
        "missing_sources": list(record.missing_sources),
        "expected_llm_used": record.expected_llm_used,
        "expected_embeddings_used": record.expected_embeddings_used,
        "expectation_errors": list(record.expectation_errors),
        "status": record.status,
        "warnings": list(record.warnings),
        "sources": list(record.sources),
        "notes": record.notes,
    }


def write_eval_json(records: Iterable[EvalRecord], path: str | Path) -> Path:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps([record_to_dict(r) for r in records], indent=2), encoding="utf-8")
    return out_path


def write_eval_csv(records: Iterable[EvalRecord], path: str | Path) -> Path:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for record in records:
            row = record_to_dict(record)
            row["elapsed_seconds"] = f"{record.elapsed_seconds:.4f}"
            for key in [
                "expected_terms",
                "missing_terms",
                "expected_sources",
                "missing_sources",
                "expectation_errors",
                "warnings",
            ]:
                row[key] = "; ".join(str(x) for x in row.get(key, []))
            writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})
    return out_path


def write_eval_html(records: Iterable[EvalRecord], path: str | Path) -> Path:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[str] = []
    for record in records:
        source_lines = []
        for source in record.sources[:12]:
            source_lines.append(
                f"<li><strong>{html.escape(str(source.get('index')))}. "
                f"{html.escape(str(source.get('label') or ''))}</strong> "
                f"<code>{html.escape(str(source.get('source_type') or ''))}</code> "
                f"{html.escape(str(source.get('part_number') or ''))} "
                f"{html.escape(str(source.get('nomenclature') or ''))}</li>"
            )
        rows.append(
            "<section class='record'>"
            f"<h2>{html.escape(record.id)}: {html.escape(record.question)}</h2>"
            f"<p><strong>Status:</strong> <span class='{html.escape(record.status)}'>{html.escape(record.status)}</span> "
            f"<strong>LLM:</strong> {record.llm_used} <strong>Embeddings:</strong> {record.embeddings_used} "
            f"<strong>Elapsed:</strong> {record.elapsed_seconds:.2f}s <strong>Sources:</strong> {record.source_count}</p>"
            f"<p><strong>Missing terms:</strong> {html.escape('; '.join(record.missing_terms) or '-')}<br>"
            f"<strong>Missing sources:</strong> {html.escape('; '.join(record.missing_sources) or '-')}<br>"
            f"<strong>Expectation errors:</strong> {html.escape('; '.join(record.expectation_errors) or '-')}</p>"
            f"<pre>{html.escape(record.answer)}</pre>"
            f"<h3>Sources</h3><ol>{''.join(source_lines)}</ol>"
            "</section>"
        )
    doc = """<!doctype html>
<html><head><meta charset=\"utf-8\"><title>TIFF RAG Evaluation</title>
<style>
body { font-family: Arial, sans-serif; margin: 24px; }
.record { border: 1px solid #ccc; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
pre { white-space: pre-wrap; background: #f7f7f7; padding: 12px; border-radius: 6px; }
.pass { color: #087a1f; font-weight: bold; }
.fail { color: #b00020; font-weight: bold; }
.manual_review { color: #8a5a00; font-weight: bold; }
code { background: #eee; padding: 2px 4px; border-radius: 3px; }
</style></head><body>
<h1>TIFF RAG Evaluation</h1>
%s
</body></html>
""" % "\n".join(rows)
    out_path.write_text(doc, encoding="utf-8")
    return out_path


def summarize_eval_records(records: Iterable[EvalRecord]) -> dict[str, int]:
    summary = {"total": 0, "pass": 0, "fail": 0, "manual_review": 0, "llm_used": 0, "embeddings_used": 0}
    for record in records:
        summary["total"] += 1
        summary[record.status] = summary.get(record.status, 0) + 1
        if record.llm_used:
            summary["llm_used"] += 1
        if record.embeddings_used:
            summary["embeddings_used"] += 1
    return summary
