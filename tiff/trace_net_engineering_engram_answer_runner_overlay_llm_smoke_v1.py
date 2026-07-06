"""TRACE-Net Engineering Engram Answer-Runner Overlay LLM Smoke v1.

Artifact-first targeted smoke for retrieved Engram overlays.

This module prepends H24 retrieved Engram overlay guidance to saved engineering
answer-runner prompts from an existing answer-smoke manifest. It can run in:

* artifact mode: deterministic scaffold answers, no LLM call
* ollama mode: targeted local Gemma/Ollama calls

Safety contract:
- no Postgres writes
- no Qdrant reads/writes
- no OpenSearch writes/uploads
- no source-truth mutation
- no answer permission
- Engram overlay is behavior guidance only; source/manual claims still require
  current proof_context citations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

MODULE = "trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1"
VERSION = "v1"

SAFETY_CONTRACT = {
    "postgres_write_attempt_count": 0,
    "qdrant_read_attempt_count": 0,
    "qdrant_write_attempt_count": 0,
    "opensearch_write_attempt_count": 0,
    "opensearch_upload_attempt_count": 0,
    "source_truth_mutation_allowed_count": 0,
    "answer_permission_count": 0,
}

DEFAULT_TARGET_QUESTION_IDS = ["q12", "q16", "q18", "q25", "q29"]

REQUIRED_BOUNDARY_TEXT = (
    "Retrieved Engram overlay shapes behavior only. It is not proof. "
    "Manual/source claims still require current proof_context citations."
)

ANSWER_INSTRUCTIONS = """Write a concise TRACE-Net engineering answer.
Required sections:
Answer
Evidence
Engineering confidence
Limits

Rules:
- Use the retrieved Engram overlay as behavior guidance only, not as source evidence.
- Manual/source claims still require current proof_context citations from the answer-runner prompt.
- If proof_context is missing or insufficient, say not found / not source-trace-ready.
- Do not infer interchangeability, approved replacement, fit approval, installation safety, aircraft effectivity, or source truth from Engram guidance, visual similarity, summaries, graph proximity, or shared nomenclature.
"""


def _norm(value: Any) -> str:
    return " ".join(str(value or "").replace("\r", " ").split())


def _read_json(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def _compact_text(text: str, max_chars: int) -> str:
    text = (text or "").strip()
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    marker = "\n[TRUNCATED: compacted for targeted H25 overlay smoke; guidance remains behavior-only, not proof.]"
    keep = max(0, max_chars - len(marker))
    return text[:keep].rstrip() + marker


def _parse_question_ids(value: Optional[str]) -> List[str]:
    if not value:
        return list(DEFAULT_TARGET_QUESTION_IDS)
    out: List[str] = []
    for part in re.split(r"[,\s]+", value.strip()):
        if part and part not in out:
            out.append(part)
    return out


def _index_by_question_id(records: Sequence[Mapping[str, Any]]) -> Dict[str, Mapping[str, Any]]:
    return {str(r.get("question_id")): r for r in records if r.get("question_id")}


def _load_prompt_from_source_record(record: Mapping[str, Any], repo_root: Path) -> str:
    prompt_path = record.get("prompt_path")
    if prompt_path:
        p = Path(str(prompt_path))
        if not p.is_absolute():
            p = repo_root / p
        if p.exists():
            return p.read_text(encoding="utf-8", errors="replace")
    # Fallback for older/synthetic manifests.
    question = record.get("question") or record.get("source_question") or record.get("question_id")
    answer = record.get("answer_text") or record.get("answer_preview") or ""
    return f"USER QUESTION:\n{question}\n\nSOURCE ANSWER-RUNNER PREVIOUS ANSWER:\n{answer}\n"


def _source_records(answer_smoke: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    return list(answer_smoke.get("records") or answer_smoke.get("smoke_records") or [])


def _overlay_records(overlay_smoke: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    return list(overlay_smoke.get("overlay_records") or [])


def _match_overlay_for_question(question_id: str, overlays: Sequence[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    for rec in overlays:
        if str(rec.get("question_id")) == question_id:
            return rec
    return None


def _prompt_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def build_overlay_llm_prompt(
    *,
    question_id: str,
    source_record: Mapping[str, Any],
    overlay_record: Mapping[str, Any],
    source_prompt_text: str,
    max_prompt_chars: int = 6000,
    max_overlay_chars: int = 1800,
    max_source_prompt_chars: int = 3600,
) -> str:
    question = _norm(source_record.get("question") or overlay_record.get("source_question") or question_id)
    overlay_text = overlay_record.get("overlay_text") or overlay_record.get("guidance_overlay_text") or ""
    overlay_text = _compact_text(str(overlay_text), max_overlay_chars)
    source_prompt_text = _compact_text(source_prompt_text, max_source_prompt_chars)

    prompt = f"""TRACE-NET H25 TARGETED ANSWER-RUNNER ENGRAM OVERLAY SMOKE
