#!/usr/bin/env python3
"""TRACE-Net engineering real-answer smoke test v1.

Runs the engineering answer runner over a broader real-question bank and records
GOOD / PARTIAL / BAD / BLOCKED outcomes without changing retrieval, evidence, or
answer-composer logic.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

MODULE = "trace_net_engineering_real_answer_smoke_test_v1"
VERSION = "v1"

DEFAULT_QUESTIONS: List[Dict[str, str]] = [
    {"id": "q01", "category": "figure_lookup", "question": "What does figure 69 show?"},
    {"id": "q02", "category": "figure_lookup", "question": "What does figure 75 show?"},
    {"id": "q03", "category": "figure_lookup", "question": "What does figure 91 show?"},
    {"id": "q04", "category": "comparison", "question": "Compare figure 69 and figure 75."},
    {"id": "q05", "category": "comparison", "question": "Compare figure 75 and figure 91."},
    {"id": "q06", "category": "exact_part_lookup", "question": "Find part number 120-50645-005 and cite the source."},
    {"id": "q07", "category": "exact_part_lookup", "question": "Find part number 120-50645-011 and cite the source."},
    {"id": "q08", "category": "exact_part_lookup", "question": "Find part number 120-29068-003 and cite the source."},
    {"id": "q09", "category": "evidence_support", "question": "What evidence supports part number 120-50645-005?"},
    {"id": "q10", "category": "evidence_support", "question": "What evidence supports Figure 69?"},
    {"id": "q11", "category": "limitations", "question": "What can TRACE-Net not prove about part number 120-50645-005?"},
    {"id": "q12", "category": "interchangeability", "question": "Is 120-50645-005 interchangeable with 120-50645-011?"},
    {"id": "q13", "category": "installation_safety", "question": "Does figure 69 prove installation safety?"},
    {"id": "q14", "category": "fit_limit", "question": "Does figure 75 prove fit approval?"},
    {"id": "q15", "category": "effectivity_limit", "question": "Does figure 91 prove aircraft effectivity?"},
    {"id": "q16", "category": "troubleshooting", "question": "Why was nomenclature missing from the visual route evidence?"},
    {"id": "q17", "category": "troubleshooting", "question": "Why does the visual route need OCR nomenclature evidence?"},
    {"id": "q18", "category": "pipeline_recovery", "question": "What changed after the raw OCR nomenclature extractor was added?"},
    {"id": "q19", "category": "source_page", "question": "What source page supports the nomenclature for Figure 69?"},
    {"id": "q20", "category": "source_page", "question": "Cite the proof for Figure 75's part number."},
    {"id": "q21", "category": "replacement_limit", "question": "Is 120-50645-005 an approved replacement for 120-50645-011?"},
    {"id": "q22", "category": "installation_safety", "question": "Can I safely install 120-50645-005 based only on Figure 69?"},
    {"id": "q23", "category": "nomenclature_summary", "question": "Summarize the evidence for DOUBLE PASSENGER SEAT ASSY."},
    {"id": "q24", "category": "nomenclature_summary", "question": "Which figures link to DOUBLE PASSENGER SEAT ASSY?"},
    {"id": "q25", "category": "unknown_part", "question": "Find part number 999-99999-999 and cite the source."},
    {"id": "q26", "category": "unknown_figure", "question": "What does figure 999 show?"},
    {"id": "q27", "category": "evidence_explanation", "question": "Explain the difference between visual proof and OCR proof for Figure 69."},
    {"id": "q28", "category": "route_explanation", "question": "What routes were required to answer what Figure 69 shows?"},
    {"id": "q29", "category": "summary_limit", "question": "Can v2 summaries alone prove Figure 69 part identity?"},
    {"id": "q30", "category": "limitations", "question": "Give the engineering limitations for Figure 91."},
]

INTENT_NEEDLES = (
    "interchange", "replacement", "install", "safety", "fit", "effectivity",
    "not prove", "cannot prove", "can't prove", "what can trace-net not prove",
    "why", "missing", "need ocr", "compare", "evidence supports", "v2 summaries alone",
)


def _write_json(path: Any, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Any, rows: Iterable[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_csv(path: Any, rows: List[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "question_id", "category", "question", "grade", "runner_passed", "quality_status",
        "task_type", "intent_answer_used", "intent_answer_type", "stage_pass_count",
        "proof_context_count", "answer_citation_count", "source_trace_ready_citation_count",
        "unsupported_claim_count", "summary_used_as_proof_count", "invalid_answer_citation_count",
        "unsafe_record_count", "answer_permission_count", "source_truth_mutation_allowed_count",
        "write_attempt_count", "failure_reason", "answer_preview", "run_dir",
    ]
    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _load_json(path: Any) -> Dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def _hash(text: str, n: int = 8) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:n]


def _hint(category: str, question: str) -> str:
    c = (category or "").lower()
    q = (question or "").lower()
    if "figure" in c or re.search(r"\bfigure\s*\d+", q):
        return "fig"
    if "part" in c or re.search(r"\d{3}-\d{5}-\d{3}", q):
        return "part"
    if "compare" in c or "compare" in q:
        return "compare"
    if "interchange" in c or "interchange" in q:
        return "inter"
    if "safety" in c or "install" in q:
        return "safe"
    if "trouble" in c or "why" in q:
        return "debug"
    if "limit" in c or "prove" in q:
        return "limit"
    return "q"


def _short_run_dir(runs_dir: Path, idx: int, question: str, category: str) -> Path:
    return runs_dir / f"q{idx:02d}_{_hint(category, question)}_{_hash(question)}"


def _normalize_questions(questions: Optional[Sequence[str]] = None, question_file: Optional[Any] = None, max_questions: Optional[int] = None) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    if question_file:
        p = Path(question_file)
        text = p.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            if line.startswith("{"):
                obj = json.loads(line)
                q = str(obj.get("question") or "").strip()
                if q:
                    rows.append({"id": str(obj.get("id") or f"q{i:02d}"), "category": str(obj.get("category") or "custom"), "question": q})
            else:
                rows.append({"id": f"q{i:02d}", "category": "custom", "question": line})
    elif questions:
        for i, q in enumerate(questions, 1):
            rows.append({"id": f"q{i:02d}", "category": "custom", "question": str(q)})
    else:
        rows = [dict(x) for x in DEFAULT_QUESTIONS]
    if max_questions and max_questions > 0:
        rows = rows[:max_questions]
    return rows


def _summary_from_runner(data: Mapping[str, Any]) -> Dict[str, Any]:
    return dict(data.get("summary") or {})


def _answer_from(data: Mapping[str, Any]) -> str:
    return str(data.get("answer_text") or data.get("answer") or "")


def _needs_intent_composer(question: str, category: str) -> bool:
    text = f"{category} {question}".lower()
    return any(n in text for n in INTENT_NEEDLES)


def _run_subprocess(cmd: List[str]) -> Tuple[int, str, str]:
    proc = subprocess.run(cmd, text=True, capture_output=True)
    return proc.returncode, proc.stdout[-4000:], proc.stderr[-4000:]


def _base_runner_cmd(
    *, question: str, run_dir: Path, v2_summary_guidance_index: Any, image_visual_evidence_pack: Any,
    raw_ocr_nomenclature_extractor: Any, table_route_evidence_packager: Any, table_exact_search_adapter: Any,
    max_guidance_pages: int, min_planner_records: int, min_required_routes: int, min_guidance_context: int,
    min_proof_context: int, min_source_trace_ready: int, min_answer_citations: int,
    min_source_trace_ready_citations: int, max_unsupported_claims: int, max_summary_used_as_proof: int,
    max_invalid_citations: int, max_llava_only_part_identity_claims: int, max_unsafe: int,
    max_answer_permission: int, max_source_truth_mutation_allowed: int, max_write_attempts: int,
) -> List[str]:
    return [
        sys.executable, "-B", "scripts/build/ingestion/build_trace_net_engineering_answer_runner_v1.py",
        "--question", question,
        "--v2-summary-guidance-index", str(v2_summary_guidance_index),
        "--image-visual-evidence-pack", str(image_visual_evidence_pack),
        "--raw-ocr-nomenclature-extractor", str(raw_ocr_nomenclature_extractor),
        "--table-route-evidence-packager", str(table_route_evidence_packager),
        "--table-exact-search-adapter", str(table_exact_search_adapter),
        "--output-dir", str(run_dir),
        "--max-guidance-pages", str(max_guidance_pages),
        "--min-planner-records", str(min_planner_records),
        "--min-required-routes", str(min_required_routes),
        "--min-guidance-context", str(min_guidance_context),
        "--min-proof-context", str(min_proof_context),
        "--min-source-trace-ready", str(min_source_trace_ready),
        "--min-answer-citations", str(min_answer_citations),
        "--min-source-trace-ready-citations", str(min_source_trace_ready_citations),
        "--max-unsupported-claims", str(max_unsupported_claims),
        "--max-summary-used-as-proof", str(max_summary_used_as_proof),
        "--max-invalid-citations", str(max_invalid_citations),
        "--max-llava-only-part-identity-claims", str(max_llava_only_part_identity_claims),
        "--max-unsafe", str(max_unsafe),
        "--max-answer-permission", str(max_answer_permission),
        "--max-source-truth-mutation-allowed", str(max_source_truth_mutation_allowed),
        "--max-write-attempts", str(max_write_attempts),
        "--require-quality-pass", "--require-engineering-answer-ready",
    ]


def _intent_cmd(
    *, runner_path: Path, out_dir: Path, min_answer_citations: int, min_source_trace_ready_citations: int,
    max_unsupported_claims: int, max_summary_used_as_proof: int, max_invalid_citations: int,
    max_llava_only_part_identity_claims: int, max_unsafe: int, max_answer_permission: int,
    max_source_truth_mutation_allowed: int, max_write_attempts: int,
) -> List[str]:
    return [
        sys.executable, "-B", "scripts/build/ingestion/build_trace_net_engineering_intent_answer_composer_v1.py",
        "--runner", str(runner_path),
        "--output-dir", str(out_dir),
        "--min-answer-citations", str(min_answer_citations),
        "--min-source-trace-ready-citations", str(min_source_trace_ready_citations),
        "--max-unsupported-claims", str(max_unsupported_claims),
        "--max-summary-used-as-proof", str(max_summary_used_as_proof),
        "--max-invalid-citations", str(max_invalid_citations),
        "--max-llava-only-part-identity-claims", str(max_llava_only_part_identity_claims),
        "--max-unsafe", str(max_unsafe),
        "--max-answer-permission", str(max_answer_permission),
        "--max-source-truth-mutation-allowed", str(max_source_truth_mutation_allowed),
        "--max-write-attempts", str(max_write_attempts),
        "--require-quality-pass",
    ]


def _grade_record(row: Mapping[str, Any], answer: str) -> str:
    if int(row.get("unsafe_record_count") or 0) > 0 or int(row.get("unsupported_claim_count") or 0) > 0:
        return "BAD"
    if int(row.get("summary_used_as_proof_count") or 0) > 0 or int(row.get("invalid_answer_citation_count") or 0) > 0:
        return "BAD"
    if not row.get("runner_passed"):
        return "BLOCKED"
    citations = int(row.get("source_trace_ready_citation_count") or 0)
    proof = int(row.get("proof_context_count") or 0)
    text = (answer or "").lower()
    q = str(row.get("question") or "").lower()
    intent_hits = 0
    if "interchange" in q:
        intent_hits += int("cannot prove" in text or "not prove" in text or "not approval" in text)
    if "install" in q or "safety" in q or "fit" in q or "effectivity" in q:
        intent_hits += int("does not prove" in text or "cannot prove" in text or "not" in text)
    if "compare" in q:
        intent_hits += int("figure 69" in text and "figure 75" in text)
    if "why" in q or "missing" in q:
        intent_hits += int("because" in text or "missing" in text or "recovered" in text)
    if citations >= 2 and proof >= 2 and (intent_hits > 0 or not _needs_intent_composer(q, str(row.get("category") or ""))):
        return "GOOD"
    return "PARTIAL"


def check_real_answer_smoke_test(
    *, manifest: Any, output: Optional[Any] = None, require_quality_pass: bool = False,
    min_smoke_questions: int = 1, min_good_answers: int = 1, min_good_or_partial_answers: int = 1,
    max_bad_answers: int = 0, max_unsupported_claims: int = 0, max_summary_used_as_proof: int = 0,
    max_invalid_citations: int = 0, max_llava_only_part_identity_claims: int = 0, max_unsafe: int = 0,
    max_answer_permission: int = 0, max_source_truth_mutation_allowed: int = 0, max_write_attempts: int = 0,
) -> Dict[str, Any]:
    data = _load_json(manifest)
    s = dict(data.get("summary") or {})
    failures: List[str] = []
    if int(s.get("smoke_question_count") or 0) < min_smoke_questions:
        failures.append(f"smoke_question_count below minimum: {s.get('smoke_question_count')} < {min_smoke_questions}")
    if int(s.get("good_answer_count") or 0) < min_good_answers:
        failures.append(f"good_answer_count below minimum: {s.get('good_answer_count')} < {min_good_answers}")
    if int(s.get("good_or_partial_answer_count") or 0) < min_good_or_partial_answers:
        failures.append(f"good_or_partial_answer_count below minimum: {s.get('good_or_partial_answer_count')} < {min_good_or_partial_answers}")
    checks = [
        ("bad_answer_count", max_bad_answers),
        ("unsupported_claim_count", max_unsupported_claims),
        ("summary_used_as_proof_count", max_summary_used_as_proof),
        ("invalid_answer_citation_count", max_invalid_citations),
        ("llava_only_part_identity_claim_count", max_llava_only_part_identity_claims),
        ("unsafe_record_count", max_unsafe),
        ("answer_permission_count", max_answer_permission),
        ("source_truth_mutation_allowed_count", max_source_truth_mutation_allowed),
        ("write_attempt_count", max_write_attempts),
    ]
    for key, max_value in checks:
        if int(s.get(key) or 0) > max_value:
            failures.append(f"{key} above maximum: {s.get(key)} > {max_value}")
    quality_status = "PASS" if not failures else "FAIL"
    result = {
        "status": "TRACE_NET_ENGINEERING_REAL_ANSWER_SMOKE_TEST_CHECKED",
        "quality_status": quality_status,
        "failures": failures,
        "summary": s,
    }
    if output:
        _write_json(output, result)
    if require_quality_pass and quality_status != "PASS":
        for f in failures:
            print("failure=" + f)
        raise SystemExit("quality_status is not PASS")
    return result


def build_real_answer_smoke_test(
    *,
    v2_summary_guidance_index: Any,
    image_visual_evidence_pack: Any,
    raw_ocr_nomenclature_extractor: Any,
    table_route_evidence_packager: Any,
    table_exact_search_adapter: Any,
    output_dir: Any,
    questions: Optional[Sequence[str]] = None,
    question_file: Optional[Any] = None,
    max_questions: int = 30,
    max_guidance_pages: int = 8,
    min_planner_records: int = 1,
    min_required_routes: int = 1,
    min_guidance_context: int = 0,
    min_proof_context: int = 2,
    min_source_trace_ready: int = 2,
    min_answer_citations: int = 2,
    min_source_trace_ready_citations: int = 2,
    min_smoke_questions: int = 10,
    min_good_answers: int = 5,
    min_good_or_partial_answers: int = 10,
    max_bad_answers: int = 0,
    max_unsupported_claims: int = 0,
    max_summary_used_as_proof: int = 0,
    max_invalid_citations: int = 0,
    max_llava_only_part_identity_claims: int = 0,
    max_unsafe: int = 0,
    max_answer_permission: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    max_write_attempts: int = 0,
    enable_intent_composer: bool = True,
    require_quality_pass: bool = False,
) -> Dict[str, Any]:
    out_dir = Path(output_dir)
    runs_dir = out_dir / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)

    question_rows = _normalize_questions(questions=questions, question_file=question_file, max_questions=max_questions)
    _write_jsonl(out_dir / "trace_net_engineering_real_answer_smoke_test_v1_question_bank.jsonl", question_rows)

    records: List[Dict[str, Any]] = []
    for idx, qrow in enumerate(question_rows, 1):
        question = qrow["question"]
        category = qrow.get("category") or "custom"
        run_dir = _short_run_dir(runs_dir, idx, question, category)
        run_dir.mkdir(parents=True, exist_ok=True)
        runner_path = run_dir / "trace_net_engineering_answer_runner_v1.json"

        record: Dict[str, Any] = {
            "question_id": qrow.get("id") or f"q{idx:02d}",
            "category": category,
            "question": question,
            "run_dir": str(run_dir),
            "runner_path": str(runner_path),
            "runner_passed": False,
            "quality_status": "FAIL",
            "intent_answer_used": False,
            "intent_answer_type": "",
            "failure_reason": "",
            "error": "",
        }

        cmd = _base_runner_cmd(
            question=question, run_dir=run_dir,
            v2_summary_guidance_index=v2_summary_guidance_index,
            image_visual_evidence_pack=image_visual_evidence_pack,
            raw_ocr_nomenclature_extractor=raw_ocr_nomenclature_extractor,
            table_route_evidence_packager=table_route_evidence_packager,
            table_exact_search_adapter=table_exact_search_adapter,
            max_guidance_pages=max_guidance_pages,
            min_planner_records=min_planner_records,
            min_required_routes=min_required_routes,
            min_guidance_context=min_guidance_context,
            min_proof_context=min_proof_context,
            min_source_trace_ready=min_source_trace_ready,
            min_answer_citations=min_answer_citations,
            min_source_trace_ready_citations=min_source_trace_ready_citations,
            max_unsupported_claims=max_unsupported_claims,
            max_summary_used_as_proof=max_summary_used_as_proof,
            max_invalid_citations=max_invalid_citations,
            max_llava_only_part_identity_claims=max_llava_only_part_identity_claims,
            max_unsafe=max_unsafe,
            max_answer_permission=max_answer_permission,
            max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
            max_write_attempts=max_write_attempts,
        )
        rc, stdout, stderr = _run_subprocess(cmd)
        record["runner_returncode"] = rc
        record["runner_stdout_tail"] = stdout
        record["runner_stderr_tail"] = stderr

        runner_data: Dict[str, Any] = {}
        if runner_path.exists():
            runner_data = _load_json(runner_path)
            rs = _summary_from_runner(runner_data)
            record.update({
                "quality_status": runner_data.get("quality_status"),
                "task_type": rs.get("task_type"),
                "stage_pass_count": int(rs.get("stage_pass_count") or 0),
                "proof_context_count": int(rs.get("proof_context_count") or 0),
                "answer_citation_count": int(rs.get("answer_citation_count") or 0),
                "valid_answer_citation_count": int(rs.get("valid_answer_citation_count") or 0),
                "source_trace_ready_citation_count": int(rs.get("source_trace_ready_citation_count") or 0),
                "unsupported_claim_count": int(rs.get("unsupported_claim_count") or 0),
                "summary_used_as_proof_count": int(rs.get("summary_used_as_proof_count") or 0),
                "invalid_answer_citation_count": int(rs.get("invalid_answer_citation_count") or 0),
                "llava_only_part_identity_claim_count": int(rs.get("llava_only_part_identity_claim_count") or 0),
                "unsafe_record_count": int(rs.get("unsafe_record_count") or 0),
                "answer_permission_count": int(rs.get("answer_permission_count") or 0),
                "source_truth_mutation_allowed_count": int(rs.get("source_truth_mutation_allowed_count") or 0),
                "write_attempt_count": int(rs.get("write_attempt_count") or 0),
                "ready_for_engineering_answer_delivery": bool(rs.get("ready_for_engineering_answer_delivery")),
            })
            record["runner_passed"] = runner_data.get("quality_status") == "PASS" and bool(rs.get("ready_for_engineering_answer_delivery"))
        else:
            record["failure_reason"] = "runner_manifest_missing"
            record["error"] = stderr or stdout

        answer_text = _answer_from(runner_data)

        if enable_intent_composer and runner_path.exists() and _needs_intent_composer(question, category):
            intent_dir = run_dir / "intent_answer"
            intent_path = intent_dir / "trace_net_engineering_intent_answer_composer_v1.json"
            icmd = _intent_cmd(
                runner_path=runner_path, out_dir=intent_dir,
                min_answer_citations=min_answer_citations,
                min_source_trace_ready_citations=min_source_trace_ready_citations,
                max_unsupported_claims=max_unsupported_claims,
                max_summary_used_as_proof=max_summary_used_as_proof,
                max_invalid_citations=max_invalid_citations,
                max_llava_only_part_identity_claims=max_llava_only_part_identity_claims,
                max_unsafe=max_unsafe,
                max_answer_permission=max_answer_permission,
                max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
                max_write_attempts=max_write_attempts,
            )
            irc, istdout, istderr = _run_subprocess(icmd)
            record["intent_returncode"] = irc
            record["intent_stdout_tail"] = istdout
            record["intent_stderr_tail"] = istderr
            if intent_path.exists():
                idata = _load_json(intent_path)
                isummary = dict(idata.get("summary") or {})
                if idata.get("quality_status") == "PASS":
                    record["intent_answer_used"] = True
                    record["intent_answer_type"] = isummary.get("intent_answer_type") or ""
                    answer_text = _answer_from(idata)
                    for key in [
                        "answer_citation_count", "valid_answer_citation_count", "source_trace_ready_citation_count",
                        "unsupported_claim_count", "summary_used_as_proof_count", "invalid_answer_citation_count",
                        "llava_only_part_identity_claim_count", "unsafe_record_count", "answer_permission_count",
                        "source_truth_mutation_allowed_count", "write_attempt_count",
                    ]:
                        if key in isummary:
                            record[key] = int(isummary.get(key) or 0)

        record["answer_text"] = answer_text
        record["answer_preview"] = answer_text[:800]
        record["grade"] = _grade_record(record, answer_text)
        records.append(record)

    summary = {
        "module": MODULE,
        "version": VERSION,
        "smoke_question_count": len(records),
        "source_question_count": len(question_rows),
        "good_answer_count": sum(1 for r in records if r.get("grade") == "GOOD"),
        "partial_answer_count": sum(1 for r in records if r.get("grade") == "PARTIAL"),
        "bad_answer_count": sum(1 for r in records if r.get("grade") == "BAD"),
        "blocked_answer_count": sum(1 for r in records if r.get("grade") == "BLOCKED"),
        "good_or_partial_answer_count": sum(1 for r in records if r.get("grade") in {"GOOD", "PARTIAL"}),
        "runner_pass_count": sum(1 for r in records if r.get("runner_passed")),
        "runner_fail_count": sum(1 for r in records if not r.get("runner_passed")),
        "intent_answer_used_count": sum(1 for r in records if r.get("intent_answer_used")),
        "stage_pass_count": sum(int(r.get("stage_pass_count") or 0) for r in records),
        "proof_context_count": sum(int(r.get("proof_context_count") or 0) for r in records),
        "answer_citation_count": sum(int(r.get("answer_citation_count") or 0) for r in records),
        "valid_answer_citation_count": sum(int(r.get("valid_answer_citation_count") or 0) for r in records),
        "source_trace_ready_citation_count": sum(int(r.get("source_trace_ready_citation_count") or 0) for r in records),
        "unsupported_claim_count": sum(int(r.get("unsupported_claim_count") or 0) for r in records),
        "summary_used_as_proof_count": sum(int(r.get("summary_used_as_proof_count") or 0) for r in records),
        "invalid_answer_citation_count": sum(int(r.get("invalid_answer_citation_count") or 0) for r in records),
        "llava_only_part_identity_claim_count": sum(int(r.get("llava_only_part_identity_claim_count") or 0) for r in records),
        "answer_permission_count": sum(int(r.get("answer_permission_count") or 0) for r in records),
        "source_truth_mutation_allowed_count": sum(int(r.get("source_truth_mutation_allowed_count") or 0) for r in records),
        "write_attempt_count": sum(int(r.get("write_attempt_count") or 0) for r in records),
        "unsafe_record_count": sum(int(r.get("unsafe_record_count") or 0) for r in records),
        "categories": sorted({str(r.get("category")) for r in records}),
        "ready_for_user_facing_answer_smoke": True,
    }
    manifest = {
        "status": "TRACE_NET_ENGINEERING_REAL_ANSWER_SMOKE_TEST_BUILT",
        "quality_status": "PASS",
        "summary": summary,
        "records": records,
        "paths": {
            "question_bank": str(out_dir / "trace_net_engineering_real_answer_smoke_test_v1_question_bank.jsonl"),
            "records_csv": str(out_dir / "trace_net_engineering_real_answer_smoke_test_v1_records.csv"),
        },
    }

    _write_csv(out_dir / "trace_net_engineering_real_answer_smoke_test_v1_records.csv", records)
    manifest_path = out_dir / "trace_net_engineering_real_answer_smoke_test_v1.json"
    _write_json(manifest_path, manifest)
    qc = check_real_answer_smoke_test(
        manifest=manifest_path,
        output=out_dir / "trace_net_engineering_real_answer_smoke_test_v1_quality_check.json",
        require_quality_pass=False,
        min_smoke_questions=min_smoke_questions,
        min_good_answers=min_good_answers,
        min_good_or_partial_answers=min_good_or_partial_answers,
        max_bad_answers=max_bad_answers,
        max_unsupported_claims=max_unsupported_claims,
        max_summary_used_as_proof=max_summary_used_as_proof,
        max_invalid_citations=max_invalid_citations,
        max_llava_only_part_identity_claims=max_llava_only_part_identity_claims,
        max_unsafe=max_unsafe,
        max_answer_permission=max_answer_permission,
        max_source_truth_mutation_allowed=max_source_truth_mutation_allowed,
        max_write_attempts=max_write_attempts,
    )
    manifest["quality_status"] = qc["quality_status"]
    manifest["quality_check"] = qc
    _write_json(manifest_path, manifest)

    print("status=" + str(manifest["status"]))
    print("quality_status=" + str(manifest["quality_status"]))
    for k in [
        "smoke_question_count", "good_answer_count", "partial_answer_count", "bad_answer_count",
        "blocked_answer_count", "runner_pass_count", "intent_answer_used_count",
        "summary_used_as_proof_count", "unsupported_claim_count", "unsafe_record_count",
    ]:
        print(f"{k}={manifest['summary'].get(k)}")
    print("smoke_test=" + str(manifest_path))

    if require_quality_pass and manifest["quality_status"] != "PASS":
        raise SystemExit("quality_status is not PASS")
    return manifest


def build_parser(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build TRACE-Net engineering real-answer smoke test v1")
    p.add_argument("--question", action="append", dest="questions", default=[])
    p.add_argument("--question-file")
    p.add_argument("--v2-summary-guidance-index", required=True)
    p.add_argument("--image-visual-evidence-pack", required=True)
    p.add_argument("--raw-ocr-nomenclature-extractor", required=True)
    p.add_argument("--table-route-evidence-packager", required=True)
    p.add_argument("--table-exact-search-adapter", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--max-questions", type=int, default=30)
    p.add_argument("--max-guidance-pages", type=int, default=8)
    p.add_argument("--min-planner-records", type=int, default=1)
    p.add_argument("--min-required-routes", type=int, default=1)
    p.add_argument("--min-guidance-context", type=int, default=0)
    p.add_argument("--min-proof-context", type=int, default=2)
    p.add_argument("--min-source-trace-ready", type=int, default=2)
    p.add_argument("--min-answer-citations", type=int, default=2)
    p.add_argument("--min-source-trace-ready-citations", type=int, default=2)
    p.add_argument("--min-smoke-questions", type=int, default=10)
    p.add_argument("--min-good-answers", type=int, default=5)
    p.add_argument("--min-good-or-partial-answers", type=int, default=10)
    p.add_argument("--max-bad-answers", type=int, default=0)
    p.add_argument("--max-unsupported-claims", type=int, default=0)
    p.add_argument("--max-summary-used-as-proof", type=int, default=0)
    p.add_argument("--max-invalid-citations", type=int, default=0)
    p.add_argument("--max-llava-only-part-identity-claims", type=int, default=0)
    p.add_argument("--max-unsafe", type=int, default=0)
    p.add_argument("--max-answer-permission", type=int, default=0)
    p.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    p.add_argument("--max-write-attempts", type=int, default=0)
    p.add_argument("--disable-intent-composer", action="store_true")
    p.add_argument("--require-quality-pass", action="store_true")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    a = build_parser(argv)
    build_real_answer_smoke_test(
        v2_summary_guidance_index=a.v2_summary_guidance_index,
        image_visual_evidence_pack=a.image_visual_evidence_pack,
        raw_ocr_nomenclature_extractor=a.raw_ocr_nomenclature_extractor,
        table_route_evidence_packager=a.table_route_evidence_packager,
        table_exact_search_adapter=a.table_exact_search_adapter,
        output_dir=a.output_dir,
        questions=a.questions,
        question_file=a.question_file,
        max_questions=a.max_questions,
        max_guidance_pages=a.max_guidance_pages,
        min_planner_records=a.min_planner_records,
        min_required_routes=a.min_required_routes,
        min_guidance_context=a.min_guidance_context,
        min_proof_context=a.min_proof_context,
        min_source_trace_ready=a.min_source_trace_ready,
        min_answer_citations=a.min_answer_citations,
        min_source_trace_ready_citations=a.min_source_trace_ready_citations,
        min_smoke_questions=a.min_smoke_questions,
        min_good_answers=a.min_good_answers,
        min_good_or_partial_answers=a.min_good_or_partial_answers,
        max_bad_answers=a.max_bad_answers,
        max_unsupported_claims=a.max_unsupported_claims,
        max_summary_used_as_proof=a.max_summary_used_as_proof,
        max_invalid_citations=a.max_invalid_citations,
        max_llava_only_part_identity_claims=a.max_llava_only_part_identity_claims,
        max_unsafe=a.max_unsafe,
        max_answer_permission=a.max_answer_permission,
        max_source_truth_mutation_allowed=a.max_source_truth_mutation_allowed,
        max_write_attempts=a.max_write_attempts,
        enable_intent_composer=not a.disable_intent_composer,
        require_quality_pass=a.require_quality_pass,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
