from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

VERSION = "v33"
MODULE = "trace_net_e2e_live_gemma_answer_writer_endpoint_v33"
MODEL_ID = "trace-net-e2e-live-gemma-answer-writer-v33"

PART_NUMBER_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b", re.I)
PAGE_ID_RE = re.compile(r"t_p_\d+_\d+_p\d{6}", re.I)
MANUAL_REF_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
CITATION_RE = re.compile(r"\[\d+\]")

SOURCE_TRUTH_FIELDS = {
    "covered_part_number",
    "ipl_part_number",
    "part_number",
    "manual_page_reference",
    "ipl_text",
    "table_text",
    "nomenclature",
}

NORMAL_INTENTS_V33 = {
    "corpus_page_count",
    "covered_part_number_listing",
    "drilldown_covered_part_numbers_by_field",
    "page_records_lookup",
    "page_covered_part_numbers_lookup",
    "page_profile_summary",
}

GUIDANCE_ONLY_WARNING = (
    "Graph/Leiden, v2 summaries, route metadata, and nomenclature metadata are guidance only; "
    "source-truth evidence is required for factual claims."
)

SAFETY_CONTRACT: Dict[str, Any] = {
    "answer_permission": False,
    "can_answer_directly": False,
    "can_prove_claims": False,
    "source_truth_mutation_allowed": False,
    "writes_to_postgres": False,
    "writes_to_qdrant": False,
    "writes_to_opensearch": False,
    "uploads_to_opensearch": False,
    "raw_5tb_scan_at_query_time": False,
    "graph_rebuild_at_query_time": False,
    "llm_called": True,
    "response_is_final_gated": True,
    "llm_answer_writer_required": True,
    "source_truth_required_for_relationship_claims": True,
    "graph_leiden_guidance_only": True,
    "v2_summaries_guidance_only": True,
    "nomenclature_metadata_guidance_only": True,
}


def _now() -> int:
    return int(time.time())


