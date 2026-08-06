#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple

MODULE = "trace_net_fixed50_trace_server_gemma_multiquery_df_fallback_v1"


def _read_json(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(data), indent=2, sort_keys=True), encoding="utf-8")


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def load_questions(path: str | Path) -> List[Dict[str, str]]:
    data = _read_json(path)
    qs = data.get("questions") or []
    if len(qs) != 50:
        raise SystemExit(f"Expected exactly 50 questions, found {len(qs)} in {path}")
    out: List[Dict[str, str]] = []
    seen=set()
    for q in qs:
        qid=_norm(q.get("question_id"))
        text=_norm(q.get("question"))
        if not qid or not text:
            raise SystemExit(f"Bad question record: {q}")
        if qid in seen:
            raise SystemExit(f"Duplicate question_id: {qid}")
        seen.add(qid)
        out.append({"question_id": qid, "question": text})
    return out


def _dedupe(items: Iterable[str]) -> List[str]:
    out=[]
    seen=set()
    for item in items:
        x=_norm(item)
        if x and x.lower() not in seen:
            out.append(x)
            seen.add(x.lower())
    return out


def classify_bucket(question: str) -> str:
    q=question.lower()
    if "df250040-501" in q or "df250040" in q:
        return "df250040-501"
    if "figure 69" in q or "fig. 69" in q or "fig 69" in q:
        return "figure_69"
    if "paper towel dispenser" in q:
        return "paper_towel_dispenser"
    if "120-36833-001" in q:
        return "120-36833-001"
    if "table" in q or "row" in q or "cell" in q:
        return "table_general"
    if "ocr" in q or "nomenclature" in q:
        return "ocr_general"
    if any(x in q for x in ["eligib", "approved", "interchange", "installation", "effectivity", "fits", "fit "]):
        return "eligibility_approval_policy"
    return "other"


def classify_intent(question: str) -> str:
    q=question.lower()
    if "df250040-501" in q and any(x in q for x in ["eligible", "eligibility", "approved", "replacement", "fits", "interchange", "installation", "effectivity"]):
        return "df250040_claim_requires_explicit_authority"
    if "figure" in q or "visual" in q or "caption" in q:
        return "visual_figure_identification"
    if any(x in q for x in ["eligible", "eligibility", "approved", "replacement", "fits", "interchange", "installation", "effectivity"]):
        return "eligibility_or_approval_claim"
    if "table" in q or "row" in q or "cell" in q or "ipl" in q:
        return "table_evidence_lookup"
    if "ocr" in q or "nomenclature" in q:
        return "ocr_nomenclature_lookup"
    if "citation" in q or "source-trace" in q or "proof_context" in q:
        return "source_trace_policy"
    if "part number" in q:
        return "part_number_lookup"
    return "general_trace_net_lookup"


def query_variants(question: str, max_variants: int = 10) -> List[str]:
    q=_norm(question)
    low=q.lower()
    variants=[q]

    if "figure 69" in low or "fig. 69" in low or "fig 69" in low:
        variants += [
            "Figure 69",
            "FIG. 69",
            "fig 69 caption title page OCR visual evidence",
            "figure 69 part number nomenclature visual assembly",
            "figure 69 installation eligibility interchangeability effectivity",
        ]

    if "df250040-501" in low or "df250040" in low:
        # Important: for eligibility/approval questions, always include the bare part queries as fallback context.
        variants += [
            "DF250040-501",
            "DF250040501",
            "DF250040 501",
            "DF250040",
            "250040-501",
            "DF250040-501 nomenclature",
            "DF250040-501 OCR",
            "DF250040-501 table evidence",
            "DF250040-501 effectivity",
            "DF250040-501 eligibility applicability approved installation interchangeability",
        ]
        platforms=[]
        for token in ["A319", "A320", "A321", "737", "787", "B737", "B787", "Boeing 737", "Boeing 787"]:
            if token.lower() in low:
                platforms.append(token)
        for platform in platforms:
            variants += [
                f"DF250040-501 {platform}",
                f"DF250040-501 {platform} eligibility applicability effectivity",
                f"DF250040-501 {platform} approved installation",
            ]

    if "paper towel dispenser" in low:
        variants += [
            "paper towel dispenser",
            "paper towel dispenser part number",
            "paper towel dispenser nomenclature OCR table",
            "DF250040-501 paper towel dispenser",
            "120-36833-001 paper towel dispenser",
        ]

    if "120-36833-001" in low:
        variants += [
            "120-36833-001",
            "12036833001",
            "120 36833 001",
            "120-36833-001 nomenclature OCR table covered part number",
        ]

    if "table" in low or "row" in low or "cell" in low:
        variants += [
            "table evidence citation ready source trace ready",
            "table rows part number",
            "table cells manual page references",
            "table values human review required",
        ]

    if "ocr" in low:
        variants += [q.replace("OCR", "raw OCR"), q + " OCR nomenclature window source trace"]

    return _dedupe(variants)[:max(1, max_variants)]


