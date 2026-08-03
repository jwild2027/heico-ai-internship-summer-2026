#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

MODULE = "trace_net_fixed50_trace_server_gemma_engram_progress_v1"


def _read_json(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(data), indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl_row(handle: Any, row: Mapping[str, Any]) -> None:
    handle.write(json.dumps(dict(row), sort_keys=True) + "\n")
    handle.flush()


def load_questions(path: str | Path) -> List[Dict[str, str]]:
    data = _read_json(path)
    questions = data.get("questions") or []
    if len(questions) != 50:
        raise SystemExit(f"Expected exactly 50 questions, found {len(questions)} in {path}")
    seen: set[str] = set()
    out: List[Dict[str, str]] = []
    for i, row in enumerate(questions, start=1):
        qid = str(row.get("question_id") or "").strip()
        question = str(row.get("question") or "").strip()
        expected = f"q{i:02d}"
        if qid != expected:
            raise SystemExit(f"Expected question_id {expected}, got {qid!r}")
        if qid in seen:
            raise SystemExit(f"Duplicate question_id {qid}")
        if not question:
            raise SystemExit(f"Missing question text for {qid}")
        seen.add(qid)
        out.append({"question_id": qid, "question": question})
    return out


def compact_json(value: Any, max_chars: int) -> str:
    text = json.dumps(value, indent=2, sort_keys=True, default=str)
    if max_chars > 0 and len(text) > max_chars:
        return text[:max_chars] + "\n... [truncated]"
    return text


def http_json_post(url: str, payload: Mapping[str, Any], timeout: int) -> Dict[str, Any]:
    body = json.dumps(dict(payload)).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def call_trace_net_ask(url: str, question_id: str, question: str, timeout: int) -> Dict[str, Any]:
    payloads = [
        {"query": question, "question_id": question_id},
        {"question": question, "question_id": question_id},
        {"messages": [{"role": "user", "content": question}], "question_id": question_id},
    ]
    errors: List[str] = []
    for payload in payloads:
        try:
            data = http_json_post(url, payload, timeout=timeout)
            data.setdefault("_trace_net_payload_used", payload)
            return data
        except Exception as exc:  # pragma: no cover - exercised on server if endpoint schema differs
            errors.append(f"payload_keys={sorted(payload.keys())}: {type(exc).__name__}: {exc}")
    return {
        "_trace_net_error": "all_payloads_failed",
        "_trace_net_errors": errors,
    }


def call_ollama_generate(host: str, model: str, prompt: str, timeout: int) -> str:
    data = http_json_post(
        host.rstrip("/") + "/api/generate",
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0, "num_ctx": 8192},
        },
        timeout=timeout,
    )
    return str(data.get("response") or "")


