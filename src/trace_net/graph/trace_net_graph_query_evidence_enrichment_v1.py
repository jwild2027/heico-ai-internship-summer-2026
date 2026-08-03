
"""TRACE-Net Graph Query Evidence Enrichment v1.

Read-only enrichment layer for controlled graph query results.

This module keeps the graph query helper/API safety contract intact: it never
writes to Postgres, Qdrant, OpenSearch, or source truth, and it never grants
answer permission or claim-proof authority. It only enriches graph lookup
records with retrieval/evidence navigation metadata from TRACE-Net v2 artifacts.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "trace_net_graph_query_evidence_enrichment_v1"
STATUS_BUILT = "GRAPH_QUERY_EVIDENCE_ENRICHMENT_BUILT"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"

PART_RE = re.compile(r"\b\d{3}-\d{5}(?:-\d{3})?\b")
ATA_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")

DEFAULT_SAFETY = {
    "no_postgres_writes": True,
    "no_qdrant_writes": True,
    "no_opensearch_writes": True,
    "no_source_truth_mutation": True,
    "no_answer_permission": True,
    "no_claim_proof_authority": True,
}


@dataclass
class Thresholds:
    min_query_records: int = 1
    min_enriched_query_records: int = 0
    min_enriched_page_records: int = 1
    min_source_resolved_pages: int = 1
    min_evidence_enriched_pages: int = 0
    min_exact_evidence_pages: int = 0
    min_hybrid_evidence_pages: int = 0
    min_leiden_navigation_pages: int = 0
    min_claim_trace_pages: int = 0
    require_helper_quality_pass: bool = False
    require_graph_query_helper_quality_pass: bool = False
    require_opensearch_quality_pass: bool = False
    require_hybrid_v2_quality_pass: bool = False
    require_leiden_bridge_quality_pass: bool = False
    require_dublin_core_quality_pass: bool = False
    require_claim_entailment_quality_pass: bool = False
    require_no_answer_permission: bool = False
    max_community_as_proof_count: int = 0
    max_category_as_proof_count: int = 0
    max_retrieval_only_answer_allowed_count: int = 0
    max_can_answer_directly_count: int = 0
    max_can_prove_claims_count: int = 0
    max_source_truth_mutation_allowed_count: int = 0


def thresholds_to_mapping(thresholds: Mapping[str, Any] | Thresholds | None) -> dict[str, Any]:
    if thresholds is None:
        return {}
    if isinstance(thresholds, Thresholds):
        return {
            "min_enriched_query_records": thresholds.min_enriched_query_records,
            "min_query_records": thresholds.min_query_records,
            "min_enriched_page_records": thresholds.min_enriched_page_records,
            "min_source_resolved_pages": thresholds.min_source_resolved_pages,
            "min_evidence_enriched_pages": thresholds.min_evidence_enriched_pages,
            "min_exact_evidence_pages": thresholds.min_exact_evidence_pages,
            "min_hybrid_evidence_pages": thresholds.min_hybrid_evidence_pages,
            "min_leiden_navigation_pages": thresholds.min_leiden_navigation_pages,
            "min_claim_trace_pages": thresholds.min_claim_trace_pages,
            "require_graph_query_helper_quality_pass": thresholds.require_graph_query_helper_quality_pass or thresholds.require_helper_quality_pass,
            "require_opensearch_quality_pass": thresholds.require_opensearch_quality_pass,
            "require_hybrid_v2_quality_pass": thresholds.require_hybrid_v2_quality_pass,
            "require_leiden_bridge_quality_pass": thresholds.require_leiden_bridge_quality_pass,
            "require_dublin_core_quality_pass": thresholds.require_dublin_core_quality_pass,
            "require_claim_entailment_quality_pass": thresholds.require_claim_entailment_quality_pass,
            "require_no_answer_permission": thresholds.require_no_answer_permission,
            "max_community_as_proof_count": thresholds.max_community_as_proof_count,
            "max_category_as_proof_count": thresholds.max_category_as_proof_count,
            "max_retrieval_only_answer_allowed_count": thresholds.max_retrieval_only_answer_allowed_count,
            "max_can_answer_directly_count": thresholds.max_can_answer_directly_count,
            "max_can_prove_claims_count": thresholds.max_can_prove_claims_count,
            "max_source_truth_mutation_allowed_count": thresholds.max_source_truth_mutation_allowed_count,
        }
    return dict(thresholds)



def load_json(path: str | Path | None, *, optional: bool = False) -> dict[str, Any]:
    if path in (None, ""):
        if optional:
            return {}
        raise FileNotFoundError("Missing JSON path")
    p = Path(path)
    if not p.exists():
        if optional:
            return {}
        raise FileNotFoundError(f"Missing JSON input: {p}")
    with p.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise TypeError(f"Expected JSON object in {p}")
    return payload


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def write_jsonl(path: str | Path, records: Iterable[Mapping[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with p.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def quality_status(payload: Mapping[str, Any]) -> str | None:
    value = payload.get("quality_status") or payload.get("status")
    if isinstance(value, str):
        return value
    summary = payload.get("summary")
    if isinstance(summary, dict):
        value = summary.get("quality_status") or summary.get("status")
        if isinstance(value, str):
            return value
    return None


def is_quality_pass(payload: Mapping[str, Any]) -> bool:
    status = quality_status(payload)
    return isinstance(status, str) and status.upper() == "PASS"


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def text_from_record(record: Mapping[str, Any]) -> str:
    chunks: list[str] = []
    for key in ("text", "search_text", "content", "body", "chunk_text", "summary", "text_preview", "title"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            chunks.append(value)
    if not chunks:
        # Some docs store short searchable snippets in nested payload/metadata fields.
        for container_key in ("payload", "metadata", "source_trace"):
            nested = record.get(container_key)
            if isinstance(nested, dict):
                for key in ("text", "search_text", "content", "summary", "title"):
                    value = nested.get(key)
                    if isinstance(value, str) and value.strip():
                        chunks.append(value)
    return "\n".join(chunks)


def normalize_page_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                nested = first_non_empty(item.get("page_id"), item.get("source_page_id"))
                if isinstance(nested, str) and nested.strip():
                    out.append(nested.strip())
        return dedupe(out)
    return []


def page_ids_from_record(record: Mapping[str, Any]) -> list[str]:
    trace = record.get("source_trace") if isinstance(record.get("source_trace"), dict) else {}
    candidates: list[str] = []
    for value in (
        record.get("page_id"),
        record.get("page_ids"),
        record.get("source_page_id"),
        record.get("source_page_ids"),
        record.get("parent_page_id"),
        trace.get("page_id") if isinstance(trace, dict) else None,
        trace.get("page_ids") if isinstance(trace, dict) else None,
        trace.get("source_page_id") if isinstance(trace, dict) else None,
        trace.get("source_page_ids") if isinstance(trace, dict) else None,
    ):
        candidates.extend(normalize_page_ids(value))
    return dedupe(candidates)


def dedupe(values: Iterable[Any]) -> list[Any]:
    seen: set[str] = set()
    out: list[Any] = []
    for value in values:
        key = json.dumps(value, sort_keys=True, default=str) if isinstance(value, (dict, list)) else str(value)
        if key not in seen:
            seen.add(key)
            out.append(value)
    return out


def collect_documents(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    keys = (
        "documents",
        "opensearch_documents",
        "safe_documents",
        "records",
        "index_documents",
        "adapter_documents",
    )
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    # Avoid silently missing nested but obvious document lists.
    for value in payload.values():
        if isinstance(value, dict):
            for key in keys:
                nested = value.get(key)
                if isinstance(nested, list):
                    return [x for x in nested if isinstance(x, dict)]
    return []


def extract_page_records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    for key in ("page_records", "pages", "records", "dublin_core_page_records"):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def make_dublin_identity_map(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    identities: dict[str, dict[str, Any]] = {}
    for record in extract_page_records(payload):
        dc = record.get("dc") if isinstance(record.get("dc"), dict) else {}
        page_id = first_non_empty(record.get("page_id"), dc.get("dc:identifier"), dc.get("identifier"), record.get("dc_identifier"))
        if not isinstance(page_id, str) or not page_id:
            continue
        identity = {
            "page_id": page_id,
            "dc_identifier": first_non_empty(dc.get("dc:identifier"), dc.get("identifier"), record.get("dc_identifier"), page_id),
            "dc_title": first_non_empty(dc.get("dc:title"), dc.get("title"), record.get("dc_title")),
            "dc_type": first_non_empty(dc.get("dc:type"), dc.get("type"), record.get("dc_type"), []),
            "source_identity_status": "DUBLIN_CORE_SOURCE_IDENTITY_RESOLVED",
        }
        source_package = first_non_empty(record.get("source_package"), record.get("trace_net:source_package"), dc.get("source_package"))
        if isinstance(source_package, dict):
            identity["source_package"] = source_package
        identities[page_id] = identity
    return identities


def query_records_from_helper(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = payload.get("query_records")
    if isinstance(records, list):
        return [x for x in records if isinstance(x, dict)]
    # API output can store helper records inside summary-like fields; keep fallback simple.
    return []


def part_numbers_from_query_record(record: Mapping[str, Any]) -> list[str]:
    input_obj = record.get("input") if isinstance(record.get("input"), dict) else {}
    values: list[str] = []
    for source in (input_obj, record):
        for key in ("part_number", "part_numbers", "query", "query_text"):
            value = source.get(key)
            if isinstance(value, str):
                values.extend(PART_RE.findall(value))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        values.extend(PART_RE.findall(item))
    return dedupe(values)


def ata_codes_from_query_record(record: Mapping[str, Any]) -> list[str]:
    input_obj = record.get("input") if isinstance(record.get("input"), dict) else {}
    values: list[str] = []
    for source in (input_obj, record):
        for key in ("ata_code", "ata_codes", "query", "query_text"):
            value = source.get(key)
            if isinstance(value, str):
                values.extend(ATA_RE.findall(value))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        values.extend(ATA_RE.findall(item))
    return dedupe(values)


def graph_pages_from_query(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    pages = record.get("pages")
    if isinstance(pages, list):
        return [x for x in pages if isinstance(x, dict)]
    return []


def add_channel(page_index: dict[str, dict[str, Any]], page_id: str, channel: str, evidence: Mapping[str, Any], dc_map: Mapping[str, dict[str, Any]]) -> None:
    if not page_id:
        return
    rec = page_index.setdefault(
        page_id,
        {
            "page_id": page_id,
            "channels": [],
            "evidence_channel_counts": {},
            "evidence_records": [],
            "source_resolved": False,
            "dublin_core_source_identity": dc_map.get(page_id),
            "retrieval_only": True,
            "can_answer_directly": False,
            "can_prove_claims": False,
        },
    )
    if channel not in rec["channels"]:
        rec["channels"].append(channel)
    counts = rec.setdefault("evidence_channel_counts", {})
    counts[channel] = int(counts.get(channel, 0)) + 1
    if not rec.get("dublin_core_source_identity") and dc_map.get(page_id):
        rec["dublin_core_source_identity"] = dc_map.get(page_id)
    rec["source_resolved"] = bool(rec.get("dublin_core_source_identity")) or bool(evidence.get("source_resolved"))
    slim_evidence = dict(evidence)
    # Avoid dumping enormous payloads into every merged page record.
    for key in list(slim_evidence.keys()):
        if key in {"raw_record", "raw_document", "full_text"}:
            slim_evidence.pop(key, None)
    rec.setdefault("evidence_records", []).append(slim_evidence)


def source_resolved_from_helper_page(page: Mapping[str, Any]) -> bool:
    return bool(page.get("source_resolved") or page.get("dublin_core_source_identity") or page.get("source_links"))


def opensearch_hits_for_part(payload: Mapping[str, Any], part_number: str, limit: int) -> list[dict[str, Any]]:
    docs = collect_documents(payload)
    hits: list[dict[str, Any]] = []
    for i, doc in enumerate(docs):
        text = text_from_record(doc)
        explicit_parts: list[str] = []
        for key in ("part_numbers", "representative_part_numbers", "parts"):
            value = doc.get(key)
            if isinstance(value, list):
                explicit_parts.extend([x for x in value if isinstance(x, str)])
            elif isinstance(value, str):
                explicit_parts.extend(PART_RE.findall(value))
        if part_number not in text and part_number not in explicit_parts:
            continue
        page_ids = page_ids_from_record(doc)
        if not page_ids:
            continue
        hits.append(
            {
                "channel": "opensearch_exact",
                "opensearch_document_id": first_non_empty(doc.get("opensearch_document_id"), doc.get("document_id"), doc.get("id"), f"opensearch_doc_{i}"),
                "document_type": first_non_empty(doc.get("document_type"), doc.get("record_type"), doc.get("type")),
                "rag_bucket": doc.get("rag_bucket"),
                "page_ids": page_ids,
                "matched_identifier": part_number,
                "text_preview": text[:600],
                "retrieval_only": True,
                "can_answer_directly": False,
                "can_prove_claims": False,
            }
        )
        if len(hits) >= limit:
            break
    return hits


def opensearch_hits_for_ata(payload: Mapping[str, Any], ata_code: str, limit: int) -> list[dict[str, Any]]:
    docs = collect_documents(payload)
    hits: list[dict[str, Any]] = []
    for i, doc in enumerate(docs):
        text = text_from_record(doc)
        ata_values: list[str] = []
        for key in ("ata", "ata_code", "ata_codes"):
            value = doc.get(key)
            if isinstance(value, str):
                ata_values.extend(ATA_RE.findall(value) or [value])
            elif isinstance(value, list):
                ata_values.extend([x for x in value if isinstance(x, str)])
        if ata_code not in text and ata_code not in ata_values:
            continue
        page_ids = page_ids_from_record(doc)
        if not page_ids:
            continue
        hits.append(
            {
                "channel": "opensearch_exact",
                "opensearch_document_id": first_non_empty(doc.get("opensearch_document_id"), doc.get("document_id"), doc.get("id"), f"opensearch_doc_{i}"),
                "document_type": first_non_empty(doc.get("document_type"), doc.get("record_type"), doc.get("type")),
                "rag_bucket": doc.get("rag_bucket"),
                "page_ids": page_ids,
                "matched_identifier": ata_code,
                "text_preview": text[:600],
                "retrieval_only": True,
                "can_answer_directly": False,
                "can_prove_claims": False,
            }
        )
        if len(hits) >= limit:
            break
    return hits


def hybrid_hits_for_identifiers(payload: Mapping[str, Any], identifiers: list[str], limit: int) -> list[dict[str, Any]]:
    results = payload.get("query_results") if isinstance(payload.get("query_results"), list) else []
    hits: list[dict[str, Any]] = []
    for query in results:
        if not isinstance(query, dict):
            continue
        query_text = str(first_non_empty(query.get("query"), query.get("query_text"), query.get("query_id"), ""))
        query_matches = any(identifier in query_text for identifier in identifiers)
        ranked_groups = query.get("ranked_groups") if isinstance(query.get("ranked_groups"), list) else []
        for group in ranked_groups:
            if not isinstance(group, dict):
                continue
            page_id = group.get("page_id")
            group_parts = []
            for value in as_list(group.get("part_numbers")):
                if isinstance(value, str):
                    group_parts.append(value)
            text = json.dumps({k: group.get(k) for k in ("part_numbers", "page_id", "document_type", "rag_bucket")}, default=str)
            if not query_matches and not any(identifier in group_parts or identifier in text for identifier in identifiers):
                continue
            if not isinstance(page_id, str):
                continue
            hits.append(
                {
                    "channel": "hybrid_v2_ranked_group",
                    "query_id": query.get("query_id"),
                    "query": query_text,
                    "page_ids": [page_id],
                    "hybrid_v2_rank": group.get("hybrid_v2_rank"),
                    "hybrid_v2_score": group.get("hybrid_v2_score"),
                    "exact_hit_count": group.get("exact_hit_count"),
                    "semantic_group_count": group.get("semantic_group_count"),
                    "part_numbers": group_parts[:20],
                    "matched_identifiers": [identifier for identifier in identifiers if identifier in query_text or identifier in group_parts or identifier in text],
                    "retrieval_only": True,
                    "can_answer_directly": False,
                    "can_prove_claims": False,
                }
            )
            if len(hits) >= limit:
                return hits
    return hits


def leiden_hits_for_part(payload: Mapping[str, Any], part_number: str, limit: int) -> list[dict[str, Any]]:
    hints = payload.get("retrieval_navigation_hints") if isinstance(payload.get("retrieval_navigation_hints"), list) else []
    hits: list[dict[str, Any]] = []
    for hint in hints:
        if not isinstance(hint, dict):
            continue
        parts = [p for p in as_list(hint.get("representative_part_numbers")) if isinstance(p, str)]
        label = str(hint.get("refined_label") or "")
        family = str(hint.get("representative_part_family") or "")
        if part_number not in parts and part_number not in label and part_number not in family:
            continue
        page_ids = normalize_page_ids(hint.get("representative_page_ids"))
        if not page_ids:
            continue
        hits.append(
            {
                "channel": "leiden_navigation_hint",
                "community_id": hint.get("community_id"),
                "refined_label": hint.get("refined_label"),
                "navigation_intent": hint.get("navigation_intent"),
                "navigation_confidence": hint.get("navigation_confidence"),
                "representative_part_family": hint.get("representative_part_family"),
                "representative_part_numbers": parts[:20],
                "page_ids": page_ids,
                "matched_identifier": part_number,
                "retrieval_only": True,
                "can_answer_directly": False,
                "can_prove_claims": False,
            }
        )
        if len(hits) >= limit:
            break
    return hits


def leiden_page_hints(payload: Mapping[str, Any], page_ids: Iterable[str]) -> dict[str, list[dict[str, Any]]]:
    wanted = set(page_ids)
    hints = payload.get("page_navigation_hints") if isinstance(payload.get("page_navigation_hints"), list) else []
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for hint in hints:
        if not isinstance(hint, dict):
            continue
        pid = first_non_empty(hint.get("page_id"), hint.get("source_page_id"))
        if not isinstance(pid, str) or pid not in wanted:
            continue
        out[pid].append(
            {
                "community_id": hint.get("community_id"),
                "refined_label": hint.get("refined_label"),
                "navigation_intent": hint.get("navigation_intent"),
                "navigation_confidence": hint.get("navigation_confidence"),
                "retrieval_only": True,
                "can_answer_directly": False,
                "can_prove_claims": False,
            }
        )
    return out


def entailment_hits_for_identifiers(payload: Mapping[str, Any], identifiers: list[str], limit: int) -> list[dict[str, Any]]:
    records = payload.get("entailment_records") if isinstance(payload.get("entailment_records"), list) else []
    hits: list[dict[str, Any]] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        claim_text = str(rec.get("claim_text") or "")
        if not any(identifier in claim_text for identifier in identifiers):
            continue
        page_ids = normalize_page_ids(first_non_empty(rec.get("page_ids"), rec.get("resolved_page_ids")))
        best_span = rec.get("best_evidence_span") if isinstance(rec.get("best_evidence_span"), dict) else {}
        span_pages = normalize_page_ids(best_span.get("page_ids") if isinstance(best_span, dict) else None)
        hits.append(
            {
                "channel": "claim_evidence_entailment",
                "query_id": rec.get("query_id"),
                "claim_id": rec.get("claim_id"),
                "claim_text": claim_text,
                "page_ids": page_ids,
                "best_evidence_page_ids": span_pages,
                "entailment_score": rec.get("entailment_score"),
                "entailment_status": rec.get("entailment_status"),
                "evidence_span_match_status": rec.get("evidence_span_match_status"),
                "human_review_escalation_recommended": rec.get("human_review_escalation_recommended"),
                "reason_codes": rec.get("reason_codes") or [],
                "page_alignment_status": "PAGE_ALIGNED" if set(page_ids) & set(span_pages) else "PAGE_MISMATCH_REVIEW",
                "retrieval_only": True,
                "can_answer_directly": False,
                "can_prove_claims": False,
            }
        )
        if len(hits) >= limit:
            break
    return hits


def make_enriched_query_record(
    query_record: Mapping[str, Any],
    *,
    opensearch_payload: Mapping[str, Any],
    hybrid_payload: Mapping[str, Any],
    leiden_payload: Mapping[str, Any],
    entailment_payload: Mapping[str, Any],
    dc_map: Mapping[str, dict[str, Any]],
    max_evidence_hits: int,
    max_pages_per_query: int,
) -> dict[str, Any]:
    query_type = query_record.get("query_type")
    page_index: dict[str, dict[str, Any]] = {}
    original_pages = graph_pages_from_query(query_record)
    for page in original_pages:
        pid = page.get("page_id")
        if isinstance(pid, str):
            evidence = {
                "channel": "organization_graph",
                "source_resolved": source_resolved_from_helper_page(page),
                "ata_codes": page.get("ata_codes") or [],
                "source_links": page.get("source_links") or [],
                "part_mentions": page.get("part_mentions") or [],
            }
            add_channel(page_index, pid, "organization_graph", evidence, dc_map)

    identifiers = []
    part_numbers = part_numbers_from_query_record(query_record)
    ata_codes = ata_codes_from_query_record(query_record)
    identifiers.extend(part_numbers)
    identifiers.extend(ata_codes)

    opensearch_hits: list[dict[str, Any]] = []
    if part_numbers:
        for part in part_numbers:
            opensearch_hits.extend(opensearch_hits_for_part(opensearch_payload, part, max_evidence_hits))
            for hit in leiden_hits_for_part(leiden_payload, part, max_evidence_hits):
                for pid in hit.get("page_ids", []):
                    add_channel(page_index, pid, "leiden_navigation_hint", hit, dc_map)
    elif ata_codes:
        for ata in ata_codes:
            opensearch_hits.extend(opensearch_hits_for_ata(opensearch_payload, ata, max_evidence_hits))

    for hit in opensearch_hits[:max_evidence_hits]:
        for pid in hit.get("page_ids", []):
            add_channel(page_index, pid, "opensearch_exact", hit, dc_map)

    hybrid_hits = hybrid_hits_for_identifiers(hybrid_payload, identifiers, max_evidence_hits) if identifiers else []
    for hit in hybrid_hits:
        for pid in hit.get("page_ids", []):
            add_channel(page_index, pid, "hybrid_v2_ranked_group", hit, dc_map)

    claim_hits = entailment_hits_for_identifiers(entailment_payload, identifiers, max_evidence_hits) if identifiers else []
    review_records: list[dict[str, Any]] = []
    for hit in claim_hits:
        for pid in hit.get("page_ids", []):
            add_channel(page_index, pid, "claim_evidence_entailment", hit, dc_map)
        if hit.get("page_alignment_status") != "PAGE_ALIGNED" or hit.get("human_review_escalation_recommended"):
            review_records.append(
                {
                    "review_type": "claim_evidence_alignment_review",
                    "query_type": query_type,
                    "query_input": query_record.get("input") or {},
                    "claim_id": hit.get("claim_id"),
                    "claim_text": hit.get("claim_text"),
                    "page_ids": hit.get("page_ids"),
                    "best_evidence_page_ids": hit.get("best_evidence_page_ids"),
                    "page_alignment_status": hit.get("page_alignment_status"),
                    "reason_codes": hit.get("reason_codes") or [],
                    "retrieval_only": True,
                    "can_answer_directly": False,
                    "can_prove_claims": False,
                }
            )

    # Attach page-level Leiden hints to all merged pages without making them proof.
    hint_map = leiden_page_hints(leiden_payload, page_index.keys())
    for pid, hints in hint_map.items():
        rec = page_index.get(pid)
        if rec is not None:
            rec["leiden_navigation_hints"] = hints[:5]
            if hints:
                if "leiden_page_navigation_hint" not in rec["channels"]:
                    rec["channels"].append("leiden_page_navigation_hint")
                counts = rec.setdefault("evidence_channel_counts", {})
                counts["leiden_page_navigation_hint"] = len(hints)

    pages = list(page_index.values())
    pages.sort(key=lambda rec: (0 if "organization_graph" in rec.get("channels", []) else 1, rec.get("page_id", "")))
    pages = pages[:max_pages_per_query]

    channel_counter = Counter()
    for page in pages:
        channel_counter.update(page.get("channels") or [])

    return {
        "plan_id": query_record.get("plan_id"),
        "query_type": query_type,
        "input": query_record.get("input") or {},
        "identifiers": {"part_numbers": part_numbers, "ata_codes": ata_codes},
        "original_graph_page_count": len({p.get("page_id") for p in original_pages if isinstance(p.get("page_id"), str)}),
        "opensearch_exact_hit_count": len(opensearch_hits),
        "hybrid_v2_hit_count": len(hybrid_hits),
        "claim_trace_hit_count": len(claim_hits),
        "enriched_page_count": len(pages),
        "source_resolved_page_count": sum(1 for p in pages if p.get("source_resolved")),
        "dublin_core_identity_count": sum(1 for p in pages if p.get("dublin_core_source_identity")),
        "leiden_navigation_hint_page_count": sum(1 for p in pages if p.get("leiden_navigation_hints")),
        "channel_counts": dict(sorted(channel_counter.items())),
        "pages": pages,
        "review_records": review_records,
        "retrieval_only": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
    }


def build_graph_query_evidence_enrichment(
    *,
    graph_query_helper_path: str | Path,
    opensearch_adapter_path: str | Path,
    hybrid_v2_report_path: str | Path,
    dublin_core_source_package_extension_path: str | Path | None = None,
    leiden_navigation_metadata_bridge_path: str | Path | None = None,
    claim_evidence_entailment_path: str | Path | None = None,
    output_dir: str | Path,
    max_evidence_hits: int = 200,
    max_pages_per_query: int = 200,
    thresholds: Mapping[str, Any] | None = None,
    write_quality: bool = True,
) -> dict[str, Any]:
    thresholds = dict(thresholds or {})
    graph_payload = load_json(graph_query_helper_path)
    opensearch_payload = load_json(opensearch_adapter_path)
    hybrid_payload = load_json(hybrid_v2_report_path)
    dc_payload = load_json(dublin_core_source_package_extension_path, optional=True)
    leiden_payload = load_json(leiden_navigation_metadata_bridge_path, optional=True)
    entailment_payload = load_json(claim_evidence_entailment_path, optional=True)

    dc_map = make_dublin_identity_map(dc_payload)
    query_records = query_records_from_helper(graph_payload)
    enriched_records: list[dict[str, Any]] = []
    all_review_records: list[dict[str, Any]] = []
    page_records_flat: list[dict[str, Any]] = []

    for qr in query_records:
        record = make_enriched_query_record(
            qr,
            opensearch_payload=opensearch_payload,
            hybrid_payload=hybrid_payload,
            leiden_payload=leiden_payload,
            entailment_payload=entailment_payload,
            dc_map=dc_map,
            max_evidence_hits=max_evidence_hits,
            max_pages_per_query=max_pages_per_query,
        )
        enriched_records.append(record)
        all_review_records.extend(record.get("review_records") or [])
        for page in record.get("pages") or []:
            page_records_flat.append(
                {
                    "query_type": record.get("query_type"),
                    "plan_id": record.get("plan_id"),
                    "input": record.get("input"),
                    **page,
                }
            )

    page_ids = dedupe([p.get("page_id") for p in page_records_flat if isinstance(p.get("page_id"), str)])
    channel_counter = Counter()
    for p in page_records_flat:
        channel_counter.update(p.get("channels") or [])

    summary = {
        "schema_version": SCHEMA_VERSION,
        "source_graph_query_helper_quality_status": quality_status(graph_payload),
        "source_opensearch_adapter_quality_status": quality_status(opensearch_payload),
        "source_hybrid_v2_quality_status": quality_status(hybrid_payload),
        "source_dublin_core_quality_status": quality_status(dc_payload) if dc_payload else None,
        "source_leiden_navigation_bridge_quality_status": quality_status(leiden_payload) if leiden_payload else None,
        "source_claim_evidence_entailment_quality_status": quality_status(entailment_payload) if entailment_payload else None,
        "source_load_statuses": {
            "graph_query_helper": "LOADED" if graph_payload else "MISSING",
            "opensearch_adapter": "LOADED" if opensearch_payload else "MISSING",
            "hybrid_v2": "LOADED" if hybrid_payload else "MISSING",
            "dublin_core_source_package_extension": "LOADED" if dc_payload else "NOT_PROVIDED",
            "leiden_navigation_metadata_bridge": "LOADED" if leiden_payload else "NOT_PROVIDED",
            "claim_evidence_entailment": "LOADED" if entailment_payload else "NOT_PROVIDED",
        },
        "query_record_count": len(query_records),
        "enriched_query_record_count": len(enriched_records),
        "enriched_page_record_count": len(page_records_flat),
        "unique_enriched_page_count": len(page_ids),
        "evidence_enriched_page_count": sum(1 for p in page_records_flat if len(set(p.get("channels") or []) - {"organization_graph"}) > 0),
        "source_resolved_page_count": sum(1 for p in page_records_flat if p.get("source_resolved")),
        "dublin_core_identity_page_count": sum(1 for p in page_records_flat if p.get("dublin_core_source_identity")),
        "leiden_navigation_hint_page_count": sum(1 for p in page_records_flat if p.get("leiden_navigation_hints")),
        "review_record_count": len(all_review_records),
        "organization_graph_channel_count": channel_counter.get("organization_graph", 0),
        "opensearch_exact_channel_count": channel_counter.get("opensearch_exact", 0),
        "hybrid_v2_channel_count": channel_counter.get("hybrid_v2_ranked_group", 0),
        "leiden_navigation_channel_count": channel_counter.get("leiden_navigation_hint", 0) + channel_counter.get("leiden_page_navigation_hint", 0),
        "claim_entailment_channel_count": channel_counter.get("claim_evidence_entailment", 0),
        "exact_evidence_page_count": sum(1 for p in page_records_flat if "opensearch_exact" in (p.get("channels") or [])),
        "hybrid_evidence_page_count": sum(1 for p in page_records_flat if "hybrid_v2_ranked_group" in (p.get("channels") or [])),
        "leiden_navigation_page_count": sum(1 for p in page_records_flat if ("leiden_navigation_hint" in (p.get("channels") or []) or "leiden_page_navigation_hint" in (p.get("channels") or []))),
        "claim_trace_page_count": sum(1 for p in page_records_flat if "claim_evidence_entailment" in (p.get("channels") or [])),
        "part_evidence_expansion_count": sum(max(0, int(r.get("enriched_page_count") or 0) - int(r.get("original_graph_page_count") or 0)) for r in enriched_records if r.get("query_type") == "part_lookup"),
        "channel_counts": dict(sorted(channel_counter.items())),
        "community_as_proof_count": 0,
        "category_as_proof_count": 0,
        "retrieval_only_answer_allowed_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "quality_status": QUALITY_PASS,
        "summary": summary,
        "safety_contract": dict(DEFAULT_SAFETY),
        "enriched_query_records": enriched_records,
        "query_records": enriched_records,
        "enriched_page_records": page_records_flat,
        "review_records": all_review_records,
    }
    quality = check_graph_query_evidence_enrichment_quality_payload(payload, thresholds=thresholds)
    payload["quality_status"] = quality["quality_status"]
    payload["summary"]["status"] = quality["quality_status"]

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "trace_net_graph_query_evidence_enrichment_v1.json"
    quality_path = out_dir / "trace_net_graph_query_evidence_enrichment_v1_quality.json"
    records_path = out_dir / "trace_net_graph_query_evidence_enrichment_v1_records.jsonl"
    review_path = out_dir / "trace_net_graph_query_evidence_enrichment_v1_review_records.jsonl"
    markdown_path = out_dir / "trace_net_graph_query_evidence_enrichment_v1.md"
    write_json(report_path, payload)
    if write_quality:
        write_json(quality_path, quality)
    write_jsonl(records_path, enriched_records)
    write_jsonl(review_path, all_review_records)
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    payload["report_path"] = str(report_path)
    payload["quality_path"] = str(quality_path)
    return payload


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    lines = [
        "# TRACE-Net Graph Query Evidence Enrichment v1",
        "",
        f"Status: `{payload.get('status')}`",
        f"Quality: `{payload.get('quality_status')}`",
        "",
        "## Summary",
    ]
    for key in (
        "enriched_query_record_count",
        "enriched_page_record_count",
        "unique_enriched_page_count",
        "evidence_enriched_page_count",
        "opensearch_exact_channel_count",
        "hybrid_v2_channel_count",
        "leiden_navigation_channel_count",
        "claim_entailment_channel_count",
        "review_record_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
    ):
        lines.append(f"- {key}: `{summary.get(key)}`")
    lines.extend([
        "",
        "This artifact is retrieval/navigation only. It does not grant answer permission or claim-proof authority.",
    ])
    return "\n".join(lines) + "\n"


def check_graph_query_evidence_enrichment_quality_payload(payload: Mapping[str, Any], thresholds: Mapping[str, Any] | None = None) -> dict[str, Any]:
    thresholds = thresholds_to_mapping(thresholds)
    summary = dict(payload.get("summary") or {})
    failures: list[str] = []

    def min_check(summary_key: str, threshold_key: str, default: int = 0) -> None:
        threshold = int(thresholds.get(threshold_key, default))
        value = int(summary.get(summary_key) or 0)
        if value < threshold:
            failures.append(f"{summary_key}={value} below {threshold_key}={threshold}")

    def max_check(summary_key: str, threshold_key: str, default: int = 0) -> None:
        threshold = int(thresholds.get(threshold_key, default))
        value = int(summary.get(summary_key) or 0)
        if value > threshold:
            failures.append(f"{summary_key}={value} above {threshold_key}={threshold}")

    min_check("enriched_query_record_count", "min_enriched_query_records", 1)
    min_check("query_record_count", "min_query_records", 0)
    min_check("enriched_page_record_count", "min_enriched_page_records", 1)
    min_check("evidence_enriched_page_count", "min_evidence_enriched_pages", 1)
    min_check("source_resolved_page_count", "min_source_resolved_pages", 1)
    min_check("exact_evidence_page_count", "min_exact_evidence_pages", 0)
    min_check("hybrid_evidence_page_count", "min_hybrid_evidence_pages", 0)
    min_check("leiden_navigation_page_count", "min_leiden_navigation_pages", 0)
    min_check("claim_trace_page_count", "min_claim_trace_pages", 0)

    if thresholds.get("require_no_answer_permission"):
        thresholds["max_can_answer_directly_count"] = 0
        thresholds["max_can_prove_claims_count"] = 0
        thresholds["max_retrieval_only_answer_allowed_count"] = 0

    if thresholds.get("require_graph_query_helper_quality_pass"):
        if str(summary.get("source_graph_query_helper_quality_status")).upper() != "PASS":
            failures.append("source_graph_query_helper_quality_status is not PASS")
    if thresholds.get("require_opensearch_quality_pass"):
        if str(summary.get("source_opensearch_adapter_quality_status")).upper() != "PASS":
            failures.append("source_opensearch_adapter_quality_status is not PASS")
    if thresholds.get("require_hybrid_v2_quality_pass"):
        if str(summary.get("source_hybrid_v2_quality_status")).upper() != "PASS":
            failures.append("source_hybrid_v2_quality_status is not PASS")
    if thresholds.get("require_leiden_bridge_quality_pass"):
        if str(summary.get("source_leiden_navigation_bridge_quality_status")).upper() != "PASS":
            failures.append("source_leiden_navigation_bridge_quality_status is not PASS")
    if thresholds.get("require_dublin_core_quality_pass"):
        if str(summary.get("source_dublin_core_quality_status")).upper() != "PASS":
            failures.append("source_dublin_core_quality_status is not PASS")
    if thresholds.get("require_claim_entailment_quality_pass"):
        if str(summary.get("source_claim_evidence_entailment_quality_status")).upper() != "PASS":
            failures.append("source_claim_evidence_entailment_quality_status is not PASS")

    for key in (
        "community_as_proof_count",
        "category_as_proof_count",
        "retrieval_only_answer_allowed_count",
        "can_answer_directly_count",
        "can_prove_claims_count",
        "source_truth_mutation_allowed_count",
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
    ):
        max_check(key, f"max_{key}", 0)

    quality = QUALITY_FAIL if failures else QUALITY_PASS
    return {
        "schema_version": SCHEMA_VERSION,
        "status": quality,
        "quality_status": quality,
        "failures": failures,
        "summary": summary,
    }


def check_graph_query_evidence_enrichment_quality(report_path: str | Path, thresholds: Mapping[str, Any] | None = None, write_json_report: bool = False) -> dict[str, Any]:
    payload = load_json(report_path)
    report = check_graph_query_evidence_enrichment_quality_payload(payload, thresholds=thresholds)
    if write_json_report:
        p = Path(report_path)
        quality_path = p.with_name("trace_net_graph_query_evidence_enrichment_v1_quality.json")
        write_json(quality_path, report)
    return report


def print_summary(payload: Mapping[str, Any], *, quality: bool = False) -> None:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    title = "TRACE-Net Graph Query Evidence Enrichment v1 quality" if quality else "TRACE-Net Graph Query Evidence Enrichment v1"
    print(title)
    print(f" Status: {payload.get('status')}")
    print(f" Quality status: {payload.get('quality_status')}")
    for key in (
        "source_graph_query_helper_quality_status",
        "source_opensearch_adapter_quality_status",
        "source_hybrid_v2_quality_status",
        "source_leiden_navigation_bridge_quality_status",
        "source_claim_evidence_entailment_quality_status",
        "enriched_query_record_count",
        "enriched_page_record_count",
        "unique_enriched_page_count",
        "evidence_enriched_page_count",
        "source_resolved_page_count",
        "dublin_core_identity_page_count",
        "leiden_navigation_hint_page_count",
        "opensearch_exact_channel_count",
        "hybrid_v2_channel_count",
        "leiden_navigation_channel_count",
        "claim_entailment_channel_count",
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
    ):
        if key in summary:
            print(f" {key}: {summary.get(key)}")
    if payload.get("report_path"):
        print(f" report_path: {payload.get('report_path')}")
    if payload.get("quality_path"):
        print(f" quality_path: {payload.get('quality_path')}")
    if payload.get("failures"):
        print(" Failures:")
        for failure in payload.get("failures") or []:
            print(f"  - {failure}")


def thresholds_from_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "min_enriched_query_records": args.min_enriched_query_records,
        "min_enriched_page_records": args.min_enriched_page_records,
        "min_evidence_enriched_pages": args.min_evidence_enriched_pages,
        "min_source_resolved_pages": args.min_source_resolved_pages,
        "require_graph_query_helper_quality_pass": args.require_graph_query_helper_quality_pass,
        "require_opensearch_quality_pass": args.require_opensearch_quality_pass,
        "require_hybrid_v2_quality_pass": args.require_hybrid_v2_quality_pass,
        "require_leiden_bridge_quality_pass": args.require_leiden_bridge_quality_pass,
        "require_dublin_core_quality_pass": args.require_dublin_core_quality_pass,
        "require_claim_entailment_quality_pass": args.require_claim_entailment_quality_pass,
        "max_community_as_proof_count": args.max_community_as_proof,
        "max_category_as_proof_count": args.max_category_as_proof,
        "max_retrieval_only_answer_allowed_count": args.max_retrieval_only_answer_allowed,
        "max_can_answer_directly_count": args.max_can_answer_directly,
        "max_can_prove_claims_count": args.max_can_prove_claims,
        "max_source_truth_mutation_allowed_count": args.max_source_truth_mutation_allowed,
        "max_postgres_write_attempt_count": 0,
        "max_qdrant_write_attempt_count": 0,
        "max_opensearch_write_attempt_count": 0,
    }



def build_enrichment_report(
    *,
    graph_query_helper: Mapping[str, Any],
    opensearch_adapter: Mapping[str, Any],
    hybrid_v2_report: Mapping[str, Any],
    leiden_navigation_metadata_bridge: Mapping[str, Any] | None = None,
    dublin_core_source_package_extension: Mapping[str, Any] | None = None,
    claim_evidence_entailment: Mapping[str, Any] | None = None,
    thresholds: Mapping[str, Any] | Thresholds | None = None,
    max_evidence_hits: int = 200,
    max_pages_per_query: int = 200,
) -> dict[str, Any]:
    """Build the enrichment report in memory from already-loaded payloads."""
    thresholds_map = thresholds_to_mapping(thresholds)
    dc_map = make_dublin_identity_map(dublin_core_source_package_extension or {})
    query_records = query_records_from_helper(graph_query_helper)
    enriched_records: list[dict[str, Any]] = []
    all_review_records: list[dict[str, Any]] = []
    page_records_flat: list[dict[str, Any]] = []

    for qr in query_records:
        record = make_enriched_query_record(
            qr,
            opensearch_payload=opensearch_adapter,
            hybrid_payload=hybrid_v2_report,
            leiden_payload=leiden_navigation_metadata_bridge or {},
            entailment_payload=claim_evidence_entailment or {},
            dc_map=dc_map,
            max_evidence_hits=max_evidence_hits,
            max_pages_per_query=max_pages_per_query,
        )
        enriched_records.append(record)
        all_review_records.extend(record.get("review_records") or [])
        for page in record.get("pages") or []:
            page_records_flat.append({"query_type": record.get("query_type"), "plan_id": record.get("plan_id"), "input": record.get("input"), **page})

    page_ids = dedupe([p.get("page_id") for p in page_records_flat if isinstance(p.get("page_id"), str)])
    channel_counter = Counter()
    for p in page_records_flat:
        channel_counter.update(p.get("channels") or [])

    summary = {
        "schema_version": SCHEMA_VERSION,
        "source_graph_query_helper_quality_status": quality_status(graph_query_helper),
        "source_opensearch_adapter_quality_status": quality_status(opensearch_adapter),
        "source_hybrid_v2_quality_status": quality_status(hybrid_v2_report),
        "source_dublin_core_quality_status": quality_status(dublin_core_source_package_extension or {}) if dublin_core_source_package_extension else None,
        "source_leiden_navigation_bridge_quality_status": quality_status(leiden_navigation_metadata_bridge or {}) if leiden_navigation_metadata_bridge else None,
        "source_claim_evidence_entailment_quality_status": quality_status(claim_evidence_entailment or {}) if claim_evidence_entailment else None,
        "query_record_count": len(query_records),
        "enriched_query_record_count": len(enriched_records),
        "enriched_page_record_count": len(page_records_flat),
        "unique_enriched_page_count": len(page_ids),
        "evidence_enriched_page_count": sum(1 for p in page_records_flat if len(set(p.get("channels") or []) - {"organization_graph"}) > 0),
        "source_resolved_page_count": sum(1 for p in page_records_flat if p.get("source_resolved")),
        "dublin_core_identity_page_count": sum(1 for p in page_records_flat if p.get("dublin_core_source_identity")),
        "leiden_navigation_hint_page_count": sum(1 for p in page_records_flat if p.get("leiden_navigation_hints")),
        "review_record_count": len(all_review_records),
        "organization_graph_channel_count": channel_counter.get("organization_graph", 0),
        "opensearch_exact_channel_count": channel_counter.get("opensearch_exact", 0),
        "hybrid_v2_channel_count": channel_counter.get("hybrid_v2_ranked_group", 0),
        "leiden_navigation_channel_count": channel_counter.get("leiden_navigation_hint", 0) + channel_counter.get("leiden_page_navigation_hint", 0),
        "claim_entailment_channel_count": channel_counter.get("claim_evidence_entailment", 0),
        "exact_evidence_page_count": sum(1 for p in page_records_flat if "opensearch_exact" in (p.get("channels") or [])),
        "hybrid_evidence_page_count": sum(1 for p in page_records_flat if "hybrid_v2_ranked_group" in (p.get("channels") or [])),
        "leiden_navigation_page_count": sum(1 for p in page_records_flat if ("leiden_navigation_hint" in (p.get("channels") or []) or "leiden_page_navigation_hint" in (p.get("channels") or []))),
        "claim_trace_page_count": sum(1 for p in page_records_flat if "claim_evidence_entailment" in (p.get("channels") or [])),
        "part_evidence_expansion_count": sum(max(0, int(r.get("enriched_page_count") or 0) - int(r.get("original_graph_page_count") or 0)) for r in enriched_records if r.get("query_type") == "part_lookup"),
        "community_as_proof_count": 0,
        "category_as_proof_count": 0,
        "retrieval_only_answer_allowed_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BUILT,
        "quality_status": QUALITY_PASS,
        "summary": summary,
        "safety_contract": dict(DEFAULT_SAFETY),
        "enriched_query_records": enriched_records,
        "query_records": enriched_records,
        "enriched_page_records": page_records_flat,
        "review_records": all_review_records,
    }
    quality = check_graph_query_evidence_enrichment_quality_payload(payload, thresholds=thresholds_map)
    payload["quality_status"] = quality["quality_status"]
    payload["summary"]["status"] = quality["quality_status"]
    return payload


def build_from_paths(
    *,
    graph_query_helper_path: str | Path,
    opensearch_adapter_path: str | Path,
    hybrid_v2_report_path: str | Path,
    output_dir: str | Path,
    leiden_navigation_metadata_bridge_path: str | Path | None = None,
    dublin_core_source_package_extension_path: str | Path | None = None,
    claim_evidence_entailment_path: str | Path | None = None,
    thresholds: Mapping[str, Any] | Thresholds | None = None,
    quality: bool = True,
    max_evidence_hits: int = 200,
    max_pages_per_query: int = 200,
) -> dict[str, Any]:
    report = build_enrichment_report(
        graph_query_helper=load_json(graph_query_helper_path),
        opensearch_adapter=load_json(opensearch_adapter_path),
        hybrid_v2_report=load_json(hybrid_v2_report_path),
        leiden_navigation_metadata_bridge=load_json(leiden_navigation_metadata_bridge_path, optional=True),
        dublin_core_source_package_extension=load_json(dublin_core_source_package_extension_path, optional=True),
        claim_evidence_entailment=load_json(claim_evidence_entailment_path, optional=True),
        thresholds=thresholds,
        max_evidence_hits=max_evidence_hits,
        max_pages_per_query=max_pages_per_query,
    )
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "trace_net_graph_query_evidence_enrichment_v1.json"
    quality_path = out_dir / "trace_net_graph_query_evidence_enrichment_v1_quality.json"
    write_json(report_path, report)
    if quality:
        write_json(quality_path, check_graph_query_evidence_enrichment_quality_payload(report, thresholds=thresholds_to_mapping(thresholds)))
    write_jsonl(out_dir / "trace_net_graph_query_evidence_enrichment_v1_records.jsonl", report.get("query_records") or [])
    write_jsonl(out_dir / "trace_net_graph_query_evidence_enrichment_v1_review_records.jsonl", report.get("review_records") or [])
    (out_dir / "trace_net_graph_query_evidence_enrichment_v1.md").write_text(render_markdown(report), encoding="utf-8")
    report["report_path"] = str(report_path)
    report["quality_path"] = str(quality_path)
    return report


def check_enrichment_quality(
    *,
    report_path: str | Path,
    thresholds: Mapping[str, Any] | Thresholds | None = None,
    write_json_report: bool = False,
) -> dict[str, Any]:
    return check_graph_query_evidence_enrichment_quality(
        report_path=report_path,
        thresholds=thresholds_to_mapping(thresholds),
        write_json_report=write_json_report,
    )

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build TRACE-Net Graph Query Evidence Enrichment v1")
    parser.add_argument("--graph-query-helper", required=True)
    parser.add_argument("--opensearch-adapter", required=True)
    parser.add_argument("--hybrid-v2-report", required=True)
    parser.add_argument("--dublin-core-source-package-extension")
    parser.add_argument("--leiden-navigation-metadata-bridge")
    parser.add_argument("--claim-evidence-entailment")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-evidence-hits", type=int, default=200)
    parser.add_argument("--max-pages-per-query", type=int, default=200)
    parser.add_argument("--min-enriched-query-records", type=int, default=1)
    parser.add_argument("--min-enriched-page-records", type=int, default=1)
    parser.add_argument("--min-evidence-enriched-pages", type=int, default=1)
    parser.add_argument("--min-source-resolved-pages", type=int, default=1)
    parser.add_argument("--max-community-as-proof", type=int, default=0)
    parser.add_argument("--max-category-as-proof", type=int, default=0)
    parser.add_argument("--max-retrieval-only-answer-allowed", type=int, default=0)
    parser.add_argument("--max-can-answer-directly", type=int, default=0)
    parser.add_argument("--max-can-prove-claims", type=int, default=0)
    parser.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    parser.add_argument("--require-graph-query-helper-quality-pass", action="store_true")
    parser.add_argument("--require-opensearch-quality-pass", action="store_true")
    parser.add_argument("--require-hybrid-v2-quality-pass", action="store_true")
    parser.add_argument("--require-leiden-bridge-quality-pass", action="store_true")
    parser.add_argument("--require-dublin-core-quality-pass", action="store_true")
    parser.add_argument("--require-claim-entailment-quality-pass", action="store_true")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--quality", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.require_no_answer_permission:
        args.max_can_answer_directly = 0
        args.max_can_prove_claims = 0
        args.max_retrieval_only_answer_allowed = 0
    payload = build_graph_query_evidence_enrichment(
        graph_query_helper_path=args.graph_query_helper,
        opensearch_adapter_path=args.opensearch_adapter,
        hybrid_v2_report_path=args.hybrid_v2_report,
        dublin_core_source_package_extension_path=args.dublin_core_source_package_extension,
        leiden_navigation_metadata_bridge_path=args.leiden_navigation_metadata_bridge,
        claim_evidence_entailment_path=args.claim_evidence_entailment,
        output_dir=args.output_dir,
        max_evidence_hits=args.max_evidence_hits,
        max_pages_per_query=args.max_pages_per_query,
        thresholds=thresholds_from_args(args),
        write_quality=args.quality,
    )
    print_summary(payload)
    return 0 if payload.get("quality_status") == QUALITY_PASS else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