def post_json(url: str, payload: Mapping[str, Any], timeout: int) -> Dict[str, Any]:
    req=urllib.request.Request(
        url,
        data=json.dumps(dict(payload)).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def trace_ask(url: str, query: str, timeout: int) -> Dict[str, Any]:
    # Include both query/question for compatibility with local endpoint variants.
    return post_json(url, {"query": query, "question": query}, timeout=timeout)


def ollama_generate(host: str, model: str, prompt: str, timeout: int) -> str:
    url=host.rstrip("/") + "/api/generate"
    payload={
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0, "num_ctx": 8192},
    }
    data=post_json(url, payload, timeout=timeout)
    return str(data.get("response") or "")


def _collect_citations_obj(obj: Any) -> List[Dict[str, Any]]:
    found=[]
    if isinstance(obj, dict):
        for key, val in obj.items():
            kl=str(key).lower()
            if kl in {"citations", "proof_context", "proof_contexts", "citation_records", "evidence", "source_evidence"} and isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        found.append(item)
                    else:
                        found.append({"text": str(item)})
            found.extend(_collect_citations_obj(val))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_collect_citations_obj(item))
    return found


def citation_count(resp: Mapping[str, Any]) -> int:
    return len(_collect_citations_obj(resp))


def response_text(resp: Mapping[str, Any]) -> str:
    parts=[]
    for key in ["answer", "response", "text", "content", "message", "draft_answer"]:
        if key in resp and not isinstance(resp[key], (dict, list)):
            parts.append(str(resp[key]))
    return "\n".join(parts)


def score_response(resp: Mapping[str, Any], query: str, original_question: str) -> int:
    c=citation_count(resp)
    text=(response_text(resp)+" "+json.dumps(resp, sort_keys=True)[:4000]).lower()
    q=query.lower()
    score=c*100
    # Favor query-specific evidence, but never mistake this for proof sufficiency.
    for token in ["df250040-501", "df250040501", "df250040", "120-36833-001", "figure 69", "fig. 69", "paper towel dispenser"]:
        if token in q and token in text:
            score += 25
    if any(x in original_question.lower() for x in ["eligible", "approved", "fits", "interchange", "installation", "effectivity"]):
        for token in ["eligib", "applicab", "effectiv", "approved", "interchange", "installation", "a319", "a320", "a321", "737", "787"]:
            if token in text:
                score += 10
    return score


def select_best_trace_response(tries: List[Dict[str, Any]], original_question: str) -> Dict[str, Any]:
    ok=[t for t in tries if t.get("status") == "ok"]
    if not ok:
        return {"status": "error", "selected_query": "", "response": {}, "citation_count": 0, "score": -1}
    ranked=[]
    for t in ok:
        resp=t.get("response") or {}
        score=score_response(resp, t.get("query") or "", original_question)
        ranked.append((score, citation_count(resp), -int(t.get("try_index") or 0), t))
    ranked.sort(reverse=True, key=lambda x: x[:3])
    best=ranked[0][3]
    resp=best.get("response") or {}
    return {
        "status": "ok",
        "selected_query": best.get("query") or "",
        "selected_try_index": best.get("try_index"),
        "response": resp,
        "citation_count": citation_count(resp),
        "score": ranked[0][0],
    }


def compact_json(obj: Any, max_chars: int=5000) -> str:
    txt=json.dumps(obj, indent=2, sort_keys=True)
    if len(txt) > max_chars:
        return txt[:max_chars] + "\n...TRUNCATED..."
    return txt


