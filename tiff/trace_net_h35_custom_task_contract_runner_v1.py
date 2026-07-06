from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable, Mapping

MODULE = "trace_net_h35_custom_task_contract_runner_v1"
VERSION = "v1"

PART_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")
CIT_RE = re.compile(r"\[([A-Z]+\d+)\]")

SAFETY_CONTRACT = {
    "answer_permission": False,
    "source_truth_mutation_allowed": False,
    "postgres_write_attempt": False,
    "qdrant_write_attempt": False,
    "qdrant_read_attempt": False,
    "opensearch_write_attempt": False,
    "opensearch_upload_attempt": False,
    "write_attempt": False,
    "proof_boundary": "Task contracts and Engram guidance shape behavior only; factual claims still require current proof_context evidence cards and citations.",
}

DEFAULT_TASKS = [
    {
        "question_id": "h35_q01_part_lookup",
        "task_type": "part_lookup",
        "category": "custom_contract_part_lookup",
        "question": "Find part number 120-50645-005. Give the nomenclature if available, cite the source, and clearly state what TRACE-Net cannot prove from this evidence.",
        "contract": {
            "required_outputs": ["answer", "evidence", "engineering_confidence", "limits"],
            "min_unique_evidence_labels": 3,
            "min_unique_routes": 2,
            "must_include": ["120-50645-005", "nomenclature", "cannot prove"],
            "forbidden_claims": ["interchangeable", "approved replacement", "installation safe"],
        },
    },
    {
        "question_id": "h35_q02_representative_page",
        "task_type": "representative_page_explanation",
        "category": "custom_contract_representative_page",
        "question": "Pick one representative source-trace-ready page, figure, or record from the available evidence and tell me what TRACE-Net can safely say about it. Cite the source.",
        "contract": {
            "required_outputs": ["answer", "evidence", "engineering_confidence", "limits"],
            "min_unique_evidence_labels": 1,
            "min_unique_routes": 1,
            "must_include_any": ["page", "figure", "record"],
            "forbidden_claims": ["interchangeable", "approved replacement", "installation safe"],
        },
    },
    {
        "question_id": "h35_q03_multi_page_summary",
        "task_type": "multi_page_summary",
        "category": "custom_contract_multi_page_summary",
        "question": "Summarize evidence across at least three different available pages, figures, or records. Keep it source-trace-ready, cite each source used, and do not use summaries as proof.",
        "contract": {
            "required_outputs": ["answer", "evidence", "limits"],
            "min_unique_evidence_labels": 3,
            "min_unique_routes": 2,
            "min_unique_pages_or_figures": 3,
            "must_include": ["summary", "source-trace"],
            "forbidden_claims": ["summary proves", "interchangeable", "approved replacement"],
        },
    },
    {
        "question_id": "h35_q04_nomenclature_lookup",
        "task_type": "nomenclature_lookup",
        "category": "custom_contract_nomenclature_lookup",
        "question": "Look up the nomenclature for part number 120-50645-005. Explain which route proves the part name and which route proves the figure-to-part link. Cite the source.",
        "contract": {
            "required_outputs": ["answer", "evidence", "engineering_confidence", "limits"],
            "min_unique_evidence_labels": 3,
            "min_unique_routes": 2,
            "must_include": ["OCR", "visual", "figure-to-part", "nomenclature"],
            "forbidden_claims": ["interchangeable", "approved replacement", "installation safe"],
        },
    },
    {
        "question_id": "h35_q05_quiz_generation",
        "task_type": "quiz_generation",
        "category": "custom_contract_quiz_generation",
        "question": "Create a 5-question technician training quiz using only source-trace-ready TRACE-Net evidence. Include an answer key and cite the evidence used for each answer.",
        "contract": {
            "required_outputs": ["5 quiz questions", "answer key", "citation per answer", "limits question"],
            "min_quiz_questions": 5,
            "min_unique_evidence_labels": 4,
            "min_unique_routes": 2,
            "must_include": ["answer key"],
            "must_include_any": ["cannot prove", "not prove", "limits", "interchangeability"],
            "forbidden_claims": ["interchangeable", "approved replacement", "installation safe"],
        },
    },
]

