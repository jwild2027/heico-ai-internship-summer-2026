from __future__ import annotations

import argparse
import json
import re
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple


MODULE = "trace_net_h38c_diversity_task_repair_runner_v1"
VERSION = "v1"


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _norm(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()


def _labels(cards: List[Mapping[str, Any]]) -> List[str]:
    out, seen = [], set()
    for c in cards:
        label = _norm(c.get("evidence_label"))
        if label and label not in seen:
            seen.add(label)
            out.append(label)
    return out


def _sentence_windows(text: str) -> List[str]:
    # Keep short markdown-ish paragraphs/sentences. This catches boundary lists like
    # "nor can it confirm installation safety, effectivity, or interchangeability".
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [_norm(p).lower() for p in parts if _norm(p)]


def _contains_safe_negation(text: str, term: str) -> bool:
    term_l = term.lower()
    term_re = re.compile(r"\b" + re.escape(term_l) + r"\b")
    safe_markers = (
        "cannot",
        "can not",
        "does not",
        "do not",
        "did not",
        "not prove",
        "not verify",
        "not establish",
        "not confirm",
        "not provided",
        "not source-trace-ready",
        "nor can",
        "no evidence",
        "does not provide evidence",
        "do not provide evidence",
        "unproven",
        "not proven",
        "not verified",
        "not established",
        "not confirmed",
        "outside the evidence",
        "limits",
        "limitations",
    )
    for sent in _sentence_windows(text):
        if term_re.search(sent) and any(m in sent for m in safe_markers):
            return True

    t = text.lower()
    patterns = [
        rf"\b(?:does|do|did)\s+not\s+(?:prove|verify|establish|show|confirm|provide)\b[\s\S]{{0,220}}\b{re.escape(term_l)}\b",
        rf"\bcannot\s+(?:prove|verify|establish|show|confirm|provide)\b[\s\S]{{0,220}}\b{re.escape(term_l)}\b",
        rf"\bnor\s+can\s+it\s+(?:prove|verify|establish|show|confirm|provide)\b[\s\S]{{0,220}}\b{re.escape(term_l)}\b",
        rf"\bno\s+evidence\b[\s\S]{{0,220}}\b{re.escape(term_l)}\b",
        rf"\b{re.escape(term_l)}\b[\s\S]{{0,120}}\b(?:not proven|not verified|not established|not confirmed|cannot be confirmed)\b",
    ]
    return any(re.search(p, t) for p in patterns)


def unsafe_forbidden_claims(answer: str) -> List[str]:
    terms = [
        "interchangeability",
        "interchangeable",
        "approved replacement",
        "replacement approval",
        "installation safety",
        "installation safe",
        "effectivity",
        "fit approval",
        "safe to install",
    ]
    claims = []
    low = answer.lower()
    for term in terms:
        if not re.search(r"\b" + re.escape(term) + r"\b", low):
            continue
        if _contains_safe_negation(answer, term):
            continue
        claims.append(f"possible_forbidden_claim:{term}")
    return sorted(set(claims))


def _card_lines(cards: List[Mapping[str, Any]]) -> str:
    lines = []
    for c in cards[:10]:
        lines.append(
            f"[{c.get('evidence_label')}] route={c.get('route')} page={c.get('page')} "
            f"figure={c.get('figure')} part={c.get('part_number')} nomenclature={c.get('nomenclature')} | "
            f"{_norm(c.get('preview'))[:380]}"
        )
    return "\n".join(lines)


def build_prompt(record: Mapping[str, Any], answer_hard_max_chars: int = 1500, repair_findings: Optional[List[str]] = None, prior_answer: str = "") -> str:
    task = _norm(record.get("task_type"))
    qid = _norm(record.get("question_id"))
    question = _norm(record.get("query_text") or record.get("question"))
    cards = record.get("selected_cards", []) or []
    label_list = " ".join(f"[{x}]" for x in _labels(cards))

    lines = [
        "TRACE-NET H38C DIVERSITY TASK REPAIR RUNNER",
        "",
        "You are a cautious, source-trace-first engineering assistant.",
        "Use ONLY the selected evidence cards below as proof_context.",
        "Planner/Engram/diversity guidance is not proof by itself.",
        "Every factual claim must cite an evidence label from the allowed label list.",
        "",
        f"target_question_id: {qid}",
        f"task_type: {task}",
        f"allowed_citation_labels: {label_list}",
        "",
        "GLOBAL HARD RULES:",
        f"- Keep the full answer under {answer_hard_max_chars} characters.",
        "- Finish the answer; do not stop mid-sentence.",
        "- Use individual citations like [V7] [O2], not [V7, O2].",
        "- Do not claim interchangeability, fit, effectivity, replacement approval, or installation safety.",
        "- You MAY say those things are not proven using clear language like: TRACE-Net cannot prove ...",
        "- Do not mention internal metadata such as source_extractor_quality_pass, quality_status, schema_version, record_count, module, or LLaVA internals.",
        "",
        "SELECTED SOURCE-TRACE EVIDENCE CARDS:",
        _card_lines(cards),
        "",
    ]

    if repair_findings:
        lines.extend([
            "REPAIR MODE:",
            f"The prior answer failed these checks: {', '.join(repair_findings)}",
            "Rewrite the answer to satisfy the contract. Do not repeat the failure.",
            "Prior answer:",
            prior_answer[:1200],
            "",
        ])

    lines.append("TASK CONTRACT:")
    if task == "representative_page_explanation":
        lines.extend([
            "- Pick ONE representative source-trace-ready page/figure/record.",
            "- State what TRACE-Net can safely verify.",
            "- Include a Limits section with: TRACE-Net cannot prove interchangeability, effectivity, fit, replacement approval, or installation safety.",
            "- Cite every factual claim.",
        ])
    elif task == "multi_page_summary":
        lines.extend([
            "- Start with: This summary is source-trace-ready.",
            "- Summarize at least 3 pages/figures/parts if available.",
            "- For each item, say Proven and Unproven.",
            "- Use at least 4 unique allowed citation labels.",
        ])
    elif task == "nomenclature_lookup":
        lines.extend([
            "- Use this exact structure:",
            "  Answer: <state nomenclature if the selected evidence contains it; otherwise say not found in selected proof_context> <citation>",
            "  OCR route: <what OCR proves or does not prove> <citation>",
            "  Visual route: <what visual proves or does not prove> <citation>",
            "  Limits: TRACE-Net cannot prove interchangeability, effectivity, fit, replacement approval, or installation safety.",
            "- You MUST cite at least one OCR label and one visual label if available.",
            "- If no nomenclature is present in the selected cards, still cite the cards that were checked.",
        ])
    elif task == "quiz_generation":
        lines.extend([
            "- Create exactly 5 technician quiz questions.",
            "- Use this exact format with each question on its own line:",
            "  1. <question>",
            "  2. <question>",
            "  3. <question>",
            "  4. <question about what TRACE-Net cannot prove>",
            "  5. <question>",
            "  Answer Key:",
            "  1. <answer> <citation>",
            "  2. <answer> <citation>",
            "  3. <answer> <citation>",
            "  4. No. TRACE-Net cannot prove interchangeability, effectivity, fit, replacement approval, or installation safety from these cards. <citation>",
            "  5. <answer> <citation>",
            "- Use at least 4 unique allowed citation labels across the answer key.",
            "- Do not ask about LLaVA, visual authority model internals, source_extractor_quality_pass, quality_status, schema_version, module, or record_count.",
        ])
    else:
        lines.extend([
            "- Use Answer, Evidence, Engineering confidence, and Limits sections.",
            "- Cite all factual claims.",
        ])

    lines.extend(["", "USER QUESTION:", question, "", "Return only the final answer."])
    return "\n".join(lines)


def call_ollama(prompt: str, model: str, url: str, timeout_seconds: int) -> Tuple[str, str]:
    payload = {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.05}}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        answer = (data.get("response") or data.get("answer") or "").strip()
        if not answer:
            return "", "Ollama response did not contain answer text"
        return answer, ""
    except Exception as e:
        return "", str(e)