def build_prompt(qid: str, question: str, selected_query: str, trace_response: Mapping[str, Any]) -> str:
    intent=classify_intent(question)
    citations=_collect_citations_obj(trace_response)
    proof_text=compact_json({"selected_query": selected_query, "citation_count": len(citations), "trace_response": trace_response}, 9000)
    return f"""TRACE-NET ANSWER-RUNNER WORK ORDER CONTEXT PACK
question_id: {qid}

USER QUESTION:
{question}

SELECTED TRACE-NET QUERY:
{selected_query}

ENGRAM OVERLAY — BEHAVIOR GUIDANCE ONLY:
Use this Engram overlay as behavior guidance only. It is not proof.
question_intent: {intent}

Behavior guidance:
- Answer only from current source evidence/citations in SOURCE EVIDENCE / PROOF_CONTEXT.
- Do not use Engram memory, summaries, graph proximity, shared nomenclature, visual similarity, or this instruction text as proof.
- If the supplied context does not prove the claim, say the answer is not source-trace-ready.
- For eligibility, applicability, approved replacement, fit, effectivity, interchangeability, or installation approval, require explicit source authority naming the part and the platform/claim. A citation that only mentions the part number is not enough.
- For DF250040-501 questions, a part-number mention may prove only that the part was mentioned. It does not prove eligibility, fit, effectivity, interchangeability, installation approval, or approved replacement unless those exact authority signals appear in proof_context.
- For figures, say what the evidence identifies; do not infer part identity or approval from figure number alone.
- For policy/meta questions, use runtime-policy-ready or policy-boundary-ready, not source-trace-ready, unless actual manual/source citations prove a manual claim.

SOURCE EVIDENCE / PROOF_CONTEXT:
{proof_text}

BOUNDARIES:
Retrieved Engram overlay shapes behavior only. It is not proof.
Manual/source claims still require current proof_context citations.
V2/V3 summaries and graph proximity are routing hints only; they cannot prove eligibility, interchangeability, fit, effectivity, or installation approval.
If proof_context is missing or insufficient, answer not found / not source-trace-ready.

ANSWER FORMAT:
- Direct answer:
- Source-trace status:
- Evidence used:
- Missing evidence / limits:
"""


