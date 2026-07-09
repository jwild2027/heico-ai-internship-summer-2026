#!/usr/bin/env python3
"""Validate target-specific citations in TRACE-Net fixed-50 answer outputs.

This validator is intentionally read-only. It does not call the TRACE-Net endpoint,
Ollama, Postgres, Qdrant, OpenSearch, or mutate source truth. It reads an
answers.jsonl file produced by the fixed-50 server runners and reports whether
returned citations actually match explicit target part numbers in the question.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

MODULE = "trace_net_fixed50_target_citation_validator_v1"
VERSION = "v1"

NUMERIC_PART_RE = re.compile(r"\b\d{2,4}[-\s]?\d{3,6}[-\s]?\d{2,4}\b")
ALPHA_PART_RE = re.compile(r"\b[A-Z]{1,6}\s*\d{3,}\s*[-\s]?\s*\d{2,}\b", re.IGNORECASE)

SAFE_NO_PROOF_PHRASES = (
    "not source-trace-ready",
    "not source trace ready",
    "not source-traceable",
    "not source traceable",
    "not found",
    "was not found",
    "no source-traceable evidence",
    "no source traceable evidence",
    "cannot prove",
    "can't prove",
    "does not prove",
    "do not prove",
    "insufficient proof",
    "insufficient evidence",
    "missing evidence",
    "no proof_context",
    "proof_context is insufficient",
)

SOURCE_READY_CLAIM_PHRASES = (
    "source-trace status: source-trace-ready",
    "source trace status: source trace ready",
    "source-trace-ready answer",
    "source trace ready answer",
    "source-traceable answer",
)

DANGEROUS_CLAIM_TERMS = (
    "eligible",
    "eligibility",
    "applicability",
    "applicable",
    "approved",
    "approval",
    "replacement",
    "interchangeability",
    "interchangeable",
    "installation",
    "effectivity",
    "fits",
    "fit",
)


def normalize_for_match(value: Any) -> str:
    """Normalize a value for target/citation comparisons."""
    if value is None:
        return ""
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def unique_keep_order(values: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in values:
        if not value:
            continue
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def extract_part_targets(text: str) -> List[Dict[str, str]]:
    """Extract explicit part-number-like targets from a question."""
    targets: List[Dict[str, str]] = []
    for pattern in (NUMERIC_PART_RE, ALPHA_PART_RE):
        for m in pattern.finditer(text or ""):
            raw = m.group(0).strip()
            norm = normalize_for_match(raw)
            # Avoid tiny/accidental matches after normalization.
            if len(norm) < 6:
                continue
            targets.append({"target_type": "part_number", "target_text": raw, "target_norm": norm})
    dedup: Dict[str, Dict[str, str]] = {}
    for target in targets:
        dedup.setdefault(target["target_norm"], target)
    return list(dedup.values())


def answer_has_safe_no_proof(answer: str) -> bool:
    low = (answer or "").lower()
    return any(phrase in low for phrase in SAFE_NO_PROOF_PHRASES)


def answer_claims_source_ready(answer: str, grade: Optional[Dict[str, Any]] = None) -> bool:
    if grade and grade.get("source_trace_ready_claim") is True:
        return True
    low = (answer or "").lower()
    return any(phrase in low for phrase in SOURCE_READY_CLAIM_PHRASES)


def question_has_dangerous_claim(question: str) -> bool:
    low = (question or "").lower()
    return any(term in low for term in DANGEROUS_CLAIM_TERMS)


def citation_strings(citation: Dict[str, Any]) -> List[str]:
    """Return fields worth checking when deciding if a citation matches a target."""
    keys = (
        "normalized_value",
        "value",
        "raw_value",
        "field_value",
        "field_name",
        "citation_id",
        "page_id",
        "source_text",
        "text",
        "ocr_text",
        "cell_text",
        "row_text",
        "nomenclature",
        "part_number",
        "covered_part_number",
        "ipl_part_number",
        "manual_page_reference",
    )
    values: List[str] = []
    for key in keys:
        if key in citation:
            values.append(str(citation.get(key)))
    # Some endpoint records keep useful values nested.
    for nested_key in ("metadata", "source", "record", "payload"):
        nested = citation.get(nested_key)
        if isinstance(nested, dict):
            for value in nested.values():
                if isinstance(value, (str, int, float)):
                    values.append(str(value))
    return values


def citation_matches_target(citation: Dict[str, Any], target_norms: Sequence[str]) -> bool:
    if not target_norms:
        return False
    haystack = " ".join(citation_strings(citation))
    norm_haystack = normalize_for_match(haystack)
    return any(target in norm_haystack for target in target_norms)


def dedupe_citations(citations: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        key = json.dumps(citation, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            out.append(citation)
    return out


def _collect_citations_from_trace_response(trace_response: Any) -> List[Dict[str, Any]]:
    citations: List[Dict[str, Any]] = []
    if not isinstance(trace_response, dict):
        return citations
    for key in ("citations",):
        value = trace_response.get(key)
        if isinstance(value, list):
            citations.extend([c for c in value if isinstance(c, dict)])
    nested_response = trace_response.get("response")
    if isinstance(nested_response, dict):
        value = nested_response.get("citations")
        if isinstance(value, list):
            citations.extend([c for c in value if isinstance(c, dict)])
    return citations


def selected_citations(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract citations from the selected TRACE try for one answer record."""
    citations: List[Dict[str, Any]] = []

    top_level = record.get("citations")
    if isinstance(top_level, list):
        citations.extend([c for c in top_level if isinstance(c, dict)])

    if isinstance(record.get("trace_response"), dict):
        citations.extend(_collect_citations_from_trace_response(record["trace_response"]))

    selected = record.get("selected_query_variant") or record.get("selected_query") or record.get("query")
    trace_tries = record.get("trace_tries")
    selected_try: Optional[Dict[str, Any]] = None
    if isinstance(trace_tries, list) and trace_tries:
        if selected:
            for item in trace_tries:
                if isinstance(item, dict) and item.get("query_variant") == selected:
                    selected_try = item
                    break
        if selected_try is None:
            # Fall back to the try with the most citations, matching how older runners often selected.
            dict_tries = [item for item in trace_tries if isinstance(item, dict)]
            if dict_tries:
                selected_try = max(dict_tries, key=lambda x: int(x.get("citation_count") or 0))
        if selected_try is not None:
            citations.extend(_collect_citations_from_trace_response(selected_try.get("trace_response")))

    return dedupe_citations(citations)


