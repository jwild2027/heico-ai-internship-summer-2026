"""TRACE-Net E2E Live Relationship/Synthesis Planner v29.

v29 sits behind v28.  v28 handles deterministic source-truth lookup,
listing, and drill-down.  v29 adds guarded relationship/navigation/synthesis
handling for questions that mention graph, Leiden communities, related pages,
neighbors, links, or relationships.

Safety contract:
- Source-truth evidence is the only proof authority.
- Graph/Leiden and v2 summaries are navigation guidance only.
- The LLM may draft synthesis text, but final answers are rebuilt/gated from
  direct source-truth evidence plus explicit guidance-only disclosures.
- The endpoint uses prebuilt indexes/artifacts only; it does not scan raw 5TB
  data, rebuild graphs, rerun OCR, mutate source truth, or write to services.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from collections import Counter
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from tiff import trace_net_e2e_live_orchestrator_endpoint_v25 as v25
from tiff import trace_net_e2e_live_deterministic_answer_planner_v28 as v28

MODULE = "trace_net_e2e_live_relationship_synthesis_planner_v29"
VERSION = "v29"
MODEL_ID = "trace-net-e2e-live-relationship-synthesis-gemma-v29"
STATUS_READY = "E2E_LIVE_RELATIONSHIP_SYNTHESIS_PLANNER_READY"
STATUS_NEEDS_REPAIR = "E2E_LIVE_RELATIONSHIP_SYNTHESIS_PLANNER_NEEDS_REPAIR"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"

_ENDPOINT_ROUTES = ["/health", "/v1/models", "/v1/chat/completions", "/"]
DEFAULT_SAMPLE_QUERIES = [
    "Find part number 120-36833-503",
    "Find part number DOES-NOT-EXIST-999",
    "What maintenance manual pages mention covered part numbers?",
    "Drill down covered part numbers by page",
    "What pages are related to part number 120-36833-503?",
    "Which pages are in the same Leiden community as page t_p_120_1176_p000003?",
    "Show graph neighbors for page t_p_120_1176_p000003",
    "Explain how part number 120-36833-503 relates to manual reference 25-21-00",
]

PAGE_ID_RE = re.compile(r"\bt_p_\d+_\d+_p\d{6}\b", flags=re.I)
PART_NUMBER_RE = re.compile(r"\b\d{3}-\d{5}-\d{3}\b")
MANUAL_REF_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")


def read_json(path: Path) -> Dict[str, Any]:
    return v25.read_json(path)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    v25.write_json(path, payload)


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    v25.write_jsonl(path, rows)


def _now() -> float:
    return time.perf_counter()


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000.0, 3)


def _to_int(value: Any, default: int = 0) -> int:
    return v25._to_int(value, default)


def normalize_query(query: str) -> str:
    return v25.normalize_query(query)


def _sum_timing(stage_timings_ms: Mapping[str, Any]) -> float:
    total = 0.0
    for value in stage_timings_ms.values():
        try:
            total += float(value)
        except Exception:
            continue
    return round(total, 3)


def is_relationship_query(query: str) -> bool:
    normalized = normalize_query(query)
    keywords = [
        "related", "relationship", "relates", "connect", "connected", "connection",
        "same leiden", "leiden", "community", "graph", "neighbor", "neighbour",
        "inspect next", "path", "linked", "links",
    ]
    return any(token in normalized for token in keywords)


def relationship_mode(query: str) -> str:
    normalized = normalize_query(query)
    if any(token in normalized for token in ["explain", "how", "why", "relates to", "relationship between"]):
        return "relationship_synthesis"
    return "relationship_navigation"


def extract_seed_terms(query: str) -> Dict[str, Any]:
    pages = sorted(set(m.group(0) for m in PAGE_ID_RE.finditer(query or "")))
    parts = sorted(set(m.group(0) for m in PART_NUMBER_RE.finditer(query or "")))
    manual_refs = sorted(set(m.group(0) for m in MANUAL_REF_RE.finditer(query or "")))
    return {"page_ids": pages, "part_numbers": parts, "manual_references": manual_refs}


def _compact(value: Any) -> str:
    return v25.compact_value(str(value or ""))


def _target_matches(target: str, value: str) -> bool:
    ct = _compact(target)
    cv = _compact(value)
    return bool(ct and cv and (ct == cv or ct in cv or (cv in ct and len(cv) > 3)))


def _row_copy(row: Mapping[str, Any], citation_id: int) -> Dict[str, Any]:
    out = dict(row)
    out["citation_id"] = citation_id
    return out


def find_seed_evidence(docs: Sequence[Mapping[str, Any]], seeds: Mapping[str, Any], top_k: int = 10) -> List[Dict[str, Any]]:
    """Find direct source-truth seed evidence for relationship planning.

    This is intentionally strict.  It only uses exact/compact matches for parsed
    part numbers and manual references. Page IDs may seed graph navigation but do
    not create proof rows by themselves.
    """
    targets: List[Tuple[str, str, Tuple[str, ...]]] = []
    for part in seeds.get("part_numbers") or []:
        targets.append(("part_number", part, ("covered_part_number", "ipl_part_number", "part_number")))
    for ref in seeds.get("manual_references") or []:
        targets.append(("manual_page_reference", ref, ("manual_page_reference", "ipl_part_number")))

    rows: List[Dict[str, Any]] = []
    seen = set()
    for intent, target, fields in targets:
        for doc in docs:
            field = str(doc.get("field_name") or doc.get("field") or "")
            value = str(doc.get("normalized_value") or doc.get("value") or "")
            if field not in fields or not _target_matches(target, value):
                continue
            page_id = str(doc.get("page_id") or doc.get("page") or "")
            key = (page_id, field, value, target)
            if key in seen:
                continue
            seen.add(key)
            row = dict(doc)
            row.setdefault("page_id", page_id)
            row.setdefault("field_name", field)
            row.setdefault("normalized_value", value)
            row["seed_target"] = target
            row["seed_intent"] = intent
            row["citation_id"] = len(rows) + 1
            rows.append(row)
            if len(rows) >= top_k:
                return rows
    return rows


def seed_pages_from_evidence_and_query(seed_evidence: Sequence[Mapping[str, Any]], seeds: Mapping[str, Any]) -> List[str]:
    pages = []
    for page_id in seeds.get("page_ids") or []:
        if page_id not in pages:
            pages.append(page_id)
    for row in seed_evidence:
        page_id = str(row.get("page_id") or "")
        if page_id and page_id not in pages:
            pages.append(page_id)
    return pages


def build_relationship_guidance(
    seed_pages: Sequence[str],
    page_summaries: Mapping[str, str],
    page_to_community: Mapping[str, str],
    community_to_pages: Mapping[str, Sequence[str]],
    max_pages_per_community: int = 25,
) -> List[Dict[str, Any]]:
    guidance: List[Dict[str, Any]] = []
    for seed_page in seed_pages:
        community = str(page_to_community.get(seed_page) or "")
        candidate_pages = list(community_to_pages.get(community) or [])[:max_pages_per_community] if community else []
        if seed_page and seed_page not in candidate_pages:
            candidate_pages = [seed_page] + candidate_pages
        candidate_pages = list(dict.fromkeys(candidate_pages))[:max_pages_per_community]
        summaries = []
        for page_id in candidate_pages[:5]:
            summary = page_summaries.get(page_id)
            if summary:
                summaries.append({
                    "page_id": page_id,
                    "summary": summary,
                    "authority": "guidance_only",
                    "proof_authority": False,
                })
        guidance.append({
            "seed_page_id": seed_page,
            "leiden_community_id": community or "unknown_community",
            "candidate_page_ids": candidate_pages,
            "candidate_page_count": len(candidate_pages),
            "returned_candidate_page_count": len(candidate_pages),
            "summary_guidance": summaries,
            "authority": "guidance_only",
            "proof_authority": False,
            "requires_source_truth_confirmation": True,
            "graph_path_provenance": [
                {"hop": 0, "node_id": seed_page, "node_type": "seed_page"},
                {"hop": 1, "node_id": community or "unknown_community", "edge_type": "member_of_leiden_community"},
            ],
        })
    return guidance


def _citation_fragment(row: Mapping[str, Any]) -> str:
    value = str(row.get("normalized_value") or row.get("value") or "")
    return f"{value} [{row.get('citation_id')}]"


def build_relationship_answer(
    query: str,
    relation_mode: str,
    seeds: Mapping[str, Any],
    seed_evidence: Sequence[Mapping[str, Any]],
    relationship_guidance: Sequence[Mapping[str, Any]],
    llm_status: str,
) -> Tuple[str, Dict[str, Any]]:
    direct_count = len(seed_evidence)
    candidate_pages: List[str] = []
    community_ids: List[str] = []
    for item in relationship_guidance:
        for page_id in item.get("candidate_page_ids") or []:
            if page_id not in candidate_pages:
                candidate_pages.append(page_id)
        community = str(item.get("leiden_community_id") or "")
        if community and community not in community_ids:
            community_ids.append(community)

    if direct_count == 0 and not seeds.get("page_ids"):
        answer = (
            "TRACE-Net did not find direct source-truth seed evidence for this relationship query. "
            "No relationship claim is made. Try seeding the question with an exact part number, manual reference, or page ID."
        )
        return answer, {
            "answerable": False,
            "response_mode": relation_mode,
            "relationship_guidance_only": True,
            "relationship_proof_violation": False,
            "unsupported_claim_count": 0,
            "citation_like_count": 0,
            "candidate_page_count": 0,
            "leiden_community_count": 0,
        }

    parts: List[str] = []
    if direct_count:
        examples = "; ".join(_citation_fragment(row) for row in seed_evidence[:5])
        pages = sorted({str(row.get("page_id")) for row in seed_evidence if row.get("page_id")})
        parts.append(
            f"TRACE-Net found direct source-truth seed evidence on page(s) {', '.join(pages)}: {examples}."
        )
    elif seeds.get("page_ids"):
        parts.append(
            "TRACE-Net is using the requested page ID as a graph-navigation seed. "
            "A page ID can seed navigation, but it is not by itself proof of a part/manual relationship."
        )

    if community_ids or candidate_pages:
        community_text = ", ".join(community_ids[:3]) if community_ids else "unknown community"
        page_text = ", ".join(candidate_pages[:8]) if candidate_pages else "no candidate pages returned"
        parts.append(
            f"Leiden/graph guidance places the seed page(s) in {community_text}; candidate pages for inspection include {page_text}."
        )

    if relation_mode == "relationship_synthesis":
        parts.append(
            "The available context can guide inspection, but it does not by itself prove a factual relationship between the entities unless a direct source-truth record states that relationship."
        )
    else:
        parts.append(
            "Graph/Leiden output is guidance only, not proof. Confirm candidate pages with source-truth evidence before making a relationship claim."
        )

    answer = " ".join(parts)
    return answer, {
        "answerable": True,
        "response_mode": relation_mode,
        "relationship_guidance_only": True,
        "relationship_proof_violation": False,
        "unsupported_claim_count": 0,
        "citation_like_count": v25.citation_like_count(answer),
        "candidate_page_count": len(candidate_pages),
        "leiden_community_count": len(community_ids),
        "llm_status": llm_status,
    }


def render_relationship_prompt(
    query: str,
    seeds: Mapping[str, Any],
    seed_evidence: Sequence[Mapping[str, Any]],
    relationship_guidance: Sequence[Mapping[str, Any]],
) -> List[Dict[str, str]]:
    evidence_lines = []
    for row in seed_evidence:
        evidence_lines.append(
            f"[{row.get('citation_id')}] page={row.get('page_id')} field={row.get('field_name')} value={row.get('normalized_value')}"
        )
    context = {
        "source_truth_seed_evidence": evidence_lines,
        "graph_leiden_guidance_only": relationship_guidance,
        "seed_terms": dict(seeds),
        "rules": {
            "source_truth_is_only_proof_authority": True,
            "graph_leiden_guidance_is_not_proof": True,
            "v2_summaries_are_not_proof": True,
            "do_not_invent_relationships": True,
        },
    }
    return [
        {
            "role": "system",
            "content": (
                "You are the TRACE-Net relationship draft writer. Write only from the provided context. "
                "Source-truth seed evidence may prove only the seed facts. Graph/Leiden and summaries are navigation guidance only. "
                "Do not claim a factual relationship unless direct source-truth evidence states it."
            ),
        },
        {"role": "user", "content": query},
        {"role": "user", "content": "TRACE-NET RELATIONSHIP CONTEXT\n" + json.dumps(context, indent=2)},
    ]


def standard_safety(response_is_final_gated: bool = True, llm_called: bool = False) -> Dict[str, Any]:
    base = v28.standard_safety(response_is_final_gated=response_is_final_gated, llm_called=llm_called)
    base["relationship_planner_enabled"] = True
    base["graph_leiden_guidance_only"] = True
    return base


def run_relationship_query_v29(
    query: str,
    state: Mapping[str, Any],
    llm_mode: Optional[str] = None,
    request_timeout: Optional[int] = None,
) -> Dict[str, Any]:
    total_start = _now()
    stage_timings_ms: Dict[str, float] = {}

    stage = _now()
    seeds = extract_seed_terms(query)
    relation_mode = relationship_mode(query)
    stage_timings_ms["relationship_planning_ms"] = _elapsed_ms(stage)

    stage = _now()
    seed_evidence = find_seed_evidence(state.get("exact_search_documents") or [], seeds, top_k=_to_int(state.get("top_k"), 10))
    seed_pages = seed_pages_from_evidence_and_query(seed_evidence, seeds)
    stage_timings_ms["source_truth_seed_retrieval_ms"] = _elapsed_ms(stage)

    stage = _now()
    relationship_guidance = build_relationship_guidance(
        seed_pages,
        state.get("page_summaries") or {},
        state.get("page_to_community") or {},
        state.get("community_to_pages") or {},
        max_pages_per_community=_to_int(state.get("max_pages_per_community"), 25),
    )
    stage_timings_ms["graph_leiden_guidance_ms"] = _elapsed_ms(stage)

    stage = _now()
    prompt_messages = render_relationship_prompt(query, seeds, seed_evidence, relationship_guidance)
    stage_timings_ms["context_prompt_pack_ms"] = _elapsed_ms(stage)

    mode = llm_mode or str(state.get("llm_mode") or "simulate")
    llm_status = "LLM_NOT_CALLED"
    llm_called = False
    llm_metadata: Dict[str, Any] = {}
    draft = ""
    error = ""

    stage = _now()
    llm_eligible = relation_mode == "relationship_synthesis" and bool(seed_evidence or seed_pages)
    if not llm_eligible:
        llm_status = "LLM_SKIPPED_RELATIONSHIP_NAVIGATION"
        draft = "TRACE-Net relationship navigation used; final answer is rebuilt/gated from source-truth seed evidence and graph guidance disclosures."
    else:
        try:
            if mode == "ollama":
                draft, llm_metadata = v25.call_ollama_chat(
                    prompt_messages,
                    str(state.get("llm_base_url") or "http://127.0.0.1:11434/v1"),
                    str(state.get("llm_model") or "gemma4:26b"),
                    str(state.get("llm_api_key") or "ollama"),
                    float(state.get("temperature", 0)),
                    int(request_timeout or state.get("request_timeout", 240)),
                )
                llm_called = True
                llm_status = "LLM_CALL_SUCCEEDED_RELATIONSHIP_DRAFT"
            else:
                draft = "Simulated relationship synthesis draft; final answer remains TRACE-Net-gated."
                llm_status = "LLM_SIMULATED_RELATIONSHIP_DRAFT"
        except Exception as exc:
            error = str(exc)
            draft = "LLM relationship draft failed; TRACE-Net returned guarded relationship guidance only."
            llm_status = "LLM_CALL_FAILED_RELATIONSHIP_GUIDANCE_FALLBACK"
            llm_metadata = {"error": error}
    stage_timings_ms["llm_relationship_draft_ms"] = _elapsed_ms(stage)

    stage = _now()
    final_answer, final_meta = build_relationship_answer(query, relation_mode, seeds, seed_evidence, relationship_guidance, llm_status)
    stage_timings_ms["relationship_final_gate_ms"] = _elapsed_ms(stage)

    total_latency_ms = _elapsed_ms(total_start)
    stage_timings_ms["total_request_ms"] = total_latency_ms
    answerable = bool(final_meta.get("answerable"))
    non_llm_ms = round(total_latency_ms - float(stage_timings_ms.get("llm_relationship_draft_ms", 0.0)), 3)

    return {
        "user_query": query,
        "relationship_query": True,
        "response_mode": relation_mode,
        "seed_terms": seeds,
        "source_truth_seed_evidence": seed_evidence,
        "source_truth_seed_evidence_count": len(seed_evidence),
        "relationship_guidance": relationship_guidance,
        "relationship_guidance_count": len(relationship_guidance),
        "candidate_page_count": int(final_meta.get("candidate_page_count", 0)),
        "leiden_community_count": int(final_meta.get("leiden_community_count", 0)),
        "relationship_guidance_only": True,
        "relationship_proof_violation": False,
        "prompt_message_count": len(prompt_messages),
        "llm_mode": mode,
        "llm_status": llm_status,
        "llm_called": llm_called,
        "llm_draft_text": draft,
        "llm_metadata": llm_metadata,
        "llm_error": error,
        "stage_timings_ms": stage_timings_ms,
        "latency_summary": {
            "total_request_ms": total_latency_ms,
            "llm_draft_ms": stage_timings_ms.get("llm_relationship_draft_ms", 0.0),
            "non_llm_ms": non_llm_ms,
            "stage_timing_sum_ms": _sum_timing({k: v for k, v in stage_timings_ms.items() if k != "total_request_ms"}),
        },
        "final_gate_status": "LIVE_RELATIONSHIP_FINAL_GATE_PASS" if answerable else "LIVE_RELATIONSHIP_AUDIT_ONLY",
        "final_answer": final_answer,
        "final_answer_ready_for_webui": answerable,
        "unsupported_claim_count": final_meta.get("unsupported_claim_count", 0),
        "citation_like_count": final_meta.get("citation_like_count", 0),
        "safety": standard_safety(response_is_final_gated=answerable, llm_called=llm_called),
    }


def run_live_query_v29(
    query: str,
    state: Mapping[str, Any],
    llm_mode: Optional[str] = None,
    request_timeout: Optional[int] = None,
) -> Dict[str, Any]:
    if is_relationship_query(query):
        return run_relationship_query_v29(query, state, llm_mode=llm_mode, request_timeout=request_timeout)
    result = v28.run_live_query_v28(query, state, llm_mode=llm_mode, request_timeout=request_timeout)
    result["relationship_query"] = False
    result.setdefault("relationship_proof_violation", False)
    return result


def build_state(
    table_exact_search_adapter_path: Path,
    output_dir: Optional[Path] = None,
    page_context_v2_path: Optional[Path] = None,
    leiden_communities_path: Optional[Path] = None,
    host: str = "127.0.0.1",
    port: int = 8024,
    model_id: str = MODEL_ID,
    llm_mode: str = "simulate",
    llm_base_url: str = "http://127.0.0.1:11434/v1",
    llm_model: str = "gemma4:26b",
    llm_api_key: str = "ollama",
    temperature: float = 0.0,
    request_timeout: int = 240,
    top_k: int = 10,
    max_pages_per_community: int = 25,
    deterministic_mode: str = "expanded",
    relationship_mode_setting: str = "guarded",
    include_standard_demo_queries: bool = False,
) -> Dict[str, Any]:
    base = v28.build_state(
        table_exact_search_adapter_path=table_exact_search_adapter_path,
        output_dir=output_dir,
        page_context_v2_path=page_context_v2_path,
        leiden_communities_path=leiden_communities_path,
        host=host,
        port=port,
        model_id=model_id,
        llm_mode=llm_mode,
        llm_base_url=llm_base_url,
        llm_model=llm_model,
        llm_api_key=llm_api_key,
        temperature=temperature,
        request_timeout=request_timeout,
        top_k=top_k,
        max_pages_per_community=max_pages_per_community,
        deterministic_mode=deterministic_mode,
        include_standard_demo_queries=False,
    )
    state: Dict[str, Any] = dict(base)
    state.update({
        "module": MODULE,
        "version": VERSION,
        "model_id": model_id,
        "port": port,
        "base_url_windows": f"http://{host}:{port}/v1",
        "base_url_open_webui_docker": f"http://host.docker.internal:{port}/v1",
        "relationship_mode": relationship_mode_setting,
        "contract": dict(base.get("contract") or {}),
    })
    state["contract"].update({
        "relationship_synthesis_planner_enabled": True,
        "graph_leiden_guidance_only": True,
        "relationship_claims_require_source_truth": True,
        "llm_reserved_for_relationship_or_synthesis": True,
        "final_answer_rebuilt_from_source_truth": True,
        "raw_5tb_scan_at_query_time": False,
        "graph_rebuild_at_query_time": False,
        "source_truth_mutation_allowed": False,
        "answer_permission": False,
    })
    if include_standard_demo_queries:
        samples = [run_live_query_v29(q, state, llm_mode=llm_mode, request_timeout=request_timeout) for q in DEFAULT_SAMPLE_QUERIES]
        state["sample_results"] = samples
        state["sample_query_count"] = len(samples)
        state["sample_success_count"] = sum(1 for r in samples if str(r.get("final_gate_status") or "").endswith("PASS") or str(r.get("final_gate_status") or "").endswith("AUDIT_ONLY"))
        state["stage_timing_record_count"] = sum(1 for r in samples if isinstance(r.get("stage_timings_ms"), Mapping) and r["stage_timings_ms"].get("total_request_ms") is not None)
        state["relationship_sample_count"] = sum(1 for r in samples if r.get("relationship_query"))
        state["relationship_guidance_sample_count"] = sum(1 for r in samples if r.get("relationship_guidance_count", 0) > 0)
        state["relationship_synthesis_sample_count"] = sum(1 for r in samples if r.get("response_mode") == "relationship_synthesis")
        state["relationship_proof_violation_count"] = sum(1 for r in samples if r.get("relationship_proof_violation"))
        state["llm_called_sample_count"] = sum(1 for r in samples if r.get("llm_called"))
        state["sample_total_latency_ms"] = round(sum(float((r.get("latency_summary") or {}).get("total_request_ms") or 0.0) for r in samples), 3)
        state["sample_avg_latency_ms"] = round(state["sample_total_latency_ms"] / len(samples), 3) if samples else 0.0
        state["sample_avg_llm_ms"] = round(sum(float((r.get("latency_summary") or {}).get("llm_draft_ms") or 0.0) for r in samples) / len(samples), 3) if samples else 0.0
        state["response_mode_counts"] = dict(Counter(str(r.get("response_mode")) for r in samples))
    else:
        state.update({
            "sample_results": [],
            "sample_query_count": 0,
            "sample_success_count": 0,
            "stage_timing_record_count": 0,
            "relationship_sample_count": 0,
            "relationship_guidance_sample_count": 0,
            "relationship_synthesis_sample_count": 0,
            "relationship_proof_violation_count": 0,
            "llm_called_sample_count": 0,
            "sample_total_latency_ms": 0.0,
            "sample_avg_latency_ms": 0.0,
            "sample_avg_llm_ms": 0.0,
            "response_mode_counts": {},
        })
    return state


def evaluate_quality(
    state: Mapping[str, Any],
    min_exact_search_documents: int = 10,
    min_endpoint_routes: int = 4,
    min_sample_queries: int = 0,
    min_sample_successes: int = 0,
    min_stage_timing_records: int = 0,
    min_relationship_samples: int = 0,
    min_relationship_guidance_samples: int = 0,
    min_relationship_synthesis_samples: int = 0,
    max_relationship_proof_violations: int = 0,
    max_answer_permission_count: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    require_no_answer_permission: bool = False,
) -> Tuple[str, List[Dict[str, Any]]]:
    checks: List[Tuple[str, Any, str, Any]] = [
        ("exact_search_document_count", state.get("exact_search_document_count", 0), ">=", min_exact_search_documents),
        ("endpoint_route_count", state.get("endpoint_route_count", 0), ">=", min_endpoint_routes),
        ("sample_query_count", state.get("sample_query_count", 0), ">=", min_sample_queries),
        ("sample_success_count", state.get("sample_success_count", 0), ">=", min_sample_successes),
        ("stage_timing_record_count", state.get("stage_timing_record_count", 0), ">=", min_stage_timing_records),
        ("relationship_sample_count", state.get("relationship_sample_count", 0), ">=", min_relationship_samples),
        ("relationship_guidance_sample_count", state.get("relationship_guidance_sample_count", 0), ">=", min_relationship_guidance_samples),
        ("relationship_synthesis_sample_count", state.get("relationship_synthesis_sample_count", 0), ">=", min_relationship_synthesis_samples),
        ("relationship_proof_violation_count", state.get("relationship_proof_violation_count", 0), "<=", max_relationship_proof_violations),
        ("answer_permission_count", state.get("answer_permission_count", 0), "<=", max_answer_permission_count),
        ("source_truth_mutation_allowed_count", state.get("source_truth_mutation_allowed_count", 0), "<=", max_source_truth_mutation_allowed),
        ("contract_raw_5tb_scan_at_query_time", state.get("contract", {}).get("raw_5tb_scan_at_query_time"), "is", False),
        ("contract_graph_rebuild_at_query_time", state.get("contract", {}).get("graph_rebuild_at_query_time"), "is", False),
        ("contract_relationship_claims_require_source_truth", state.get("contract", {}).get("relationship_claims_require_source_truth"), "is", True),
        ("contract_graph_leiden_guidance_only", state.get("contract", {}).get("graph_leiden_guidance_only"), "is", True),
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
    out = v28._state_for_file(state)
    out["sample_results"] = list(state.get("sample_results") or [])
    return out


def render_markdown_report(state: Mapping[str, Any]) -> str:
    lines = [
        "# TRACE-Net E2E Live Relationship/Synthesis Planner v29",
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
        "stage_timing_record_count",
        "relationship_sample_count",
        "relationship_guidance_sample_count",
        "relationship_synthesis_sample_count",
        "relationship_proof_violation_count",
        "llm_called_sample_count",
        "sample_avg_latency_ms",
        "sample_avg_llm_ms",
        "response_mode_counts",
        "relationship_mode",
        "llm_mode",
        "llm_model",
        "base_url_windows",
        "base_url_open_webui_docker",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ]:
        lines.append(f"- {key}: {state.get(key)}")
    lines.extend([
        "",
        "## Contract",
        "- v28 deterministic lookup/listing/drill-down remains the first path.",
        "- Relationship/navigation/synthesis questions use graph/Leiden as guidance only.",
        "- Source-truth seed evidence proves only the seed facts, not inferred relationships.",
        "- The LLM may draft relationship synthesis, but TRACE-Net rebuilds/final-gates the answer.",
        "- No raw 5TB scan, graph rebuild, OCR rerun, source-truth mutation, or service writes occur at query time.",
        "",
        "## Sample query results",
    ])
    for result in state.get("sample_results", []):
        latency = result.get("latency_summary") or {}
        lines.append(f"### {result.get('user_query')}")
        lines.append(f"- relationship_query: {result.get('relationship_query')}")
        lines.append(f"- response_mode: {result.get('response_mode')}")
        lines.append(f"- final_gate_status: {result.get('final_gate_status')}")
        lines.append(f"- llm_status: {result.get('llm_status')}")
        lines.append(f"- source_truth_seed_evidence_count: {result.get('source_truth_seed_evidence_count', '')}")
        lines.append(f"- relationship_guidance_count: {result.get('relationship_guidance_count', '')}")
        lines.append(f"- candidate_page_count: {result.get('candidate_page_count', '')}")
        lines.append(f"- total_request_ms: {latency.get('total_request_ms')}")
        lines.append(f"- llm_draft_ms: {latency.get('llm_draft_ms')}")
        lines.append(f"- final_answer_preview: {str(result.get('final_answer') or '')[:500]}")
        lines.append("")
    lines.extend(["## Quality checks"])
    for row in state.get("quality_checks", []):
        status = "PASS" if row.get("passed") else "FAIL"
        lines.append(f"- {status} {row['name']}: observed={row['observed']} expected={row['op']} {row['expected']}")
    if state.get("report_path"):
        lines.extend(["", f"report_path: `{state.get('report_path')}`", f"sample_jsonl_path: `{state.get('sample_jsonl_path')}`"])
    return "\n".join(lines) + "\n"


def write_endpoint_files(state: Dict[str, Any], output_dir: Path) -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "trace_net_e2e_live_relationship_synthesis_planner_v29.json"
    sample_jsonl_path = output_dir / "trace_net_e2e_live_relationship_synthesis_planner_samples_v29.jsonl"
    inspect_md_path = output_dir / "trace_net_e2e_live_relationship_synthesis_planner_v29.md"
    state["report_path"] = str(report_path)
    state["sample_jsonl_path"] = str(sample_jsonl_path)
    state["inspect_md_path"] = str(inspect_md_path)
    write_json(report_path, _state_for_file(state))
    write_jsonl(sample_jsonl_path, state.get("sample_results", []))
    inspect_md_path.write_text(render_markdown_report(state), encoding="utf-8")
    write_json(report_path, _state_for_file(state))
    return {"report_path": str(report_path), "sample_jsonl_path": str(sample_jsonl_path), "inspect_md_path": str(inspect_md_path)}


def load_state_for_serving(report_path: Path) -> Dict[str, Any]:
    state = read_json(report_path)
    adapter = Path(str(state.get("table_exact_search_adapter_path") or ""))
    if adapter.exists():
        state["exact_search_documents"] = v25.load_exact_docs(adapter)
    page_path = Path(str(state.get("page_context_v2_path") or "")) if state.get("page_context_v2_path") else None
    leiden_path = Path(str(state.get("leiden_communities_path") or "")) if state.get("leiden_communities_path") else None
    state["page_summaries"] = v25.load_optional_page_summaries(page_path)
    page_to_community, community_to_pages = v25.load_optional_leiden(leiden_path)
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
        "relationship_mode": state.get("relationship_mode"),
        "safety": standard_safety(response_is_final_gated=True, llm_called=False),
    }


def chat_completion_response(state: Mapping[str, Any], request_payload: Mapping[str, Any]) -> Dict[str, Any]:
    query = v25.extract_user_message(request_payload.get("messages"))
    result = run_live_query_v29(query, state)
    retrieval = result.get("retrieval") or {}
    return {
        "id": "chatcmpl-tracenet-v29-" + uuid.uuid4().hex[:16],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": state.get("model_id", MODEL_ID),
        "choices": [{"index": 0, "message": {"role": "assistant", "content": result["final_answer"]}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "trace_net": {
            "endpoint_version": "live_relationship_synthesis_planner_v29",
            "relationship_query": result.get("relationship_query"),
            "response_mode": result.get("response_mode"),
            "llm_status": result.get("llm_status"),
            "llm_mode": result.get("llm_mode"),
            "llm_called": result.get("llm_called"),
            "final_gate_status": result.get("final_gate_status"),
            "citation_like_count": result.get("citation_like_count"),
            "query_intent": (result.get("query_plan") or {}).get("query_intent"),
            "total_match_count": retrieval.get("total_match_count"),
            "returned_match_count": retrieval.get("returned_match_count"),
            "source_truth_seed_evidence_count": result.get("source_truth_seed_evidence_count"),
            "relationship_guidance_count": result.get("relationship_guidance_count"),
            "candidate_page_count": result.get("candidate_page_count"),
            "leiden_community_count": result.get("leiden_community_count"),
            "relationship_guidance_only": result.get("relationship_guidance_only"),
            "relationship_proof_violation": result.get("relationship_proof_violation"),
            "stage_timings_ms": result.get("stage_timings_ms"),
            "latency_summary": result.get("latency_summary"),
            "safety": result.get("safety"),
        },
    }


class TraceNetV29Handler(BaseHTTPRequestHandler):
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
    TraceNetV29Handler.state = state
    server = HTTPServer((host, port), TraceNetV29Handler)
    print(f"TRACE-Net v29 serving {state.get('model_id', MODEL_ID)} at http://{host}:{port}/v1", flush=True)
    server.serve_forever()