def grade(answer: str, citation_count_value: int) -> Dict[str, bool]:
    low=answer.lower()
    source_trace_ready_claim=("source-trace status: source-trace-ready" in low or "source-trace-ready" in low) and "not source-trace-ready" not in low
    policy_ready=("policy-boundary-ready" in low or "runtime-policy-ready" in low)
    engram_policy_used=("engram" in low and "evidence used" in low and source_trace_ready_claim and citation_count_value == 0 and not policy_ready)
    return {
        "source_trace_ready_claim": bool(source_trace_ready_claim),
        "source_trace_ready_without_citation": bool(source_trace_ready_claim and citation_count_value == 0 and not policy_ready),
        "engram_policy_used_as_source_proof": bool(engram_policy_used),
    }


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--questions", default="tests/fixtures/trace_net_fixed50_questions_v1.json")
    ap.add_argument("--output-dir", default="tmp/fixed50_trace_server_gemma_multiquery_df_fallback_v1")
    ap.add_argument("--trace-net-ask-url", default="http://127.0.0.1:8014/api/trace-net/ask")
    ap.add_argument("--ollama-host", default="http://127.0.0.1:11434")
    ap.add_argument("--model", default="gemma4:26b")
    ap.add_argument("--max-query-variants", type=int, default=10)
    ap.add_argument("--trace-timeout", type=int, default=120)
    ap.add_argument("--ollama-timeout", type=int, default=600)
    args=ap.parse_args()

    questions=load_questions(args.questions)
    total=len(questions)
    out_dir=Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir=out_dir/"prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    answers_path=out_dir/"answers.jsonl"

    answered=0
    trace_ok=0
    trace_errors=0
    total_tries=0
    citation_backed=0
    improved_by_variant=0
    source_trace_ready_without_citation=0
    engram_policy_as_proof=0
    ollama_errors=0
    start_all=time.time()

    with answers_path.open("w", encoding="utf-8") as f:
        for idx, qrec in enumerate(questions, start=1):
            qid=qrec["question_id"]
            question=qrec["question"]
            bucket=classify_bucket(question)
            variants=query_variants(question, args.max_query_variants)
            print(f"[{idx:03d}/{total:03d}] START {qid}: {question}", flush=True)
            started=time.time()
            tries=[]
            original_citations=0
            for ti, variant in enumerate(variants, start=1):
                print(f"[{idx:03d}/{total:03d}] TRACE {qid}: try {ti}/{len(variants)} query={variant}", flush=True)
                total_tries += 1
                try:
                    resp=trace_ask(args.trace_net_ask_url, variant, args.trace_timeout)
                    c=citation_count(resp)
                    if ti == 1:
                        original_citations=c
                    trace_ok += 1
                    tries.append({"try_index": ti, "query": variant, "status": "ok", "citation_count": c, "response": resp})
                    print(f"[{idx:03d}/{total:03d}] TRACE {qid}: try {ti} ok citations={c}", flush=True)
                except Exception as exc:
                    trace_errors += 1
                    tries.append({"try_index": ti, "query": variant, "status": "error", "error": repr(exc), "citation_count": 0, "response": {}})
                    print(f"[{idx:03d}/{total:03d}] TRACE {qid}: try {ti} error={exc!r}", flush=True)
            best=select_best_trace_response(tries, question)
            selected_query=best.get("selected_query") or question
            c=int(best.get("citation_count") or 0)
            if c > 0:
                citation_backed += 1
            if c > original_citations:
                improved_by_variant += 1
            prompt=build_prompt(qid, question, selected_query, best.get("response") or {})
            prompt_path=prompts_dir/f"{qid}_work_order_prompt.txt"
            prompt_path.write_text(prompt, encoding="utf-8")
            print(f"[{idx:03d}/{total:03d}] GEMMA {qid}: model={args.model} selected_citations={c} selected_query={selected_query}", flush=True)
            rec: Dict[str, Any] = {
                "module": MODULE,
                "version": "v1",
                "question_index": idx,
                "question_total": total,
                "question_id": qid,
                "question": question,
                "bucket": bucket,
                "query_variants": variants,
                "trace_try_count": len(tries),
                "trace_tries": [{k:v for k,v in t.items() if k != "response"} for t in tries],
                "selected_query": selected_query,
                "selected_try_index": best.get("selected_try_index"),
                "citation_count": c,
                "original_citation_count": original_citations,
                "improved_by_variant": bool(c > original_citations),
                "prompt_path": str(prompt_path),
                "model": args.model,
                "answer_permission": False,
                "source_truth_mutation_allowed": False,
                "write_attempt_count": 0,
            }
            try:
                answer=ollama_generate(args.ollama_host, args.model, prompt, args.ollama_timeout)
                g=grade(answer, c)
                if g["source_trace_ready_without_citation"]:
                    source_trace_ready_without_citation += 1
                if g["engram_policy_used_as_source_proof"]:
                    engram_policy_as_proof += 1
                elapsed=round(time.time()-started, 2)
                rec.update({"status": "ok", "answer": answer, "answer_char_count": len(answer), "elapsed_seconds": elapsed, "grade": g})
                answered += 1
                print(f"[{idx:03d}/{total:03d}] DONE  {qid}: status=ok chars={len(answer)} citations={c} seconds={elapsed}", flush=True)
            except Exception as exc:
                elapsed=round(time.time()-started, 2)
                ollama_errors += 1
                rec.update({"status": "error", "answer": "", "error": repr(exc), "elapsed_seconds": elapsed, "grade": {}})
                print(f"[{idx:03d}/{total:03d}] ERROR {qid}: {exc!r}", flush=True)
            f.write(json.dumps(rec, sort_keys=True)+"\n")
            f.flush()

    summary={
        "module": MODULE,
        "version": "v1",
        "quality_status": "PASS",
        "question_count": total,
        "answered_count": answered,
        "citation_backed_count": citation_backed,
        "improved_by_variant_count": improved_by_variant,
        "total_trace_try_count": total_tries,
        "trace_ask_success_count": trace_ok,
        "trace_ask_error_count": trace_errors,
        "ollama_error_count": ollama_errors,
        "source_trace_ready_without_citation_count": source_trace_ready_without_citation,
        "engram_policy_as_proof_count": engram_policy_as_proof,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "write_attempt_count": 0,
        "model": args.model,
        "answers": str(answers_path),
        "elapsed_seconds": round(time.time()-start_all, 2),
        "quality_failures": [],
    }
    failures=[]
    if answered != total:
        failures.append(f"answered_count:{answered}!={total}")
    if trace_errors:
        failures.append(f"trace_ask_error_count:{trace_errors}")
    if ollama_errors:
        failures.append(f"ollama_error_count:{ollama_errors}")
    if source_trace_ready_without_citation:
        failures.append(f"source_trace_ready_without_citation_count:{source_trace_ready_without_citation}")
    if engram_policy_as_proof:
        failures.append(f"engram_policy_as_proof_count:{engram_policy_as_proof}")
    summary["quality_failures"]=failures
    summary["quality_status"]="PASS" if not failures else "FAIL"
    _write_json(out_dir/"summary.json", summary)
    print(f"status=TRACE_NET_FIXED50_TRACE_SERVER_GEMMA_MULTIQUERY_DF_FALLBACK_DONE", flush=True)
    for k in ["quality_status", "question_count", "answered_count", "trace_ask_success_count", "total_trace_try_count", "improved_by_variant_count", "citation_backed_count", "source_trace_ready_without_citation_count", "engram_policy_as_proof_count"]:
        print(f"{k}={summary[k]}", flush=True)
    print(f"answers={answers_path}", flush=True)
    print(f"summary={out_dir/'summary.json'}", flush=True)
    return 0 if summary["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
