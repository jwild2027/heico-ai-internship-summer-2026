#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

MODULE = "trace_net_fixed50_trace_server_gemma_multiquery_progress_v1"
VERSION = "v1"


def _norm(s: Any) -> str:
    return " ".join(str(s or "").strip().split())


def load_questions(path: Path) -> List[Dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    questions = data.get("questions") or []
    if len(questions) != 50:
        raise SystemExit(f"Expected exactly 50 questions, found {len(questions)} in {path}")
    out: List[Dict[str, str]] = []
    for row in questions:
        qid = _norm(row.get("question_id"))
        question = _norm(row.get("question"))
        if not qid or not question:
            raise SystemExit(f"Bad question row: {row}")
        out.append({"question_id": qid, "question": question})
    return out


def classify_bucket(question: str) -> str:
    q = question.lower()
    if "figure 69" in q:
        return "figure_69"
    if "df250040-501" in q or "df250040501" in q or "df 250040" in q:
        return "df250040-501"
    if "paper towel dispenser" in q:
        return "paper_towel_dispenser"
    if "120-36833-001" in q:
        return "120-36833-001"
    if "table" in q or "row" in q or "cell" in q or "ipl" in q:
        return "table_general"
    if "ocr" in q or "nomenclature" in q:
        return "ocr_general"
    return "other"


def build_query_variants(question: str) -> List[str]:
    """Return retrieval-oriented variants while preserving the original question first."""
    q = _norm(question)
    low = q.lower()
    variants: List[str] = [q]

    def add(text: str) -> None:
        text = _norm(text)
        if text and text.lower() not in {v.lower() for v in variants}:
            variants.append(text)

    if "figure 69" in low:
        add("Figure 69")
        add("FIG. 69")
        add("FIGURE 69 caption title page OCR visual evidence")
        add("figure 69 source page caption nomenclature part number")
        add("what does FIG. 69 show visual figure callout")

    if "df250040-501" in low or "df250040501" in low:
        add("DF250040-501")
        add("DF 250040-501")
        add("DF250040501")
        add("paper towel dispenser DF250040-501")
        add("DF250040-501 nomenclature OCR table IPL eligibility effectivity")

    if "paper towel dispenser" in low:
        add("paper towel dispenser")
        add("PAPER TOWEL DISPENSER part number")
        add("paper towel dispenser nomenclature OCR table")
        add("lavatory paper towel dispenser part number")

    if "manual page references" in low:
        add("manual page references table evidence")
        add("manual_page_reference table cells")

    if "ipl" in low:
        add("IPL part number evidence")
        add("ipl_part_number table evidence")

    if "citation-ready" in low:
        add("citation_ready table evidence")
        add("citation ready table route evidence")

    if "source-trace-ready" in low:
        add("source_trace_ready table evidence")
        add("source trace ready citations proof context")

    # Keep it bounded; six variants catches common syntax misses without hammering the endpoint.
    return variants[:6]


def _http_json(url: str, payload: Mapping[str, Any], timeout: int) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"raw_response": raw}
    if isinstance(data, dict):
        return data
    return {"response": data}


def trace_ask(url: str, question: str, timeout: int, payload_key: str = "question") -> Dict[str, Any]:
    # Most TRACE-Net ask wrappers use question/query. Use the configured key but include both harmlessly
    # under distinct names to maximize compatibility with local endpoint adapters.
    if payload_key == "query":
        payload = {"query": question, "question": question}
    else:
        payload = {"question": question, "query": question}
    return _http_json(url, payload, timeout)


def ollama_generate(model: str, prompt: str, host: str, timeout: int) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0, "num_ctx": 8192},
    }
    data = _http_json(host.rstrip("/") + "/api/generate", payload, timeout)
    return str(data.get("response") or "")