def artifact_answer(record: Mapping[str, Any]) -> str:
    cards = record.get("selected_cards", []) or []
    labels = _labels(cards)
    cite = " ".join(f"[{x}]" for x in labels[:5])
    task = _norm(record.get("task_type"))

    if task == "quiz_generation":
        items = cards[:5]
        lines = [
            "1. What part or figure is identified by the first selected card?",
            "2. Which route provides OCR/table/visual support in the selected evidence?",
            "3. What page or figure is source-trace-ready in the selected evidence?",
            "4. Does TRACE-Net prove interchangeability, effectivity, fit, replacement approval, or installation safety?",
            "5. Which selected evidence card supports a part-number lookup?",
            "Answer Key:",
        ]
        for i, c in enumerate(items, 1):
            label = c.get("evidence_label")
            if i == 4:
                lines.append(f"4. No. TRACE-Net cannot prove interchangeability, effectivity, fit, replacement approval, or installation safety from these cards [{label}].")
            else:
                value = c.get("part_number") or c.get("figure") or c.get("page") or c.get("route")
                lines.append(f"{i}. {value} [{label}].")
        return "\n".join(lines)

    return (
        f"Answer: TRACE-Net can use the selected source-trace-ready cards {cite} for this task.\n"
        f"Evidence: {cite}\n"
        "Engineering confidence: Medium/high for claims directly cited.\n"
        "Limits: TRACE-Net cannot prove interchangeability, effectivity, fit, replacement approval, or installation safety."
    )


