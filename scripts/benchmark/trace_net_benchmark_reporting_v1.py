#!/usr/bin/env python3
"""Durable reporting and recovery helpers for TRACE-Net benchmark JSONL runs."""
from __future__ import annotations

import csv
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


REPORT_VERSION = "trace_net_benchmark_reporting_v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def load_records_jsonl(path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Load completed records while tolerating a final partial line after interruption."""
    records: List[Dict[str, Any]] = []
    warnings: List[str] = []
    if not path.exists():
        return records, warnings

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line_number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            if line_number == len(lines):
                warnings.append(
                    f"ignored_trailing_partial_json_line:{line_number}:{exc.msg}"
                )
                continue
            raise ValueError(
                f"Invalid JSONL record at {path}:{line_number}: {exc}"
            ) from exc
        if not isinstance(value, Mapping):
            warnings.append(f"ignored_non_object_record:{line_number}")
            continue
        records.append(dict(value))
    return records, warnings


def completed_question_ids(records: Sequence[Mapping[str, Any]]) -> List[str]:
    seen: List[str] = []
    for index, row in enumerate(records, 1):
        qid = str(row.get("question_id") or f"q{index:03d}")
        if qid not in seen:
            seen.append(qid)
    return seen


def rewrite_records_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    """Atomically rewrite JSONL from validated records, removing a partial tail."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        for row in records:
            handle.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
        handle.flush()
    temp.replace(path)


def safe_git_value(repo_root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception:
        return ""
    return result.stdout.strip()


def build_run_metadata(
    *,
    repo_root: Path,
    question_bank: Path,
    output_dir: Path,
    base_url: str,
    model: str,
    request_timeout: int,
    expected_question_count: int,
    resume_enabled: bool,
    existing_record_count: int,
) -> Dict[str, Any]:
    return {
        "report_version": REPORT_VERSION,
        "created_at_utc": utc_now_iso(),
        "repository_root": str(repo_root.resolve()),
        "git_commit": safe_git_value(repo_root, "rev-parse", "HEAD"),
        "git_branch": safe_git_value(repo_root, "rev-parse", "--abbrev-ref", "HEAD"),
        "git_status_porcelain": safe_git_value(repo_root, "status", "--porcelain"),
        "question_bank": str(question_bank),
        "output_dir": str(output_dir),
        "base_url": base_url,
        "model": model,
        "request_timeout_seconds": int(request_timeout),
        "expected_question_count": int(expected_question_count),
        "resume_enabled": bool(resume_enabled),
        "existing_record_count": int(existing_record_count),
        "safety_contract": {
            "read_only_queries": True,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
        },
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


def _trace(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("trace_net")
    return value if isinstance(value, Mapping) else {}


def _selected_skills(row: Mapping[str, Any]) -> List[str]:
    trace = _trace(row)
    for key in ("selected_engram_skills", "engram_skills", "injected_engram_skills"):
        values = _string_list(trace.get(key))
        if values:
            return values
    planner = trace.get("planner_execution")
    if isinstance(planner, Mapping):
        for key in ("selected_engram_skills", "engram_skills"):
            values = _string_list(planner.get(key))
            if values:
                return values
    return []


def _critic_summary(row: Mapping[str, Any]) -> str:
    trace = _trace(row)
    for key in ("answer_quality", "quality_guard", "critic", "self_rag_critic"):
        value = trace.get(key)
        if isinstance(value, Mapping):
            decision = value.get("decision") or value.get("quality_status") or value.get("status")
            if decision:
                return str(decision)
    return ""


def _repair_count(row: Mapping[str, Any]) -> int:
    trace = _trace(row)
    for key in ("crag_attempts", "repair_attempts", "correction_attempts"):
        value = trace.get(key)
        if isinstance(value, list):
            return len(value)
        if isinstance(value, int):
            return value
    return 0


def record_to_flat_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    followups = _string_list(row.get("follow_up_questions"))
    failures = _string_list(row.get("failures"))
    return {
        "question_id": row.get("question_id", ""),
        "category": row.get("category", ""),
        "quality_status": row.get("quality_status", ""),
        "query": row.get("query", ""),
        "answer": row.get("answer", ""),
        "expected_route": row.get("expected_route", ""),
        "actual_route": row.get("actual_route", ""),
        "planned_tunnels": json.dumps(row.get("planned_tunnels") or [], ensure_ascii=False),
        "used_tunnels": json.dumps(row.get("used_tunnels") or [], ensure_ascii=False),
        "writer_status": row.get("writer_status", ""),
        "writer_mode": row.get("writer_mode", ""),
        "writer_model": row.get("writer_model", ""),
        "citation_count": row.get("citation_count", 0),
        "direct_evidence_count": row.get("direct_evidence_count", 0),
        "candidate_evidence_count": row.get("candidate_evidence_count", 0),
        "follow_up_questions": json.dumps(followups, ensure_ascii=False),
        "selected_engram_skills": json.dumps(_selected_skills(row), ensure_ascii=False),
        "critic_result": _critic_summary(row),
        "repair_attempt_count": _repair_count(row),
        "latency_ms": row.get("latency_ms", 0),
        "failures": json.dumps(failures, ensure_ascii=False),
    }


def _record_markdown(row: Mapping[str, Any], index: int) -> List[str]:
    qid = str(row.get("question_id") or f"q{index:03d}")
    status = str(row.get("quality_status") or "UNKNOWN")
    answer = str(row.get("answer") or "")
    followups = _string_list(row.get("follow_up_questions"))
    failures = _string_list(row.get("failures"))
    skills = _selected_skills(row)
    lines = [
        f"## {qid.upper()} — {status}",
        "",
        f"- **Category:** `{row.get('category', '')}`",
        f"- **Expected route:** `{row.get('expected_route', '')}`",
        f"- **Actual route:** `{row.get('actual_route', '')}`",
        f"- **Planned tunnels:** `{', '.join(_string_list(row.get('planned_tunnels')))}`",
        f"- **Used tunnels:** `{', '.join(_string_list(row.get('used_tunnels')))}`",
        f"- **Writer:** `{row.get('writer_status', '')}`",
        f"- **Writer mode:** `{row.get('writer_mode', '')}`",
        f"- **Citations:** `{row.get('citation_count', 0)}`",
        f"- **Direct evidence:** `{row.get('direct_evidence_count', 0)}`",
        f"- **Candidate evidence:** `{row.get('candidate_evidence_count', 0)}`",
        f"- **Selected Engram skills:** `{', '.join(skills)}`",
        f"- **Critic result:** `{_critic_summary(row)}`",
        f"- **Repair attempts:** `{_repair_count(row)}`",
        f"- **Latency:** `{float(row.get('latency_ms') or 0.0) / 1000.0:.1f} s`",
        "",
        "### Question",
        "",
        str(row.get("query") or ""),
        "",
        "### Full answer",
        "",
        answer or "_No answer stored._",
    ]
    if followups:
        lines.extend(["", "### Follow-up questions", ""])
        lines.extend(f"- {value}" for value in followups)
    if failures:
        lines.extend(["", "### Benchmark failures", ""])
        lines.extend(f"- `{value}`" for value in failures)
    lines.extend(["", "---", ""])
    return lines


def build_progress_summary(
    records: Sequence[Mapping[str, Any]],
    *,
    expected_question_count: int,
    interrupted: bool,
    load_warnings: Sequence[str],
    run_metadata: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    failed = [row for row in records if str(row.get("quality_status")) != "PASS"]
    return {
        "report_version": REPORT_VERSION,
        "updated_at_utc": utc_now_iso(),
        "status": "INTERRUPTED" if interrupted else (
            "COMPLETE" if len(records) == expected_question_count else "IN_PROGRESS"
        ),
        "quality_status": "PASS" if (
            len(records) == expected_question_count and not failed and not interrupted
        ) else "FAIL",
        "question_count": len(records),
        "expected_question_count": int(expected_question_count),
        "pass_count": len(records) - len(failed),
        "fail_count": len(failed),
        "completed_question_ids": completed_question_ids(records),
        "category_counts": dict(Counter(str(row.get("category") or "unknown") for row in records)),
        "route_counts": dict(Counter(str(row.get("actual_route") or "unknown") for row in records)),
        "failure_counts": dict(Counter(
            failure
            for row in failed
            for failure in _string_list(row.get("failures"))
        )),
        "load_warnings": list(load_warnings),
        "run_metadata": dict(run_metadata or {}),
    }


def write_qa_reports(
    records: Sequence[Mapping[str, Any]],
    *,
    output_dir: Path,
    expected_question_count: int,
    interrupted: bool = False,
    load_warnings: Sequence[str] = (),
    run_metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, str]:
    """Write complete and failed-only reports atomically."""
    output_dir.mkdir(parents=True, exist_ok=True)
    qa_dir = output_dir / "question_answer_report"
    qa_dir.mkdir(parents=True, exist_ok=True)

    full_md = qa_dir / "full_question_answers.md"
    full_csv = qa_dir / "full_question_answers.csv"
    failed_md = qa_dir / "failed_question_answers.md"
    snapshot_json = qa_dir / "records_snapshot.json"
    progress_json = output_dir / "progress_summary.json"

    header = [
        "# TRACE-Net Benchmark — Complete Questions and Answers",
        "",
        f"- Records recovered: **{len(records)}**",
        f"- Expected records: **{expected_question_count}**",
        f"- Passed: **{sum(str(row.get('quality_status')) == 'PASS' for row in records)}**",
        f"- Failed: **{sum(str(row.get('quality_status')) != 'PASS' for row in records)}**",
        f"- Interrupted: **{'yes' if interrupted else 'no'}**",
        "",
        "> Answers below are complete stored answers, not terminal previews.",
        "",
    ]
    full_lines = list(header)
    for index, row in enumerate(records, 1):
        full_lines.extend(_record_markdown(row, index))
    temp = full_md.with_suffix(".md.tmp")
    temp.write_text("\n".join(full_lines), encoding="utf-8")
    temp.replace(full_md)

    failed = [row for row in records if str(row.get("quality_status")) != "PASS"]
    failed_lines = [
        "# TRACE-Net Benchmark — Failed Questions",
        "",
        f"- Failed records: **{len(failed)}**",
        "",
    ]
    for index, row in enumerate(failed, 1):
        failed_lines.extend(_record_markdown(row, index))
    temp = failed_md.with_suffix(".md.tmp")
    temp.write_text("\n".join(failed_lines), encoding="utf-8")
    temp.replace(failed_md)

    fieldnames = list(record_to_flat_row({}).keys())
    temp_csv = full_csv.with_suffix(".csv.tmp")
    with temp_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in records:
            writer.writerow(record_to_flat_row(row))
    temp_csv.replace(full_csv)

    write_json(snapshot_json, list(records))
    progress = build_progress_summary(
        records,
        expected_question_count=expected_question_count,
        interrupted=interrupted,
        load_warnings=load_warnings,
        run_metadata=run_metadata,
    )
    write_json(progress_json, progress)

    return {
        "full_question_answers_markdown": str(full_md),
        "full_question_answers_csv": str(full_csv),
        "failed_question_answers_markdown": str(failed_md),
        "records_snapshot": str(snapshot_json),
        "progress_summary": str(progress_json),
    }