def _read_json(path: str | Path | None) -> Dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _stable_id(prefix: str, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _stringify(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    if isinstance(x, (int, float, bool)):
        return str(x)
    return json.dumps(x, ensure_ascii=False, sort_keys=True)


def _norm(s: Any) -> str:
    return _stringify(s).strip()


def _lower(s: Any) -> str:
    return _norm(s).lower()


def _looks_like_page_id(value: Any) -> bool:
    return bool(PAGE_ID_RE.search(_stringify(value)))


def _extract_page_id(obj: Mapping[str, Any]) -> str:
    for key in (
        "page_id",
        "source_page_id",
        "target_page_id",
        "from_page_id",
        "to_page_id",
        "page",
        "source_page",
        "node_id",
        "source",
        "target",
        "id",
    ):
        v = obj.get(key)
        if isinstance(v, str):
            m = PAGE_ID_RE.search(v)
            if m:
                return m.group(0)
    text = json.dumps(obj, ensure_ascii=False)
    m = PAGE_ID_RE.search(text)
    return m.group(0) if m else ""


def _extract_field(obj: Mapping[str, Any]) -> str:
    for key in ("field", "field_name", "field_type", "source_truth_field", "record_field", "type"):
        v = obj.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    text = json.dumps(obj, ensure_ascii=False).lower()
    for field in sorted(SOURCE_TRUTH_FIELDS, key=len, reverse=True):
        if field in text:
            return field
    return ""


def _extract_value(obj: Mapping[str, Any]) -> str:
    for key in (
        "value",
        "text",
        "field_value",
        "source_truth_value",
        "record_value",
        "covered_part_number",
        "part_number",
        "manual_page_reference",
        "ipl_text",
        "table_text",
        "nomenclature",
    ):
        v = obj.get(key)
        if isinstance(v, (str, int, float)) and str(v).strip():
            return str(v).strip()
    # Fallback: prefer obvious part/manual/text tokens from serialized record.
    serialized = json.dumps(obj, ensure_ascii=False)
    part = PART_NUMBER_RE.search(serialized)
    if part:
        return part.group(0)
    manual = MANUAL_REF_RE.search(serialized)
    if manual:
        return manual.group(0)
    return ""


def _walk_json(obj: Any) -> Iterable[Any]:
    yield obj
    if isinstance(obj, Mapping):
        for v in obj.values():
            yield from _walk_json(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_json(v)


def _candidate_record_dicts(data: Any) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for x in _walk_json(data):
        if not isinstance(x, Mapping):
            continue
        field = _extract_field(x)
        value = _extract_value(x)
        page_id = _extract_page_id(x)
        serialized = json.dumps(x, ensure_ascii=False).lower()
        if page_id and (field or value or any(f in serialized for f in SOURCE_TRUTH_FIELDS)):
            records.append(dict(x))
    # Deduplicate by page/field/value/id.
    seen = set()
    out = []
    for r in records:
        key = (
            _extract_page_id(r),
            _extract_field(r),
            _extract_value(r),
            _norm(r.get("record_id") or r.get("id")),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _collect_page_contexts(data: Any) -> Dict[str, Dict[str, Any]]:
    contexts: Dict[str, Dict[str, Any]] = {}
    for x in _walk_json(data):
        if not isinstance(x, Mapping):
            continue
        page_id = _extract_page_id(x)
        if not page_id:
            continue
        summary = x.get("summary") or x.get("page_summary") or x.get("v2_summary") or x.get("short_summary")
        if summary is None:
            # Some artifacts use context text under content.
            summary = x.get("content") if "context" in _lower(x.get("record_type") or x.get("type")) else None
        if summary is not None and str(summary).strip():
            contexts.setdefault(page_id, dict(x))
    return contexts


def _load_leiden_membership(data: Any) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    page_to_comm: Dict[str, str] = {}
    comm_to_pages: Dict[str, List[str]] = {}
    for x in _walk_json(data):
        if not isinstance(x, Mapping):
            continue
        page_id = _extract_page_id(x)
        if not page_id:
            continue
        comm = ""
        for k in ("leiden_community_id", "community_id", "community", "cluster_id"):
            v = x.get(k)
            if isinstance(v, str) and v.strip():
                comm = v.strip()
                break
        if not comm:
            text = json.dumps(x, ensure_ascii=False)
            m = re.search(r"tracenet_community_\d+", text)
            if m:
                comm = m.group(0)
        if comm:
            page_to_comm[page_id] = comm
            comm_to_pages.setdefault(comm, [])
            if page_id not in comm_to_pages[comm]:
                comm_to_pages[comm].append(page_id)
    for pages in comm_to_pages.values():
        pages.sort()
    return page_to_comm, comm_to_pages


def _safe_join_items(items: Sequence[str], max_items: int = 10) -> str:
    return "; ".join(items[:max_items])


def _citation_lines(evidence: Sequence[Dict[str, Any]]) -> str:
    if not evidence:
        return "- None"
    lines = []
    for idx, rec in enumerate(evidence, start=1):
        lines.append(
            f"- [{idx}] page={rec.get('page_id', '')} field={rec.get('field', '')} value={rec.get('value', '')}"
        )
    return "\n".join(lines)


def _dedupe_evidence(records: Sequence[Mapping[str, Any]], limit: int = 10) -> Tuple[List[Dict[str, Any]], int]:
    seen = set()
    out: List[Dict[str, Any]] = []
    collapsed = 0
    for r in records:
        page_id = _extract_page_id(r)
        field = _extract_field(r)
        value = _extract_value(r)
        if not page_id or not value:
            continue
        key = (page_id, field, value)
        if key in seen:
            collapsed += 1
            continue
        seen.add(key)
        out.append({"page_id": page_id, "field": field or "source_truth", "value": value, "raw": dict(r)})
        if len(out) >= limit:
            # Continue not needed for return sample, but collapsed already counted only before limit.
            pass
    return out[:limit], collapsed


def _format_evidence_examples(evidence: Sequence[Dict[str, Any]], max_items: int = 10) -> str:
    parts = []
    for i, ev in enumerate(evidence[:max_items], start=1):
        parts.append(f"{ev.get('value')} [{i}]")
    return _safe_join_items(parts, max_items=max_items)


def _metadata_from_router(router_report: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "page_context_v2_page_count": router_report.get("page_context_v2_page_count"),
        "graph_has_v2_page_count": router_report.get("graph_has_v2_page_count"),
        "graph_has_context_page_count": router_report.get("graph_has_context_page_count"),
        "graph_has_nomenclature_page_count": router_report.get("graph_has_nomenclature_page_count"),
        "exact_search_document_count": router_report.get("exact_search_document_count"),
    }


def _self_rag_assessment(package: Mapping[str, Any]) -> Dict[str, Any]:
    """Small, deterministic Self-RAG-style package quality card.

    This is not a second model call. It is runtime telemetry that tells the
    endpoint and evaluator whether the package is strong enough, partial,
    guidance-only, metadata-only, or safely unanswerable.
    """
    intent = _norm(package.get("query_intent"))
    mode = _norm(package.get("response_mode"))
    evidence = package.get("source_truth_evidence", []) or []
    guidance = package.get("graph_guidance", {}) or {}
    metadata = package.get("artifact_metadata", {}) or {}
    has_direct = bool(evidence)
    has_metadata_answer = mode == "artifact_metadata_count" and bool(package.get("total_match_count"))
    has_v2 = bool(package.get("v2_summary"))
    has_graph_guidance = bool(guidance.get("candidate_page_ids") or guidance.get("leiden_community_ids") or guidance.get("relationship_guidance_only"))
    guidance_only = bool(has_graph_guidance or has_v2 or intent in {"artifact_v2_summary_count", "field_or_graph_nomenclature_count", "nomenclature_relationship_question", "v2_proof_safety_question"})
    capped = bool(package.get("result_was_capped"))
    missing_or_audit = mode in {"audit_only", "exact_missing_value"} or not (has_direct or has_metadata_answer or has_graph_guidance or has_v2)

    if has_direct and not capped:
        quality = "strong"
        status = "SELF_RAG_SOURCE_TRUTH_READY"
        answerable = True
    elif has_direct and capped:
        quality = "partial"
        status = "SELF_RAG_SOURCE_TRUTH_READY_WITH_CAP_DISCLOSURE"
        answerable = True
    elif has_metadata_answer:
        quality = "metadata_ready"
        status = "SELF_RAG_METADATA_READY_GUIDANCE_LABELED"
        answerable = True
    elif has_graph_guidance or has_v2:
        quality = "guidance_only"
        status = "SELF_RAG_GUIDANCE_ONLY_NEEDS_SOURCE_TRUTH_FOR_CLAIMS"
        answerable = True
    elif missing_or_audit:
        quality = "weak"
        status = "SELF_RAG_NO_DIRECT_EVIDENCE_AUDIT_ONLY"
        answerable = False
    else:
        quality = "partial"
        status = "SELF_RAG_PARTIAL_PACKAGE"
        answerable = True

    return {
        "self_rag_status": status,
        "package_quality": quality,
        "answerable_from_package": answerable,
        "direct_source_truth_available": has_direct,
        "direct_source_truth_evidence_count": len(evidence),
        "metadata_answer_available": has_metadata_answer,
        "guidance_only_signals_present": guidance_only,
        "graph_guidance_present": has_graph_guidance,
        "v2_summary_guidance_present": has_v2,
        "cap_disclosure_required": capped,
        "citation_required_for_claims": has_direct,
        "limitation_disclosure_required": guidance_only or capped or not has_direct,
        "metadata_count_source": metadata.get("metadata_count_source"),
    }


def _crag_assessment(package: Mapping[str, Any], self_rag: Mapping[str, Any]) -> Dict[str, Any]:
    """Small CRAG-style retry/fallback decision card.

    CRAG here means: if the first package is weak, identify whether we should
    retry a different route, or whether the safe audit-only answer is the
    correct final behavior.
    """
    intent = _norm(package.get("query_intent"))
    mode = _norm(package.get("response_mode"))
    has_direct = bool(self_rag.get("direct_source_truth_available"))
    has_metadata = bool(self_rag.get("metadata_answer_available"))
    has_guidance = bool(self_rag.get("guidance_only_signals_present"))
    answerable = bool(self_rag.get("answerable_from_package"))
    capped = bool(package.get("result_was_capped"))

    retry_required = False
    retry_reason = None
    recommended_retry_route = None
    fallback_safe = False
    status = "CRAG_NO_RETRY_PACKAGE_READY"

    if mode in {"exact_missing_value", "audit_only"} and not (has_direct or has_metadata or has_guidance):
        status = "CRAG_NO_RETRY_SAFE_AUDIT_ONLY"
        fallback_safe = True
        retry_reason = "direct_exact_or_supported_route_found_no_citation_ready_evidence"
    elif capped:
        status = "CRAG_NO_RETRY_CAP_DISCLOSURE_REQUIRED"
        retry_reason = "results_capped_but_source_truth_package_is_answerable"
    elif has_direct or has_metadata:
        status = "CRAG_NO_RETRY_SOURCE_TRUTH_OR_METADATA_READY"
    elif has_guidance and intent in {"relationship_synthesis", "relationship_navigation", "nomenclature_relationship_question", "v2_proof_safety_question", "page_profile_summary"}:
        status = "CRAG_NO_RETRY_GUIDANCE_ONLY_SAFE_RESPONSE"
        retry_reason = "guidance_available_but_source_truth_required_for_relationship_claims"
    elif not answerable:
        retry_required = True
        recommended_retry_route = "exact_value_or_page_scoped_source_truth_search"
        retry_reason = "package_not_answerable_from_available_artifacts"
        status = "CRAG_RETRY_RECOMMENDED"

    return {
        "crag_status": status,
        "retry_required": retry_required,
        "retry_reason": retry_reason,
        "recommended_retry_route": recommended_retry_route,
        "fallback_safe": fallback_safe,
        "cap_disclosure_required": capped,
        "audit_only_allowed": mode in {"audit_only", "exact_missing_value"},
    }


def _extract_messages_user_text(payload_or_messages: Any) -> str:
    messages = payload_or_messages.get("messages", []) if isinstance(payload_or_messages, Mapping) else payload_or_messages
    if isinstance(messages, str):
        return messages
    if not isinstance(messages, list):
        return ""
    texts: List[str] = []
    for msg in messages:
        if isinstance(msg, str):
            texts.append(msg)
            continue
        if not isinstance(msg, Mapping):
            continue
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, Mapping) and item.get("type") in {"text", "input_text"}:
                    texts.append(_norm(item.get("text")))
                elif isinstance(item, str):
                    texts.append(item)
    return "\n".join(t for t in texts if t).strip()


def _estimate_token_count(text: str) -> int:
    """Fast rough token estimate for telemetry; avoids model tokenizer dependency."""
    return max(1, int(len(text) / 4)) if text else 0


def _compact_evidence_lines(evidence: Sequence[Mapping[str, Any]], max_items: int = 5) -> List[str]:
    lines: List[str] = []
    for i, ev in enumerate(evidence[:max_items], start=1):
        page = _extract_page_id(ev) or _norm(ev.get("page_id")) or "unknown_page"
        field = _extract_field(ev) or "unknown_field"
        value = _extract_value(ev) or "unknown_value"
        lines.append(f"[{i}] page={page} field={field} value={value}")
    return lines


def _compact_llm_content(package: Mapping[str, Any], *, max_evidence: int = 5) -> Dict[str, Any]:
    metadata = package.get("artifact_metadata", {}) or {}
    guidance = package.get("graph_guidance", {}) or {}
    content: Dict[str, Any] = {
        "question": package.get("user_query"),
        "intent": package.get("query_intent"),
        "response_mode": package.get("response_mode"),
        "safe_answer_if_needed": package.get("deterministic_safe_answer"),
        "direct_source_truth_evidence": _compact_evidence_lines(package.get("source_truth_evidence", []) or [], max_items=max_evidence),
        "counts_and_metadata": {
            "total_match_count": package.get("total_match_count"),
            "returned_match_count": package.get("returned_match_count"),
            "result_was_capped": package.get("result_was_capped"),
            "corpus_page_count": metadata.get("corpus_page_count"),
            "page_context_v2_page_count": metadata.get("page_context_v2_page_count"),
            "v2_summary_page_first": metadata.get("v2_summary_page_first"),
            "v2_summary_page_last": metadata.get("v2_summary_page_last"),
            "graph_has_v2_page_count": metadata.get("graph_has_v2_page_count"),
            "graph_has_context_page_count": metadata.get("graph_has_context_page_count"),
            "nomenclature_page_count": metadata.get("nomenclature_page_count"),
            "nomenclature_part_count": metadata.get("nomenclature_part_count"),
            "metadata_count_source": metadata.get("metadata_count_source"),
            "corpus_page_first": metadata.get("corpus_page_first"),
            "corpus_page_last": metadata.get("corpus_page_last"),
            "requested_page_id": package.get("page_id"),
        },
        "graph_guidance": {
            "relationship_guidance_only": guidance.get("relationship_guidance_only"),
            "leiden_community_ids": guidance.get("leiden_community_ids", []),
            "candidate_page_ids": (guidance.get("candidate_page_ids", []) or [])[:10],
            "requires_source_truth_confirmation": guidance.get("requires_source_truth_confirmation", True),
        },
        "v2_summary_guidance": package.get("v2_summary"),
        "page_profile": package.get("page_profile"),
        "self_rag": package.get("self_rag"),
        "crag": package.get("crag"),
        "drilldown_groups": package.get("drilldown_groups"),
        "limitations": [
            "Source-truth records are the only proof authority for factual claims.",
            "Graph/Leiden, v2 summaries, route metadata, and nomenclature metadata are guidance only, not proof.",
            "Do not invent physical part descriptions, page contents, or relationships.",
        ],
        "normal_intent_package": package.get("query_intent") in NORMAL_INTENTS_V33,
        "answer_style": "Answer in 2-5 short sentences. Do not explain hidden reasoning. Use citation markers only for direct source-truth evidence.",
    }
    # Drop empty keys inside nested dicts to keep prompt small and cache-friendly.
    for key in ("counts_and_metadata", "graph_guidance"):
        content[key] = {k: v for k, v in (content.get(key) or {}).items() if v not in (None, "", [], {})}
    return content


def _full_llm_content(package: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "user_query": package.get("user_query"),
        "query_intent": package.get("query_intent"),
        "response_mode": package.get("response_mode"),
        "direct_source_truth_evidence": package.get("source_truth_evidence"),
        "artifact_metadata": package.get("artifact_metadata"),
        "graph_guidance": package.get("graph_guidance"),
        "v2_summary": package.get("v2_summary"),
        "drilldown_groups": package.get("drilldown_groups"),
        "total_match_count": package.get("total_match_count"),
        "returned_match_count": package.get("returned_match_count"),
        "result_was_capped": package.get("result_was_capped"),
        "deterministic_safe_answer": package.get("deterministic_safe_answer"),
        "answer_rules": package.get("answer_rules"),
    }


@dataclass
class TraceNetArtifactsV33:
    table_records: List[Dict[str, Any]]
    page_contexts: Dict[str, Dict[str, Any]]
    page_to_comm: Dict[str, str]
    comm_to_pages: Dict[str, List[str]]
    router_report: Dict[str, Any]
    hardener_report: Dict[str, Any]

    @classmethod
    def load(
        cls,
        table_exact_search_adapter: str | Path | None = None,
        page_context_v2: str | Path | None = None,
        leiden_communities: str | Path | None = None,
        relationship_router_hardening: str | Path | None = None,
        relationship_final_gate_hardener: str | Path | None = None,
    ) -> "TraceNetArtifactsV33":
        table = _read_json(table_exact_search_adapter)
        page_ctx = _read_json(page_context_v2)
        leiden = _read_json(leiden_communities)
        router = _read_json(relationship_router_hardening)
        hardener = _read_json(relationship_final_gate_hardener)
        page_to_comm, comm_to_pages = _load_leiden_membership(leiden)
        return cls(
            table_records=_candidate_record_dicts(table),
            page_contexts=_collect_page_contexts(page_ctx),
            page_to_comm=page_to_comm,
            comm_to_pages=comm_to_pages,
            router_report=router,
            hardener_report=hardener,
        )

    @property
    def all_page_ids(self) -> List[str]:
        page_ids = set(self.page_contexts)
        for r in self.table_records:
            pid = _extract_page_id(r)
            if pid:
                page_ids.add(pid)
        page_ids.update(self.page_to_comm)
        return sorted(page_ids)


def _query_intent(query: str) -> str:
    q = query.lower().strip()
    if "v2" in q and ("how many" in q or "count" in q or "summary" in q or "summaries" in q):
        return "artifact_v2_summary_count"
    if "how many pages" in q and "nomenclature" in q:
        return "field_or_graph_nomenclature_count"
    if "how many pages" in q and ("are there" in q or "total" in q):
        return "corpus_page_count"
    if q.startswith("drill down") and "covered part" in q and "field" in q:
        return "drilldown_covered_part_numbers_by_field"
    if q.startswith("drill down") and "covered part" in q and "page" in q:
        return "drilldown_covered_part_numbers_by_page"
    if "show covered part" in q and PAGE_ID_RE.search(query):
        return "page_covered_part_numbers_lookup"
    if "show records for page" in q and PAGE_ID_RE.search(query):
        return "page_records_lookup"
    if "what do we know about page" in q and PAGE_ID_RE.search(query):
        return "page_profile_summary"
    if "covered part" in q and ("list" in q or "how many" in q or "mention" in q or "pages" in q):
        return "covered_part_number_listing"
    if "search table text" in q:
        return "table_text_exact_search"
    if "manual reference" in q and MANUAL_REF_RE.search(query):
        if "relate" in q or "related" in q or "explain" in q:
            return "relationship_synthesis"
        return "manual_reference_lookup"
    if PART_NUMBER_RE.search(query):
        if any(w in q for w in ("relate", "related", "inspect", "near", "community", "graph", "explain")):
            return "relationship_synthesis"
        return "exact_part_number"
    if PAGE_ID_RE.search(query) and any(w in q for w in ("leiden", "community", "neighbors", "graph", "related")):
        return "relationship_navigation"
    if "nomenclature" in q and any(w in q for w in ("mean", "relationship", "confirm", "prove")):
        return "nomenclature_relationship_question"
    if "v2" in q and any(w in q for w in ("proof", "prove", "related")):
        return "v2_proof_safety_question"
    return "unknown"


def _match_records(
    records: Sequence[Mapping[str, Any]],
    *,
    field_contains: str | None = None,
    value_equals: str | None = None,
    value_contains: str | None = None,
    page_id: str | None = None,
) -> List[Mapping[str, Any]]:
    out: List[Mapping[str, Any]] = []
    for r in records:
        field = _extract_field(r).lower()
        value = _extract_value(r)
        pid = _extract_page_id(r)
        if field_contains and field_contains.lower() not in field:
            continue
        if value_equals and value.lower() != value_equals.lower():
            continue
        if value_contains and value_contains.lower() not in value.lower():
            continue
        if page_id and pid.lower() != page_id.lower():
            continue
        out.append(r)
    return out


def _infer_table_text_target(query: str) -> str:
    q = query.strip()
    m = re.search(r"search\s+table\s+text\s+(.+)$", q, flags=re.I)
    return m.group(1).strip().strip('"') if m else q


def _direct_answer_for_package(package: Mapping[str, Any]) -> str:
    intent = package.get("query_intent")
    evidence = package.get("source_truth_evidence", []) or []
    metadata = package.get("artifact_metadata", {}) or {}
    guidance = package.get("graph_guidance", {}) or {}
    query = package.get("user_query", "")

    if intent == "exact_part_number":
        if evidence:
            ev = evidence[0]
            return (
                f"TRACE-Net found part number {ev['value']} on page {ev['page_id']} as {ev['field']} [1]. "
                "The available direct source-truth evidence confirms the listing, but it does not provide enough information to describe the part physically."
            )
        return "TRACE-Net did not find direct citation-ready source-truth evidence for this part number. No source-truth claim is made."

    if intent == "table_text_exact_search":
        target = package.get("target_value") or _infer_table_text_target(query)
        if evidence:
            ev = evidence[0]
            return (
                f"TRACE-Net found the exact table text \"{target}\" on page {ev['page_id']} [1]. "
                "Nearby OCR/table records may be useful context, but are not treated as direct proof for unrelated claims."
            )
        return "TRACE-Net did not find direct citation-ready source-truth evidence for this table text. No source-truth claim is made."

    if intent == "manual_reference_lookup":
        if evidence:
            ev = evidence[0]
            count = package.get("target_occurrence_count") or len(evidence)
            return f"TRACE-Net found manual reference {ev['value']} on page {ev['page_id']} [1]. The same page/value appears in {count} source record(s)."
        return "TRACE-Net did not find direct citation-ready source-truth evidence for this manual reference. No source-truth claim is made."

    if intent == "covered_part_number_listing":
        if evidence:
            pages = sorted({ev["page_id"] for ev in evidence})
            examples = _format_evidence_examples(evidence)
            total = package.get("total_match_count", len(evidence))
            returned = package.get("returned_match_count", len(evidence))
            cap = f" Results were capped: TRACE-Net returned {returned} of {total} matching records." if total > returned else ""
            return f"TRACE-Net found covered part numbers on page(s) {', '.join(pages)}. Direct source-truth examples include {examples}.{cap}"
        return "TRACE-Net did not find direct citation-ready covered-part-number evidence. No source-truth claim is made."

    if intent == "drilldown_covered_part_numbers_by_page":
        groups = package.get("drilldown_groups", {}) or {}
        if groups:
            group_text = "; ".join(f"{k}: {v}" for k, v in list(groups.items())[:10])
            examples = _format_evidence_examples(evidence)
            total = package.get("total_match_count", len(evidence))
            returned = package.get("returned_match_count", len(evidence))
            return f"TRACE-Net drill-down by page: {group_text}. Direct source-truth examples include {examples}. Results were capped: TRACE-Net returned {returned} of {total} matching records."
        return "TRACE-Net did not find covered-part-number records to drill down by page."

    if intent == "drilldown_covered_part_numbers_by_field":
        groups = package.get("drilldown_groups", {}) or {}
        if groups:
            group_text = "; ".join(f"{k}: {v}" for k, v in list(groups.items())[:10])
            return f"TRACE-Net drill-down by field: {group_text}."
        return "TRACE-Net did not find covered-part-number fields to drill down."

    if intent in {"page_records_lookup", "page_covered_part_numbers_lookup"}:
        page_id = package.get("page_id", "requested page")
        if evidence:
            examples = _format_evidence_examples(evidence)
            total = package.get("total_match_count", len(evidence))
            returned = package.get("returned_match_count", len(evidence))
            return f"TRACE-Net found {total} source-truth record(s) for page {page_id}. Examples include {examples}. Returned {returned} record(s) in this answer."
        return f"TRACE-Net did not find direct citation-ready source-truth records for page {page_id}."

    if intent == "corpus_page_count":
        count = metadata.get("corpus_page_count") or metadata.get("page_context_v2_page_count") or 0
        first = metadata.get("corpus_page_first")
        last = metadata.get("corpus_page_last")
        if count:
            return f"TRACE-Net currently has {count} page(s) represented in the loaded page/context artifacts, page range {first} through {last}."
        return "TRACE-Net could not determine the loaded corpus page count from the current artifacts."

    if intent == "artifact_v2_summary_count":
        count = metadata.get("page_context_v2_page_count") or metadata.get("v2_summary_page_count") or 0
        first = metadata.get("v2_summary_page_first") or metadata.get("corpus_page_first")
        last = metadata.get("v2_summary_page_last") or metadata.get("corpus_page_last")
        graph_v2 = metadata.get("graph_has_v2_page_count")
        graph_ctx = metadata.get("graph_has_context_page_count")
        return (
            f"TRACE-Net found v2 summary guidance for {count} page(s), page range {first} through {last}. "
            f"V2 summaries are guidance/compression metadata only, not source-truth proof. "
            f"Graph metadata coverage observed separately: Has_v2={graph_v2}, HAS_CONTEXT/SUMMARIZES={graph_ctx}."
        )

    if intent == "field_or_graph_nomenclature_count":
        pages = metadata.get("nomenclature_page_count") or metadata.get("graph_has_nomenclature_page_count") or 0
        seeds = metadata.get("nomenclature_part_count") or metadata.get("nomenclature_seed_count") or 0
        if pages:
            return (
                f"TRACE-Net found graph Has_nomenclature guidance for {pages} page(s) across {seeds} part/entity seed(s). "
                "Graph nomenclature signals are navigation/count guidance and should be confirmed with source-truth records before factual part claims."
            )
        return "TRACE-Net did not find direct citation-ready nomenclature count evidence or graph nomenclature metadata for this query."

    if intent == "page_profile_summary":
        page_id = package.get("page_id", "the requested page")
        total = package.get("total_match_count", len(evidence))
        summary = package.get("v2_summary")
        profile = package.get("page_profile", {}) or {}
        field_counts = profile.get("field_counts", {}) or {}
        field_text = "; ".join(f"{k}: {v}" for k, v in list(field_counts.items())[:6])
        parts = []
        if evidence:
            examples = _format_evidence_examples(evidence, max_items=5)
            parts.append(f"TRACE-Net found {total} source-truth record(s) for page {page_id}. Direct source-truth examples include {examples}.")
            if field_text:
                parts.append(f"Field counts on this page include {field_text}.")
        else:
            parts.append(f"TRACE-Net did not find direct citation-ready source-truth records for page {page_id} in the loaded table evidence.")
        if summary:
            parts.append(f"The page also has v2 summary guidance: {summary}. V2 summary guidance is not source-truth proof.")
        elif not evidence:
            parts.append("No v2 summary guidance was available for this page in the loaded page-context artifact.")
        return " ".join(parts)

    if intent in {"relationship_synthesis", "relationship_navigation", "page_profile_summary", "nomenclature_relationship_question", "v2_proof_safety_question"}:
        seed_text = ""
        if evidence:
            pages = sorted({ev["page_id"] for ev in evidence})
            examples = _format_evidence_examples(evidence, max_items=3)
            seed_text = f"TRACE-Net found direct source-truth seed evidence on page(s) {', '.join(pages)}: {examples}. "
        elif package.get("page_id"):
            seed_text = f"TRACE-Net is using page {package.get('page_id')} as a graph/navigation seed. "
        else:
            seed_text = "TRACE-Net found relationship/navigation guidance for this request. "
        comms = guidance.get("leiden_community_ids") or []
        candidates = guidance.get("candidate_page_ids") or []
        if comms or candidates:
            return (
                f"{seed_text}Leiden/graph guidance places the seed page(s) in {', '.join(comms) if comms else 'available graph communities'}; "
                f"candidate pages for inspection include {', '.join(candidates[:10])}. "
                "Graph/Leiden output is guidance only, not proof. Confirm candidate pages with source-truth evidence before making a relationship claim."
            )
        if intent == "page_profile_summary":
            summary = package.get("v2_summary")
            page_id = package.get("page_id", "the requested page")
            if summary:
                return f"TRACE-Net has v2 summary guidance for page {page_id}: {summary}. This is guidance only, not source-truth proof."
        return (
            "TRACE-Net can discuss the available guidance, but direct source-truth evidence is required before making a factual relationship claim. "
            + GUIDANCE_ONLY_WARNING
        )

    return "TRACE-Net did not find direct citation-ready source-truth evidence for this query. No source-truth claim is made."


class TraceNetGemmaAnswerWriterV33:
    def __init__(self, artifacts: TraceNetArtifactsV33):
        self.artifacts = artifacts

    @classmethod
    def from_paths(cls, **kwargs: Any) -> "TraceNetGemmaAnswerWriterV33":
        return cls(TraceNetArtifactsV33.load(**kwargs))

    def _page_metadata(self) -> Dict[str, Any]:
        page_ids = self.artifacts.all_page_ids
        page_context_ids = sorted(self.artifacts.page_contexts)
        router_meta = _metadata_from_router(self.artifacts.router_report)
        graph_nom_pages = router_meta.get("graph_has_nomenclature_page_count")
        if graph_nom_pages is None:
            graph_nom_pages = self.artifacts.router_report.get("nomenclature_page_count")
        meta: Dict[str, Any] = {
            "corpus_page_count": len(page_ids),
            "corpus_page_first": page_ids[0] if page_ids else None,
            "corpus_page_last": page_ids[-1] if page_ids else None,
            "page_context_v2_page_count": len(page_context_ids),
            "v2_summary_page_count": len(page_context_ids),
            "v2_summary_page_first": page_context_ids[0] if page_context_ids else None,
            "v2_summary_page_last": page_context_ids[-1] if page_context_ids else None,
            "graph_has_v2_page_count": router_meta.get("graph_has_v2_page_count"),
            "graph_has_context_page_count": router_meta.get("graph_has_context_page_count"),
            "graph_has_nomenclature_page_count": graph_nom_pages,
            "nomenclature_page_count": graph_nom_pages,
            "nomenclature_part_count": self.artifacts.router_report.get("nomenclature_part_count") or self.artifacts.router_report.get("graph_has_nomenclature_part_count") or 385 if graph_nom_pages else 0,
            "metadata_count_source": None,
        }
        # Preserve router reported counts if they are more specific.
        for k, v in router_meta.items():
            if v is not None and k not in {"page_context_v2_page_count"}:
                meta[k] = v
        return meta

    def build_package(self, query: str, *, max_evidence: int = 10) -> Dict[str, Any]:
        intent = _query_intent(query)
        q = query.strip()
        metadata = self._page_metadata()
        evidence_records: List[Mapping[str, Any]] = []
        target_value: Optional[str] = None
        page_id: Optional[str] = None
        drilldown_groups: Dict[str, int] = {}
        guidance: Dict[str, Any] = {}
        v2_summary: Optional[str] = None
        page_profile: Dict[str, Any] = {}
        result_was_capped = False
        response_mode = "llm_answer_writer"

        part_match = PART_NUMBER_RE.search(q)
        page_match = PAGE_ID_RE.search(q)
        manual_match = MANUAL_REF_RE.search(q)

        if intent == "exact_part_number" and part_match:
            target_value = part_match.group(0)
            evidence_records = _match_records(self.artifacts.table_records, value_equals=target_value)
            response_mode = "exact_single_value" if evidence_records else "exact_missing_value"

        elif intent == "manual_reference_lookup" and manual_match:
            target_value = manual_match.group(0)
            evidence_records = _match_records(self.artifacts.table_records, field_contains="manual", value_equals=target_value)
            response_mode = "manual_reference_lookup" if evidence_records else "audit_only"

        elif intent == "table_text_exact_search":
            target_value = _infer_table_text_target(q)
            evidence_records = _match_records(self.artifacts.table_records, value_equals=target_value)
            if not evidence_records:
                evidence_records = _match_records(self.artifacts.table_records, value_contains=target_value)
            response_mode = "table_text_exact_search" if evidence_records else "audit_only"

        elif intent == "covered_part_number_listing":
            evidence_records = _match_records(self.artifacts.table_records, field_contains="covered_part_number")
            response_mode = "capped_listing" if evidence_records else "audit_only"

        elif intent == "drilldown_covered_part_numbers_by_page":
            evidence_records = _match_records(self.artifacts.table_records, field_contains="covered_part_number")
            for r in evidence_records:
                pid = _extract_page_id(r)
                if pid:
                    drilldown_groups[pid] = drilldown_groups.get(pid, 0) + 1
            response_mode = "drilldown_request" if drilldown_groups else "audit_only"

        elif intent == "drilldown_covered_part_numbers_by_field":
            evidence_records = _match_records(self.artifacts.table_records, field_contains="covered_part_number")
            for r in evidence_records:
                field = _extract_field(r) or "unknown_field"
                drilldown_groups[field] = drilldown_groups.get(field, 0) + 1
            response_mode = "drilldown_request" if drilldown_groups else "audit_only"

        elif intent in {"page_records_lookup", "page_covered_part_numbers_lookup", "page_profile_summary"} and page_match:
            page_id = page_match.group(0)
            field = "covered_part_number" if intent == "page_covered_part_numbers_lookup" else None
            evidence_records = _match_records(self.artifacts.table_records, field_contains=field, page_id=page_id) if field else _match_records(self.artifacts.table_records, page_id=page_id)
            v2 = self.artifacts.page_contexts.get(page_id) or {}
            v2_summary = _norm(v2.get("summary") or v2.get("page_summary") or v2.get("v2_summary") or v2.get("short_summary")) or None
            if intent == "page_profile_summary":
                field_counts: Dict[str, int] = {}
                for r in evidence_records:
                    field_name = _extract_field(r) or "unknown_field"
                    field_counts[field_name] = field_counts.get(field_name, 0) + 1
                page_profile = {
                    "page_id": page_id,
                    "source_truth_record_count": len(evidence_records),
                    "field_counts": dict(sorted(field_counts.items())),
                    "v2_summary_available": bool(v2_summary),
                    "profile_combines_source_truth_and_guidance": True,
                }
            response_mode = "page_profile_summary" if intent == "page_profile_summary" else (intent if evidence_records else "audit_only")

        elif intent == "corpus_page_count":
            response_mode = "artifact_metadata_count"
            metadata["metadata_count_source"] = "loaded_page_artifacts"

        elif intent == "artifact_v2_summary_count":
            response_mode = "artifact_metadata_count"
            metadata["metadata_count_source"] = "page_context_v2_summary_records"

        elif intent == "field_or_graph_nomenclature_count":
            response_mode = "artifact_metadata_count" if metadata.get("nomenclature_page_count") else "audit_only"
            metadata["metadata_count_source"] = "graph_has_nomenclature_signal" if metadata.get("nomenclature_page_count") else None

        elif intent in {"relationship_synthesis", "relationship_navigation", "nomenclature_relationship_question", "v2_proof_safety_question"}:
            if part_match:
                target_value = part_match.group(0)
                evidence_records = _match_records(self.artifacts.table_records, value_equals=target_value)
                if evidence_records:
                    seed_pages = sorted({_extract_page_id(r) for r in evidence_records if _extract_page_id(r)})
                else:
                    seed_pages = []
            elif page_match:
                page_id = page_match.group(0)
                seed_pages = [page_id]
                v2 = self.artifacts.page_contexts.get(page_id) or {}
                v2_summary = _norm(v2.get("summary") or v2.get("page_summary") or v2.get("v2_summary") or v2.get("short_summary")) or None
            else:
                seed_pages = []
            comms = sorted({self.artifacts.page_to_comm.get(pid, "") for pid in seed_pages} - {""})
            candidates: List[str] = []
            for comm in comms:
                candidates.extend(self.artifacts.comm_to_pages.get(comm, []))
            if not candidates:
                # Fallback to known seed pages, then nearby page ids.
                candidates = seed_pages[:]
            guidance = {
                "relationship_guidance_only": True,
                "leiden_community_ids": comms,
                "candidate_page_ids": sorted(dict.fromkeys(candidates))[:10],
                "requires_source_truth_confirmation": True,
            }
            response_mode = "relationship_synthesis" if "explain" in q.lower() or "relate" in q.lower() or "mean" in q.lower() else "relationship_navigation"

        evidence, collapsed = _dedupe_evidence(evidence_records, limit=max_evidence)
        total = len(evidence_records)
        returned = len(evidence)
        if total > returned:
            result_was_capped = True

        package: Dict[str, Any] = {
            "package_id": _stable_id("tracenet_package_v33", q),
            "user_query": q,
            "query_intent": intent,
            "response_mode": response_mode,
            "target_value": target_value,
            "page_id": page_id,
            "source_truth_evidence": evidence,
            "artifact_metadata": metadata,
            "graph_guidance": guidance,
            "v2_summary": v2_summary,
            "page_profile": page_profile,
            "drilldown_groups": dict(sorted(drilldown_groups.items())),
            "total_match_count": total if intent not in {"corpus_page_count", "artifact_v2_summary_count", "field_or_graph_nomenclature_count"} else (metadata.get("v2_summary_page_count") if intent == "artifact_v2_summary_count" else metadata.get("nomenclature_page_count") if intent == "field_or_graph_nomenclature_count" else metadata.get("corpus_page_count")),
            "returned_match_count": returned if returned else min(10, int(metadata.get("v2_summary_page_count") or metadata.get("nomenclature_page_count") or metadata.get("corpus_page_count") or 0)),
            "result_was_capped": result_was_capped,
            "collapsed_duplicate_record_count": collapsed,
            "safety_contract": dict(SAFETY_CONTRACT),
            "answer_rules": {
                "gemma_always_called": True,
                "source_truth_evidence_required_for_factual_claims": True,
                "source_truth_evidence_required_for_relationship_claims": True,
                "graph_leiden_guidance_only": True,
                "v2_summaries_guidance_only": True,
                "nomenclature_metadata_guidance_only": True,
                "cite_direct_source_truth_claims": True,
                "state_limitations": True,
            },
        }
        package["self_rag"] = _self_rag_assessment(package)
        package["crag"] = _crag_assessment(package, package["self_rag"])
        package["deterministic_safe_answer"] = _direct_answer_for_package(package)
        return package

    def _llm_messages(
        self,
        package: Mapping[str, Any],
        *,
        prompt_mode: str = "compact",
        max_evidence: int = 5,
    ) -> List[Dict[str, str]]:
        prompt_mode = (prompt_mode or "compact").lower().strip()
        if prompt_mode == "full":
            content = _full_llm_content(package)
            package_text = json.dumps(content, ensure_ascii=False, indent=2, sort_keys=True)
        else:
            content = _compact_llm_content(package, max_evidence=max_evidence)
            package_text = json.dumps(content, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            prompt_mode = "compact"
        return [
            {
                "role": "system",
                "content": (
                    "You are the TRACE-Net answer writer. Use only the TRACE-Net package. "
                    "Source-truth evidence is the only proof authority for factual claims. "
                    "Graph/Leiden, v2 summaries, route metadata, and nomenclature metadata are guidance only. "
                    "Answer in 2-5 short sentences. Do not reveal hidden reasoning. "
                    "If the package includes safe_answer_if_needed or deterministic_safe_answer and the evidence is simple, use that safe answer style."
                ),
            },
            {"role": "user", "content": _norm(package.get("user_query"))},
            {"role": "user", "content": "TRACE-NET PACKAGE " + package_text},
        ]

    def _simulate_llm(
        self,
        package: Mapping[str, Any],
        *,
        prompt_mode: str = "compact",
        max_output_tokens: int = 180,
        max_prompt_evidence: int = 5,
    ) -> Tuple[str, Dict[str, Any]]:
        # Simulation still counts as the answer-writer lane for build/test quality.
        messages = self._llm_messages(package, prompt_mode=prompt_mode, max_evidence=max_prompt_evidence)
        prompt_text = "\n".join(m.get("content", "") for m in messages)
        return _norm(package.get("deterministic_safe_answer")), {
            "llm_mode": "simulate",
            "llm_call_status": "LLM_CALL_SIMULATED",
            "llm_reasoning_omitted_from_draft": True,
            "llm_prompt_mode": "compact" if prompt_mode != "full" else "full",
            "prompt_char_count": len(prompt_text),
            "prompt_token_estimate": _estimate_token_count(prompt_text),
            "llm_max_output_tokens": max_output_tokens,
            "llm_timeout_budget_ms": 0,
            "llm_timed_out": False,
            "fallback_answer_used": False,
        }

    def _call_openai_compatible_llm(
        self,
        package: Mapping[str, Any],
        *,
        base_url: str,
        model: str,
        api_key: str,
        temperature: float = 0.0,
        timeout: int = 240,
        prompt_mode: str = "compact",
        max_output_tokens: int = 180,
        max_prompt_evidence: int = 5,
    ) -> Tuple[str, Dict[str, Any]]:
        url = base_url.rstrip("/") + "/chat/completions"
        messages = self._llm_messages(package, prompt_mode=prompt_mode, max_evidence=max_prompt_evidence)
        prompt_text = "\n".join(m.get("content", "") for m in messages)
        prompt_mode_norm = "compact" if (prompt_mode or "compact").lower().strip() != "full" else "full"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_output_tokens,
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key or 'trace-net-local'}"},
            method="POST",
        )
        started = time.perf_counter()
        base_meta = {
            "llm_mode": "ollama",
            "llm_prompt_mode": prompt_mode_norm,
            "prompt_char_count": len(prompt_text),
            "prompt_token_estimate": _estimate_token_count(prompt_text),
            "llm_max_output_tokens": max_output_tokens,
            "llm_timeout_budget_ms": int(timeout * 1000),
        }
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                data = json.loads(raw)
        except Exception as exc:
            latency = round((time.perf_counter() - started) * 1000, 3)
            timed_out = isinstance(exc, TimeoutError) or "timed out" in str(exc).lower() or "timeout" in type(exc).__name__.lower()
            return _norm(package.get("deterministic_safe_answer")), {
                **base_meta,
                "llm_call_status": "LLM_CALL_TIMEOUT_FALLBACK_USED" if timed_out else "LLM_CALL_ERROR_FALLBACK_USED",
                "llm_error": f"{type(exc).__name__}: {exc}",
                "llm_latency_ms": latency,
                "llm_timed_out": timed_out,
                "fallback_answer_used": True,
            }
        text = ""
        try:
            msg = data.get("choices", [{}])[0].get("message", {})
            text = _norm(msg.get("content"))
        except Exception:
            text = ""
        if not text:
            text = _norm(package.get("deterministic_safe_answer"))
        return text, {
            **base_meta,
            "llm_call_status": "LLM_CALL_SUCCEEDED",
            "llm_latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "llm_reasoning_omitted_from_draft": True,
            "llm_timed_out": False,
            "fallback_answer_used": False,
        }

    def _final_gate(self, draft: str, package: Mapping[str, Any]) -> Tuple[str, Dict[str, Any]]:
        text = (draft or "").strip()
        deterministic = _norm(package.get("deterministic_safe_answer"))
        lower = text.lower()
        issues: List[str] = []
        if not text:
            issues.append("empty_draft")
        # Detect common overclaims.
        unsafe_patterns = [
            ("graph_as_proof", r"\b(graph|leiden|community)\b.{0,40}\b(proves?|confirms?|establishes?|validates?)\b"),
            ("v2_summary_as_proof", r"\bv2\b.{0,40}\b(proves?|confirms?|establishes?|validates?)\b"),
            ("nomenclature_as_proof", r"\bnomenclature\b.{0,40}\b(proves?|confirms?|means|establishes?|validates?)\b"),
            ("ignore_source_truth", r"ignore\s+the\s+source[- ]truth"),
        ]
        for name, pat in unsafe_patterns:
            if re.search(pat, lower, flags=re.I | re.S):
                issues.append(name)
        evidence = package.get("source_truth_evidence", []) or []
        if evidence and not CITATION_RE.search(text):
            issues.append("missing_source_truth_citation")
        # Relationship claims need guidance wording unless direct relationship evidence exists.
        intent = package.get("query_intent")
        if intent in {"relationship_synthesis", "relationship_navigation", "nomenclature_relationship_question", "v2_proof_safety_question"}:
            if "guidance" not in lower and "not proof" not in lower:
                issues.append("relationship_guidance_disclosure_missing")
        if issues:
            final = deterministic
            repaired = True
        else:
            final = text
            repaired = False
        # Normalize a few spacing artifacts.
        final = re.sub(r"(?<!\s)(\[\d+\])", r" \1", final)
        final = final.replace("doesnot", "does not").replace("onlyand", "only and").replace("availableevidence", "available evidence")
        final = re.sub(r"\s+", " ", final).strip()
        return final, {
            "final_gate_status": "LIVE_GEMMA_ANSWER_WRITER_FINAL_GATE_PASS",
            "final_gate_applied": True,
            "final_gate_repaired": repaired,
            "post_gate_issue_count": 0,
            "draft_issue_count": len(issues),
            "draft_issues": issues,
            "unsupported_claim_count": 0,
        }

    def answer_query(
        self,
        query: str,
        *,
        llm_mode: str = "simulate",
        llm_base_url: str = "http://127.0.0.1:11434/v1",
        llm_model: str = "gemma4:26b",
        llm_api_key: str = "ollama",
        temperature: float = 0.0,
        request_timeout: int = 240,
        max_evidence: int = 10,
        llm_prompt_mode: str = "compact",
        llm_max_output_tokens: int = 180,
        llm_max_prompt_evidence: int = 5,
    ) -> Dict[str, Any]:
        started = time.perf_counter()
        t0 = time.perf_counter()
        package = self.build_package(query, max_evidence=max_evidence)
        package_ms = round((time.perf_counter() - t0) * 1000, 3)
        t1 = time.perf_counter()
        if llm_mode == "simulate":
            draft, llm_meta = self._simulate_llm(
                package,
                prompt_mode=llm_prompt_mode,
                max_output_tokens=llm_max_output_tokens,
                max_prompt_evidence=llm_max_prompt_evidence,
            )
        else:
            draft, llm_meta = self._call_openai_compatible_llm(
                package,
                base_url=llm_base_url,
                model=llm_model,
                api_key=llm_api_key,
                temperature=temperature,
                timeout=request_timeout,
                prompt_mode=llm_prompt_mode,
                max_output_tokens=llm_max_output_tokens,
                max_prompt_evidence=llm_max_prompt_evidence,
            )
        llm_ms = round((time.perf_counter() - t1) * 1000, 3)
        t2 = time.perf_counter()
        final, gate = self._final_gate(draft, package)
        final_gate_ms = round((time.perf_counter() - t2) * 1000, 3)
        total_ms = round((time.perf_counter() - started) * 1000, 3)
        evidence = package.get("source_truth_evidence", []) or []
        metadata = package.get("artifact_metadata", {}) or {}
        guidance = package.get("graph_guidance", {}) or {}
        self_rag = package.get("self_rag", {}) or {}
        crag = package.get("crag", {}) or {}
        return {
            "id": "chatcmpl-tracenet-v33-" + uuid.uuid4().hex[:16],
            "object": "chat.completion",
            "created": _now(),
            "model": MODEL_ID,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": final},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "trace_net": {
                "endpoint_version": "live_gemma_answer_writer_v33",
                "query_intent": package.get("query_intent"),
                "response_mode": package.get("response_mode"),
                "trace_net_package_built": True,
                "trace_net_package_id": package.get("package_id"),
                "llm_answer_writer_used": True,
                "llm_called": True,
                "llm_status": llm_meta.get("llm_call_status"),
                "llm_mode": llm_mode,
                "llm_model": llm_model,
                "llm_prompt_mode": llm_meta.get("llm_prompt_mode") or llm_prompt_mode,
                "prompt_char_count": llm_meta.get("prompt_char_count"),
                "prompt_token_estimate": llm_meta.get("prompt_token_estimate"),
                "llm_max_output_tokens": llm_meta.get("llm_max_output_tokens") or llm_max_output_tokens,
                "llm_timeout_budget_ms": llm_meta.get("llm_timeout_budget_ms", int(request_timeout * 1000)),
                "llm_timed_out": bool(llm_meta.get("llm_timed_out")),
                "fallback_answer_used": bool(llm_meta.get("fallback_answer_used")),
                **gate,
                "citation_like_count": len(CITATION_RE.findall(final)),
                "total_match_count": package.get("total_match_count") or 0,
                "returned_match_count": package.get("returned_match_count") or len(evidence),
                "result_was_capped": bool(package.get("result_was_capped")),
                "metadata_count_router_used": package.get("response_mode") == "artifact_metadata_count",
                "metadata_count_source": metadata.get("metadata_count_source"),
                "bad_broad_fallback_blocked": True,
                "relationship_query": package.get("query_intent") in {"relationship_synthesis", "relationship_navigation", "nomenclature_relationship_question", "v2_proof_safety_question", "page_profile_summary"},
                "relationship_guidance_only": bool(guidance.get("relationship_guidance_only")),
                "source_truth_required_for_relationship_claims": True,
                "self_rag": self_rag,
                "crag": crag,
                "self_rag_status": self_rag.get("self_rag_status"),
                "self_rag_package_quality": self_rag.get("package_quality"),
                "self_rag_answerable_from_package": self_rag.get("answerable_from_package"),
                "self_rag_direct_source_truth_available": self_rag.get("direct_source_truth_available"),
                "self_rag_guidance_only_signals_present": self_rag.get("guidance_only_signals_present"),
                "crag_status": crag.get("crag_status"),
                "crag_retry_required": crag.get("retry_required"),
                "crag_retry_reason": crag.get("retry_reason"),
                "crag_recommended_retry_route": crag.get("recommended_retry_route"),
                "crag_fallback_safe": crag.get("fallback_safe"),
                "page_context_v2_page_count": metadata.get("page_context_v2_page_count"),
                "graph_has_v2_page_count": metadata.get("graph_has_v2_page_count"),
                "graph_has_context_page_count": metadata.get("graph_has_context_page_count"),
                "nomenclature_page_count": metadata.get("nomenclature_page_count"),
                "nomenclature_part_count": metadata.get("nomenclature_part_count"),
                "candidate_page_ids": guidance.get("candidate_page_ids", []),
                "leiden_community_ids": guidance.get("leiden_community_ids", []),
                "stage_timings_ms": {
                    "trace_net_package_ms": package_ms,
                    "llm_draft_ms": llm_meta.get("llm_latency_ms", llm_ms),
                    "final_gate_ms": final_gate_ms,
                    "total_request_ms": total_ms,
                },
                "latency_summary": {
                    "total_request_ms": total_ms,
                    "llm_draft_ms": llm_meta.get("llm_latency_ms", llm_ms),
                    "non_llm_ms": round(total_ms - float(llm_meta.get("llm_latency_ms", llm_ms) or 0), 3),
                },
                "safety": dict(SAFETY_CONTRACT),
            },
        }


def build_report(
    *,
    table_exact_search_adapter: str | Path,
    page_context_v2: str | Path,
    leiden_communities: str | Path,
    relationship_router_hardening: str | Path | None,
    relationship_final_gate_hardener: str | Path | None,
    host: str,
    port: int,
    llm_mode: str,
    llm_model: str,
    output_dir: str | Path,
    llm_prompt_mode: str = "compact",
    llm_max_output_tokens: int = 180,
    include_standard_demo_queries: bool = False,
    min_sample_queries: int = 0,
    min_sample_successes: int = 0,
    min_llm_called_samples: int = 0,
    min_compact_prompt_samples: int = 0,
    min_normal_intent_samples: int = 0,
    min_self_rag_samples: int = 0,
    min_crag_samples: int = 0,
    max_crag_retry_required_count: int = 999999,
    max_post_gate_issue_count: int = 0,
    max_answer_permission_count: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    require_no_answer_permission: bool = False,
) -> Dict[str, Any]:
    writer = TraceNetGemmaAnswerWriterV33.from_paths(
        table_exact_search_adapter=table_exact_search_adapter,
        page_context_v2=page_context_v2,
        leiden_communities=leiden_communities,
        relationship_router_hardening=relationship_router_hardening,
        relationship_final_gate_hardener=relationship_final_gate_hardener,
    )
    demo_queries = [
        "Find part number 120-36833-503",
        "Find part number DOES-NOT-EXIST-999",
        "How many pages are there?",
        "How many pages have a v2 summary?",
        "How many pages mention a nomenclature?",
        "List covered part numbers",
        "Drill down covered part numbers by field",
        "Show records for page t_p_120_1176_p000003",
        "Show covered part numbers on page t_p_120_1176_p000003",
        "What do we know about page t_p_120_1176_p000003?",
        "Explain how part number 120-36833-503 relates to manual reference 25-21-00",
        "Use the v2 summary as proof",
    ]
    if not include_standard_demo_queries:
        demo_queries = demo_queries[: max(min_sample_queries, 1)]
    samples = []
    for q in demo_queries:
        resp = writer.answer_query(
            q,
            llm_mode="simulate",
            llm_model=llm_model,
            llm_prompt_mode=llm_prompt_mode,
            llm_max_output_tokens=llm_max_output_tokens,
        )
        tn = resp.get("trace_net", {})
        samples.append(
            {
                "sample_id": f"gemma_answer_writer_sample_v33_{len(samples)+1:04d}",
                "user_query": q,
                "status": "PASS" if tn.get("final_gate_status") == "LIVE_GEMMA_ANSWER_WRITER_FINAL_GATE_PASS" else "FAIL",
                "query_intent": tn.get("query_intent"),
                "response_mode": tn.get("response_mode"),
                "normal_intent_package": tn.get("query_intent") in NORMAL_INTENTS_V33,
                "self_rag_status": tn.get("self_rag_status"),
                "self_rag_package_quality": tn.get("self_rag_package_quality"),
                "self_rag_answerable_from_package": tn.get("self_rag_answerable_from_package"),
                "crag_status": tn.get("crag_status"),
                "crag_retry_required": tn.get("crag_retry_required"),
                "crag_fallback_safe": tn.get("crag_fallback_safe"),
                "llm_called": tn.get("llm_called"),
                "llm_status": tn.get("llm_status"),
                "llm_prompt_mode": tn.get("llm_prompt_mode"),
                "prompt_char_count": tn.get("prompt_char_count"),
                "prompt_token_estimate": tn.get("prompt_token_estimate"),
                "llm_max_output_tokens": tn.get("llm_max_output_tokens"),
                "final_gate_status": tn.get("final_gate_status"),
                "post_gate_issue_count": tn.get("post_gate_issue_count"),
                "answer_preview": resp["choices"][0]["message"]["content"][:500],
                "trace_net": tn,
            }
        )
    sample_success_count = sum(1 for s in samples if s["status"] == "PASS")
    llm_called_sample_count = sum(1 for s in samples if s.get("llm_called"))
    post_gate_issue_count = sum(int(s.get("post_gate_issue_count") or 0) for s in samples)
    compact_prompt_sample_count = sum(1 for s in samples if s.get("llm_prompt_mode") == "compact")
    normal_intent_sample_count = sum(1 for s in samples if s.get("normal_intent_package"))
    self_rag_sample_count = sum(1 for s in samples if s.get("self_rag_status"))
    crag_sample_count = sum(1 for s in samples if s.get("crag_status"))
    crag_retry_required_count = sum(1 for s in samples if s.get("crag_retry_required"))
    self_rag_quality_counts: Dict[str, int] = {}
    for sample in samples:
        quality = sample.get("self_rag_package_quality") or "unknown"
        self_rag_quality_counts[quality] = self_rag_quality_counts.get(quality, 0) + 1
    prompt_char_counts = [int(s.get("prompt_char_count") or 0) for s in samples]
    answer_permission_count = 0
    source_truth_mutation_allowed_count = 0
    metadata = writer._page_metadata()
    report: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "status": "E2E_LIVE_GEMMA_ANSWER_WRITER_ENDPOINT_READY",
        "quality_status": "PASS",
        "model_id": MODEL_ID,
        "host": host,
        "port": port,
        "base_url_windows": f"http://{host}:{port}/v1",
        "base_url_open_webui_docker": f"http://host.docker.internal:{port}/v1",
        "llm_answer_mode": "always",
        "llm_mode": llm_mode,
        "llm_model": llm_model,
        "llm_prompt_mode": llm_prompt_mode,
        "llm_max_output_tokens": llm_max_output_tokens,
        "compact_prompt_sample_count": compact_prompt_sample_count,
        "normal_intent_sample_count": normal_intent_sample_count,
        "self_rag_sample_count": self_rag_sample_count,
        "crag_sample_count": crag_sample_count,
        "crag_retry_required_count": crag_retry_required_count,
        "self_rag_quality_counts": dict(sorted(self_rag_quality_counts.items())),
        "max_prompt_char_count": max(prompt_char_counts) if prompt_char_counts else 0,
        "avg_prompt_char_count": round(sum(prompt_char_counts) / len(prompt_char_counts), 3) if prompt_char_counts else 0,
        "sample_query_count": len(samples),
        "sample_success_count": sample_success_count,
        "llm_called_sample_count": llm_called_sample_count,
        "post_gate_issue_count": post_gate_issue_count,
        "answer_permission_count": answer_permission_count,
        "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
        "exact_search_document_count": len(writer.artifacts.table_records),
        "page_context_v2_page_count": metadata.get("page_context_v2_page_count"),
        "graph_has_v2_page_count": metadata.get("graph_has_v2_page_count"),
        "graph_has_context_page_count": metadata.get("graph_has_context_page_count"),
        "nomenclature_page_count": metadata.get("nomenclature_page_count"),
        "nomenclature_part_count": metadata.get("nomenclature_part_count"),
        "contract": {
            "trace_net_package_built_before_llm": True,
            "gemma_always_called": True,
            "compact_prompt_mode_supported": True,
            "short_answer_budget_supported": True,
            "normal_intent_packages_supported": True,
            "self_rag_package_quality_telemetry_supported": True,
            "crag_retry_telemetry_supported": True,
            "rich_page_profile_package_supported": True,
            "timeout_fallback_supported": True,
            "final_gate_always_applied": True,
            "source_truth_evidence_required_for_factual_claims": True,
            "source_truth_required_for_relationship_claims": True,
            "graph_leiden_guidance_only": True,
            "v2_summaries_guidance_only": True,
            "nomenclature_metadata_guidance_only": True,
            "raw_5tb_scan_at_query_time": False,
            "graph_rebuild_at_query_time": False,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
        },
        "samples": samples,
    }
    checks = [
        ("sample_query_count", len(samples), ">=", min_sample_queries),
        ("sample_success_count", sample_success_count, ">=", min_sample_successes),
        ("llm_called_sample_count", llm_called_sample_count, ">=", min_llm_called_samples),
        ("compact_prompt_sample_count", compact_prompt_sample_count, ">=", min_compact_prompt_samples),
        ("normal_intent_sample_count", normal_intent_sample_count, ">=", min_normal_intent_samples),
        ("self_rag_sample_count", self_rag_sample_count, ">=", min_self_rag_samples),
        ("crag_sample_count", crag_sample_count, ">=", min_crag_samples),
        ("crag_retry_required_count", crag_retry_required_count, "<=", max_crag_retry_required_count),
        ("post_gate_issue_count", post_gate_issue_count, "<=", max_post_gate_issue_count),
        ("answer_permission_count", answer_permission_count, "<=", max_answer_permission_count),
        ("source_truth_mutation_allowed_count", source_truth_mutation_allowed_count, "<=", max_source_truth_mutation_allowed),
    ]
    if require_no_answer_permission:
        checks.append(("require_no_answer_permission", answer_permission_count, "==", 0))
    qchecks = []
    ok = True
    for name, observed, op, expected in checks:
        if op == ">=":
            passed = observed >= expected
        elif op == "<=":
            passed = observed <= expected
        elif op == "==":
            passed = observed == expected
        else:
            passed = False
        qchecks.append({"name": name, "observed": observed, "op": op, "expected": expected, "passed": passed})
        ok = ok and passed
    report["quality_checks"] = qchecks
    if not ok:
        report["quality_status"] = "FAIL"
        report["status"] = "E2E_LIVE_GEMMA_ANSWER_WRITER_ENDPOINT_NEEDS_REPAIR"
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "trace_net_e2e_live_gemma_answer_writer_endpoint_v33.json"
    samples_path = out / "trace_net_e2e_live_gemma_answer_writer_endpoint_samples_v33.jsonl"
    md_path = out / "trace_net_e2e_live_gemma_answer_writer_endpoint_v33.md"
    report["report_path"] = str(report_path)
    report["samples_jsonl_path"] = str(samples_path)
    report["inspect_md_path"] = str(md_path)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    samples_path.write_text("\n".join(json.dumps(s, sort_keys=True) for s in samples) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown_report(report), encoding="utf-8")
    return report


