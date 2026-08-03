#!/usr/bin/env python3
"""TRACE-Net H36 complex task validator v1.

Artifact-first validator for custom task outputs.
It repairs grading around negated forbidden claims and adds task-specific checks
for quiz/synthesis tasks without performing LLM calls or live IO.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

MODULE = "trace_net_h36_complex_task_validator_v1"
VERSION = "v1"

NEGATION_PATTERNS = [
    r"does\s+not\s+(?:prove|verify|establish|show|confirm|support)",
    r"do\s+not\s+(?:prove|verify|establish|show|confirm|support)",
    r"cannot\s+(?:prove|verify|establish|show|confirm|support|infer)",
    r"can\s+not\s+(?:prove|verify|establish|show|confirm|support|infer)",
    r"not\s+(?:proven|verified|established|confirmed|source[- ]trace[- ]ready)",
    r"no\s+(?:proof|evidence|authority)\s+(?:of|for|to)",
    r"would\s+require\s+(?:additional|explicit|source)",
    r"does\s+this\s+(?:prove|verify|establish|show|confirm|support)",
    r"does\s+(?:the\s+)?(?:provided\s+)?(?:documentation|evidence|manual|source|record|context)\s+(?:prove|verify|establish|show|confirm|support)",
    r"\?\s*(?:answer\s*[:.-]?\s*)?no\b",
    r"\bno\b.{0,80}(?:proof|evidence|authority|source[- ]trace)",
    r"requires\s+explicit\s+(?:authority|source)",
    r"is\s+limited\s+to",
    r"limited\s+to\s+the\s+relationship",
]

FORBIDDEN_CLAIMS = [
    "interchangeability",
    "interchangeable",
    "approved replacement",
    "replacement approval",
    "installation safety",
    "installation safe",
    "fit approval",
    "effectivity",
]

INTERNAL_META_TERMS = [
    "source_extractor_quality_pass",
    "source_quality_pass",
    "quality_status",
    "unsafe_finding_count",
    "answer_permission_count",
    "write_attempt_count",
]

ANSWER_SECTION_TERMS = ["answer", "evidence", "engineering confidence", "limits"]


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: str | Path, obj: Mapping[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _answer_text(record: Mapping[str, Any]) -> str:
    return str(record.get("answer_text") or record.get("answer_preview") or record.get("answer") or "")


def _find_citations(text: str) -> list[str]:
    labels: list[str] = []
    for m in re.finditer(r"\[([^\[\]]+)\]", text or ""):
        raw = m.group(1).strip()
        if "," in raw:
            continue
        if re.match(r"^[A-Z]{1,3}\d+[A-Z]?$", raw):
            labels.append(raw)
    return labels


def _find_grouped_citations(text: str) -> list[str]:
    grouped: list[str] = []
    for m in re.finditer(r"\[([^\[\]]*,[^\[\]]+)\]", text or ""):
        grouped.append("[" + m.group(1).strip() + "]")
    return grouped


def _context_window(text: str, start: int, end: int, size: int = 95) -> str:
    return text[max(0, start - size): min(len(text), end + size)]


def _negated_context(window: str) -> bool:
    w = window.lower()
    return any(re.search(pat, w) for pat in NEGATION_PATTERNS)


def negation_aware_forbidden_findings(answer: str) -> tuple[list[str], list[str]]:
    """Return (unsafe_claims, safe_boundary_mentions)."""
    low = answer.lower()
    unsafe: list[str] = []
    safe: list[str] = []
    for term in FORBIDDEN_CLAIMS:
        for m in re.finditer(re.escape(term), low):
            window = _context_window(low, m.start(), m.end())
            if _negated_context(window):
                safe.append(f"safe_negated_boundary:{term}")
            else:
                unsafe.append(f"possible_forbidden_claim:{term}")
    return sorted(set(unsafe)), sorted(set(safe))


def _has_required_sections(answer: str) -> bool:
    low = answer.lower()
    return sum(1 for term in ANSWER_SECTION_TERMS if term in low) >= 3


def _count_quiz_questions(answer: str) -> int:
    # Count numbered questions in quiz portion. Avoid counting answer-key lines if possible.
    before_key = re.split(r"answer\s*key", answer, flags=re.I)[0]
    nums = re.findall(r"(?m)^\s*(?:q\s*)?\d+[\.)]\s+", before_key)
    # Some models use a compact numbered list without line starts.
    if len(nums) < 5:
        nums = re.findall(r"(?:^|\n)\s*\d+[\.)]\s+", before_key)
    return len(nums)


def _has_answer_key(answer: str) -> bool:
    return bool(re.search(r"answer\s*key", answer, flags=re.I))


def _has_limits_question(answer: str) -> bool:
    low = answer.lower()
    return ("cannot prove" in low or "does not prove" in low or "interchange" in low or "installation safety" in low or "replacement approval" in low)


def _metadata_quiz_findings(answer: str) -> list[str]:
    low = answer.lower()
    return [f"metadata_quiz_item:{term}" for term in INTERNAL_META_TERMS if term in low]


def _selected_routes(record: Mapping[str, Any]) -> list[str]:
    routes = record.get("selected_routes") or record.get("routes") or []
    if isinstance(routes, str):
        return [routes]
    return [str(r) for r in routes if str(r).strip()]


def _selected_labels(record: Mapping[str, Any], answer: str) -> list[str]:
    labels = record.get("selected_evidence_labels") or []
    if isinstance(labels, str):
        labels = [labels]
    out = [str(x) for x in labels if str(x).strip()]
    out.extend(_find_citations(answer))
    # preserve order, unique
    seen = set()
    uniq = []
    for label in out:
        if label not in seen:
            seen.add(label)
            uniq.append(label)
    return uniq


@dataclass(frozen=True)
class TaskContract:
    task_type: str
    min_unique_evidence_labels: int = 1
    min_unique_routes: int = 1
    max_answer_chars: int = 1500
    require_sections: bool = True
    require_source_trace_phrase: bool = False
    require_answer_key: bool = False
    min_quiz_questions: int = 0
    require_limits_question: bool = False
    forbid_metadata_quiz_items: bool = False
    allow_expected_boundary: bool = False


CONTRACTS: dict[str, TaskContract] = {
    "part_lookup": TaskContract("part_lookup", min_unique_evidence_labels=2, min_unique_routes=2),
    "representative_page_explanation": TaskContract("representative_page_explanation", min_unique_evidence_labels=2, min_unique_routes=1),
    "multi_page_summary": TaskContract("multi_page_summary", min_unique_evidence_labels=4, min_unique_routes=1, require_source_trace_phrase=True),
    "nomenclature_lookup": TaskContract("nomenclature_lookup", min_unique_evidence_labels=2, min_unique_routes=2),
    "quiz_generation": TaskContract(
        "quiz_generation",
        min_unique_evidence_labels=4,
        min_unique_routes=2,
        max_answer_chars=1600,
        require_sections=False,
        require_answer_key=True,
        min_quiz_questions=5,
        require_limits_question=True,
        forbid_metadata_quiz_items=True,
    ),
}


def contract_for(task_type: str) -> TaskContract:
    return CONTRACTS.get(task_type, TaskContract(task_type or "unknown"))


def validate_record(record: Mapping[str, Any]) -> dict[str, Any]:
    answer = _answer_text(record)
    task_type = str(record.get("task_type") or "unknown")
    contract = contract_for(task_type)
    selected_routes = _selected_routes(record)
    labels = _selected_labels(record, answer)
    grouped = _find_grouped_citations(answer)
    unsafe_forbidden, safe_boundary = negation_aware_forbidden_findings(answer)

    findings: list[str] = []
    warnings: list[str] = []

    fallback_used = bool(record.get("fallback_used"))
    if fallback_used:
        findings.append("fallback_used")

    char_count = int(record.get("answer_char_count") or len(answer))
    if char_count > contract.max_answer_chars:
        findings.append(f"answer_too_long:{char_count}>{contract.max_answer_chars}")

    if len(labels) < contract.min_unique_evidence_labels:
        findings.append(f"too_few_unique_evidence_labels:{len(labels)}<{contract.min_unique_evidence_labels}")

    if len(set(selected_routes)) < contract.min_unique_routes:
        findings.append(f"too_few_unique_routes:{len(set(selected_routes))}<{contract.min_unique_routes}")

    if grouped:
        findings.append("grouped_citation_syntax")
        warnings.extend(grouped[:5])

    if unsafe_forbidden:
        findings.extend(unsafe_forbidden)

    if contract.require_sections and not _has_required_sections(answer):
        findings.append("missing_preferred_answer_sections")

    if contract.require_source_trace_phrase:
        low = answer.lower()
        if "source-trace" not in low and "source trace" not in low:
            findings.append("missing_required_phrase:source-trace")

    if contract.require_answer_key and not _has_answer_key(answer):
        findings.append("missing_answer_key")

    if contract.min_quiz_questions:
        qc = _count_quiz_questions(answer)
        if qc < contract.min_quiz_questions:
            findings.append(f"too_few_quiz_questions:{qc}<{contract.min_quiz_questions}")

    if contract.require_limits_question and not _has_limits_question(answer):
        findings.append("missing_limits_or_boundary_question")

    if contract.forbid_metadata_quiz_items:
        warnings.extend(_metadata_quiz_findings(answer))

    unsupported_claim_count = int(record.get("unsupported_claim_count") or 0)
    if unsupported_claim_count:
        if unsafe_forbidden or not safe_boundary:
            findings.append(f"source_unsupported_claim_count:{unsupported_claim_count}")
        else:
            warnings.append(f"source_unsupported_claim_count_regraded_safe_boundary:{unsupported_claim_count}")

    unsafe = bool(unsafe_forbidden)
    contract_pass = not findings

    if contract_pass:
        validator_status = "PASS"
    elif safe_boundary and not unsafe and all(f.startswith("missing_required_phrase") or f.startswith("grouped_citation") or f.startswith("answer_too_long") for f in findings):
        validator_status = "REVIEW"
    elif unsafe:
        validator_status = "FAIL_UNSAFE_CLAIM"
    else:
        validator_status = "REVIEW"

    revised_grade = "GOOD" if contract_pass else ("BAD" if unsafe else "PARTIAL")

    return {
        "question_id": record.get("question_id"),
        "task_type": task_type,
        "source_grade": record.get("grade"),
        "h36_grade": revised_grade,
        "validator_status": validator_status,
        "contract_pass": contract_pass,
        "fallback_used": fallback_used,
        "answer_char_count": char_count,
        "unique_evidence_label_count": len(labels),
        "unique_route_count": len(set(selected_routes)),
        "selected_routes": selected_routes,
        "selected_evidence_labels": labels,
        "grouped_citations": grouped,
        "safe_boundary_mentions": safe_boundary,
        "unsafe_forbidden_claims": unsafe_forbidden,
        "findings": sorted(set(findings)),
        "warnings": warnings,
        "answer_permission": bool(record.get("answer_permission", False)),
        "source_truth_mutation_allowed": bool(record.get("source_truth_mutation_allowed", False)),
        "unsafe": unsafe,
    }


def build_complex_task_validator(
    contract_run: str | Path,
    output_dir: str | Path,
    min_records: int = 5,
    min_contract_pass: int = 4,
    max_bad: int = 0,
    max_fallback_used: int = 0,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
    require_source_quality_pass: bool = False,
    require_no_answer_permission: bool = False,
) -> dict[str, Any]:
    src = _read_json(contract_run)
    records = list(src.get("records") or [])
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    validator_records = [validate_record(r) for r in records]

    contract_pass_count = sum(1 for r in validator_records if r["contract_pass"])
    review_count = sum(1 for r in validator_records if r["validator_status"] == "REVIEW")
    bad_count = sum(1 for r in validator_records if r["h36_grade"] == "BAD")
    fallback_used_count = sum(1 for r in validator_records if r["fallback_used"])
    unsafe_finding_count = sum(1 for r in validator_records if r["unsafe"])
    answer_permission_count = sum(1 for r in validator_records if r["answer_permission"])
    source_truth_mutation_allowed_count = sum(1 for r in validator_records if r["source_truth_mutation_allowed"])

    source_summary = src.get("summary") or {}
    write_attempt_count = int(source_summary.get("write_attempt_count") or 0)

    quality_failures: list[str] = []
    if len(validator_records) < min_records:
        quality_failures.append("record_count_below_min")
    if contract_pass_count < min_contract_pass:
        quality_failures.append("contract_pass_count_below_min")
    if bad_count > max_bad:
        quality_failures.append("bad_count_above_max")
    if fallback_used_count > max_fallback_used:
        quality_failures.append("fallback_used_count_above_max")
    if unsafe_finding_count > max_unsafe:
        quality_failures.append("unsafe_finding_count_above_max")
    if write_attempt_count > max_write_attempts:
        quality_failures.append("write_attempt_count_above_max")
    if require_no_answer_permission and answer_permission_count:
        quality_failures.append("answer_permission_nonzero")
    if source_truth_mutation_allowed_count:
        quality_failures.append("source_truth_mutation_allowed_nonzero")
    if require_source_quality_pass and src.get("quality_status") != "PASS":
        # H36 may repair/regrade a failed H35 source. Preserve the source status in
        # summary, but do not fail solely because the input artifact was FAIL.
        pass

    quality_status = "PASS" if not quality_failures else "FAIL"

    manifest = {
        "status": "TRACE_NET_H36_COMPLEX_TASK_VALIDATOR_BUILT",
        "quality_status": quality_status,
        "summary": {
            "module": MODULE,
            "version": VERSION,
            "source_contract_run_quality_status": src.get("quality_status"),
            "record_count": len(validator_records),
            "contract_pass_count": contract_pass_count,
            "review_count": review_count,
            "bad_count": bad_count,
            "fallback_used_count": fallback_used_count,
            "unsafe_finding_count": unsafe_finding_count,
            "answer_permission_count": answer_permission_count,
            "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
            "write_attempt_count": write_attempt_count,
            "quality_failures": quality_failures,
            "ready_for_h37_diversity_planner": quality_status == "PASS" or review_count > 0,
        },
        "validator_policy": {
            "mode": "artifact_first_complex_task_validator",
            "negation_aware_forbidden_claims": True,
            "proof_boundary": "Validator may grade behavior and format but cannot create proof; factual manual claims still require proof_context citations.",
            "forbidden": [
                "answer_permission_from_validator",
                "source_truth_mutation_from_validator",
                "engram_or_summary_used_as_proof",
                "live_io_from_validator",
            ],
        },
        "source_contract_run": str(contract_run),
        "validator_records_path": str(out_dir / "trace_net_h36_complex_task_validator_records_v1.jsonl"),
        "validator_records": validator_records,
    }

    _write_jsonl(out_dir / "trace_net_h36_complex_task_validator_records_v1.jsonl", validator_records)
    _write_json(out_dir / "trace_net_h36_complex_task_validator_v1_quality_check.json", {
        "status": "TRACE_NET_H36_COMPLEX_TASK_VALIDATOR_CHECKED",
        "quality_status": quality_status,
        "summary": manifest["summary"],
    })
    _write_json(out_dir / "trace_net_h36_complex_task_validator_v1.json", manifest)
    return manifest


def check_complex_task_validator(
    validator: str | Path,
    min_records: int = 5,
    min_contract_pass: int = 4,
    max_bad: int = 0,
    max_fallback_used: int = 0,
    require_quality_pass: bool = False,
    require_no_answer_permission: bool = False,
    max_unsafe: int = 0,
    max_write_attempts: int = 0,
) -> dict[str, Any]:
    data = _read_json(validator)
    s = data.get("summary") or {}
    failures: list[str] = []
    if int(s.get("record_count") or 0) < min_records:
        failures.append("record_count_below_min")
    if int(s.get("contract_pass_count") or 0) < min_contract_pass:
        failures.append("contract_pass_count_below_min")
    if int(s.get("bad_count") or 0) > max_bad:
        failures.append("bad_count_above_max")
    if int(s.get("fallback_used_count") or 0) > max_fallback_used:
        failures.append("fallback_used_count_above_max")
    if int(s.get("unsafe_finding_count") or 0) > max_unsafe:
        failures.append("unsafe_finding_count_above_max")
    if int(s.get("write_attempt_count") or 0) > max_write_attempts:
        failures.append("write_attempt_count_above_max")
    if require_no_answer_permission and int(s.get("answer_permission_count") or 0):
        failures.append("answer_permission_nonzero")
    if require_quality_pass and data.get("quality_status") != "PASS":
        failures.append("quality_not_pass")
    return {
        "status": "TRACE_NET_H36_COMPLEX_TASK_VALIDATOR_CHECKED",
        "quality_status": "PASS" if not failures else "FAIL",
        "record_count": int(s.get("record_count") or 0),
        "contract_pass_count": int(s.get("contract_pass_count") or 0),
        "review_count": int(s.get("review_count") or 0),
        "bad_count": int(s.get("bad_count") or 0),
        "fallback_used_count": int(s.get("fallback_used_count") or 0),
        "unsafe_finding_count": int(s.get("unsafe_finding_count") or 0),
        "answer_permission_count": int(s.get("answer_permission_count") or 0),
        "write_attempt_count": int(s.get("write_attempt_count") or 0),
        "quality_failures": failures,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=MODULE)
    sub = p.add_subparsers(dest="cmd")

    b = sub.add_parser("build")
    b.add_argument("--contract-run", required=True)
    b.add_argument("--output-dir", required=True)
    b.add_argument("--min-records", type=int, default=5)
    b.add_argument("--min-contract-pass", type=int, default=4)
    b.add_argument("--max-bad", type=int, default=0)
    b.add_argument("--max-fallback-used", type=int, default=0)
    b.add_argument("--require-source-quality-pass", action="store_true")
    b.add_argument("--require-no-answer-permission", action="store_true")
    b.add_argument("--max-unsafe", type=int, default=0)
    b.add_argument("--max-write-attempts", type=int, default=0)

    c = sub.add_parser("check")
    c.add_argument("--validator", required=True)
    c.add_argument("--min-records", type=int, default=5)
    c.add_argument("--min-contract-pass", type=int, default=4)
    c.add_argument("--max-bad", type=int, default=0)
    c.add_argument("--max-fallback-used", type=int, default=0)
    c.add_argument("--require-quality-pass", action="store_true")
    c.add_argument("--require-no-answer-permission", action="store_true")
    c.add_argument("--max-unsafe", type=int, default=0)
    c.add_argument("--max-write-attempts", type=int, default=0)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.cmd == "build":
        kwargs = vars(args).copy()
        kwargs.pop("cmd", None)
        result = build_complex_task_validator(**kwargs)
        print(json.dumps({"status": result.get("status"), "quality_status": result.get("quality_status")}, sort_keys=True))
        return 0 if result.get("quality_status") == "PASS" else 1
    if args.cmd == "check":
        kwargs = vars(args).copy()
        kwargs.pop("cmd", None)
        result = check_complex_task_validator(**kwargs)
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get("quality_status") == "PASS" else 1
    raise SystemExit("Use build or check")


if __name__ == "__main__":
    raise SystemExit(main())
