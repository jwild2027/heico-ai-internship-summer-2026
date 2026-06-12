"""TRACE-Net Answer Claim Critic v1.

This module adds a safe Self-RAG-style answer/claim critic layer.
It reads Dynamic Final-Gate Execution, Evidence Sufficiency Critic, and
Retrieval Critic outputs, then reviews final/dynamic answer text and claims
for wording, citation, proof-source, and leakage issues.

Safety contract:
- The critic can flag or clear claims for policy use.
- The critic cannot answer directly.
- The critic cannot prove claims.
- The critic cannot mutate source truth.
- Feedback, community, category, and retrieval-only records remain advisory
  and cannot become proof through this critic.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "trace_net_answer_claim_critic_v1"
ALGORITHM = "trace_net_read_only_self_rag_style_answer_claim_critic_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/answer_claim_critic")
DEFAULT_DYNAMIC_FINAL_GATE = Path("local_data/organization/trace_net/dynamic_final_gate_execution/trace_net_dynamic_final_gate_execution_v1.json")
DEFAULT_EVIDENCE_SUFFICIENCY = Path("local_data/organization/trace_net/evidence_sufficiency_critic/trace_net_evidence_sufficiency_critic_v1.json")
DEFAULT_RETRIEVAL_CRITIC = Path("local_data/organization/trace_net/retrieval_critic/trace_net_retrieval_critic_v1.json")
DEFAULT_OUTPUT_FILE = "trace_net_answer_claim_critic_v1.json"
DEFAULT_RECORDS_FILE = "trace_net_answer_claim_critic_v1_records.jsonl"
DEFAULT_CLAIMS_FILE = "trace_net_answer_claim_critic_v1_claims.jsonl"
DEFAULT_SUMMARY_FILE = "trace_net_answer_claim_critic_v1_summary.json"
DEFAULT_QUALITY_FILE = "trace_net_answer_claim_critic_v1_quality.json"
DEFAULT_MANIFEST_FILE = "trace_net_answer_claim_critic_v1_manifest.json"
DEFAULT_MD_FILE = "trace_net_answer_claim_critic_v1.md"
DEFAULT_HTML_FILE = "trace_net_answer_claim_critic_v1.html"

LOCAL_PATH_RE = re.compile(r"(?:[A-Za-z]:\\\\|[A-Za-z]:/|/mnt/|/home/|local_data[\\/]|\\\\Users\\\\|/Users/)", re.I)
RAW_BYTES_RE = re.compile(r"b['\"]|\\x[0-9a-fA-F]{2}")
CITATION_RE = re.compile(r"(?:\[?cite[:\w_./-]*[:\]][^\]\s,;)]*\]?|cite:[A-Za-z0-9_./:-]+)")
SOURCE_TRUTH_MUTATION_RE = re.compile(r"\b(?:mutate|rewrite|overwrite|delete|update|promote|commit|write back|writeback)\b.{0,40}\b(?:source truth|canonical source|graph truth|citation truth)\b", re.I)
FEEDBACK_PROOF_RE = re.compile(r"\bfeedback\b.{0,40}\b(?:proves?|confirms?|establishes?|shows?|truth|evidence)\b", re.I)
COMMUNITY_PROOF_RE = re.compile(r"\b(?:community|leiden)\b.{0,40}\b(?:proves?|confirms?|establishes?|shows?|truth|evidence)\b", re.I)
CATEGORY_PROOF_RE = re.compile(r"\bcategory\b.{0,40}\b(?:proves?|confirms?|establishes?|shows?|truth|evidence)\b", re.I)
RETRIEVAL_ONLY_PROOF_RE = re.compile(r"\bretrieval[- ]only\b.{0,40}\b(?:proves?|confirms?|establishes?|truth|final answer)\b", re.I)
OVERSTATEMENT_RE = re.compile(r"\b(?:guaranteed|definitive(?:ly)?|certain(?:ly)?|always|never|undeniable|conclusive(?:ly)?|without doubt|exactly proves|confirmed as source truth)\b", re.I)
OCR_OVERCONFIDENCE_RE = re.compile(r"\bOCR\b.{0,80}\b(?:perfect|definitive|guaranteed|certain|exact source truth|no noise)\b", re.I)

SAFE_ANSWER_STATUSES = {"FINAL_GATE_ARTIFACT_ANSWER", "DYNAMIC_FINAL_GATE_APPROVED"}
AUDIT_SUFFICIENCY_STATUSES = {"final_evidence_sufficient_but_retrieval_audit_required", "final_gate_claims_need_audit"}
CLEAR_SUFFICIENCY_STATUSES = {"final_artifact_evidence_sufficient", "final_evidence_sufficient"}
AUDIT_RETRIEVAL_STATUSES = {"dynamic_final_gate_needs_audit"}
CLEAR_RETRIEVAL_STATUSES = {"final_gate_already_authorized"}


class AnswerClaimCriticError(RuntimeError):
    """Raised when the answer claim critic cannot be built safely."""


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "pass", "allowed"}:
            return True
        if lowered in {"0", "false", "no", "n", "fail", "blocked"}:
            return False
    return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except Exception:
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def unique_texts(values: Iterable[Any]) -> list[str]:
    return sorted({as_text(value) for value in values if as_text(value)})


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def stable_hash(value: Any, length: int = 16) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()[:length]


def read_json(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        value = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with p.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False, default=str) + "\n")
            count += 1
    return count


def quality_status(payload: Mapping[str, Any]) -> str:
    for key in ("quality_status", "status"):
        value = as_text(payload.get(key)).upper()
        if value in {"PASS", "FAIL"}:
            return value
    summary = payload.get("summary")
    if isinstance(summary, Mapping):
        for key in ("quality_status", "status"):
            value = as_text(summary.get(key)).upper()
            if value in {"PASS", "FAIL"}:
                return value
    return ""


def normalize_query(value: Any) -> str:
    return re.sub(r"\s+", " ", as_text(value).lower())


def index_records_by_query(report: Mapping[str, Any], record_key: str) -> dict[str, dict[str, Any]]:
    rows = report.get(record_key) or report.get("query_results") or report.get("results") or []
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(rows, list):
        return out
    for row in rows:
        if isinstance(row, Mapping):
            q = normalize_query(row.get("query"))
            if q:
                out[q] = dict(row)
    return out


def text_issue_counts(text: str) -> dict[str, int]:
    return {
        "local_path_leak_count": len(LOCAL_PATH_RE.findall(text)),
        "raw_bytes_repr_count": len(RAW_BYTES_RE.findall(text)),
        "feedback_as_proof_count": len(FEEDBACK_PROOF_RE.findall(text)),
        "community_as_proof_count": len(COMMUNITY_PROOF_RE.findall(text)),
        "category_as_proof_count": len(CATEGORY_PROOF_RE.findall(text)),
        "retrieval_only_as_proof_count": len(RETRIEVAL_ONLY_PROOF_RE.findall(text)),
        "source_truth_mutation_language_count": len(SOURCE_TRUTH_MUTATION_RE.findall(text)),
        "overstatement_warning_count": len(OVERSTATEMENT_RE.findall(text)),
        "ocr_overconfidence_warning_count": len(OCR_OVERCONFIDENCE_RE.findall(text)),
    }


def citation_refs_in_text(text: str) -> list[str]:
    refs: set[str] = set()
    for match in CITATION_RE.finditer(text or ""):
        value = match.group(0).strip("[]")
        if value:
            refs.add(value)
    return sorted(refs)


def claim_text(claim: Mapping[str, Any]) -> str:
    for key in ("claim_text", "final_claim_text", "clean_materialized_claim_text", "materialized_claim_text", "text"):
        value = as_text(claim.get(key))
        if value:
            return value
    return ""


def claim_id(claim: Mapping[str, Any], fallback: Any) -> str:
    for key in ("dynamic_final_claim_id", "final_claim_id", "claim_id", "id"):
        value = as_text(claim.get(key))
        if value:
            return value
    return f"claim__{stable_hash([fallback, claim])}"


def evaluate_claim(claim: Mapping[str, Any], *, query: str, answer_status: str) -> dict[str, Any]:
    text = claim_text(claim)
    citations = unique_texts(as_list(claim.get("citation_ids")))
    page_id = as_text(claim.get("page_id"))
    reasons: list[str] = []
    warnings: list[str] = []

    if not text:
        reasons.append("missing_claim_text")
    if not page_id and answer_status != "FINAL_GATE_ARTIFACT_ANSWER":
        reasons.append("missing_page_id")
    if not citations and answer_status != "FINAL_GATE_ARTIFACT_ANSWER":
        reasons.append("missing_citation_ids")
    if as_bool(claim.get("retrieval_only")):
        reasons.append("retrieval_only_claim")
    if as_bool(claim.get("feedback_as_proof")):
        reasons.append("feedback_as_proof")
    if as_bool(claim.get("community_as_proof")):
        reasons.append("community_as_proof")
    if as_bool(claim.get("category_as_proof")):
        reasons.append("category_as_proof")
    if as_bool(claim.get("source_truth_mutation_allowed")) or as_bool(claim.get("can_mutate_source_truth")):
        reasons.append("source_truth_mutation_risk")

    issues = text_issue_counts(text)
    if issues["local_path_leak_count"]:
        reasons.append("local_path_leak_in_claim")
    if issues["raw_bytes_repr_count"]:
        reasons.append("raw_bytes_repr_in_claim")
    if issues["feedback_as_proof_count"]:
        reasons.append("feedback_used_as_claim_proof_text")
    if issues["community_as_proof_count"]:
        reasons.append("community_used_as_claim_proof_text")
    if issues["category_as_proof_count"]:
        reasons.append("category_used_as_claim_proof_text")
    if issues["retrieval_only_as_proof_count"]:
        reasons.append("retrieval_only_used_as_claim_proof_text")
    if issues["source_truth_mutation_language_count"]:
        reasons.append("source_truth_mutation_language_in_claim")
    if issues["overstatement_warning_count"]:
        warnings.append("overstatement_language_present")
    if issues["ocr_overconfidence_warning_count"]:
        warnings.append("ocr_overconfidence_language_present")

    status = "claim_clear"
    if reasons:
        status = "claim_blocked"
    elif warnings:
        status = "claim_clear_with_wording_warning"

    return {
        "answer_claim_critic_claim_id": f"ansclaimcrit__{stable_hash([query, claim_id(claim, query), reasons, warnings])}",
        "source_claim_id": claim_id(claim, query),
        "query": query,
        "answer_status": answer_status,
        "claim_status": status,
        "claim_text": text,
        "page_id": page_id,
        "citation_ids": citations,
        "part_numbers": unique_texts(as_list(claim.get("part_numbers"))),
        "rag_buckets": unique_texts(as_list(claim.get("rag_buckets") or claim.get("rag_bucket"))),
        "authorities": unique_texts(as_list(claim.get("authorities") or claim.get("authority"))),
        "reason_codes": unique_texts(reasons),
        "warning_codes": unique_texts(warnings),
        **issues,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
        "advisory_only": True,
    }


def evaluate_answer_text(text: str, *, expected_citations: Iterable[str]) -> dict[str, Any]:
    issues = text_issue_counts(text)
    text_refs = citation_refs_in_text(text)
    expected = unique_texts(expected_citations)
    missing_refs: list[str] = []
    if expected and text:
        # Support both exact cite IDs and shortened bracketed forms that include the ID.
        for cid in expected:
            if cid and cid not in text:
                missing_refs.append(cid)
    return {
        "answer_text_length": len(text or ""),
        "citation_reference_count": len(text_refs),
        "expected_citation_count": len(expected),
        "missing_expected_citation_reference_count": len(missing_refs),
        "missing_expected_citation_references": missing_refs[:20],
        **issues,
    }


def build_answer_record(
    result: Mapping[str, Any],
    *,
    evidence_sufficiency_record: Mapping[str, Any] | None = None,
    retrieval_critic_record: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    query = as_text(result.get("query"))
    answer_status = as_text(result.get("answer_status"))
    answer_text = as_text(result.get("final_answer_text") or result.get("answer_text"))
    claims = [c for c in as_list(result.get("final_claims")) if isinstance(c, Mapping)]
    claim_records = [evaluate_claim(c, query=query, answer_status=answer_status) for c in claims]
    expected_citations = [cid for c in claims for cid in as_list(c.get("citation_ids"))]
    answer_text_eval = evaluate_answer_text(answer_text, expected_citations=expected_citations)

    evidence_status = as_text((evidence_sufficiency_record or {}).get("evidence_sufficiency_status"))
    evidence_action = as_text((evidence_sufficiency_record or {}).get("recommended_next_action"))
    retrieval_status = as_text((retrieval_critic_record or {}).get("critic_status"))
    retrieval_action = as_text((retrieval_critic_record or {}).get("recommended_next_action"))

    blocked_claims = [c for c in claim_records if c["claim_status"] == "claim_blocked"]
    warning_claims = [c for c in claim_records if c["claim_status"] == "claim_clear_with_wording_warning"]
    clear_claims = [c for c in claim_records if c["claim_status"] in {"claim_clear", "claim_clear_with_wording_warning"}]

    reason_codes: list[str] = []
    warning_codes: list[str] = []
    for c in blocked_claims:
        reason_codes.extend(as_list(c.get("reason_codes")))
    for c in warning_claims:
        warning_codes.extend(as_list(c.get("warning_codes")))
    if answer_text_eval["local_path_leak_count"]:
        reason_codes.append("local_path_leak_in_answer_text")
    if answer_text_eval["raw_bytes_repr_count"]:
        reason_codes.append("raw_bytes_repr_in_answer_text")
    if answer_text_eval["feedback_as_proof_count"]:
        reason_codes.append("feedback_used_as_answer_proof_text")
    if answer_text_eval["community_as_proof_count"]:
        reason_codes.append("community_used_as_answer_proof_text")
    if answer_text_eval["category_as_proof_count"]:
        reason_codes.append("category_used_as_answer_proof_text")
    if answer_text_eval["retrieval_only_as_proof_count"]:
        reason_codes.append("retrieval_only_used_as_answer_proof_text")
    if answer_text_eval["source_truth_mutation_language_count"]:
        reason_codes.append("source_truth_mutation_language_in_answer_text")
    if answer_text_eval["missing_expected_citation_reference_count"]:
        reason_codes.append("answer_text_missing_expected_citation_references")
    if answer_text_eval["overstatement_warning_count"]:
        warning_codes.append("overstatement_language_in_answer_text")
    if answer_text_eval["ocr_overconfidence_warning_count"]:
        warning_codes.append("ocr_overconfidence_language_in_answer_text")

    final_allowed = as_bool(result.get("final_answer_allowed"))
    if final_allowed and not answer_text and answer_status != "FINAL_GATE_ARTIFACT_ANSWER":
        reason_codes.append("final_allowed_but_missing_answer_text")
    if final_allowed and answer_status not in SAFE_ANSWER_STATUSES:
        reason_codes.append("unrecognized_final_answer_status")
    if evidence_status in AUDIT_SUFFICIENCY_STATUSES:
        reason_codes.append("evidence_sufficiency_requires_audit")
    elif evidence_status and evidence_status not in CLEAR_SUFFICIENCY_STATUSES:
        reason_codes.append("evidence_sufficiency_not_clear")
    if retrieval_status in AUDIT_RETRIEVAL_STATUSES:
        reason_codes.append("retrieval_critic_requires_audit")
    elif retrieval_status and retrieval_status not in CLEAR_RETRIEVAL_STATUSES:
        warning_codes.append("retrieval_critic_not_explicitly_clear")

    if as_int(result.get("uncited_final_claim_count")):
        reason_codes.append("dynamic_gate_uncited_final_claim_count_nonzero")
    if as_int(result.get("retrieval_only_final_claim_count")):
        reason_codes.append("dynamic_gate_retrieval_only_final_claim_count_nonzero")
    if as_int(result.get("feedback_as_proof_count")):
        reason_codes.append("dynamic_gate_feedback_as_proof_count_nonzero")
    if as_int(result.get("community_as_proof_count")):
        reason_codes.append("dynamic_gate_community_as_proof_count_nonzero")
    if as_int(result.get("category_as_proof_count")):
        reason_codes.append("dynamic_gate_category_as_proof_count_nonzero")
    if as_int(result.get("source_truth_mutation_allowed_count")) or as_bool(result.get("source_truth_mutation_allowed")):
        reason_codes.append("dynamic_gate_source_truth_mutation_risk")

    if not final_allowed:
        status = "no_final_answer_to_criticize"
        action = "keep_retrieval_only_or_run_final_gate"
    elif reason_codes:
        status = "answer_claims_need_audit"
        action = "audit_answer_claims_before_returning_answer"
    elif evidence_status in AUDIT_SUFFICIENCY_STATUSES or retrieval_status in AUDIT_RETRIEVAL_STATUSES:
        status = "answer_claims_clear_but_audit_required"
        action = "audit_retrieval_or_evidence_before_returning_answer"
    elif warning_codes:
        status = "answer_claims_clear_with_wording_warnings"
        action = "return_answer_if_policy_allows_after_wording_review"
    elif answer_status == "FINAL_GATE_ARTIFACT_ANSWER":
        status = "final_artifact_answer_claims_clear"
        action = "return_final_gate_artifact_answer_if_policy_allows"
    else:
        status = "answer_claims_clear_for_return"
        action = "return_dynamic_final_answer_if_policy_allows"

    return {
        "answer_claim_critic_record_id": f"anscrit__{stable_hash([query, answer_status, status])}",
        "query_id": as_text(result.get("query_id")),
        "query": query,
        "answer_status": answer_status,
        "answer_claim_critic_status": status,
        "recommended_next_action": action,
        "reason_codes": unique_texts(reason_codes),
        "warning_codes": unique_texts(warning_codes),
        "final_answer_allowed_by_dynamic_gate": final_allowed,
        "answer_text_present": bool(answer_text),
        "answer_text_preview": answer_text[:1000],
        "final_claim_count": as_int(result.get("final_claim_count") or len(claims)),
        "claim_critic_record_count": len(claim_records),
        "claim_clear_count": len(clear_claims),
        "claim_blocked_count": len(blocked_claims),
        "claim_warning_count": len(warning_claims),
        "blocked_claim_count_from_dynamic_gate": as_int(result.get("blocked_claim_count")),
        "retrieval_group_count": as_int(result.get("retrieval_group_count")),
        "exact_hit_group_count": as_int(result.get("exact_hit_group_count")),
        "semantic_group_count": as_int(result.get("semantic_group_count")),
        "evidence_sufficiency_status": evidence_status,
        "evidence_sufficiency_action": evidence_action,
        "retrieval_critic_status": retrieval_status,
        "retrieval_critic_action": retrieval_action,
        **answer_text_eval,
        "claim_local_path_leak_count": sum(as_int(c.get("local_path_leak_count")) for c in claim_records),
        "claim_raw_bytes_repr_count": sum(as_int(c.get("raw_bytes_repr_count")) for c in claim_records),
        "claim_feedback_as_proof_count": sum(as_int(c.get("feedback_as_proof_count")) for c in claim_records),
        "claim_community_as_proof_count": sum(as_int(c.get("community_as_proof_count")) for c in claim_records),
        "claim_category_as_proof_count": sum(as_int(c.get("category_as_proof_count")) for c in claim_records),
        "claim_retrieval_only_as_proof_count": sum(as_int(c.get("retrieval_only_as_proof_count")) for c in claim_records),
        "claim_source_truth_mutation_language_count": sum(as_int(c.get("source_truth_mutation_language_count")) for c in claim_records),
        "claim_overstatement_warning_count": sum(as_int(c.get("overstatement_warning_count")) for c in claim_records),
        "claim_ocr_overconfidence_warning_count": sum(as_int(c.get("ocr_overconfidence_warning_count")) for c in claim_records),
        "uncited_final_claim_count": as_int(result.get("uncited_final_claim_count")),
        "retrieval_only_final_claim_count": as_int(result.get("retrieval_only_final_claim_count")),
        "feedback_as_proof_count": as_int(result.get("feedback_as_proof_count")),
        "community_as_proof_count": as_int(result.get("community_as_proof_count")),
        "category_as_proof_count": as_int(result.get("category_as_proof_count")),
        "source_truth_mutation_allowed_count": as_int(result.get("source_truth_mutation_allowed_count")),
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
        "advisory_only": True,
    }, claim_records


def build_report(
    *,
    dynamic_final_gate_report: Mapping[str, Any],
    evidence_sufficiency_report: Mapping[str, Any] | None = None,
    retrieval_critic_report: Mapping[str, Any] | None = None,
    query_filter: str | None = None,
) -> dict[str, Any]:
    suff_by_query = index_records_by_query(evidence_sufficiency_report or {}, "sufficiency_records")
    retrieval_by_query = index_records_by_query(retrieval_critic_report or {}, "critic_records")
    rows = [r for r in as_list(dynamic_final_gate_report.get("query_results")) if isinstance(r, Mapping)]
    if query_filter:
        q = normalize_query(query_filter)
        rows = [r for r in rows if normalize_query(r.get("query")) == q]

    answer_records: list[dict[str, Any]] = []
    claim_records: list[dict[str, Any]] = []
    for result in rows:
        q = normalize_query(result.get("query"))
        answer_record, claims = build_answer_record(
            result,
            evidence_sufficiency_record=suff_by_query.get(q),
            retrieval_critic_record=retrieval_by_query.get(q),
        )
        answer_records.append(answer_record)
        claim_records.extend(claims)

    source_quality_statuses = {
        "dynamic_final_gate": quality_status(dynamic_final_gate_report),
        "evidence_sufficiency_critic": quality_status(evidence_sufficiency_report or {}),
        "retrieval_critic": quality_status(retrieval_critic_report or {}),
    }
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "ANSWER_CLAIM_CRITIC_BUILT",
        "generated_at": now_iso(),
        "read_only_critic": True,
        "answer_critic_records": answer_records,
        "claim_critic_records": claim_records,
        "source_quality_statuses": source_quality_statuses,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "source_truth_mutations_performed": 0,
    }
    report["summary"] = summarize(report)
    report["quality_status"] = "PASS" if report["summary"].get("status") == "PASS" else "FAIL"
    return report


def summarize(report: Mapping[str, Any]) -> dict[str, Any]:
    records = [r for r in as_list(report.get("answer_critic_records")) if isinstance(r, Mapping)]
    claims = [c for c in as_list(report.get("claim_critic_records")) if isinstance(c, Mapping)]
    status_counts = Counter(as_text(r.get("answer_claim_critic_status")) for r in records)
    action_counts = Counter(as_text(r.get("recommended_next_action")) for r in records)
    reason_counts = Counter(reason for r in records for reason in as_list(r.get("reason_codes")))
    warning_counts = Counter(warn for r in records for warn in as_list(r.get("warning_codes")))
    claim_status_counts = Counter(as_text(c.get("claim_status")) for c in claims)
    source_statuses = report.get("source_quality_statuses") if isinstance(report.get("source_quality_statuses"), Mapping) else {}

    critic_can_answer = sum(1 for r in records if as_bool(r.get("can_answer_directly")))
    critic_can_prove = sum(1 for r in records if as_bool(r.get("can_prove_claims")))
    source_truth_mutation_allowed = sum(1 for r in records if as_bool(r.get("source_truth_mutation_allowed")) or as_bool(r.get("can_mutate_source_truth")))
    source_truth_mutation_allowed += sum(1 for c in claims if as_bool(c.get("source_truth_mutation_allowed")) or as_bool(c.get("can_mutate_source_truth")))

    local_path_leaks = sum(as_int(r.get("local_path_leak_count")) + as_int(r.get("claim_local_path_leak_count")) for r in records)
    raw_bytes = sum(as_int(r.get("raw_bytes_repr_count")) + as_int(r.get("claim_raw_bytes_repr_count")) for r in records)
    feedback_as_proof = sum(as_int(r.get("feedback_as_proof_count")) + as_int(r.get("claim_feedback_as_proof_count")) for r in records)
    community_as_proof = sum(as_int(r.get("community_as_proof_count")) + as_int(r.get("claim_community_as_proof_count")) for r in records)
    category_as_proof = sum(as_int(r.get("category_as_proof_count")) + as_int(r.get("claim_category_as_proof_count")) for r in records)
    retrieval_only_as_proof = sum(as_int(r.get("retrieval_only_as_proof_count")) + as_int(r.get("claim_retrieval_only_as_proof_count")) for r in records)
    source_truth_mutation_language = sum(as_int(r.get("source_truth_mutation_language_count")) + as_int(r.get("claim_source_truth_mutation_language_count")) for r in records)
    missing_citation_refs = sum(as_int(r.get("missing_expected_citation_reference_count")) for r in records)
    overstatement = sum(as_int(r.get("overstatement_warning_count")) + as_int(r.get("claim_overstatement_warning_count")) for r in records)
    ocr_overconfidence = sum(as_int(r.get("ocr_overconfidence_warning_count")) + as_int(r.get("claim_ocr_overconfidence_warning_count")) for r in records)
    unsafe_answer_records = sum(1 for r in records if as_text(r.get("answer_claim_critic_status")) == "answer_claims_need_audit")

    summary = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "PASS",
        "answer_claim_record_count": len(records),
        "query_count": len(records),
        "claim_critic_record_count": len(claims),
        "answer_claim_critic_status_counts": dict(sorted(status_counts.items())),
        "recommended_action_counts": dict(sorted(action_counts.items())),
        "reason_code_counts": dict(sorted(reason_counts.items())),
        "warning_code_counts": dict(sorted(warning_counts.items())),
        "claim_status_counts": dict(sorted(claim_status_counts.items())),
        "final_artifact_answer_claims_clear_count": status_counts.get("final_artifact_answer_claims_clear", 0),
        "answer_claims_clear_for_return_count": status_counts.get("answer_claims_clear_for_return", 0),
        "answer_claims_clear_with_wording_warnings_count": status_counts.get("answer_claims_clear_with_wording_warnings", 0),
        "answer_claims_clear_but_audit_required_count": status_counts.get("answer_claims_clear_but_audit_required", 0),
        "answer_claims_need_audit_count": status_counts.get("answer_claims_need_audit", 0),
        "no_final_answer_to_criticize_count": status_counts.get("no_final_answer_to_criticize", 0),
        "claim_clear_count": claim_status_counts.get("claim_clear", 0) + claim_status_counts.get("claim_clear_with_wording_warning", 0),
        "claim_blocked_count": claim_status_counts.get("claim_blocked", 0),
        "claim_warning_count": claim_status_counts.get("claim_clear_with_wording_warning", 0),
        "answer_text_present_count": sum(1 for r in records if as_bool(r.get("answer_text_present"))),
        "missing_citation_reference_count": missing_citation_refs,
        "overstatement_warning_count": overstatement,
        "ocr_overconfidence_warning_count": ocr_overconfidence,
        "local_path_leak_count": local_path_leaks,
        "raw_bytes_repr_count": raw_bytes,
        "feedback_as_proof_count": feedback_as_proof,
        "community_as_proof_count": community_as_proof,
        "category_as_proof_count": category_as_proof,
        "retrieval_only_as_proof_count": retrieval_only_as_proof,
        "source_truth_mutation_language_count": source_truth_mutation_language,
        "uncited_final_claim_count": sum(as_int(r.get("uncited_final_claim_count")) for r in records),
        "retrieval_only_final_claim_count": sum(as_int(r.get("retrieval_only_final_claim_count")) for r in records),
        "unsafe_answer_claim_record_count": unsafe_answer_records,
        "answer_critic_can_answer_directly_count": critic_can_answer,
        "answer_critic_can_prove_claims_count": critic_can_prove,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed,
        "source_truth_mutations_performed": as_int(report.get("source_truth_mutations_performed")),
        "postgres_write_attempt_count": as_int(report.get("postgres_write_attempt_count")),
        "qdrant_write_attempt_count": as_int(report.get("qdrant_write_attempt_count")),
        "opensearch_write_attempt_count": as_int(report.get("opensearch_write_attempt_count")),
        "source_quality_statuses": dict(source_statuses),
        "dynamic_final_gate_quality_status": as_text(source_statuses.get("dynamic_final_gate")),
        "evidence_sufficiency_critic_quality_status": as_text(source_statuses.get("evidence_sufficiency_critic")),
        "retrieval_critic_quality_status": as_text(source_statuses.get("retrieval_critic")),
    }
    if any([
        local_path_leaks,
        raw_bytes,
        feedback_as_proof,
        community_as_proof,
        category_as_proof,
        retrieval_only_as_proof,
        source_truth_mutation_language,
        as_int(summary.get("uncited_final_claim_count")),
        as_int(summary.get("retrieval_only_final_claim_count")),
        critic_can_answer,
        critic_can_prove,
        source_truth_mutation_allowed,
        as_int(report.get("postgres_write_attempt_count")),
        as_int(report.get("qdrant_write_attempt_count")),
        as_int(report.get("opensearch_write_attempt_count")),
        as_int(report.get("source_truth_mutations_performed")),
    ]):
        summary["status"] = "FAIL"
    return summary


def quality_report(
    report: Mapping[str, Any],
    *,
    min_answer_records: int = 1,
    min_queries: int = 1,
    min_claim_records: int = 0,
    require_dynamic_final_gate_quality_pass: bool = False,
    require_evidence_sufficiency_quality_pass: bool = False,
    require_retrieval_critic_quality_pass: bool = False,
) -> dict[str, Any]:
    summary = dict(report.get("summary") if isinstance(report.get("summary"), Mapping) else summarize(report))
    checks = {
        "answer_claim_record_count_minimum_met": as_int(summary.get("answer_claim_record_count")) >= min_answer_records,
        "query_count_minimum_met": as_int(summary.get("query_count")) >= min_queries,
        "claim_critic_record_count_minimum_met": as_int(summary.get("claim_critic_record_count")) >= min_claim_records,
        "answer_critic_can_answer_directly_zero": as_int(summary.get("answer_critic_can_answer_directly_count")) == 0,
        "answer_critic_can_prove_claims_zero": as_int(summary.get("answer_critic_can_prove_claims_count")) == 0,
        "source_truth_mutation_allowed_zero": as_int(summary.get("source_truth_mutation_allowed_count")) == 0,
        "source_truth_mutations_performed_zero": as_int(summary.get("source_truth_mutations_performed")) == 0,
        "feedback_as_proof_zero": as_int(summary.get("feedback_as_proof_count")) == 0,
        "community_as_proof_zero": as_int(summary.get("community_as_proof_count")) == 0,
        "category_as_proof_zero": as_int(summary.get("category_as_proof_count")) == 0,
        "retrieval_only_as_proof_zero": as_int(summary.get("retrieval_only_as_proof_count")) == 0,
        "local_path_leak_zero": as_int(summary.get("local_path_leak_count")) == 0,
        "raw_bytes_repr_zero": as_int(summary.get("raw_bytes_repr_count")) == 0,
        "source_truth_mutation_language_zero": as_int(summary.get("source_truth_mutation_language_count")) == 0,
        "uncited_final_claim_count_zero": as_int(summary.get("uncited_final_claim_count")) == 0,
        "retrieval_only_final_claim_count_zero": as_int(summary.get("retrieval_only_final_claim_count")) == 0,
        "postgres_write_attempt_zero": as_int(summary.get("postgres_write_attempt_count")) == 0,
        "qdrant_write_attempt_zero": as_int(summary.get("qdrant_write_attempt_count")) == 0,
        "opensearch_write_attempt_zero": as_int(summary.get("opensearch_write_attempt_count")) == 0,
    }
    if require_dynamic_final_gate_quality_pass:
        checks["dynamic_final_gate_quality_pass"] = as_text(summary.get("dynamic_final_gate_quality_status")).upper() == "PASS"
    if require_evidence_sufficiency_quality_pass:
        checks["evidence_sufficiency_quality_pass"] = as_text(summary.get("evidence_sufficiency_critic_quality_status")).upper() == "PASS"
    if require_retrieval_critic_quality_pass:
        checks["retrieval_critic_quality_pass"] = as_text(summary.get("retrieval_critic_quality_status")).upper() == "PASS"
    status = "PASS" if all(checks.values()) else "FAIL"
    return {"schema_version": f"{SCHEMA_VERSION}_quality", "status": status, "summary": summary, "checks": checks}


def write_markdown(path: str | Path, report: Mapping[str, Any]) -> None:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# TRACE-Net Answer Claim Critic v1",
        "",
        f"**Status:** {html.escape(as_text(report.get('quality_status') or summary.get('status')))}",
        f"**Generated:** {html.escape(as_text(report.get('generated_at')))}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "answer_claim_record_count",
        "claim_critic_record_count",
        "final_artifact_answer_claims_clear_count",
        "answer_claims_clear_for_return_count",
        "answer_claims_clear_but_audit_required_count",
        "answer_claims_need_audit_count",
        "missing_citation_reference_count",
        "overstatement_warning_count",
        "local_path_leak_count",
        "raw_bytes_repr_count",
        "feedback_as_proof_count",
        "community_as_proof_count",
        "category_as_proof_count",
        "retrieval_only_as_proof_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.append("")
    lines.append("## Critic Records")
    lines.append("")
    for rec in as_list(report.get("answer_critic_records"))[:20]:
        if isinstance(rec, Mapping):
            lines.append(f"- **{html.escape(as_text(rec.get('query')))}**: `{html.escape(as_text(rec.get('answer_claim_critic_status')))}` -> {html.escape(as_text(rec.get('recommended_next_action')))}")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_html(path: str | Path, report: Mapping[str, Any]) -> None:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}
    rows = []
    for rec in as_list(report.get("answer_critic_records"))[:100]:
        if isinstance(rec, Mapping):
            rows.append(
                "<tr>"
                f"<td>{html.escape(as_text(rec.get('query')))}</td>"
                f"<td>{html.escape(as_text(rec.get('answer_claim_critic_status')))}</td>"
                f"<td>{html.escape(as_text(rec.get('recommended_next_action')))}</td>"
                f"<td>{html.escape(', '.join(as_text(x) for x in as_list(rec.get('reason_codes'))))}</td>"
                "</tr>"
            )
    body = f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><title>TRACE-Net Answer Claim Critic v1</title>
<style>body{{font-family:Arial,sans-serif;margin:2rem}} table{{border-collapse:collapse;width:100%}} td,th{{border:1px solid #ddd;padding:.4rem}} th{{background:#f3f3f3}}</style></head>
<body>
<h1>TRACE-Net Answer Claim Critic v1</h1>
<p><b>Status:</b> {html.escape(as_text(report.get('quality_status') or summary.get('status')))}</p>
<p><b>Records:</b> {summary.get('answer_claim_record_count')} answers, {summary.get('claim_critic_record_count')} claims</p>
<table><thead><tr><th>Query</th><th>Status</th><th>Action</th><th>Reasons</th></tr></thead><tbody>
{''.join(rows)}
</tbody></table>
</body></html>"""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(body, encoding="utf-8")


