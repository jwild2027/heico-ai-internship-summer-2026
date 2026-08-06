"""TRACE-Net E2E dynamic query endpoint v1.

Query-time dynamic endpoint over prebuilt TRACE-Net artifacts.

This module intentionally does *not* rerun OCR, page classification,
embeddings, summaries, graph construction, or table extraction. It consumes
prebuilt, audited artifacts and performs live query planning/retrieval over
those artifacts for WebUI/API smoke use.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

DEFAULT_MODEL_ID = "trace-net-e2e-dynamic-query-endpoint-v1"
QUALITY_PASS = "PASS"
STATUS_BUILT = "E2E_DYNAMIC_QUERY_ENDPOINT_MANIFEST_BUILT"
STATUS_READY = "E2E_DYNAMIC_QUERY_ENDPOINT_READY_FOR_OPEN_WEBUI_DYNAMIC_SMOKE"

PART_NUMBER_RE = re.compile(r"\b\d{2,4}-\d{4,6}-\d{3}\b")
MANUAL_REF_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
NUMBER_RE = re.compile(r"\b\d{1,4}\b")
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-]*")

AUTHORITY_ZERO = {
    "answer_permission": False,
    "can_answer_directly": False,
    "can_prove_claims": False,
    "source_truth_mutation_allowed": False,
    "writes_to_postgres": False,
    "writes_to_qdrant": False,
    "writes_to_opensearch": False,
    "uploads_to_opensearch": False,
}

OPTIONAL_TUNNEL_TYPES = [
    "page_summary_tunnel",
    "graph_community_tunnel",
    "graph_navigation_tunnel",
    "table_route_summary_tunnel",
]
CORE_TUNNEL_TYPES = [
    "table_exact_search_tunnel",
    "table_hybrid_bridge_tunnel",
    "route_metadata_tunnel",
    "qdrant_page_profile_tunnel",
]
TUNNEL_AUTHORITY_CONTRACT = {
    "uses_prebuilt_artifacts": True,
    "tunnels_are_routing_and_ranking_only": True,
    "summaries_are_not_source_truth": True,
    "graph_is_not_proof_authority": True,
    "answer_permission": False,
    "can_answer_directly": False,
    "can_prove_claims": False,
    "source_truth_mutation_allowed": False,
    "reruns_ocr": False,
    "reruns_page_classification": False,
    "reruns_embeddings": False,
    "reruns_page_summaries": False,
    "reruns_graph_build": False,
}

GENERIC_QUERY_STOP_TERMS = {
    "find", "part", "number", "where", "used", "search", "table", "text", "manual",
    "reference", "references", "pages", "page", "mention", "mentions", "with", "what", "the",
}

GENERIC_TABLE_TEXT_VALUES = {
    "NUMBER", "PART", "ITEM", "QTY", "QUANTITY", "FIG", "FIGURE", "DESCRIPTION",
    "NOMENCLATURE", "CODE", "PAGE", "MANUAL", "REFERENCE",
}

INTENT_FIELD_PREFERENCES = {
    "covered_part_number": ["covered_part_number", "ipl_part_number", "manual_page_reference"],
    "ipl_part_number": ["ipl_part_number", "covered_part_number", "manual_page_reference"],
    "manual_page_reference": ["manual_page_reference", "ipl_part_number"],
    "ipl_figure_item_or_quantity": ["ipl_figure_item_or_quantity"],
    "table_text": ["ipl_text", "table_text"],
}


def clean_dynamic_value(value: Any) -> str:
    """Normalize small OCR/value spacing issues before scoring/citation display."""
    text = _safe_str(value)
    if not text:
        return ""
    text = clean_response_text(text)
    # Common table OCR seam: MAINTENANCEMANUAL -> MAINTENANCE MANUAL.
    text = text.replace("MAINTENANCEMANUAL", "MAINTENANCE MANUAL")
    # Add spaces only for safe, known all-caps technical phrase joins seen in table text.
    text = text.replace("MAINTENANCEWITH", "MAINTENANCE WITH")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))




def load_tunnel_debug_metadata(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load v3 tunnel report metadata for endpoint debug payloads.

    The tunnel report is optional. Missing graph/summary artifacts remain explicit
    as missing optional tunnels rather than being treated as endpoint failures.
    """
    default = {
        "tunnel_debug_version": "v4",
        "tunnel_report_present": False,
        "tunnel_report_quality_status": "MISSING",
        "tunnel_report_status": "MISSING",
        "tunnels_available": [],
        "missing_optional_tunnels": OPTIONAL_TUNNEL_TYPES,
        "tunnel_authority_contract": dict(TUNNEL_AUTHORITY_CONTRACT),
        "tunnel_report_path": str(path) if path else "",
    }
    if not path or not Path(path).exists():
        return default
    data = _read_json(Path(path))
    summary = data.get("summary") if isinstance(data.get("summary"), Mapping) else {}
    artifact_states = data.get("artifact_states") if isinstance(data.get("artifact_states"), list) else []

    available = []
    missing_optional = []
    for row in artifact_states:
        if not isinstance(row, Mapping):
            continue
        tunnel_type = _safe_str(row.get("tunnel_type"))
        if not tunnel_type or tunnel_type == "dynamic_endpoint_contract":
            continue
        if bool(row.get("present")):
            if tunnel_type not in available:
                available.append(tunnel_type)
        elif tunnel_type in OPTIONAL_TUNNEL_TYPES and tunnel_type not in missing_optional:
            missing_optional.append(tunnel_type)

    # Fallback to report summary when artifact_states are not present.
    if not available:
        for tunnel_type in summary.get("unique_tunnel_types", []) or []:
            tunnel_type = _safe_str(tunnel_type)
            if tunnel_type and tunnel_type not in available:
                available.append(tunnel_type)

    for tunnel_type in OPTIONAL_TUNNEL_TYPES:
        if tunnel_type not in available and tunnel_type not in missing_optional:
            missing_optional.append(tunnel_type)

    contract = data.get("dynamic_query_tunnel_contract") if isinstance(data.get("dynamic_query_tunnel_contract"), Mapping) else {}
    merged_contract = {**TUNNEL_AUTHORITY_CONTRACT, **dict(contract)}
    return {
        "tunnel_debug_version": "v4",
        "tunnel_report_present": True,
        "tunnel_report_quality_status": _safe_str(data.get("quality_status"), "UNKNOWN"),
        "tunnel_report_status": _safe_str(data.get("e2e_dynamic_query_tunnels_status") or data.get("status"), "UNKNOWN"),
        "tunnels_available": available,
        "missing_optional_tunnels": missing_optional,
        "tunnel_authority_contract": merged_contract,
        "tunnel_report_path": str(path),
        "query_tunnel_plan_count": int(summary.get("query_tunnel_plan_count", 0) or 0),
        "ready_query_tunnel_plan_count": int(summary.get("ready_query_tunnel_plan_count", 0) or 0),
        "total_tunnel_count": int(summary.get("total_tunnel_count", 0) or 0),
        "unique_tunnel_type_count": int(summary.get("unique_tunnel_type_count", 0) or 0),
        "plans_with_graph_or_summary_tunnel_count": int(summary.get("plans_with_graph_or_summary_tunnel_count", 0) or 0),
    }