def _count_quiz_questions(answer: str) -> int:
    body = re.split(r"answer\s+key\s*:", answer, flags=re.I)[0]
    return len(re.findall(r"(?<!\d)(?:^|\s)([1-5])[\).\:]\s+", body))


def validate_answer(record: Mapping[str, Any], answer: str, fallback_used: bool, answer_hard_max_chars: int) -> Dict[str, Any]:
    task = _norm(record.get("task_type"))
    cards = record.get("selected_cards", []) or []
    allowed = set(_labels(cards))
    cited = sorted(set(re.findall(r"\[([A-Z][0-9]+)\]", answer)))
    valid = [x for x in cited if x in allowed]
    findings: List[str] = []

    if fallback_used:
        findings.append("fallback_used")
    if len(answer) > answer_hard_max_chars:
        findings.append(f"answer_too_long:{len(answer)}>{answer_hard_max_chars}")
    if not valid:
        findings.append("missing_valid_citations")
    if re.search(r"\[[A-Z][0-9]+,\s*[A-Z][0-9]+", answer):
        findings.append("grouped_citation_syntax")

    unsafe = unsafe_forbidden_claims(answer)
    findings.extend(unsafe)

    if task == "quiz_generation":
        q_count = _count_quiz_questions(answer)
        if q_count < 5:
            findings.append(f"too_few_quiz_questions:{q_count}<5")
        if "answer key" not in answer.lower():
            findings.append("missing_answer_key")
        if len(valid) < 4:
            findings.append(f"too_few_quiz_citations:{len(valid)}<4")
        if not any(x in answer.lower() for x in ("cannot prove", "does not prove", "not prove")):
            findings.append("missing_limits_quiz_item")
        if re.search(r"source_extractor_quality_pass|quality_status|schema_version|record_count|module|llava|visual authority model", answer, re.I):
            findings.append("metadata_or_internal_quiz_item")

    if task == "multi_page_summary":
        if "source-trace" not in answer.lower():
            findings.append("missing_source_trace_wording")
        if len(valid) < 4:
            findings.append(f"too_few_summary_citations:{len(valid)}<4")

    if task == "nomenclature_lookup":
        if not valid:
            findings.append("missing_valid_citations")
        routes_by_label = {c.get("evidence_label"): c.get("route") for c in cards}
        cited_routes = {routes_by_label.get(x) for x in valid}
        if "ocr" in {c.get("route") for c in cards} and "ocr" not in cited_routes:
            findings.append("missing_ocr_citation")
        if "visual" in {c.get("route") for c in cards} and "visual" not in cited_routes:
            findings.append("missing_visual_citation")

    unsupported = len([f for f in findings if f.startswith("possible_forbidden_claim")])
    if not findings:
        grade = "GOOD"
        contract_pass = True
    elif fallback_used or unsupported or "missing_valid_citations" in findings:
        grade = "BAD"
        contract_pass = False
    else:
        grade = "PARTIAL"
        contract_pass = False

    # De-dupe while preserving order
    seen = set()
    deduped = []
    for f in findings:
        if f not in seen:
            seen.add(f)
            deduped.append(f)

    return {
        "grade": grade,
        "contract_pass": contract_pass,
        "findings": deduped,
        "answer_citation_count": len(cited),
        "valid_answer_citation_count": len(valid),
        "unsupported_claim_count": unsupported,
    }