def build_answer_claim_critic(
    *,
    dynamic_final_gate_path: str | Path,
    evidence_sufficiency_critic_path: str | Path | None = None,
    retrieval_critic_path: str | Path | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    query: str = "",
    min_answer_records: int = 1,
    min_queries: int = 1,
    min_claim_records: int = 0,
    require_dynamic_final_gate_quality_pass: bool = False,
    require_evidence_sufficiency_quality_pass: bool = False,
    require_retrieval_critic_quality_pass: bool = False,
) -> dict[str, Any]:
    dynamic = read_json(dynamic_final_gate_path)
    suff = read_json(evidence_sufficiency_critic_path) if evidence_sufficiency_critic_path else {}
    retrieval = read_json(retrieval_critic_path) if retrieval_critic_path else {}
    report = build_report(
        dynamic_final_gate_report=dynamic,
        evidence_sufficiency_report=suff,
        retrieval_critic_report=retrieval,
        query_filter=query or None,
    )
    qreport = quality_report(
        report,
        min_answer_records=min_answer_records,
        min_queries=min_queries,
        min_claim_records=min_claim_records,
        require_dynamic_final_gate_quality_pass=require_dynamic_final_gate_quality_pass,
        require_evidence_sufficiency_quality_pass=require_evidence_sufficiency_quality_pass,
        require_retrieval_critic_quality_pass=require_retrieval_critic_quality_pass,
    )
    report["quality_status"] = qreport["status"]
    report["quality_checks"] = qreport["checks"]
    report["summary"]["status"] = qreport["status"]
    report["source_artifacts"] = {
        "dynamic_final_gate": str(dynamic_final_gate_path),
        "evidence_sufficiency_critic": str(evidence_sufficiency_critic_path or ""),
        "retrieval_critic": str(retrieval_critic_path or ""),
    }

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / DEFAULT_OUTPUT_FILE
    records_path = out_dir / DEFAULT_RECORDS_FILE
    claims_path = out_dir / DEFAULT_CLAIMS_FILE
    summary_path = out_dir / DEFAULT_SUMMARY_FILE
    quality_path = out_dir / DEFAULT_QUALITY_FILE
    manifest_path = out_dir / DEFAULT_MANIFEST_FILE
    md_path = out_dir / DEFAULT_MD_FILE
    html_path = out_dir / DEFAULT_HTML_FILE
    write_json(report_path, report)
    write_jsonl(records_path, report.get("answer_critic_records", []))
    write_jsonl(claims_path, report.get("claim_critic_records", []))
    write_json(summary_path, report["summary"])
    write_json(quality_path, qreport)
    write_json(manifest_path, {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": now_iso(),
        "report_path": str(report_path),
        "records_path": str(records_path),
        "claims_path": str(claims_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "source_artifacts": report["source_artifacts"],
    })
    write_markdown(md_path, report)
    write_html(html_path, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Answer Claim Critic v1")
    parser.add_argument("--dynamic-final-gate", default=str(DEFAULT_DYNAMIC_FINAL_GATE))
    parser.add_argument("--evidence-sufficiency-critic", default=str(DEFAULT_EVIDENCE_SUFFICIENCY))
    parser.add_argument("--retrieval-critic", default=str(DEFAULT_RETRIEVAL_CRITIC))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--query", default="")
    parser.add_argument("--min-answer-records", type=int, default=1)
    parser.add_argument("--min-queries", type=int, default=1)
    parser.add_argument("--min-claim-records", type=int, default=0)
    parser.add_argument("--require-dynamic-final-gate-quality-pass", action="store_true")
    parser.add_argument("--require-evidence-sufficiency-quality-pass", action="store_true")
    parser.add_argument("--require-retrieval-critic-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def print_summary(report: Mapping[str, Any]) -> None:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}
    print("TRACE-Net Answer Claim Critic v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "answer_claim_record_count",
        "claim_critic_record_count",
        "final_artifact_answer_claims_clear_count",
        "answer_claims_clear_for_return_count",
        "answer_claims_clear_but_audit_required_count",
        "answer_claims_need_audit_count",
        "overstatement_warning_count",
        "local_path_leak_count",
        "raw_bytes_repr_count",
        "feedback_as_proof_count",
        "community_as_proof_count",
        "category_as_proof_count",
        "retrieval_only_as_proof_count",
        "answer_critic_can_answer_directly_count",
        "answer_critic_can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    print(f" report_path: {Path(DEFAULT_OUTPUT_DIR) / DEFAULT_OUTPUT_FILE if False else ''}".rstrip())


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_answer_claim_critic(
        dynamic_final_gate_path=args.dynamic_final_gate,
        evidence_sufficiency_critic_path=args.evidence_sufficiency_critic,
        retrieval_critic_path=args.retrieval_critic,
        output_dir=args.output_dir,
        query=args.query,
        min_answer_records=args.min_answer_records,
        min_queries=args.min_queries,
        min_claim_records=args.min_claim_records,
        require_dynamic_final_gate_quality_pass=args.require_dynamic_final_gate_quality_pass,
        require_evidence_sufficiency_quality_pass=args.require_evidence_sufficiency_quality_pass,
        require_retrieval_critic_quality_pass=args.require_retrieval_critic_quality_pass,
    )
    summary = report.get("summary", {})
    print("TRACE-Net Answer Claim Critic v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "answer_claim_record_count",
        "claim_critic_record_count",
        "final_artifact_answer_claims_clear_count",
        "answer_claims_clear_for_return_count",
        "answer_claims_clear_but_audit_required_count",
        "answer_claims_need_audit_count",
        "overstatement_warning_count",
        "local_path_leak_count",
        "raw_bytes_repr_count",
        "feedback_as_proof_count",
        "community_as_proof_count",
        "category_as_proof_count",
        "retrieval_only_as_proof_count",
        "answer_critic_can_answer_directly_count",
        "answer_critic_can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key)}")
    out_dir = Path(args.output_dir)
    print(f" report_path: {out_dir / DEFAULT_OUTPUT_FILE}")
    print(f" quality_path: {out_dir / DEFAULT_QUALITY_FILE}")
    return 0 if report.get("quality_status") == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