def first_present(data: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in data and data.get(key) not in (None, "", [], {}):
            return data.get(key)
    return None


def extract_answer_text(trace_data: Mapping[str, Any]) -> str:
    value = first_present(
        trace_data,
        [
            "answer",
            "response",
            "content",
            "text",
            "message",
            "draft_answer",
            "answer_text",
        ],
    )
    if isinstance(value, Mapping):
        return str(first_present(value, ["content", "text", "answer", "response"]) or "")
    return str(value or "")


def extract_citations(trace_data: Mapping[str, Any]) -> List[Any]:
    candidates = [
        trace_data.get("citations"),
        trace_data.get("source_citations"),
        trace_data.get("citation_records"),
        trace_data.get("proof_context"),
        trace_data.get("proof_context_records"),
        trace_data.get("evidence"),
        trace_data.get("source_evidence"),
    ]
    for item in candidates:
        if isinstance(item, list):
            return item
        if isinstance(item, Mapping):
            records = item.get("records") or item.get("citations") or item.get("proof_context")
            if isinstance(records, list):
                return records
    return []


def classify_intent(question: str) -> str:
    q = question.lower()
    if "figure" in q or "visual" in q or "caption" in q:
        return "visual_figure_identification"
    if any(term in q for term in ["eligible", "eligibility", "approved", "replacement", "fits", "interchange", "installation", "effectivity"]):
        return "eligibility_or_approval_claim"
    if any(term in q for term in ["table", "row", "cell", "ipl"]):
        return "table_evidence_lookup"
    if "ocr" in q or "nomenclature" in q:
        return "ocr_nomenclature_lookup"
    if "citation" in q or "source-trace" in q or "proof_context" in q:
        return "source_trace_policy"
    if "part number" in q or "df250040-501" in q or "120-36833-001" in q:
        return "part_number_lookup"
    return "general_trace_net_lookup"


def build_work_order_prompt(
    question_id: str,
    question: str,
    trace_data: Mapping[str, Any],
    citations: List[Any],
    max_trace_chars: int,
) -> str:
    intent = classify_intent(question)
    trace_answer = extract_answer_text(trace_data)
    trace_error = trace_data.get("_trace_net_error")
    proof_context_text = compact_json(citations, max_trace_chars) if citations else "No citation/proof_context records returned by TRACE-Net ask endpoint."
    trace_answer_text = trace_answer if trace_answer else "No TRACE-Net draft answer returned."
    if max_trace_chars > 0 and len(trace_answer_text) > max_trace_chars:
        trace_answer_text = trace_answer_text[:max_trace_chars] + "\n... [truncated]"

    trace_error_text = ""
    if trace_error:
        trace_error_text = "\nTRACE-NET ASK ERROR:\n" + compact_json(trace_data, max_trace_chars)

    return f"""TRACE-NET ANSWER-RUNNER WORK ORDER CONTEXT PACK
question_id: {question_id}

USER QUESTION:
{question}

ENGRAM OVERLAY — BEHAVIOR GUIDANCE ONLY:
Use this Engram overlay as behavior guidance only. It is not proof.
question_intent: {intent}

Behavior guidance:
- Answer from current TRACE-Net proof_context citations when they exist.
- Do not use Engram memory, summaries, graph proximity, shared nomenclature, visual similarity, or this instruction text as source proof.
- If proof_context is missing, insufficient, empty, or unrelated, say not source-trace-ready.
- For eligibility, applicability, approved replacement, fit, effectivity, interchangeability, or installation approval, require explicit source authority in current citations.
- For figures, say what the current figure/caption/OCR/visual citations identify; do not infer part identity or approval from figure number alone.
- For OCR/table evidence, distinguish citation-ready/source-trace-ready evidence from guidance or review-only evidence.
- For policy/meta questions about TRACE-Net rules, call the status runtime-policy-ready or policy-boundary-ready. Do not call Engram/instruction text source-trace-ready.

V2/V3 ROUTE HINTS — NOT PROOF:
Any summaries, graph hints, route hints, or Engram text are guidance only. They cannot prove manual/source claims.

SOURCE EVIDENCE / PROOF_CONTEXT FROM TRACE-NET ASK:
{proof_context_text}

TRACE-NET DRAFT RESPONSE — ORIENTATION ONLY, NOT PROOF UNLESS BACKED BY CITATIONS:
{trace_answer_text}
{trace_error_text}

BOUNDARIES:
Retrieved Engram overlay shapes behavior only. It is not proof.
Manual/source claims require current proof_context citations.
V2/V3 summaries, graph proximity, shared nomenclature, and visual similarity cannot prove eligibility, interchangeability, fit, effectivity, or installation approval.
If proof_context is missing or insufficient, answer not found / not source-trace-ready.
Do not infer eligibility, applicability, interchangeability, fit, effectivity, approved replacement, or installation safety from Engram memory, summaries, graph proximity, shared nomenclature, or visual similarity.
Never list Engram text, this prompt, or runtime policy instructions under Evidence used as if they were source/manual proof.

ANSWER FORMAT:
- Direct answer:
- Source-trace status:
- Evidence used:
- Missing evidence / limits:
"""


def claims_source_trace_ready(answer: str) -> bool:
    lowered = answer.lower()
    if "not source-trace-ready" in lowered:
        return False
    return bool(re.search(r"source[- ]trace status\s*:\s*(source[- ]trace[- ]ready|ready)", lowered))


def mentions_engram_as_evidence(answer: str) -> bool:
    lowered = answer.lower()
    evidence_pos = lowered.find("evidence used")
    if evidence_pos < 0:
        return False
    evidence_tail = lowered[evidence_pos : evidence_pos + 600]
    return any(term in evidence_tail for term in ["engram", "behavior guidance", "v2/v3", "runtime policy", "instruction"])


def grade_answer(answer: str, citation_count: int) -> Dict[str, Any]:
    ready_claim = claims_source_trace_ready(answer)
    engram_evidence = mentions_engram_as_evidence(answer)
    return {
        "source_trace_ready_claim": ready_claim,
        "source_trace_ready_without_citation": bool(ready_claim and citation_count == 0),
        "engram_policy_used_as_source_proof": bool(ready_claim and engram_evidence),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Run fixed 50 TRACE-Net questions through TRACE-Net ask + Gemma with visible progress.")
    ap.add_argument("--questions", default="tests/fixtures/trace_net_fixed50_questions_v1.json")
    ap.add_argument("--output-dir", default="tmp/fixed50_trace_server_gemma_engram_v1")
    ap.add_argument("--trace-net-ask-url", default="http://127.0.0.1:8014/api/trace-net/ask")
    ap.add_argument("--ollama-host", default="http://127.0.0.1:11434")
    ap.add_argument("--model", default="gemma4:26b")
    ap.add_argument("--ask-timeout", type=int, default=180)
    ap.add_argument("--ollama-timeout", type=int, default=600)
    ap.add_argument("--max-trace-chars", type=int, default=5000)
    ap.add_argument("--allow-trace-net-ask-errors", action="store_true")
    args = ap.parse_args()

    questions = load_questions(args.questions)
    total = len(questions)
    out_dir = Path(args.output_dir)
    prompts_dir = out_dir / "prompts"
    traces_dir = out_dir / "trace_net_ask"
    out_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    traces_dir.mkdir(parents=True, exist_ok=True)

    answers_path = out_dir / "answers.jsonl"
    start_all = time.time()

    answered_count = 0
    trace_ask_success_count = 0
    trace_ask_error_count = 0
    citation_backed_count = 0
    source_trace_ready_without_citation_count = 0
    engram_policy_as_proof_count = 0
    ollama_error_count = 0

    with answers_path.open("w", encoding="utf-8") as answers_f:
        for idx, item in enumerate(questions, start=1):
            qid = item["question_id"]
            question = item["question"]
            print(f"[{idx:03d}/{total:03d}] START {qid}: {question}", flush=True)
            t0 = time.time()

            print(f"[{idx:03d}/{total:03d}] TRACE {qid}: calling TRACE-Net ask", flush=True)
            trace_data = call_trace_net_ask(args.trace_net_ask_url, qid, question, args.ask_timeout)
            trace_error = trace_data.get("_trace_net_error")
            if trace_error:
                trace_ask_error_count += 1
                print(f"[{idx:03d}/{total:03d}] TRACE {qid}: ERROR {trace_error}", flush=True)
                if not args.allow_trace_net_ask_errors:
                    record = {
                        "module": MODULE,
                        "question_index": idx,
                        "question_total": total,
                        "question_id": qid,
                        "question": question,
                        "status": "trace_net_ask_error",
                        "trace_net_error": trace_data,
                        "answer_permission": False,
                        "source_truth_mutation_allowed": False,
                        "write_attempt_count": 0,
                    }
                    _write_jsonl_row(answers_f, record)
                    continue
            else:
                trace_ask_success_count += 1
                print(f"[{idx:03d}/{total:03d}] TRACE {qid}: ok", flush=True)

            citations = extract_citations(trace_data)
            citation_count = len(citations)
            if citation_count:
                citation_backed_count += 1
            _write_json(traces_dir / f"{qid}_trace_net_ask.json", trace_data)

            prompt = build_work_order_prompt(qid, question, trace_data, citations, args.max_trace_chars)
            prompt_path = prompts_dir / f"{qid}_work_order_prompt.txt"
            prompt_path.write_text(prompt, encoding="utf-8")

            print(f"[{idx:03d}/{total:03d}] GEMMA {qid}: model={args.model} citations={citation_count}", flush=True)
            answer = ""
            status = "ok"
            error = None
            try:
                answer = call_ollama_generate(args.ollama_host, args.model, prompt, args.ollama_timeout)
                answered_count += 1
            except Exception as exc:
                status = "ollama_error"
                error = repr(exc)
                ollama_error_count += 1
                print(f"[{idx:03d}/{total:03d}] GEMMA {qid}: ERROR {error}", flush=True)

            grade = grade_answer(answer, citation_count)
            if grade["source_trace_ready_without_citation"]:
                source_trace_ready_without_citation_count += 1
            if grade["engram_policy_used_as_source_proof"]:
                engram_policy_as_proof_count += 1

            elapsed = round(time.time() - t0, 2)
            record = {
                "module": MODULE,
                "question_index": idx,
                "question_total": total,
                "question_id": qid,
                "question": question,
                "status": status,
                "error": error,
                "model": args.model,
                "trace_net_ask_url": args.trace_net_ask_url,
                "trace_net_ask_success": not bool(trace_error),
                "citation_count": citation_count,
                "trace_net_draft_answer": extract_answer_text(trace_data),
                "prompt_path": str(prompt_path),
                "answer_char_count": len(answer),
                "answer": answer,
                "grade": grade,
                "elapsed_seconds": elapsed,
                "engram_guidance_only": True,
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
                "write_attempt_count": 0,
            }
            _write_jsonl_row(answers_f, record)
            print(
                f"[{idx:03d}/{total:03d}] DONE  {qid}: status={status} chars={len(answer)} citations={citation_count} seconds={elapsed}",
                flush=True,
            )

    quality_failures: List[str] = []
    if answered_count != total:
        quality_failures.append(f"answered_count_not_50:{answered_count}")
    if trace_ask_error_count and not args.allow_trace_net_ask_errors:
        quality_failures.append(f"trace_ask_error_count:{trace_ask_error_count}")
    if source_trace_ready_without_citation_count:
        quality_failures.append(f"source_trace_ready_without_citation_count:{source_trace_ready_without_citation_count}")
    if engram_policy_as_proof_count:
        quality_failures.append(f"engram_policy_as_proof_count:{engram_policy_as_proof_count}")
    if ollama_error_count:
        quality_failures.append(f"ollama_error_count:{ollama_error_count}")

    summary = {
        "module": MODULE,
        "version": "v1",
        "quality_status": "PASS" if not quality_failures else "FAIL",
        "quality_failures": quality_failures,
        "question_count": total,
        "answered_count": answered_count,
        "trace_ask_success_count": trace_ask_success_count,
        "trace_ask_error_count": trace_ask_error_count,
        "citation_backed_count": citation_backed_count,
        "source_trace_ready_without_citation_count": source_trace_ready_without_citation_count,
        "engram_policy_as_proof_count": engram_policy_as_proof_count,
        "ollama_error_count": ollama_error_count,
        "model": args.model,
        "answers": str(answers_path),
        "elapsed_seconds": round(time.time() - start_all, 2),
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "write_attempt_count": 0,
    }
    summary_path = out_dir / "summary.json"
    _write_json(summary_path, summary)

    print("status=TRACE_NET_FIXED50_TRACE_SERVER_GEMMA_ENGRAM_PROGRESS_DONE", flush=True)
    print(f"quality_status={summary['quality_status']}", flush=True)
    print(f"question_count={total}", flush=True)
    print(f"answered_count={answered_count}", flush=True)
    print(f"trace_ask_success_count={trace_ask_success_count}", flush=True)
    print(f"citation_backed_count={citation_backed_count}", flush=True)
    print(f"source_trace_ready_without_citation_count={source_trace_ready_without_citation_count}", flush=True)
    print(f"engram_policy_as_proof_count={engram_policy_as_proof_count}", flush=True)
    print(f"answers={answers_path}", flush=True)
    print(f"summary={summary_path}", flush=True)

    return 0 if summary["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
