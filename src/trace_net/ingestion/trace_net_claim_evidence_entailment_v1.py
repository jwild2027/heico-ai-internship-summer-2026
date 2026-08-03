"""
TRACE-Net Claim Evidence Entailment v1.

Read-only advisory critic that strengthens the Self-RAG-style safety stack by
scoring claim-to-citation/evidence support, finding weak evidence spans,
flagging simple contradiction risks, recording critic disagreements, and
creating human-review escalation recommendations.

This module is intentionally NOT an answer gate. It cannot answer directly and
cannot prove claims. It produces structured review signals for downstream final
return policy / human-review routing.

Safety contract:
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no claim-proof authority
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_claim_evidence_entailment_v1"
DEFAULT_STATUS = "CLAIM_EVIDENCE_ENTAILMENT_BUILT"
DEFAULT_OUTPUT_NAME = "trace_net_claim_evidence_entailment_v1.json"
DEFAULT_QUALITY_NAME = "trace_net_claim_evidence_entailment_v1_quality.json"
DEFAULT_MARKDOWN_NAME = "trace_net_claim_evidence_entailment_v1.md"

PASS = "PASS"
FAIL = "FAIL"

CLAIM_TEXT_KEYS = (
    "claim_text",
    "final_claim_text",
    "answer_claim_text",
    "claim",
    "final_claim",
    "statement",
    "text_claim",
)

TEXT_KEYS = (
    "evidence_text",
    "supporting_text",
    "snippet_text",
    "clean_snippet",
    "text_preview",
    "search_text",
    "chunk_text",
    "content",
    "body",
    "text",
    "summary_text",
    "summary",
)

CITATION_KEYS = (
    "citation_id",
    "citation_ids",
    "citation",
    "citations",
    "source_citation",
    "source_citations",
    "supporting_citation",
    "supporting_citations",
)

PAGE_KEYS = (
    "page_id",
    "page_ids",
    "source_page_id",
    "source_page_ids",
    "supporting_page_id",
    "supporting_page_ids",
)

NEGATION_WORDS = {"not", "no", "never", "without", "cannot", "can't", "neither", "nor"}
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have", "in", "is",
    "it", "its", "of", "on", "or", "page", "pages", "part", "parts", "rev", "revision", "the", "this",
    "to", "with", "which", "that", "these", "those", "was", "were", "will", "can", "should", "does",
}

SAFETY_ZERO_KEYS = [
    "postgres_write_attempt_count",
    "qdrant_write_attempt_count",
    "opensearch_write_attempt_count",
    "source_truth_mutation_allowed_count",
    "source_truth_mutations_performed",
    "direct_answer_allowed_count",
    "claim_proof_allowed_count",
    "can_answer_directly_count",
    "can_prove_claims_count",
    "feedback_as_proof_count",
    "community_as_proof_count",
    "category_as_proof_count",
    "retrieval_only_answer_allowed_count",
]


@dataclass(frozen=True)
class EntailmentThresholds:
    min_entailment_records: int = 1
    min_claim_records: int = 1
    min_queries: int = 1
    min_source_resolved_records: int = 0
    max_unsafe_records: int = 0
    max_direct_answer_allowed: int = 0
    require_dynamic_final_gate_quality_pass: bool = False
    require_dublin_core_source_quality_pass: bool = False
    weak_entailment_threshold: float = 0.25
    supported_entailment_threshold: float = 0.55


def load_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing JSON input: {p}")
    payload = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected JSON object in {p}")
    return payload


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return p


def first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def get_nested(record: dict[str, Any], path: str) -> Any:
    cur: Any = record
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def infer_quality_status(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return first_non_empty(
        payload.get("quality_status"),
        payload.get("status"),
        summary.get("quality_status"),
        summary.get("status"),
    )


def optional_payload(path: str | Path | None) -> tuple[str, dict[str, Any] | None]:
    if not path:
        return "NOT_PROVIDED", None
    p = Path(path)
    if not p.exists():
        return "MISSING", None
    try:
        return "LOADED", load_json(p)
    except Exception as exc:  # pragma: no cover - defensive path
        return f"UNREADABLE:{type(exc).__name__}", None


def walk_json(value: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], Any]]:
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk_json(child, path + (str(key),))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from walk_json(child, path + (str(i),))


def compact_path(path: tuple[str, ...], max_parts: int = 10) -> str:
    if len(path) <= max_parts:
        return ".".join(path)
    return "..." + "." + ".".join(path[-max_parts:])


def text_from_record(record: dict[str, Any], keys: Iterable[str] = TEXT_KEYS) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("dc", "metadata", "source", "payload"):
        nested = record.get(key)
        if isinstance(nested, dict):
            nested_text = text_from_record(nested, keys)
            if nested_text:
                return nested_text
    return ""


def claim_text_from_record(record: dict[str, Any]) -> str:
    text = text_from_record(record, CLAIM_TEXT_KEYS)
    if text:
        return text
    # Some artifacts store claims as compact dicts with only value/content.
    for key in ("value", "content", "text"):
        value = record.get(key)
        if isinstance(value, str) and len(value.strip()) >= 12:
            return value.strip()
    return ""


def flatten_strings(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, str) and value.strip():
        found.append(value.strip())
    elif isinstance(value, list):
        for item in value:
            found.extend(flatten_strings(item))
    elif isinstance(value, dict):
        for key in ("id", "citation_id", "page_id", "source_page_id", "value", "label", "text"):
            v = value.get(key)
            if isinstance(v, str) and v.strip():
                found.append(v.strip())
    return found


def extract_values_by_keys(record: dict[str, Any], keys: Iterable[str]) -> list[str]:
    out: list[str] = []
    for key in keys:
        if key in record:
            out.extend(flatten_strings(record.get(key)))
    source_trace = record.get("source_trace")
    if isinstance(source_trace, dict):
        for key in keys:
            if key in source_trace:
                out.extend(flatten_strings(source_trace.get(key)))
    # Preserve order while de-duplicating.
    seen = set()
    deduped = []
    for value in out:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def extract_page_ids(record: dict[str, Any]) -> list[str]:
    values = extract_values_by_keys(record, PAGE_KEYS)
    # Citation IDs can include embedded page ids. Extract common TRACE-Net form.
    for citation in extract_values_by_keys(record, CITATION_KEYS):
        values.extend(re.findall(r"t_p_\d+_\d+_p\d{6}", citation))
    seen = set()
    return [x for x in values if x and not (x in seen or seen.add(x))]


def extract_citation_ids(record: dict[str, Any]) -> list[str]:
    values = extract_values_by_keys(record, CITATION_KEYS)
    seen = set()
    return [x for x in values if x and not (x in seen or seen.add(x))]


def is_claim_like(record: dict[str, Any], path: tuple[str, ...]) -> bool:
    text = claim_text_from_record(record)
    if not text or len(text) < 12:
        return False
    path_text = "/".join(path).lower()
    keys = {str(k).lower() for k in record.keys()}
    if keys.intersection(CLAIM_TEXT_KEYS):
        return True
    if "claim" in path_text or "final_claim" in path_text or "answer_claim" in path_text:
        return True
    if keys.intersection(CITATION_KEYS) and ("claim" in path_text or "answer" in path_text):
        return True
    return False


def infer_context_from_path(path: tuple[str, ...]) -> dict[str, str | None]:
    query_id = None
    for part in path:
        lower = part.lower()
        if lower in {"query_results", "queries", "results", "answer_records", "policy_records"}:
            continue
        if re.match(r"^[a-z0-9_\-]+$", lower) and any(token in lower for token in ("query", "part_", "ata_", "revision", "manual", "record")):
            query_id = part
    return {"query_id_from_path": query_id}


def extract_claim_records(dynamic_payload: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for path, value in walk_json(dynamic_payload):
        if not isinstance(value, dict):
            continue
        if not is_claim_like(value, path):
            continue
        claim_text = claim_text_from_record(value)
        page_ids = extract_page_ids(value)
        citation_ids = extract_citation_ids(value)
        query_id = first_non_empty(
            value.get("query_id"),
            value.get("query_key"),
            value.get("id") if str(value.get("id", "")).startswith("query") else None,
            get_nested(value, "query.query_id"),
            infer_context_from_path(path).get("query_id_from_path"),
        )
        query = first_non_empty(
            value.get("query"),
            value.get("question"),
            get_nested(value, "query.text"),
            get_nested(value, "query.query"),
        )
        status = first_non_empty(
            value.get("claim_status"),
            value.get("final_gate_status"),
            value.get("answer_status"),
            value.get("status"),
        )
        source_record_path = compact_path(path)
        key = (claim_text, ",".join(page_ids), ",".join(citation_ids))
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "claim_index": len(records) + 1,
                "claim_id": first_non_empty(value.get("claim_id"), value.get("id"), f"claim_{len(records)+1:04d}"),
                "query_id": query_id or "unknown_query",
                "query": query,
                "claim_text": claim_text,
                "citation_ids": citation_ids,
                "page_ids": page_ids,
                "source_record_path": source_record_path,
                "source_claim_status": status,
                "raw_claim_keys": sorted(str(k) for k in value.keys())[:40],
            }
        )

    summary = dynamic_payload.get("summary") if isinstance(dynamic_payload.get("summary"), dict) else {}
    expected_claims = summary.get("final_claim_count") or dynamic_payload.get("final_claim_count")
    if not records and isinstance(expected_claims, int) and expected_claims > 0:
        # Defensive fallback: this keeps the artifact useful when a legacy final
        # gate reports only summary counts. These records are intentionally weak
        # and will escalate to review rather than being treated as proof.
        for i in range(expected_claims):
            records.append(
                {
                    "claim_index": i + 1,
                    "claim_id": f"summary_only_claim_{i+1:04d}",
                    "query_id": "unknown_query",
                    "query": None,
                    "claim_text": f"UNEXTRACTED_FINAL_CLAIM_{i+1}",
                    "citation_ids": [],
                    "page_ids": [],
                    "source_record_path": "summary.final_claim_count",
                    "source_claim_status": "NEEDS_STRUCTURED_CLAIM_EXPORT",
                    "raw_claim_keys": [],
                }
            )
    return records


def tokenize(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9][a-z0-9\-_/]*", (text or "").lower())
    return {t for t in tokens if len(t) > 1 and t not in STOPWORDS}


def lexical_overlap_score(claim_text: str, evidence_text: str) -> float:
    claim_tokens = tokenize(claim_text)
    evidence_tokens = tokenize(evidence_text)
    if not claim_tokens or not evidence_tokens:
        return 0.0
    overlap = claim_tokens & evidence_tokens
    recall = len(overlap) / max(len(claim_tokens), 1)
    precisionish = len(overlap) / max(min(len(evidence_tokens), len(claim_tokens) * 4), 1)
    return round((0.75 * recall) + (0.25 * precisionish), 6)


def contains_negation(text: str) -> bool:
    return bool(tokenize(text) & NEGATION_WORDS)


def build_page_identity_map(dublin_payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not dublin_payload:
        return {}
    candidates: list[Any] = []
    for key in ("page_records", "records", "pages", "source_package_records", "page_profiles"):
        value = dublin_payload.get(key)
        if isinstance(value, list):
            candidates.extend(value)
    page_map: dict[str, dict[str, Any]] = {}
    for item in candidates:
        if not isinstance(item, dict):
            continue
        page_id = first_non_empty(
            item.get("page_id"),
            item.get("source_page_id"),
            get_nested(item, "dc.identifier"),
            get_nested(item, "source_trace.page_id"),
        )
        if not isinstance(page_id, str) or not page_id:
            continue
        page_map[page_id] = item
    return page_map


def source_identity_status(page_ids: list[str], page_identity_map: dict[str, dict[str, Any]]) -> tuple[str, list[str]]:
    if not page_ids:
        return "NO_PAGE_IDS", []
    resolved = [pid for pid in page_ids if pid in page_identity_map]
    if len(resolved) == len(page_ids):
        return "SOURCE_IDENTITY_RESOLVED", resolved
    if resolved:
        return "SOURCE_IDENTITY_PARTIAL", resolved
    return "SOURCE_IDENTITY_UNRESOLVED", []


def gather_evidence_candidates(*payloads: dict[str, Any] | None) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for payload in payloads:
        if not payload:
            continue
        for path, value in walk_json(payload):
            if not isinstance(value, dict):
                continue
            text = text_from_record(value)
            if not text or len(text) < 12:
                continue
            page_ids = extract_page_ids(value)
            citation_ids = extract_citation_ids(value)
            # Avoid using claim records themselves as evidence when possible.
            path_text = "/".join(path).lower()
            evidence_kind = first_non_empty(
                value.get("document_type"), value.get("record_type"), value.get("rag_bucket"), value.get("type")
            )
            if "final_claim" in path_text or "answer_claim" in path_text:
                continue
            key = (text[:160], ",".join(page_ids), ",".join(citation_ids))
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                {
                    "evidence_id": first_non_empty(
                        value.get("evidence_id"), value.get("id"), value.get("document_id"), value.get("opensearch_document_id"),
                        f"evidence_{len(candidates)+1:05d}",
                    ),
                    "page_ids": page_ids,
                    "citation_ids": citation_ids,
                    "text": text,
                    "source_record_path": compact_path(path),
                    "evidence_kind": evidence_kind,
                }
            )
    return candidates


def best_evidence_for_claim(claim: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    claim_pages = set(claim.get("page_ids") or [])
    claim_citations = set(claim.get("citation_ids") or [])
    scored: list[tuple[float, dict[str, Any]]] = []
    for candidate in candidates:
        cand_pages = set(candidate.get("page_ids") or [])
        cand_citations = set(candidate.get("citation_ids") or [])
        page_bonus = 0.08 if claim_pages and cand_pages and claim_pages & cand_pages else 0.0
        citation_bonus = 0.12 if claim_citations and cand_citations and claim_citations & cand_citations else 0.0
        score = lexical_overlap_score(claim.get("claim_text", ""), candidate.get("text", "")) + page_bonus + citation_bonus
        if score > 0:
            scored.append((round(min(score, 1.0), 6), candidate))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    score, candidate = scored[0]
    out = dict(candidate)
    out["match_score"] = score
    out["text_preview"] = candidate.get("text", "")[:500]
    out.pop("text", None)
    return out


def infer_entailment_status(score: float, has_citation: bool, source_status: str, thresholds: EntailmentThresholds) -> str:
    if not has_citation:
        return "NEEDS_REVIEW_MISSING_CITATION"
    if source_status not in {"SOURCE_IDENTITY_RESOLVED", "SOURCE_IDENTITY_PARTIAL"}:
        return "NEEDS_REVIEW_SOURCE_UNRESOLVED"
    if score >= thresholds.supported_entailment_threshold:
        return "SUPPORTED_BY_CITATION_EVIDENCE"
    if score >= thresholds.weak_entailment_threshold:
        return "PARTIALLY_SUPPORTED_NEEDS_REVIEW"
    return "WEAK_OR_MISSING_EVIDENCE_SPAN"


def build_critic_status_index(payloads: dict[str, dict[str, Any] | None]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = defaultdict(dict)
    for critic_name, payload in payloads.items():
        if not payload:
            continue
        for _path, value in walk_json(payload):
            if not isinstance(value, dict):
                continue
            query_id = value.get("query_id") or value.get("query_key")
            if not isinstance(query_id, str) or not query_id:
                continue
            status = first_non_empty(
                value.get("critic_status"),
                value.get("sufficiency_status"),
                value.get("answer_claim_status"),
                value.get("policy_status"),
                value.get("final_gate_status"),
                value.get("answer_status"),
                value.get("status"),
            )
            if status:
                index[query_id][critic_name] = status
    return dict(index)


def status_needs_audit(status: Any) -> bool:
    text = str(status or "").lower()
    return any(token in text for token in ("audit", "review", "fail", "blocked", "unsafe", "insufficient", "weak"))


def detect_critic_disagreement(query_id: str, critic_index: dict[str, dict[str, Any]]) -> dict[str, Any]:
    statuses = critic_index.get(query_id, {})
    if not statuses:
        return {"critic_disagreement": False, "critic_statuses": {}}
    audit_like = {name: status for name, status in statuses.items() if status_needs_audit(status)}
    approved_like = {name: status for name, status in statuses.items() if "authorized" in str(status).lower() or "approved" in str(status).lower() or str(status).upper() == "PASS"}
    disagreement = bool(audit_like and approved_like)
    return {"critic_disagreement": disagreement, "critic_statuses": statuses}


def detect_contradictions(records: list[dict[str, Any]]) -> set[str]:
    risky_ids: set[str] = set()
    by_query: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_query[str(record.get("query_id") or "unknown_query")].append(record)
    for _query_id, items in by_query.items():
        for i, left in enumerate(items):
            left_text = left.get("claim_text", "")
            left_tokens = tokenize(left_text)
            if not left_tokens:
                continue
            for right in items[i + 1 :]:
                right_text = right.get("claim_text", "")
                right_tokens = tokenize(right_text)
                if not right_tokens:
                    continue
                overlap = len(left_tokens & right_tokens) / max(min(len(left_tokens), len(right_tokens)), 1)
                if overlap >= 0.55 and contains_negation(left_text) != contains_negation(right_text):
                    risky_ids.add(str(left.get("claim_id")))
                    risky_ids.add(str(right.get("claim_id")))
    return risky_ids


def build_entailment_report(
    *,
    dynamic_final_gate_path: str | Path,
    output_dir: str | Path,
    dublin_core_source_package_extension_path: str | Path | None = None,
    hybrid_v2_report_path: str | Path | None = None,
    retrieval_critic_path: str | Path | None = None,
    evidence_sufficiency_critic_path: str | Path | None = None,
    answer_claim_critic_path: str | Path | None = None,
    thresholds: EntailmentThresholds | None = None,
    quality: bool = False,
) -> dict[str, Any]:
    thresholds = thresholds or EntailmentThresholds()
    dynamic_payload = load_json(dynamic_final_gate_path)
    dublin_load_status, dublin_payload = optional_payload(dublin_core_source_package_extension_path)
    hybrid_load_status, hybrid_payload = optional_payload(hybrid_v2_report_path)
    retrieval_load_status, retrieval_payload = optional_payload(retrieval_critic_path)
    sufficiency_load_status, sufficiency_payload = optional_payload(evidence_sufficiency_critic_path)
    answer_claim_load_status, answer_claim_payload = optional_payload(answer_claim_critic_path)

    page_identity_map = build_page_identity_map(dublin_payload)
    claims = extract_claim_records(dynamic_payload)
    evidence_candidates = gather_evidence_candidates(dynamic_payload, hybrid_payload, sufficiency_payload, answer_claim_payload)
    critic_index = build_critic_status_index(
        {
            "retrieval_critic": retrieval_payload,
            "evidence_sufficiency_critic": sufficiency_payload,
            "answer_claim_critic": answer_claim_payload,
        }
    )
    contradiction_claim_ids = detect_contradictions(claims)

    records: list[dict[str, Any]] = []
    review_escalations: list[dict[str, Any]] = []

    for claim in claims:
        best_evidence = best_evidence_for_claim(claim, evidence_candidates)
        score = float(best_evidence.get("match_score", 0.0)) if best_evidence else 0.0
        source_status, resolved_pages = source_identity_status(claim.get("page_ids", []), page_identity_map)
        citation_ids = claim.get("citation_ids") or []
        entailment_status = infer_entailment_status(score, bool(citation_ids), source_status, thresholds)
        critic_info = detect_critic_disagreement(str(claim.get("query_id") or "unknown_query"), critic_index)
        contradiction_risk = str(claim.get("claim_id")) in contradiction_claim_ids
        weak = entailment_status != "SUPPORTED_BY_CITATION_EVIDENCE" or contradiction_risk or critic_info["critic_disagreement"]

        reason_codes: list[str] = []
        if not citation_ids:
            reason_codes.append("missing_citation")
        if source_status not in {"SOURCE_IDENTITY_RESOLVED", "SOURCE_IDENTITY_PARTIAL"}:
            reason_codes.append("source_identity_unresolved")
        if not best_evidence:
            reason_codes.append("no_matching_evidence_span")
        elif score < thresholds.weak_entailment_threshold:
            reason_codes.append("weak_evidence_overlap")
        elif score < thresholds.supported_entailment_threshold:
            reason_codes.append("partial_evidence_overlap")
        if contradiction_risk:
            reason_codes.append("possible_contradiction")
        if critic_info["critic_disagreement"]:
            reason_codes.append("critic_disagreement")

        record = {
            "entailment_record_id": f"entailment_{len(records)+1:04d}",
            "schema_version": SCHEMA_VERSION,
            "advisory_only": True,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "can_mutate_source_truth": False,
            "query_id": claim.get("query_id"),
            "query": claim.get("query"),
            "claim_id": claim.get("claim_id"),
            "claim_index": claim.get("claim_index"),
            "claim_text": claim.get("claim_text"),
            "citation_ids": citation_ids,
            "page_ids": claim.get("page_ids") or [],
            "resolved_page_ids": resolved_pages,
            "source_identity_status": source_status,
            "best_evidence_span": best_evidence,
            "entailment_score": score,
            "entailment_status": entailment_status,
            "evidence_span_match_status": "MATCHED" if best_evidence else "NO_MATCH",
            "contradiction_risk": contradiction_risk,
            "critic_disagreement": critic_info["critic_disagreement"],
            "critic_statuses": critic_info["critic_statuses"],
            "human_review_escalation_recommended": weak,
            "reason_codes": reason_codes,
            "recommended_action": "human_review_or_audit_before_final_return" if weak else "eligible_for_downstream_policy_review",
            "source_claim_status": claim.get("source_claim_status"),
            "source_record_path": claim.get("source_record_path"),
        }
        records.append(record)
        if weak:
            review_escalations.append(
                {
                    "review_escalation_id": f"claim_entailment_review_{len(review_escalations)+1:04d}",
                    "entailment_record_id": record["entailment_record_id"],
                    "query_id": record["query_id"],
                    "claim_id": record["claim_id"],
                    "priority": "high" if (not citation_ids or contradiction_risk or critic_info["critic_disagreement"]) else "medium",
                    "reason_codes": reason_codes,
                    "advisory_only": True,
                    "writes_human_review_queue": False,
                    "recommended_action": "route_to_human_review_queue_candidate",
                }
            )

    status_counts = Counter(record["entailment_status"] for record in records)
    query_ids = sorted({str(r.get("query_id")) for r in records if r.get("query_id")})
    summary = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": "lexical_overlap_page_citation_source_identity_entailment_advisory_v1",
        "dynamic_final_gate_quality_status": infer_quality_status(dynamic_payload),
        "dublin_core_source_quality_status": infer_quality_status(dublin_payload),
        "hybrid_v2_quality_status": infer_quality_status(hybrid_payload),
        "retrieval_critic_quality_status": infer_quality_status(retrieval_payload),
        "evidence_sufficiency_quality_status": infer_quality_status(sufficiency_payload),
        "answer_claim_critic_quality_status": infer_quality_status(answer_claim_payload),
        "source_load_statuses": {
            "dublin_core_source_package_extension": dublin_load_status,
            "hybrid_v2": hybrid_load_status,
            "retrieval_critic": retrieval_load_status,
            "evidence_sufficiency_critic": sufficiency_load_status,
            "answer_claim_critic": answer_claim_load_status,
        },
        "claim_record_count": len(claims),
        "entailment_record_count": len(records),
        "query_count": len(query_ids),
        "evidence_candidate_count": len(evidence_candidates),
        "source_identity_page_count": len(page_identity_map),
        "source_resolved_record_count": sum(1 for r in records if r["source_identity_status"] == "SOURCE_IDENTITY_RESOLVED"),
        "source_partial_record_count": sum(1 for r in records if r["source_identity_status"] == "SOURCE_IDENTITY_PARTIAL"),
        "source_unresolved_record_count": sum(1 for r in records if r["source_identity_status"] == "SOURCE_IDENTITY_UNRESOLVED"),
        "no_page_id_record_count": sum(1 for r in records if r["source_identity_status"] == "NO_PAGE_IDS"),
        "claims_with_citation_count": sum(1 for r in records if r.get("citation_ids")),
        "claims_without_citation_count": sum(1 for r in records if not r.get("citation_ids")),
        "evidence_span_matched_count": sum(1 for r in records if r["evidence_span_match_status"] == "MATCHED"),
        "supported_entailment_count": status_counts.get("SUPPORTED_BY_CITATION_EVIDENCE", 0),
        "partial_entailment_count": status_counts.get("PARTIALLY_SUPPORTED_NEEDS_REVIEW", 0),
        "weak_or_missing_evidence_span_count": status_counts.get("WEAK_OR_MISSING_EVIDENCE_SPAN", 0),
        "missing_citation_review_count": status_counts.get("NEEDS_REVIEW_MISSING_CITATION", 0),
        "source_unresolved_review_count": status_counts.get("NEEDS_REVIEW_SOURCE_UNRESOLVED", 0),
        "contradiction_risk_record_count": sum(1 for r in records if r["contradiction_risk"]),
        "critic_disagreement_record_count": sum(1 for r in records if r["critic_disagreement"]),
        "human_review_escalation_count": len(review_escalations),
        "entailment_status_counts": dict(status_counts),
        "query_ids": query_ids,
        "unsafe_entailment_record_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "source_truth_mutations_performed": 0,
        "direct_answer_allowed_count": 0,
        "claim_proof_allowed_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "feedback_as_proof_count": 0,
        "community_as_proof_count": 0,
        "category_as_proof_count": 0,
        "retrieval_only_answer_allowed_count": 0,
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": DEFAULT_STATUS,
        "quality_status": PASS,
        "summary": summary,
        "entailment_records": records,
        "review_escalations": review_escalations,
        "quality_notes": [
            "Advisory only: entailment records cannot answer directly or prove claims.",
            "Human-review escalations are candidate records only; this module does not write the review queue.",
        ],
    }

    out_dir = Path(output_dir)
    write_json(out_dir / DEFAULT_OUTPUT_NAME, payload)
    write_markdown(out_dir / DEFAULT_MARKDOWN_NAME, payload)
    if quality:
        payload = check_claim_evidence_entailment_quality(
            report_path=out_dir / DEFAULT_OUTPUT_NAME,
            thresholds=thresholds,
            write_json_report=True,
        )
    return payload


def check_claim_evidence_entailment_quality(
    *,
    report_path: str | Path,
    thresholds: EntailmentThresholds | None = None,
    write_json_report: bool = False,
) -> dict[str, Any]:
    thresholds = thresholds or EntailmentThresholds()
    payload = load_json(report_path)
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    records = payload.get("entailment_records") if isinstance(payload.get("entailment_records"), list) else []
    failures: list[str] = []

    if len(records) < thresholds.min_entailment_records:
        failures.append(f"entailment_record_count<{thresholds.min_entailment_records}")
    if int(summary.get("claim_record_count") or 0) < thresholds.min_claim_records:
        failures.append(f"claim_record_count<{thresholds.min_claim_records}")
    if int(summary.get("query_count") or 0) < thresholds.min_queries:
        failures.append(f"query_count<{thresholds.min_queries}")
    if int(summary.get("source_resolved_record_count") or 0) < thresholds.min_source_resolved_records:
        failures.append(f"source_resolved_record_count<{thresholds.min_source_resolved_records}")
    if int(summary.get("unsafe_entailment_record_count") or 0) > thresholds.max_unsafe_records:
        failures.append("unsafe_entailment_record_count_exceeded")
    if int(summary.get("direct_answer_allowed_count") or 0) > thresholds.max_direct_answer_allowed:
        failures.append("direct_answer_allowed_count_exceeded")

    if thresholds.require_dynamic_final_gate_quality_pass and str(summary.get("dynamic_final_gate_quality_status")).upper() != PASS:
        failures.append("dynamic_final_gate_quality_not_pass")
    if thresholds.require_dublin_core_source_quality_pass and str(summary.get("dublin_core_source_quality_status")).upper() != PASS:
        failures.append("dublin_core_source_quality_not_pass")

    for key in SAFETY_ZERO_KEYS:
        if int(summary.get(key) or 0) != 0:
            failures.append(f"{key}_nonzero")

    for record in records:
        if record.get("can_answer_directly") or record.get("can_prove_claims"):
            failures.append("record_grants_answer_or_proof_permission")
            break
        if not record.get("advisory_only"):
            failures.append("record_not_advisory_only")
            break

    quality_status = FAIL if failures else PASS
    payload["quality_status"] = quality_status
    summary["status"] = quality_status
    summary["quality_status"] = quality_status
    summary["quality_failures"] = failures
    payload["summary"] = summary

    if write_json_report:
        report = Path(report_path)
        write_json(report.with_name(DEFAULT_QUALITY_NAME), payload)
        write_json(report, payload)
    return payload


def write_markdown(path: str | Path, payload: dict[str, Any]) -> Path:
    summary = payload.get("summary", {})
    lines = [
        "# TRACE-Net Claim Evidence Entailment v1",
        "",
        "Read-only advisory claim-to-citation/evidence scoring artifact.",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "quality_status",
        "claim_record_count",
        "entailment_record_count",
        "query_count",
        "supported_entailment_count",
        "partial_entailment_count",
        "weak_or_missing_evidence_span_count",
        "missing_citation_review_count",
        "source_unresolved_review_count",
        "contradiction_risk_record_count",
        "critic_disagreement_record_count",
        "human_review_escalation_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- **{key}:** {summary.get(key, payload.get(key))}")
    lines.extend(
        [
            "",
            "## Safety contract",
            "",
            "This artifact is advisory only. It cannot answer directly, cannot prove claims, and does not write to Postgres, Qdrant, OpenSearch, or source-truth stores.",
        ]
    )
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def print_quality_summary(payload: dict[str, Any]) -> None:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    print("TRACE-Net Claim Evidence Entailment v1")
    print(" Status:", payload.get("status"))
    print(" Quality status:", payload.get("quality_status"))
    for key in [
        "claim_record_count",
        "entailment_record_count",
        "query_count",
        "source_resolved_record_count",
        "claims_with_citation_count",
        "evidence_span_matched_count",
        "supported_entailment_count",
        "partial_entailment_count",
        "weak_or_missing_evidence_span_count",
        "missing_citation_review_count",
        "source_unresolved_review_count",
        "contradiction_risk_record_count",
        "critic_disagreement_record_count",
        "human_review_escalation_count",
        "unsafe_entailment_record_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}:", summary.get(key))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Claim Evidence Entailment v1.")
    parser.add_argument("--dynamic-final-gate", required=True)
    parser.add_argument("--dublin-core-source-package-extension")
    parser.add_argument("--hybrid-v2-report")
    parser.add_argument("--retrieval-critic")
    parser.add_argument("--evidence-sufficiency-critic")
    parser.add_argument("--answer-claim-critic")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--min-entailment-records", type=int, default=1)
    parser.add_argument("--min-claim-records", type=int, default=1)
    parser.add_argument("--min-queries", type=int, default=1)
    parser.add_argument("--min-source-resolved-records", type=int, default=0)
    parser.add_argument("--max-unsafe-records", type=int, default=0)
    parser.add_argument("--weak-entailment-threshold", type=float, default=0.25)
    parser.add_argument("--supported-entailment-threshold", type=float, default=0.55)
    parser.add_argument("--require-dynamic-final-gate-quality-pass", action="store_true")
    parser.add_argument("--require-dublin-core-source-quality-pass", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def thresholds_from_args(args: argparse.Namespace) -> EntailmentThresholds:
    return EntailmentThresholds(
        min_entailment_records=args.min_entailment_records,
        min_claim_records=args.min_claim_records,
        min_queries=args.min_queries,
        min_source_resolved_records=args.min_source_resolved_records,
        max_unsafe_records=args.max_unsafe_records,
        require_dynamic_final_gate_quality_pass=args.require_dynamic_final_gate_quality_pass,
        require_dublin_core_source_quality_pass=args.require_dublin_core_source_quality_pass,
        weak_entailment_threshold=args.weak_entailment_threshold,
        supported_entailment_threshold=args.supported_entailment_threshold,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    payload = build_entailment_report(
        dynamic_final_gate_path=args.dynamic_final_gate,
        dublin_core_source_package_extension_path=args.dublin_core_source_package_extension,
        hybrid_v2_report_path=args.hybrid_v2_report,
        retrieval_critic_path=args.retrieval_critic,
        evidence_sufficiency_critic_path=args.evidence_sufficiency_critic,
        answer_claim_critic_path=args.answer_claim_critic,
        output_dir=args.output_dir,
        thresholds=thresholds_from_args(args),
        quality=args.quality,
    )
    print_quality_summary(payload)
    print(" report_path:", str(Path(args.output_dir) / DEFAULT_OUTPUT_NAME))
    print(" quality_path:", str(Path(args.output_dir) / DEFAULT_QUALITY_NAME))
    return 0 if payload.get("quality_status") == PASS else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
