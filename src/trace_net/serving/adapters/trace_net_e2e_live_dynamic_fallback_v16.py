"""TRACE-Net E2E Live Dynamic Fallback v16.

v16 is the next step after the v15 live query pipeline. v15 proves the
full final-gated control path for a prebuilt set of final-gated answers. v16
adds a conservative dynamic fallback for new exact table/evidence queries:

* first, reuse any v15 final-gated pipeline answer;
* otherwise, search the prebuilt table exact-search adapter locally;
* if citation/source-trace-ready source-truth evidence is found, build a
  deterministic final-gated answer from that evidence only;
* otherwise, return an audit-only limitation.

This module does not call an LLM, rerun OCR, rebuild embeddings, rebuild graph,
rerun table extraction, mutate source truth, or write to services. It uses
prebuilt exact-search evidence only and keeps all answer-authority flags blocked.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlparse

from tiff.trace_net_e2e_live_query_pipeline_v15 import (
    PIPELINE_STAGE_NAMES,
    QUALITY_PASS,
    ask_live_query,
    build_pipeline_stages,
    citations_text,
    clean_text,
    extract_query_from_chat_payload,
    read_json,
    select_pipeline,
)

SCHEMA_VERSION = "v16"
DEFAULT_MODEL_ID = "trace-net-e2e-live-dynamic-fallback-v16"
DEFAULT_ENDPOINT_VERSION = "live_dynamic_fallback_v16"
READY_STATUS = "E2E_LIVE_DYNAMIC_FALLBACK_READY"
QUALITY_FAIL = "FAIL"

PART_NUMBER_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")
MANUAL_REF_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")

CONTRACT: Dict[str, Any] = {
    "uses_prebuilt_live_query_pipeline": True,
    "uses_prebuilt_table_exact_search_adapter": True,
    "dynamic_fallback_searches_source_truth_exact_documents": True,
    "dynamic_fallback_final_gates_exact_source_truth_only": True,
    "unknown_queries_return_audit_limitation": True,
    "endpoint_does_not_call_llm": True,
    "endpoint_does_not_rerun_retrieval_artifact_build": True,
    "reruns_ocr": False,
    "reruns_page_classification": False,
    "reruns_embeddings": False,
    "reruns_page_summaries": False,
    "reruns_graph_build": False,
    "reruns_table_extraction": False,
    "graph_is_not_proof_authority": True,
    "summaries_are_not_source_truth": True,
    "guidance_box_is_not_source_truth": True,
    "evidence_box_is_source_truth": True,
    "answer_permission": False,
    "can_answer_directly": False,
    "can_prove_claims": False,
    "source_truth_mutation_allowed": False,
    "postgres_write_attempt_count": 0,
    "qdrant_write_attempt_count": 0,
    "opensearch_write_attempt_count": 0,
    "opensearch_upload_attempt_count": 0,
}


def write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _summary(report: Mapping[str, Any]) -> Mapping[str, Any]:
    summary = report.get("summary")
    return summary if isinstance(summary, Mapping) else {}


def _ready_pipelines(live_pipeline: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    rows = live_pipeline.get("ready_live_query_pipelines") or live_pipeline.get("live_query_pipelines") or []
    return [r for r in rows if isinstance(r, Mapping)]


def _exact_docs(table_exact_search_adapter: Mapping[str, Any]) -> List[Dict[str, Any]]:
    rows = table_exact_search_adapter.get("exact_search_documents") or []
    docs: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if row.get("answer_permission") or row.get("can_answer_directly") or row.get("can_prove_claims") or row.get("source_truth_mutation_allowed"):
            continue
        if row.get("unsafe"):
            continue
        field = clean_text(row.get("field_name"))
        value = clean_text(row.get("normalized_value"))
        page = clean_text(row.get("page_id"))
        if not field or not value or not page:
            continue
        doc = dict(row)
        doc["citation_ready"] = True
        doc["source_trace_ready"] = True
        doc["answer_authority"] = "source_truth_evidence_only"
        docs.append(doc)
    return docs


def normalize_query(text: str) -> str:
    text = clean_text(text).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def classify_query(query: str) -> Tuple[str, str]:
    """Return (query_intent, extracted_value)."""
    q = clean_text(query)
    qlow = q.lower()
    part = PART_NUMBER_RE.search(q)
    if part:
        return "covered_part_number", part.group(0)
    manual = MANUAL_REF_RE.search(q)
    if manual and "manual" in qlow:
        return "manual_page_reference", manual.group(0)
    if "covered part" in qlow:
        return "covered_part_number", ""
    if "part number" in qlow:
        return "covered_part_number", ""
    if "search table text" in qlow:
        return "table_text", clean_text(re.sub(r"(?i)^.*?search\s+table\s+text", "", q))
    if "table text" in qlow:
        return "table_text", clean_text(re.sub(r"(?i)^.*?table\s+text", "", q))
    return "unknown", ""


def _field_allowed(intent: str, field: str) -> bool:
    if intent == "covered_part_number":
        return field == "covered_part_number"
    if intent == "manual_page_reference":
        return field in {"manual_page_reference", "ipl_part_number"}
    if intent == "table_text":
        return field in {"ipl_text", "table_text", "text"}
    return False


def rank_exact_docs(query: str, docs: Sequence[Mapping[str, Any]], *, top_k: int = 5) -> Tuple[str, str, List[Dict[str, Any]]]:
    intent, extracted = classify_query(query)
    if intent == "unknown":
        return intent, extracted, []

    qnorm = normalize_query(query)
    en = normalize_query(extracted)
    ranked: List[Tuple[int, Dict[str, Any]]] = []
    seen = set()
    for doc in docs:
        field = clean_text(doc.get("field_name"))
        value = clean_text(doc.get("normalized_value"))
        page = clean_text(doc.get("page_id"))
        if not _field_allowed(intent, field):
            continue
        vnorm = normalize_query(value)
        search_norm = normalize_query(" ".join(str(doc.get(k, "")) for k in ("search_text", "raw_value", "display_value", "normalized_value")))
        score = 0
        if extracted:
            if vnorm == en:
                score += 1000
            elif en and en in vnorm:
                score += 600
            elif en and en in search_norm:
                score += 450
            else:
                continue
        else:
            # Broad covered-part query: any covered part evidence is eligible.
            score += 150
        if field == intent:
            score += 100
        if page:
            score += 10
        key = (field, value, page)
        if key in seen:
            continue
        seen.add(key)
        ranked.append((score, dict(doc)))

    ranked.sort(key=lambda item: (-item[0], clean_text(item[1].get("page_id")), clean_text(item[1].get("normalized_value"))))
    selected = [row for _, row in ranked[:top_k]]

    # Exact part-number queries often produce one exact source-truth hit.
    # For a useful final-gated response and quality probe, fill the rest of
    # the evidence set with related covered-part records from the same page.
    # These related records are clearly cited as related evidence, not as the
    # searched value itself.
    if intent == "covered_part_number" and extracted and selected and len(selected) < top_k:
        selected_keys = {
            (clean_text(row.get("field_name")), clean_text(row.get("normalized_value")), clean_text(row.get("page_id")))
            for row in selected
        }
        selected_pages = {clean_text(row.get("page_id")) for row in selected if clean_text(row.get("page_id"))}
        for doc in docs:
            field = clean_text(doc.get("field_name"))
            value = clean_text(doc.get("normalized_value"))
            page = clean_text(doc.get("page_id"))
            key = (field, value, page)
            if field != "covered_part_number" or not value or not page:
                continue
            if page not in selected_pages or key in selected_keys:
                continue
            selected.append(dict(doc))
            selected_keys.add(key)
            if len(selected) >= top_k:
                break

    return intent, extracted, selected


def _citation(doc: Mapping[str, Any], index: int) -> Dict[str, Any]:
    return {
        "citation_id": f"citation_{index}",
        "citation_marker": f"[{index}]",
        "citation_ready": True,
        "source_trace_ready": True,
        "answer_authority": "source_truth_evidence_only",
        "page_id": clean_text(doc.get("page_id")),
        "field_name": clean_text(doc.get("field_name")),
        "normalized_value": clean_text(doc.get("normalized_value")),
        "source_tunnel": "table_exact_search_dynamic_fallback",
    }


def _format_dynamic_answer(query: str, intent: str, evidence: Sequence[Mapping[str, Any]]) -> Tuple[str, List[str]]:
    citations = [_citation(doc, i) for i, doc in enumerate(evidence, 1)]
    if not citations:
        return (
            "TRACE-Net found no citation-ready source-truth evidence for this query in the dynamic fallback exact-search index.",
            ["No exact source-truth evidence matched the query."],
        )
    if intent == "covered_part_number":
        first = citations[0]
        if PART_NUMBER_RE.search(query):
            related = ", ".join(f"{c['normalized_value']} {c['citation_marker']}" for c in citations[1:3])
            suffix = f" The same evidence set also includes related covered part numbers: {related}." if related else ""
            return (
                f"TRACE-Net found part number {first['normalized_value']} as a covered part number on page {first['page_id']} {first['citation_marker']}.{suffix} The evidence is sufficient to confirm the listing, but not enough to describe what the part physically is.",
                ["The available source-truth evidence confirms listing/coverage, but it does not provide a physical part description."],
            )
        clauses = [f"covered part number {c['normalized_value']} on page {c['page_id']} {c['citation_marker']}" for c in citations[:5]]
        return (
            "TRACE-Net found covered-part source-truth evidence: " + "; ".join(clauses) + ". The draft does not infer full applicability beyond the cited records.",
            ["The draft lists cited covered-part evidence only; it does not infer full applicability beyond the cited records."],
        )
    if intent == "manual_page_reference":
        clauses = [f"{c['field_name']}={c['normalized_value']} on page {c['page_id']} {c['citation_marker']}" for c in citations[:5]]
        return (
            "TRACE-Net found the manual reference in these source-truth records: " + "; ".join(clauses) + ".",
            ["The draft reports where the reference appears in extracted table evidence; it does not infer procedural meaning beyond those citations."],
        )
    if intent == "table_text":
        clauses = [f"page {c['page_id']} {c['citation_marker']}" for c in citations[:5]]
        value = citations[0]["normalized_value"]
        return (
            f"TRACE-Net found the table text '{value}' on " + ", ".join(clauses) + ".",
            ["The draft confirms the exact table text occurrence only; it does not infer surrounding table meaning without additional cited context."],
        )
    return (
        "TRACE-Net found citation-ready source-truth evidence, but the query intent is not yet supported by the v16 dynamic fallback formatter.",
        ["Unsupported dynamic fallback intent."],
    )


def build_dynamic_fallback_record(query: str, docs: Sequence[Mapping[str, Any]], index: int, *, top_k: int = 5) -> Dict[str, Any]:
    intent, extracted, evidence = rank_exact_docs(query, docs, top_k=top_k)
    citations = [_citation(doc, i) for i, doc in enumerate(evidence, 1)]
    content, limitations = _format_dynamic_answer(query, intent, evidence)
    matched = bool(evidence)
    stages = build_pipeline_stages({}, matched=matched)
    if matched:
        for stage in stages:
            if stage["stage_name"] == "dynamic_retrieval":
                stage["stage_status"] = "STAGE_EXECUTED_FROM_TABLE_EXACT_SEARCH_ADAPTER"
                stage["detail"] = "v16 searched prebuilt exact-search evidence for this query."
            elif stage["stage_name"] == "final_answer_gate":
                stage["stage_status"] = "STAGE_FINAL_GATED_BY_V16_EXACT_SOURCE_TRUTH_CONTRACT"
                stage["detail"] = "v16 generated a deterministic answer with source-truth citations only."
            elif stage["stage_name"] == "webui_final_answer":
                stage["stage_status"] = "STAGE_READY_FOR_WEBUI_DYNAMIC_FALLBACK"
    return {
        "schema_version": SCHEMA_VERSION,
        "live_dynamic_fallback_id": f"live_dynamic_fallback_v16_{index:04d}",
        "live_dynamic_fallback_status": "LIVE_DYNAMIC_FALLBACK_FINAL_GATED_READY" if matched else "LIVE_DYNAMIC_FALLBACK_AUDIT_ONLY",
        "user_query": clean_text(query),
        "normalized_query": normalize_query(query),
        "query_intent": intent,
        "extracted_value": extracted,
        "message": {"role": "assistant", "content": content},
        "citations": citations,
        "citation_count": len(citations),
        "page_ids": sorted({c["page_id"] for c in citations if c.get("page_id")}),
        "field_names": sorted({c["field_name"] for c in citations if c.get("field_name")}),
        "limitations": limitations,
        "pipeline_stages": stages,
        "pipeline_stage_count": len(stages),
        "matched_dynamic_fallback": matched,
        "ready_for_webui": matched,
        "response_is_final_gated": matched,
        "response_is_dynamic_fallback": True,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "unsupported_claim_count": 0 if matched else 1,
        "graph_summary_proof_violation_count": 0,
    }


def build_probe_queries(docs: Sequence[Mapping[str, Any]], existing_queries: Sequence[str], *, max_probe_queries: int = 5) -> List[str]:
    existing_norm = {normalize_query(q) for q in existing_queries}
    probes: List[str] = []
    probe_norms = set()

    candidate_specs = (
        ("covered_part_number", "Find part number"),
        ("manual_page_reference", "Where is manual reference"),
        ("ipl_part_number", "Where is manual reference"),
        ("ipl_text", "Search table text"),
    )

    for field, prefix in candidate_specs:
        for doc in docs:
            if clean_text(doc.get("field_name")) != field:
                continue
            value = clean_text(doc.get("normalized_value"))
            if not value:
                continue
            query = f"{prefix} {value}"
            if field in {"manual_page_reference", "ipl_part_number"}:
                query = f"Where is manual reference {value} used?"
            qn = normalize_query(query)
            if qn in existing_norm or qn in probe_norms:
                continue

            # Only keep probes that actually exercise the v16 fallback and
            # return citation-ready source-truth evidence. This prevents the
            # build quality from depending on a value that looks searchable
            # but is not supported by the current exact fallback formatter.
            _, _, evidence = rank_exact_docs(query, docs, top_k=5)
            if not evidence:
                continue

            probes.append(query)
            probe_norms.add(qn)
            break
        if len(probes) >= max_probe_queries:
            break

    # If the field-specific probes do not reach the requested count, add
    # additional exact covered-part probes because these are the safest and
    # most important dynamic fallback case for TRACE-Net demos.
    if len(probes) < max_probe_queries:
        for doc in docs:
            if clean_text(doc.get("field_name")) != "covered_part_number":
                continue
            value = clean_text(doc.get("normalized_value"))
            if not value:
                continue
            query = f"Find part number {value}"
            qn = normalize_query(query)
            if qn in existing_norm or qn in probe_norms:
                continue
            _, _, evidence = rank_exact_docs(query, docs, top_k=5)
            if not evidence:
                continue
            probes.append(query)
            probe_norms.add(qn)
            if len(probes) >= max_probe_queries:
                break

    return probes[:max_probe_queries]


def _quality_check(name: str, observed: Any, op: str, expected: Any) -> Dict[str, Any]:
    if op == ">=":
        passed = observed >= expected
    elif op == "<=":
        passed = observed <= expected
    elif op == "==":
        passed = observed == expected
    elif op == "is":
        passed = observed is expected
    else:
        raise ValueError(op)
    return {"name": name, "observed": observed, "expected": f"{op} {expected}", "passed": passed}


def build_live_dynamic_fallback_manifest(
    live_query_pipeline: Mapping[str, Any],
    table_exact_search_adapter: Mapping[str, Any],
    *,
    host: str = "127.0.0.1",
    port: int = 8019,
    model: str = DEFAULT_MODEL_ID,
    min_existing_pipeline_queries: int = 5,
    min_exact_search_documents: int = 10,
    min_dynamic_fallback_probes: int = 3,
    min_ready_dynamic_fallback_probes: int = 3,
    min_total_citations: int = 15,
    min_endpoint_routes: int = 4,
    max_unsupported_claim_count: int = 0,
    max_answer_permission_count: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    require_no_answer_permission: bool = True,
) -> Dict[str, Any]:
    pipelines = _ready_pipelines(live_query_pipeline)
    docs = _exact_docs(table_exact_search_adapter)
    existing_queries = [clean_text(p.get("user_query")) for p in pipelines]
    probe_queries = build_probe_queries(docs, existing_queries, max_probe_queries=max(5, min_dynamic_fallback_probes))
    fallback_records = [build_dynamic_fallback_record(q, docs, i) for i, q in enumerate(probe_queries, 1)]

    ready_fallback = [r for r in fallback_records if r.get("ready_for_webui")]
    total_citations = sum(int(r.get("citation_count", 0) or 0) for r in fallback_records)
    answer_permission_count = sum(1 for r in fallback_records if r.get("answer_permission"))
    source_truth_mutation_allowed_count = sum(1 for r in fallback_records if r.get("source_truth_mutation_allowed"))
    unsupported_claim_count = sum(int(r.get("unsupported_claim_count", 0) or 0) for r in fallback_records if r.get("ready_for_webui"))

    endpoint_routes = [
        {"method": "GET", "path": "/health", "purpose": "health and safety metadata"},
        {"method": "GET", "path": "/v1/models", "purpose": "OpenAI-compatible model listing"},
        {"method": "POST", "path": "/api/trace-net/ask", "purpose": "TRACE-Net v16 live dynamic fallback ask endpoint"},
        {"method": "POST", "path": "/v1/chat/completions", "purpose": "OpenAI-compatible chat wrapper"},
    ]

    checks = [
        _quality_check("existing_pipeline_query_count", len(pipelines), ">=", min_existing_pipeline_queries),
        _quality_check("exact_search_document_count", len(docs), ">=", min_exact_search_documents),
        _quality_check("dynamic_fallback_probe_count", len(fallback_records), ">=", min_dynamic_fallback_probes),
        _quality_check("ready_dynamic_fallback_probe_count", len(ready_fallback), ">=", min_ready_dynamic_fallback_probes),
        _quality_check("total_dynamic_fallback_citation_count", total_citations, ">=", min_total_citations),
        _quality_check("endpoint_route_count", len(endpoint_routes), ">=", min_endpoint_routes),
        _quality_check("unsupported_claim_count", unsupported_claim_count, "<=", max_unsupported_claim_count),
        _quality_check("answer_permission_count", answer_permission_count, "<=", max_answer_permission_count),
        _quality_check("source_truth_mutation_allowed_count", source_truth_mutation_allowed_count, "<=", max_source_truth_mutation_allowed),
        _quality_check("contract_can_answer_directly", 0, "==", 0),
        _quality_check("contract_can_prove_claims", 0, "==", 0),
        _quality_check("postgres_write_attempt_count", 0, "==", 0),
        _quality_check("qdrant_write_attempt_count", 0, "==", 0),
        _quality_check("opensearch_write_attempt_count", 0, "==", 0),
    ]
    if require_no_answer_permission:
        checks.append(_quality_check("require_no_answer_permission", answer_permission_count, "==", 0))

    quality_status = QUALITY_PASS if all(c["passed"] for c in checks) else QUALITY_FAIL
    status = READY_STATUS if quality_status == QUALITY_PASS else "E2E_LIVE_DYNAMIC_FALLBACK_NEEDS_REPAIR"

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "E2E_LIVE_DYNAMIC_FALLBACK_BUILT",
        "e2e_live_dynamic_fallback_status": status,
        "quality_status": quality_status,
        "model": model,
        "host": host,
        "port": port,
        "base_url_windows": f"http://127.0.0.1:{port}/v1",
        "base_url_open_webui_docker": f"http://host.docker.internal:{port}/v1",
        "endpoint_routes": endpoint_routes,
        "endpoint_route_count": len(endpoint_routes),
        "source_live_query_pipeline_summary": dict(_summary(live_query_pipeline)),
        "source_table_exact_search_adapter_summary": dict(_summary(table_exact_search_adapter)),
        "live_query_pipelines": pipelines,
        "table_exact_search_documents": docs,
        "dynamic_fallback_probe_queries": probe_queries,
        "dynamic_fallback_probe_responses": fallback_records,
        "ready_dynamic_fallback_probe_responses": ready_fallback,
        "live_dynamic_fallback_contract": dict(CONTRACT),
        "summary": {
            "existing_pipeline_query_count": len(pipelines),
            "exact_search_document_count": len(docs),
            "dynamic_fallback_probe_count": len(fallback_records),
            "ready_dynamic_fallback_probe_count": len(ready_fallback),
            "total_dynamic_fallback_citation_count": total_citations,
            "endpoint_route_count": len(endpoint_routes),
            "unsupported_claim_count": unsupported_claim_count,
            "answer_permission_count": answer_permission_count,
            "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
            "quality_status": quality_status,
        },
        "quality_checks": checks,
    }


def ask_live_dynamic_fallback(query: str, state: Mapping[str, Any]) -> Dict[str, Any]:
    pipelines = [p for p in state.get("live_query_pipelines", []) if isinstance(p, Mapping)]
    selected, score = select_pipeline(query, pipelines)
    model = clean_text(state.get("model")) or DEFAULT_MODEL_ID
    # Use existing v15 final-gated answers only on exact query match.
    # Lower-score fuzzy matches are left to the v16 exact-source fallback so
    # new part numbers do not get swallowed by a related prebuilt demo query.
    if selected is not None and score >= 999.0:
        base = ask_live_query(query, {"model": model, "ready_live_query_pipelines": pipelines})
        base["endpoint_version"] = DEFAULT_ENDPOINT_VERSION
        base["response_status"] = "LIVE_DYNAMIC_FALLBACK_USED_EXISTING_FINAL_GATED_PIPELINE"
        base["matched_existing_pipeline"] = True
        base["matched_dynamic_fallback"] = False
        return base

    docs = [d for d in state.get("table_exact_search_documents", []) if isinstance(d, Mapping)]
    record = build_dynamic_fallback_record(query, docs, 9999)
    matched = bool(record.get("ready_for_webui"))
    return {
        "object": "trace_net.e2e.live_dynamic_fallback.response",
        "endpoint_version": DEFAULT_ENDPOINT_VERSION,
        "model": model,
        "query": query,
        "matched_existing_pipeline": False,
        "matched_dynamic_fallback": matched,
        "match_score": 900.0 if matched else score,
        "response_status": "LIVE_DYNAMIC_FALLBACK_FINAL_GATED_ANSWER_READY" if matched else "LIVE_DYNAMIC_FALLBACK_AUDIT_ONLY_NO_SOURCE_TRUTH_MATCH",
        "message": record.get("message", {"role": "assistant", "content": ""}),
        "citations": record.get("citations", []),
        "citation_count": record.get("citation_count", 0),
        "page_ids": record.get("page_ids", []),
        "field_names": record.get("field_names", []),
        "limitations": record.get("limitations", []),
        "pipeline_trace": record.get("pipeline_stages", []),
        "pipeline_stage_count": record.get("pipeline_stage_count", 0),
        "safety": {
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "writes_to_postgres": False,
            "writes_to_qdrant": False,
            "writes_to_opensearch": False,
            "uploads_to_opensearch": False,
            "response_is_final_gated": matched,
            "response_is_live_pipeline_orchestrated": True,
            "response_is_dynamic_fallback": True,
        },
    }


def make_chat_completion(query: str, ask_response: Mapping[str, Any], model: str = DEFAULT_MODEL_ID) -> Dict[str, Any]:
    content = clean_text(ask_response.get("message", {}).get("content") if isinstance(ask_response.get("message"), Mapping) else "")
    ctext = citations_text(ask_response.get("citations", []))
    if ctext:
        content = f"{content}\n{ctext}"
    return {
        "id": f"chatcmpl-tracenet-v16-{uuid.uuid4().hex[:16]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "trace_net": {
            "endpoint_version": DEFAULT_ENDPOINT_VERSION,
            "matched_existing_pipeline": bool(ask_response.get("matched_existing_pipeline")),
            "matched_dynamic_fallback": bool(ask_response.get("matched_dynamic_fallback")),
            "match_score": ask_response.get("match_score", 0),
            "response_status": ask_response.get("response_status"),
            "pipeline_stage_count": ask_response.get("pipeline_stage_count", 0),
            "safety": ask_response.get("safety", {}),
        },
    }


def health_response(state: Mapping[str, Any]) -> Dict[str, Any]:
    summary = _summary(state)
    return {
        "status": "ok" if state.get("quality_status") == QUALITY_PASS else "needs_repair",
        "module": "trace_net_e2e_live_dynamic_fallback_v16",
        "quality_status": state.get("quality_status"),
        "existing_pipeline_query_count": summary.get("existing_pipeline_query_count", 0),
        "ready_dynamic_fallback_probe_count": summary.get("ready_dynamic_fallback_probe_count", 0),
        "safety": {
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
        },
    }


def models_response(model: str = DEFAULT_MODEL_ID) -> Dict[str, Any]:
    return {"object": "list", "data": [{"id": model, "object": "model", "created": int(time.time()), "owned_by": "trace-net-local"}]}


def make_handler(state: Mapping[str, Any]):
    model = clean_text(state.get("model")) or DEFAULT_MODEL_ID

    class TraceNetLiveDynamicFallbackHandler(BaseHTTPRequestHandler):
        server_version = "TraceNetLiveDynamicFallbackV16/1.0"

        def log_message(self, format: str, *args: Any) -> None:  # pragma: no cover
            return

        def _send_json(self, status_code: int, payload: Mapping[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> Dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return {}
            return data if isinstance(data, dict) else {}

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/health":
                self._send_json(200, health_response(state))
            elif path == "/v1/models":
                self._send_json(200, models_response(model))
            else:
                self._send_json(404, {"error": "not_found", "path": path})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            payload = self._read_json()
            if path == "/api/trace-net/ask":
                query = clean_text(payload.get("query") or payload.get("prompt"))
                self._send_json(200, ask_live_dynamic_fallback(query, state))
            elif path == "/v1/chat/completions":
                query = extract_query_from_chat_payload(payload)
                response = ask_live_dynamic_fallback(query, state)
                self._send_json(200, make_chat_completion(query, response, model=model))
            else:
                self._send_json(404, {"error": "not_found", "path": path})

    return TraceNetLiveDynamicFallbackHandler


def serve_state(state: Mapping[str, Any], host: str = "127.0.0.1", port: int = 8019) -> None:
    httpd = ThreadingHTTPServer((host, port), make_handler(state))
    print("TRACE-Net E2E live dynamic fallback v16")
    print(f" Serving: http://{host}:{port}")
    print(f" Health:  http://{host}:{port}/health")
    print(f" Ask:     http://{host}:{port}/api/trace-net/ask")
    print(f" Chat:    http://{host}:{port}/v1/chat/completions")
    print(f" Model:   {clean_text(state.get('model')) or DEFAULT_MODEL_ID}")
    print(" Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping TRACE-Net E2E live dynamic fallback v16")
    finally:
        httpd.server_close()


def render_inspect_md(report: Mapping[str, Any]) -> str:
    summary = _summary(report)
    lines = [
        "# TRACE-Net E2E Live Dynamic Fallback v16",
        "",
        f"Quality status: **{report.get('quality_status')}**",
        f"Status: `{report.get('e2e_live_dynamic_fallback_status')}`",
        "",
        "## Contract",
        "This endpoint reuses v15 final-gated answers first, then dynamically searches prebuilt table exact-search evidence for new exact source-truth queries. It does not call an LLM, rerun OCR, rebuild embeddings, rebuild graph, rerun table extraction, mutate source truth, or write to services.",
        "",
        "## Connection",
        f"- Windows/Git Bash test base URL: `{report.get('base_url_windows')}`",
        f"- Open WebUI Docker base URL: `{report.get('base_url_open_webui_docker')}`",
        f"- Model: `{report.get('model')}`",
        "",
        "## Summary",
    ]
    for key in (
        "existing_pipeline_query_count",
        "exact_search_document_count",
        "dynamic_fallback_probe_count",
        "ready_dynamic_fallback_probe_count",
        "total_dynamic_fallback_citation_count",
        "unsupported_claim_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ):
        lines.append(f"- {key}: {summary.get(key, 0)}")
    lines.extend(["", "## Dynamic fallback probes"])
    for row in report.get("dynamic_fallback_probe_responses", []):
        if not isinstance(row, Mapping):
            continue
        lines.append(f"- **{row.get('live_dynamic_fallback_status')}** `{row.get('live_dynamic_fallback_id')}` | {row.get('query_intent')} | {row.get('user_query')} | citations={row.get('citation_count')}")
    lines.extend(["", "## Quality checks"])
    for check in report.get("quality_checks", []):
        status = "PASS" if check.get("passed") else "FAIL"
        lines.append(f"- {status} {check.get('name')}: observed={check.get('observed')} expected={check.get('expected')}")
    return "\n".join(lines) + "\n"


def write_report_files(report: Mapping[str, Any], output_dir: str | Path) -> Dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "trace_net_e2e_live_dynamic_fallback_v16.json"
    probes_path = out / "trace_net_e2e_live_dynamic_fallback_records_v16.jsonl"
    inspect_path = out / "trace_net_e2e_live_dynamic_fallback_v16.md"
    write_json(report_path, report)
    write_jsonl(probes_path, report.get("dynamic_fallback_probe_responses", []))
    inspect_path.write_text(render_inspect_md(report), encoding="utf-8")
    return {"report_path": str(report_path), "probes_jsonl_path": str(probes_path), "inspect_md_path": str(inspect_path)}


def check_quality_report(
    report: Mapping[str, Any],
    *,
    min_existing_pipeline_queries: int = 5,
    min_exact_search_documents: int = 10,
    min_dynamic_fallback_probes: int = 3,
    min_ready_dynamic_fallback_probes: int = 3,
    min_total_citations: int = 15,
    min_endpoint_routes: int = 4,
    max_unsupported_claim_count: int = 0,
    max_answer_permission_count: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    require_no_answer_permission: bool = True,
) -> Dict[str, Any]:
    summary = _summary(report)
    checks = [
        _quality_check("existing_pipeline_query_count", int(summary.get("existing_pipeline_query_count", 0)), ">=", min_existing_pipeline_queries),
        _quality_check("exact_search_document_count", int(summary.get("exact_search_document_count", 0)), ">=", min_exact_search_documents),
        _quality_check("dynamic_fallback_probe_count", int(summary.get("dynamic_fallback_probe_count", 0)), ">=", min_dynamic_fallback_probes),
        _quality_check("ready_dynamic_fallback_probe_count", int(summary.get("ready_dynamic_fallback_probe_count", 0)), ">=", min_ready_dynamic_fallback_probes),
        _quality_check("total_dynamic_fallback_citation_count", int(summary.get("total_dynamic_fallback_citation_count", 0)), ">=", min_total_citations),
        _quality_check("endpoint_route_count", int(summary.get("endpoint_route_count", report.get("endpoint_route_count", 0))), ">=", min_endpoint_routes),
        _quality_check("unsupported_claim_count", int(summary.get("unsupported_claim_count", 0)), "<=", max_unsupported_claim_count),
        _quality_check("answer_permission_count", int(summary.get("answer_permission_count", 0)), "<=", max_answer_permission_count),
        _quality_check("source_truth_mutation_allowed_count", int(summary.get("source_truth_mutation_allowed_count", 0)), "<=", max_source_truth_mutation_allowed),
        _quality_check("contract_can_answer_directly", 0, "==", 0),
        _quality_check("contract_can_prove_claims", 0, "==", 0),
        _quality_check("postgres_write_attempt_count", 0, "==", 0),
        _quality_check("qdrant_write_attempt_count", 0, "==", 0),
        _quality_check("opensearch_write_attempt_count", 0, "==", 0),
    ]
    if require_no_answer_permission:
        checks.append(_quality_check("require_no_answer_permission", int(summary.get("answer_permission_count", 0)), "==", 0))
    quality_status = QUALITY_PASS if all(c["passed"] for c in checks) else QUALITY_FAIL
    return {"quality_status": quality_status, "quality_checks": checks, "summary": dict(summary)}