def run_repair_runner(
    diversity_planner: str | Path,
    output_dir: str | Path,
    llm_mode: str = "ollama",
    ollama_model: str = "gemma4:26b",
    ollama_url: str = "http://127.0.0.1:11434/api/generate",
    timeout_seconds: int = 420,
    max_questions: int = 5,
    answer_hard_max_chars: int = 1500,
    max_repair_attempts: int = 1,
    min_good_answers: int = 4,
    min_contract_pass: int = 4,
    max_fallback_used: int = 0,
    progress: bool = True,
) -> Dict[str, Any]:
    planner = _read_json(diversity_planner)
    plan_records = (planner.get("plan_records") or [])[:max_questions]
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    pdir, adir, tdir = out / "p", out / "a", out / "t"
    records = []
    start = time.time()

    for idx, rec in enumerate(plan_records, 1):
        qid = _norm(rec.get("question_id")) or f"q{idx:02d}"
        prompt = build_prompt(rec, answer_hard_max_chars)
        _write_text(pdir / f"{idx:02d}_{qid}_p.txt", prompt)

        fallback_used = False
        repair_used = False
        llm_error = ""
        if llm_mode == "artifact":
            answer = artifact_answer(rec)
        else:
            answer, llm_error = call_ollama(prompt, ollama_model, ollama_url, timeout_seconds)
            if not answer:
                fallback_used = True
                answer = artifact_answer(rec)

        validation = validate_answer(rec, answer, fallback_used, answer_hard_max_chars)

        attempts = 0
        while (
            llm_mode == "ollama"
            and not fallback_used
            and not validation["contract_pass"]
            and attempts < max_repair_attempts
        ):
            attempts += 1
            repair_used = True
            repair_prompt = build_prompt(
                rec,
                answer_hard_max_chars,
                repair_findings=validation["findings"],
                prior_answer=answer,
            )
            _write_text(pdir / f"{idx:02d}_{qid}_repair{attempts}_p.txt", repair_prompt)
            repaired, err = call_ollama(repair_prompt, ollama_model, ollama_url, timeout_seconds)
            if repaired:
                repaired_validation = validate_answer(rec, repaired, False, answer_hard_max_chars)
                # Accept repair if it improves grade/contract/citation count.
                old_score = (1 if validation["contract_pass"] else 0, validation["valid_answer_citation_count"], -len(validation["findings"]))
                new_score = (1 if repaired_validation["contract_pass"] else 0, repaired_validation["valid_answer_citation_count"], -len(repaired_validation["findings"]))
                if new_score >= old_score:
                    answer = repaired
                    validation = repaired_validation
                    llm_error = ""
            else:
                llm_error = (llm_error + "; " if llm_error else "") + f"repair_failed:{err}"

        _write_text(adir / f"{idx:02d}_{qid}_a.txt", answer)

        record = {
            "question_id": qid,
            "task_type": rec.get("task_type"),
            "query_text": rec.get("query_text"),
            "grade": validation["grade"],
            "contract_pass": validation["contract_pass"],
            "findings": validation["findings"],
            "fallback_used": fallback_used,
            "repair_used": repair_used,
            "repair_attempt_count": attempts,
            "llm_error": llm_error,
            "answer_char_count": len(answer),
            "answer_citation_count": validation["answer_citation_count"],
            "valid_answer_citation_count": validation["valid_answer_citation_count"],
            "unsupported_claim_count": validation["unsupported_claim_count"],
            "selected_evidence_labels": rec.get("selected_evidence_labels"),
            "selected_routes": rec.get("selected_routes"),
            "selected_pages": rec.get("selected_pages"),
            "selected_part_numbers": rec.get("selected_part_numbers"),
            "selected_figures": rec.get("selected_figures"),
            "answer_preview": answer[:2600],
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "unsafe": validation["unsupported_claim_count"] > 0,
            "write_attempt_count": 0,
        }
        _write_json(tdir / f"{idx:02d}_{qid}_trace.json", record)
        records.append(record)

        if progress:
            elapsed = time.time() - start
            print(
                f"[H38C progress] {idx}/{len(plan_records)} ({idx/max(1,len(plan_records))*100:.1f}%) "
                f"qid={qid} grade={record['grade']} contract={record['contract_pass']} "
                f"repair={repair_used} fallback={fallback_used} citations={record['valid_answer_citation_count']} "
                f"chars={record['answer_char_count']} elapsed={elapsed:.1f}s",
                flush=True,
            )

    summary = {
        "module": MODULE,
        "version": VERSION,
        "question_count": len(records),
        "good_answer_count": sum(1 for r in records if r["grade"] == "GOOD"),
        "partial_answer_count": sum(1 for r in records if r["grade"] == "PARTIAL"),
        "bad_answer_count": sum(1 for r in records if r["grade"] == "BAD"),
        "contract_pass_count": sum(1 for r in records if r["contract_pass"]),
        "fallback_used_count": sum(1 for r in records if r["fallback_used"]),
        "repair_used_count": sum(1 for r in records if r["repair_used"]),
        "repair_attempt_count": sum(int(r["repair_attempt_count"]) for r in records),
        "unsupported_claim_count": sum(int(r["unsupported_claim_count"]) for r in records),
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_read_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
        "write_attempt_count": 0,
        "unsafe_finding_count": sum(1 for r in records if r.get("unsafe")),
    }
    failures = []
    if summary["good_answer_count"] < min_good_answers:
        failures.append("good_answer_count_below_min")
    if summary["contract_pass_count"] < min_contract_pass:
        failures.append("contract_pass_count_below_min")
    if summary["fallback_used_count"] > max_fallback_used:
        failures.append("fallback_used_count_above_max")
    if summary["bad_answer_count"] > 0:
        failures.append("bad_answer_count_nonzero")
    if summary["unsupported_claim_count"] > 0:
        failures.append("unsupported_claim_count_nonzero")
    summary["quality_failures"] = failures
    quality_status = "PASS" if not failures else "FAIL"

    manifest = {
        "status": "TRACE_NET_H38C_DIVERSITY_TASK_REPAIR_RUN_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "runner_policy": {
            "mode": "diversity_task_runner_with_contract_repair",
            "proof_boundary": "Selected diversity cards are proof_context candidates. Planner/Engram guidance is not proof.",
            "forbidden": [
                "answer_permission_from_runner",
                "source_truth_mutation_from_runner",
                "summary_or_engram_used_as_proof",
                "live_io_from_runner",
            ],
        },
        "source_paths": {"diversity_planner": str(diversity_planner)},
        "records": records,
    }
    _write_json(out / f"{MODULE}.json", manifest)
    _write_json(out / f"{MODULE}_quality_check.json", {
        "status": "TRACE_NET_H38C_DIVERSITY_TASK_REPAIR_RUN_CHECKED",
        "quality_status": quality_status,
        "summary": summary,
    })
    return manifest