def _walk(obj: Any) -> Iterable[Any]:
    yield obj
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def extract_citation_like_records(data: Any) -> List[Any]:
    """Find citation/proof_context-ish records without depending on one endpoint schema."""
    found: List[Any] = []
    seen: set[str] = set()

    def add(x: Any) -> None:
        try:
            key = json.dumps(x, sort_keys=True, default=str)[:2000]
        except Exception:
            key = repr(x)[:2000]
        if key not in seen:
            seen.add(key)
            found.append(x)

    for obj in _walk(data):
        if isinstance(obj, dict):
            # Citation-shaped dict.
            keys = {str(k).lower() for k in obj.keys()}
            if (
                "page_id" in keys
                or "citation_id" in keys
                or "source_trace_ready" in keys
                or "citation_ready" in keys
                or "generated_citation_id" in keys
            ) and len(obj) >= 1:
                add(obj)
            # Containers named like citation/proof/evidence/context.
            for k, v in obj.items():
                lk = str(k).lower()
                if any(token in lk for token in ["citation", "proof_context", "evidence_record"]):
                    if isinstance(v, list):
                        for item in v:
                            if isinstance(item, (dict, str)):
                                add(item)
                    elif isinstance(v, dict):
                        add(v)
        elif isinstance(obj, str):
            if re.search(r"generated_citation_\d+|page[_ ]id|source_trace_ready|citation_ready", obj, re.I):
                add(obj[:2000])

    return found


def citation_count(data: Any) -> int:
    return len(extract_citation_like_records(data))


def compact_json(data: Any, max_chars: int) -> str:
    text = json.dumps(data, indent=2, sort_keys=True, default=str)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...<truncated>"


