
"""TRACE-Net Engineering Draft Final Gate v1.

Evaluates Gemma draft-runner outputs before any response is allowed out.

v1.1:
- adds negation-aware risky phrase scanning
- blocks "approved replacement" when asserted
- does NOT block safe boundary language such as
  "this does not claim approved replacement"
- records raw, blocked, and negated risky phrase hits separately

This gate is intentionally conservative:
- a model response is not enough
- the draft must be non-empty and long enough
- risky/forbidden claims are blocked only when asserted
- final answer permission remains false in v1
- source trace/citation markers are checked but do not grant proof by themselves

Safety:
- no LLM calls
- no retrieval execution
- no DB/search/vector writes
- no source-truth mutation
- no final answer permission
- no direct answer permission
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


MODULE_VERSION = "trace_net_engineering_draft_final_gate_v1"
REPORT_NAME = "trace_net_engineering_draft_final_gate_v1.json"

RISKY_PHRASES = [
    "approved replacement",
    "guaranteed fit",
    "safe to install",
    "engineering approval",
    "drop-in replacement",
    "airworthy",
    "certified",
    "interchangeable",
    "will fit",
    "safe modification",
    "approved modification",
]

EXPECTED_SECTION_MARKERS = [
    "source-backed",
    "candidate",
    "missing",
    "source trace",
]

NEGATION_PATTERNS = [
    "does not claim",
    "do not claim",
    "doesn't claim",
    "does not state",
    "does not establish",
    "does not prove",
    "not claim",
    "no claim",
    "no evidence",
    "not proven",
    "is not proven",
    "are not proven",
    "not approved",
    "is not approved",
    "are not approved",
    "not guaranteed",
    "is not guaranteed",
    "not safe",
    "not certified",
    "not implied",
    "is implied by this information",
    "no engineering approval",
    "no claims regarding",
    "no claim regarding",
    "not an approved",
    "not a guaranteed",
    "cannot claim",
    "cannot be treated as",
    "should not be treated as",
    "must not be treated as",
]


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


def _normalize_path(path_text: str) -> Path:
    return Path(str(path_text).replace("\\", "/"))


def _read_draft_response(record: Mapping[str, Any]) -> Dict[str, Any]:
    path_text = record.get("draft_response_path")
    if not path_text:
        return {
            "draft_response_missing": True,
            "draft_text": "",
            "raw_response": {},
            "error": "missing draft_response_path",
        }
    path = _normalize_path(str(path_text))
    if not path.exists():
        return {
            "draft_response_missing": True,
            "draft_text": "",
            "raw_response": {},
            "error": f"draft response file not found: {path}",
        }
    payload = _read_json(path)
    return {
        "draft_response_missing": False,
        "draft_response_path": str(path),
        "draft_text": str(payload.get("draft_text") or ""),
        "raw_response": payload.get("raw_response") or {},
        "error": payload.get("error"),
        "draft_safety_scan": payload.get("draft_safety_scan") or {},
    }


def _sentence_window(text: str, start: int, end: int, *, radius: int = 140) -> str:
    left_boundary = max(text.rfind(".", 0, start), text.rfind("\n", 0, start), text.rfind(";", 0, start))
    if left_boundary < 0:
        left_boundary = max(0, start - radius)
    else:
        left_boundary += 1
    right_candidates = [idx for idx in [text.find(".", end), text.find("\n", end), text.find(";", end)] if idx != -1]
    right_boundary = min(right_candidates) if right_candidates else min(len(text), end + radius)
    return text[left_boundary:right_boundary].strip()


def _has_negation_context(text: str, match_start: int, match_end: int) -> bool:
    """Return True when a risky phrase is being explicitly denied, not asserted."""
    lowered = text.lower()
    before = lowered[max(0, match_start - 120):match_start]
    after = lowered[match_end:min(len(lowered), match_end + 80)]
    sentence = _sentence_window(lowered, match_start, match_end, radius=180)

    # Strong local negation before the phrase.
    for pattern in NEGATION_PATTERNS:
        if pattern in before or pattern in sentence:
            return True

    # Common "no X or Y is implied" shape where the negation appears before/after.
    if "no " in before and ("implied" in after or "implied" in sentence):
        return True

    # "not claim that any part is an approved replacement or guaranteed fit"
    if ("not claim" in before or "does not claim" in before or "no claim" in before) and len(before) < 120:
        return True

    # "there are no claims regarding unverified..." style.
    if "there are no claims" in sentence or "there is no claim" in sentence:
        return True

    return False


def _risky_hit_records(text: str, forbidden_claims: Sequence[str]) -> Dict[str, Any]:
    lowered = text.lower()
    phrases = list(RISKY_PHRASES)
    for claim in forbidden_claims:
        claim_text = str(claim).strip().lower()
        if claim_text and claim_text not in phrases:
            phrases.append(claim_text)

    raw_hits: List[Dict[str, Any]] = []
    blocked_hits: List[Dict[str, Any]] = []
    negated_hits: List[Dict[str, Any]] = []

    for phrase in phrases:
        if not phrase:
            continue
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        for match in pattern.finditer(text):
            hit = {
                "phrase": phrase,
                "start": match.start(),
                "end": match.end(),
                "context": _sentence_window(text, match.start(), match.end()),
            }
            raw_hits.append(hit)
            if _has_negation_context(text, match.start(), match.end()):
                negated_hits.append(hit)
            else:
                blocked_hits.append(hit)

    # Dedupe by phrase/context, preserving useful metadata.
    def dedupe(items: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        out: List[Dict[str, Any]] = []
        for item in items:
            key = (item.get("phrase"), item.get("context"))
            if key in seen:
                continue
            seen.add(key)
            out.append(dict(item))
        return out

    raw = dedupe(raw_hits)
    blocked = dedupe(blocked_hits)
    negated = dedupe(negated_hits)
    return {
        "raw_risky_phrase_hits": raw,
        "blocked_risky_phrase_hits": blocked,
        "negated_risky_phrase_hits": negated,
        "raw_risky_phrase_hit_count": len(raw),
        "blocked_risky_phrase_hit_count": len(blocked),
        "negated_risky_phrase_hit_count": len(negated),
        # Backward-compatible fields now mean blocked/asserted hits only.
        "risky_phrase_hits": [item["phrase"] for item in blocked],
        "risky_phrase_hit_count": len(blocked),
    }


def _citation_marker_count(text: str) -> int:
    lowered = text.lower()
    patterns = [
        r"\bpage_id\b",
        r"\bsource trace\b",
        r"\bcitation\b",
        r"\bp\d{3,}\b",
        r"\bp0{2,}\d+\b",
        r"\bt_p_\d+",
        r"\bmetadata_page_\d+",
        r"\bsource_p\d+",
    ]
    return sum(len(re.findall(pattern, lowered)) for pattern in patterns)


def _section_marker_count(text: str) -> int:
    lowered = text.lower()
    return sum(1 for marker in EXPECTED_SECTION_MARKERS if marker in lowered)


def _forbidden_claims_from_adapter_like(record: Mapping[str, Any]) -> List[str]:
    values = record.get("forbidden_claims") or []
    return [str(v) for v in values] if isinstance(values, list) else []


def evaluate_runner_record(
    *,
    runner_record: Mapping[str, Any],
    index: int,
    min_draft_chars: int,
    require_citation_markers: bool,
    min_section_markers: int,
) -> Dict[str, Any]:
    response = _read_draft_response(runner_record)
    draft_text = response.get("draft_text") or ""
    text_len = len(draft_text.strip())
    forbidden_claims = _forbidden_claims_from_adapter_like(runner_record)
    risky_scan = _risky_hit_records(draft_text, forbidden_claims)
    citation_count = _citation_marker_count(draft_text)
    section_count = _section_marker_count(draft_text)

    blocking_reasons: List[str] = []
    warnings: List[str] = []

    if response.get("draft_response_missing"):
        blocking_reasons.append("draft_response_missing")
    if runner_record.get("request_error"):
        blocking_reasons.append("request_error")
    if not runner_record.get("response_received"):
        blocking_reasons.append("no_model_response")
    if text_len == 0:
        blocking_reasons.append("empty_draft")
    elif text_len < min_draft_chars:
        blocking_reasons.append("draft_too_short")
    if risky_scan["blocked_risky_phrase_hit_count"]:
        blocking_reasons.append("risky_or_forbidden_claim_phrase_detected")
    if require_citation_markers and citation_count <= 0:
        blocking_reasons.append("missing_source_trace_or_citation_marker")
    if section_count < min_section_markers:
        warnings.append("missing_expected_section_markers")
    if risky_scan["negated_risky_phrase_hit_count"]:
        warnings.append("negated_risky_boundary_language_detected")
    if not runner_record.get("ready_for_final_gate_review"):
        warnings.append("runner_not_ready_for_final_gate_review")

    final_gate_status = "FINAL_GATE_BLOCKED" if blocking_reasons else "FINAL_GATE_DRAFT_ACCEPTED_FOR_MANUAL_REVIEW"
    human_review_required = True

    return {
        "final_gate_record_version": MODULE_VERSION,
        "final_gate_record_id": f"engineering_draft_final_gate_{index+1:04d}",
        "source_runner_record_id": runner_record.get("runner_record_id"),
        "source_adapter_record_id": runner_record.get("source_adapter_record_id"),
        "source_draft_packet_id": runner_record.get("source_draft_packet_id"),
        "question_id": runner_record.get("question_id"),
        "user_question": runner_record.get("user_question"),
        "intent_family": runner_record.get("intent_family"),
        "selected_playbook_id": runner_record.get("selected_playbook_id"),
        "model_id": runner_record.get("model_id"),
        "provider": runner_record.get("provider"),
        "draft_response_path": response.get("draft_response_path") or runner_record.get("draft_response_path"),
        "draft_text_char_count": text_len,
        "min_draft_chars": min_draft_chars,
        "citation_marker_count": citation_count,
        "section_marker_count": section_count,
        **risky_scan,
        "blocking_reasons": sorted(set(blocking_reasons)),
        "warning_reasons": sorted(set(warnings)),
        "final_gate_status": final_gate_status,
        "human_review_required": human_review_required,
        "draft_preview": draft_text[:1500],
        "ready_for_manual_review": final_gate_status == "FINAL_GATE_DRAFT_ACCEPTED_FOR_MANUAL_REVIEW",
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


def build_engineering_draft_final_gate(
    *,
    runner_report_path: Path,
    output_dir: Path,
    min_draft_chars: int = 300,
    require_citation_markers: bool = False,
    min_section_markers: int = 1,
) -> Dict[str, Any]:
    runner_payload = _read_json(runner_report_path)
    runner_records = runner_payload.get("records") or []

    records = [
        evaluate_runner_record(
            runner_record=record,
            index=index,
            min_draft_chars=min_draft_chars,
            require_citation_markers=require_citation_markers,
            min_section_markers=min_section_markers,
        )
        for index, record in enumerate(runner_records)
        if isinstance(record, dict)
    ]

    status_counts = Counter(record.get("final_gate_status") for record in records)
    block_counts = Counter(reason for record in records for reason in record.get("blocking_reasons", []))
    warning_counts = Counter(reason for record in records for reason in record.get("warning_reasons", []))
    intent_counts = Counter(record.get("intent_family") for record in records)

    summary = {
        "source_runner_quality_status": runner_payload.get("quality_status"),
        "source_runner_record_count": len(runner_records),
        "final_gate_record_count": len(records),
        "final_gate_status_counts": dict(sorted(status_counts.items())),
        "blocking_reason_counts": dict(sorted(block_counts.items())),
        "warning_reason_counts": dict(sorted(warning_counts.items())),
        "intent_family_counts": dict(sorted(intent_counts.items())),
        "blocked_record_count": sum(1 for r in records if r.get("final_gate_status") == "FINAL_GATE_BLOCKED"),
        "manual_review_ready_count": sum(1 for r in records if r.get("ready_for_manual_review")),
        "human_review_required_count": sum(1 for r in records if r.get("human_review_required")),
        "raw_risky_phrase_hit_count": sum(r.get("raw_risky_phrase_hit_count", 0) for r in records),
        "blocked_risky_phrase_hit_count": sum(r.get("blocked_risky_phrase_hit_count", 0) for r in records),
        "negated_risky_phrase_hit_count": sum(r.get("negated_risky_phrase_hit_count", 0) for r in records),
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
    if runner_payload.get("quality_status") != "PASS":
        quality_status = "FAIL"
    if not records:
        quality_status = "FAIL"
    if summary["ready_for_final_answer_count"] != 0:
        quality_status = "FAIL"
    if summary["answer_permission_count"] != 0:
        quality_status = "FAIL"
    if summary["unsafe_record_count"] != 0:
        quality_status = "FAIL"

    payload: Dict[str, Any] = {
        "module": MODULE_VERSION,
        "status": "ENGINEERING_DRAFT_FINAL_GATE_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "source_runner_report_path": str(runner_report_path),
        "gate_config": {
            "min_draft_chars": min_draft_chars,
            "require_citation_markers": require_citation_markers,
            "min_section_markers": min_section_markers,
            "negation_aware_risky_phrase_scan": True,
        },
        "records": records,
        "safety_contract": {
            "artifact_authority": "draft_final_gate_only",
            "answers_user_question": False,
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
    _write_jsonl(output_dir / "trace_net_engineering_draft_final_gate_v1_records.jsonl", records)
    _write_json(output_dir / "trace_net_engineering_draft_final_gate_v1_summary.json", summary)
    _write_json(output_dir / "trace_net_engineering_draft_final_gate_v1_quality.json", {"quality_status": quality_status, "summary": summary})
    _write_markdown(output_dir / "trace_net_engineering_draft_final_gate_v1.md", payload)
    return payload


def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    summary = payload.get("summary") or {}
    config = payload.get("gate_config") or {}
    lines = [
        "# TRACE-Net Engineering Draft Final Gate v1.1",
        "",
        f"Quality status: **{payload.get('quality_status')}**",
        "",
        "## Gate config",
        "",
        f"- Min draft chars: `{config.get('min_draft_chars')}`",
        f"- Require citation markers: `{config.get('require_citation_markers')}`",
        f"- Min section markers: `{config.get('min_section_markers')}`",
        f"- Negation-aware risky phrase scan: `{config.get('negation_aware_risky_phrase_scan')}`",
        "",
        "## Summary",
        "",
        f"- Final gate records: {summary.get('final_gate_record_count')}",
        f"- Blocked records: {summary.get('blocked_record_count')}",
        f"- Manual review ready: {summary.get('manual_review_ready_count')}",
        f"- Ready for final answer: {summary.get('ready_for_final_answer_count')}",
        f"- Raw risky phrase hits: {summary.get('raw_risky_phrase_hit_count')}",
        f"- Blocked risky phrase hits: {summary.get('blocked_risky_phrase_hit_count')}",
        f"- Negated risky phrase hits: {summary.get('negated_risky_phrase_hit_count')}",
        f"- Blocking reasons: `{summary.get('blocking_reason_counts')}`",
        "",
        "## Records",
        "",
    ]
    for record in payload.get("records") or []:
        lines.extend([
            f"### {record.get('final_gate_record_id')} — {record.get('final_gate_status')}",
            "",
            f"- Question: `{record.get('user_question')}`",
            f"- Model: `{record.get('model_id')}`",
            f"- Draft chars: `{record.get('draft_text_char_count')}`",
            f"- Blocking reasons: `{record.get('blocking_reasons')}`",
            f"- Warning reasons: `{record.get('warning_reasons')}`",
            f"- Blocked risky phrase hits: `{record.get('blocked_risky_phrase_hit_count')}`",
            f"- Negated risky phrase hits: `{record.get('negated_risky_phrase_hit_count')}`",
            f"- Ready for final answer: `{record.get('ready_for_final_answer')}`",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def check_engineering_draft_final_gate_quality(
    *,
    report_path: Path,
    require_source_runner_quality_pass: bool = False,
    min_final_gate_records: int = 1,
    min_blocked_records: int = 0,
    min_manual_review_ready: int = 0,
    max_blocked_risky_phrase_hits: Optional[int] = None,
    min_negated_risky_phrase_hits: int = 0,
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

    if require_source_runner_quality_pass:
        fail_if(summary.get("source_runner_quality_status") != "PASS", "source runner quality is not PASS")
    fail_if(summary.get("final_gate_record_count", 0) < min_final_gate_records, "not enough final gate records")
    fail_if(summary.get("blocked_record_count", 0) < min_blocked_records, "not enough blocked records")
    fail_if(summary.get("manual_review_ready_count", 0) < min_manual_review_ready, "not enough manual-review-ready records")
    if max_blocked_risky_phrase_hits is not None:
        fail_if(summary.get("blocked_risky_phrase_hit_count", 0) > max_blocked_risky_phrase_hits, "too many blocked risky phrase hits")
    fail_if(summary.get("negated_risky_phrase_hit_count", 0) < min_negated_risky_phrase_hits, "not enough negated risky phrase hits")
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
    parser = argparse.ArgumentParser(description="Build TRACE-Net engineering draft final gate v1.")
    parser.add_argument("--runner-report", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--min-draft-chars", type=int, default=300)
    parser.add_argument("--require-citation-markers", action="store_true")
    parser.add_argument("--min-section-markers", type=int, default=1)
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)

    payload = build_engineering_draft_final_gate(
        runner_report_path=Path(args.runner_report),
        output_dir=Path(args.output_dir),
        min_draft_chars=args.min_draft_chars,
        require_citation_markers=args.require_citation_markers,
        min_section_markers=args.min_section_markers,
    )
    print("Status:", payload["status"])
    print("Quality status:", payload["quality_status"])
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["quality_status"] == "PASS" else 1


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net engineering draft final gate v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--require-source-runner-quality-pass", action="store_true")
    parser.add_argument("--min-final-gate-records", type=int, default=1)
    parser.add_argument("--min-blocked-records", type=int, default=0)
    parser.add_argument("--min-manual-review-ready", type=int, default=0)
    parser.add_argument("--max-blocked-risky-phrase-hits", type=int)
    parser.add_argument("--min-negated-risky-phrase-hits", type=int, default=0)
    parser.add_argument("--max-ready-for-final-answer", type=int, default=0)
    parser.add_argument("--max-unsafe", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-llm-calls", action="store_true")
    parser.add_argument("--require-no-retrieval-execution", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    args = parser.parse_args(argv)

    result = check_engineering_draft_final_gate_quality(
        report_path=Path(args.report_path),
        require_source_runner_quality_pass=args.require_source_runner_quality_pass,
        min_final_gate_records=args.min_final_gate_records,
        min_blocked_records=args.min_blocked_records,
        min_manual_review_ready=args.min_manual_review_ready,
        max_blocked_risky_phrase_hits=args.max_blocked_risky_phrase_hits,
        min_negated_risky_phrase_hits=args.min_negated_risky_phrase_hits,
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
        out = Path(args.report_path).with_name("trace_net_engineering_draft_final_gate_v1_quality_check.json")
        _write_json(out, result)
        print("Wrote:", out)
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main_build())