def merge_tunnel_debug_into_response(response: Dict[str, Any], tunnel_debug: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Attach tunnel debug metadata without granting answer/proof authority."""
    if not tunnel_debug:
        return response
    response = dict(response)
    response["tunnel_debug"] = dict(tunnel_debug)
    trace = response.get("trace_net") if isinstance(response.get("trace_net"), Mapping) else {}
    trace = dict(trace)
    trace["tunnels_available"] = list(tunnel_debug.get("tunnels_available", []))
    trace["missing_optional_tunnels"] = list(tunnel_debug.get("missing_optional_tunnels", []))
    trace["tunnel_authority_contract"] = dict(tunnel_debug.get("tunnel_authority_contract", TUNNEL_AUTHORITY_CONTRACT))
    response["trace_net"] = trace
    return _deep_clean(response)

def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def clean_response_text(value: str) -> str:
    return value.replace("ont_p_", "on t_p_").replace(" on  t_p_", " on t_p_")


def _deep_clean(value: Any) -> Any:
    if isinstance(value, str):
        return clean_response_text(value)
    if isinstance(value, list):
        return [_deep_clean(v) for v in value]
    if isinstance(value, dict):
        return {k: _deep_clean(v) for k, v in value.items()}
    return value


def normalize_query(query: str) -> str:
    return " ".join(_safe_str(query).split())


def classify_query_intent(query: str) -> str:
    q = normalize_query(query)
    ql = q.lower()
    if PART_NUMBER_RE.search(q):
        if "ipl" in ql:
            return "ipl_part_number"
        return "covered_part_number"

    # Broad covered-part questions may not include a concrete part-number token.
    # They still need the covered_part_number evidence lane, not the generic
    # table_text lane merely because the query also says "maintenance manual".
    if (
        "covered" in ql
        and "part" in ql
        and ("number" in ql or "numbers" in ql or "part_number" in ql)
    ):
        return "covered_part_number"

    if MANUAL_REF_RE.search(q):
        return "manual_page_reference"
    if "ipl" in ql and NUMBER_RE.search(q):
        return "ipl_figure_item_or_quantity"
    if "table" in ql or q.isupper() or "maintenance manual" in ql:
        return "table_text"
    if any(token in ql for token in ["figure", "diagram", "callout", "image", "visual"]):
        return "visual_or_callout_query"
    return "normal_text_query"


def query_terms(query: str) -> List[str]:
    q = normalize_query(query)
    ql = q.lower()
    terms: List[str] = []

    def add(term: str) -> None:
        term = clean_dynamic_value(term)
        if not term:
            return
        if term.lower() in GENERIC_QUERY_STOP_TERMS:
            return
        if term not in terms:
            terms.append(term)

    # Exact technical identifiers first; these drive strict matching/reranking.
    for rx in (PART_NUMBER_RE, MANUAL_REF_RE):
        for match in rx.findall(q):
            add(match)

    # Numeric item/quantity terms are useful for IPL item queries, but generic small numbers
    # should not outrank exact part/manual identifiers.
    if "ipl" in ql or "item" in ql or "quantity" in ql:
        for match in NUMBER_RE.findall(q):
            add(match)

    # Preserve uppercase phrase blocks often produced by table/IPL OCR.
    upper_words = [w for w in re.findall(r"[A-Z][A-Z0-9\-]+", q) if len(w) >= 2]
    if len(upper_words) >= 2:
        add(" ".join(upper_words))

    for word in WORD_RE.findall(q):
        if len(word) >= 3:
            add(word)
    return terms

def planned_routes_for_intent(intent: str) -> List[str]:
    if intent in {"covered_part_number", "ipl_part_number", "manual_page_reference", "ipl_figure_item_or_quantity", "table_text"}:
        return ["table", "normal_text", "graph_source_trace"]
    if intent == "visual_or_callout_query":
        return ["image_visual", "graph_source_trace", "normal_text"]
    return ["normal_text", "graph_source_trace", "table"]


def planned_channels_for_intent(intent: str) -> List[str]:
    base = ["graph_source_trace_tunnel", "page_summary_tunnel"]
    if intent in {"covered_part_number", "ipl_part_number", "manual_page_reference", "ipl_figure_item_or_quantity", "table_text"}:
        return ["table_exact_search", "table_hybrid_bridge", "table_route_summary_tunnel", *base]
    if intent == "visual_or_callout_query":
        return ["visual_summary_tunnel", *base, "route_metadata"]
    return ["qdrant_page_profile_hint", *base, "table_exact_search"]


def _coerce_record(row: Mapping[str, Any], source: str) -> Dict[str, Any]:
    return {
        "page_id": _safe_str(row.get("page_id")),
        "table_id": _safe_str(row.get("table_id") or row.get("table_key")),
        "field_name": _safe_str(row.get("field_name") or row.get("field") or row.get("normalized_field")),
        "normalized_value": clean_dynamic_value(row.get("normalized_value") or row.get("value") or row.get("field_value")),
        "raw_value": clean_dynamic_value(row.get("raw_value") or row.get("source_value") or row.get("text")),
        "routing_boost": float(row.get("routing_boost") or row.get("boost") or 1.0),
        "retrieval_source": source,
    }


def load_exact_search_documents(path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    data = _read_json(path)
    rows = data.get("exact_search_documents") or data.get("table_exact_search_documents") or []
    docs = [_coerce_record(row, "table_exact_search") for row in rows if isinstance(row, Mapping)]
    docs = [d for d in docs if d["page_id"] and d["field_name"] and d["normalized_value"]]
    return docs, data


def load_bridge_records(path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    data = _read_json(path)
    rows = data.get("bridge_records") or data.get("table_hybrid_bridge_records") or []
    docs = [_coerce_record(row, "table_hybrid_bridge") for row in rows if isinstance(row, Mapping)]
    docs = [d for d in docs if d["page_id"] and d["field_name"] and d["normalized_value"]]
    return docs, data


def _field_alias_score(intent: str, field_name: str, query_l: str) -> int:
    field = field_name.lower()
    score = 0
    if intent == "covered_part_number" and field == "covered_part_number":
        score += 180
    if intent == "ipl_part_number" and field == "ipl_part_number":
        score += 160
    if intent == "manual_page_reference" and field in {"manual_page_reference", "ipl_part_number"}:
        score += 120
    if intent == "ipl_figure_item_or_quantity" and field == "ipl_figure_item_or_quantity":
        score += 180
    if intent == "table_text" and field in {"ipl_text", "table_text"}:
        score += 180
    if field.replace("_", " ") in query_l:
        score += 50
    if "part" in query_l and "part_number" in field:
        score += 70
    if "manual" in query_l and "manual" in field:
        score += 70
    if "item" in query_l and ("item" in field or "quantity" in field):
        score += 70
    return score



def _preferred_field_rank(intent: str, field_name: str) -> int:
    prefs = INTENT_FIELD_PREFERENCES.get(intent, [])
    field = field_name.lower()
    if field in prefs:
        return prefs.index(field)
    return 99


def _is_generic_table_text_hit(intent: str, record: Mapping[str, Any], terms: Sequence[str]) -> bool:
    field = _safe_str(record.get("field_name")).lower()
    value = clean_dynamic_value(record.get("normalized_value"))
    value_u = value.upper()
    if not value:
        return True
    # Suppress column headers/generic OCR labels for identifier queries unless the query
    # explicitly asks for table text and the full value is a meaningful phrase.
    if intent in {"covered_part_number", "ipl_part_number", "manual_page_reference"}:
        if field in {"ipl_text", "table_text"} and value_u in GENERIC_TABLE_TEXT_VALUES:
            return True
        if value_u in GENERIC_TABLE_TEXT_VALUES and not any(t.upper() == value_u for t in terms):
            return True
    return False


def _passes_intent_filter(intent: str, record: Mapping[str, Any], terms: Sequence[str]) -> bool:
    field = _safe_str(record.get("field_name")).lower()
    value = clean_dynamic_value(record.get("normalized_value"))

    if _is_generic_table_text_hit(intent, record, terms):
        return False

    # Part-number query: require a part-number-shaped value or a preferred part field.
    if intent in {"covered_part_number", "ipl_part_number"}:
        if PART_NUMBER_RE.search(value):
            return True
        if field in {"covered_part_number", "ipl_part_number"}:
            return True
        return False

    # Manual reference query: require a manual-ref-shaped value or a manual/part-reference field.
    if intent == "manual_page_reference":
        if MANUAL_REF_RE.search(value):
            return True
        return field in {"manual_page_reference", "ipl_part_number"}

    # IPL item query: generic text headers do not count; numeric item/quantity fields do.
    if intent == "ipl_figure_item_or_quantity":
        return field == "ipl_figure_item_or_quantity" and bool(NUMBER_RE.search(value))

    # Table text queries want meaningful text values, not empty/generic headers.
    if intent == "table_text":
        if field not in {"ipl_text", "table_text"}:
            return False
        return value.upper() not in GENERIC_TABLE_TEXT_VALUES and len(value) >= 3

    return True

def score_record(query: str, intent: str, terms: Sequence[str], record: Mapping[str, Any]) -> float:
    ql = query.lower()
    value = clean_dynamic_value(record.get("normalized_value"))
    raw = clean_dynamic_value(record.get("raw_value"))
    field = _safe_str(record.get("field_name"))
    page = _safe_str(record.get("page_id"))
    hay = " ".join([value, raw, field, page]).lower()
    vl = value.lower()

    if not _passes_intent_filter(intent, record, terms):
        return 0.0

    score = 0.0

    # Intent-field reranker: preferred fields are given deterministic priority.
    rank = _preferred_field_rank(intent, field)
    if rank < 99:
        score += 500 - (rank * 65)
    else:
        score -= 80

    # Exact identifier/phrase match is dominant.
    if value and vl in ql:
        score += 1600
    if value and ql in vl:
        score += 900
    for term in terms:
        tl = term.lower()
        if not tl:
            continue
        if value.lower() == tl:
            score += 1450
        elif tl in value.lower():
            score += 650
        elif tl in hay:
            score += 110

    # Strong bonuses for values matching the query's technical pattern.
    if intent in {"covered_part_number", "ipl_part_number"} and PART_NUMBER_RE.search(value):
        score += 600
    if intent == "manual_page_reference" and MANUAL_REF_RE.search(value):
        score += 550
    if intent == "ipl_figure_item_or_quantity" and NUMBER_RE.search(value):
        score += 450
    if intent == "table_text" and len(value.split()) >= 2:
        score += 350

    score += _field_alias_score(intent, field, ql)
    if record.get("retrieval_source") == "table_exact_search":
        score += 85
    if record.get("retrieval_source") == "table_hybrid_bridge":
        score += 20 * float(record.get("routing_boost") or 1.0)

    # Penalize short generic all-caps values for non-table-text intents.
    if intent != "table_text" and value.upper() in GENERIC_TABLE_TEXT_VALUES:
        score -= 1000
    return max(0.0, score)

def dynamic_retrieve(
    query: str,
    exact_docs: Sequence[Mapping[str, Any]],
    bridge_docs: Sequence[Mapping[str, Any]],
    *,
    top_k: int = 8,
) -> Dict[str, Any]:
    query = normalize_query(query)
    intent = classify_query_intent(query)
    terms = query_terms(query)
    combined: List[Mapping[str, Any]] = [*exact_docs, *bridge_docs]
    scored: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str, str]] = set()
    for row in combined:
        score = score_record(query, intent, terms, row)
        if score <= 0:
            continue
        key = (_safe_str(row.get("page_id")), _safe_str(row.get("field_name")), _safe_str(row.get("normalized_value")))
        if key in seen:
            # Prefer exact over bridge duplicates, but keep highest score.
            continue
        seen.add(key)
        hit = dict(row)
        hit["normalized_value"] = clean_dynamic_value(hit.get("normalized_value"))
        hit["raw_value"] = clean_dynamic_value(hit.get("raw_value"))
        hit["intent_field_rank"] = _preferred_field_rank(intent, _safe_str(hit.get("field_name")))
        hit["retrieval_score"] = round(score, 3)
        hit["citation_ready"] = True
        hit["source_trace_ready"] = True
        hit["answer_permission"] = False
        hit["can_answer_directly"] = False
        hit["can_prove_claims"] = False
        scored.append(hit)

    scored.sort(key=lambda h: (int(h.get("intent_field_rank", 99)), -float(h["retrieval_score"]), h.get("page_id", ""), h.get("field_name", "")))
    hits = scored[: max(1, int(top_k))]
    return {
        "query": query,
        "query_intent": intent,
        "query_terms": terms,
        "requested_routes": planned_routes_for_intent(intent),
        "retrieval_channels": planned_channels_for_intent(intent),
        "retrieval_status": "DYNAMIC_RETRIEVAL_MATCHED" if hits else "DYNAMIC_RETRIEVAL_NO_MATCH",
        "hit_count": len(hits),
        "total_candidate_match_count": len(scored),
        "page_ids": sorted({h["page_id"] for h in hits if h.get("page_id")}),
        "hits": hits,
    }


def _citation_from_hit(index: int, hit: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "citation_id": f"dynamic_citation_{index}",
        "page_id": _safe_str(hit.get("page_id")),
        "field_name": _safe_str(hit.get("field_name")),
        "normalized_value": clean_dynamic_value(hit.get("normalized_value")),
        "retrieval_score": hit.get("retrieval_score", 0),
        "citation_ready": True,
        "source_trace_ready": True,
    }


def build_dynamic_ask_response(query: str, retrieval: Mapping[str, Any], *, top_k_citations: int = 3, tunnel_debug: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    hits = list(retrieval.get("hits") or [])
    citations = [_citation_from_hit(idx + 1, hit) for idx, hit in enumerate(hits[: max(1, int(top_k_citations))])]
    query_text = _safe_str(retrieval.get("query"), normalize_query(query))
    if hits:
        evidence_bits = [
            f"{c['field_name']}={c['normalized_value']} on {c['page_id']}" for c in citations
        ]
        content = (
            f"Dynamic TRACE-Net draft for query: '{query_text}'. "
            f"TRACE-Net searched prebuilt route/evidence artifacts and found citation/source-trace-ready evidence: "
            f"{'; '.join(evidence_bits)}. "
            f"This draft is retrieval/gate constrained and remains non-mutating; it does not rerun OCR, rebuild embeddings, or rewrite source truth."
        )
        status = "citation_backed_dynamic_response_draft"
    else:
        content = (
            f"Dynamic TRACE-Net audit for query: '{query_text}'. "
            f"TRACE-Net searched the prebuilt dynamic evidence artifacts but did not find sufficient citation/source-trace-ready table evidence for this query. "
            f"This remains audit-only and non-mutating."
        )
        status = "audit_only_no_dynamic_match"

    response = {
        "object": "trace_net.e2e.dynamic_query.response",
        "endpoint_version": "v1",
        "model": DEFAULT_MODEL_ID,
        "query": query_text,
        "dynamic_retrieval_used": True,
        "api_response_status": status,
        "query_intent": retrieval.get("query_intent"),
        "requested_routes": retrieval.get("requested_routes", []),
        "retrieval_channels": retrieval.get("retrieval_channels", []),
        "retrieval_status": retrieval.get("retrieval_status"),
        "hit_count": retrieval.get("hit_count", 0),
        "message": {"role": "assistant", "content": content},
        "citations": citations,
        "citation_count": len(citations),
        "page_ids": retrieval.get("page_ids", []),
        "safety": {**AUTHORITY_ZERO, "response_is_dynamic_draft": True},
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "retrieval_permission": "dynamic_ranking_until_runtime_final_gate",
    }
    return merge_tunnel_debug_into_response(_deep_clean(response), tunnel_debug)


def make_openai_chat_completion(query: str, ask_response: Mapping[str, Any], model: str = DEFAULT_MODEL_ID) -> Dict[str, Any]:
    content = _safe_str(ask_response.get("message", {}).get("content"))
    citation_lines = []
    for idx, c in enumerate(ask_response.get("citations") or [], 1):
        citation_lines.append(
            f"[{idx}] page={_safe_str(c.get('page_id'), 'unknown')} "
            f"field={_safe_str(c.get('field_name'), 'unknown')} "
            f"value={_safe_str(c.get('normalized_value'))}"
        )
    if citation_lines:
        content = f"{content.rstrip()}\n\nCitations:\n" + "\n".join(citation_lines)
    output = {
        "id": f"chatcmpl-tracenet-dyn-{uuid.uuid4().hex[:16]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "trace_net": {
            "endpoint_version": "dynamic_v1",
            "dynamic_retrieval_used": True,
            "retrieval_status": ask_response.get("retrieval_status"),
            "query_intent": ask_response.get("query_intent"),
            "hit_count": ask_response.get("hit_count", 0),
            "tunnels_available": list((ask_response.get("tunnel_debug") or {}).get("tunnels_available", [])),
            "missing_optional_tunnels": list((ask_response.get("tunnel_debug") or {}).get("missing_optional_tunnels", [])),
            "tunnel_authority_contract": dict((ask_response.get("tunnel_debug") or {}).get("tunnel_authority_contract", TUNNEL_AUTHORITY_CONTRACT)),
            "safety": ask_response.get("safety", AUTHORITY_ZERO),
        },
    }
    return _deep_clean(output)


def extract_user_query_from_openai_payload(payload: Mapping[str, Any]) -> str:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return ""
    for msg in reversed(messages):
        if not isinstance(msg, Mapping):
            continue
        if msg.get("role") == "user":
            return _safe_str(msg.get("content"))
    return ""


@dataclass
class DynamicEndpointState:
    exact_docs: List[Dict[str, Any]]
    bridge_docs: List[Dict[str, Any]]
    exact_path: Path
    bridge_path: Path
    model_id: str = DEFAULT_MODEL_ID
    top_k: int = 8
    top_k_citations: int = 3
    tunnel_debug: Dict[str, Any] = field(default_factory=dict)

    def ask(self, query: str) -> Dict[str, Any]:
        retrieval = dynamic_retrieve(query, self.exact_docs, self.bridge_docs, top_k=self.top_k)
        return build_dynamic_ask_response(query, retrieval, top_k_citations=self.top_k_citations, tunnel_debug=self.tunnel_debug)

    def health(self) -> Dict[str, Any]:
        return {
            "status": "ok",
            "module": "trace_net_e2e_dynamic_query_endpoint_v1",
            "model": self.model_id,
            "exact_document_count": len(self.exact_docs),
            "bridge_record_count": len(self.bridge_docs),
            "dynamic_query_time_retrieval": True,
            "does_not_rerun_ocr_embeddings_or_summaries": True,
            "tunnel_debug": self.tunnel_debug,
            "safety": AUTHORITY_ZERO,
        }

    def models(self) -> Dict[str, Any]:
        return {"object": "list", "data": [{"id": self.model_id, "object": "model", "created": int(time.time()), "owned_by": "trace-net-local"}]}


def build_endpoint_state(
    table_exact_search_adapter: Path,
    table_hybrid_retrieval_bridge: Path,
    *,
    top_k: int = 8,
    top_k_citations: int = 3,
    model_id: str = DEFAULT_MODEL_ID,
    dynamic_query_tunnels: Optional[Path] = None,
) -> DynamicEndpointState:
    exact_docs, _ = load_exact_search_documents(table_exact_search_adapter)
    bridge_docs, _ = load_bridge_records(table_hybrid_retrieval_bridge)
    tunnel_debug = load_tunnel_debug_metadata(dynamic_query_tunnels)
    return DynamicEndpointState(
        exact_docs=exact_docs,
        bridge_docs=bridge_docs,
        exact_path=table_exact_search_adapter,
        bridge_path=table_hybrid_retrieval_bridge,
        model_id=model_id,
        top_k=top_k,
        top_k_citations=top_k_citations,
        tunnel_debug=tunnel_debug,
    )


def make_handler(state: DynamicEndpointState):
    class DynamicTraceNetHandler(BaseHTTPRequestHandler):
        server_version = "TraceNetDynamicEndpointV1/1.0"

        def _send_json(self, status: int, payload: Mapping[str, Any]) -> None:
            data = json.dumps(_deep_clean(payload), indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _read_json_body(self) -> Dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return {}

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self._send_json(200, state.health())
                return
            if self.path == "/v1/models":
                self._send_json(200, state.models())
                return
            self._send_json(404, {"error": "not_found", "path": self.path})

        def do_POST(self) -> None:  # noqa: N802
            payload = self._read_json_body()
            if self.path == "/api/trace-net/ask":
                query = _safe_str(payload.get("query") or payload.get("input") or payload.get("prompt"))
                if not query:
                    self._send_json(400, {"error": "missing_query"})
                    return
                self._send_json(200, state.ask(query))
                return
            if self.path == "/v1/chat/completions":
                query = extract_user_query_from_openai_payload(payload)
                if not query:
                    self._send_json(400, {"error": "missing_user_message"})
                    return
                ask = state.ask(query)
                self._send_json(200, make_openai_chat_completion(query, ask, model=state.model_id))
                return
            self._send_json(404, {"error": "not_found", "path": self.path})

        def log_message(self, format: str, *args: Any) -> None:
            return

    return DynamicTraceNetHandler


def serve_dynamic_endpoint(state: DynamicEndpointState, host: str, port: int) -> None:
    handler = make_handler(state)
    httpd = ThreadingHTTPServer((host, port), handler)
    print("TRACE-Net E2E dynamic query endpoint v1")
    print(f" Serving: http://{host}:{port}")
    print(f" Health:  http://{host}:{port}/health")
    print(f" Ask:     http://{host}:{port}/api/trace-net/ask")
    print(f" Chat:    http://{host}:{port}/v1/chat/completions")
    print(f" Model:   {state.model_id}")
    print(" Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping TRACE-Net E2E dynamic query endpoint v1")
    finally:
        httpd.server_close()


def summarize_manifest(exact_docs: Sequence[Mapping[str, Any]], bridge_docs: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    fields = sorted({str(d.get("field_name")) for d in [*exact_docs, *bridge_docs] if d.get("field_name")})
    pages = sorted({str(d.get("page_id")) for d in [*exact_docs, *bridge_docs] if d.get("page_id")})
    return {
        "table_exact_search_document_count": len(exact_docs),
        "table_hybrid_bridge_record_count": len(bridge_docs),
        "dynamic_search_document_count": len(exact_docs) + len(bridge_docs),
        "field_count": len(fields),
        "page_with_dynamic_search_document_count": len(pages),
        "fields": fields,
        "safety": AUTHORITY_ZERO,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "opensearch_upload_attempt_count": 0,
    }


def build_manifest(
    table_exact_search_adapter: Path,
    table_hybrid_retrieval_bridge: Path,
    output_dir: Path,
    *,
    min_exact_search_documents: int = 1000,
    min_bridge_records: int = 1000,
    min_field_count: int = 3,
    quality: bool = True,
) -> Dict[str, Any]:
    exact_docs, exact_source = load_exact_search_documents(table_exact_search_adapter)
    bridge_docs, bridge_source = load_bridge_records(table_hybrid_retrieval_bridge)
    summary = summarize_manifest(exact_docs, bridge_docs)
    checks = [
        len(exact_docs) >= min_exact_search_documents,
        len(bridge_docs) >= min_bridge_records,
        summary["field_count"] >= min_field_count,
        exact_source.get("quality_status") == QUALITY_PASS,
        bridge_source.get("quality_status") == QUALITY_PASS,
    ]
    quality_status = QUALITY_PASS if all(checks) else "FAIL"
    manifest = {
        "module": "trace_net_e2e_dynamic_query_endpoint_v1",
        "status": STATUS_BUILT,
        "quality_status": quality_status if quality else "NOT_RUN",
        "e2e_dynamic_query_endpoint_status": STATUS_READY if quality_status == QUALITY_PASS else "E2E_DYNAMIC_QUERY_ENDPOINT_NOT_READY",
        "dynamic_contract": {
            "query_time_dynamic_retrieval": True,
            "reranker_version": "v2_intent_field_exact_match",
            "endpoint_tunnel_debug_version": "v4_optional_tunnel_metadata",
            "uses_prebuilt_ocr": True,
            "uses_prebuilt_page_classification": True,
            "uses_prebuilt_embeddings_or_profiles": "planned/optional tunnel; does not rebuild",
            "uses_prebuilt_table_exact_search": True,
            "uses_prebuilt_table_hybrid_bridge": True,
            "does_not_rerun_ocr": True,
            "does_not_rebuild_embeddings": True,
            "does_not_mutate_source_truth": True,
            "answer_authority": "blocked_until_final_gate",
        },
        "source_paths": {
            "table_exact_search_adapter": str(table_exact_search_adapter),
            "table_hybrid_retrieval_bridge": str(table_hybrid_retrieval_bridge),
        },
        "summary": summary,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_e2e_dynamic_query_endpoint_v1.json"
    md_path = output_dir / "trace_net_e2e_dynamic_query_endpoint_v1.md"
    _write_json(report_path, manifest)
    md_path.write_text(render_manifest_markdown(manifest), encoding="utf-8")
    manifest["report_path"] = str(report_path)
    manifest["inspect_md_path"] = str(md_path)
    _write_json(report_path, manifest)
    return manifest


def render_manifest_markdown(manifest: Mapping[str, Any]) -> str:
    summary = manifest.get("summary", {})
    lines = [
        "# TRACE-Net E2E Dynamic Query Endpoint v1",
        "",
        f"Quality status: **{manifest.get('quality_status')}**",
        f"Dynamic endpoint status: **{manifest.get('e2e_dynamic_query_endpoint_status')}**",
        "",
        "## Reranker v2",
        "",
        "Dynamic reranker v2 boosts exact intent-field matches, suppresses generic table tokens for identifier queries, and normalizes small OCR spacing issues before citation display.",
        "",
        "## What dynamic means here",
        "",
        "This endpoint runs query-time retrieval over prebuilt artifacts. It does not rerun OCR, page classification, embeddings, summaries, graph construction, or source ingest.",
        "",
        "## Counters",
        f"- table_exact_search_document_count: {summary.get('table_exact_search_document_count', 0)}",
        f"- table_hybrid_bridge_record_count: {summary.get('table_hybrid_bridge_record_count', 0)}",
        f"- dynamic_search_document_count: {summary.get('dynamic_search_document_count', 0)}",
        f"- page_with_dynamic_search_document_count: {summary.get('page_with_dynamic_search_document_count', 0)}",
        f"- field_count: {summary.get('field_count', 0)}",
        "",
        "## Safety",
        "- answer_permission_count: 0",
        "- can_answer_directly_count: 0",
        "- can_prove_claims_count: 0",
        "- source_truth_mutation_allowed_count: 0",
        "- service write attempts: 0",
        "",
    ]
    return "\n".join(lines)


def quality_check(manifest: Mapping[str, Any], args: argparse.Namespace) -> Tuple[str, List[str]]:
    s = manifest.get("summary", {})
    checks: List[Tuple[str, bool, str]] = [
        ("quality_status", manifest.get("quality_status") == QUALITY_PASS, f"observed={manifest.get('quality_status')} expected=PASS"),
        ("table_exact_search_document_count", int(s.get("table_exact_search_document_count", 0)) >= args.min_exact_search_documents, f"observed={s.get('table_exact_search_document_count', 0)} expected>={args.min_exact_search_documents}"),
        ("table_hybrid_bridge_record_count", int(s.get("table_hybrid_bridge_record_count", 0)) >= args.min_bridge_records, f"observed={s.get('table_hybrid_bridge_record_count', 0)} expected>={args.min_bridge_records}"),
        ("field_count", int(s.get("field_count", 0)) >= args.min_field_count, f"observed={s.get('field_count', 0)} expected>={args.min_field_count}"),
        ("answer_permission_count", int(s.get("answer_permission_count", 0)) <= args.max_answer_permission_count, f"observed={s.get('answer_permission_count', 0)} expected<={args.max_answer_permission_count}"),
        ("source_truth_mutation_allowed_count", int(s.get("source_truth_mutation_allowed_count", 0)) <= args.max_source_truth_mutation_allowed, f"observed={s.get('source_truth_mutation_allowed_count', 0)} expected<={args.max_source_truth_mutation_allowed}"),
        ("postgres_write_attempt_count", int(s.get("postgres_write_attempt_count", 0)) == 0, f"observed={s.get('postgres_write_attempt_count', 0)} expected=0"),
        ("qdrant_write_attempt_count", int(s.get("qdrant_write_attempt_count", 0)) == 0, f"observed={s.get('qdrant_write_attempt_count', 0)} expected=0"),
        ("opensearch_write_attempt_count", int(s.get("opensearch_write_attempt_count", 0)) == 0, f"observed={s.get('opensearch_write_attempt_count', 0)} expected=0"),
    ]
    lines = []
    status = QUALITY_PASS
    for name, ok, detail in checks:
        if not ok:
            status = "FAIL"
        lines.append(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")
    return status, lines


__all__ = [
    "DEFAULT_MODEL_ID",
    "build_endpoint_state",
    "build_manifest",
    "build_dynamic_ask_response",
    "classify_query_intent",
    "dynamic_retrieve",
    "load_exact_search_documents",
    "load_bridge_records",
    "make_openai_chat_completion",
    "query_terms",
    "serve_dynamic_endpoint",
    "quality_check",
]