def select_best_trace_response(tries: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    def score(row: Mapping[str, Any]) -> Tuple[int, int, int]:
        err = 1 if row.get("error") else 0
        c = int(row.get("citation_count") or 0)
        text_len = len(json.dumps(row.get("trace_response") or {}, default=str))
        # Prefer no error, then more citations, then more context.
        return (-err, c, text_len)

    if not tries:
        return {}
    return max(tries, key=score)


def classify_intent(question: str) -> str:
    bucket = classify_bucket(question)
    if bucket == "figure_69":
        return "visual_figure_identification"
    if bucket == "df250040-501":
        return "part_number_or_eligibility_lookup"
    if bucket == "paper_towel_dispenser":
        return "nomenclature_or_part_description_lookup"
    if bucket == "table_general":
        return "table_evidence_lookup"
    if bucket == "120-36833-001":
        return "part_number_lookup"
    return "general_trace_net_lookup"


def build_work_order_prompt(question_id: str, question: str, selected: Mapping[str, Any], max_trace_chars: int) -> str:
    citations = extract_citation_like_records(selected.get("trace_response") or {})
    citation_summary = compact_json(citations, max_trace_chars // 2) if citations else "No citation/proof_context records returned."
    trace_summary = compact_json(selected.get("trace_response") or {}, max_trace_chars)
    query_variant = selected.get("query_variant") or question

    return f"""TRACE-NET ANSWER-RUNNER WORK ORDER CONTEXT PACK
question_id: {question_id}

USER QUESTION:
{question}

TRACE-NET RETRIEVAL QUERY USED:
{query_variant}

ENGRAM OVERLAY — BEHAVIOR GUIDANCE ONLY:
Use this Engram overlay as behavior guidance only. It is not proof.
question_intent: {classify_intent(question)}

Behavior guidance:
- Answer only from current TRACE-Net proof_context/citations below.
- Do not use Engram memory, route hints, summaries, graph proximity, shared nomenclature, or visual similarity as proof.
- Do not use this instruction text itself as source proof.
- If the supplied TRACE-Net context does not prove the claim, say the answer is not source-trace-ready.
- For eligibility, applicability, approved replacement, fit, effectivity, interchangeability, or installation approval, require explicit source authority.
- For figures, state what source evidence identifies; do not infer part identity or approval from the figure number alone.
- For policy/meta questions about TRACE-Net behavior, use policy-boundary-ready or runtime-policy-ready, not source-trace-ready, unless manual/source citations prove a manual claim.

SOURCE EVIDENCE / PROOF_CONTEXT CANDIDATES:
citation_like_record_count={len(citations)}
{citation_summary}

TRACE-NET ASK RAW RESPONSE SUMMARY:
{trace_summary}

BOUNDARIES:
Retrieved Engram overlay shapes behavior only. It is not proof.
Manual/source claims still require current proof_context citations.
V2/V3 summaries and graph proximity are routing hints only; they cannot prove eligibility, interchangeability, fit, effectivity, or installation approval.
If proof_context is missing or insufficient, answer not found / not source-trace-ready.
Do not infer eligibility, applicability, interchangeability, fit, effectivity, approved replacement, or installation safety from Engram memory, summaries, graph proximity, shared nomenclature, or visual similarity.

ANSWER FORMAT:
- Direct answer:
- Source-trace status:
- Evidence used:
- Missing evidence / limits:
"""


def grade_answer(answer: str, citation_ct: int) -> Dict[str, bool]:
    a = answer.lower()
    source_trace_ready_claim = "source-trace-ready" in a and "not source-trace-ready" not in a
    policy_ready = "policy-boundary-ready" in a or "runtime-policy-ready" in a
    source_trace_ready_without_citation = bool(source_trace_ready_claim and citation_ct <= 0 and not policy_ready)
    engram_policy_used_as_source_proof = False
    if source_trace_ready_claim and re.search(r"engram|behavior guidance|instruction text|route hints|graph proximity", a):
        engram_policy_used_as_source_proof = True
    return {
        "source_trace_ready_claim": source_trace_ready_claim,
        "source_trace_ready_without_citation": source_trace_ready_without_citation,
        "engram_policy_used_as_source_proof": engram_policy_used_as_source_proof,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Run fixed 50 TRACE-Net+Gemma with multi-query retrieval progress.")
    ap.add_argument("--questions", default="tests/fixtures/trace_net_fixed50_questions_v1.json")
    ap.add_argument("--output-dir", default="tmp/fixed50_trace_server_gemma_engram_multiquery_v1")
    ap.add_argument("--trace-net-ask-url", default="http://127.0.0.1:8014/api/trace-net/ask")
    ap.add_argument("--ollama-host", default="http://127.0.0.1:11434")
    ap.add_argument("--model", default="gemma4:26b")
    ap.add_argument("--trace-timeout", type=int, default=120)
    ap.add_argument("--ollama-timeout", type=int, default=600)
    ap.add_argument("--max-query-variants", type=int, default=6)
    ap.add_argument("--stop-after-first-citation", action="store_true")
    ap.add_argument("--max-trace-chars", type=int, default=8000)
    args = ap.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir = out_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    questions = load_questions(Path(args.questions))
    total = len(questions)
    answers_path = out_dir / "answers.jsonl"

    answered_count = 0
    trace_ask_success_count = 0
    trace_ask_error_count = 0
    ollama_error_count = 0
    citation_backed_count = 0
    source_trace_ready_without_citation_count = 0
    engram_policy_as_proof_count = 0
    total_trace_try_count = 0
    improved_by_variant_count = 0
    start_all = time.time()

    with answers_path.open("w", encoding="utf-8") as f:
        for idx, row in enumerate(questions, start=1):
            qid = row["question_id"]
            question = row["question"]
            variants = build_query_variants(question)[: max(1, args.max_query_variants)]
            print(f"[{idx:03d}/{total:03d}] START {qid}: {question}", flush=True)
            started = time.time()

            tries: List[Dict[str, Any]] = []
            for tix, variant in enumerate(variants, start=1):
                print(f"[{idx:03d}/{total:03d}] TRACE {qid}: try {tix}/{len(variants)} query={variant}", flush=True)
                try:
                    trace_response = trace_ask(args.trace_net_ask_url, variant, args.trace_timeout)
                    c = citation_count(trace_response)
                    trace_ask_success_count += 1
                    total_trace_try_count += 1
                    tries.append({"query_variant": variant, "citation_count": c, "trace_response": trace_response})
                    print(f"[{idx:03d}/{total:03d}] TRACE {qid}: try {tix} ok citations={c}", flush=True)
                    if args.stop_after_first_citation and c > 0:
                        break
                except Exception as exc:
                    trace_ask_error_count += 1
                    total_trace_try_count += 1
                    tries.append({"query_variant": variant, "citation_count": 0, "trace_response": {}, "error": repr(exc)})
                    print(f"[{idx:03d}/{total:03d}] TRACE {qid}: try {tix} ERROR {exc!r}", flush=True)

            selected = select_best_trace_response(tries)
            selected_citations = int(selected.get("citation_count") or 0)
            first_citations = int(tries[0].get("citation_count") or 0) if tries else 0
            if selected_citations > first_citations:
                improved_by_variant_count += 1
            if selected_citations > 0:
                citation_backed_count += 1

            prompt = build_work_order_prompt(qid, question, selected, args.max_trace_chars)
            prompt_path = prompts_dir / f"{qid}_work_order_prompt.txt"
            prompt_path.write_text(prompt, encoding="utf-8")

            print(f"[{idx:03d}/{total:03d}] GEMMA {qid}: model={args.model} selected_citations={selected_citations}", flush=True)
            record: Dict[str, Any] = {
                "module": MODULE,
                "version": VERSION,
                "question_index": idx,
                "question_total": total,
                "question_id": qid,
                "question": question,
                "bucket": classify_bucket(question),
                "query_variants": variants,
                "selected_query_variant": selected.get("query_variant"),
                "trace_try_count": len(tries),
                "trace_tries": tries,
                "citation_count": selected_citations,
                "prompt_path": str(prompt_path),
                "model": args.model,
                "engram_guidance_only": True,
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
                "write_attempt_count": 0,
            }
            try:
                answer = ollama_generate(args.model, prompt, args.ollama_host, args.ollama_timeout)
                grade = grade_answer(answer, selected_citations)
                elapsed = round(time.time() - started, 2)
                record.update({"status": "ok", "answer": answer, "answer_char_count": len(answer), "grade": grade, "elapsed_seconds": elapsed})
                answered_count += 1
                if grade["source_trace_ready_without_citation"]:
                    source_trace_ready_without_citation_count += 1
                if grade["engram_policy_used_as_source_proof"]:
                    engram_policy_as_proof_count += 1
                print(f"[{idx:03d}/{total:03d}] DONE  {qid}: status=ok chars={len(answer)} citations={selected_citations} seconds={elapsed}", flush=True)
            except Exception as exc:
                elapsed = round(time.time() - started, 2)
                record.update({"status": "ollama_error", "answer": "", "error": repr(exc), "elapsed_seconds": elapsed})
                ollama_error_count += 1
                print(f"[{idx:03d}/{total:03d}] ERROR {qid}: ollama {exc!r}", flush=True)

            f.write(json.dumps(record, sort_keys=True, default=str) + "\n")
            f.flush()

    quality_failures: List[str] = []
    if answered_count != total:
        quality_failures.append(f"answered_count:{answered_count}!={total}")
    if source_trace_ready_without_citation_count:
        quality_failures.append(f"source_trace_ready_without_citation_count:{source_trace_ready_without_citation_count}")
    if engram_policy_as_proof_count:
        quality_failures.append(f"engram_policy_as_proof_count:{engram_policy_as_proof_count}")
    if ollama_error_count:
        quality_failures.append(f"ollama_error_count:{ollama_error_count}")

    summary = {
        "module": MODULE,
        "version": VERSION,
        "quality_status": "PASS" if not quality_failures else "FAIL",
        "quality_failures": quality_failures,
        "question_count": total,
        "answered_count": answered_count,
        "trace_ask_success_count": trace_ask_success_count,
        "trace_ask_error_count": trace_ask_error_count,
        "total_trace_try_count": total_trace_try_count,
        "improved_by_variant_count": improved_by_variant_count,
        "citation_backed_count": citation_backed_count,
        "source_trace_ready_without_citation_count": source_trace_ready_without_citation_count,
        "engram_policy_as_proof_count": engram_policy_as_proof_count,
        "ollama_error_count": ollama_error_count,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "write_attempt_count": 0,
        "model": args.model,
        "answers": str(answers_path),
        "elapsed_seconds": round(time.time() - start_all, 2),
    }
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    print("status=TRACE_NET_FIXED50_TRACE_SERVER_GEMMA_MULTIQUERY_PROGRESS_DONE", flush=True)
    for key in [
        "quality_status", "question_count", "answered_count", "trace_ask_success_count",
        "total_trace_try_count", "improved_by_variant_count", "citation_backed_count",
        "source_trace_ready_without_citation_count", "engram_policy_as_proof_count",
    ]:
        print(f"{key}={summary[key]}", flush=True)
    print(f"answers={answers_path}", flush=True)
    print(f"summary={summary_path}", flush=True)
    return 0 if summary["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