@dataclass
class RecordValidation:
    question_id: str
    question: str
    bucket: str
    raw_citation_count: int
    selected_citation_count: int
    explicit_part_targets: List[Dict[str, str]]
    target_citation_count: int
    target_citation_backed: bool
    off_target_citation_returned: bool
    safe_no_proof_answer: bool
    corpus_missing_target: bool
    dangerous_claim_question: bool
    source_ready_claim_without_target_citation: bool
    unsupported_claim: bool
    answer_permission: bool
    source_truth_mutation_allowed: bool
    engram_policy_used_as_source_proof: bool
    selected_query_variant: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question_id": self.question_id,
            "question": self.question,
            "bucket": self.bucket,
            "raw_citation_count": self.raw_citation_count,
            "selected_citation_count": self.selected_citation_count,
            "explicit_part_targets": self.explicit_part_targets,
            "target_citation_count": self.target_citation_count,
            "target_citation_backed": self.target_citation_backed,
            "off_target_citation_returned": self.off_target_citation_returned,
            "safe_no_proof_answer": self.safe_no_proof_answer,
            "corpus_missing_target": self.corpus_missing_target,
            "dangerous_claim_question": self.dangerous_claim_question,
            "source_ready_claim_without_target_citation": self.source_ready_claim_without_target_citation,
            "unsupported_claim": self.unsupported_claim,
            "answer_permission": self.answer_permission,
            "source_truth_mutation_allowed": self.source_truth_mutation_allowed,
            "engram_policy_used_as_source_proof": self.engram_policy_used_as_source_proof,
            "selected_query_variant": self.selected_query_variant,
        }