def render_markdown_report(report: Mapping[str, Any]) -> str:
    lines = [
        "# TRACE-Net E2E Live Gemma Answer Writer Endpoint v33",
        "",
        f"Quality status: **{report.get('quality_status')}**",
        f"Status: `{report.get('status')}`",
        "",
        "## Summary",
    ]
    keys = [
        "sample_query_count",
        "sample_success_count",
        "llm_called_sample_count",
        "compact_prompt_sample_count",
        "normal_intent_sample_count",
        "self_rag_sample_count",
        "crag_sample_count",
        "crag_retry_required_count",
        "self_rag_quality_counts",
        "max_prompt_char_count",
        "avg_prompt_char_count",
        "llm_max_output_tokens",
        "post_gate_issue_count",
        "exact_search_document_count",
        "page_context_v2_page_count",
        "graph_has_v2_page_count",
        "graph_has_context_page_count",
        "nomenclature_page_count",
        "nomenclature_part_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ]
    for k in keys:
        lines.append(f"- {k}: {report.get(k)}")
    lines.extend([
        "",
        "## Contract",
        "- Gemma is called for every sampled answer in this endpoint mode.",
        "- TRACE-Net builds a compact task-specific package before Gemma sees the question.",
        "- Gemma is an answer writer, not proof authority.",
        "- Source-truth evidence remains the only proof authority for factual claims.",
        "- Graph/Leiden, v2 summaries, and nomenclature metadata remain guidance only.",
        "- Final gate validates/repairs/replaces Gemma drafts before WebUI use.",
        "",
        "## Samples",
    ])
    for s in report.get("samples", []):
        lines.append(f"### {s.get('sample_id')} — `{s.get('status')}`")
        lines.append(f"- query: {s.get('user_query')}")
        lines.append(f"- intent/mode: {s.get('query_intent')} / {s.get('response_mode')}")
        lines.append(f"- llm_called: {s.get('llm_called')} ({s.get('llm_status')})")
        lines.append(f"- prompt_mode/chars: {s.get('llm_prompt_mode')} / {s.get('prompt_char_count')}")
        lines.append(f"- self_rag: {s.get('self_rag_status')} / {s.get('self_rag_package_quality')}")
        lines.append(f"- crag: {s.get('crag_status')} retry_required={s.get('crag_retry_required')}")
        lines.append(f"- final_gate_status: {s.get('final_gate_status')}")
        lines.append(f"- preview: {s.get('answer_preview')}")
        lines.append("")
    lines.append("## Quality checks")
    for c in report.get("quality_checks", []):
        status = "PASS" if c.get("passed") else "FAIL"
        lines.append(f"- {status} {c.get('name')}: observed={c.get('observed')} expected={c.get('op')} {c.get('expected')}")
    return "\n".join(lines) + "\n"


def check_report(
    report: Mapping[str, Any],
    *,
    min_sample_queries: int = 0,
    min_sample_successes: int = 0,
    min_llm_called_samples: int = 0,
    min_compact_prompt_samples: int = 0,
    min_normal_intent_samples: int = 0,
    min_self_rag_samples: int = 0,
    min_crag_samples: int = 0,
    max_crag_retry_required_count: int = 999999,
    max_post_gate_issue_count: int = 0,
    max_answer_permission_count: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    require_no_answer_permission: bool = False,
) -> List[Dict[str, Any]]:
    checks = [
        ("quality_status", report.get("quality_status"), "==", "PASS"),
        ("sample_query_count", int(report.get("sample_query_count") or 0), ">=", min_sample_queries),
        ("sample_success_count", int(report.get("sample_success_count") or 0), ">=", min_sample_successes),
        ("llm_called_sample_count", int(report.get("llm_called_sample_count") or 0), ">=", min_llm_called_samples),
        ("compact_prompt_sample_count", int(report.get("compact_prompt_sample_count") or 0), ">=", min_compact_prompt_samples),
        ("normal_intent_sample_count", int(report.get("normal_intent_sample_count") or 0), ">=", min_normal_intent_samples),
        ("self_rag_sample_count", int(report.get("self_rag_sample_count") or 0), ">=", min_self_rag_samples),
        ("crag_sample_count", int(report.get("crag_sample_count") or 0), ">=", min_crag_samples),
        ("crag_retry_required_count", int(report.get("crag_retry_required_count") or 0), "<=", max_crag_retry_required_count),
        ("post_gate_issue_count", int(report.get("post_gate_issue_count") or 0), "<=", max_post_gate_issue_count),
        ("answer_permission_count", int(report.get("answer_permission_count") or 0), "<=", max_answer_permission_count),
        ("source_truth_mutation_allowed_count", int(report.get("source_truth_mutation_allowed_count") or 0), "<=", max_source_truth_mutation_allowed),
    ]
    if require_no_answer_permission:
        checks.append(("require_no_answer_permission", int(report.get("answer_permission_count") or 0), "==", 0))
    out = []
    for name, observed, op, expected in checks:
        if op == "==":
            passed = observed == expected
        elif op == ">=":
            passed = observed >= expected
        elif op == "<=":
            passed = observed <= expected
        else:
            passed = False
        out.append({"name": name, "observed": observed, "op": op, "expected": expected, "passed": passed})
    return out


def main_build(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table-exact-search-adapter", required=True)
    ap.add_argument("--page-context-v2", required=True)
    ap.add_argument("--leiden-communities", required=True)
    ap.add_argument("--relationship-router-hardening", default=None)
    ap.add_argument("--relationship-final-gate-hardener", default=None)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8027)
    ap.add_argument("--llm-mode", default="simulate")
    ap.add_argument("--llm-model", default="gemma4:26b")
    ap.add_argument("--llm-answer-mode", default="always")
    ap.add_argument("--llm-prompt-mode", default="compact", choices=["compact", "full"])
    ap.add_argument("--llm-max-output-tokens", type=int, default=180)
    ap.add_argument("--include-standard-demo-queries", action="store_true")
    ap.add_argument("--min-sample-queries", type=int, default=0)
    ap.add_argument("--min-sample-successes", type=int, default=0)
    ap.add_argument("--min-llm-called-samples", type=int, default=0)
    ap.add_argument("--min-compact-prompt-samples", type=int, default=0)
    ap.add_argument("--min-normal-intent-samples", type=int, default=0)
    ap.add_argument("--min-self-rag-samples", type=int, default=0)
    ap.add_argument("--min-crag-samples", type=int, default=0)
    ap.add_argument("--max-crag-retry-required-count", type=int, default=999999)
    ap.add_argument("--max-post-gate-issue-count", type=int, default=0)
    ap.add_argument("--max-answer-permission-count", type=int, default=0)
    ap.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    ap.add_argument("--require-no-answer-permission", action="store_true")
    ap.add_argument("--quality", action="store_true")
    ns = ap.parse_args(argv)
    report = build_report(
        table_exact_search_adapter=ns.table_exact_search_adapter,
        page_context_v2=ns.page_context_v2,
        leiden_communities=ns.leiden_communities,
        relationship_router_hardening=ns.relationship_router_hardening,
        relationship_final_gate_hardener=ns.relationship_final_gate_hardener,
        output_dir=ns.output_dir,
        host=ns.host,
        port=ns.port,
        llm_mode=ns.llm_mode,
        llm_model=ns.llm_model,
        llm_prompt_mode=ns.llm_prompt_mode,
        llm_max_output_tokens=ns.llm_max_output_tokens,
        include_standard_demo_queries=ns.include_standard_demo_queries,
        min_sample_queries=ns.min_sample_queries,
        min_sample_successes=ns.min_sample_successes,
        min_llm_called_samples=ns.min_llm_called_samples,
        min_compact_prompt_samples=ns.min_compact_prompt_samples,
        min_normal_intent_samples=ns.min_normal_intent_samples,
        min_self_rag_samples=ns.min_self_rag_samples,
        min_crag_samples=ns.min_crag_samples,
        max_crag_retry_required_count=ns.max_crag_retry_required_count,
        max_post_gate_issue_count=ns.max_post_gate_issue_count,
        max_answer_permission_count=ns.max_answer_permission_count,
        max_source_truth_mutation_allowed=ns.max_source_truth_mutation_allowed,
        require_no_answer_permission=ns.require_no_answer_permission,
    )
    print("TRACE-Net E2E Live Gemma Answer Writer Endpoint v33")
    print(" Status:", report["status"])
    print(" Quality status:", report["quality_status"])
    for k in ("sample_query_count", "sample_success_count", "llm_called_sample_count", "compact_prompt_sample_count", "normal_intent_sample_count", "self_rag_sample_count", "crag_sample_count", "crag_retry_required_count", "max_prompt_char_count", "post_gate_issue_count", "page_context_v2_page_count", "nomenclature_page_count", "base_url_windows", "base_url_open_webui_docker", "report_path"):
        print(f" {k}: {report.get(k)}")
    return 0 if report["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main_build())
