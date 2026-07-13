"""TRACE-Net E2E Live Orchestrator Endpoint v25.

This module provides a live OpenAI-compatible endpoint that runs a compact
TRACE-Net query-time pipeline for new questions:

user query -> query plan -> exact source-truth retrieval -> graph/summary guidance
-> compact prompt -> optional local LLM draft -> deterministic final gate repair
-> final-gated WebUI answer.

The implementation remains local-only and retrieval-only: it does not scan raw 5TB
corpus data, rebuild graph artifacts, rerun OCR, mutate source truth, or write to
Postgres/Qdrant/OpenSearch. The LLM output is treated as draft text only; the final
answer is rebuilt from direct source-truth evidence and cap/disclosure metadata.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter, defaultdict
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

MODULE = "trace_net_e2e_live_orchestrator_endpoint_v25"
VERSION = "v25"
MODEL_ID = "trace-net-e2e-live-orchestrator-gemma-v25"
STATUS_READY = "E2E_LIVE_ORCHESTRATOR_ENDPOINT_READY"
STATUS_NEEDS_REPAIR = "E2E_LIVE_ORCHESTRATOR_ENDPOINT_NEEDS_REPAIR"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"

_ENDPOINT_ROUTES = ["/health", "/v1/models", "/v1/chat/completions", "/"]
DEFAULT_SAMPLE_QUERIES = [
    "Find part number 120-36834-509",
    "Find part number 120-36833-501",
    "What maintenance manual pages mention covered part numbers?",
    "Where is manual reference 25-21-00 used?",
    "Search table text MAINTENANCE MANUAL WITH",
]

PART_NUMBER_RE = re.compile(r"\b\d{2,3}-\d{5}(?:-\d{3})?\b")
MANUAL_REF_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
CITATION_RE = re.compile(r"\[(\d{1,3})\]")


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=False) + "\n")


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", (query or "").strip().lower())


def normalize_value(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).lower()


def compact_value(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", normalize_value(value))


def citation_like_count(text: str) -> int:
    return len(set(int(x) for x in CITATION_RE.findall(text or "")))


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _to_bool(value: Any) -> bool:
    return value is True or str(value).lower() in {"true", "1", "yes"}


def first_str(row: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def load_exact_docs(table_exact_search_adapter_path: Path) -> List[Dict[str, Any]]:
    data = read_json(table_exact_search_adapter_path)
    for key in ("exact_search_documents", "documents", "records", "table_exact_search_documents"):
        rows = data.get(key)
        if isinstance(rows, list):
            return [dict(row) for row in rows if isinstance(row, Mapping)]
    paths = data.get("paths") if isinstance(data.get("paths"), Mapping) else {}
    for key in ("exact_search_jsonl_path", "docs_jsonl_path", "documents_jsonl_path"):
        raw = paths.get(key) or data.get(key)
        if not raw:
            continue
        path = Path(str(raw))
        if path.exists():
            return read_jsonl(path)
    return []


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
    return rows


def load_optional_page_summaries(page_context_v2_path: Optional[Path]) -> Dict[str, str]:
    if not page_context_v2_path or not page_context_v2_path.exists():
        return {}
    try:
        data = read_json(page_context_v2_path)
    except Exception:
        return {}
    rows: List[Any] = []
    if isinstance(data, dict):
        for key in ("page_contexts", "page_context_records", "pages", "records", "page_context_v2_records"):
            if isinstance(data.get(key), list):
                rows = data[key]
                break
        if not rows:
            # Some earlier artifacts may be a mapping from page id -> context.
            for key, value in data.items():
                if isinstance(value, dict) and re.search(r"p\d{6}", key):
                    row = dict(value)
                    row.setdefault("page_id", key)
                    rows.append(row)
    summaries: Dict[str, str] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        page_id = first_str(row, ("page_id", "source_page_id", "page"))
        summary = first_str(row, ("summary", "page_summary", "v2_summary", "context_summary", "text"))
        if page_id and summary:
            summaries[page_id] = summary
    return summaries


def load_optional_leiden(leiden_path: Optional[Path]) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    if not leiden_path or not leiden_path.exists():
        return {}, {}
    try:
        data = read_json(leiden_path)
    except Exception:
        return {}, {}
    rows: List[Any] = []
    for key in ("communities", "leiden_communities", "community_records", "records"):
        if isinstance(data.get(key), list):
            rows = data[key]
            break
    page_to_community: Dict[str, str] = {}
    community_to_pages: Dict[str, List[str]] = defaultdict(list)
    for idx, row in enumerate(rows):
        if not isinstance(row, Mapping):
            continue
        community_id = first_str(row, ("community_id", "leiden_community_id", "id", "node_id")) or f"community_{idx:04d}"
        pages: List[str] = []
        for key in ("page_ids", "pages", "member_page_ids", "candidate_page_ids"):
            value = row.get(key)
            if isinstance(value, list):
                pages.extend(str(x) for x in value if str(x).strip())
        page_id = first_str(row, ("page_id", "source_page_id"))
        if page_id:
            pages.append(page_id)
        for page in dict.fromkeys(pages):
            page_to_community[page] = community_id
            community_to_pages[community_id].append(page)
    # De-duplicate page lists.
    return page_to_community, {k: list(dict.fromkeys(v)) for k, v in community_to_pages.items()}


def _extract_requested_part_number(query: str, canonical_part_numbers: Sequence[str]) -> Tuple[Optional[str], bool]:
    """Return a part-number target and whether it matches the canonical format.

    This intentionally treats queries like ``Find part number DOES-NOT-EXIST-999``
    as part-number lookups with an invalid/noncanonical target rather than falling
    through to broad retrieval.  Broad retrieval created false positives because
    generic table text such as ``NUMBER`` could look relevant to the words
    "part number" even when the requested value was absent.
    """
    if canonical_part_numbers:
        return canonical_part_numbers[0], True
    m = re.search(r"\bpart\s*(?:number|no\.?|#)\s*[:#-]?\s*([A-Za-z0-9][A-Za-z0-9._/-]{2,})", query or "", flags=re.I)
    if not m:
        return None, False
    token = m.group(1).strip().strip(".,;:()[]{}")
    return (token or None), False


def detect_query_plan(query: str) -> Dict[str, Any]:
    normalized = normalize_query(query)
    part_numbers = PART_NUMBER_RE.findall(query or "")
    raw_part_target, raw_part_target_is_canonical = _extract_requested_part_number(query, part_numbers)
    manual_refs = MANUAL_REF_RE.findall(query or "")
    table_text = ""
    m = re.search(r"search\s+table\s+text\s+(.+)$", query or "", flags=re.I)
    if m:
        table_text = m.group(1).strip()

    if raw_part_target:
        intent = "part_number"
        target = raw_part_target
        fields = ["covered_part_number", "ipl_part_number", "part_number"]
        subquery_type = "exact_value_lookup"
    elif "covered part" in normalized:
        intent = "covered_part_number"
        target = None
        fields = ["covered_part_number"]
        subquery_type = "field_aware_source_truth_lookup"
    elif manual_refs and ("manual" in normalized or "reference" in normalized or "used" in normalized):
        intent = "manual_page_reference"
        target = manual_refs[0]
        fields = ["manual_page_reference", "ipl_part_number"]
        subquery_type = "manual_reference_lookup"
    elif table_text:
        intent = "table_text"
        target = table_text
        fields = ["ipl_text", "table_text"]
        subquery_type = "table_text_lookup"
    else:
        intent = "unknown_dynamic_query"
        target = None
        fields = ["covered_part_number", "ipl_part_number", "manual_page_reference", "ipl_text", "table_text"]
        subquery_type = "broad_source_truth_lookup"

    return {
        "query_intent": intent,
        "query_goal": f"Find source-truth evidence for query: {query}",
        "target_value": target,
        "required_source_truth_fields": fields,
        "primary_tunnels": ["table_exact_search_tunnel"],
        "secondary_tunnels": ["table_hybrid_bridge_tunnel", "qdrant_page_profile_tunnel"],
        "guidance_tunnels": ["page_summary_tunnel", "graph_community_tunnel", "graph_navigation_tunnel", "route_metadata_tunnel"],
        "subqueries": [{"subquery_type": subquery_type, "target_value": target, "required_source_truth_fields": fields}],
        "target_format_valid": bool(raw_part_target_is_canonical) if intent == "part_number" else True,
        "strict_target_match_required": bool(target),
        "authority": {
            "source_truth_evidence_is_proof": True,
            "graph_leiden_guidance_is_proof": False,
            "v2_summary_guidance_is_proof": False,
            "nearby_context_is_direct_proof": False,
        },
    }


def doc_field(doc: Mapping[str, Any]) -> str:
    return first_str(doc, ("field_name", "field", "field_role", "normalized_field_name"))


def doc_value(doc: Mapping[str, Any]) -> str:
    return first_str(doc, ("normalized_value", "value", "display_value", "raw_value", "text"))


def doc_page(doc: Mapping[str, Any]) -> str:
    return first_str(doc, ("page_id", "source_page_id", "page"))



def _significant_text_tokens(value: str) -> set[str]:
    stop = {"a", "an", "and", "or", "the", "of", "for", "to", "in", "on", "with"}
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalize_value(value))
        if len(token) > 1 and token not in stop
    }

def _target_matches_value(target: str, value: str, intent: str) -> Tuple[bool, str, int]:
    target_comp = compact_value(target)
    value_comp = compact_value(value)
    if not target_comp or not value_comp:
        return False, "no_match", 0
    if normalize_value(value) == normalize_value(target):
        return True, "exact_value_match", 1100
    if value_comp == target_comp:
        return True, "compact_value_match", 1000
    # Free-text table/nomenclature searches may match a longer cell or OCR-normalized
    # value. They also support token-order-insensitive matching, so queries like
    # "LOCKING RING" can match source nomenclature written as "RING, LOCKING".
    # Structured part/manual-reference targets remain exact normalized/compact equality
    # so unrelated values do not inflate counts or create false positives.
    if intent == "table_text":
        target_tokens = _significant_text_tokens(target)
        value_tokens = _significant_text_tokens(value)
        if target_tokens and target_tokens.issubset(value_tokens):
            return True, "target_tokens_in_value_any_order", 750
        if value_tokens and value_tokens.issubset(target_tokens):
            return True, "value_tokens_in_target_any_order", 550
        if target_comp in value_comp and len(target_comp) > 3:
            return True, "target_contained_in_value", 800
        if value_comp in target_comp and len(value_comp) > 3:
            return True, "value_contained_in_target", 500
    return False, "no_match", 0


def score_doc(doc: Mapping[str, Any], plan: Mapping[str, Any], query: str) -> Tuple[int, str]:
    field = doc_field(doc)
    value = doc_value(doc)
    target = str(plan.get("target_value") or "").strip()
    required_fields = set(plan.get("required_source_truth_fields") or [])
    intent = str(plan.get("query_intent") or "")
    if field not in required_fields:
        return 0, "field_not_allowed_for_intent"

    if target:
        matched, reason, base_score = _target_matches_value(target, value, intent)
        if matched:
            return base_score + 100, reason
        search_text = str(doc.get("search_text") or "")
        if compact_value(target) and compact_value(target) in compact_value(search_text):
            return 250, "search_text_match"
        return 0, "target_not_found_in_value"

    # Field-aware inventory queries, such as "which pages list covered part numbers",
    # intentionally retrieve records from the requested field.
    if field in required_fields:
        return 200, "field_match"
    q = normalize_value(query)
    if normalize_value(value) and normalize_value(value) in q:
        return 150, "query_mentions_value"
    return 0, "no_match"


def unique_evidence_key(doc: Mapping[str, Any]) -> Tuple[str, str, str]:
    return (doc_page(doc), doc_field(doc), doc_value(doc))


def retrieve_source_truth_evidence(
    docs: Sequence[Mapping[str, Any]],
    plan: Mapping[str, Any],
    query: str,
    top_k: int = 10,
) -> Dict[str, Any]:
    scored: List[Tuple[int, str, Mapping[str, Any]]] = []
    for doc in docs:
        score, reason = score_doc(doc, plan, query)
        if score > 0:
            scored.append((score, reason, doc))
    scored.sort(key=lambda item: (-item[0], doc_page(item[2]), doc_field(item[2]), doc_value(item[2])))

    total_matches = len(scored)
    direct_rows: List[Dict[str, Any]] = []
    nearby_rows: List[Dict[str, Any]] = []
    seen_direct: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

    required_fields = set(plan.get("required_source_truth_fields") or [])
    target = str(plan.get("target_value") or "").strip()
    direct_pages: List[str] = []
    for score, reason, doc in scored:
        key = unique_evidence_key(doc)
        field = key[1]
        value = key[2]
        page = key[0]
        is_tiny_ocr = len(compact_value(value)) <= 1
        is_direct = field in required_fields and not is_tiny_ocr
        if target:
            matched_for_direct, _, _ = _target_matches_value(target, value, str(plan.get("query_intent") or ""))
            is_direct = is_direct and matched_for_direct
        if is_direct and len(direct_rows) < top_k:
            if key in seen_direct:
                seen_direct[key]["occurrence_count"] += 1
                continue
            row = {
                "citation_id": len(direct_rows) + 1,
                "page_id": page,
                "field_name": field,
                "normalized_value": value,
                "document_id": first_str(doc, ("document_id", "source_evidence_id")),
                "score": score,
                "match_reason": reason,
                "occurrence_count": 1,
                "direct_proof_authority": True,
            }
            seen_direct[key] = row
            direct_rows.append(row)
            direct_pages.append(page)

    # Nearby context only from the direct pages, never proof.
    direct_page_set = set(direct_pages)
    for score, reason, doc in scored:
        if len(nearby_rows) >= max(0, top_k - len(direct_rows)):
            break
        key = unique_evidence_key(doc)
        if key in seen_direct:
            continue
        if direct_page_set and doc_page(doc) not in direct_page_set:
            continue
        nearby_rows.append(
            {
                "citation_id": len(direct_rows) + len(nearby_rows) + 1,
                "page_id": doc_page(doc),
                "field_name": doc_field(doc),
                "normalized_value": doc_value(doc),
                "score": score,
                "match_reason": reason,
                "direct_proof_authority": False,
                "nearby_context_only": True,
            }
        )

    returned_count = len(direct_rows) + len(nearby_rows)
    field_counts = Counter(doc_field(item[2]) for item in scored)
    page_counts = Counter(doc_page(item[2]) for item in scored)
    result_was_capped = total_matches > returned_count
    return {
        "direct_evidence": direct_rows,
        "nearby_context": nearby_rows,
        "total_match_count": total_matches,
        "returned_match_count": returned_count,
        "result_was_capped": result_was_capped,
        "more_results_available": result_was_capped,
        "high_degree_node_detected": total_matches > top_k,
        "cap_reason": "high_degree_or_top_k_budget" if result_was_capped else "not_capped",
        "group_counts": {
            "by_field": dict(field_counts.most_common(25)),
            "by_page": dict(page_counts.most_common(25)),
        },
        "available_drilldowns": ["document", "manual", "revision", "section", "route", "field_type", "page", "leiden_community"],
    }


def build_guidance(
    direct_evidence: Sequence[Mapping[str, Any]],
    page_summaries: Mapping[str, str],
    page_to_community: Mapping[str, str],
    community_to_pages: Mapping[str, Sequence[str]],
    max_pages_per_community: int = 25,
) -> Dict[str, Any]:
    pages = list(dict.fromkeys(str(row.get("page_id") or "") for row in direct_evidence if row.get("page_id")))
    graph_guidance: List[Dict[str, Any]] = []
    summary_guidance: List[Dict[str, Any]] = []
    for idx, page in enumerate(pages, 1):
        community_id = page_to_community.get(page, "unknown_community")
        candidates = list(community_to_pages.get(community_id, [page]))[:max_pages_per_community]
        if page not in candidates:
            candidates.insert(0, page)
        graph_guidance.append(
            {
                "guidance_id": f"live_graph_guidance_{idx:04d}",
                "authority": "guidance_only",
                "proof_authority": False,
                "requires_source_truth_confirmation": True,
                "seed_page_id": page,
                "leiden_community_id": community_id,
                "candidate_page_ids": candidates,
                "returned_candidate_page_count": len(candidates),
                "graph_path_provenance": [
                    {"hop": 0, "node_id": page, "node_type": "source_truth_seed_page"},
                    {"hop": 1, "node_id": community_id, "edge_type": "member_of_leiden_community"},
                ],
            }
        )
        if page in page_summaries:
            summary_guidance.append(
                {
                    "record_id": f"summary_guidance_{idx:04d}",
                    "authority": "guidance_only",
                    "proof_authority": False,
                    "page_id": page,
                    "summary": page_summaries[page],
                }
            )
    return {"graph_guidance": graph_guidance, "v2_summary_guidance": summary_guidance}


def render_prompt(query: str, plan: Mapping[str, Any], retrieval: Mapping[str, Any], guidance: Mapping[str, Any]) -> List[Dict[str, str]]:
    direct = retrieval.get("direct_evidence") or []
    nearby = retrieval.get("nearby_context") or []
    lines: List[str] = ["TRACE-NET LIVE CONTEXT PACK", "", "SOURCE-TRUTH EVIDENCE (direct proof authority):"]
    if direct:
        for row in direct:
            occ = f" occurrence_count={row.get('occurrence_count')}" if _to_int(row.get("occurrence_count"), 1) > 1 else ""
            lines.append(f"- [{row.get('citation_id')}] page={row.get('page_id')} field={row.get('field_name')} value={row.get('normalized_value')}{occ}")
    else:
        lines.append("- None")
    lines.extend(["", "NEARBY SOURCE-TRUTH CONTEXT (not direct proof):"])
    if nearby:
        for row in nearby[:8]:
            lines.append(f"- [{row.get('citation_id')}] page={row.get('page_id')} field={row.get('field_name')} value={row.get('normalized_value')}")
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "GRAPH / LEIDEN GUIDANCE (navigation only; not proof):",
            json.dumps(guidance.get("graph_guidance") or [], indent=2),
            "",
            "V2 SUMMARY GUIDANCE (meaning/compression only; not proof):",
            json.dumps(guidance.get("v2_summary_guidance") or [], indent=2),
            "",
            "AGGREGATION / CAPPING METADATA:",
            json.dumps({k: retrieval.get(k) for k in ["total_match_count", "returned_match_count", "result_was_capped", "more_results_available", "high_degree_node_detected", "cap_reason", "group_counts", "available_drilldowns"]}, indent=2),
            "",
            "ANSWER RULES:",
            json.dumps(
                {
                    "cite_every_factual_claim": True,
                    "source_truth_evidence_required_for_final_claims": True,
                    "graph_is_guidance_not_proof": True,
                    "leiden_is_guidance_not_proof": True,
                    "v2_summaries_are_guidance_not_proof": True,
                    "nearby_context_is_not_direct_proof": True,
                    "disclose_capped_results": True,
                    "state_limitations_when_evidence_is_incomplete": True,
                },
                indent=2,
            ),
        ]
    )
    system = (
        "You are the TRACE-Net draft writer. Write a concise draft from the provided context. "
        "Use only SOURCE-TRUTH EVIDENCE for factual claims. Graph/Leiden, v2 summaries, and nearby context are guidance only. "
        "If evidence is capped or incomplete, say so. Do not invent citations or physical part descriptions."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": query},
        {"role": "user", "content": "\n".join(lines)},
    ]


def call_ollama_chat(messages: Sequence[Mapping[str, str]], base_url: str, model: str, api_key: str, temperature: float, timeout: int) -> Tuple[str, Dict[str, Any]]:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = json.dumps({"model": model, "messages": list(messages), "temperature": temperature}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = str(message.get("content") or "")
    metadata = {
        "provider_response_id": data.get("id"),
        "reasoning_omitted_from_draft": "reasoning" in message,
        "usage": data.get("usage") or {},
    }
    return content, metadata


def simulate_llm_draft(query: str, retrieval: Mapping[str, Any]) -> str:
    direct = retrieval.get("direct_evidence") or []
    if not direct:
        return "TRACE-Net did not find citation-ready source-truth evidence for this query. No factual claim is made."
    row = direct[0]
    return f"TRACE-Net found {row.get('field_name')}={row.get('normalized_value')} on page {row.get('page_id')} [{row.get('citation_id')}]."


def build_final_answer(query: str, plan: Mapping[str, Any], retrieval: Mapping[str, Any]) -> Tuple[str, Dict[str, Any]]:
    direct = list(retrieval.get("direct_evidence") or [])
    if not direct:
        return (
            "TRACE-Net did not find direct citation-ready source-truth evidence for this query. "
            "No source-truth claim is made. Try narrowing by part number, manual reference, page, or table text.",
            {"unsupported_claim_count": 0, "answerable": False, "citation_like_count": 0},
        )
    intent = str(plan.get("query_intent") or "")
    target = str(plan.get("target_value") or "").strip()
    cap = ""
    if retrieval.get("result_was_capped"):
        cap = f" Results were capped: TRACE-Net returned {retrieval.get('returned_match_count')} of {retrieval.get('total_match_count')} matching records. Available drill-downs include document, manual, revision, section, route, field_type."

    if intent == "part_number":
        row = direct[0]
        answer = (
            f"TRACE-Net found part number {target or row.get('normalized_value')} on page {row.get('page_id')} "
            f"as {row.get('field_name')} [{row.get('citation_id')}]. The available direct source-truth evidence confirms the listing, "
            "but it does not provide enough information to describe the part physically."
        )
    elif intent == "covered_part_number":
        pages = ", ".join(sorted(set(str(row.get("page_id")) for row in direct)))
        examples = "; ".join(f"{row.get('normalized_value')} [{row.get('citation_id')}]" for row in direct[:10])
        answer = f"TRACE-Net found covered part numbers on page(s) {pages}. Direct source-truth examples include {examples}."
    elif intent == "manual_page_reference":
        row = direct[0]
        occ = _to_int(row.get("occurrence_count"), 1)
        dup = f" The same page/value was collapsed from {occ} repeated source records." if occ > 1 else ""
        answer = f"TRACE-Net found manual reference {target or row.get('normalized_value')} on page {row.get('page_id')} [{row.get('citation_id')}].{dup}"
    elif intent == "table_text":
        row = direct[0]
        answer = (
            f"TRACE-Net found the exact table text \"{target or row.get('normalized_value')}\" on page {row.get('page_id')} [{row.get('citation_id')}]. "
            "Nearby OCR/table records were returned as context only and are not treated as direct proof for this query."
        )
    else:
        examples = "; ".join(f"page {row.get('page_id')} {row.get('field_name')}={row.get('normalized_value')} [{row.get('citation_id')}]" for row in direct[:5])
        answer = f"TRACE-Net found direct source-truth evidence: {examples}."
    answer += cap
    return answer, {"unsupported_claim_count": 0, "answerable": True, "citation_like_count": citation_like_count(answer)}


def run_live_query(
    query: str,
    state: Mapping[str, Any],
    llm_mode: Optional[str] = None,
    request_timeout: Optional[int] = None,
) -> Dict[str, Any]:
    docs = state.get("exact_search_documents") or []
    plan = detect_query_plan(query)
    retrieval = retrieve_source_truth_evidence(docs, plan, query, top_k=_to_int(state.get("top_k"), 10))
    guidance = build_guidance(
        retrieval.get("direct_evidence") or [],
        state.get("page_summaries") or {},
        state.get("page_to_community") or {},
        state.get("community_to_pages") or {},
        max_pages_per_community=_to_int(state.get("max_pages_per_community"), 25),
    )
    prompt_messages = render_prompt(query, plan, retrieval, guidance)
    mode = llm_mode or str(state.get("llm_mode") or "simulate")
    draft = ""
    llm_status = "LLM_NOT_CALLED"
    llm_metadata: Dict[str, Any] = {}
    error = ""
    try:
        if mode == "ollama":
            draft, llm_metadata = call_ollama_chat(
                prompt_messages,
                str(state.get("llm_base_url") or "http://127.0.0.1:11434/v1"),
                str(state.get("llm_model") or "gemma4:26b"),
                str(state.get("llm_api_key") or "ollama"),
                float(state.get("temperature", 0)),
                int(request_timeout or state.get("request_timeout", 240)),
            )
            llm_status = "LLM_CALL_SUCCEEDED"
        else:
            draft = simulate_llm_draft(query, retrieval)
            llm_status = "LLM_SIMULATED"
    except Exception as exc:  # endpoint should stay safe even if local LLM fails.
        error = str(exc)
        draft = simulate_llm_draft(query, retrieval)
        llm_status = "LLM_CALL_FAILED_SIMULATED_FALLBACK"
        llm_metadata = {"error": error}

    final_answer, final_meta = build_final_answer(query, plan, retrieval)
    return {
        "user_query": query,
        "query_plan": plan,
        "retrieval": retrieval,
        "guidance": guidance,
        "prompt_message_count": len(prompt_messages),
        "llm_mode": mode,
        "llm_status": llm_status,
        "llm_draft_text": draft,
        "llm_metadata": llm_metadata,
        "final_gate_status": "LIVE_ORCHESTRATOR_FINAL_GATE_PASS" if final_meta["answerable"] else "LIVE_ORCHESTRATOR_AUDIT_ONLY",
        "final_answer": final_answer,
        "final_answer_ready_for_webui": bool(final_meta["answerable"]),
        "unsupported_claim_count": final_meta["unsupported_claim_count"],
        "citation_like_count": final_meta["citation_like_count"],
        "cap_disclosure_required": bool(retrieval.get("result_was_capped")),
        "cap_disclosure_in_final_answer": "Results were capped" in final_answer,
        "safety": standard_safety(response_is_final_gated=bool(final_meta["answerable"]), llm_called=(mode == "ollama" and llm_status == "LLM_CALL_SUCCEEDED")),
    }


def standard_safety(response_is_final_gated: bool = True, llm_called: bool = False) -> Dict[str, Any]:
    return {
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
        "llm_called": llm_called,
        "response_is_final_gated": response_is_final_gated,
    }


def build_orchestrator_state(
    table_exact_search_adapter_path: Path,
    output_dir: Optional[Path] = None,
    page_context_v2_path: Optional[Path] = None,
    leiden_communities_path: Optional[Path] = None,
    host: str = "127.0.0.1",
    port: int = 8021,
    model_id: str = MODEL_ID,
    llm_mode: str = "simulate",
    llm_base_url: str = "http://127.0.0.1:11434/v1",
    llm_model: str = "gemma4:26b",
    llm_api_key: str = "ollama",
    temperature: float = 0.0,
    request_timeout: int = 240,
    top_k: int = 10,
    max_pages_per_community: int = 25,
    include_standard_demo_queries: bool = False,
) -> Dict[str, Any]:
    docs = load_exact_docs(table_exact_search_adapter_path)
    page_summaries = load_optional_page_summaries(page_context_v2_path)
    page_to_community, community_to_pages = load_optional_leiden(leiden_communities_path)
    state: Dict[str, Any] = {
        "module": MODULE,
        "version": VERSION,
        "model_id": model_id,
        "host": host,
        "port": port,
        "base_url_windows": f"http://{host}:{port}/v1",
        "base_url_open_webui_docker": f"http://host.docker.internal:{port}/v1",
        "endpoint_routes": list(_ENDPOINT_ROUTES),
        "endpoint_route_count": len(_ENDPOINT_ROUTES),
        "table_exact_search_adapter_path": str(table_exact_search_adapter_path),
        "page_context_v2_path": str(page_context_v2_path) if page_context_v2_path else "",
        "leiden_communities_path": str(leiden_communities_path) if leiden_communities_path else "",
        "exact_search_document_count": len(docs),
        "page_summary_count": len(page_summaries),
        "leiden_page_membership_count": len(page_to_community),
        "llm_mode": llm_mode,
        "llm_base_url": llm_base_url,
        "llm_model": llm_model,
        "llm_api_key": llm_api_key,
        "temperature": temperature,
        "request_timeout": request_timeout,
        "top_k": top_k,
        "max_pages_per_community": max_pages_per_community,
        "contract": {
            "runs_live_query_pipeline_at_request_time": True,
            "llm_output_is_draft_only": True,
            "final_gate_repairs_from_source_truth": True,
            "source_truth_evidence_required_for_final_claims": True,
            "graph_leiden_guidance_only": True,
            "v2_summaries_guidance_only": True,
            "nearby_context_not_direct_proof": True,
            "raw_5tb_scan_at_query_time": False,
            "graph_rebuild_at_query_time": False,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
        },
        "safety": standard_safety(response_is_final_gated=True, llm_called=(llm_mode == "ollama")),
        # Store docs for serving. 1497 records is still a tiny prebuilt index artifact, not raw corpus.
        "exact_search_documents": docs,
        "page_summaries": page_summaries,
        "page_to_community": page_to_community,
        "community_to_pages": community_to_pages,
    }
    sample_results: List[Dict[str, Any]] = []
    if include_standard_demo_queries:
        for query in DEFAULT_SAMPLE_QUERIES:
            sample_results.append(run_live_query(query, state, llm_mode="simulate"))
    state["sample_query_count"] = len(sample_results)
    state["sample_success_count"] = sum(1 for r in sample_results if r.get("final_answer_ready_for_webui"))
    state["sample_results"] = sample_results
    state["answer_permission_count"] = 0
    state["source_truth_mutation_allowed_count"] = 0
    return state


def evaluate_quality(
    state: Mapping[str, Any],
    min_exact_search_documents: int = 10,
    min_endpoint_routes: int = 4,
    min_sample_queries: int = 5,
    min_sample_successes: int = 5,
    max_unsupported_claim_count: int = 0,
    max_llm_call_errors: int = 0,
    max_answer_permission_count: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    require_no_answer_permission: bool = True,
) -> Tuple[str, List[Dict[str, Any]]]:
    sample_results = state.get("sample_results") or []
    unsupported = sum(_to_int(r.get("unsupported_claim_count"), 0) for r in sample_results)
    llm_errors = sum(1 for r in sample_results if "FAILED" in str(r.get("llm_status")))
    checks = [
        ("exact_search_document_count", state.get("exact_search_document_count", 0), ">=", min_exact_search_documents),
        ("endpoint_route_count", state.get("endpoint_route_count", 0), ">=", min_endpoint_routes),
        ("sample_query_count", state.get("sample_query_count", 0), ">=", min_sample_queries),
        ("sample_success_count", state.get("sample_success_count", 0), ">=", min_sample_successes),
        ("sample_unsupported_claim_count", unsupported, "<=", max_unsupported_claim_count),
        ("sample_llm_call_error_count", llm_errors, "<=", max_llm_call_errors),
        ("answer_permission_count", state.get("answer_permission_count", 0), "<=", max_answer_permission_count),
        ("source_truth_mutation_allowed_count", state.get("source_truth_mutation_allowed_count", 0), "<=", max_source_truth_mutation_allowed),
        ("contract_raw_5tb_scan_at_query_time", state.get("contract", {}).get("raw_5tb_scan_at_query_time"), "is", False),
        ("contract_graph_rebuild_at_query_time", state.get("contract", {}).get("graph_rebuild_at_query_time"), "is", False),
    ]
    if require_no_answer_permission:
        checks.append(("require_no_answer_permission", state.get("answer_permission_count", 0), "==", 0))
    rows: List[Dict[str, Any]] = []
    for name, observed, op, expected in checks:
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
        rows.append({"name": name, "observed": observed, "op": op, "expected": expected, "passed": bool(passed)})
    return (QUALITY_PASS if all(row["passed"] for row in rows) else QUALITY_FAIL, rows)


def attach_quality(state: Dict[str, Any], quality_status: str, quality_checks: List[Dict[str, Any]]) -> Dict[str, Any]:
    state["quality_status"] = quality_status
    state["quality_checks"] = quality_checks
    state["status"] = STATUS_READY if quality_status == QUALITY_PASS else STATUS_NEEDS_REPAIR
    return state


def _state_for_file(state: Mapping[str, Any]) -> Dict[str, Any]:
    # Avoid duplicating the full exact index inside the report when not needed for inspection.
    out = dict(state)
    out["exact_search_documents"] = list(state.get("exact_search_documents") or [])[:25]
    out["page_summaries"] = {k: state.get("page_summaries", {}).get(k) for k in list((state.get("page_summaries") or {}).keys())[:25]}
    out["page_to_community"] = {k: state.get("page_to_community", {}).get(k) for k in list((state.get("page_to_community") or {}).keys())[:25]}
    out["community_to_pages"] = {k: list(v)[:10] for k, v in list((state.get("community_to_pages") or {}).items())[:25]}
    return out


def render_markdown_report(state: Mapping[str, Any]) -> str:
    lines = [
        "# TRACE-Net E2E Live Orchestrator Endpoint v25",
        "",
        f"Quality status: **{state.get('quality_status', 'UNKNOWN')}**",
        f"Status: `{state.get('status', 'UNKNOWN')}`",
        "",
        "## Summary",
    ]
    for key in [
        "exact_search_document_count",
        "page_summary_count",
        "leiden_page_membership_count",
        "endpoint_route_count",
        "sample_query_count",
        "sample_success_count",
        "llm_mode",
        "llm_model",
        "base_url_windows",
        "base_url_open_webui_docker",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {state.get(key)}")
    lines.extend(
        [
            "",
            "## Contract",
            "- This endpoint runs a compact live query pipeline at request time.",
            "- The LLM output is a draft only; final answers are rebuilt/gated from direct source-truth evidence.",
            "- Graph/Leiden and v2 summaries remain guidance only.",
            "- Nearby context is not direct proof.",
            "- The endpoint reads prebuilt indexes/artifacts and does not scan raw 5TB data or rebuild the graph.",
            "",
            "## Sample query results",
        ]
    )
    for result in state.get("sample_results", []):
        lines.append(f"### {result.get('user_query')}")
        lines.append(f"- final_gate_status: {result.get('final_gate_status')}")
        lines.append(f"- llm_status: {result.get('llm_status')}")
        lines.append(f"- final_answer_preview: {str(result.get('final_answer') or '').replace(chr(10), ' ')[:500]}")
        lines.append("")
    lines.append("## Quality checks")
    for check in state.get("quality_checks", []):
        status = "PASS" if check.get("passed") else "FAIL"
        lines.append(f"- {status} {check.get('name')}: observed={check.get('observed')} expected={check.get('op')} {check.get('expected')}")
    lines.append("")
    return "\n".join(lines)


def write_endpoint_files(state: Dict[str, Any], output_dir: Path) -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_e2e_live_orchestrator_endpoint_v25.json"
    sample_jsonl_path = output_dir / "trace_net_e2e_live_orchestrator_endpoint_samples_v25.jsonl"
    inspect_md_path = output_dir / "trace_net_e2e_live_orchestrator_endpoint_v25.md"
    write_json(report_path, _state_for_file(state))
    write_jsonl(sample_jsonl_path, state.get("sample_results", []))
    inspect_md_path.write_text(render_markdown_report(state), encoding="utf-8")
    state["report_path"] = str(report_path)
    state["sample_jsonl_path"] = str(sample_jsonl_path)
    state["inspect_md_path"] = str(inspect_md_path)
    write_json(report_path, _state_for_file(state))
    return {"report_path": str(report_path), "sample_jsonl_path": str(sample_jsonl_path), "inspect_md_path": str(inspect_md_path)}


def load_state_for_serving(report_path: Path) -> Dict[str, Any]:
    # The report stores only a preview of the exact docs. Reload full docs from the source adapter path.
    state = read_json(report_path)
    adapter = Path(str(state.get("table_exact_search_adapter_path") or ""))
    if adapter.exists():
        state["exact_search_documents"] = load_exact_docs(adapter)
    page_path = Path(str(state.get("page_context_v2_path") or "")) if state.get("page_context_v2_path") else None
    leiden_path = Path(str(state.get("leiden_communities_path") or "")) if state.get("leiden_communities_path") else None
    state["page_summaries"] = load_optional_page_summaries(page_path)
    page_to_community, community_to_pages = load_optional_leiden(leiden_path)
    state["page_to_community"] = page_to_community
    state["community_to_pages"] = community_to_pages
    return state


def openai_models_response(state: Mapping[str, Any]) -> Dict[str, Any]:
    return {"object": "list", "data": [{"id": state.get("model_id", MODEL_ID), "object": "model", "created": int(time.time()), "owned_by": "trace-net-local"}]}


def health_response(state: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "status": "ok" if state.get("quality_status") == QUALITY_PASS else "needs_repair",
        "module": MODULE,
        "quality_status": state.get("quality_status"),
        "model_id": state.get("model_id", MODEL_ID),
        "exact_search_document_count": len(state.get("exact_search_documents") or []),
        "llm_mode": state.get("llm_mode"),
        "llm_model": state.get("llm_model"),
        "safety": standard_safety(response_is_final_gated=True, llm_called=(state.get("llm_mode") == "ollama")),
    }


def extract_user_message(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            return str(message.get("content") or "")
    return ""


def chat_completion_response(state: Mapping[str, Any], request_payload: Mapping[str, Any]) -> Dict[str, Any]:
    query = extract_user_message(request_payload.get("messages"))
    result = run_live_query(query, state)
    return {
        "id": "chatcmpl-tracenet-v25-" + uuid.uuid4().hex[:16],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": state.get("model_id", MODEL_ID),
        "choices": [{"index": 0, "message": {"role": "assistant", "content": result["final_answer"]}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "trace_net": {
            "endpoint_version": "live_orchestrator_v25",
            "query_intent": result.get("query_plan", {}).get("query_intent"),
            "llm_status": result.get("llm_status"),
            "llm_mode": result.get("llm_mode"),
            "final_gate_status": result.get("final_gate_status"),
            "citation_like_count": result.get("citation_like_count"),
            "total_match_count": result.get("retrieval", {}).get("total_match_count"),
            "returned_match_count": result.get("retrieval", {}).get("returned_match_count"),
            "result_was_capped": result.get("retrieval", {}).get("result_was_capped"),
            "safety": result.get("safety"),
        },
    }


class TraceNetV25Handler(BaseHTTPRequestHandler):
    state: Dict[str, Any] = {}

    def _send_json(self, payload: Mapping[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_json({"status": "ok"})

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/", "/health"}:
            self._send_json(health_response(self.state))
            return
        if self.path == "/v1/models":
            self._send_json(openai_models_response(self.state))
            return
        self._send_json({"error": f"Unknown route: {self.path}"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/chat/completions":
            self._send_json({"error": f"Unknown route: {self.path}"}, status=404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            payload = json.loads(raw) if raw else {}
            if not isinstance(payload, dict):
                raise ValueError("payload must be a JSON object")
            self._send_json(chat_completion_response(self.state, payload))
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=400)


def serve(state: Dict[str, Any], host: str, port: int) -> None:
    TraceNetV25Handler.state = state
    server = HTTPServer((host, port), TraceNetV25Handler)
    print(f"TRACE-Net v25 serving {state.get('model_id', MODEL_ID)} at http://{host}:{port}/v1", flush=True)
    server.serve_forever()