def validate_record(record: Dict[str, Any], corpus_missing_norms: Sequence[str]) -> RecordValidation:
    question = str(record.get("question") or "")
    answer = str(record.get("answer") or "")
    targets = extract_part_targets(question)
    target_norms = [t["target_norm"] for t in targets]
    citations = selected_citations(record)
    raw_citation_count = int(record.get("citation_count") or 0)
    selected_citation_count = len(citations)
    target_citation_count = sum(1 for c in citations if citation_matches_target(c, target_norms))
    target_citation_backed = bool(target_norms) and target_citation_count > 0
    off_target = bool(target_norms) and selected_citation_count > 0 and target_citation_count == 0
    safe_no_proof = answer_has_safe_no_proof(answer)
    grade = record.get("grade") if isinstance(record.get("grade"), dict) else {}
    source_ready_without_target = bool(target_norms) and target_citation_count == 0 and answer_claims_source_ready(answer, grade)
    dangerous = question_has_dangerous_claim(question)
    unsupported_claim = source_ready_without_target

    # If the model gives a safe no-proof answer for a missing target, that is not an unsupported claim.
    if safe_no_proof and not answer_claims_source_ready(answer, grade):
        unsupported_claim = False

    corpus_missing = any(target in set(corpus_missing_norms) for target in target_norms)

    return RecordValidation(
        question_id=str(record.get("question_id") or ""),
        question=question,
        bucket=str(record.get("bucket") or ""),
        raw_citation_count=raw_citation_count,
        selected_citation_count=selected_citation_count,
        explicit_part_targets=targets,
        target_citation_count=target_citation_count,
        target_citation_backed=target_citation_backed,
        off_target_citation_returned=off_target,
        safe_no_proof_answer=safe_no_proof,
        corpus_missing_target=corpus_missing,
        dangerous_claim_question=dangerous,
        source_ready_claim_without_target_citation=source_ready_without_target,
        unsupported_claim=unsupported_claim,
        answer_permission=bool(record.get("answer_permission")),
        source_truth_mutation_allowed=bool(record.get("source_truth_mutation_allowed")),
        engram_policy_used_as_source_proof=bool(grade.get("engram_policy_used_as_source_proof")),
        selected_query_variant=str(record.get("selected_query_variant") or record.get("selected_query") or ""),
    )


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
        if not isinstance(value, dict):
            raise SystemExit(f"Invalid JSONL at {path}:{line_number}: row is not an object")
        rows.append(value)
    return rows