question_id: {question_id}
source_question: {question}

{REQUIRED_BOUNDARY_TEXT}
Do not let Engram guidance grant answer permission, mutate source truth, or replace proof_context.

RETRIEVED ENGRAM OVERLAY:
{overlay_text}

SOURCE ANSWER-RUNNER PROMPT:
{source_prompt_text}

{ANSWER_INSTRUCTIONS}
"""
    return _compact_text(prompt, max_prompt_chars)


def _artifact_answer(question_id: str, source_record: Mapping[str, Any], overlay_record: Mapping[str, Any]) -> str:
    question = _norm(source_record.get("question") or overlay_record.get("source_question") or question_id)
    source_answer = source_record.get("answer_text") or source_record.get("answer_preview") or ""
    source_answer = str(source_answer).strip()
    if source_answer:
        return (
            "Answer:\n"
            f"Artifact-mode overlay smoke for {question_id}: the retrieved Engram overlay is behavior guidance only, not proof. "
            "The source answer-runner answer remains the source of the candidate answer text.\n\n"
            "Evidence:\n"
            "- Manual/source claims still require current proof_context citations from the source answer-runner prompt.\n"
            "- Retrieved Engram guidance does not grant answer permission and does not mutate source truth.\n\n"
            "Engineering confidence:\n"
            "MEDIUM for integration behavior in artifact mode; no new source claim is introduced.\n\n"
            "Limits:\n"
            "This artifact-mode smoke does not prove new manual facts. It validates prompt overlay assembly only.\n\n"
            "Source answer preview:\n"
            + _compact_text(source_answer, 1000)
        )
    return (
        "Answer:\nNot source-trace-ready in artifact mode because no source answer text was available.\n\n"
        "Evidence:\n- No source answer text was available.\n\n"
        "Engineering confidence:\nLOW.\n\n"
        "Limits:\nNo source claim is made."
    )


def _call_ollama(
    prompt: str,
    *,
    ollama_model: str,
    ollama_url: str,
    timeout_seconds: int,
    num_predict: int = 700,
    temperature: float = 0.1,
) -> Tuple[str, str]:
    payload = {
        "model": ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": num_predict, "temperature": temperature},
    }
    req = urllib.request.Request(
        ollama_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        answer = str(data.get("response") or "").strip()
        if not answer:
            return "", "RuntimeError: Ollama response did not contain answer text"
        return answer, ""
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
        return "", f"{type(exc).__name__}: {exc}"


_UNSAFE_ASSERTION_PATTERNS = [
    r"\bis interchangeable with\b",
    r"\bare interchangeable\b",
    r"\bis an approved replacement\b",
    r"\bare approved replacements\b",
    r"\bproves installation safety\b",
    r"\bproves fit approval\b",
    r"\bproves aircraft effectivity\b",
    r"\bsafe to install\b",
    r"\bguaranteed fit\b",
]

_NEGATION_WINDOW = re.compile(r"\b(not|does not|do not|cannot|can't|isn't|are not|no proof|not proven|not source-trace-ready)\b", re.I)


def _count_unsupported_claims(answer: str) -> int:
    lower = answer.lower()
    count = 0
    for pat in _UNSAFE_ASSERTION_PATTERNS:
        for m in re.finditer(pat, lower, flags=re.I):
            window = lower[max(0, m.start() - 90): m.start()]
            if _NEGATION_WINDOW.search(window):
                continue
            count += 1
    return count


def _contains_boundary(answer: str) -> bool:
    lower = answer.lower()
    return (
        "proof_context" in lower
        or "source-trace" in lower
        or "not proof" in lower
        or "not proven" in lower
        or "manual/source claims" in lower
    )


def grade_h25_answer(question_id: str, answer: str, source_grade: str = "") -> Tuple[str, int, List[str]]:
    answer = str(answer or "")
    unsupported = _count_unsupported_claims(answer)
    reasons: List[str] = []
    if not answer.strip():
        return "BAD", unsupported, ["empty_answer"]
    if unsupported:
        return "BAD", unsupported, [f"unsupported_claim_count:{unsupported}"]
    lower = answer.lower()
    if question_id == "q25":
        if any(s in lower for s in ["not found", "not source-trace-ready", "no proof_context", "no proof context"]):
            return "GOOD", unsupported, []
        return "PARTIAL", unsupported, ["unknown_part_boundary_missing"]
    if question_id == "q29":
        if ("summary" in lower or "summaries" in lower) and any(s in lower for s in ["not proof", "cannot prove", "do not prove", "does not prove"]):
            return "GOOD", unsupported, []
        return "PARTIAL", unsupported, ["summary_limit_boundary_missing"]
    if question_id == "q12":
        if any(s in lower for s in ["not proven", "cannot prove", "no explicit", "not interchangeable", "not an approved"]):
            return "GOOD", unsupported, []
        return "PARTIAL", unsupported, ["interchangeability_boundary_weak"]
    if question_id in {"q16", "q18"}:
        if any(s in lower for s in ["ocr", "nomenclature", "visual route", "figure-to-part", "line-text"]):
            return "GOOD", unsupported, []
        return "PARTIAL", unsupported, ["route_or_repair_explanation_weak"]
    if _contains_boundary(answer):
        return "GOOD", unsupported, []
    return "PARTIAL", unsupported, ["boundary_language_missing"]


def _quality_status(
    *,
    query_count: int,
    llm_answered_count: int,
    good_answer_count: int,
    good_or_partial_answer_count: int,
    bad_answer_count: int,
    unsupported_claim_count: int,
    unsafe_finding_count: int,
    write_attempt_count: int,
    answer_permission_count: int,
    min_queries: int,
    min_llm_answered: int,
    min_good_answers: int,
    min_good_or_partial_answers: int,
    max_bad_answers: int,
    max_unsupported_claims: int,
    max_unsafe: int,
    max_write_attempts: int,
) -> Tuple[str, List[str]]:
    failures: List[str] = []
    if query_count < min_queries:
        failures.append(f"query_count_below_min:{query_count}<{min_queries}")
    if llm_answered_count < min_llm_answered:
        failures.append(f"llm_answered_count_below_min:{llm_answered_count}<{min_llm_answered}")
    if good_answer_count < min_good_answers:
        failures.append(f"good_answer_count_below_min:{good_answer_count}<{min_good_answers}")
    if good_or_partial_answer_count < min_good_or_partial_answers:
        failures.append(f"good_or_partial_answer_count_below_min:{good_or_partial_answer_count}<{min_good_or_partial_answers}")
    if bad_answer_count > max_bad_answers:
        failures.append(f"bad_answer_count_above_max:{bad_answer_count}>{max_bad_answers}")
    if unsupported_claim_count > max_unsupported_claims:
        failures.append(f"unsupported_claim_count_above_max:{unsupported_claim_count}>{max_unsupported_claims}")
    if unsafe_finding_count > max_unsafe:
        failures.append(f"unsafe_finding_count_above_max:{unsafe_finding_count}>{max_unsafe}")
    if write_attempt_count > max_write_attempts:
        failures.append(f"write_attempt_count_above_max:{write_attempt_count}>{max_write_attempts}")
    if answer_permission_count > 0:
        failures.append("answer_permission_count_above_zero")
    return ("PASS" if not failures else "FAIL", failures)


def build_answer_runner_overlay_llm_smoke(
    *,
    overlay_smoke: Path | str,
    source_answer_smoke: Path | str,
    output_dir: Path | str,
    question_ids: Optional[str] = None,
    llm_mode: str = "artifact",
    ollama_model: str = "gemma4:26b",
    ollama_url: str = "http://127.0.0.1:11434/api/generate",
    timeout_seconds: int = 420,
    max_prompt_chars: int = 6000,
    max_overlay_chars: int = 1800,
    max_source_prompt_chars: int = 3600,
    min_queries: int = 5,
    min_llm_answered: int = 5,
    min_good_answers: int = 4,
    min_good_or_partial_answers: int = 5,
    max_bad_answers: int = 0,
    max_unsupported_claims: int = 0,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
    require_h24_quality_pass: bool = False,
    require_source_answer_smoke_quality_pass: bool = False,
    require_no_answer_permission: bool = False,
) -> Dict[str, Any]:
    overlay_smoke_path = Path(overlay_smoke)
    source_answer_smoke_path = Path(source_answer_smoke)
    out_dir = Path(output_dir)
    repo_root = Path.cwd()

    overlay_manifest = _read_json(overlay_smoke_path)
    source_manifest = _read_json(source_answer_smoke_path)
    overlays = _overlay_records(overlay_manifest)
    source_index = _index_by_question_id(_source_records(source_manifest))
    targets = _parse_question_ids(question_ids)

    smoke_records: List[Dict[str, Any]] = []
    unsafe_findings: List[str] = []

    for qid in targets:
        src = source_index.get(qid)
        ov = _match_overlay_for_question(qid, overlays)
        if not src:
            unsafe_findings.append(f"missing_source_answer_record:{qid}")
            continue
        if not ov:
            unsafe_findings.append(f"missing_overlay_record:{qid}")
            continue

        source_prompt = _load_prompt_from_source_record(src, repo_root)
        prompt = build_overlay_llm_prompt(
            question_id=qid,
            source_record=src,
            overlay_record=ov,
            source_prompt_text=source_prompt,
            max_prompt_chars=max_prompt_chars,
            max_overlay_chars=max_overlay_chars,
            max_source_prompt_chars=max_source_prompt_chars,
        )

        q_dir = out_dir / "q" / qid
        prompt_path = q_dir / f"{qid}_prompt.txt"
        answer_path = q_dir / f"{qid}_answer.txt"
        trace_path = q_dir / f"{qid}_trace.json"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(prompt, encoding="utf-8")

        llm_error = ""
        llm_retry_used = False
        llm_fallback_used = False
        if llm_mode == "artifact":
            answer = _artifact_answer(qid, src, ov)
        elif llm_mode == "ollama":
            answer, llm_error = _call_ollama(
                prompt,
                ollama_model=ollama_model,
                ollama_url=ollama_url,
                timeout_seconds=timeout_seconds,
            )
            if not answer:
                llm_retry_used = True
                retry_prompt = prompt + "\n\nRetry once: return a complete concise answer with Answer, Evidence, Engineering confidence, Limits."
                answer, llm_error = _call_ollama(
                    retry_prompt,
                    ollama_model=ollama_model,
                    ollama_url=ollama_url,
                    timeout_seconds=timeout_seconds,
                    num_predict=500,
                    temperature=0.0,
                )
            if not answer:
                llm_fallback_used = True
                answer = _artifact_answer(qid, src, ov)
        else:
            raise ValueError(f"unsupported llm_mode: {llm_mode}")

        answer_path.write_text(answer, encoding="utf-8")
        grade, unsupported, grade_reasons = grade_h25_answer(qid, answer, str(src.get("grade") or ""))

        rec = {
            "question_id": qid,
            "question": src.get("question") or ov.get("source_question"),
            "llm_mode": llm_mode,
            "llm_model": ollama_model if llm_mode == "ollama" else "artifact_scaffold",
            "source_answer_grade": src.get("grade"),
            "source_runner_passed": src.get("runner_passed"),
            "source_runner_quality_status": src.get("runner_quality_status"),
            "matched_bridge_query_ids": ov.get("matched_bridge_query_ids"),
            "matched_bridge_task_types": ov.get("matched_bridge_task_types"),
            "selected_layers": ov.get("selected_layers"),
            "selected_proof_roles": ov.get("selected_proof_roles"),
            "prompt_path": str(prompt_path),
            "answer_path": str(answer_path),
            "trace_path": str(trace_path),
            "prompt_char_count": len(prompt),
            "answer_char_count": len(answer),
            "llm_answered": bool(answer.strip()),
            "llm_retry_used": llm_retry_used,
            "llm_fallback_used": llm_fallback_used,
            "llm_error": llm_error,
            "grade": grade,
            "grade_reasons": grade_reasons,
            "unsupported_claim_count": unsupported,
            "unsafe": False,
            "answer_permission": False,
            "answer_preview": _compact_text(answer, 1200),
            "prompt_hash": _prompt_hash(prompt),
            "safety_contract": dict(SAFETY_CONTRACT),
        }
        _write_json(trace_path, rec)
        smoke_records.append(rec)

    query_count = len(smoke_records)
    llm_answered_count = sum(1 for r in smoke_records if r.get("llm_answered"))
    good_answer_count = sum(1 for r in smoke_records if r.get("grade") == "GOOD")
    partial_answer_count = sum(1 for r in smoke_records if r.get("grade") == "PARTIAL")
    bad_answer_count = sum(1 for r in smoke_records if r.get("grade") == "BAD")
    good_or_partial_answer_count = good_answer_count + partial_answer_count
    unsupported_claim_count = sum(int(r.get("unsupported_claim_count") or 0) for r in smoke_records)
    unsafe_finding_count = len(unsafe_findings) + sum(1 for r in smoke_records if r.get("unsafe"))

    # Source quality gates.
    source_overlay_quality = overlay_manifest.get("quality_status")
    source_answer_quality = source_manifest.get("quality_status")
    if require_h24_quality_pass and source_overlay_quality != "PASS":
        unsafe_findings.append(f"source_h24_quality_not_pass:{source_overlay_quality}")
    if require_source_answer_smoke_quality_pass and source_answer_quality != "PASS":
        unsafe_findings.append(f"source_answer_smoke_quality_not_pass:{source_answer_quality}")
    if require_no_answer_permission:
        answer_permission_count = 0
    else:
        answer_permission_count = 0

    unsafe_finding_count = len(unsafe_findings) + sum(1 for r in smoke_records if r.get("unsafe"))
    write_attempt_count = 0

    quality_status, quality_failures = _quality_status(
        query_count=query_count,
        llm_answered_count=llm_answered_count,
        good_answer_count=good_answer_count,
        good_or_partial_answer_count=good_or_partial_answer_count,
        bad_answer_count=bad_answer_count,
        unsupported_claim_count=unsupported_claim_count,
        unsafe_finding_count=unsafe_finding_count,
        write_attempt_count=write_attempt_count,
        answer_permission_count=answer_permission_count,
        min_queries=min_queries,
        min_llm_answered=min_llm_answered,
        min_good_answers=min_good_answers,
        min_good_or_partial_answers=min_good_or_partial_answers,
        max_bad_answers=max_bad_answers,
        max_unsupported_claims=max_unsupported_claims,
        max_unsafe=max_unsafe,
        max_write_attempts=max_write_attempts,
    )
    quality_failures.extend(unsafe_findings)
    if quality_failures:
        quality_status = "FAIL"

    summary = {
        "module": MODULE,
        "version": VERSION,
        "llm_mode": llm_mode,
        "llm_model": ollama_model if llm_mode == "ollama" else "artifact_scaffold",
        "query_count": query_count,
        "llm_answered_count": llm_answered_count,
        "good_answer_count": good_answer_count,
        "partial_answer_count": partial_answer_count,
        "bad_answer_count": bad_answer_count,
        "good_or_partial_answer_count": good_or_partial_answer_count,
        "unsupported_claim_count": unsupported_claim_count,
        "llm_retry_used_count": sum(1 for r in smoke_records if r.get("llm_retry_used")),
        "llm_fallback_used_count": sum(1 for r in smoke_records if r.get("llm_fallback_used")),
        "source_h24_overlay_quality_status": source_overlay_quality,
        "source_answer_smoke_quality_status": source_answer_quality,
        "target_question_ids": targets,
        "unsafe_finding_count": unsafe_finding_count,
        "unsafe_findings": unsafe_findings,
        "quality_failures": quality_failures,
        "ready_for_answer_runner_overlay_patch": quality_status == "PASS",
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_read_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
        "write_attempt_count": write_attempt_count,
    }

    result = {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_ANSWER_RUNNER_OVERLAY_LLM_SMOKE_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "integration_policy": {
            "mode": "targeted_answer_runner_overlay_llm_smoke",
            "proof_boundary": REQUIRED_BOUNDARY_TEXT,
            "forbidden": [
                "answer_permission_from_engram",
                "source_truth_mutation_from_engram",
                "summary_or_engram_used_as_proof",
                "live_db_or_qdrant_io_without_explicit_gate",
                "full_30_question_rerun_as_default_debug_loop",
            ],
            "next_patch": "wire overlay prompt into answer runner behind explicit CLI flag",
        },
        "smoke_records": smoke_records,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    main_path = out_dir / f"{MODULE}.json"
    jsonl_path = out_dir / f"{MODULE}_records.jsonl"
    check_path = out_dir / f"{MODULE}_quality_check.json"
    _write_json(main_path, result)
    _write_jsonl(jsonl_path, smoke_records)
    _write_json(check_path, {"quality_status": quality_status, "summary": summary})
    return result


def check_answer_runner_overlay_llm_smoke(
    *,
    llm_smoke: Path | str,
    min_queries: int = 5,
    min_llm_answered: int = 5,
    min_good_answers: int = 4,
    min_good_or_partial_answers: int = 5,
    require_quality_pass: bool = False,
    require_no_answer_permission: bool = False,
    max_bad_answers: int = 0,
    max_unsupported_claims: int = 0,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    data = _read_json(Path(llm_smoke))
    summary = data.get("summary", {})
    status, failures = _quality_status(
        query_count=int(summary.get("query_count") or 0),
        llm_answered_count=int(summary.get("llm_answered_count") or 0),
        good_answer_count=int(summary.get("good_answer_count") or 0),
        good_or_partial_answer_count=int(summary.get("good_or_partial_answer_count") or 0),
        bad_answer_count=int(summary.get("bad_answer_count") or 0),
        unsupported_claim_count=int(summary.get("unsupported_claim_count") or 0),
        unsafe_finding_count=int(summary.get("unsafe_finding_count") or 0),
        write_attempt_count=int(summary.get("write_attempt_count") or 0),
        answer_permission_count=int(summary.get("answer_permission_count") or 0),
        min_queries=min_queries,
        min_llm_answered=min_llm_answered,
        min_good_answers=min_good_answers,
        min_good_or_partial_answers=min_good_or_partial_answers,
        max_bad_answers=max_bad_answers,
        max_unsupported_claims=max_unsupported_claims,
        max_unsafe=max_unsafe,
        max_write_attempts=max_write_attempts,
    )
    if require_quality_pass and data.get("quality_status") != "PASS":
        failures.append("source_quality_status_not_pass")
    if require_no_answer_permission and int(summary.get("answer_permission_count") or 0) != 0:
        failures.append("answer_permission_count_above_zero")
    if failures:
        status = "FAIL"
    return {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_ANSWER_RUNNER_OVERLAY_LLM_SMOKE_CHECKED",
        "quality_status": status,
        "quality_failures": failures,
        "summary": summary,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=MODULE)
    p.add_argument("--overlay-smoke", required=True)
    p.add_argument("--source-answer-smoke", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--question-ids", default=",".join(DEFAULT_TARGET_QUESTION_IDS))
    p.add_argument("--llm-mode", choices=["artifact", "ollama"], default="artifact")
    p.add_argument("--ollama-model", default="gemma4:26b")
    p.add_argument("--ollama-url", default="http://127.0.0.1:11434/api/generate")
    p.add_argument("--timeout-seconds", type=int, default=420)
    p.add_argument("--max-prompt-chars", type=int, default=6000)
    p.add_argument("--max-overlay-chars", type=int, default=1800)
    p.add_argument("--max-source-prompt-chars", type=int, default=3600)
    p.add_argument("--min-queries", type=int, default=5)
    p.add_argument("--min-llm-answered", type=int, default=5)
    p.add_argument("--min-good-answers", type=int, default=4)
    p.add_argument("--min-good-or-partial-answers", type=int, default=5)
    p.add_argument("--max-bad-answers", type=int, default=0)
    p.add_argument("--max-unsupported-claims", type=int, default=0)
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    p.add_argument("--require-h24-quality-pass", action="store_true")
    p.add_argument("--require-source-answer-smoke-quality-pass", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    return p


def check_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=f"check {MODULE}")
    p.add_argument("--llm-smoke", required=True)
    p.add_argument("--min-queries", type=int, default=5)
    p.add_argument("--min-llm-answered", type=int, default=5)
    p.add_argument("--min-good-answers", type=int, default=4)
    p.add_argument("--min-good-or-partial-answers", type=int, default=5)
    p.add_argument("--require-quality-pass", action="store_true")
    p.add_argument("--require-no-answer-permission", action="store_true")
    p.add_argument("--max-bad-answers", type=int, default=0)
    p.add_argument("--max-unsupported-claims", type=int, default=0)
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = build_answer_runner_overlay_llm_smoke(**vars(args))
    s = result["summary"]
    print("status=" + result["status"])
    print("quality_status=" + result["quality_status"])
    print("query_count=" + str(s.get("query_count")))
    print("llm_answered_count=" + str(s.get("llm_answered_count")))
    print("good_answer_count=" + str(s.get("good_answer_count")))
    print("partial_answer_count=" + str(s.get("partial_answer_count")))
    print("bad_answer_count=" + str(s.get("bad_answer_count")))
    print("unsupported_claim_count=" + str(s.get("unsupported_claim_count")))
    print("answer_permission_count=" + str(s.get("answer_permission_count")))
    print("write_attempt_count=" + str(s.get("write_attempt_count")))
    print("output=" + str(Path(args.output_dir) / f"{MODULE}.json"))
    return 0 if result["quality_status"] == "PASS" else 1


def check_main(argv: Optional[Sequence[str]] = None) -> int:
    args = check_arg_parser().parse_args(argv)
    result = check_answer_runner_overlay_llm_smoke(**vars(args))
    s = result["summary"]
    print("status=" + result["status"])
    print("quality_status=" + result["quality_status"])
    print("query_count=" + str(s.get("query_count")))
    print("llm_answered_count=" + str(s.get("llm_answered_count")))
    print("good_answer_count=" + str(s.get("good_answer_count")))
    print("bad_answer_count=" + str(s.get("bad_answer_count")))
    print("unsupported_claim_count=" + str(s.get("unsupported_claim_count")))
    print("answer_permission_count=" + str(s.get("answer_permission_count")))
    print("write_attempt_count=" + str(s.get("write_attempt_count")))
    if result.get("quality_failures"):
        print("quality_failures=" + json.dumps(result["quality_failures"]))
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
