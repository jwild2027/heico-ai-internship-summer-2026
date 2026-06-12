"""TRACE-Net Evidence Sufficiency Critic v1.

This module adds the second safe Self-RAG-style critic layer to TRACE-Net.
It reads Hybrid Retrieval v2, Dynamic Final-Gate Execution, and Retrieval
Critic outputs, then produces read-only evidence sufficiency records.

Safety contract:
- The critic can judge whether retrieved/final-gate candidate evidence is
  sufficient for a final-gate attempt or for a gated answer to be returned.
- The critic cannot answer directly.
- The critic cannot prove claims.
- The critic cannot mutate source truth.
- Feedback, community, and category signals remain advisory only.
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

SCHEMA_VERSION = "trace_net_evidence_sufficiency_critic_v1"
ALGORITHM = "trace_net_read_only_self_rag_style_evidence_sufficiency_critic_v1"
DEFAULT_OUTPUT_DIR = Path("local_data/organization/trace_net/evidence_sufficiency_critic")
DEFAULT_HYBRID_V2_REPORT = Path("local_data/organization/trace_net/hybrid_retrieval_v2/trace_net_hybrid_retrieval_v2.json")
DEFAULT_DYNAMIC_FINAL_GATE = Path("local_data/organization/trace_net/dynamic_final_gate_execution/trace_net_dynamic_final_gate_execution_v1.json")
DEFAULT_RETRIEVAL_CRITIC = Path("local_data/organization/trace_net/retrieval_critic/trace_net_retrieval_critic_v1.json")
DEFAULT_OUTPUT_FILE = "trace_net_evidence_sufficiency_critic_v1.json"
DEFAULT_RECORDS_FILE = "trace_net_evidence_sufficiency_critic_v1_records.jsonl"
DEFAULT_SUMMARY_FILE = "trace_net_evidence_sufficiency_critic_v1_summary.json"
DEFAULT_QUALITY_FILE = "trace_net_evidence_sufficiency_critic_v1_quality.json"
DEFAULT_MANIFEST_FILE = "trace_net_evidence_sufficiency_critic_v1_manifest.json"
DEFAULT_MD_FILE = "trace_net_evidence_sufficiency_critic_v1.md"
DEFAULT_HTML_FILE = "trace_net_evidence_sufficiency_critic_v1.html"

PART_RE = re.compile(r"\b\d{2,4}-\d{2,6}-\d{2,4}\b")
ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
REVISION_RE = re.compile(r"\brev(?:ision)?\.?\s*\d+\b", re.I)
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./-]*")
LOCAL_PATH_RE = re.compile(r"(?:[A-Za-z]:\\\\|[A-Za-z]:/|/mnt/|/home/|local_data[\\/]|\\\\Users\\\\|/Users/)", re.I)
RAW_BYTES_RE = re.compile(r"b['\"]|\\x[0-9a-fA-F]{2}")

ANSWER_SUPPORT_BUCKETS = {
    "source_text_evidence",
    "verified_part_evidence",
    "table_part_catalog_evidence",
    "table_structured_evidence",
    "clean_evidence_snippet",
    "promoted_table_part_evidence_candidate",
    "promoted_visual_part_evidence_candidate",
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
ANSWER_SUPPORT_AUTHORITIES = {
    "ocr_text_claim_with_citation",
    "part_page_relationship",
    "table_part_catalog_evidence_with_citation",
    "promoted_table_part_evidence_with_citation",
    "promoted_visual_part_evidence_with_citation",
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
REVIEW_TOKENS = {"review", "unverified", "candidate", "callout", "visual", "diagram", "table_repair", "needs_human"}


class EvidenceSufficiencyCriticError(RuntimeError):
    """Raised when the evidence sufficiency critic cannot be built safely."""


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


def tokenize(text: Any) -> list[str]:
    return [m.group(0).lower() for m in TOKEN_RE.finditer(as_text(text))]


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
    if len([t for t in tokenize(query_text) if len(t) > 1]) <= 2:
        return "short_exact_or_keyword_lookup"
    return "semantic_topic_lookup"


def index_by_query(report: Mapping[str, Any], key: str = "query_results") -> dict[str, dict[str, Any]]:
    rows = report.get(key)
    if rows is None:
        rows = report.get("results") or report.get("critic_records") or []
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        query = normalize_query(row.get("query"))
        if query:
            out[query] = dict(row)
    return out


def ranked_groups(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    groups = row.get("ranked_groups") or row.get("groups") or []
    return [dict(group) for group in groups if isinstance(group, Mapping)] if isinstance(groups, list) else []


def collect_values_from_hits(group: Mapping[str, Any], key: str) -> list[Any]:
    values: list[Any] = []
    values.extend(as_list(group.get(key)))
    for hit_key in ("exact_hits", "semantic_groups", "candidate_hits", "hits"):
        for hit in as_list(group.get(hit_key)):
            if isinstance(hit, Mapping):
                values.extend(as_list(hit.get(key)))
                singular = key[:-1] if key.endswith("s") else key
                if hit.get(singular):
                    values.append(hit.get(singular))
                values.extend(collect_values_from_hits(hit, key))
    return values


def group_page_lineage(group: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    values.append(group.get("page_id"))
    values.extend(as_list(group.get("source_page_ids")))
    values.extend(collect_values_from_hits(group, "source_page_ids"))
    values.extend(collect_values_from_hits(group, "page_ids"))
    return unique_texts(values)


def group_citations(group: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    values.extend(as_list(group.get("citation_ids")))
    if group.get("citation_id"):
        values.append(group.get("citation_id"))
    values.extend(collect_values_from_hits(group, "citation_ids"))
    return unique_texts(values)


def group_buckets(group: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    values.extend(as_list(group.get("rag_buckets") or group.get("buckets")))
    for key in ("rag_bucket", "bucket"):
        if group.get(key):
            values.append(group.get(key))
    values.extend(collect_values_from_hits(group, "rag_buckets"))
    values.extend(collect_values_from_hits(group, "buckets"))
    values.extend(collect_values_from_hits(group, "rag_bucket"))
    return unique_texts(as_text(value).lower() for value in values if as_text(value))


def group_authorities(group: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    values.extend(as_list(group.get("authorities")))
    if group.get("authority"):
        values.append(group.get("authority"))
    values.extend(collect_values_from_hits(group, "authorities"))
    values.extend(collect_values_from_hits(group, "authority"))
    return unique_texts(as_text(value).lower() for value in values if as_text(value))


def group_part_numbers(group: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    values.extend(as_list(group.get("part_numbers")))
    values.extend(collect_values_from_hits(group, "part_numbers"))
    for field in ("text", "text_preview", "claim_text", "summary"):
        values.extend(PART_RE.findall(as_text(group.get(field))))
    return unique_texts(values)


def has_banned_bucket(buckets: Iterable[str]) -> bool:
    for bucket in buckets:
        lowered = as_text(bucket).lower()
        if any(token in lowered for token in BANNED_BUCKET_TOKENS):
            return True
    return False


def group_is_unsafe(group: Mapping[str, Any]) -> bool:
    if as_bool(group.get("unsafe")) or as_int(group.get("unsafe_group_count")) > 0:
        return True
    if as_bool(group.get("source_truth_mutation_allowed")) or as_bool(group.get("can_mutate_source_truth")):
        return True
    if as_bool(group.get("feedback_as_proof")) or as_bool(group.get("community_as_proof")) or as_bool(group.get("category_as_proof")):
        return True
    return has_banned_bucket(group_buckets(group))


def group_has_answer_support(group: Mapping[str, Any]) -> bool:
    if as_bool(group.get("answer_support_candidate")):
        return True
    if as_int(group.get("answer_support_record_count")) > 0 or as_int(group.get("answer_support_candidate_count")) > 0:
        return True
    buckets = set(group_buckets(group))
    authorities = set(group_authorities(group))
    if buckets & ANSWER_SUPPORT_BUCKETS:
        return True
    if authorities & ANSWER_SUPPORT_AUTHORITIES:
        return True
    for hit in as_list(group.get("exact_hits")):
        if isinstance(hit, Mapping) and as_bool(hit.get("answer_support_candidate")):
            return True
    return False


def group_has_review_signal(group: Mapping[str, Any]) -> bool:
    labels = " ".join(as_text(x).lower() for x in as_list(group.get("category_labels")))
    text = " ".join([
        labels,
        as_text(group.get("page_category_label")).lower(),
        " ".join(as_text(x).lower() for x in as_list(group.get("dominant_leiden_hint_families"))),
    ])
    return any(token in text for token in REVIEW_TOKENS)


def evaluate_group_sufficiency(group: Mapping[str, Any]) -> dict[str, Any]:
    lineage = group_page_lineage(group)
    citations = group_citations(group)
    buckets = group_buckets(group)
    authorities = group_authorities(group)
    reasons: list[str] = []
    if not lineage:
        reasons.append("missing_source_page_lineage")
    if not citations:
        reasons.append("missing_citation")
    if has_banned_bucket(buckets):
        reasons.append("banned_raw_or_unsafe_bucket")
    if group_is_unsafe(group):
        reasons.append("unsafe_group")
    if not group_has_answer_support(group):
        reasons.append("missing_answer_support_authority")
    if as_bool(group.get("retrieval_only"), True) and "missing_answer_support_authority" in reasons:
        reasons.append("retrieval_only_group")
    if group_has_review_signal(group):
        reasons.append("review_signal_present")
    sufficient = not any(r in reasons for r in [
        "missing_source_page_lineage",
        "missing_citation",
        "banned_raw_or_unsafe_bucket",
        "unsafe_group",
        "missing_answer_support_authority",
        "retrieval_only_group",
    ])
    return {
        "group_id": as_text(group.get("hybrid_v2_group_id")) or as_text(group.get("group_id")) or stable_hash(group),
        "page_id": as_text(group.get("page_id")) or (lineage[0] if lineage else ""),
        "source_page_ids": lineage,
        "citation_ids": citations,
        "rag_buckets": buckets,
        "authorities": authorities,
        "part_numbers": group_part_numbers(group),
        "exact_hit_count": as_int(group.get("exact_hit_count")),
        "semantic_group_count": as_int(group.get("semantic_group_count")),
        "answer_support_like": group_has_answer_support(group),
        "retrieval_only": as_bool(group.get("retrieval_only"), not group_has_answer_support(group)),
        "review_signal_present": group_has_review_signal(group),
        "unsafe_group": group_is_unsafe(group),
        "sufficient_for_final_gate": sufficient,
        "insufficiency_reason_codes": unique_texts(reasons),
    }


def claim_buckets(claim: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    values.extend(as_list(claim.get("rag_buckets") or claim.get("buckets")))
    for key in ("rag_bucket", "bucket"):
        if claim.get(key):
            values.append(claim.get(key))
    return unique_texts(as_text(value).lower() for value in values if as_text(value))


def claim_authorities(claim: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    values.extend(as_list(claim.get("authorities")))
    if claim.get("authority"):
        values.append(claim.get("authority"))
    return unique_texts(as_text(value).lower() for value in values if as_text(value))


def claim_lineage(claim: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    values.append(claim.get("page_id"))
    values.extend(as_list(claim.get("source_page_ids")))
    values.extend(as_list(claim.get("page_ids")))
    return unique_texts(values)


def claim_citations(claim: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    values.extend(as_list(claim.get("citation_ids")))
    if claim.get("citation_id"):
        values.append(claim.get("citation_id"))
    return unique_texts(values)


def evaluate_claim_sufficiency(claim: Mapping[str, Any]) -> dict[str, Any]:
    lineage = claim_lineage(claim)
    citations = claim_citations(claim)
    buckets = claim_buckets(claim)
    authorities = claim_authorities(claim)
    text = as_text(claim.get("claim_text") or claim.get("clean_materialized_claim_text") or claim.get("materialized_claim_text"))
    reasons: list[str] = []
    if not lineage:
        reasons.append("missing_source_page_lineage")
    if not citations:
        reasons.append("missing_citation")
    if not (set(buckets) & ANSWER_SUPPORT_BUCKETS or set(authorities) & ANSWER_SUPPORT_AUTHORITIES):
        reasons.append("missing_answer_support_authority")
    if as_bool(claim.get("retrieval_only")):
        reasons.append("retrieval_only_claim")
    if has_banned_bucket(buckets):
        reasons.append("banned_raw_or_unsafe_bucket")
    if as_bool(claim.get("source_truth_mutation_allowed")) or as_bool(claim.get("can_mutate_source_truth")):
        reasons.append("source_truth_mutation_risk")
    if as_bool(claim.get("feedback_as_proof")):
        reasons.append("feedback_as_proof")
    if as_bool(claim.get("community_as_proof")):
        reasons.append("community_as_proof")
    if as_bool(claim.get("category_as_proof")):
        reasons.append("category_as_proof")
    if LOCAL_PATH_RE.search(text):
        reasons.append("local_path_leak")
    if RAW_BYTES_RE.search(text):
        reasons.append("raw_bytes_repr")
    sufficient = not reasons
    return {
        "claim_id": as_text(claim.get("dynamic_final_claim_id") or claim.get("claim_id")) or stable_hash(claim),
        "page_id": as_text(claim.get("page_id")) or (lineage[0] if lineage else ""),
        "source_page_ids": lineage,
        "citation_ids": citations,
        "rag_buckets": buckets,
        "authorities": authorities,
        "sufficient_for_final_answer": sufficient,
        "insufficiency_reason_codes": unique_texts(reasons),
    }


def safe_final_gate_result(dynamic_result: Mapping[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    answer_status = as_text(dynamic_result.get("answer_status"))
    final_allowed = as_bool(dynamic_result.get("final_answer_allowed"))
    final_claim_count = as_int(dynamic_result.get("final_claim_count"))
    final_text_present = bool(as_text(dynamic_result.get("final_answer_text")))
    if not final_allowed:
        reasons.append("dynamic_final_gate_not_allowed")
    if answer_status not in {"DYNAMIC_FINAL_GATE_APPROVED", "FINAL_GATE_ARTIFACT_ANSWER"}:
        reasons.append("unrecognized_or_nonfinal_answer_status")
    if final_claim_count <= 0 and not final_text_present:
        reasons.append("missing_final_claims_or_answer_text")
    for counter_key in [
        "uncited_final_claim_count",
        "retrieval_only_final_claim_count",
        "feedback_as_proof_count",
        "community_as_proof_count",
        "category_as_proof_count",
        "source_truth_mutation_allowed_count",
        "local_path_leak_count",
        "raw_bytes_repr_count",
    ]:
        if as_int(dynamic_result.get(counter_key)) > 0:
            reasons.append(f"{counter_key}_nonzero")
    claim_rows = [c for c in as_list(dynamic_result.get("final_claims")) if isinstance(c, Mapping)]
    insufficient_claims = [evaluate_claim_sufficiency(c) for c in claim_rows]
    bad_claims = [c for c in insufficient_claims if not c["sufficient_for_final_answer"]]
    if claim_rows and bad_claims:
        reasons.append("insufficient_final_claim_records")
    return not reasons, unique_texts(reasons)


def build_sufficiency_record(
    query_result: Mapping[str, Any],
    *,
    dynamic_result: Mapping[str, Any] | None = None,
    retrieval_critic_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    query = as_text(query_result.get("query"))
    query_id = as_text(query_result.get("query_id")) or f"query__{stable_hash(query)}"
    intent = as_text(query_result.get("query_intent")) or detect_query_intent(query)
    groups = ranked_groups(query_result)
    group_evals = [evaluate_group_sufficiency(group) for group in groups]

    exact_group_count = as_int(query_result.get("exact_hit_group_count"), sum(1 for g in groups if as_int(g.get("exact_hit_count")) > 0))
    semantic_group_count = as_int(query_result.get("semantic_group_count"), sum(1 for g in groups if as_int(g.get("semantic_group_count")) > 0))
    ranked_group_count = as_int(query_result.get("ranked_group_count"), len(groups))
    sufficient_groups = [g for g in group_evals if g["sufficient_for_final_gate"]]
    answer_support_groups = [g for g in group_evals if g["answer_support_like"] and not g["unsafe_group"]]
    retrieval_only_groups = [g for g in group_evals if g["retrieval_only"] and not g["sufficient_for_final_gate"] and not g["unsafe_group"]]
    review_groups = [g for g in group_evals if g["review_signal_present"]]
    unsafe_groups = [g for g in group_evals if g["unsafe_group"]]

    final_status = as_text(dynamic_result.get("answer_status")) if dynamic_result else ""
    final_allowed = bool(dynamic_result and as_bool(dynamic_result.get("final_answer_allowed")))
    final_claims = [c for c in as_list(dynamic_result.get("final_claims") if dynamic_result else []) if isinstance(c, Mapping)]
    claim_evals = [evaluate_claim_sufficiency(c) for c in final_claims]
    safe_claims = [c for c in claim_evals if c["sufficient_for_final_answer"]]
    bad_claims = [c for c in claim_evals if not c["sufficient_for_final_answer"]]
    dynamic_safe, dynamic_block_reasons = safe_final_gate_result(dynamic_result or {}) if dynamic_result else (False, ["missing_dynamic_final_gate_result"])

    retrieval_critic_status = as_text((retrieval_critic_result or {}).get("critic_status"))
    retrieval_critic_action = as_text((retrieval_critic_result or {}).get("recommended_next_action"))

    reason_codes: list[str] = []
    recommended_action = ""
    status = ""
    confidence = 0.0

    if unsafe_groups:
        status = "unsafe_evidence_blocked"
        recommended_action = "block_and_review_unsafe_evidence"
        reason_codes.append("unsafe_groups_present")
        confidence = 0.95
    elif final_allowed and dynamic_safe:
        if retrieval_critic_status == "dynamic_final_gate_needs_audit":
            status = "final_evidence_sufficient_but_retrieval_audit_required"
            recommended_action = "audit_retrieval_consistency_before_returning_answer"
            reason_codes.append("retrieval_critic_requires_audit")
            confidence = 0.75
        elif final_status == "FINAL_GATE_ARTIFACT_ANSWER":
            status = "final_artifact_evidence_sufficient"
            recommended_action = "return_final_answer_if_policy_allows"
            reason_codes.append("final_gate_artifact_evidence_clean")
            confidence = 0.95
        else:
            status = "final_evidence_sufficient"
            recommended_action = "return_final_answer_if_retrieval_critic_allows"
            reason_codes.append("dynamic_final_gate_evidence_clean")
            confidence = 0.9
    elif final_allowed and not dynamic_safe:
        status = "final_gate_claims_need_audit"
        recommended_action = "audit_dynamic_final_gate_claims_before_answer"
        reason_codes.extend(dynamic_block_reasons)
        confidence = 0.85
    elif ranked_group_count == 0:
        status = "insufficient_no_candidate_groups"
        recommended_action = "abstain_or_expand_retrieval"
        reason_codes.append("no_retrieval_groups")
        confidence = 0.9
    elif intent in {"exact_part_number_lookup", "exact_ata_code_lookup", "revision_lookup", "short_exact_or_keyword_lookup"} and exact_group_count == 0:
        status = "insufficient_missing_exact_support"
        recommended_action = "run_or_expand_exact_search_before_final_gate"
        reason_codes.append("exact_identifier_query_without_exact_hit_groups")
        confidence = 0.85
    elif sufficient_groups:
        status = "sufficient_for_final_gate_attempt"
        recommended_action = "run_dynamic_final_gate_for_query"
        reason_codes.append("groups_have_source_citation_authority")
        confidence = 0.8
    elif all("missing_citation" in g["insufficiency_reason_codes"] for g in group_evals if not g["unsafe_group"]):
        status = "insufficient_missing_citation"
        recommended_action = "resolve_citations_or_keep_retrieval_only"
        reason_codes.append("candidate_groups_missing_citations")
        confidence = 0.8
    elif answer_support_groups and not sufficient_groups:
        status = "insufficient_missing_source_or_citation_lineage"
        recommended_action = "resolve_source_trace_and_citations_before_final_gate"
        reason_codes.append("answer_support_groups_lack_lineage_or_citation")
        confidence = 0.78
    elif retrieval_only_groups and len(retrieval_only_groups) >= max(1, ranked_group_count - len(unsafe_groups)):
        status = "insufficient_retrieval_only_evidence"
        recommended_action = "keep_retrieval_only_and_run_citation_authority_or_review"
        reason_codes.append("only_retrieval_only_groups_available")
        confidence = 0.75
    elif review_groups:
        status = "evidence_needs_human_review"
        recommended_action = "send_evidence_to_human_review_before_final_gate"
        reason_codes.append("review_signals_present")
        confidence = 0.7
    else:
        status = "insufficient_evidence"
        recommended_action = "expand_retrieval_or_abstain"
        reason_codes.append("no_sufficient_source_citation_authority_path")
        confidence = 0.7

    if review_groups and "review_signals_present" not in reason_codes:
        reason_codes.append("review_signals_present")
    if dynamic_result and not final_allowed:
        reason_codes.append("dynamic_final_gate_not_allowed")
    if bad_claims:
        reason_codes.append("insufficient_final_claim_records")

    top_pages = unique_texts(g.get("page_id") or (g.get("source_page_ids") or [""])[0] for g in group_evals)[:10]
    top_parts = unique_texts(p for g in group_evals for p in g.get("part_numbers", []))[:10]
    top_citations = unique_texts(c for g in group_evals for c in g.get("citation_ids", []))[:10]

    return {
        "sufficiency_record_id": f"evsuff__{stable_hash([query_id, query, status])}",
        "query_id": query_id,
        "query": query,
        "query_intent": intent,
        "evidence_sufficiency_status": status,
        "recommended_next_action": recommended_action,
        "reason_codes": unique_texts(reason_codes),
        "critic_confidence": round(confidence, 6),
        "retrieval_critic_status": retrieval_critic_status,
        "retrieval_critic_action": retrieval_critic_action,
        "dynamic_final_gate_status": final_status,
        "dynamic_final_answer_allowed": final_allowed,
        "dynamic_final_answer_safe_to_return": bool(final_allowed and dynamic_safe and retrieval_critic_status != "dynamic_final_gate_needs_audit"),
        "dynamic_final_gate_block_reasons": dynamic_block_reasons,
        "ranked_group_count": ranked_group_count,
        "exact_hit_group_count": exact_group_count,
        "semantic_group_count": semantic_group_count,
        "answer_support_group_count": len(answer_support_groups),
        "sufficient_group_count": len(sufficient_groups),
        "retrieval_only_group_count": len(retrieval_only_groups),
        "review_signal_group_count": len(review_groups),
        "unsafe_group_count": len(unsafe_groups),
        "source_trace_candidate_count": sum(1 for g in group_evals if g.get("source_page_ids")),
        "citation_candidate_count": sum(1 for g in group_evals if g.get("citation_ids")),
        "authority_candidate_count": sum(1 for g in group_evals if g.get("authorities")),
        "final_claim_count": as_int(dynamic_result.get("final_claim_count") if dynamic_result else 0),
        "safe_final_claim_count": len(safe_claims),
        "insufficient_final_claim_count": len(bad_claims),
        "blocked_claim_count": as_int(dynamic_result.get("blocked_claim_count") if dynamic_result else 0),
        "top_page_ids": top_pages,
        "top_part_numbers": top_parts,
        "top_citation_ids": top_citations,
        "group_sufficiency_records": group_evals[:20],
        "claim_sufficiency_records": claim_evals[:20],
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


def build_report(
    *,
    hybrid_v2_report: Mapping[str, Any],
    dynamic_final_gate_report: Mapping[str, Any] | None = None,
    retrieval_critic_report: Mapping[str, Any] | None = None,
    query_filter: str | None = None,
) -> dict[str, Any]:
    dynamic_by_query = index_by_query(dynamic_final_gate_report or {}, key="query_results")
    retrieval_critic_by_query = index_by_query(retrieval_critic_report or {}, key="critic_records")
    query_rows = [row for row in as_list(hybrid_v2_report.get("query_results")) if isinstance(row, Mapping)]
    if query_filter:
        q = normalize_query(query_filter)
        query_rows = [row for row in query_rows if normalize_query(row.get("query")) == q]

    records: list[dict[str, Any]] = []
    for row in query_rows:
        q = normalize_query(row.get("query"))
        records.append(build_sufficiency_record(
            row,
            dynamic_result=dynamic_by_query.get(q),
            retrieval_critic_result=retrieval_critic_by_query.get(q),
        ))

    source_quality_statuses = {
        "hybrid_v2": quality_status(hybrid_v2_report),
        "dynamic_final_gate": quality_status(dynamic_final_gate_report or {}),
        "retrieval_critic": quality_status(retrieval_critic_report or {}),
    }
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "EVIDENCE_SUFFICIENCY_CRITIC_BUILT",
        "generated_at": now_iso(),
        "read_only_critic": True,
        "sufficiency_records": records,
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
    records = [r for r in as_list(report.get("sufficiency_records")) if isinstance(r, Mapping)]
    status_counts = Counter(as_text(r.get("evidence_sufficiency_status")) for r in records)
    intent_counts = Counter(as_text(r.get("query_intent")) for r in records)
    action_counts = Counter(as_text(r.get("recommended_next_action")) for r in records)
    reason_counts = Counter(reason for r in records for reason in as_list(r.get("reason_codes")))

    critic_can_answer = sum(1 for r in records if as_bool(r.get("can_answer_directly")))
    critic_can_prove = sum(1 for r in records if as_bool(r.get("can_prove_claims")))
    source_truth_mutation_allowed = sum(1 for r in records if as_bool(r.get("source_truth_mutation_allowed")) or as_bool(r.get("can_mutate_source_truth")))
    unsafe_records = sum(1 for r in records if as_int(r.get("unsafe_group_count")) > 0 or r.get("evidence_sufficiency_status") == "unsafe_evidence_blocked")
    feedback_as_proof = sum(as_int(r.get("feedback_as_proof_count")) for r in records)
    community_as_proof = sum(as_int(r.get("community_as_proof_count")) for r in records)
    category_as_proof = sum(as_int(r.get("category_as_proof_count")) for r in records)
    raw_feedback_to_llm = sum(1 for r in records if as_bool(r.get("raw_feedback_direct_to_llm")))

    source_statuses = report.get("source_quality_statuses") if isinstance(report.get("source_quality_statuses"), Mapping) else {}
    summary = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "status": "PASS",
        "sufficiency_record_count": len(records),
        "query_count": len(records),
        "evidence_sufficiency_status_counts": dict(sorted(status_counts.items())),
        "query_intent_counts": dict(sorted(intent_counts.items())),
        "recommended_action_counts": dict(sorted(action_counts.items())),
        "reason_code_counts": dict(sorted(reason_counts.items())),
        "final_evidence_sufficient_count": status_counts.get("final_evidence_sufficient", 0),
        "final_artifact_evidence_sufficient_count": status_counts.get("final_artifact_evidence_sufficient", 0),
        "final_evidence_sufficient_but_retrieval_audit_required_count": status_counts.get("final_evidence_sufficient_but_retrieval_audit_required", 0),
        "final_gate_claims_need_audit_count": status_counts.get("final_gate_claims_need_audit", 0),
        "sufficient_for_final_gate_attempt_count": status_counts.get("sufficient_for_final_gate_attempt", 0),
        "insufficient_retrieval_only_evidence_count": status_counts.get("insufficient_retrieval_only_evidence", 0),
        "insufficient_missing_citation_count": status_counts.get("insufficient_missing_citation", 0),
        "insufficient_missing_exact_support_count": status_counts.get("insufficient_missing_exact_support", 0),
        "evidence_needs_human_review_count": status_counts.get("evidence_needs_human_review", 0),
        "unsafe_evidence_blocked_count": status_counts.get("unsafe_evidence_blocked", 0),
        "safe_final_claim_count": sum(as_int(r.get("safe_final_claim_count")) for r in records),
        "insufficient_final_claim_count": sum(as_int(r.get("insufficient_final_claim_count")) for r in records),
        "sufficient_group_count": sum(as_int(r.get("sufficient_group_count")) for r in records),
        "answer_support_group_count": sum(as_int(r.get("answer_support_group_count")) for r in records),
        "retrieval_only_group_count": sum(as_int(r.get("retrieval_only_group_count")) for r in records),
        "unsafe_sufficiency_record_count": unsafe_records,
        "sufficiency_can_answer_directly_count": critic_can_answer,
        "sufficiency_can_prove_claims_count": critic_can_prove,
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
        "retrieval_critic_quality_status": as_text(source_statuses.get("retrieval_critic")),
    }
    if any([
        critic_can_answer,
        critic_can_prove,
        source_truth_mutation_allowed,
        feedback_as_proof,
        community_as_proof,
        category_as_proof,
        raw_feedback_to_llm,
        unsafe_records,
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
    min_sufficiency_records: int = 1,
    min_queries: int = 1,
    require_hybrid_v2_quality_pass: bool = False,
    require_dynamic_final_gate_quality_pass: bool = False,
    require_retrieval_critic_quality_pass: bool = False,
) -> dict[str, Any]:
    summary = dict(report.get("summary") if isinstance(report.get("summary"), Mapping) else summarize(report))
    checks = {
        "sufficiency_record_count_minimum_met": as_int(summary.get("sufficiency_record_count")) >= min_sufficiency_records,
        "query_count_minimum_met": as_int(summary.get("query_count")) >= min_queries,
        "sufficiency_can_answer_directly_zero": as_int(summary.get("sufficiency_can_answer_directly_count")) == 0,
        "sufficiency_can_prove_claims_zero": as_int(summary.get("sufficiency_can_prove_claims_count")) == 0,
        "unsafe_sufficiency_record_count_zero": as_int(summary.get("unsafe_sufficiency_record_count")) == 0,
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
    if require_retrieval_critic_quality_pass:
        checks["retrieval_critic_quality_pass"] = as_text(summary.get("retrieval_critic_quality_status")).upper() == "PASS"
    status = "PASS" if all(checks.values()) and summary.get("status") == "PASS" else "FAIL"
    payload = {
        "schema_version": f"{SCHEMA_VERSION}_quality",
        "status": status,
        "quality_status": status,
        "summary": summary,
        "checks": checks,
    }
    return payload


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else summarize(report)
    lines = [
        "# TRACE-Net Evidence Sufficiency Critic v1",
        "",
        f"**Status:** {report.get('status', '')}",
        f"**Quality:** {report.get('quality_status', '')}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "sufficiency_record_count",
        "final_evidence_sufficient_count",
        "final_artifact_evidence_sufficient_count",
        "final_evidence_sufficient_but_retrieval_audit_required_count",
        "sufficient_for_final_gate_attempt_count",
        "insufficient_retrieval_only_evidence_count",
        "unsafe_sufficiency_record_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {summary.get(key, 0)}")
    lines.extend(["", "## Evidence Sufficiency Records", ""])
    for record in as_list(report.get("sufficiency_records"))[:50]:
        if not isinstance(record, Mapping):
            continue
        lines.append(f"- **{record.get('query')}**: `{record.get('evidence_sufficiency_status')}` -> {record.get('recommended_next_action')}")
    lines.append("")
    return "\n".join(lines)


def render_html(markdown_text: str) -> str:
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
    return "<!doctype html><html><head><meta charset='utf-8'><title>TRACE-Net Evidence Sufficiency Critic v1</title></head><body>" + "\n".join(body) + "</body></html>"


def write_outputs(report: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / DEFAULT_OUTPUT_FILE
    records_path = out / DEFAULT_RECORDS_FILE
    summary_path = out / DEFAULT_SUMMARY_FILE
    quality_path = out / DEFAULT_QUALITY_FILE
    manifest_path = out / DEFAULT_MANIFEST_FILE
    md_path = out / DEFAULT_MD_FILE
    html_path = out / DEFAULT_HTML_FILE
    write_json(report_path, report)
    write_jsonl(records_path, report.get("sufficiency_records", []))
    write_json(summary_path, report.get("summary", {}))
    quality = quality_report(report)
    write_json(quality_path, quality)
    manifest = {
        "schema_version": f"{SCHEMA_VERSION}_manifest",
        "generated_at": now_iso(),
        "report_path": str(report_path),
        "records_path": str(records_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "read_only_critic": True,
        "source_truth_mutation_allowed": False,
    }
    write_json(manifest_path, manifest)
    md = render_markdown(report)
    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(render_html(md), encoding="utf-8")
    return {
        "report_path": str(report_path),
        "records_path": str(records_path),
        "summary_path": str(summary_path),
        "quality_path": str(quality_path),
        "manifest_path": str(manifest_path),
        "markdown_path": str(md_path),
        "html_path": str(html_path),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Evidence Sufficiency Critic v1")
    parser.add_argument("--hybrid-v2-report", default=str(DEFAULT_HYBRID_V2_REPORT))
    parser.add_argument("--dynamic-final-gate", default=str(DEFAULT_DYNAMIC_FINAL_GATE))
    parser.add_argument("--retrieval-critic", default=str(DEFAULT_RETRIEVAL_CRITIC))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--query", default="")
    parser.add_argument("--min-sufficiency-records", type=int, default=1)
    parser.add_argument("--min-queries", type=int, default=1)
    parser.add_argument("--require-hybrid-v2-quality-pass", action="store_true")
    parser.add_argument("--require-dynamic-final-gate-quality-pass", action="store_true")
    parser.add_argument("--require-retrieval-critic-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    hybrid = read_json(args.hybrid_v2_report)
    dynamic = read_json(args.dynamic_final_gate)
    retrieval = read_json(args.retrieval_critic)
    report = build_report(
        hybrid_v2_report=hybrid,
        dynamic_final_gate_report=dynamic,
        retrieval_critic_report=retrieval,
        query_filter=args.query or None,
    )
    outputs = write_outputs(report, args.output_dir)
    quality = quality_report(
        report,
        min_sufficiency_records=args.min_sufficiency_records,
        min_queries=args.min_queries,
        require_hybrid_v2_quality_pass=args.require_hybrid_v2_quality_pass,
        require_dynamic_final_gate_quality_pass=args.require_dynamic_final_gate_quality_pass,
        require_retrieval_critic_quality_pass=args.require_retrieval_critic_quality_pass,
    )
    if args.quality:
        write_json(outputs["quality_path"], quality)
        report["quality_status"] = quality["status"]
        write_json(outputs["report_path"], report)

    summary = report.get("summary", {})
    print("TRACE-Net Evidence Sufficiency Critic v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {quality.get('status') if args.quality else report.get('quality_status')}")
    print(f" sufficiency_record_count: {summary.get('sufficiency_record_count')}")
    print(f" final_evidence_sufficient_count: {summary.get('final_evidence_sufficient_count')}")
    print(f" final_artifact_evidence_sufficient_count: {summary.get('final_artifact_evidence_sufficient_count')}")
    print(f" final_evidence_sufficient_but_retrieval_audit_required_count: {summary.get('final_evidence_sufficient_but_retrieval_audit_required_count')}")
    print(f" sufficient_for_final_gate_attempt_count: {summary.get('sufficient_for_final_gate_attempt_count')}")
    print(f" insufficient_retrieval_only_evidence_count: {summary.get('insufficient_retrieval_only_evidence_count')}")
    print(f" unsafe_sufficiency_record_count: {summary.get('unsafe_sufficiency_record_count')}")
    print(f" sufficiency_can_answer_directly_count: {summary.get('sufficiency_can_answer_directly_count')}")
    print(f" sufficiency_can_prove_claims_count: {summary.get('sufficiency_can_prove_claims_count')}")
    print(f" source_truth_mutation_allowed_count: {summary.get('source_truth_mutation_allowed_count')}")
    print(f" report_path: {outputs['report_path']}")
    print(f" quality_path: {outputs['quality_path']}")
    return 0 if (not args.quality or quality.get("status") == "PASS") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
