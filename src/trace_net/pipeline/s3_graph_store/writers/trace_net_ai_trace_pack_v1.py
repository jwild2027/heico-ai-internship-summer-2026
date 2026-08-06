"""TRACE-Net AI Trace Pack v1.

Builds compact, read-only trace packs that join graph query evidence enrichment,
retrieval, Dublin Core identity, Leiden navigation hints, Self-RAG-style critic
signals, claim-evidence entailment, and final-gate summaries.

This module does not grant answer permission. It is an inspection/audit artifact.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "trace_net_ai_trace_pack_v1"
STATUS_BUILT = "AI_TRACE_PACK_BUILT"
STATUS_PASS = "PASS"


def load_json(path: str | Path | None, *, required: bool = True) -> dict[str, Any]:
    if path in (None, ""):
        if required:
            raise FileNotFoundError("Missing required JSON path")
        return {}
    p = Path(path)
    if not p.exists():
        if required:
            raise FileNotFoundError(f"Missing JSON input: {p}")
        return {}
    with p.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise TypeError(f"Expected JSON object in {p}")
    return payload


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def write_jsonl(path: str | Path, records: Iterable[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def get_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary")
    return summary if isinstance(summary, dict) else {}


def quality_status(payload: dict[str, Any]) -> str | None:
    return payload.get("quality_status") or get_summary(payload).get("quality_status") or get_summary(payload).get("status") or payload.get("status")


def normalize_query_id(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or None


def query_id_for_part(part_number: str | None) -> str | None:
    if not part_number:
        return None
    return "part_" + normalize_query_id(part_number.replace("-", "_"))


def query_id_for_ata(ata_code: str | None) -> str | None:
    if not ata_code:
        return None
    return "ata_" + normalize_query_id(ata_code.replace("-", "_"))


def query_id_for_page(page_id: str | None) -> str | None:
    if not page_id:
        return None
    return "page_" + normalize_query_id(page_id)


def infer_query_identity(record: dict[str, Any]) -> tuple[str, str]:
    query_id = record.get("query_id")
    query = record.get("query") or record.get("query_text")
    input_payload = record.get("input") if isinstance(record.get("input"), dict) else {}
    query_type = record.get("query_type")

    if query_id:
        return str(query_id), str(query or query_id)

    if query_type == "part_lookup" or input_payload.get("part_number"):
        part = input_payload.get("part_number") or record.get("part_number")
        return query_id_for_part(str(part)) or "part_lookup", str(part)

    if query_type == "ata_browse" or input_payload.get("ata_code"):
        ata = input_payload.get("ata_code") or record.get("ata_code")
        return query_id_for_ata(str(ata)) or "ata_browse", str(ata)

    if query_type == "page_lookup" or input_payload.get("page_id_or_label") or input_payload.get("page_id"):
        page = input_payload.get("page_id_or_label") or input_payload.get("page_id") or record.get("page_id")
        return query_id_for_page(str(page)) or "page_lookup", str(page)

    inferred = normalize_query_id(str(query or query_type or "trace_query")) or "trace_query"
    return inferred, str(query or inferred)


def collect_hybrid_records(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for result in as_list(payload.get("query_results")):
        if not isinstance(result, dict):
            continue
        query_id, query_text = infer_query_identity(result)
        groups = [g for g in as_list(result.get("ranked_groups")) if isinstance(g, dict)]
        pages = []
        for group in groups:
            page_id = group.get("page_id")
            if page_id:
                pages.append(page_id)
        out[query_id] = {
            "query_id": query_id,
            "query_text": query_text,
            "query_result_present": True,
            "ranked_group_count": len(groups),
            "top_page_ids": list(dict.fromkeys(pages))[:15],
            "exact_hit_group_count": sum(1 for g in groups if (g.get("exact_hit_count") or 0) > 0),
            "semantic_group_count": sum(1 for g in groups if (g.get("semantic_group_count") or 0) > 0),
            "top_groups": [
                {
                    "rank": g.get("hybrid_v2_rank"),
                    "page_id": g.get("page_id"),
                    "score": g.get("hybrid_v2_score"),
                    "exact_hit_count": g.get("exact_hit_count"),
                    "semantic_group_count": g.get("semantic_group_count"),
                    "part_numbers": as_list(g.get("part_numbers"))[:10],
                }
                for g in groups[:5]
            ],
        }
    return out


def collect_graph_records(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records = payload.get("enriched_query_records") or payload.get("query_records") or []
    out: dict[str, dict[str, Any]] = {}
    for record in as_list(records):
        if not isinstance(record, dict):
            continue
        query_id, query_text = infer_query_identity(record)
        pages = [p for p in as_list(record.get("pages")) if isinstance(p, dict)]
        page_ids = [p.get("page_id") for p in pages if p.get("page_id")]
        channel_counter: Counter[str] = Counter()
        source_resolved = 0
        dublin_core = 0
        leiden = 0
        review_flags: list[dict[str, Any]] = []
        for page in pages:
            channel_counter.update(as_list(page.get("channels")))
            if page.get("source_resolved"):
                source_resolved += 1
            if page.get("dublin_core_source_identity"):
                dublin_core += 1
            if page.get("leiden_navigation_hints"):
                leiden += 1
            for ev in as_list(page.get("evidence_records")):
                if not isinstance(ev, dict):
                    continue
                if ev.get("human_review_escalation_recommended") or ev.get("page_alignment_status") == "PAGE_MISMATCH_REVIEW":
                    review_flags.append(
                        {
                            "page_id": page.get("page_id"),
                            "channel": ev.get("channel"),
                            "claim_id": ev.get("claim_id"),
                            "page_alignment_status": ev.get("page_alignment_status"),
                            "reason_codes": as_list(ev.get("reason_codes")),
                        }
                    )
        review_records = [r for r in as_list(record.get("review_records")) if isinstance(r, dict)]
        for r in review_records:
            review_flags.append(
                {
                    "page_id": (as_list(r.get("page_ids")) or [None])[0],
                    "channel": "claim_evidence_entailment",
                    "claim_id": r.get("claim_id"),
                    "page_alignment_status": r.get("page_alignment_status"),
                    "reason_codes": as_list(r.get("reason_codes")),
                }
            )
        out[query_id] = {
            "query_id": query_id,
            "query_text": query_text,
            "query_type": record.get("query_type"),
            "plan_id": record.get("plan_id"),
            "original_graph_page_count": record.get("original_graph_page_count") or record.get("result_count"),
            "enriched_page_count": record.get("enriched_page_count") or len(page_ids),
            "source_resolved_page_count": record.get("source_resolved_page_count") or source_resolved,
            "dublin_core_identity_page_count": dublin_core,
            "leiden_navigation_hint_page_count": leiden,
            "channel_counts": dict(channel_counter or Counter(record.get("channel_counts") or {})),
            "page_ids": list(dict.fromkeys(page_ids))[:50],
            "sample_pages": [
                {
                    "page_id": p.get("page_id"),
                    "channels": as_list(p.get("channels")),
                    "source_resolved": bool(p.get("source_resolved")),
                    "has_dublin_core_identity": bool(p.get("dublin_core_source_identity")),
                    "leiden_hint_count": len(as_list(p.get("leiden_navigation_hints"))),
                    "evidence_record_count": len(as_list(p.get("evidence_records"))),
                }
                for p in pages[:10]
            ],
            "review_flags": review_flags[:25],
            "can_answer_directly": False,
            "can_prove_claims": False,
            "retrieval_only": True,
        }
    return out


def collect_critic_records(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records = payload.get("critic_records") or payload.get("retrieval_critic_records") or payload.get("sufficiency_records") or payload.get("answer_records") or payload.get("records") or []
    out: dict[str, dict[str, Any]] = {}
    for record in as_list(records):
        if not isinstance(record, dict):
            continue
        query_id, query_text = infer_query_identity(record)
        status = record.get("critic_status") or record.get("retrieval_critic_status") or record.get("sufficiency_status") or record.get("answer_claim_status") or record.get("status")
        out[query_id] = {
            "query_id": query_id,
            "query_text": query_text,
            "status": status,
            "recommended_action": record.get("recommended_action"),
            "reason_codes": as_list(record.get("reason_codes")),
            "issues": as_list(record.get("issues")) or as_list(record.get("warnings")),
            "can_answer_directly": bool(record.get("can_answer_directly", False)),
            "can_prove_claims": bool(record.get("can_prove_claims", False)),
        }
    return out


def collect_entailment_records(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records = payload.get("entailment_records") or payload.get("records") or []
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in as_list(records):
        if not isinstance(record, dict):
            continue
        query_id, _ = infer_query_identity(record)
        groups[query_id].append(record)
    out: dict[str, dict[str, Any]] = {}
    for query_id, recs in groups.items():
        status_counts = Counter(r.get("entailment_status") for r in recs)
        review_count = sum(1 for r in recs if r.get("human_review_escalation_recommended"))
        mismatch_count = sum(1 for r in recs if r.get("page_alignment_status") == "PAGE_MISMATCH_REVIEW" or _page_mismatch(r))
        out[query_id] = {
            "query_id": query_id,
            "claim_count": len(recs),
            "claims_with_citation_count": sum(1 for r in recs if r.get("citation_ids") or (r.get("best_evidence_span") or {}).get("citation_ids")),
            "entailment_status_counts": dict(status_counts),
            "supported_claim_count": status_counts.get("SUPPORTED_BY_CITATION_EVIDENCE", 0),
            "partial_claim_count": status_counts.get("PARTIALLY_SUPPORTED_NEEDS_REVIEW", 0),
            "human_review_escalation_count": review_count,
            "page_mismatch_review_count": mismatch_count,
            "sample_claims": [
                {
                    "claim_id": r.get("claim_id"),
                    "claim_text": r.get("claim_text"),
                    "page_ids": as_list(r.get("page_ids")),
                    "best_evidence_page_ids": as_list((r.get("best_evidence_span") or {}).get("page_ids")),
                    "entailment_score": r.get("entailment_score"),
                    "entailment_status": r.get("entailment_status"),
                    "human_review_escalation_recommended": bool(r.get("human_review_escalation_recommended")),
                    "reason_codes": as_list(r.get("reason_codes")),
                }
                for r in recs[:8]
            ],
        }
    return out


def _page_mismatch(record: dict[str, Any]) -> bool:
    claim_pages = set(as_list(record.get("page_ids")))
    span = record.get("best_evidence_span") or {}
    evidence_pages = set(as_list(span.get("page_ids")))
    return bool(claim_pages and evidence_pages and not (claim_pages & evidence_pages))


def collect_dynamic_records(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    candidate_keys = ["records", "dynamic_records", "results", "query_results", "dynamic_gate_records", "policy_records"]
    for key in candidate_keys:
        for record in as_list(payload.get(key)):
            if not isinstance(record, dict):
                continue
            query_id, query_text = infer_query_identity(record)
            status = record.get("final_gate_status") or record.get("answer_status") or record.get("status")
            out[query_id] = {
                "query_id": query_id,
                "query_text": query_text,
                "status": status,
                "final_claim_count": len(as_list(record.get("final_claims") or record.get("claims"))),
                "page_ids": as_list(record.get("page_ids") or record.get("supporting_page_ids")),
            }
    return out


def build_trace_packs(
    *,
    graph_query_api_v1_1: dict[str, Any],
    graph_query_evidence_enrichment: dict[str, Any],
    hybrid_v2: dict[str, Any],
    dynamic_final_gate: dict[str, Any],
    retrieval_critic: dict[str, Any],
    evidence_sufficiency_critic: dict[str, Any],
    answer_claim_critic: dict[str, Any],
    claim_evidence_entailment: dict[str, Any],
    dublin_core_source_package_extension: dict[str, Any],
    leiden_navigation_metadata_bridge: dict[str, Any],
    final_return_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    graph_records = collect_graph_records(graph_query_evidence_enrichment)
    hybrid_records = collect_hybrid_records(hybrid_v2)
    dynamic_records = collect_dynamic_records(dynamic_final_gate)
    retrieval_critic_records = collect_critic_records(retrieval_critic)
    sufficiency_records = collect_critic_records(evidence_sufficiency_critic)
    answer_claim_records = collect_critic_records(answer_claim_critic)
    entailment_records = collect_entailment_records(claim_evidence_entailment)
    final_policy_records = collect_dynamic_records(final_return_policy or {})

    query_ids: list[str] = []
    for source in [hybrid_records, graph_records, dynamic_records, retrieval_critic_records, sufficiency_records, answer_claim_records, entailment_records, final_policy_records]:
        for query_id in source:
            if query_id not in query_ids:
                query_ids.append(query_id)

    trace_packs: list[dict[str, Any]] = []
    review_records: list[dict[str, Any]] = []

    for query_id in query_ids:
        query_text = (
            (hybrid_records.get(query_id) or {}).get("query_text")
            or (graph_records.get(query_id) or {}).get("query_text")
            or (retrieval_critic_records.get(query_id) or {}).get("query_text")
            or query_id
        )
        graph = graph_records.get(query_id) or {}
        hybrid = hybrid_records.get(query_id) or {}
        retrieval_critic_record = retrieval_critic_records.get(query_id) or {}
        sufficiency = sufficiency_records.get(query_id) or {}
        answer_claim = answer_claim_records.get(query_id) or {}
        entailment = entailment_records.get(query_id) or {}
        dynamic = dynamic_records.get(query_id) or {}
        final_policy = final_policy_records.get(query_id) or {}

        critic_statuses = {
            "retrieval_critic": retrieval_critic_record.get("status"),
            "evidence_sufficiency_critic": sufficiency.get("status"),
            "answer_claim_critic": answer_claim.get("status"),
        }

        needs_review_reasons: list[str] = []
        if retrieval_critic_record.get("status") and "audit" in str(retrieval_critic_record.get("status")).lower():
            needs_review_reasons.append("retrieval_critic_audit")
        if entailment.get("human_review_escalation_count", 0):
            needs_review_reasons.append("claim_evidence_review")
        if entailment.get("page_mismatch_review_count", 0):
            needs_review_reasons.append("page_alignment_review")
        if graph.get("review_flags"):
            needs_review_reasons.append("graph_evidence_review_flags")

        trace_status = "TRACE_PACK_READY"
        if needs_review_reasons:
            trace_status = "TRACE_PACK_REVIEW_RECOMMENDED"
        if retrieval_critic_record.get("status") == "final_gate_already_authorized" and not needs_review_reasons:
            trace_status = "TRACE_PACK_FINAL_GATE_AUTHORIZED_NO_REVIEW_FLAGS"

        page_ids = list(dict.fromkeys(
            as_list(graph.get("page_ids"))
            + as_list(hybrid.get("top_page_ids"))
            + as_list(dynamic.get("page_ids"))
        ))

        trace_pack = {
            "schema_version": SCHEMA_VERSION,
            "trace_pack_id": f"trace_pack::{query_id}",
            "query_id": query_id,
            "query": query_text,
            "trace_status": trace_status,
            "needs_review": bool(needs_review_reasons),
            "review_reason_codes": needs_review_reasons,
            "page_ids": page_ids[:50],
            "source_trace_summary": {
                "source_resolved_page_count": graph.get("source_resolved_page_count", 0),
                "dublin_core_identity_page_count": graph.get("dublin_core_identity_page_count", 0),
                "dublin_core_source_quality_status": quality_status(dublin_core_source_package_extension),
                "source_package_page_count": get_summary(dublin_core_source_package_extension).get("page_record_count") or get_summary(dublin_core_source_package_extension).get("pages_with_source_package_entry_count"),
            },
            "retrieval_summary": {
                "hybrid_query_present": bool(hybrid),
                "ranked_group_count": hybrid.get("ranked_group_count", 0),
                "exact_hit_group_count": hybrid.get("exact_hit_group_count", 0),
                "semantic_group_count": hybrid.get("semantic_group_count", 0),
                "top_groups": hybrid.get("top_groups", []),
            },
            "graph_trace_summary": {
                "graph_query_present": bool(graph),
                "plan_id": graph.get("plan_id"),
                "query_type": graph.get("query_type"),
                "original_graph_page_count": graph.get("original_graph_page_count", 0),
                "enriched_page_count": graph.get("enriched_page_count", 0),
                "channel_counts": graph.get("channel_counts", {}),
                "sample_pages": graph.get("sample_pages", []),
                "review_flags": graph.get("review_flags", []),
            },
            "leiden_navigation_summary": {
                "leiden_navigation_bridge_quality_status": quality_status(leiden_navigation_metadata_bridge),
                "leiden_navigation_hint_page_count": graph.get("leiden_navigation_hint_page_count", 0),
                "retrieval_navigation_hint_count": get_summary(leiden_navigation_metadata_bridge).get("retrieval_navigation_hint_count"),
                "page_navigation_hint_count": get_summary(leiden_navigation_metadata_bridge).get("page_navigation_hint_count"),
            },
            "final_gate_summary": {
                "dynamic_final_gate_quality_status": quality_status(dynamic_final_gate),
                "dynamic_query_status": dynamic.get("status"),
                "final_policy_status": final_policy.get("status"),
                "dynamic_summary_counts": {
                    "final_answer_allowed_count": get_summary(dynamic_final_gate).get("final_answer_allowed_count"),
                    "dynamic_final_gate_approved_count": get_summary(dynamic_final_gate).get("dynamic_final_gate_approved_count"),
                    "final_artifact_answer_count": get_summary(dynamic_final_gate).get("final_artifact_answer_count"),
                    "blocked_claim_count": get_summary(dynamic_final_gate).get("blocked_claim_count"),
                },
            },
            "critic_summary": {
                "retrieval_critic_quality_status": quality_status(retrieval_critic),
                "evidence_sufficiency_critic_quality_status": quality_status(evidence_sufficiency_critic),
                "answer_claim_critic_quality_status": quality_status(answer_claim_critic),
                "critic_statuses": critic_statuses,
                "retrieval_critic_action": retrieval_critic_record.get("recommended_action"),
                "retrieval_critic_reason_codes": retrieval_critic_record.get("reason_codes", []),
            },
            "claim_evidence_summary": {
                "claim_evidence_entailment_quality_status": quality_status(claim_evidence_entailment),
                "claim_count": entailment.get("claim_count", 0),
                "claims_with_citation_count": entailment.get("claims_with_citation_count", 0),
                "entailment_status_counts": entailment.get("entailment_status_counts", {}),
                "supported_claim_count": entailment.get("supported_claim_count", 0),
                "partial_claim_count": entailment.get("partial_claim_count", 0),
                "human_review_escalation_count": entailment.get("human_review_escalation_count", 0),
                "page_mismatch_review_count": entailment.get("page_mismatch_review_count", 0),
                "sample_claims": entailment.get("sample_claims", []),
            },
            "safety_contract": {
                "no_postgres_writes": True,
                "no_qdrant_writes": True,
                "no_opensearch_writes": True,
                "no_source_truth_mutation": True,
                "no_answer_permission": True,
                "no_claim_proof_authority": True,
            },
            "retrieval_only": True,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
        }
        trace_packs.append(trace_pack)
        for reason in needs_review_reasons:
            review_records.append(
                {
                    "trace_pack_id": trace_pack["trace_pack_id"],
                    "query_id": query_id,
                    "query": query_text,
                    "review_reason": reason,
                    "retrieval_only": True,
                    "can_answer_directly": False,
                    "can_prove_claims": False,
                }
            )

    summary = summarize_trace_packs(
        trace_packs=trace_packs,
        review_records=review_records,
        sources={
            "graph_query_api_v1_1": graph_query_api_v1_1,
            "graph_query_evidence_enrichment": graph_query_evidence_enrichment,
            "hybrid_v2": hybrid_v2,
            "dynamic_final_gate": dynamic_final_gate,
            "retrieval_critic": retrieval_critic,
            "evidence_sufficiency_critic": evidence_sufficiency_critic,
            "answer_claim_critic": answer_claim_critic,
            "claim_evidence_entailment": claim_evidence_entailment,
            "dublin_core_source_package_extension": dublin_core_source_package_extension,
            "leiden_navigation_metadata_bridge": leiden_navigation_metadata_bridge,
            "final_return_policy": final_return_policy or {},
        },
    )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "quality_status": STATUS_PASS,
        "summary": summary,
        "trace_pack_records": trace_packs,
        "review_records": review_records,
        "safety_contract": {
            "no_postgres_writes": True,
            "no_qdrant_writes": True,
            "no_opensearch_writes": True,
            "no_source_truth_mutation": True,
            "no_answer_permission": True,
            "no_claim_proof_authority": True,
        },
    }
    return payload


def summarize_trace_packs(*, trace_packs: list[dict[str, Any]], review_records: list[dict[str, Any]], sources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    trace_pack_count = len(trace_packs)
    with_graph = sum(1 for p in trace_packs if p["graph_trace_summary"].get("graph_query_present"))
    with_hybrid = sum(1 for p in trace_packs if p["retrieval_summary"].get("hybrid_query_present"))
    with_dublin = sum(1 for p in trace_packs if (p["source_trace_summary"].get("dublin_core_identity_page_count") or 0) > 0)
    with_leiden = sum(1 for p in trace_packs if (p["leiden_navigation_summary"].get("leiden_navigation_hint_page_count") or 0) > 0)
    with_claims = sum(1 for p in trace_packs if (p["claim_evidence_summary"].get("claim_count") or 0) > 0)
    needs_review = sum(1 for p in trace_packs if p.get("needs_review"))
    review_reason_counts = Counter()
    trace_status_counts = Counter(p.get("trace_status") for p in trace_packs)
    channel_counts = Counter()
    critic_status_counts = Counter()
    for p in trace_packs:
        review_reason_counts.update(p.get("review_reason_codes") or [])
        channel_counts.update(p["graph_trace_summary"].get("channel_counts") or {})
        critic_status_counts.update(v for v in p["critic_summary"].get("critic_statuses", {}).values() if v)

    return {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_PASS,
        "source_quality_statuses": {name: quality_status(payload) for name, payload in sources.items() if payload},
        "trace_pack_count": trace_pack_count,
        "trace_pack_with_graph_context_count": with_graph,
        "trace_pack_with_hybrid_retrieval_count": with_hybrid,
        "trace_pack_with_dublin_core_identity_count": with_dublin,
        "trace_pack_with_leiden_navigation_count": with_leiden,
        "trace_pack_with_claim_entailment_count": with_claims,
        "review_recommended_trace_pack_count": needs_review,
        "review_record_count": len(review_records),
        "trace_status_counts": dict(trace_status_counts),
        "review_reason_counts": dict(review_reason_counts),
        "channel_counts": dict(channel_counts),
        "critic_status_counts": dict(critic_status_counts),
        "community_as_proof_count": 0,
        "category_as_proof_count": 0,
        "feedback_as_proof_count": 0,
        "retrieval_only_answer_allowed_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }


@dataclass
class TracePackThresholds:
    min_trace_packs: int = 1
    min_trace_packs_with_graph_context: int = 1
    min_trace_packs_with_dublin_core_identity: int = 1
    min_trace_packs_with_leiden_navigation: int = 0
    min_trace_packs_with_claim_entailment: int = 0
    max_community_as_proof: int = 0
    max_category_as_proof: int = 0
    max_retrieval_only_answer_allowed: int = 0
    max_source_truth_mutation_allowed: int = 0
    require_graph_api_quality_pass: bool = False
    require_enrichment_quality_pass: bool = False
    require_hybrid_v2_quality_pass: bool = False
    require_dynamic_final_gate_quality_pass: bool = False
    require_claim_entailment_quality_pass: bool = False
    require_no_answer_permission: bool = False


def check_trace_pack_quality(report: dict[str, Any], thresholds: TracePackThresholds) -> dict[str, Any]:
    summary = get_summary(report)
    failures: list[str] = []

    def require_count(key: str, minimum: int) -> None:
        if int(summary.get(key) or 0) < minimum:
            failures.append(f"{key} below minimum {minimum}: {summary.get(key)}")

    def require_max(key: str, maximum: int) -> None:
        if int(summary.get(key) or 0) > maximum:
            failures.append(f"{key} above maximum {maximum}: {summary.get(key)}")

    require_count("trace_pack_count", thresholds.min_trace_packs)
    require_count("trace_pack_with_graph_context_count", thresholds.min_trace_packs_with_graph_context)
    require_count("trace_pack_with_dublin_core_identity_count", thresholds.min_trace_packs_with_dublin_core_identity)
    require_count("trace_pack_with_leiden_navigation_count", thresholds.min_trace_packs_with_leiden_navigation)
    require_count("trace_pack_with_claim_entailment_count", thresholds.min_trace_packs_with_claim_entailment)

    require_max("community_as_proof_count", thresholds.max_community_as_proof)
    require_max("category_as_proof_count", thresholds.max_category_as_proof)
    require_max("retrieval_only_answer_allowed_count", thresholds.max_retrieval_only_answer_allowed)
    require_max("source_truth_mutation_allowed_count", thresholds.max_source_truth_mutation_allowed)

    source_statuses = summary.get("source_quality_statuses") if isinstance(summary.get("source_quality_statuses"), dict) else {}
    if thresholds.require_graph_api_quality_pass and source_statuses.get("graph_query_api_v1_1") != STATUS_PASS:
        failures.append("graph_query_api_v1_1 quality is not PASS")
    if thresholds.require_enrichment_quality_pass and source_statuses.get("graph_query_evidence_enrichment") != STATUS_PASS:
        failures.append("graph_query_evidence_enrichment quality is not PASS")
    if thresholds.require_hybrid_v2_quality_pass and source_statuses.get("hybrid_v2") != STATUS_PASS:
        failures.append("hybrid_v2 quality is not PASS")
    if thresholds.require_dynamic_final_gate_quality_pass and source_statuses.get("dynamic_final_gate") != STATUS_PASS:
        failures.append("dynamic_final_gate quality is not PASS")
    if thresholds.require_claim_entailment_quality_pass and source_statuses.get("claim_evidence_entailment") != STATUS_PASS:
        failures.append("claim_evidence_entailment quality is not PASS")

    if thresholds.require_no_answer_permission:
        if int(summary.get("can_answer_directly_count") or 0) != 0:
            failures.append("trace pack granted direct answer permission")
        if int(summary.get("can_prove_claims_count") or 0) != 0:
            failures.append("trace pack granted claim proof authority")

    status = STATUS_PASS if not failures else "FAIL"
    quality = {
        "schema_version": SCHEMA_VERSION + "_quality",
        "status": status,
        "quality_status": status,
        "failures": failures,
        "summary": summary,
    }
    return quality


def build_markdown(report: dict[str, Any]) -> str:
    summary = get_summary(report)
    lines = [
        "# TRACE-Net AI Trace Pack v1",
        "",
        f"Status: `{report.get('status')}`",
        f"Quality status: `{report.get('quality_status')}`",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "trace_pack_count",
        "trace_pack_with_graph_context_count",
        "trace_pack_with_hybrid_retrieval_count",
        "trace_pack_with_dublin_core_identity_count",
        "trace_pack_with_leiden_navigation_count",
        "trace_pack_with_claim_entailment_count",
        "review_recommended_trace_pack_count",
        "review_record_count",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.extend([
        "",
        "Safety: this artifact is read-only and cannot answer directly or prove claims.",
        "",
        "## Trace packs",
        "",
    ])
    for pack in report.get("trace_pack_records", [])[:20]:
        lines.append(f"- `{pack.get('query_id')}` — {pack.get('trace_status')} — review={pack.get('needs_review')}")
    lines.append("")
    return "\n".join(lines)


def print_trace_pack_summary(report: dict[str, Any]) -> None:
    summary = get_summary(report)
    print("TRACE-Net AI Trace Pack v1")
    print(f" Status: {report.get('status')}")
    print(f" Quality status: {report.get('quality_status')}")
    for key in [
        "trace_pack_count",
        "trace_pack_with_graph_context_count",
        "trace_pack_with_hybrid_retrieval_count",
        "trace_pack_with_dublin_core_identity_count",
        "trace_pack_with_leiden_navigation_count",
        "trace_pack_with_claim_entailment_count",
        "review_recommended_trace_pack_count",
        "review_record_count",
        "community_as_proof_count",
        "category_as_proof_count",
        "retrieval_only_answer_allowed_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ]:
        print(f" {key}: {summary.get(key)}")


def build_from_paths(args: argparse.Namespace) -> dict[str, Any]:
    report = build_trace_packs(
        graph_query_api_v1_1=load_json(args.graph_query_api_v1_1),
        graph_query_evidence_enrichment=load_json(args.graph_query_evidence_enrichment),
        hybrid_v2=load_json(args.hybrid_v2_report),
        dynamic_final_gate=load_json(args.dynamic_final_gate),
        retrieval_critic=load_json(args.retrieval_critic),
        evidence_sufficiency_critic=load_json(args.evidence_sufficiency_critic, required=False),
        answer_claim_critic=load_json(args.answer_claim_critic, required=False),
        claim_evidence_entailment=load_json(args.claim_evidence_entailment),
        dublin_core_source_package_extension=load_json(args.dublin_core_source_package_extension),
        leiden_navigation_metadata_bridge=load_json(args.leiden_navigation_metadata_bridge),
        final_return_policy=load_json(args.final_return_policy, required=False),
    )
    thresholds = thresholds_from_args(args)
    quality = check_trace_pack_quality(report, thresholds)
    report["quality_status"] = quality["quality_status"]
    report["summary"]["status"] = quality["quality_status"]
    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    report_path = outdir / "trace_net_ai_trace_pack_v1.json"
    quality_path = outdir / "trace_net_ai_trace_pack_v1_quality.json"
    records_path = outdir / "trace_net_ai_trace_pack_v1_records.jsonl"
    review_path = outdir / "trace_net_ai_trace_pack_v1_review_records.jsonl"
    md_path = outdir / "trace_net_ai_trace_pack_v1.md"
    write_json(report_path, report)
    write_json(quality_path, quality)
    write_jsonl(records_path, report.get("trace_pack_records", []))
    write_jsonl(review_path, report.get("review_records", []))
    md_path.write_text(build_markdown(report), encoding="utf-8")
    report["report_path"] = str(report_path)
    report["quality_path"] = str(quality_path)
    return report


def thresholds_from_args(args: argparse.Namespace) -> TracePackThresholds:
    return TracePackThresholds(
        min_trace_packs=args.min_trace_packs,
        min_trace_packs_with_graph_context=args.min_trace_packs_with_graph_context,
        min_trace_packs_with_dublin_core_identity=args.min_trace_packs_with_dublin_core_identity,
        min_trace_packs_with_leiden_navigation=args.min_trace_packs_with_leiden_navigation,
        min_trace_packs_with_claim_entailment=args.min_trace_packs_with_claim_entailment,
        max_community_as_proof=args.max_community_as_proof,
        max_category_as_proof=args.max_category_as_proof,
        max_retrieval_only_answer_allowed=args.max_retrieval_only_answer_allowed,
        max_source_truth_mutation_allowed=args.max_source_truth_mutation_allowed,
        require_graph_api_quality_pass=args.require_graph_api_quality_pass,
        require_enrichment_quality_pass=args.require_enrichment_quality_pass,
        require_hybrid_v2_quality_pass=args.require_hybrid_v2_quality_pass,
        require_dynamic_final_gate_quality_pass=args.require_dynamic_final_gate_quality_pass,
        require_claim_entailment_quality_pass=args.require_claim_entailment_quality_pass,
        require_no_answer_permission=args.require_no_answer_permission,
    )


def add_threshold_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-trace-packs", type=int, default=1)
    parser.add_argument("--min-trace-packs-with-graph-context", type=int, default=1)
    parser.add_argument("--min-trace-packs-with-dublin-core-identity", type=int, default=1)
    parser.add_argument("--min-trace-packs-with-leiden-navigation", type=int, default=0)
    parser.add_argument("--min-trace-packs-with-claim-entailment", type=int, default=0)
    parser.add_argument("--max-community-as-proof", type=int, default=0)
    parser.add_argument("--max-category-as-proof", type=int, default=0)
    parser.add_argument("--max-retrieval-only-answer-allowed", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-graph-api-quality-pass", action="store_true")
    parser.add_argument("--require-enrichment-quality-pass", action="store_true")
    parser.add_argument("--require-hybrid-v2-quality-pass", action="store_true")
    parser.add_argument("--require-dynamic-final-gate-quality-pass", action="store_true")
    parser.add_argument("--require-claim-entailment-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net AI Trace Pack v1")
    parser.add_argument("--graph-query-api-v1-1", required=True)
    parser.add_argument("--graph-query-evidence-enrichment", required=True)
    parser.add_argument("--hybrid-v2-report", required=True)
    parser.add_argument("--dynamic-final-gate", required=True)
    parser.add_argument("--retrieval-critic", required=True)
    parser.add_argument("--evidence-sufficiency-critic")
    parser.add_argument("--answer-claim-critic")
    parser.add_argument("--claim-evidence-entailment", required=True)
    parser.add_argument("--dublin-core-source-package-extension", required=True)
    parser.add_argument("--leiden-navigation-metadata-bridge", required=True)
    parser.add_argument("--final-return-policy")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--quality", action="store_true")
    add_threshold_args(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = build_from_paths(args)
    print_trace_pack_summary(report)
    print(" report_path:", report.get("report_path"))
    print(" quality_path:", report.get("quality_path"))
    return 0 if report.get("quality_status") == STATUS_PASS else 2


if __name__ == "__main__":
    raise SystemExit(main())
