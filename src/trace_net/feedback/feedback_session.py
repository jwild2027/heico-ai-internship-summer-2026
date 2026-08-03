"""Interactive feedback capture for TIFF/RAG user answers.

This module stores feedback as append-only JSONL so it can be reviewed,
replayed, and later promoted into graph/quality workflows without mutating
source truth directly.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
import zipfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DEFAULT_OUTPUT = Path("local_data/feedback/user_feedback.jsonl")
DEFAULT_SUMMARY = Path("local_data/feedback/user_feedback_summary.json")


@dataclass(frozen=True)
class SourceZipAudit:
    zip_path: str | None
    status: str
    exists: bool
    total_entries: int = 0
    total_bytes: int = 0
    tiff_files: int = 0
    xml_files: int = 0
    ocr_text_files: int = 0
    other_files: int = 0
    metadata_xml_present: bool = False
    warnings: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class AnswerRun:
    question: str
    command: list[str]
    returncode: int
    elapsed_seconds: float
    stdout: str
    stderr: str
    llm_used: bool | None = None
    embeddings_used: bool | None = None


@dataclass(frozen=True)
class FeedbackEntry:
    feedback_id: str
    session_id: str
    created_at: str
    question: str
    rating: str
    score: int | None
    reason: str
    category: str | None
    answer_text: str
    answer_returncode: int
    answer_elapsed_seconds: float
    llm_used: bool | None
    embeddings_used: bool | None
    source_zip: dict[str, Any]
    config: str
    source: str = "interactive_feedback_session"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_answer_id(question: str, answer_text: str) -> str:
    raw = f"{question}\n---\n{answer_text}".encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()[:16]


def audit_source_zip(zip_path: str | os.PathLike[str] | None) -> SourceZipAudit:
    if not zip_path:
        return SourceZipAudit(
            zip_path=None,
            status="not_provided",
            exists=False,
            warnings=("source ZIP was not provided",),
        )

    path = Path(zip_path).expanduser()
    if not path.exists():
        return SourceZipAudit(
            zip_path=str(path),
            status="missing",
            exists=False,
            error="source ZIP does not exist",
        )

    try:
        with zipfile.ZipFile(path) as zf:
            infos = [i for i in zf.infolist() if not i.is_dir()]
    except zipfile.BadZipFile as exc:
        return SourceZipAudit(
            zip_path=str(path),
            status="bad_zip",
            exists=True,
            error=str(exc),
        )

    tiff = xml = txt = other = 0
    total_bytes = 0
    metadata_xml = False
    for info in infos:
        name = info.filename.replace("\\", "/").lower()
        total_bytes += int(info.file_size or 0)
        if name.endswith((".tif", ".tiff")):
            tiff += 1
        elif name.endswith(".xml"):
            xml += 1
            if name.endswith("metadata.xml") or name == "metadata.xml":
                metadata_xml = True
        elif name.endswith(".txt"):
            txt += 1
        else:
            other += 1

    warnings: list[str] = []
    if tiff == 0:
        warnings.append("no TIFF files found in ZIP")
    if not metadata_xml:
        warnings.append("metadata.xml was not found in ZIP")
    if txt == 0:
        warnings.append("no OCR .txt files found in ZIP; OCR may need to be imported/generated separately")

    return SourceZipAudit(
        zip_path=str(path),
        status="ok" if tiff > 0 and metadata_xml else "needs_attention",
        exists=True,
        total_entries=len(infos),
        total_bytes=total_bytes,
        tiff_files=tiff,
        xml_files=xml,
        ocr_text_files=txt,
        other_files=other,
        metadata_xml_present=metadata_xml,
        warnings=tuple(warnings),
    )


def normalize_rating(value: str) -> tuple[str, int | None]:
    raw = (value or "").strip().lower()
    if raw in {"up", "thumbs_up", "thumbsup", "yes", "y", "+", "+1", "good", "pass"}:
        return "thumbs_up", 1
    if raw in {"down", "thumbs_down", "thumbsdown", "no", "n", "-", "-1", "bad", "fail"}:
        return "thumbs_down", -1
    if raw in {"skip", "neutral", "0", "meh"}:
        return "neutral", 0
    if raw in {"1", "2", "3", "4", "5"}:
        score = int(raw)
        if score >= 4:
            return "thumbs_up", score
        if score <= 2:
            return "thumbs_down", score
        return "neutral", score
    raise ValueError("rating must be thumbs up/down, pass/fail, neutral, or 1-5")


def parse_bool_line(text: str, label: str) -> bool | None:
    pattern = re.compile(rf"^{re.escape(label)}:\s*(true|false)", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(text or "")
    if not match:
        return None
    return match.group(1).lower() == "true"


def run_answer_command(
    question: str,
    *,
    config: str = "local_config.yaml",
    timeout: int = 180,
    python_executable: str | None = None,
) -> AnswerRun:
    py = python_executable or sys.executable
    command = [py, "scripts/operations/ingestion/ask_tiff_rag.py", "--config", config, question]
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    elapsed = time.perf_counter() - started
    combined = f"{completed.stdout}\n{completed.stderr}"
    return AnswerRun(
        question=question,
        command=command,
        returncode=int(completed.returncode),
        elapsed_seconds=round(elapsed, 3),
        stdout=completed.stdout,
        stderr=completed.stderr,
        llm_used=parse_bool_line(combined, "LLM used"),
        embeddings_used=parse_bool_line(combined, "Embeddings used"),
    )


def make_feedback_entry(
    *,
    session_id: str,
    question: str,
    answer: AnswerRun,
    rating_value: str,
    reason: str,
    category: str | None,
    source_zip: SourceZipAudit,
    config: str,
) -> FeedbackEntry:
    rating, score = normalize_rating(rating_value)
    feedback_id = f"fb_{stable_answer_id(question, answer.stdout)}_{uuid.uuid4().hex[:8]}"
    return FeedbackEntry(
        feedback_id=feedback_id,
        session_id=session_id,
        created_at=utc_now_iso(),
        question=question,
        rating=rating,
        score=score,
        reason=reason.strip(),
        category=(category or "").strip() or None,
        answer_text=answer.stdout,
        answer_returncode=answer.returncode,
        answer_elapsed_seconds=answer.elapsed_seconds,
        llm_used=answer.llm_used,
        embeddings_used=answer.embeddings_used,
        source_zip=asdict(source_zip),
        config=config,
    )


def append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def summarize_feedback(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = list(rows)
    rating_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    for row in items:
        rating = str(row.get("rating") or "unknown")
        category = str(row.get("category") or "uncategorized")
        rating_counts[rating] = rating_counts.get(rating, 0) + 1
        category_counts[category] = category_counts.get(category, 0) + 1
    return {
        "generated_at": utc_now_iso(),
        "total_feedback": len(items),
        "rating_counts": dict(sorted(rating_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "latest_feedback_id": items[-1].get("feedback_id") if items else None,
    }


def write_summary(feedback_path: Path, summary_path: Path) -> dict[str, Any]:
    rows = read_jsonl(feedback_path)
    summary = summarize_feedback(rows)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def save_feedback(entry: FeedbackEntry, output_path: Path = DEFAULT_OUTPUT, summary_path: Path = DEFAULT_SUMMARY) -> dict[str, Any]:
    append_jsonl(output_path, asdict(entry))
    return write_summary(output_path, summary_path)


def print_source_zip_audit(audit: SourceZipAudit) -> None:
    print("Source ZIP audit")
    print(f"  Status: {audit.status}")
    print(f"  ZIP: {audit.zip_path or '-'}")
    print(f"  Exists: {audit.exists}")
    if audit.exists and audit.status not in {"bad_zip", "missing"}:
        print(f"  TIFF files: {audit.tiff_files}")
        print(f"  XML files: {audit.xml_files}")
        print(f"  OCR text files: {audit.ocr_text_files}")
        print(f"  metadata.xml present: {audit.metadata_xml_present}")
    if audit.error:
        print(f"  Error: {audit.error}")
    for warning in audit.warnings:
        print(f"  Warning: {warning}")


def prompt_nonempty(message: str) -> str:
    while True:
        value = input(message).strip()
        if value:
            return value
        print("Please enter a value, or type 'quit' at the question prompt to exit.")


def run_interactive_session(
    *,
    config: str,
    source_zip_path: str | None,
    output_path: Path,
    summary_path: Path,
    timeout: int = 180,
) -> int:
    session_id = f"session_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:6]}"
    audit = audit_source_zip(source_zip_path)
    print("TIFF/RAG feedback session")
    print(f"  Session: {session_id}")
    print(f"  Config: {config}")
    print(f"  Output: {output_path}")
    print()
    print_source_zip_audit(audit)
    print()
    print("Type a question. After the answer, grade it with thumbs up/down or 1-5 and give a reason.")
    print("Type 'quit' or press Enter on an empty question to exit.")

    while True:
        question = input("\nQuestion> ").strip()
        if not question or question.lower() in {"q", "quit", "exit"}:
            break
        print("\nAnswering...\n")
        try:
            answer = run_answer_command(question, config=config, timeout=timeout)
        except subprocess.TimeoutExpired:
            print(f"Answer command timed out after {timeout}s.")
            continue
        print(answer.stdout.rstrip())
        if answer.stderr.strip():
            print("\n[stderr]")
            print(answer.stderr.rstrip())
        print(f"\nAnswer return code: {answer.returncode}")
        print(f"Elapsed: {answer.elapsed_seconds:.2f}s | LLM used: {answer.llm_used} | Embeddings used: {answer.embeddings_used}")
        rating_value = prompt_nonempty("Rating [up/down/1-5/neutral]> ")
        try:
            normalize_rating(rating_value)
        except ValueError as exc:
            print(f"Invalid rating: {exc}")
            rating_value = prompt_nonempty("Rating [up/down/1-5/neutral]> ")
        category = input("Category [wrong_answer/wrong_source/missing_source/incomplete/useful/other] (optional)> ").strip()
        reason = prompt_nonempty("Reason/comment> ")
        entry = make_feedback_entry(
            session_id=session_id,
            question=question,
            answer=answer,
            rating_value=rating_value,
            reason=reason,
            category=category,
            source_zip=audit,
            config=config,
        )
        summary = save_feedback(entry, output_path, summary_path)
        print(f"Saved feedback: {entry.feedback_id}")
        print(f"Feedback summary: total={summary['total_feedback']} ratings={summary['rating_counts']}")
    print("\nFeedback session complete.")
    write_summary(output_path, summary_path)
    return 0
