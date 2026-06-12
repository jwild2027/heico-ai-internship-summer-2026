"""TRACE-Net Retrieval Critic v1.

This module adds the first safe Self-RAG-style critic layer to TRACE-Net.
It reads Hybrid Retrieval v2 results and emits read-only critic records that
judge retrieval readiness and recommend next actions.

Safety contract:
- The critic can recommend another retrieval/search/review/final-gate action.
- The critic cannot answer directly.
- The critic cannot prove claims.
- The critic cannot mutate source truth.
- Feedback, community, and category signals remain advisory only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "trace_net_retrieval_critic_v1"
ALGORITHM = "trace_net_read_only_self_rag_style_retrieval_critic_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/retrieval_critic")
DEFAULT_HYBRID_V2_REPORT = Path("local_data/organization/trace_net/hybrid_retrieval_v2/trace_net_hybrid_retrieval_v2.json")
DEFAULT_DYNAMIC_FINAL_GATE = Path("local_data/organization/trace_net/dynamic_final_gate_execution/trace_net_dynamic_final_gate_execution_v1.json")
DEFAULT_OPENSEARCH_ADAPTER = Path("local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_adapter_v1.json")
DEFAULT_CATEGORY_OVERLAY = Path("local_data/organization/trace_net/category_aware_leiden_overlay/trace_net_category_aware_leiden_overlay_v1.json")
DEFAULT_FEEDBACK_MEMORY = Path("local_data/organization/trace_net/feedback_memory/trace_net_feedback_memory_v1.json")
DEFAULT_OUTPUT_FILE = "trace_net_retrieval_critic_v1.json"
DEFAULT_RECORDS_FILE = "trace_net_retrieval_critic_v1_records.jsonl"
DEFAULT_SUMMARY_FILE = "trace_net_retrieval_critic_v1_summary.json"
DEFAULT_QUALITY_FILE = "trace_net_retrieval_critic_v1_quality.json"
DEFAULT_MANIFEST_FILE = "trace_net_retrieval_critic_v1_manifest.json"
DEFAULT_MARKDOWN_FILE = "trace_net_retrieval_critic_v1.md"
DEFAULT_HTML_FILE = "trace_net_retrieval_critic_v1.html"

PART_RE = re.compile(r"\b\d{2,4}-\d{2,6}-\d{2,4}\b")
ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
REVISION_RE = re.compile(r"\brev(?:ision)?\.?\s*\d+\b", re.I)
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "in", "is", "it", "of", "on", "or", "the", "this", "to", "what", "where", "which", "who", "with",
}
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./-]*")

ANSWER_SUPPORT_BUCKETS = {
    "source_text_evidence",
    "verified_part_evidence",
    "table_structured_evidence",
    "table_part_catalog_evidence",
    "clean_evidence_snippet",
}
RETRIEVAL_ONLY_BUCKETS = {
    "source_evidence",
    "derived_context",
    "context_retrieval_helper",
    "page_retrieval_profile",
    "community_retrieval_helper",
    "part_candidate_lineage",
    "table_cell_normalized",
    "table_row_normalized",
    "feedback_memory_advisory",
}
BANNED_BUCKET_TOKENS = {
    "raw_ocr",
    "raw_visual",
    "raw_table",
    "raw_feedback",
    "prompt",
    "debug",
    "unsafe",
    "excluded",
}
REVIEW_TOKENS = {"review", "unverified", "candidate", "callout", "visual", "diagram", "table_repair"}


class RetrievalCriticError(RuntimeError):
    """Raised when the retrieval critic cannot be built safely."""


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def read_json(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        value = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with p.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
            count += 1
    return count


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
        return int(value)
    except (TypeError, ValueError):
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
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


def tokenize(text: Any) -> list[str]:
    tokens = [m.group(0).lower() for m in TOKEN_RE.finditer(as_text(text))]
    return [t for t in tokens if len(t) > 1 and t not in STOPWORDS]


def detect_query_intent(query: str) -> str:
    query_text = as_text(query)
    if PART_RE.search(query_text):
        return "exact_part_number_lookup"
    if ATA_RE.search(query_text):
        return "exact_ata_code_lookup"
    if REVISION_RE.search(query_text):
        return "revision_lookup"
    lowered = query_text.lower()
    if "revision" in lowered or "record of revisions" in lowered:
        return "revision_history_lookup"
    if len(tokenize(query_text)) <= 2:
        return "short_exact_or_keyword_lookup"
    return "semantic_topic_lookup"




def dynamic_gate_authorization_state(dynamic_gate_result: Mapping[str, Any] | None) -> tuple[bool, list[str], dict[str, int]]:
    """Return whether a dynamic/final gate record is safe enough to return.

    The retrieval critic is advisory-only, but it should not blindly trust a
    `final_answer_allowed=true` flag if the query result lacks claim/citation
    evidence or still reports retrieval-only/uncited/source-truth issues.
    """
    if not dynamic_gate_result:
        return False, [], {
            "final_claim_count": 0,
            "uncited_final_claim_count": 0,
            "retrieval_only_final_claim_count": 0,
            "source_truth_mutation_allowed_count": 0,
        }

    final_claims = [c for c in as_list(dynamic_gate_result.get("final_claims")) if isinstance(c, Mapping)]
    final_claim_count = as_int(dynamic_gate_result.get("final_claim_count"), len(final_claims))
    if final_claim_count <= 0 and as_text(dynamic_gate_result.get("final_answer_text")):
        # Some final-gate artifacts store answer text but not claim objects in the
        # per-query record. Treat this as one output unit, but still require all
        # explicit safety counters to be clean.
        final_claim_count = 1

    counters = {
        "final_claim_count": final_claim_count,
        "uncited_final_claim_count": as_int(dynamic_gate_result.get("uncited_final_claim_count")),
        "retrieval_only_final_claim_count": as_int(dynamic_gate_result.get("retrieval_only_final_claim_count")),
        "source_truth_mutation_allowed_count": as_int(dynamic_gate_result.get("source_truth_mutation_allowed_count")),
        "feedback_as_proof_count": as_int(dynamic_gate_result.get("feedback_as_proof_count")),
        "community_as_proof_count": as_int(dynamic_gate_result.get("community_as_proof_count")),
        "category_as_proof_count": as_int(dynamic_gate_result.get("category_as_proof_count")),
        "local_path_leak_count": as_int(dynamic_gate_result.get("local_path_leak_count")),
        "raw_bytes_repr_count": as_int(dynamic_gate_result.get("raw_bytes_repr_count")),
    }

    reasons: list[str] = []
    if not as_bool(dynamic_gate_result.get("final_answer_allowed")):
        reasons.append("dynamic_final_gate_not_allowed")
    if counters["final_claim_count"] <= 0:
        reasons.append("dynamic_final_gate_missing_final_claims")
    if counters["uncited_final_claim_count"] > 0:
        reasons.append("dynamic_final_gate_uncited_claims_present")
    if counters["retrieval_only_final_claim_count"] > 0:
        reasons.append("dynamic_final_gate_retrieval_only_claims_present")
    if counters["source_truth_mutation_allowed_count"] > 0:
        reasons.append("dynamic_final_gate_source_truth_mutation_risk")
    if counters["feedback_as_proof_count"] > 0:
        reasons.append("dynamic_final_gate_feedback_as_proof")
    if counters["community_as_proof_count"] > 0:
        reasons.append("dynamic_final_gate_community_as_proof")
    if counters["category_as_proof_count"] > 0:
        reasons.append("dynamic_final_gate_category_as_proof")
    if counters["local_path_leak_count"] > 0:
        reasons.append("dynamic_final_gate_local_path_leak")
    if counters["raw_bytes_repr_count"] > 0:
        reasons.append("dynamic_final_gate_raw_bytes_leak")

    return not reasons, reasons, counters


def dynamic_gate_retrieval_consistency_reasons(
    *,
    intent: str,
    exact_group_count: int,
    semantic_group_count: int,
    ranked_group_count: int,
    answer_support_group_count: int,
    retrieval_only_group_count: int,
    dynamic_gate_result: Mapping[str, Any] | None,
) -> list[str]:
    """Return reasons a dynamic gate approval should be audited.

    This critic is intentionally more conservative than the dynamic gate. The
    dynamic gate may be allowed from its own page/citation/authority checks,
    but a Self-RAG-style retrieval critic should still ask whether the approval
    makes sense for the query and retrieval pattern.

    Final artifact answers are exempt because they already passed the earlier
    full final-gate artifact pipeline. Dynamic approvals for new queries must
    align with retrieval evidence shape.
    """
    if not dynamic_gate_result or not as_bool(dynamic_gate_result.get("final_answer_allowed")):
        return []

    status = as_text(dynamic_gate_result.get("answer_status"))
    if status == "FINAL_GATE_ARTIFACT_ANSWER":
        return []

    reasons: list[str] = []
    if status and status != "DYNAMIC_FINAL_GATE_APPROVED":
        reasons.append("dynamic_final_gate_unrecognized_answer_status")

    exact_intents = {"exact_part_number_lookup", "exact_ata_code_lookup", "short_exact_or_keyword_lookup"}
    if intent in exact_intents and exact_group_count <= 0:
        reasons.append("dynamic_final_gate_exact_query_missing_exact_hits")

    if intent in exact_intents | {"revision_lookup"} and answer_support_group_count <= 0:
        reasons.append("dynamic_final_gate_missing_answer_support_groups_for_exact_query")

    if ranked_group_count > 0 and answer_support_group_count <= 0 and retrieval_only_group_count >= ranked_group_count:
        reasons.append("dynamic_final_gate_retrieval_pattern_only_retrieval_groups")

    if intent in {"semantic_topic_lookup", "revision_history_lookup"} and exact_group_count <= 0 and semantic_group_count <= 0:
        reasons.append("dynamic_final_gate_topic_query_missing_semantic_or_exact_support")

    return unique_texts(reasons)


def get_dynamic_gate_by_query(dynamic_gate: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    results = dynamic_gate.get("query_results")
    if not isinstance(results, list):
        return {}
    by_query: dict[str, dict[str, Any]] = {}
    for result in results:
        if not isinstance(result, Mapping):
            continue
        query = as_text(result.get("query"))
        if query:
            by_query[query.lower()] = dict(result)
    return by_query


def bucket_counts(group: Mapping[str, Any]) -> Counter[str]:
    counts = Counter()
    value = group.get("bucket_counts") or group.get("rag_bucket_counts")
    if isinstance(value, Mapping):
        for key, count in value.items():
            counts[as_text(key)] += as_int(count, 1)
    for key in ("rag_bucket", "bucket"):
        text = as_text(group.get(key))
        if text:
            counts[text] += 1
    for doc in as_list(group.get("exact_hits")):
        if isinstance(doc, Mapping):
            text = as_text(doc.get("rag_bucket"))
            if text:
                counts[text] += 1
    return counts


def has_banned_bucket(group: Mapping[str, Any]) -> bool:
    for bucket in bucket_counts(group):
        lower = bucket.lower()
        if any(token in lower for token in BANNED_BUCKET_TOKENS):
            return True
    return False


def answer_support_like(group: Mapping[str, Any]) -> bool:
    if as_bool(group.get("answer_support_candidate")):
        return True
    if as_int(group.get("answer_support_record_count")) > 0:
        return True
    counts = bucket_counts(group)
    if any(bucket in ANSWER_SUPPORT_BUCKETS and counts[bucket] > 0 for bucket in counts):
        return True
    authorities = " ".join(as_text(x).lower() for x in as_list(group.get("authorities") or group.get("authority")))
    if "ocr_text_claim_with_citation" in authorities or "part_page_relationship" in authorities:
        return True
    return False


def review_signal_like(group: Mapping[str, Any]) -> bool:
    labels = " ".join(as_text(x).lower() for x in as_list(group.get("category_labels")))
    roles = " ".join(as_text(x).lower() for x in as_list(group.get("dominant_leiden_hint_families")))
    text = " ".join([labels, roles, as_text(group.get("page_category_label")).lower()])
    return any(token in text for token in REVIEW_TOKENS)


def group_is_unsafe(group: Mapping[str, Any]) -> bool:
    if as_bool(group.get("unsafe")) or as_int(group.get("unsafe_group_count")) > 0:
        return True
    if as_bool(group.get("source_truth_mutation_allowed")):
        return True
    if as_bool(group.get("can_mutate_source_truth")):
        return True
    if as_bool(group.get("feedback_as_proof")) or as_bool(group.get("community_as_proof")) or as_bool(group.get("category_as_proof")):
        return True
    if has_banned_bucket(group):
        return True
    return False


def collect_top_values(groups: Iterable[Mapping[str, Any]], key: str, limit: int = 10) -> list[str]:
    values: list[str] = []
    for group in groups:
        values.extend(as_text(v) for v in as_list(group.get(key)) if as_text(v))
    return unique_texts(values)[:limit]


def build_critic_record(query_result: Mapping[str, Any], dynamic_gate_result: Mapping[str, Any] | None = None) -> dict[str, Any]:
    query = as_text(query_result.get("query"))
    query_id = as_text(query_result.get("query_id")) or stable_hash(query)
    groups = [g for g in as_list(query_result.get("ranked_groups")) if isinstance(g, Mapping)]
    intent = detect_query_intent(query)

    exact_group_count = as_int(query_result.get("exact_hit_group_count"), sum(1 for g in groups if as_int(g.get("exact_hit_count")) > 0))
    semantic_group_count = as_int(query_result.get("semantic_group_count"), sum(1 for g in groups if as_int(g.get("semantic_group_count")) > 0 or as_int(g.get("semantic_hit_count")) > 0))
    ranked_group_count = as_int(query_result.get("ranked_group_count"), len(groups))

    unsafe_groups = [g for g in groups if group_is_unsafe(g)]
    answer_support_groups = [g for g in groups if answer_support_like(g) and not group_is_unsafe(g)]
    review_groups = [g for g in groups if review_signal_like(g)]
    retrieval_only_groups = [g for g in groups if not answer_support_like(g) and not group_is_unsafe(g)]

    dynamic_final_allowed_flag = bool(dynamic_gate_result and as_bool(dynamic_gate_result.get("final_answer_allowed")))
    dynamic_final_safe_to_return, dynamic_gate_block_reasons, dynamic_gate_counters = dynamic_gate_authorization_state(dynamic_gate_result)
    dynamic_answer_status = as_text(dynamic_gate_result.get("answer_status")) if dynamic_gate_result else ""
    dynamic_retrieval_consistency_reasons = dynamic_gate_retrieval_consistency_reasons(
        intent=intent,
        exact_group_count=exact_group_count,
        semantic_group_count=semantic_group_count,
        ranked_group_count=ranked_group_count,
        answer_support_group_count=len(answer_support_groups),
        retrieval_only_group_count=len(retrieval_only_groups),
        dynamic_gate_result=dynamic_gate_result,
    )

    reason_codes: list[str] = []
    recommended_action = ""
    critic_status = ""
    confidence = 0.0

    if dynamic_final_safe_to_return and not dynamic_retrieval_consistency_reasons:
        critic_status = "final_gate_already_authorized"
        recommended_action = "return_final_gate_answer"
        reason_codes.append("dynamic_final_gate_allowed_and_claim_safe")
        confidence = 0.95
    elif dynamic_final_safe_to_return and dynamic_retrieval_consistency_reasons:
        critic_status = "dynamic_final_gate_needs_audit"
        recommended_action = "audit_dynamic_final_gate_retrieval_consistency_before_returning_answer"
        reason_codes.extend(dynamic_retrieval_consistency_reasons)
        confidence = 0.92
    elif dynamic_final_allowed_flag and dynamic_gate_block_reasons:
        critic_status = "dynamic_final_gate_needs_audit"
        recommended_action = "audit_dynamic_final_gate_before_returning_answer"
        reason_codes.extend(dynamic_gate_block_reasons)
        confidence = 0.9
    elif ranked_group_count == 0:
        critic_status = "abstain_no_evidence"
        recommended_action = "abstain_or_expand_retrieval"
        reason_codes.append("no_retrieval_groups")
        confidence = 0.9
    elif unsafe_groups:
        critic_status = "unsafe_retrieval_blocked"
        recommended_action = "block_and_review_unsafe_retrieval"
        reason_codes.append("unsafe_retrieval_groups_present")
        confidence = 0.9
    elif intent in {"exact_part_number_lookup", "exact_ata_code_lookup", "revision_lookup", "short_exact_or_keyword_lookup"} and exact_group_count == 0:
        critic_status = "needs_exact_search"
        recommended_action = "run_or_expand_exact_search"
        reason_codes.append("exact_identifier_query_without_exact_hits")
        confidence = 0.85
    elif intent in {"semantic_topic_lookup", "revision_history_lookup"} and semantic_group_count == 0 and exact_group_count > 0:
        critic_status = "needs_semantic_expansion"
        recommended_action = "expand_semantic_search_or_context_profiles"
        reason_codes.append("topic_query_has_exact_only_results")
        confidence = 0.7
    elif answer_support_groups:
        critic_status = "strong_enough_for_final_gate_attempt"
        recommended_action = "run_dynamic_final_gate_for_query"
        reason_codes.append("answer_support_groups_present")
        if exact_group_count > 0:
            reason_codes.append("exact_hits_present")
        if semantic_group_count > 0:
            reason_codes.append("semantic_groups_present")
        confidence = 0.8
    else:
        critic_status = "retrieval_only_not_answer_ready"
        recommended_action = "keep_retrieval_only_and_run_citation_authority_or_review"
        reason_codes.append("no_answer_support_groups")
        if exact_group_count > 0:
            reason_codes.append("exact_hits_present")
        if semantic_group_count > 0:
            reason_codes.append("semantic_groups_present")
        confidence = 0.75

    if review_groups:
        reason_codes.append("review_signals_present")
        if critic_status not in {"final_gate_already_authorized", "unsafe_retrieval_blocked"}:
            recommended_action = recommended_action + "; prioritize_human_review_for_unverified_groups"

    if dynamic_gate_result and not dynamic_final_safe_to_return and not dynamic_final_allowed_flag and dynamic_answer_status:
        reason_codes.append("dynamic_final_gate_not_authorized")

    record = {
        "critic_record_id": f"retrieval_critic__{stable_hash([query_id, query, critic_status])}",
        "query_id": query_id,
        "query": query,
        "query_intent": intent,
        "critic_status": critic_status,
        "recommended_next_action": recommended_action,
        "reason_codes": unique_texts(reason_codes),
        "critic_confidence": round(confidence, 6),
        "ranked_group_count": ranked_group_count,
        "exact_hit_group_count": exact_group_count,
        "semantic_group_count": semantic_group_count,
        "answer_support_group_count": len(answer_support_groups),
        "retrieval_only_group_count": len(retrieval_only_groups),
        "review_signal_group_count": len(review_groups),
        "unsafe_group_count": len(unsafe_groups),
        "top_page_ids": collect_top_values(groups, "page_id", limit=10),
        "top_category_labels": collect_top_values(groups, "category_labels", limit=10),
        "top_part_numbers": collect_top_values(groups, "part_numbers", limit=10),
        "dynamic_final_gate_status": dynamic_answer_status,
        "dynamic_final_answer_allowed": dynamic_final_allowed_flag,
        "dynamic_final_answer_safe_to_return": dynamic_final_safe_to_return,
        "dynamic_final_gate_block_reasons": unique_texts(dynamic_gate_block_reasons),
        "dynamic_final_gate_retrieval_consistency_reasons": unique_texts(dynamic_retrieval_consistency_reasons),
        "dynamic_final_gate_counters": dynamic_gate_counters,
        "feedback_as_proof_count": 0,
        "community_as_proof_count": 0,
        "category_as_proof_count": 0,
        "raw_feedback_direct_to_llm": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "can_mutate_source_truth": False,
        "source_truth_mutation_allowed": False,
        "advisory_only": True,
    }
    return record


def build_report(
    *,
    hybrid_v2_report: Mapping[str, Any],
    dynamic_final_gate_report: Mapping[str, Any] | None = None,
    opensearch_adapter: Mapping[str, Any] | None = None,
    category_overlay: Mapping[str, Any] | None = None,
    feedback_memory: Mapping[str, Any] | None = None,
    query_filter: str | None = None,
) -> dict[str, Any]:
    dynamic_by_query = get_dynamic_gate_by_query(dynamic_final_gate_report or {})
    query_results = [r for r in as_list(hybrid_v2_report.get("query_results")) if isinstance(r, Mapping)]
    if query_filter:
        lowered = query_filter.strip().lower()
        query_results = [r for r in query_results if as_text(r.get("query")).lower() == lowered]

    critic_records = []
    for result in query_results:
        query = as_text(result.get("query"))
        dynamic_result = dynamic_by_query.get(query.lower()) if query else None
        critic_records.append(build_critic_record(result, dynamic_result))

    source_quality_statuses = {
        "hybrid_v2": quality_status(hybrid_v2_report),
        "dynamic_final_gate": quality_status(dynamic_final_gate_report or {}),
        "opensearch_adapter": quality_status(opensearch_adapter or {}),
        "category_aware_leiden_overlay": quality_status(category_overlay or {}),
        "feedback_memory": quality_status(feedback_memory or {}),
    }

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "RETRIEVAL_CRITIC_BUILT",
        "generated_at": now_iso(),
        "read_only_critic": True,
        "critic_records": critic_records,
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
    records = [r for r in as_list(report.get("critic_records")) if isinstance(r, Mapping)]
    status_counts = Counter(as_text(r.get("critic_status")) for r in records)
    intent_counts = Counter(as_text(r.get("query_intent")) for r in records)
    action_counts = Counter(as_text(r.get("recommended_next_action")) for r in records)
    reason_counts = Counter(reason for r in records for reason in as_list(r.get("reason_codes")))

    critic_can_answer = sum(1 for r in records if as_bool(r.get("can_answer_directly")))
    critic_can_prove = sum(1 for r in records if as_bool(r.get("can_prove_claims")))
    source_truth_mutation_allowed = sum(1 for r in records if as_bool(r.get("source_truth_mutation_allowed")) or as_bool(r.get("can_mutate_source_truth")))
    unsafe_records = sum(1 for r in records if as_int(r.get("unsafe_group_count")) > 0)
    feedback_as_proof = sum(as_int(r.get("feedback_as_proof_count")) for r in records)
    community_as_proof = sum(as_int(r.get("community_as_proof_count")) for r in records)
    category_as_proof = sum(as_int(r.get("category_as_proof_count")) for r in records)
    raw_feedback_to_llm = sum(1 for r in records if as_bool(r.get("raw_feedback_direct_to_llm")))

    source_statuses = report.get("source_quality_statuses")
    if not isinstance(source_statuses, Mapping):
        source_statuses = {}

    summary = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "PASS",
        "critic_record_count": len(records),
        "query_count": len(records),
        "critic_status_counts": dict(sorted(status_counts.items())),
        "query_intent_counts": dict(sorted(intent_counts.items())),
        "recommended_action_counts": dict(sorted(action_counts.items())),
        "reason_code_counts": dict(sorted(reason_counts.items())),
        "strong_enough_for_final_gate_attempt_count": status_counts.get("strong_enough_for_final_gate_attempt", 0),
        "retrieval_only_not_answer_ready_count": status_counts.get("retrieval_only_not_answer_ready", 0),
        "needs_exact_search_count": status_counts.get("needs_exact_search", 0),
        "needs_semantic_expansion_count": status_counts.get("needs_semantic_expansion", 0),
        "abstain_no_evidence_count": status_counts.get("abstain_no_evidence", 0),
        "final_gate_already_authorized_count": status_counts.get("final_gate_already_authorized", 0),
        "dynamic_final_gate_needs_audit_count": status_counts.get("dynamic_final_gate_needs_audit", 0),
        "dynamic_final_gate_retrieval_consistency_audit_count": sum(1 for r in records if r.get("dynamic_final_gate_retrieval_consistency_reasons")),
        "unsafe_retrieval_blocked_count": status_counts.get("unsafe_retrieval_blocked", 0),
        "critic_can_answer_directly_count": critic_can_answer,
        "critic_can_prove_claims_count": critic_can_prove,
        "unsafe_critic_record_count": unsafe_records,
        "feedback_as_proof_count": feedback_as_proof,
        "community_as_proof_count": community_as_proof,
        "category_as_proof_count": category_as_proof,
        "raw_feedback_direct_to_llm_count": raw_feedback_to_llm,
        "postgres_write_attempt_count": as_int(report.get("postgres_write_attempt_count")),
        "qdrant_write_attempt_count": as_int(report.get("qdrant_write_attempt_count")),
        "opensearch_write_attempt_count": as_int(report.get("opensearch_write_attempt_count")),
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed,
        "source_truth_mutations_performed": as_int(report.get("source_truth_mutations_performed")),
        "source_quality_statuses": dict(source_statuses),
        "hybrid_v2_quality_status": as_text(source_statuses.get("hybrid_v2")),
        "dynamic_final_gate_quality_status": as_text(source_statuses.get("dynamic_final_gate")),
        "opensearch_quality_status": as_text(source_statuses.get("opensearch_adapter")),
        "category_aware_quality_status": as_text(source_statuses.get("category_aware_leiden_overlay")),
        "feedback_memory_quality_status": as_text(source_statuses.get("feedback_memory")),
    }
    if any([
        critic_can_answer,
        critic_can_prove,
        source_truth_mutation_allowed,
        feedback_as_proof,
        community_as_proof,
        category_as_proof,
        raw_feedback_to_llm,
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
    min_critic_records: int = 1,
    min_queries: int = 1,
    require_hybrid_v2_quality_pass: bool = False,
    require_dynamic_final_gate_quality_pass: bool = False,
) -> dict[str, Any]:
    summary = dict(report.get("summary") if isinstance(report.get("summary"), Mapping) else summarize(report))
    checks = {
        "critic_record_count_minimum_met": as_int(summary.get("critic_record_count")) >= min_critic_records,
        "query_count_minimum_met": as_int(summary.get("query_count")) >= min_queries,
        "critic_can_answer_directly_zero": as_int(summary.get("critic_can_answer_directly_count")) == 0,
        "critic_can_prove_claims_zero": as_int(summary.get("critic_can_prove_claims_count")) == 0,
        "source_truth_mutation_allowed_zero": as_int(summary.get("source_truth_mutation_allowed_count")) == 0,
        "feedback_as_proof_zero": as_int(summary.get("feedback_as_proof_count")) == 0,
        "community_as_proof_zero": as_int(summary.get("community_as_proof_count")) == 0,
        "category_as_proof_zero": as_int(summary.get("category_as_proof_count")) == 0,
        "raw_feedback_direct_to_llm_zero": as_int(summary.get("raw_feedback_direct_to_llm_count")) == 0,
        "postgres_write_attempt_zero": as_int(summary.get("postgres_write_attempt_count")) == 0,
        "qdrant_write_attempt_zero": as_int(summary.get("qdrant_write_attempt_count")) == 0,
        "opensearch_write_attempt_zero": as_int(summary.get("opensearch_write_attempt_count")) == 0,
    }
    if require_hybrid_v2_quality_pass:
        checks["hybrid_v2_quality_pass"] = as_text(summary.get("hybrid_v2_quality_status")).upper() == "PASS"
    if require_dynamic_final_gate_quality_pass:
        checks["dynamic_final_gate_quality_pass"] = as_text(summary.get("dynamic_final_gate_quality_status")).upper() == "PASS"

    status = "PASS" if all(checks.values()) and summary.get("status") == "PASS" else "FAIL"
    payload = {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": status,
        "summary": summary,
        "checks": checks,
    }
    payload["quality_status"] = status
    return payload


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else summarize(report)
    lines = [
        "# TRACE-Net Retrieval Critic v1",
        "",
        f"**Status:** {report.get('status', '')}",
        f"**Quality:** {report.get('quality_status', '')}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "critic_record_count",
        "strong_enough_for_final_gate_attempt_count",
        "retrieval_only_not_answer_ready_count",
        "needs_exact_search_count",
        "needs_semantic_expansion_count",
        "abstain_no_evidence_count",
        "final_gate_already_authorized_count",
        "dynamic_final_gate_needs_audit_count",
        "unsafe_critic_record_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key, 0)}")
    lines.extend(["", "## Critic Records", ""])
    for record in as_list(report.get("critic_records"))[:50]:
        if not isinstance(record, Mapping):
            continue
        lines.append(f"- **{record.get('query')}**: `{record.get('critic_status')}` -> {record.get('recommended_next_action')}")
    lines.append("")
    return "\n".join(lines)


def render_html(markdown_text: str) -> str:
    import html
    body = []
    for line in markdown_text.splitlines():
        if line.startswith("# "):
            body.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            body.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("- "):
            body.append(f"<p>{html.escape(line)}</p>")
        elif line.strip():
            body.append(f"<p>{html.escape(line)}</p>")
        else:
            body.append("")
    return "<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Retrieval Critic v1</title></head><body>" + "\n".join(body) + "</body></html>"


def write_outputs(report: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / DEFAULT_OUTPUT_FILE
    records_path = out / DEFAULT_RECORDS_FILE
    summary_path = out / DEFAULT_SUMMARY_FILE
    quality_path = out / DEFAULT_QUALITY_FILE
    manifest_path = out / DEFAULT_MANIFEST_FILE
    markdown_path = out / DEFAULT_MARKDOWN_FILE
    html_path = out / DEFAULT_HTML_FILE

    write_json(report_path, report)
    write_jsonl(records_path, report.get("critic_records", []))
    write_json(summary_path, report.get("summary", {}))
    q = quality_report(report, min_critic_records=0, min_queries=0)
    write_json(quality_path, q)
    markdown = render_markdown(report)
    markdown_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(render_html(markdown), encoding="utf-8")
    manifest = {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": now_iso(),
        "report_path": str(report_path),
        "records_path": str(records_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "markdown_path": str(markdown_path),
        "html_path": str(html_path),
        "read_only_critic": True,
    }
    write_json(manifest_path, manifest)
    report["report_path"] = str(report_path)
    report["records_path"] = str(records_path)
    report["summary_path"] = str(summary_path)
    report["quality_path"] = str(quality_path)
    report["manifest_path"] = str(manifest_path)
    report["markdown_path"] = str(markdown_path)
    report["html_path"] = str(html_path)
    write_json(report_path, report)
    return {
        "report_path": str(report_path),
        "records_path": str(records_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "manifest_path": str(manifest_path),
        "markdown_path": str(markdown_path),
        "html_path": str(html_path),
    }


def build_from_paths(
    *,
    hybrid_v2_report_path: str | Path = DEFAULT_HYBRID_V2_REPORT,
    dynamic_final_gate_path: str | Path | None = DEFAULT_DYNAMIC_FINAL_GATE,
    opensearch_adapter_path: str | Path | None = DEFAULT_OPENSEARCH_ADAPTER,
    category_overlay_path: str | Path | None = DEFAULT_CATEGORY_OVERLAY,
    feedback_memory_path: str | Path | None = DEFAULT_FEEDBACK_MEMORY,
    query_filter: str | None = None,
) -> dict[str, Any]:
    hybrid = read_json(hybrid_v2_report_path)
    if not hybrid:
        raise RetrievalCriticError(f"Hybrid v2 report not found or invalid: {hybrid_v2_report_path}")
    return build_report(
        hybrid_v2_report=hybrid,
        dynamic_final_gate_report=read_json(dynamic_final_gate_path),
        opensearch_adapter=read_json(opensearch_adapter_path),
        category_overlay=read_json(category_overlay_path),
        feedback_memory=read_json(feedback_memory_path),
        query_filter=query_filter,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Retrieval Critic v1")
    parser.add_argument("--hybrid-v2-report", default=str(DEFAULT_HYBRID_V2_REPORT))
    parser.add_argument("--dynamic-final-gate", default=str(DEFAULT_DYNAMIC_FINAL_GATE))
    parser.add_argument("--opensearch-adapter", default=str(DEFAULT_OPENSEARCH_ADAPTER))
    parser.add_argument("--category-aware-leiden-overlay", default=str(DEFAULT_CATEGORY_OVERLAY))
    parser.add_argument("--feedback-memory", default=str(DEFAULT_FEEDBACK_MEMORY))
    parser.add_argument("--query", default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--min-critic-records", type=int, default=1)
    parser.add_argument("--min-queries", type=int, default=1)
    parser.add_argument("--require-hybrid-v2-quality-pass", action="store_true")
    parser.add_argument("--require-dynamic-final-gate-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = build_from_paths(
        hybrid_v2_report_path=args.hybrid_v2_report,
        dynamic_final_gate_path=args.dynamic_final_gate,
        opensearch_adapter_path=args.opensearch_adapter,
        category_overlay_path=args.category_aware_leiden_overlay,
        feedback_memory_path=args.feedback_memory,
        query_filter=args.query,
    )
    paths = write_outputs(report, args.output_dir)

    q = quality_report(
        report,
        min_critic_records=args.min_critic_records,
        min_queries=args.min_queries,
        require_hybrid_v2_quality_pass=args.require_hybrid_v2_quality_pass,
        require_dynamic_final_gate_quality_pass=args.require_dynamic_final_gate_quality_pass,
    )
    write_json(paths["quality_path"], q)
    report["quality_status"] = q["status"]
    report["summary"] = q["summary"]
    write_json(paths["report_path"], report)

    print("TRACE-Net Retrieval Critic v1")
    print(f" Status: {report['status']}")
    print(f" Quality status: {q['status']}")
    summary = q["summary"]
    for key in [
        "critic_record_count",
        "strong_enough_for_final_gate_attempt_count",
        "retrieval_only_not_answer_ready_count",
        "needs_exact_search_count",
        "needs_semantic_expansion_count",
        "abstain_no_evidence_count",
        "unsafe_critic_record_count",
        "critic_can_answer_directly_count",
        "critic_can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ]:
        print(f" {key}: {summary.get(key, 0)}")
    print(f" report_path: {paths['report_path']}")
    print(f" quality_path: {paths['quality_path']}")
    return 0 if q["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
