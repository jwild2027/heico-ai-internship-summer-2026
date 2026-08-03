"""TRACE-Net Ask API Final Return Policy v2.1.

Read-only policy layer that decides whether the Ask API may return a dynamic
final answer or must return an audit/retrieval-only response.

Safety contract:
- The policy is a controller, not evidence.
- It cannot answer directly or prove claims.
- It cannot mutate source truth.
- A final answer may be returned only when dynamic final gate, retrieval critic,
  evidence sufficiency critic, and answer claim critic all agree and hard safety
  counters are zero.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence
from urllib.parse import urlparse

SCHEMA_VERSION = "trace_net_ask_api_final_return_policy_v21"
DEFAULT_MODEL_NAME = "trace-net-final-return-policy-v2.1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/ask_api_final_return_policy_v21")
DEFAULT_PORT = 8014

LOCAL_PATH_PATTERN = re.compile(
    r"(?:[A-Za-z]:\\\\|[A-Za-z]:/|/mnt/|/home/|local_data[\\/]|\\\\Users\\\\|/Users/)",
    re.IGNORECASE,
)
RAW_BYTES_PATTERN = re.compile(r"b['\"]|\\x[0-9a-fA-F]{2}")

RETRIEVAL_OK_STATUSES = {
    "final_gate_already_authorized",
    "retrieval_consistent_final_gate_authorized",
    "final_gate_authorized_retrieval_consistent",
}
RETRIEVAL_AUDIT_STATUSES = {
    "dynamic_final_gate_needs_audit",
    "retrieval_only_not_answer_ready",
    "needs_exact_search",
    "needs_semantic_expansion",
    "strong_enough_for_final_gate_attempt",
}
EVIDENCE_OK_STATUSES = {
    "final_artifact_evidence_sufficient",
    "final_evidence_sufficient",
}
EVIDENCE_AUDIT_STATUSES = {
    "final_evidence_sufficient_but_retrieval_audit_required",
    "final_gate_claims_need_audit",
    "sufficient_for_final_gate_attempt",
}
ANSWER_OK_STATUSES = {
    "final_artifact_answer_claims_clear",
    "answer_claims_clear_for_return",
}
ANSWER_AUDIT_STATUSES = {
    "answer_claims_need_audit",
    "answer_claims_clear_but_audit_required",
}

HARD_ZERO_COUNTER_KEYS = [
    "local_path_leak_count",
    "raw_bytes_repr_count",
    "feedback_as_proof_count",
    "community_as_proof_count",
    "category_as_proof_count",
    "retrieval_only_as_proof_count",
    "retrieval_only_final_claim_count",
    "uncited_final_claim_count",
    "retrieval_only_answer_allowed_count",
    "source_truth_mutation_allowed_count",
    "unsafe_group_count",
    "unsafe_critic_record_count",
    "unsafe_sufficiency_record_count",
    "unsafe_answer_claim_record_count",
    "answer_critic_can_answer_directly_count",
    "answer_critic_can_prove_claims_count",
    "sufficiency_can_answer_directly_count",
    "sufficiency_can_prove_claims_count",
    "critic_can_answer_directly_count",
    "critic_can_prove_claims_count",
]


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def stable_id(prefix: str, *parts: Any) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(str(part).encode("utf-8", errors="replace"))
        h.update(b"\0")
    return f"{prefix}__{h.hexdigest()[:16]}"


def normalize_query(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def read_json(path: Optional[Path | str]) -> dict[str, Any]:
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


def write_json(path: Path | str, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path | str, rows: Iterable[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


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
        v = value.strip().lower()
        if v in {"1", "true", "yes", "y", "pass", "allowed"}:
            return True
        if v in {"0", "false", "no", "n", "fail", "blocked"}:
            return False
    return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str) and value.strip():
            return int(float(value.strip()))
    except Exception:
        return default
    return default


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def get_summary(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    summary = payload.get("summary")
    return summary if isinstance(summary, Mapping) else {}


def get_quality_status(payload: Mapping[str, Any]) -> str:
    for source in (payload, get_summary(payload)):
        for key in ("quality_status", "status"):
            value = as_text(source.get(key)).upper()
            if value in {"PASS", "FAIL", "ERROR"}:
                return value
    return ""


def record_get(record: Mapping[str, Any], key: str, default: Any = None) -> Any:
    if key in record:
        return record.get(key)
    summary = record.get("summary")
    if isinstance(summary, Mapping) and key in summary:
        return summary.get(key)
    return default


def count_value(record: Mapping[str, Any], key: str) -> int:
    return as_int(record_get(record, key, 0))


def contains_local_path_or_raw_bytes(text: str) -> dict[str, int]:
    return {
        "local_path_leak_count": len(LOCAL_PATH_PATTERN.findall(text or "")),
        "raw_bytes_repr_count": len(RAW_BYTES_PATTERN.findall(text or "")),
    }


def sanitize_for_user(text: str, max_chars: int = 12000) -> tuple[str, dict[str, int]]:
    text = text or ""
    counts = contains_local_path_or_raw_bytes(text)
    text = LOCAL_PATH_PATTERN.sub("[redacted-local-path]", text)
    text = RAW_BYTES_PATTERN.sub("[redacted-bytes]", text)
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n\n[truncated by TRACE-Net final return policy v2.1]"
    return text, counts


def source_quality(payload: Mapping[str, Any]) -> str:
    return get_quality_status(payload)


def index_records_by_query(records: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for record in records:
        query = as_text(record.get("query"))
        if query:
            result[normalize_query(query)] = record
    return result


def dynamic_records(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    for key in ("query_results", "results", "records"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, Mapping)]
    return []


def retrieval_records(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = payload.get("critic_records")
    return [r for r in rows if isinstance(r, Mapping)] if isinstance(rows, list) else []


def sufficiency_records(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = payload.get("sufficiency_records")
    return [r for r in rows if isinstance(r, Mapping)] if isinstance(rows, list) else []


def answer_records(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = payload.get("answer_critic_records")
    return [r for r in rows if isinstance(r, Mapping)] if isinstance(rows, list) else []


def summarize_groups_from_dynamic(record: Mapping[str, Any], max_groups: int = 8) -> str:
    groups = as_list(record.get("ranked_groups"))
    if not groups:
        groups = as_list(record.get("top_groups"))
    lines: list[str] = []
    for group in groups[:max_groups]:
        if not isinstance(group, Mapping):
            continue
        rank = group.get("hybrid_v2_rank") or group.get("rank") or len(lines) + 1
        page_id = as_text(group.get("page_id")) or as_text(group.get("source_page_id")) or "unknown-page"
        score = group.get("hybrid_v2_score") or group.get("score") or ""
        exact = group.get("exact_hit_count", 0)
        semantic = group.get("semantic_group_count", group.get("semantic_count", 0))
        parts = as_list(group.get("part_numbers"))[:3]
        categories = as_list(group.get("category_labels"))[:2]
        lines.append(
            f"- rank {rank}: {page_id}; score={score}; exact={exact}; semantic={semantic}; categories={categories}; parts={parts}"
        )
    return "\n".join(lines)


def get_dynamic_answer_text(record: Mapping[str, Any]) -> str:
    for key in ("final_answer_text", "answer_text", "answer_markdown", "final_answer_markdown"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def hard_safety_counters(*records: Optional[Mapping[str, Any]]) -> dict[str, int]:
    counters = {key: 0 for key in HARD_ZERO_COUNTER_KEYS}
    for record in records:
        if not isinstance(record, Mapping):
            continue
        for key in HARD_ZERO_COUNTER_KEYS:
            counters[key] += count_value(record, key)
        if as_bool(record.get("source_truth_mutation_allowed"), False):
            counters["source_truth_mutation_allowed_count"] += 1
        if as_bool(record.get("can_mutate_source_truth"), False):
            counters["source_truth_mutation_allowed_count"] += 1
        if as_bool(record.get("can_answer_directly"), False):
            # Critics/controllers must not be answer-capable evidence.
            if "answer_critic" in record or "critic_status" in record or "evidence_sufficiency_status" in record:
                counters["answer_critic_can_answer_directly_count"] += 1
        if as_bool(record.get("can_prove_claims"), False):
            if "answer_critic" in record or "critic_status" in record or "evidence_sufficiency_status" in record:
                counters["answer_critic_can_prove_claims_count"] += 1
    return counters


def zero_counter_violations(counters: Mapping[str, int]) -> list[str]:
    return [key for key, value in counters.items() if as_int(value) > 0]


@dataclass(frozen=True)
class FinalReturnPolicyConfig:
    dynamic_final_gate: Optional[Path] = None
    retrieval_critic: Optional[Path] = None
    evidence_sufficiency_critic: Optional[Path] = None
    answer_claim_critic: Optional[Path] = None
    ask_api_dynamic: Optional[Path] = None
    output_dir: Path = DEFAULT_OUTPUT_DIR
    model_name: str = DEFAULT_MODEL_NAME
    api_key: str = ""
    max_groups: int = 8


def build_policy_record(
    query: str,
    dynamic_record: Optional[Mapping[str, Any]],
    retrieval_record: Optional[Mapping[str, Any]],
    sufficiency_record: Optional[Mapping[str, Any]],
    answer_record: Optional[Mapping[str, Any]],
    *,
    model_name: str = DEFAULT_MODEL_NAME,
    max_groups: int = 8,
) -> dict[str, Any]:
    dynamic_record = dynamic_record or {}
    retrieval_record = retrieval_record or {}
    sufficiency_record = sufficiency_record or {}
    answer_record = answer_record or {}

    retrieval_status = as_text(retrieval_record.get("critic_status"))
    evidence_status = as_text(sufficiency_record.get("evidence_sufficiency_status"))
    answer_critic_status = as_text(answer_record.get("answer_claim_critic_status"))
    dynamic_status = as_text(dynamic_record.get("answer_status"))
    dynamic_allowed = as_bool(dynamic_record.get("final_answer_allowed"), False)
    dynamic_answer_text = get_dynamic_answer_text(dynamic_record)
    safe_text, text_safety = sanitize_for_user(dynamic_answer_text)

    counters = hard_safety_counters(dynamic_record, retrieval_record, sufficiency_record, answer_record)
    counters["local_path_leak_count"] += text_safety["local_path_leak_count"]
    counters["raw_bytes_repr_count"] += text_safety["raw_bytes_repr_count"]
    hard_violations = zero_counter_violations(counters)

    reason_codes: list[str] = []
    warning_codes: list[str] = []

    retrieval_ok = retrieval_status in RETRIEVAL_OK_STATUSES
    retrieval_audit = retrieval_status in RETRIEVAL_AUDIT_STATUSES or "audit" in retrieval_status
    evidence_ok = evidence_status in EVIDENCE_OK_STATUSES
    evidence_audit = evidence_status in EVIDENCE_AUDIT_STATUSES or "audit" in evidence_status
    answer_ok = answer_critic_status in ANSWER_OK_STATUSES
    answer_audit = answer_critic_status in ANSWER_AUDIT_STATUSES or "audit" in answer_critic_status

    if not dynamic_record:
        reason_codes.append("missing_dynamic_final_gate_record")
    if not retrieval_record:
        reason_codes.append("missing_retrieval_critic_record")
    if not sufficiency_record:
        reason_codes.append("missing_evidence_sufficiency_record")
    if not answer_record:
        reason_codes.append("missing_answer_claim_critic_record")
    if hard_violations:
        reason_codes.extend([f"hard_safety_counter_nonzero:{key}" for key in hard_violations])

    final_answer_return_allowed = False
    final_answer_withheld = False
    policy_status = ""
    required_action = ""
    user_response_text = ""

    if hard_violations:
        policy_status = "FINAL_ANSWER_BLOCKED_UNSAFE"
        required_action = "block_and_repair_safety_counters"
        final_answer_withheld = True
        user_response_text = (
            "TRACE-Net blocked this answer because one or more hard safety counters were nonzero. "
            "Repair the source artifact or critic record before returning an answer."
        )
    elif dynamic_allowed and retrieval_ok and evidence_ok and answer_ok and safe_text:
        policy_status = "FINAL_ANSWER_RETURN_ALLOWED"
        required_action = "return_final_answer"
        final_answer_return_allowed = True
        reason_codes.append("dynamic_final_gate_and_all_critics_clear")
        user_response_text = safe_text
    elif dynamic_allowed and (retrieval_audit or evidence_audit or answer_audit):
        policy_status = "FINAL_ANSWER_AUDIT_REQUIRED"
        required_action = "audit_before_returning_final_answer"
        final_answer_withheld = True
        reason_codes.append("one_or_more_critics_require_audit")
        if retrieval_audit:
            warning_codes.append("retrieval_critic_requires_audit")
        if evidence_audit:
            warning_codes.append("evidence_sufficiency_requires_audit")
        if answer_audit:
            warning_codes.append("answer_claim_critic_requires_audit")
        user_response_text = (
            "TRACE-Net found citation/authority-backed candidate answer material, but the critic stack requires audit "
            "before returning it as a final answer. Review retrieval consistency, evidence sufficiency, and answer-claim "
            "critic records for this query."
        )
    elif dynamic_allowed:
        policy_status = "FINAL_ANSWER_AUDIT_REQUIRED"
        required_action = "audit_unclear_policy_state_before_returning_answer"
        final_answer_withheld = True
        reason_codes.append("dynamic_final_gate_allowed_but_critic_state_not_clear")
        user_response_text = (
            "TRACE-Net final gate reported an allowed result, but the return policy could not confirm that all critics "
            "were clear. Audit required before returning a final answer."
        )
    else:
        group_count = as_int(dynamic_record.get("retrieval_group_count", dynamic_record.get("ranked_group_count", 0)))
        if group_count <= 0:
            group_count = as_int(dynamic_record.get("exact_hit_group_count", 0)) + as_int(dynamic_record.get("semantic_group_count", 0))
        if group_count > 0:
            policy_status = "RETRIEVAL_ONLY_FINAL_GATE_REQUIRED"
            required_action = "return_retrieval_groups_and_run_final_gate"
            final_answer_withheld = True
            reason_codes.append("retrieval_groups_present_but_final_answer_not_allowed")
            groups_text = summarize_groups_from_dynamic(dynamic_record, max_groups=max_groups)
            user_response_text = (
                "TRACE-Net found candidate retrieval groups, but no final answer is authorized for this query. "
                "Run the final-gate and critic pipeline before returning a final answer."
            )
            if groups_text:
                user_response_text += "\n\nCandidate retrieval groups:\n" + groups_text
        else:
            policy_status = "NO_SAFE_ANSWER_AVAILABLE"
            required_action = "abstain_or_retrieve_more"
            final_answer_withheld = True
            reason_codes.append("no_final_answer_and_no_retrieval_groups")
            user_response_text = "TRACE-Net did not find enough safe evidence to return an answer. Retrieve more evidence or abstain."

    return {
        "policy_record_id": stable_id("askretpol", SCHEMA_VERSION, query),
        "schema_version": SCHEMA_VERSION,
        "query": query,
        "normalized_query": normalize_query(query),
        "model_name": model_name,
        "policy_status": policy_status,
        "required_action": required_action,
        "final_answer_return_allowed": final_answer_return_allowed,
        "final_answer_withheld": final_answer_withheld,
        "policy_response_text": user_response_text,
        "reason_codes": sorted(set(reason_codes)),
        "warning_codes": sorted(set(warning_codes)),
        "dynamic_final_gate_status": dynamic_status,
        "dynamic_final_answer_allowed": dynamic_allowed,
        "dynamic_final_claim_count": as_int(dynamic_record.get("final_claim_count", 0)),
        "dynamic_blocked_claim_count": as_int(dynamic_record.get("blocked_claim_count", 0)),
        "retrieval_critic_status": retrieval_status,
        "retrieval_critic_action": as_text(retrieval_record.get("recommended_next_action")),
        "evidence_sufficiency_status": evidence_status,
        "evidence_sufficiency_action": as_text(sufficiency_record.get("recommended_next_action")),
        "answer_claim_critic_status": answer_critic_status,
        "answer_claim_critic_action": as_text(answer_record.get("recommended_next_action")),
        "retrieval_group_count": as_int(dynamic_record.get("retrieval_group_count", dynamic_record.get("ranked_group_count", 0))),
        "exact_hit_group_count": as_int(dynamic_record.get("exact_hit_group_count", 0)),
        "semantic_group_count": as_int(dynamic_record.get("semantic_group_count", 0)),
        "answer_support_group_count": as_int(retrieval_record.get("answer_support_group_count", 0)),
        "retrieval_only_group_count": as_int(retrieval_record.get("retrieval_only_group_count", 0)),
        "hard_safety_counters": counters,
        "hard_safety_violation_count": len(hard_violations),
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
        "feedback_as_proof_count": counters.get("feedback_as_proof_count", 0),
        "community_as_proof_count": counters.get("community_as_proof_count", 0),
        "category_as_proof_count": counters.get("category_as_proof_count", 0),
        "retrieval_only_as_proof_count": counters.get("retrieval_only_as_proof_count", 0),
        "retrieval_only_answer_allowed_count": counters.get("retrieval_only_answer_allowed_count", 0),
        "source_truth_mutation_allowed_count": counters.get("source_truth_mutation_allowed_count", 0),
        "local_path_leak_count": counters.get("local_path_leak_count", 0),
        "raw_bytes_repr_count": counters.get("raw_bytes_repr_count", 0),
    }


def build_final_return_policy(config: FinalReturnPolicyConfig) -> dict[str, Any]:
    dynamic_payload = read_json(config.dynamic_final_gate)
    retrieval_payload = read_json(config.retrieval_critic)
    sufficiency_payload = read_json(config.evidence_sufficiency_critic)
    answer_payload = read_json(config.answer_claim_critic)
    ask_payload = read_json(config.ask_api_dynamic)

    dynamic_by_q = index_records_by_query(dynamic_records(dynamic_payload))
    retrieval_by_q = index_records_by_query(retrieval_records(retrieval_payload))
    suff_by_q = index_records_by_query(sufficiency_records(sufficiency_payload))
    answer_by_q = index_records_by_query(answer_records(answer_payload))

    normalized_queries = sorted(set(dynamic_by_q) | set(retrieval_by_q) | set(suff_by_q) | set(answer_by_q))
    records: list[dict[str, Any]] = []
    for nq in normalized_queries:
        query = ""
        for source in (dynamic_by_q, retrieval_by_q, suff_by_q, answer_by_q):
            if nq in source and as_text(source[nq].get("query")):
                query = as_text(source[nq].get("query"))
                break
        query = query or nq
        records.append(
            build_policy_record(
                query,
                dynamic_by_q.get(nq),
                retrieval_by_q.get(nq),
                suff_by_q.get(nq),
                answer_by_q.get(nq),
                model_name=config.model_name,
                max_groups=config.max_groups,
            )
        )

    final_answer_return_allowed_count = sum(1 for r in records if r["final_answer_return_allowed"])
    audit_required_count = sum(1 for r in records if r["policy_status"] == "FINAL_ANSWER_AUDIT_REQUIRED")
    retrieval_only_count = sum(1 for r in records if r["policy_status"] == "RETRIEVAL_ONLY_FINAL_GATE_REQUIRED")
    blocked_unsafe_count = sum(1 for r in records if r["policy_status"] == "FINAL_ANSWER_BLOCKED_UNSAFE")
    no_safe_answer_count = sum(1 for r in records if r["policy_status"] == "NO_SAFE_ANSWER_AVAILABLE")
    hard_safety_violation_count = sum(as_int(r["hard_safety_violation_count"]) for r in records)

    unsafe_return_allowed_count = sum(
        1
        for r in records
        if r["final_answer_return_allowed"] and (
            r["policy_status"] != "FINAL_ANSWER_RETURN_ALLOWED" or as_int(r["hard_safety_violation_count"]) > 0
        )
    )
    audit_return_allowed_count = sum(
        1 for r in records if r["final_answer_return_allowed"] and "AUDIT" in r["policy_status"]
    )

    source_quality_statuses = {
        "dynamic_final_gate": source_quality(dynamic_payload),
        "retrieval_critic": source_quality(retrieval_payload),
        "evidence_sufficiency_critic": source_quality(sufficiency_payload),
        "answer_claim_critic": source_quality(answer_payload),
        "ask_api_dynamic": source_quality(ask_payload),
    }

    summary = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": "trace_net_ask_api_conservative_final_return_policy_v21",
        "status": "PASS",
        "query_count": len(records),
        "policy_record_count": len(records),
        "final_answer_return_allowed_count": final_answer_return_allowed_count,
        "audit_required_count": audit_required_count,
        "retrieval_only_final_gate_required_count": retrieval_only_count,
        "blocked_unsafe_count": blocked_unsafe_count,
        "no_safe_answer_count": no_safe_answer_count,
        "hard_safety_violation_count": hard_safety_violation_count,
        "unsafe_return_allowed_count": unsafe_return_allowed_count,
        "audit_return_allowed_count": audit_return_allowed_count,
        "policy_status_counts": count_by(records, "policy_status"),
        "required_action_counts": count_by(records, "required_action"),
        "source_quality_statuses": source_quality_statuses,
        "dynamic_final_gate_quality_status": source_quality_statuses["dynamic_final_gate"],
        "retrieval_critic_quality_status": source_quality_statuses["retrieval_critic"],
        "evidence_sufficiency_quality_status": source_quality_statuses["evidence_sufficiency_critic"],
        "answer_claim_critic_quality_status": source_quality_statuses["answer_claim_critic"],
        "read_only_policy": True,
        "can_answer_directly_count": sum(1 for r in records if as_bool(r.get("can_answer_directly"), False)),
        "can_prove_claims_count": sum(1 for r in records if as_bool(r.get("can_prove_claims"), False)),
        "source_truth_mutation_allowed_count": sum(as_int(r.get("source_truth_mutation_allowed_count", 0)) for r in records),
        "feedback_as_proof_count": sum(as_int(r.get("feedback_as_proof_count", 0)) for r in records),
        "community_as_proof_count": sum(as_int(r.get("community_as_proof_count", 0)) for r in records),
        "category_as_proof_count": sum(as_int(r.get("category_as_proof_count", 0)) for r in records),
        "retrieval_only_as_proof_count": sum(as_int(r.get("retrieval_only_as_proof_count", 0)) for r in records),
        "retrieval_only_answer_allowed_count": sum(as_int(r.get("retrieval_only_answer_allowed_count", 0)) for r in records),
        "local_path_leak_count": sum(as_int(r.get("local_path_leak_count", 0)) for r in records),
        "raw_bytes_repr_count": sum(as_int(r.get("raw_bytes_repr_count", 0)) for r in records),
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "source_truth_mutations_performed": 0,
    }

    if unsafe_return_allowed_count or audit_return_allowed_count or hard_safety_violation_count:
        summary["status"] = "FAIL"
    if summary["can_answer_directly_count"] or summary["can_prove_claims_count"] or summary["source_truth_mutation_allowed_count"]:
        summary["status"] = "FAIL"

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ASK_API_FINAL_RETURN_POLICY_BUILT",
        "quality_status": summary["status"],
        "generated_at": utc_now(),
        "model_name": config.model_name,
        "read_only_policy": True,
        "source_artifacts": {
            "dynamic_final_gate": str(config.dynamic_final_gate or ""),
            "retrieval_critic": str(config.retrieval_critic or ""),
            "evidence_sufficiency_critic": str(config.evidence_sufficiency_critic or ""),
            "answer_claim_critic": str(config.answer_claim_critic or ""),
            "ask_api_dynamic": str(config.ask_api_dynamic or ""),
        },
        "summary": summary,
        "policy_records": records,
    }


def count_by(records: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = as_text(record.get(key)) or "unknown"
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def quality_report(
    report: Mapping[str, Any],
    *,
    min_policy_records: int = 1,
    min_queries: int = 1,
    min_return_allowed: int = 0,
    require_dynamic_final_gate_quality_pass: bool = False,
    require_retrieval_critic_quality_pass: bool = False,
    require_evidence_sufficiency_quality_pass: bool = False,
    require_answer_claim_critic_quality_pass: bool = False,
) -> dict[str, Any]:
    summary = get_summary(report)
    issue_records: list[dict[str, Any]] = []

    def add_issue(code: str, message: str) -> None:
        issue_records.append({"issue_code": code, "message": message})

    policy_record_count = as_int(summary.get("policy_record_count", 0))
    query_count = as_int(summary.get("query_count", 0))
    final_answer_return_allowed_count = as_int(summary.get("final_answer_return_allowed_count", 0))

    if policy_record_count < min_policy_records:
        add_issue("min_policy_records_not_met", f"policy_record_count {policy_record_count} < {min_policy_records}")
    if query_count < min_queries:
        add_issue("min_queries_not_met", f"query_count {query_count} < {min_queries}")
    if final_answer_return_allowed_count < min_return_allowed:
        add_issue("min_return_allowed_not_met", f"final_answer_return_allowed_count {final_answer_return_allowed_count} < {min_return_allowed}")

    for key in [
        "unsafe_return_allowed_count",
        "audit_return_allowed_count",
        "hard_safety_violation_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "feedback_as_proof_count",
        "community_as_proof_count",
        "category_as_proof_count",
        "retrieval_only_as_proof_count",
        "retrieval_only_answer_allowed_count",
        "local_path_leak_count",
        "raw_bytes_repr_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        if as_int(summary.get(key, 0)) != 0:
            add_issue(f"{key}_must_be_zero", f"{key} = {summary.get(key)}")

    source_statuses = summary.get("source_quality_statuses") if isinstance(summary.get("source_quality_statuses"), Mapping) else {}
    quality_requirements = {
        "dynamic_final_gate": require_dynamic_final_gate_quality_pass,
        "retrieval_critic": require_retrieval_critic_quality_pass,
        "evidence_sufficiency_critic": require_evidence_sufficiency_quality_pass,
        "answer_claim_critic": require_answer_claim_critic_quality_pass,
    }
    for source_name, required in quality_requirements.items():
        if required and as_text(source_statuses.get(source_name)).upper() != "PASS":
            add_issue("source_quality_not_pass", f"{source_name} quality status is {source_statuses.get(source_name)!r}")

    status = "PASS" if not issue_records else "FAIL"
    return {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": status,
        "quality_status": status,
        "checked_at": utc_now(),
        "policy_record_count": policy_record_count,
        "query_count": query_count,
        "final_answer_return_allowed_count": final_answer_return_allowed_count,
        "audit_required_count": as_int(summary.get("audit_required_count", 0)),
        "retrieval_only_final_gate_required_count": as_int(summary.get("retrieval_only_final_gate_required_count", 0)),
        "unsafe_return_allowed_count": as_int(summary.get("unsafe_return_allowed_count", 0)),
        "audit_return_allowed_count": as_int(summary.get("audit_return_allowed_count", 0)),
        "hard_safety_violation_count": as_int(summary.get("hard_safety_violation_count", 0)),
        "source_truth_mutation_allowed_count": as_int(summary.get("source_truth_mutation_allowed_count", 0)),
        "feedback_as_proof_count": as_int(summary.get("feedback_as_proof_count", 0)),
        "community_as_proof_count": as_int(summary.get("community_as_proof_count", 0)),
        "category_as_proof_count": as_int(summary.get("category_as_proof_count", 0)),
        "retrieval_only_as_proof_count": as_int(summary.get("retrieval_only_as_proof_count", 0)),
        "issue_count": len(issue_records),
        "issues": issue_records,
    }


def write_outputs(report: Mapping[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_ask_api_final_return_policy_v21.json"
    records_path = output_dir / "trace_net_ask_api_final_return_policy_v21_records.jsonl"
    summary_path = output_dir / "trace_net_ask_api_final_return_policy_v21_summary.json"
    quality_path = output_dir / "trace_net_ask_api_final_return_policy_v21_quality.json"
    manifest_path = output_dir / "trace_net_ask_api_final_return_policy_v21_manifest.json"
    md_path = output_dir / "trace_net_ask_api_final_return_policy_v21.md"
    html_path = output_dir / "trace_net_ask_api_final_return_policy_v21.html"

    write_json(report_path, report)
    write_jsonl(records_path, report.get("policy_records", []))
    write_json(summary_path, report.get("summary", {}))
    quality = quality_report(report)
    write_json(quality_path, quality)
    manifest = {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": utc_now(),
        "report_path": str(report_path),
        "records_path": str(records_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
    }
    write_json(manifest_path, manifest)

    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# TRACE-Net Ask API Final Return Policy v2.1",
        "",
        f"**Status:** {report.get('quality_status', '')}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "policy_record_count",
        "final_answer_return_allowed_count",
        "audit_required_count",
        "retrieval_only_final_gate_required_count",
        "blocked_unsafe_count",
        "unsafe_return_allowed_count",
        "hard_safety_violation_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key, 0)}")
    lines.append("")
    lines.append("## Policy Records")
    lines.append("")
    for record in report.get("policy_records", [])[:20]:
        lines.append(f"- **{record.get('policy_status')}** `{record.get('query')}` -> {record.get('required_action')}")
    md = "\n".join(lines) + "\n"
    md_path.write_text(md, encoding="utf-8")
    html_path.write_text("<html><body><pre>" + md.replace("&", "&amp;").replace("<", "&lt;") + "</pre></body></html>", encoding="utf-8")

    return {
        "report_path": str(report_path),
        "records_path": str(records_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "manifest_path": str(manifest_path),
        "md_path": str(md_path),
        "html_path": str(html_path),
    }


class FinalReturnPolicyServer:
    def __init__(self, report: Mapping[str, Any], *, model_name: str = DEFAULT_MODEL_NAME, api_key: str = "") -> None:
        self.report = report
        self.model_name = model_name
        self.api_key = api_key
        self.records = {
            normalize_query(as_text(r.get("query"))): r
            for r in report.get("policy_records", [])
            if isinstance(r, Mapping) and as_text(r.get("query"))
        }

    def find_record(self, query: str) -> Optional[Mapping[str, Any]]:
        return self.records.get(normalize_query(query))

    def build_trace_response(self, query: str) -> dict[str, Any]:
        record = self.find_record(query)
        if record is None:
            text = (
                "TRACE-Net final return policy has no prebuilt policy record for this query. "
                "Run Hybrid Retrieval v2, Dynamic Final-Gate Execution, and the critic stack before returning an answer."
            )
            return {
                "schema_version": SCHEMA_VERSION,
                "status": "ASK_API_FINAL_RETURN_POLICY_RESPONSE_BUILT",
                "quality_status": "PASS",
                "query": query,
                "model": self.model_name,
                "answer_text": text,
                "trace_net": {
                    "schema_version": SCHEMA_VERSION,
                    "query": query,
                    "policy_status": "POLICY_RECORD_NOT_FOUND",
                    "required_action": "run_dynamic_retrieval_and_critics",
                    "final_answer_return_allowed": False,
                    "can_answer_directly": False,
                    "can_prove_claims": False,
                    "source_truth_mutation_allowed": False,
                },
            }
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "ASK_API_FINAL_RETURN_POLICY_RESPONSE_BUILT",
            "quality_status": "PASS",
            "query": query,
            "model": self.model_name,
            "answer_text": record.get("policy_response_text", ""),
            "trace_net": {
                "schema_version": SCHEMA_VERSION,
                "query": query,
                "policy_status": record.get("policy_status"),
                "required_action": record.get("required_action"),
                "final_answer_return_allowed": record.get("final_answer_return_allowed"),
                "final_answer_withheld": record.get("final_answer_withheld"),
                "retrieval_critic_status": record.get("retrieval_critic_status"),
                "evidence_sufficiency_status": record.get("evidence_sufficiency_status"),
                "answer_claim_critic_status": record.get("answer_claim_critic_status"),
                "dynamic_final_gate_status": record.get("dynamic_final_gate_status"),
                "reason_codes": record.get("reason_codes", []),
                "warning_codes": record.get("warning_codes", []),
                "hard_safety_violation_count": record.get("hard_safety_violation_count", 0),
                "can_answer_directly": False,
                "can_prove_claims": False,
                "can_mutate_source_truth": False,
                "source_truth_mutation_allowed": False,
                "feedback_as_proof_count": record.get("feedback_as_proof_count", 0),
                "community_as_proof_count": record.get("community_as_proof_count", 0),
                "category_as_proof_count": record.get("category_as_proof_count", 0),
                "retrieval_only_as_proof_count": record.get("retrieval_only_as_proof_count", 0),
                "source_truth_mutation_allowed_count": record.get("source_truth_mutation_allowed_count", 0),
            },
        }


def create_handler(server_state: FinalReturnPolicyServer):
    class Handler(BaseHTTPRequestHandler):
        server_version = "TraceNetAskFinalReturnPolicyV21/1.0"

        def _json(self, status_code: int, payload: Mapping[str, Any]) -> None:
            data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _auth_ok(self) -> bool:
            if not server_state.api_key:
                return True
            header = self.headers.get("Authorization", "")
            return header == f"Bearer {server_state.api_key}" or self.headers.get("X-API-Key") == server_state.api_key

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/health":
                self._json(200, {"status": "ok", "schema_version": SCHEMA_VERSION, "service": "TRACE-Net Ask API Final Return Policy v2.1", "read_only": True})
            elif path == "/v1/models":
                self._json(200, {"object": "list", "data": [{"id": server_state.model_name, "object": "model", "owned_by": "trace-net"}]})
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if not self._auth_ok():
                self._json(401, {"error": "unauthorized"})
                return
            path = urlparse(self.path).path
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except Exception:
                self._json(400, {"error": "invalid json"})
                return
            query = ""
            if path == "/api/trace-net/ask":
                query = as_text(body.get("query"))
            elif path == "/v1/chat/completions":
                messages = body.get("messages") if isinstance(body.get("messages"), list) else []
                for msg in reversed(messages):
                    if isinstance(msg, Mapping) and as_text(msg.get("role")) == "user":
                        query = as_text(msg.get("content"))
                        break
                if not query and messages and isinstance(messages[-1], Mapping):
                    query = as_text(messages[-1].get("content"))
            else:
                self._json(404, {"error": "not found"})
                return
            if not query:
                self._json(400, {"error": "query is required"})
                return
            response = server_state.build_trace_response(query)
            if path == "/v1/chat/completions":
                payload = {
                    "id": stable_id("chatcmpl", query, time.time()),
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": server_state.model_name,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": response["answer_text"]}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    "trace_net": response["trace_net"],
                }
                self._json(200, payload)
            else:
                self._json(200, response)

        def log_message(self, fmt: str, *args: Any) -> None:
            sys.stderr.write("TRACE-Net Ask final return policy: " + fmt % args + "\n")

    return Handler


def run_server(report: Mapping[str, Any], host: str, port: int, *, model_name: str, api_key: str) -> None:
    state = FinalReturnPolicyServer(report, model_name=model_name, api_key=api_key)
    httpd = ThreadingHTTPServer((host, port), create_handler(state))
    print("TRACE-Net Ask API Final Return Policy v2.1")
    print(" Status: SERVER_RUNNING")
    print(f" url: http://{host}:{port}/")
    print(f" model: {model_name}")
    print(" safety: final answer returned only when final gate and all critics agree")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        print("TRACE-Net Ask API Final Return Policy v2.1 stopped")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build or serve TRACE-Net Ask API Final Return Policy v2.1")
    parser.add_argument("--dynamic-final-gate", type=Path, default=Path("local_data/organization/trace_net/dynamic_final_gate_execution/trace_net_dynamic_final_gate_execution_v1.json"))
    parser.add_argument("--retrieval-critic", type=Path, default=Path("local_data/organization/trace_net/retrieval_critic/trace_net_retrieval_critic_v1.json"))
    parser.add_argument("--evidence-sufficiency-critic", type=Path, default=Path("local_data/organization/trace_net/evidence_sufficiency_critic/trace_net_evidence_sufficiency_critic_v1.json"))
    parser.add_argument("--answer-claim-critic", type=Path, default=Path("local_data/organization/trace_net/answer_claim_critic/trace_net_answer_claim_critic_v1.json"))
    parser.add_argument("--ask-api-dynamic", type=Path, default=Path("local_data/organization/trace_net/ask_api_dynamic_retrieval_v2/trace_net_ask_api_dynamic_retrieval_v2.json"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--max-groups", type=int, default=8)
    parser.add_argument("--min-policy-records", type=int, default=1)
    parser.add_argument("--min-queries", type=int, default=1)
    parser.add_argument("--min-return-allowed", type=int, default=0)
    parser.add_argument("--require-dynamic-final-gate-quality-pass", action="store_true")
    parser.add_argument("--require-retrieval-critic-quality-pass", action="store_true")
    parser.add_argument("--require-evidence-sufficiency-quality-pass", action="store_true")
    parser.add_argument("--require-answer-claim-critic-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--api-key", default="")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    config = FinalReturnPolicyConfig(
        dynamic_final_gate=args.dynamic_final_gate,
        retrieval_critic=args.retrieval_critic,
        evidence_sufficiency_critic=args.evidence_sufficiency_critic,
        answer_claim_critic=args.answer_claim_critic,
        ask_api_dynamic=args.ask_api_dynamic,
        output_dir=args.output_dir,
        model_name=args.model_name,
        api_key=args.api_key,
        max_groups=args.max_groups,
    )
    report = build_final_return_policy(config)
    paths = write_outputs(report, args.output_dir)
    q = quality_report(
        report,
        min_policy_records=args.min_policy_records,
        min_queries=args.min_queries,
        min_return_allowed=args.min_return_allowed,
        require_dynamic_final_gate_quality_pass=args.require_dynamic_final_gate_quality_pass,
        require_retrieval_critic_quality_pass=args.require_retrieval_critic_quality_pass,
        require_evidence_sufficiency_quality_pass=args.require_evidence_sufficiency_quality_pass,
        require_answer_claim_critic_quality_pass=args.require_answer_claim_critic_quality_pass,
    )
    write_json(paths["quality_path"], q)

    summary = report["summary"]
    print("TRACE-Net Ask API Final Return Policy v2.1")
    print(" Status: ASK_API_FINAL_RETURN_POLICY_BUILT")
    print(f" Quality status: {q['quality_status'] if args.quality else report['quality_status']}")
    for key in [
        "policy_record_count",
        "final_answer_return_allowed_count",
        "audit_required_count",
        "retrieval_only_final_gate_required_count",
        "unsafe_return_allowed_count",
        "hard_safety_violation_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key, 0)}")
    print(f" report_path: {paths['report_path']}")
    print(f" quality_path: {paths['quality_path']}")
    if args.quality and q["quality_status"] != "PASS":
        return 1
    if not args.build_only:
        run_server(report, args.host, args.port, model_name=args.model_name, api_key=args.api_key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