def check_repair_run(
    repair_run: str | Path,
    min_records: int = 5,
    min_good_answers: int = 4,
    min_contract_pass: int = 4,
    max_fallback_used: int = 0,
    require_quality_pass: bool = False,
    require_no_answer_permission: bool = False,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> Dict[str, Any]:
    data = _read_json(repair_run)
    s = data.get("summary", {})
    failures = []
    if int(s.get("question_count") or 0) < min_records:
        failures.append("question_count_below_min")
    if int(s.get("good_answer_count") or 0) < min_good_answers:
        failures.append("good_answer_count_below_min")
    if int(s.get("contract_pass_count") or 0) < min_contract_pass:
        failures.append("contract_pass_count_below_min")
    if int(s.get("fallback_used_count") or 0) > max_fallback_used:
        failures.append("fallback_used_count_above_max")
    if require_quality_pass and data.get("quality_status") != "PASS":
        failures.append("quality_not_pass")
    if require_no_answer_permission and int(s.get("answer_permission_count") or 0) != 0:
        failures.append("answer_permission_nonzero")
    if int(s.get("unsafe_finding_count") or 0) > max_unsafe:
        failures.append("unsafe_finding_count_above_max")
    if int(s.get("write_attempt_count") or 0) > max_write_attempts:
        failures.append("write_attempt_count_above_max")
    return {
        "status": "TRACE_NET_H38C_DIVERSITY_TASK_REPAIR_RUN_CHECKED",
        "quality_status": "PASS" if not failures else "FAIL",
        "question_count": int(s.get("question_count") or 0),
        "good_answer_count": int(s.get("good_answer_count") or 0),
        "contract_pass_count": int(s.get("contract_pass_count") or 0),
        "fallback_used_count": int(s.get("fallback_used_count") or 0),
        "repair_used_count": int(s.get("repair_used_count") or 0),
        "bad_answer_count": int(s.get("bad_answer_count") or 0),
        "unsupported_claim_count": int(s.get("unsupported_claim_count") or 0),
        "unsafe_finding_count": int(s.get("unsafe_finding_count") or 0),
        "answer_permission_count": int(s.get("answer_permission_count") or 0),
        "write_attempt_count": int(s.get("write_attempt_count") or 0),
        "quality_failures": failures,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run TRACE-Net H38C diversity task repair runner")
    parser.add_argument("--diversity-planner", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--llm-mode", default="ollama", choices=["ollama", "artifact"])
    parser.add_argument("--ollama-model", default="gemma4:26b")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434/api/generate")
    parser.add_argument("--timeout-seconds", type=int, default=420)
    parser.add_argument("--max-questions", type=int, default=5)
    parser.add_argument("--answer-hard-max-chars", type=int, default=1500)
    parser.add_argument("--max-repair-attempts", type=int, default=1)
    parser.add_argument("--min-good-answers", type=int, default=4)
    parser.add_argument("--min-contract-pass", type=int, default=4)
    parser.add_argument("--max-fallback-used", type=int, default=0)
    parser.add_argument("--no-progress", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    kwargs = vars(args).copy()
    no_progress = bool(kwargs.pop("no_progress", False))
    manifest = run_repair_runner(progress=not no_progress, **kwargs)
    s = manifest["summary"]
    print("status=TRACE_NET_H38C_DIVERSITY_TASK_REPAIR_RUN_BUILT")
    print(f"quality_status={manifest['quality_status']}")
    print(f"question_count={s['question_count']}")
    print(f"good_answer_count={s['good_answer_count']}")
    print(f"partial_answer_count={s['partial_answer_count']}")
    print(f"bad_answer_count={s['bad_answer_count']}")
    print(f"contract_pass_count={s['contract_pass_count']}")
    print(f"fallback_used_count={s['fallback_used_count']}")
    print(f"repair_used_count={s['repair_used_count']}")
    print(f"unsupported_claim_count={s['unsupported_claim_count']}")
    print(f"output={Path(args.output_dir) / (MODULE + '.json')}")
    return 0 if manifest["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
