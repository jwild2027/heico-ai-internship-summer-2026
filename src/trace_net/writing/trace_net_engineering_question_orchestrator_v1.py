
"""TRACE-Net Engineering Question Orchestrator v1.

Single-command controlled question lookup over existing TRACE-Net engineering
artifacts.

v1 is intentionally conservative:
- it does not run retrieval
- it does not call Gemma
- it does not mutate source truth
- it matches a user question to an already-built, final-gated draft
- it returns a manual-review-ready draft only when Final Gate allowed it
- final answer permission remains false

This is the first "ask a question" interface for the controlled pipeline:
question -> matched final-gate record -> draft response artifact -> gated response packet.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence


MODULE_VERSION = "trace_net_engineering_question_orchestrator_v1"
REPORT_NAME = "trace_net_engineering_question_orchestrator_v1.json"


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing JSON file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _normalize(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _path(path_text: Any) -> Path:
    return Path(str(path_text or "").replace("\\", "/"))


def _match_score(query: str, candidate: str, match_mode: str) -> int:
    q = _normalize(query)
    c = _normalize(candidate)
    if not q or not c:
        return 0
    if q == c:
        return 100
    if match_mode == "exact":
        return 0
    if match_mode == "contains" and (q in c or c in q):
        return 80
    q_terms = set(re.findall(r"[a-z0-9-]+", q))
    c_terms = set(re.findall(r"[a-z0-9-]+", c))
    if not q_terms:
        return 0
    overlap = len(q_terms & c_terms)
    return int(60 * (overlap / max(1, len(q_terms))))


def _find_best_final_gate_record(records: Sequence[Mapping[str, Any]], question: str, match_mode: str) -> Optional[Dict[str, Any]]:
    best: Optional[Dict[str, Any]] = None
    best_score = -1
    for record in records:
        score = _match_score(question, str(record.get("user_question") or ""), match_mode)
        if score > best_score:
            best_score = score
            best = dict(record)
            best["_question_match_score"] = score
    if best is None or best_score <= 0:
        return None
    return best


def _find_runner_record(records: Sequence[Mapping[str, Any]], final_gate_record: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    target_runner_id = final_gate_record.get("source_runner_record_id")
    target_packet_id = final_gate_record.get("source_draft_packet_id")
    for record in records:
        if target_runner_id and record.get("runner_record_id") == target_runner_id:
            return record
    for record in records:
        if target_packet_id and record.get("source_draft_packet_id") == target_packet_id:
            return record
    return None


def _read_draft_text(runner_record: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not runner_record:
        return {"draft_text": "", "draft_response_path": None, "draft_read_error": "missing_runner_record"}
    path_text = runner_record.get("draft_response_path")
    if not path_text:
        return {"draft_text": "", "draft_response_path": None, "draft_read_error": "missing_draft_response_path"}
    path = _path(path_text)
    if not path.exists():
        return {"draft_text": "", "draft_response_path": str(path), "draft_read_error": f"draft response file not found: {path}"}
    payload = _read_json(path)
    return {
        "draft_text": str(payload.get("draft_text") or ""),
        "draft_response_path": str(path),
        "draft_read_error": None,
        "raw_response_available": bool(payload.get("raw_response")),
    }


def build_question_record(
    *,
    question: str,
    final_gate_record: Optional[Mapping[str, Any]],
    runner_record: Optional[Mapping[str, Any]],
    allow_manual_review_ready_only: bool,
) -> Dict[str, Any]:
    if final_gate_record is None:
        return {
            "question_orchestrator_record_version": MODULE_VERSION,
            "question": question,
            "question_match_status": "no_matching_final_gate_record",
            "question_match_score": 0,
            "controlled_response_status": "no_response_available",
            "response_text": "",
            "response_available_for_manual_review": False,
            "ready_for_final_answer": False,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "llm_call_allowed": False,
            "retrieval_execution_allowed": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_attempt": False,
            "qdrant_write_attempt": False,
            "opensearch_write_attempt": False,
            "unsafe": False,
        }

    draft = _read_draft_text(runner_record)
    final_gate_status = final_gate_record.get("final_gate_status")
    ready_for_manual_review = bool(final_gate_record.get("ready_for_manual_review"))
    blocked = final_gate_status == "FINAL_GATE_BLOCKED"
    has_text = bool(draft.get("draft_text"))

    response_text = ""
    response_available = False
    if ready_for_manual_review and has_text:
        response_text = str(draft.get("draft_text") or "")
        response_available = True
    elif not allow_manual_review_ready_only and has_text:
        response_text = str(draft.get("draft_text") or "")
        response_available = False

    if blocked:
        status = "final_gate_blocked"
    elif ready_for_manual_review and has_text:
        status = "manual_review_ready_draft_available"
    elif ready_for_manual_review and not has_text:
        status = "manual_review_ready_but_draft_text_missing"
    else:
        status = "not_manual_review_ready"

    return {
        "question_orchestrator_record_version": MODULE_VERSION,
        "question": question,
        "question_match_status": "matched_final_gate_record",
        "question_match_score": final_gate_record.get("_question_match_score", 0),
        "matched_user_question": final_gate_record.get("user_question"),
        "source_final_gate_record_id": final_gate_record.get("final_gate_record_id"),
        "source_runner_record_id": final_gate_record.get("source_runner_record_id"),
        "source_draft_packet_id": final_gate_record.get("source_draft_packet_id"),
        "model_id": final_gate_record.get("model_id"),
        "intent_family": final_gate_record.get("intent_family"),
        "final_gate_status": final_gate_status,
        "blocking_reasons": final_gate_record.get("blocking_reasons") or [],
        "warning_reasons": final_gate_record.get("warning_reasons") or [],
        "draft_response_path": draft.get("draft_response_path"),
        "draft_read_error": draft.get("draft_read_error"),
        "controlled_response_status": status,
        "response_text": response_text,
        "response_text_char_count": len(response_text),
        "response_available_for_manual_review": response_available,
        "human_review_required": True,
        "ready_for_final_answer": False,
        "answer_permission": False,
        "answers_user_question": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "llm_call_allowed": False,
        "retrieval_execution_allowed": False,
        "source_truth_mutation_allowed": False,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
        "unsafe": False,
    }


def build_engineering_question_orchestrator(
    *,
    question: str,
    final_gate_report_path: Path,
    runner_report_path: Path,
    output_dir: Path,
    match_mode: str = "contains",
    allow_manual_review_ready_only: bool = True,
) -> Dict[str, Any]:
    final_gate_payload = _read_json(final_gate_report_path)
    runner_payload = _read_json(runner_report_path)

    final_gate_records = final_gate_payload.get("records") or []
    runner_records = runner_payload.get("records") or []

    best_final_gate = _find_best_final_gate_record(final_gate_records, question, match_mode)
    runner_record = _find_runner_record(runner_records, best_final_gate) if best_final_gate else None

    record = build_question_record(
        question=question,
        final_gate_record=best_final_gate,
        runner_record=runner_record,
        allow_manual_review_ready_only=allow_manual_review_ready_only,
    )
    records = [record]

    summary = {
        "source_final_gate_quality_status": final_gate_payload.get("quality_status"),
        "source_runner_quality_status": runner_payload.get("quality_status"),
        "question_count": 1,
        "matched_question_count": sum(1 for r in records if r.get("question_match_status") == "matched_final_gate_record"),
        "manual_review_ready_response_count": sum(1 for r in records if r.get("response_available_for_manual_review")),
        "final_gate_blocked_response_count": sum(1 for r in records if r.get("controlled_response_status") == "final_gate_blocked"),
        "response_text_char_count": sum(r.get("response_text_char_count", 0) for r in records),
        "human_review_required_count": sum(1 for r in records if r.get("human_review_required")),
        "ready_for_final_answer_count": sum(1 for r in records if r.get("ready_for_final_answer")),
        "answer_permission_count": sum(1 for r in records if r.get("answer_permission")),
        "can_answer_directly_count": sum(1 for r in records if r.get("can_answer_directly")),
        "can_prove_claims_count": sum(1 for r in records if r.get("can_prove_claims")),
        "llm_call_allowed_count": sum(1 for r in records if r.get("llm_call_allowed")),
        "retrieval_execution_allowed_count": sum(1 for r in records if r.get("retrieval_execution_allowed")),
        "source_truth_mutation_allowed_count": sum(1 for r in records if r.get("source_truth_mutation_allowed")),
        "postgres_write_attempt_count": sum(1 for r in records if r.get("postgres_write_attempt")),
        "qdrant_write_attempt_count": sum(1 for r in records if r.get("qdrant_write_attempt")),
        "opensearch_write_attempt_count": sum(1 for r in records if r.get("opensearch_write_attempt")),
        "unsafe_record_count": sum(1 for r in records if r.get("unsafe")),
    }

    quality_status = "PASS"
    if final_gate_payload.get("quality_status") != "PASS":
        quality_status = "FAIL"
    if runner_payload.get("quality_status") != "PASS":
        quality_status = "FAIL"
    if summary["answer_permission_count"] != 0:
        quality_status = "FAIL"
    if summary["ready_for_final_answer_count"] != 0:
        quality_status = "FAIL"
    if summary["unsafe_record_count"] != 0:
        quality_status = "FAIL"

    payload: Dict[str, Any] = {
        "module": MODULE_VERSION,
        "status": "ENGINEERING_QUESTION_ORCHESTRATOR_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "question": question,
        "source_final_gate_report_path": str(final_gate_report_path),
        "source_runner_report_path": str(runner_report_path),
        "orchestrator_config": {
            "match_mode": match_mode,
            "allow_manual_review_ready_only": allow_manual_review_ready_only,
            "retrieval_execution_allowed": False,
            "llm_call_allowed": False,
        },
        "records": records,
        "safety_contract": {
            "artifact_authority": "controlled_question_lookup_over_existing_gated_drafts",
            "answers_user_question": False,
            "manual_review_required": True,
            "llm_call_allowed": False,
            "retrieval_execution_allowed": False,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "ready_for_final_answer": False,
            "postgres_write_allowed": False,
            "qdrant_write_allowed": False,
            "opensearch_write_allowed": False,
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / REPORT_NAME, payload)
    _write_jsonl(output_dir / "trace_net_engineering_question_orchestrator_v1_records.jsonl", records)
    _write_json(output_dir / "trace_net_engineering_question_orchestrator_v1_summary.json", summary)
    _write_json(output_dir / "trace_net_engineering_question_orchestrator_v1_quality.json", {"quality_status": quality_status, "summary": summary})
    _write_markdown(output_dir / "trace_net_engineering_question_orchestrator_v1.md", payload)
    return payload


def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    summary = payload.get("summary") or {}
    lines = [
        "# TRACE-Net Engineering Question Orchestrator v1",
        "",
        f"Quality status: **{payload.get('quality_status')}**",
        "",
        "## Summary",
        "",
        f"- Matched questions: {summary.get('matched_question_count')}",
        f"- Manual-review-ready responses: {summary.get('manual_review_ready_response_count')}",
        f"- Final-gate-blocked responses: {summary.get('final_gate_blocked_response_count')}",
        f"- Ready for final answer: {summary.get('ready_for_final_answer_count')}",
        f"- Answer permission: {summary.get('answer_permission_count')}",
        "",
        "## Records",
        "",
    ]
    for record in payload.get("records") or []:
        lines.extend([
            f"### Question",
            "",
            f"- Question: `{record.get('question')}`",
            f"- Status: `{record.get('controlled_response_status')}`",
            f"- Matched source question: `{record.get('matched_user_question')}`",
            f"- Final gate status: `{record.get('final_gate_status')}`",
            f"- Response chars: `{record.get('response_text_char_count')}`",
            f"- Human review required: `{record.get('human_review_required')}`",
            f"- Ready for final answer: `{record.get('ready_for_final_answer')}`",
            f"- Answer permission: `{record.get('answer_permission')}`",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def check_engineering_question_orchestrator_quality(
    *,
    report_path: Path,
    require_source_final_gate_quality_pass: bool = False,
    require_source_runner_quality_pass: bool = False,
    min_matched_questions: int = 1,
    min_manual_review_ready_responses: int = 0,
    min_response_chars: int = 0,
    max_ready_for_final_answer: int = 0,
    max_unsafe: int = 0,
    require_no_answer_permission: bool = False,
    require_no_llm_calls: bool = False,
    require_no_retrieval_execution: bool = False,
    require_no_source_truth_mutation: bool = False,
) -> Dict[str, Any]:
    payload = _read_json(report_path)
    summary = payload.get("summary") or {}
    failures: List[str] = []

    def fail_if(condition: bool, msg: str) -> None:
        if condition:
            failures.append(msg)

    if require_source_final_gate_quality_pass:
        fail_if(summary.get("source_final_gate_quality_status") != "PASS", "source final gate quality is not PASS")
    if require_source_runner_quality_pass:
        fail_if(summary.get("source_runner_quality_status") != "PASS", "source runner quality is not PASS")
    fail_if(summary.get("matched_question_count", 0) < min_matched_questions, "not enough matched questions")
    fail_if(summary.get("manual_review_ready_response_count", 0) < min_manual_review_ready_responses, "not enough manual-review-ready responses")
    fail_if(summary.get("response_text_char_count", 0) < min_response_chars, "not enough response text chars")
    fail_if(summary.get("ready_for_final_answer_count", 0) > max_ready_for_final_answer, "too many final-answer-ready records")
    fail_if(summary.get("unsafe_record_count", 0) > max_unsafe, "unsafe record count exceeded")
    if require_no_answer_permission:
        fail_if(summary.get("answer_permission_count", 0) != 0, "answer permission count not zero")
        fail_if(summary.get("can_answer_directly_count", 0) != 0, "can answer directly count not zero")
        fail_if(summary.get("can_prove_claims_count", 0) != 0, "can prove claims count not zero")
    if require_no_llm_calls:
        fail_if(summary.get("llm_call_allowed_count", 0) != 0, "LLM call allowed count not zero")
    if require_no_retrieval_execution:
        fail_if(summary.get("retrieval_execution_allowed_count", 0) != 0, "retrieval execution allowed count not zero")
    if require_no_source_truth_mutation:
        fail_if(summary.get("source_truth_mutation_allowed_count", 0) != 0, "source truth mutation allowed count not zero")

    quality_status = "FAIL" if failures else "PASS"
    return {
        "quality_status": quality_status,
        "summary": summary,
        "failures": failures,
        "checked_report_path": str(report_path),
    }


def main_build(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run TRACE-Net engineering question orchestrator v1 over existing gated draft artifacts.")
    parser.add_argument("--question", required=True)
    parser.add_argument("--final-gate", required=True)
    parser.add_argument("--runner-report", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--match-mode", choices=["exact", "contains", "fuzzy"], default="contains")
    parser.add_argument("--allow-non-manual-review-drafts", action="store_true")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    payload = build_engineering_question_orchestrator(
        question=args.question,
        final_gate_report_path=Path(args.final_gate),
        runner_report_path=Path(args.runner_report),
        output_dir=Path(args.output_dir),
        match_mode=args.match_mode,
        allow_manual_review_ready_only=not args.allow_non_manual_review_drafts,
    )
    print("Status:", payload["status"])
    print("Quality status:", payload["quality_status"])
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    if payload.get("records"):
        record = payload["records"][0]
        print("Controlled response status:", record.get("controlled_response_status"))
        print("Response chars:", record.get("response_text_char_count"))
        print("Answer permission:", record.get("answer_permission"))
    return 0 if payload["quality_status"] == "PASS" else 1


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net engineering question orchestrator v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--require-source-final-gate-quality-pass", action="store_true")
    parser.add_argument("--require-source-runner-quality-pass", action="store_true")
    parser.add_argument("--min-matched-questions", type=int, default=1)
    parser.add_argument("--min-manual-review-ready-responses", type=int, default=0)
    parser.add_argument("--min-response-chars", type=int, default=0)
    parser.add_argument("--max-ready-for-final-answer", type=int, default=0)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-llm-calls", action="store_true")
    parser.add_argument("--require-no-retrieval-execution", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    args = parser.parse_args(argv)

    result = check_engineering_question_orchestrator_quality(
        report_path=Path(args.report_path),
        require_source_final_gate_quality_pass=args.require_source_final_gate_quality_pass,
        require_source_runner_quality_pass=args.require_source_runner_quality_pass,
        min_matched_questions=args.min_matched_questions,
        min_manual_review_ready_responses=args.min_manual_review_ready_responses,
        min_response_chars=args.min_response_chars,
        max_ready_for_final_answer=args.max_ready_for_final_answer,
        max_unsafe=args.max_unsafe,
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_llm_calls=args.require_no_llm_calls,
        require_no_retrieval_execution=args.require_no_retrieval_execution,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
    )
    print("Quality status:", result["quality_status"])
    print("Summary:", json.dumps(result["summary"], sort_keys=True))
    if result["failures"]:
        print("Failures:", json.dumps(result["failures"], indent=2))
    if args.write_json:
        out = Path(args.report_path).with_name("trace_net_engineering_question_orchestrator_v1_quality_check.json")
        _write_json(out, result)
        print("Wrote:", out)
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main_build())