@dataclass
class EvidenceCard:
    label: str
    route: str
    source: str
    page: str = ""
    page_id: str = ""
    figure: str = ""
    part_number: str = ""
    nomenclature: str = ""
    line_text: str = ""
    claim_supported: str = "source-trace-ready evidence card"
    citation_ready: bool = True
    raw_id: str = ""

    def prompt_line(self) -> str:
        parts = [f"[{self.label}] route={self.route}"]
        if self.page:
            parts.append(f"page={self.page}")
        if self.page_id:
            parts.append(f"page_id={self.page_id}")
        if self.figure:
            parts.append(f"figure={self.figure}")
        if self.part_number:
            parts.append(f"part={self.part_number}")
        if self.nomenclature:
            parts.append(f"nomenclature={self.nomenclature}")
        if self.line_text:
            parts.append(f"line_text={_compact(self.line_text, 160)}")
        parts.append(f"supports={self.claim_supported}")
        return " | ".join(parts)


def _norm(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, (str, int, float, bool)):
        return str(x)
    return json.dumps(x, ensure_ascii=False, sort_keys=True)[:800]


def _compact(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[: max(0, n - 3)].rstrip() + "..."


def _load_json(path: str | Path | None) -> Any:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _walk(obj: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def _first(d: Mapping[str, Any], keys: list[str]) -> str:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return _norm(d[k])
    return ""


def _dict_text(d: Mapping[str, Any], max_len: int = 4000) -> str:
    try:
        return json.dumps(d, ensure_ascii=False, sort_keys=True)[:max_len]
    except Exception:
        return str(d)[:max_len]


def _part_from_text(text: str) -> str:
    m = PART_RE.search(text or "")
    return m.group(0) if m else ""


def _make_cards_from_json(obj: Any, route: str, prefix: str, source_name: str, limit: int = 160) -> list[EvidenceCard]:
    cards: list[EvidenceCard] = []
    seen = set()
    for d in _walk(obj):
        text = _dict_text(d)
        part = _first(d, ["part_number", "linked_part_number", "covered_part_number", "part", "ipl_part_number"]) or _part_from_text(text)
        nomen = _first(d, ["nomenclature", "part_name", "description", "name", "line_nomenclature"])
        fig = _first(d, ["figure", "figure_number", "linked_figure"])
        page = _first(d, ["page", "page_number", "manual_page", "source_page"])
        page_id = _first(d, ["page_id", "source_page_id", "ocr_page_id"])
        line = _first(d, ["line_text", "ocr_line_text", "text", "raw_text"])
        citation_ready_raw = d.get("citation_ready", True)
        citation_ready = False if citation_ready_raw is False else True
        if not (part or nomen or fig or page or line):
            continue
        # Avoid pure metadata blobs unless they contain a part, figure, page, or useful line.
        if route in {"ocr", "table", "exact"} and not (part or nomen or line):
            continue
        key = (route, part, nomen, fig, page, page_id, line[:120])
        if key in seen:
            continue
        seen.add(key)
        raw_id = _first(d, ["record_id", "evidence_id", "source_record_id", "id"])
        label = f"{prefix}{len(cards)+1}"
        if route == "visual":
            claim = "visual figure/page evidence; can support figure-to-part identity when linked"
        elif route == "ocr":
            claim = "OCR-backed line text/nomenclature evidence"
        elif route == "table":
            claim = "table/evidence-packager part or field evidence"
        else:
            claim = "exact-search part evidence"
        cards.append(EvidenceCard(label, route, source_name, page, page_id, fig, part, nomen, line, claim, citation_ready, raw_id))
        if len(cards) >= limit:
            break
    return cards


def load_evidence_cards(
    image_visual_evidence_pack: str | Path | None = None,
    raw_ocr_nomenclature_extractor: str | Path | None = None,
    table_route_evidence_packager: str | Path | None = None,
    table_exact_search_adapter: str | Path | None = None,
) -> list[EvidenceCard]:
    specs = [
        (image_visual_evidence_pack, "visual", "V", "image_visual_evidence_pack"),
        (raw_ocr_nomenclature_extractor, "ocr", "O", "raw_ocr_nomenclature_extractor"),
        (table_route_evidence_packager, "table", "T", "table_route_evidence_packager"),
        (table_exact_search_adapter, "exact", "E", "table_exact_search_adapter"),
    ]
    cards: list[EvidenceCard] = []
    for path, route, prefix, source_name in specs:
        obj = _load_json(path)
        if obj is not None:
            cards.extend(_make_cards_from_json(obj, route, prefix, source_name))
    return cards


def build_contract_records(max_questions: int = 5) -> list[dict[str, Any]]:
    out = []
    for spec in DEFAULT_TASKS[:max_questions]:
        rec = dict(spec)
        rec["contract_id"] = "contract_" + spec["question_id"]
        rec["answer_budget"] = {
            "target_min_chars": 350,
            "target_max_chars": 1200,
            "hard_max_chars": 1500,
            "must_finish_sections": True,
        }
        rec["proof_boundary"] = SAFETY_CONTRACT["proof_boundary"]
        rec["safety_contract"] = dict(SAFETY_CONTRACT)
        out.append(rec)
    return out


def _score_card_for_task(card: EvidenceCard, task: Mapping[str, Any]) -> int:
    q = (task.get("question") or "").lower()
    t = (task.get("task_type") or "").lower()
    blob = " ".join([card.route, card.part_number, card.nomenclature, card.figure, card.page, card.line_text]).lower()
    score = 0
    if "120-50645-005" in q and "120-50645-005" in blob:
        score += 100
    if "nomenclature" in q and card.nomenclature:
        score += 40
    if "figure" in q and card.figure:
        score += 25
    if "page" in q and (card.page or card.page_id):
        score += 15
    if t == "quiz_generation":
        score += {"visual": 20, "ocr": 20, "table": 12, "exact": 12}.get(card.route, 0)
        if card.part_number:
            score += 10
        if card.nomenclature:
            score += 10
    if t == "multi_page_summary":
        score += 20 if (card.page or card.figure) else 0
    if card.citation_ready:
        score += 5
    return score


def select_evidence_for_task(cards: list[EvidenceCard], task: Mapping[str, Any], max_cards: int = 8) -> list[EvidenceCard]:
    scored = sorted(cards, key=lambda c: (_score_card_for_task(c, task), c.citation_ready, c.label), reverse=True)
    selected: list[EvidenceCard] = []
    routes = set()
    pages_figs = set()
    # First pass: maximize route/page diversity among relevant cards.
    for c in scored:
        if len(selected) >= max_cards:
            break
        route_new = c.route not in routes
        pf = c.page or c.figure or c.page_id or c.label
        pf_new = pf not in pages_figs
        if route_new or pf_new or len(selected) < 3:
            selected.append(c)
            routes.add(c.route)
            pages_figs.add(pf)
    # Second pass: fill with top cards.
    for c in scored:
        if len(selected) >= max_cards:
            break
        if c not in selected:
            selected.append(c)
    return selected


def build_prompt(task: Mapping[str, Any], evidence: list[EvidenceCard], answer_hard_max_chars: int = 1500) -> str:
    contract = task.get("contract", {})
    evidence_text = "\n".join("- " + c.prompt_line() for c in evidence)
    return f"""TRACE-NET H35 CUSTOM TASK CONTRACT RUNNER

Use this contract as behavior guidance only. It is not proof.
Only the evidence cards below can support factual source claims.
Use individual citations like [V1] [O2]. Do not use grouped citations like [V1, O2].
Do not claim interchangeability, fit, effectivity, replacement approval, or installation safety unless explicit authority appears in the evidence cards.
Do not use Engram, summaries, feedback, graph hints, or vector retrieval as proof.

QUESTION_ID: {task.get('question_id')}
TASK_TYPE: {task.get('task_type')}
USER QUESTION:
{task.get('question')}

TASK CONTRACT:
{json.dumps(contract, ensure_ascii=False, indent=2)}

EVIDENCE CARDS:
{evidence_text}

OUTPUT RULES:
- Use sections when appropriate: Answer, Evidence, Engineering confidence, Limits.
- For quiz_generation: create exactly 5 quiz questions plus an answer key; cite every answer.
- Use at least the required number of unique evidence labels and routes when available.
- Keep the entire response under {answer_hard_max_chars} characters.
- Finish the answer; do not stop mid-sentence.
"""


def call_ollama(prompt: str, model: str, url: str, timeout_seconds: int) -> str:
    payload = {"model": model, "prompt": prompt, "stream": False}
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    answer = data.get("response") or data.get("answer") or data.get("text") or ""
    if not str(answer).strip():
        raise RuntimeError("Ollama response did not contain answer text")
    return str(answer).strip()


def build_artifact_answer(task: Mapping[str, Any], evidence: list[EvidenceCard]) -> str:
    t = task.get("task_type")
    cited = evidence[:5]
    if t == "quiz_generation":
        lines = ["Answer:"]
        for i, c in enumerate(cited[:5], 1):
            subject = c.part_number or c.nomenclature or c.figure or c.page or c.route
            lines.append(f"{i}. What does evidence card [{c.label}] support about {subject}?")
        lines.append("\nAnswer key:")
        for i, c in enumerate(cited[:5], 1):
            claim = c.claim_supported
            if c.part_number:
                claim += f" for part {c.part_number}"
            if c.nomenclature:
                claim += f" / {c.nomenclature}"
            lines.append(f"{i}. {claim} [{c.label}]")
        lines.append("\nLimits: This quiz does not prove interchangeability, fit, effectivity, replacement approval, or installation safety.")
        return "\n".join(lines)
    labels = " ".join(f"[{c.label}]" for c in cited[:4])
    first = cited[0] if cited else EvidenceCard("E0", "none", "none")
    return (
        f"Answer:\nTRACE-Net can answer this task using selected source-trace-ready evidence {labels}. "
        f"The strongest selected card is [{first.label}] from route {first.route}.\n\n"
        f"Evidence:\n" + "\n".join(f"- [{c.label}] {c.prompt_line()}" for c in cited[:4]) +
        "\n\nEngineering confidence:\nMedium/high for claims directly supported by cited cards.\n\n"
        "Limits:\nThis does not prove interchangeability, effectivity, fit, replacement approval, or installation safety."
    )


def _citation_labels(text: str) -> list[str]:
    return CIT_RE.findall(text or "")


def _routes_for_labels(labels: Iterable[str], evidence: list[EvidenceCard]) -> set[str]:
    m = {c.label: c.route for c in evidence}
    return {m[x] for x in labels if x in m}


def _pages_figs_for_labels(labels: Iterable[str], evidence: list[EvidenceCard]) -> set[str]:
    m = {c.label: (c.page or c.figure or c.page_id or c.label) for c in evidence}
    return {m[x] for x in labels if x in m}


def validate_answer(task: Mapping[str, Any], answer: str, evidence: list[EvidenceCard], fallback_used: bool, answer_hard_max_chars: int, max_fallback_used: int) -> dict[str, Any]:
    contract = task.get("contract", {}) or {}
    labels = _citation_labels(answer)
    unique_labels = sorted(set(labels))
    routes = sorted(_routes_for_labels(unique_labels, evidence))
    pages_figs = sorted(_pages_figs_for_labels(unique_labels, evidence))
    findings: list[str] = []
    if fallback_used and max_fallback_used <= 0:
        findings.append("fallback_used_forbidden")
    if len(answer) > answer_hard_max_chars:
        findings.append("answer_over_hard_max_chars")
    if len(unique_labels) < int(contract.get("min_unique_evidence_labels", 1)):
        findings.append("too_few_unique_evidence_labels")
    if len(routes) < int(contract.get("min_unique_routes", 1)):
        findings.append("too_few_unique_routes")
    if int(contract.get("min_unique_pages_or_figures", 0)) and len(pages_figs) < int(contract.get("min_unique_pages_or_figures", 0)):
        findings.append("too_few_unique_pages_or_figures")
    lower = answer.lower()
    for phrase in contract.get("must_include", []) or []:
        if str(phrase).lower() not in lower:
            findings.append(f"missing_required_phrase:{phrase}")
    if contract.get("must_include_any"):
        if not any(str(p).lower() in lower for p in contract.get("must_include_any", [])):
            findings.append("missing_required_any_phrase")
    if task.get("task_type") == "quiz_generation":
        q_lines = [ln for ln in answer.splitlines() if re.match(r"^\s*(?:Q?\d+[\).]|[-*]\s*Q\d+)", ln.strip(), re.I)]
        if len(q_lines) < int(contract.get("min_quiz_questions", 5)):
            # This regex is intentionally conservative; allow all-cited answer key to pass with a warning only if answer key exists.
            if "answer key" not in lower:
                findings.append("quiz_questions_or_answer_key_missing")
            else:
                findings.append("quiz_question_count_low")
        if "answer key" not in lower:
            findings.append("answer_key_missing")
    forbidden = contract.get("forbidden_claims", []) or []
    for f in forbidden:
        f_low = str(f).lower()
        if f_low in lower and "does not prove" not in lower and "cannot prove" not in lower and "not prove" not in lower:
            findings.append(f"possible_forbidden_claim:{f}")
    unsupported_claim_count = sum(1 for f in findings if f.startswith("possible_forbidden_claim"))
    grade = "GOOD" if not findings else "PARTIAL"
    if unsupported_claim_count or (fallback_used and max_fallback_used <= 0):
        grade = "BAD" if unsupported_claim_count else "PARTIAL"
    return {
        "grade": grade,
        "findings": findings or ["contract_checks_passed"],
        "answer_citation_count": len(labels),
        "unique_evidence_label_count": len(unique_labels),
        "unique_evidence_labels": unique_labels,
        "unique_route_count": len(routes),
        "unique_routes": routes,
        "unique_page_or_figure_count": len(pages_figs),
        "unsupported_claim_count": unsupported_claim_count,
        "answer_char_count": len(answer),
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def build_custom_task_contract_run(
    output_dir: str | Path,
    image_visual_evidence_pack: str | Path | None = None,
    raw_ocr_nomenclature_extractor: str | Path | None = None,
    table_route_evidence_packager: str | Path | None = None,
    table_exact_search_adapter: str | Path | None = None,
    llm_mode: str = "artifact",
    ollama_model: str = "gemma4:26b",
    ollama_url: str = "http://127.0.0.1:11434/api/generate",
    timeout_seconds: int = 420,
    max_questions: int = 5,
    max_cards_per_question: int = 8,
    answer_hard_max_chars: int = 1500,
    max_fallback_used: int = 0,
    min_good_answers: int = 5,
    min_contract_pass: int = 5,
    progress: bool = True,
) -> dict[str, Any]:
    out = Path(output_dir)
    prompts = out / "p"
    answers = out / "a"
    traces = out / "t"
    for d in (out, prompts, answers, traces):
        d.mkdir(parents=True, exist_ok=True)
    cards = load_evidence_cards(image_visual_evidence_pack, raw_ocr_nomenclature_extractor, table_route_evidence_packager, table_exact_search_adapter)
    contracts = build_contract_records(max_questions=max_questions)
    records = []
    fallback_used_count = 0
    good_answer_count = 0
    bad_answer_count = 0
    contract_pass_count = 0
    started = time.time()
    for idx, task in enumerate(contracts, 1):
        selected = select_evidence_for_task(cards, task, max_cards=max_cards_per_question)
        prompt = build_prompt(task, selected, answer_hard_max_chars=answer_hard_max_chars)
        qid = task["question_id"]
        digest = hashlib.sha1(qid.encode("utf-8")).hexdigest()[:6]
        p_path = prompts / f"{idx:02d}_{qid}_{digest}_p.txt"
        a_path = answers / f"{idx:02d}_{qid}_{digest}_a.txt"
        t_path = traces / f"{idx:02d}_{qid}_{digest}_trace.json"
        p_path.write_text(prompt, encoding="utf-8")
        fallback_used = False
        llm_error = ""
        try:
            if llm_mode == "artifact":
                answer = build_artifact_answer(task, selected)
            elif llm_mode == "ollama":
                answer = call_ollama(prompt, ollama_model, ollama_url, timeout_seconds)
            else:
                raise ValueError(f"unsupported llm_mode={llm_mode}")
        except Exception as e:
            llm_error = str(e)
            fallback_used = True
            answer = build_artifact_answer(task, selected)
        a_path.write_text(answer, encoding="utf-8")
        validation = validate_answer(task, answer, selected, fallback_used, answer_hard_max_chars, max_fallback_used)
        if fallback_used:
            fallback_used_count += 1
        if validation["grade"] == "GOOD":
            good_answer_count += 1
        if validation["grade"] == "BAD":
            bad_answer_count += 1
        if validation["grade"] == "GOOD":
            contract_pass_count += 1
        rec = {
            "question_id": qid,
            "category": task.get("category"),
            "task_type": task.get("task_type"),
            "question": task.get("question"),
            "contract": task.get("contract"),
            "selected_evidence_labels": [c.label for c in selected],
            "selected_routes": sorted(set(c.route for c in selected)),
            "selected_evidence_cards": [asdict(c) for c in selected],
            "prompt_path": str(p_path),
            "answer_path": str(a_path),
            "trace_path": str(t_path),
            "llm_mode": llm_mode,
            "llm_model": ollama_model if llm_mode == "ollama" else "artifact",
            "llm_error": llm_error,
            "fallback_used": fallback_used,
            **validation,
            "answer_preview": answer[:2600],
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "unsafe": False,
        }
        write_json(t_path, rec)
        records.append(rec)
        if progress:
            elapsed = time.time() - started
            print(
                f"[H35 progress] {idx}/{len(contracts)} ({idx/len(contracts)*100:.1f}%) "
                f"qid={qid} grade={rec['grade']} fallback={fallback_used} "
                f"labels={validation['unique_evidence_label_count']} routes={validation['unique_route_count']} "
                f"chars={validation['answer_char_count']} elapsed={elapsed:.1f}s",
                flush=True,
            )
    summary = {
        "module": MODULE,
        "version": VERSION,
        "question_count": len(contracts),
        "evidence_card_count": len(cards),
        "good_answer_count": good_answer_count,
        "partial_answer_count": sum(1 for r in records if r["grade"] == "PARTIAL"),
        "bad_answer_count": bad_answer_count,
        "contract_pass_count": contract_pass_count,
        "fallback_used_count": fallback_used_count,
        "unsupported_claim_count": sum(r.get("unsupported_claim_count", 0) for r in records),
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "qdrant_read_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
        "write_attempt_count": 0,
        "unsafe_finding_count": 0,
        "quality_failures": [],
    }
    failures = []
    if good_answer_count < min_good_answers:
        failures.append("good_answer_count_below_min")
    if contract_pass_count < min_contract_pass:
        failures.append("contract_pass_count_below_min")
    if fallback_used_count > max_fallback_used:
        failures.append("fallback_used_count_above_max")
    if bad_answer_count > 0:
        failures.append("bad_answer_count_nonzero")
    summary["quality_failures"] = failures
    quality_status = "PASS" if not failures else "FAIL"
    manifest = {
        "status": "TRACE_NET_H35_CUSTOM_TASK_CONTRACT_RUN_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "task_contracts": contracts,
        "records": records,
        "contract_runner_policy": {
            "mode": "contract_first_custom_task_runner",
            "fallback_policy": "fallback is counted and can be forbidden with --max-fallback-used 0",
            "proof_boundary": SAFETY_CONTRACT["proof_boundary"],
            "forbidden": [
                "fallback_hidden_as_success",
                "engram_or_summary_or_feedback_used_as_proof",
                "interchangeability_or_approval_without_explicit_authority",
                "live_db_vector_or_graph_io",
            ],
        },
        "safety_contract": dict(SAFETY_CONTRACT),
    }
    write_json(out / f"{MODULE}.json", manifest)
    (out / f"{MODULE}_records.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in records) + "\n", encoding="utf-8")
    print(f"status=TRACE_NET_H35_CUSTOM_TASK_CONTRACT_RUN_BUILT")
    print(f"quality_status={quality_status}")
    print(f"question_count={len(contracts)}")
    print(f"good_answer_count={good_answer_count}")
    print(f"contract_pass_count={contract_pass_count}")
    print(f"fallback_used_count={fallback_used_count}")
    print(f"output={out / (MODULE + '.json')}")
    return manifest


def check_custom_task_contract_run(
    contract_run: str | Path,
    min_records: int = 5,
    min_good_answers: int = 5,
    min_contract_pass: int = 5,
    max_fallback_used: int = 0,
    require_quality_pass: bool = False,
    require_no_answer_permission: bool = True,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> dict[str, Any]:
    data = _load_json(contract_run)
    if not isinstance(data, dict):
        raise ValueError("contract_run must be a JSON object")
    summary = data.get("summary", {})
    failures = []
    if len(data.get("records", [])) < min_records:
        failures.append("record_count_below_min")
    if summary.get("good_answer_count", 0) < min_good_answers:
        failures.append("good_answer_count_below_min")
    if summary.get("contract_pass_count", 0) < min_contract_pass:
        failures.append("contract_pass_count_below_min")
    if summary.get("fallback_used_count", 0) > max_fallback_used:
        failures.append("fallback_used_count_above_max")
    if require_quality_pass and data.get("quality_status") != "PASS":
        failures.append("source_quality_not_pass")
    if require_no_answer_permission and summary.get("answer_permission_count", 0) != 0:
        failures.append("answer_permission_nonzero")
    if summary.get("unsafe_finding_count", 0) > max_unsafe:
        failures.append("unsafe_finding_count_above_max")
    if summary.get("write_attempt_count", 0) > max_write_attempts:
        failures.append("write_attempt_count_above_max")
    quality = "PASS" if not failures else "FAIL"
    result = {
        "status": "TRACE_NET_H35_CUSTOM_TASK_CONTRACT_RUN_CHECKED",
        "quality_status": quality,
        "quality_failures": failures,
        "record_count": len(data.get("records", [])),
        "good_answer_count": summary.get("good_answer_count", 0),
        "contract_pass_count": summary.get("contract_pass_count", 0),
        "fallback_used_count": summary.get("fallback_used_count", 0),
        "answer_permission_count": summary.get("answer_permission_count", 0),
        "unsafe_finding_count": summary.get("unsafe_finding_count", 0),
        "write_attempt_count": summary.get("write_attempt_count", 0),
    }
    print(f"status={result['status']}")
    print(f"quality_status={quality}")
    print(f"record_count={result['record_count']}")
    print(f"good_answer_count={result['good_answer_count']}")
    print(f"contract_pass_count={result['contract_pass_count']}")
    print(f"fallback_used_count={result['fallback_used_count']}")
    return result


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="TRACE-Net H35 custom task contract runner")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--image-visual-evidence-pack")
    p.add_argument("--raw-ocr-nomenclature-extractor")
    p.add_argument("--table-route-evidence-packager")
    p.add_argument("--table-exact-search-adapter")
    p.add_argument("--llm-mode", choices=["artifact", "ollama"], default="artifact")
    p.add_argument("--ollama-model", default="gemma4:26b")
    p.add_argument("--ollama-url", default="http://127.0.0.1:11434/api/generate")
    p.add_argument("--timeout-seconds", type=int, default=420)
    p.add_argument("--max-questions", type=int, default=5)
    p.add_argument("--max-cards-per-question", type=int, default=8)
    p.add_argument("--answer-hard-max-chars", type=int, default=1500)
    p.add_argument("--max-fallback-used", type=int, default=0)
    p.add_argument("--min-good-answers", type=int, default=5)
    p.add_argument("--min-contract-pass", type=int, default=5)
    p.add_argument("--no-progress", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    kwargs = vars(args).copy()
    no_progress = kwargs.pop("no_progress", False)
    build_custom_task_contract_run(progress=not no_progress, **kwargs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