def summarize(records: List[RecordValidation], raw_rows: List[Dict[str, Any]], corpus_missing_targets: Sequence[str]) -> Dict[str, Any]:
    raw_citation_backed = sum(1 for r in records if r.raw_citation_count > 0)
    off_target = sum(1 for r in records if r.off_target_citation_returned)
    unsupported = sum(1 for r in records if r.unsupported_claim)
    source_ready_without_target = sum(1 for r in records if r.source_ready_claim_without_target_citation)
    answer_permission = sum(1 for r in records if r.answer_permission)
    mutation_allowed = sum(1 for r in records if r.source_truth_mutation_allowed)
    engram_as_proof = sum(1 for r in records if r.engram_policy_used_as_source_proof)
    safe_no_proof = sum(1 for r in records if r.safe_no_proof_answer)
    corpus_missing = sum(1 for r in records if r.corpus_missing_target)
    target_citation_backed = sum(1 for r in records if r.target_citation_backed)
    part_target_questions = sum(1 for r in records if r.explicit_part_targets)

    quality_failures: List[str] = []
    if answer_permission:
        quality_failures.append("answer_permission_count_nonzero")
    if mutation_allowed:
        quality_failures.append("source_truth_mutation_allowed_count_nonzero")
    if engram_as_proof:
        quality_failures.append("engram_policy_as_proof_count_nonzero")
    if unsupported:
        quality_failures.append("unsupported_claim_count_nonzero")
    if source_ready_without_target:
        quality_failures.append("source_ready_claim_without_target_citation_nonzero")

    # Off-target citations are not necessarily a model safety failure when the final answer rejects them,
    # but they are a retrieval/scoring warning that must be visible.
    target_quality_status = "WARN" if off_target else "PASS"

    adjusted_citation_backed_count = max(0, raw_citation_backed - off_target)

    return {
        "module": MODULE,
        "version": VERSION,
        "status": "TRACE_NET_FIXED50_TARGET_CITATION_VALIDATION_DONE",
        "quality_status": "FAIL" if quality_failures else "PASS",
        "target_quality_status": target_quality_status,
        "quality_failures": quality_failures,
        "question_count": len(records),
        "answered_count": sum(1 for row in raw_rows if row.get("status") == "ok" or row.get("answer")),
        "raw_citation_backed_count": raw_citation_backed,
        "adjusted_citation_backed_count": adjusted_citation_backed_count,
        "part_target_question_count": part_target_questions,
        "target_citation_backed_count": target_citation_backed,
        "safe_no_proof_count": safe_no_proof,
        "corpus_missing_answer_count": corpus_missing,
        "off_target_citation_answer_count": off_target,
        "unsupported_claim_count": unsupported,
        "source_ready_claim_without_target_citation_count": source_ready_without_target,
        "answer_permission_count": answer_permission,
        "source_truth_mutation_allowed_count": mutation_allowed,
        "engram_policy_as_proof_count": engram_as_proof,
        "corpus_missing_targets": list(corpus_missing_targets),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate target-specific citations in fixed-50 TRACE-Net answers.")
    parser.add_argument("--answers", required=True, type=Path, help="Path to fixed-50 answers.jsonl")
    parser.add_argument("--summary-output", type=Path, default=None, help="Output summary JSON path")
    parser.add_argument("--records-output", type=Path, default=None, help="Output per-record validation JSONL path")
    parser.add_argument(
        "--corpus-missing-target",
        action="append",
        default=[],
        help="Explicit target known to be absent from source artifacts, e.g. DF250040-501. May be repeated.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    answers_path: Path = args.answers
    if not answers_path.exists():
        raise SystemExit(f"answers file not found: {answers_path}")

    rows = read_jsonl(answers_path)
    corpus_missing_norms = unique_keep_order(normalize_for_match(t) for t in args.corpus_missing_target)
    validations = [validate_record(row, corpus_missing_norms) for row in rows]
    summary = summarize(validations, rows, args.corpus_missing_target)

    summary_output = args.summary_output or answers_path.with_name("target_citation_summary_v1.json")
    records_output = args.records_output or answers_path.with_name("target_citation_records_v1.jsonl")
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    records_output.parent.mkdir(parents=True, exist_ok=True)

    summary["answers"] = str(answers_path)
    summary["summary_output"] = str(summary_output)
    summary["records_output"] = str(records_output)

    summary_output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with records_output.open("w", encoding="utf-8") as f:
        for record in validations:
            f.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")

    print(f"status={summary['status']}")
    print(f"quality_status={summary['quality_status']}")
    print(f"target_quality_status={summary['target_quality_status']}")
    print(f"question_count={summary['question_count']}")
    print(f"answered_count={summary['answered_count']}")
    print(f"raw_citation_backed_count={summary['raw_citation_backed_count']}")
    print(f"adjusted_citation_backed_count={summary['adjusted_citation_backed_count']}")
    print(f"part_target_question_count={summary['part_target_question_count']}")
    print(f"target_citation_backed_count={summary['target_citation_backed_count']}")
    print(f"safe_no_proof_count={summary['safe_no_proof_count']}")
    print(f"corpus_missing_answer_count={summary['corpus_missing_answer_count']}")
    print(f"off_target_citation_answer_count={summary['off_target_citation_answer_count']}")
    print(f"unsupported_claim_count={summary['unsupported_claim_count']}")
    print(f"source_ready_claim_without_target_citation_count={summary['source_ready_claim_without_target_citation_count']}")
    print(f"answer_permission_count={summary['answer_permission_count']}")
    print(f"source_truth_mutation_allowed_count={summary['source_truth_mutation_allowed_count']}")
    print(f"engram_policy_as_proof_count={summary['engram_policy_as_proof_count']}")
    print(f"summary={summary_output}")
    print(f"records={records_output}")
    return 1 if summary["quality_status"] == "FAIL" else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
