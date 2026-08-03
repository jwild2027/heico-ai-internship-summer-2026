"""TRACE-Net E2E Live Deterministic Answer Planner + Drilldown v28.

v28 extends the v27 stage-timing fast path with an explicit deterministic answer
planner.  The goal is to keep operational/source-truth questions fast while
reserving the local LLM for relationship or synthesis work.

New response modes:
- exact_single_value
- exact_missing_value
- field_listing
- capped_listing
- drilldown_request
- relationship_or_synthesis_needs_llm

The module never scans raw 5TB source data, rebuilds graph artifacts, reruns OCR,
mutates source truth, or writes to Postgres/Qdrant/OpenSearch. Source-truth
records are the only proof authority. Graph/Leiden, v2 summaries, nearby OCR, and
aggregation metadata remain guidance/disclosure only. v28.1 also polishes deterministic answer spacing and preserves raw/collapsed match metadata for exact filtered responses.
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
from tiff import trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27 as v27

MODULE = "trace_net_e2e_live_deterministic_answer_planner_v28"
VERSION = "v28"
MODEL_ID = "trace-net-e2e-live-deterministic-planner-gemma-v28"
STATUS_READY = "E2E_LIVE_DETERMINISTIC_ANSWER_PLANNER_READY"
STATUS_NEEDS_REPAIR = "E2E_LIVE_DETERMINISTIC_ANSWER_PLANNER_NEEDS_REPAIR"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"

_ENDPOINT_ROUTES = ["/health", "/v1/models", "/v1/chat/completions", "/"]
DEFAULT_SAMPLE_QUERIES = [
    "Find part number 120-36833-503",
    "Find part number DOES-NOT-EXIST-999",
    "Where is manual reference 25-21-00 used?",
    "Where is manual reference 99-99-99 used?",
    "Search table text ILLUSTRATED PARTS LIST",
    "Search table text THIS TEXT DOES NOT EXIST",
    "What maintenance manual pages mention covered part numbers?",
    "Drill down covered part numbers by page",
]

DETERMINISTIC_RESPONSE_MODES = {
    "exact_single_value",
    "exact_missing_value",
    "field_listing",
    "capped_listing",
    "drilldown_request",
}
FIELD_LISTING_INTENTS = {"covered_part_number", "manual_page_reference", "table_text"}


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


def _sum_timing(stage_timings_ms: Mapping[str, Any]) -> float:
    total = 0.0
    for value in stage_timings_ms.values():
        try:
            total += float(value)
        except Exception:
            continue
    return round(total, 3)


def _occurrence_count(row: Mapping[str, Any]) -> int:
    return max(1, _to_int(row.get("occurrence_count"), 1))


def _deduped_occurrence_count(rows: Sequence[Mapping[str, Any]]) -> int:
    return sum(_occurrence_count(row) for row in rows)


def _polish_answer_text(text: str) -> str:
    """Clean deterministic formatter whitespace without changing claims."""
    text = str(text or "")
    text = re.sub(r"(?<=\d)\[(\d+)\]", r" [\1]", text)
    text = text.replace("doesnot", "does not")
    text = text.replace("onlyand", "only and")
    text = text.replace("availableevidence", "available evidence")
    text = re.sub(r"\s+([.;,:])", r"\1", text)
    text = re.sub(r"([.;,:])(?=\S)", r"\1 ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_query(query: str) -> str:
    return v25.normalize_query(query)



def detect_query_plan_v28(query: str) -> Dict[str, Any]:
    """Use v25 planning, with stricter entity extraction for non-canonical values.

    This catches prompts like `Find part number DOES-NOT-EXIST-999`, which are
    intentionally not canonical aircraft part-number shapes but must still be
    treated as strict exact lookups rather than broad searches.
    """
    plan = dict(v25.detect_query_plan(query))
    normalized = normalize_query(query)
    target = str(plan.get("target_value") or "").strip()
    if not target:
        m = re.search(r"find\s+part\s+number\s+(.+)$", query or "", flags=re.I)
        if m:
            target = m.group(1).strip().strip("?.")
            plan.update({
                "query_intent": "part_number",
                "target_value": target,
                "required_source_truth_fields": ["covered_part_number", "ipl_part_number", "part_number"],
                "strict_target_match_required": True,
            })
        m = re.search(r"where\s+is\s+manual\s+reference\s+(.+?)\s+used", query or "", flags=re.I)
        if m:
            target = m.group(1).strip().strip("?.")
            plan.update({
                "query_intent": "manual_page_reference",
                "target_value": target,
                "required_source_truth_fields": ["manual_page_reference", "ipl_part_number"],
                "strict_target_match_required": True,
            })
    if plan.get("target_value"):
        plan.setdefault("strict_target_match_required", True)
    elif plan.get("query_intent") in {"covered_part_number"}:
        plan.setdefault("strict_target_match_required", False)
    return plan


def _compact(value: Any) -> str:
    return v25.compact_value(str(value or ""))


def _target_matches_value(target: str, value: str) -> bool:
    ct = _compact(target)
    cv = _compact(value)
    if not ct or not cv:
        return False
    return ct == cv or ct in cv or (cv in ct and len(cv) > 3)


def apply_strict_target_filter(plan: Mapping[str, Any], retrieval: Mapping[str, Any]) -> Dict[str, Any]:
    """Remove broad same-field matches when a strict target value was requested.

    v28.1 keeps explicit raw/collapsed metadata so the WebUI can distinguish:
    - target_unique_match_count: unique citation rows after page+field+value dedupe
    - target_occurrence_count: duplicate source records represented by those rows
    - raw_candidate_match_count: broader candidate count before strict filtering

    The answer still uses only filtered direct evidence as proof authority.
    """
    target = _target_value(plan)
    if not target:
        filtered = dict(retrieval)
        rows = list(filtered.get("direct_evidence") or []) + list(filtered.get("nearby_context") or [])
        filtered.setdefault("raw_candidate_match_count", _to_int(filtered.get("total_match_count"), len(rows)))
        filtered.setdefault("target_unique_match_count", len(rows))
        filtered.setdefault("target_occurrence_count", _deduped_occurrence_count(rows))
        filtered.setdefault("collapsed_duplicate_record_count", max(0, _deduped_occurrence_count(rows) - len(rows)))
        return filtered
    strict = bool(plan.get("strict_target_match_required", True))
    if not strict:
        filtered = dict(retrieval)
        rows = list(filtered.get("direct_evidence") or []) + list(filtered.get("nearby_context") or [])
        filtered.setdefault("raw_candidate_match_count", _to_int(filtered.get("total_match_count"), len(rows)))
        filtered.setdefault("target_unique_match_count", len(rows))
        filtered.setdefault("target_occurrence_count", _deduped_occurrence_count(rows))
        filtered.setdefault("collapsed_duplicate_record_count", max(0, _deduped_occurrence_count(rows) - len(rows)))
        return filtered

    raw_candidate_count = _to_int(retrieval.get("total_match_count"), 0)
    direct = [dict(row) for row in (retrieval.get("direct_evidence") or []) if _target_matches_value(target, str(row.get("normalized_value") or ""))]
    nearby = [dict(row) for row in (retrieval.get("nearby_context") or []) if _target_matches_value(target, str(row.get("normalized_value") or ""))]
    for idx, row in enumerate(direct, 1):
        row["citation_id"] = idx
    for idx, row in enumerate(nearby, len(direct) + 1):
        row["citation_id"] = idx

    rows = direct + nearby
    unique_count = len(rows)
    target_occurrence_count = _deduped_occurrence_count(rows)
    collapsed_duplicate_count = max(0, target_occurrence_count - unique_count)

    filtered = dict(retrieval)
    filtered["direct_evidence"] = direct
    filtered["nearby_context"] = nearby
    filtered["raw_candidate_match_count"] = raw_candidate_count
    filtered["target_unique_match_count"] = unique_count
    filtered["target_occurrence_count"] = target_occurrence_count
    filtered["collapsed_duplicate_record_count"] = collapsed_duplicate_count

    # Public match counts reflect exact target evidence, not broad fallback candidates.
    # This prevents missing exact values from showing noisy broad-match counts.
    filtered["total_match_count"] = target_occurrence_count
    filtered["returned_match_count"] = unique_count
    filtered["result_was_capped"] = False
    filtered["more_results_available"] = False
    filtered["high_degree_node_detected"] = False
    filtered["cap_reason"] = "not_capped"
    filtered["group_counts"] = {
        "by_field": dict(Counter(str(row.get("field_name")) for row in rows)),
        "by_page": dict(Counter(str(row.get("page_id")) for row in rows)),
    }
    return filtered

def _target_value(plan: Mapping[str, Any]) -> str:
    return str(plan.get("target_value") or "").strip()


def _direct_evidence(retrieval: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    rows = retrieval.get("direct_evidence") or []
    return [row for row in rows if isinstance(row, Mapping)]


def infer_response_mode(query: str, plan: Mapping[str, Any], retrieval: Mapping[str, Any]) -> str:
    """Classify how TRACE-Net should answer before any LLM call.

    The mode is intentionally conservative.  Any mode that can be rebuilt from
    direct source-truth evidence can skip the LLM.  Relationship/synthesis queries
    remain eligible for the LLM.
    """
    normalized = normalize_query(query)
    intent = str(plan.get("query_intent") or "")
    target = _target_value(plan)
    strict = bool(plan.get("strict_target_match_required"))
    direct_count = len(_direct_evidence(retrieval))
    capped = bool(retrieval.get("result_was_capped"))

    if "drill" in normalized or "show more" in normalized or "group by" in normalized or "by page" in normalized:
        if direct_count > 0:
            return "drilldown_request"
        if strict or target:
            return "exact_missing_value"
        return "relationship_or_synthesis_needs_llm"

    if strict or target:
        if direct_count > 0:
            return "exact_single_value"
        return "exact_missing_value"

    if intent in FIELD_LISTING_INTENTS and direct_count > 0:
        return "capped_listing" if capped else "field_listing"

    if "list" in normalized or "which pages" in normalized or "what pages" in normalized or "mention" in normalized:
        if direct_count > 0:
            return "capped_listing" if capped else "field_listing"

    return "relationship_or_synthesis_needs_llm"


def deterministic_mode_can_skip_llm(response_mode: str, deterministic_mode: str = "expanded") -> Tuple[bool, str]:
    if deterministic_mode in {"off", "disabled", "none"}:
        return False, "deterministic_planner_disabled"
    if deterministic_mode == "exact" and response_mode not in {"exact_single_value", "exact_missing_value"}:
        return False, "deterministic_exact_only_requires_llm"
    if response_mode in DETERMINISTIC_RESPONSE_MODES:
        return True, f"deterministic_{response_mode}_source_truth_ready"
    return False, "relationship_or_synthesis_requires_llm"


def _citation_fragment(row: Mapping[str, Any]) -> str:
    occ = f" occurrence_count={_occurrence_count(row)}" if _occurrence_count(row) > 1 else ""
    return f"{row.get('normalized_value')} [{row.get('citation_id')}]{occ}"


def build_drilldown_answer(query: str, plan: Mapping[str, Any], retrieval: Mapping[str, Any]) -> Tuple[str, Dict[str, Any]]:
    direct = _direct_evidence(retrieval)
    if not direct:
        return v25.build_final_answer(query, plan, retrieval)

    normalized = normalize_query(query)
    group_counts = retrieval.get("group_counts") if isinstance(retrieval.get("group_counts"), Mapping) else {}
    by_page = group_counts.get("by_page") if isinstance(group_counts.get("by_page"), Mapping) else {}
    by_field = group_counts.get("by_field") if isinstance(group_counts.get("by_field"), Mapping) else {}

    axis = "page"
    if "field" in normalized:
        axis = "field_type"
    elif "document" in normalized:
        axis = "document"
    elif "leiden" in normalized or "community" in normalized:
        axis = "leiden_community"

    if axis == "field_type" and by_field:
        groups = list(by_field.items())[:10]
    elif by_page:
        groups = list(by_page.items())[:10]
    else:
        groups = list(Counter(str(row.get("page_id")) for row in direct).items())[:10]

    examples = "; ".join(_citation_fragment(row) for row in direct[:10])
    group_text = "; ".join(f"{key}: {value}" for key, value in groups)
    field_names = sorted({str(row.get("field_name")) for row in direct if row.get("field_name")})
    answer = (
        f"TRACE-Net drill-down by {axis}: {group_text}. "
        f"Direct source-truth examples include {examples}."
    )
    if retrieval.get("result_was_capped"):
        answer += f" Results were capped: TRACE-Net returned {retrieval.get('returned_match_count')} of {retrieval.get('total_match_count')} matching records."
    drilldowns = retrieval.get("available_drilldowns") or []
    if drilldowns:
        answer += " Available drill-downs include " + ", ".join(str(x) for x in drilldowns[:6]) + "."

    return answer, {
        "answerable": True,
        "unsupported_claim_count": 0,
        "citation_like_count": v25.citation_like_count(answer),
        "response_mode": "drilldown_request",
        "drilldown_axis": axis,
        "drilldown_group_count": len(groups),
        "drilldown_fields": field_names,
    }


def build_deterministic_answer(query: str, plan: Mapping[str, Any], retrieval: Mapping[str, Any], response_mode: str) -> Tuple[str, Dict[str, Any]]:
    if response_mode == "drilldown_request":
        answer, meta = build_drilldown_answer(query, plan, retrieval)
        return _polish_answer_text(answer), meta

    direct = _direct_evidence(retrieval)
    if not direct:
        answer = (
            "TRACE-Net did not find direct citation-ready source-truth evidence for this query. "
            "No source-truth claim is made. Try narrowing by part number, manual reference, page, or table text."
        )
        return _polish_answer_text(answer), {
            "unsupported_claim_count": 0,
            "answerable": False,
            "citation_like_count": 0,
            "response_mode": response_mode,
        }

    intent = str(plan.get("query_intent") or "")
    target = _target_value(plan)
    raw_candidate_count = _to_int(retrieval.get("raw_candidate_match_count"), _to_int(retrieval.get("total_match_count"), 0))
    target_occurrence_count = _to_int(retrieval.get("target_occurrence_count"), _deduped_occurrence_count(direct))
    unique_count = _to_int(retrieval.get("target_unique_match_count"), len(direct) + len(retrieval.get("nearby_context") or []))
    collapsed_duplicate_count = _to_int(retrieval.get("collapsed_duplicate_record_count"), max(0, target_occurrence_count - unique_count))

    if intent == "part_number":
        row = direct[0]
        answer = (
            f"TRACE-Net found part number {target or row.get('normalized_value')} on page {row.get('page_id')} "
            f"as {row.get('field_name')} [{row.get('citation_id')}]. The available direct source-truth evidence confirms the listing, "
            "but it does not provide enough information to describe the part physically."
        )
    elif intent == "covered_part_number":
        pages = ", ".join(sorted(set(str(row.get("page_id")) for row in direct)))
        examples = "; ".join(_citation_fragment(row) for row in direct[:10])
        answer = f"TRACE-Net found covered part numbers on page(s) {pages}. Direct source-truth examples include {examples}."
    elif intent == "manual_page_reference":
        row = direct[0]
        dup = f" The same page/value was collapsed from {collapsed_duplicate_count} repeated source records." if collapsed_duplicate_count > 0 else ""
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

    if retrieval.get("result_was_capped"):
        answer += f" Results were capped: TRACE-Net returned {retrieval.get('returned_match_count')} of {retrieval.get('total_match_count')} matching records."
    elif raw_candidate_count and raw_candidate_count > max(target_occurrence_count, unique_count) and target_occurrence_count > 0:
        # Disclosure only: the strict target answer is exact, while broader candidate counts are retained for audit.
        answer += f" Strict target filtering was applied; raw candidate matches before filtering: {raw_candidate_count}."
    drilldowns = retrieval.get("available_drilldowns") or []
    if (retrieval.get("result_was_capped") or response_mode in {"capped_listing", "drilldown_request"}) and drilldowns:
        answer += " Available drill-downs include " + ", ".join(str(x) for x in drilldowns[:6]) + "."

    answer = _polish_answer_text(answer)
    meta = {
        "unsupported_claim_count": 0,
        "answerable": True,
        "citation_like_count": v25.citation_like_count(answer),
        "response_mode": response_mode,
        "raw_candidate_match_count": raw_candidate_count,
        "target_unique_match_count": unique_count,
        "target_occurrence_count": target_occurrence_count,
        "collapsed_duplicate_record_count": collapsed_duplicate_count,
    }
    return answer, meta

def standard_safety(response_is_final_gated: bool = True, llm_called: bool = False) -> Dict[str, Any]:
    base = v25.standard_safety(response_is_final_gated=response_is_final_gated, llm_called=llm_called)
    base["deterministic_planner_can_skip_llm"] = True
    base["drilldown_supported"] = True
    return base


def run_live_query_v28(
    query: str,
    state: Mapping[str, Any],
    llm_mode: Optional[str] = None,
    request_timeout: Optional[int] = None,
) -> Dict[str, Any]:
    total_start = _now()
    stage_timings_ms: Dict[str, float] = {}

    stage = _now()
    plan = detect_query_plan_v28(query)
    stage_timings_ms["query_planning_ms"] = _elapsed_ms(stage)

    stage = _now()
    retrieval = v25.retrieve_source_truth_evidence(
        state.get("exact_search_documents") or [],
        plan,
        query,
        top_k=_to_int(state.get("top_k"), 10),
    )
    retrieval = apply_strict_target_filter(plan, retrieval)
    stage_timings_ms["source_truth_retrieval_ms"] = _elapsed_ms(stage)

    stage = _now()
    guidance = v25.build_guidance(
        retrieval.get("direct_evidence") or [],
        state.get("page_summaries") or {},
        state.get("page_to_community") or {},
        state.get("community_to_pages") or {},
        max_pages_per_community=_to_int(state.get("max_pages_per_community"), 25),
    )
    stage_timings_ms["graph_summary_guidance_ms"] = _elapsed_ms(stage)

    stage = _now()
    response_mode = infer_response_mode(query, plan, retrieval)
    deterministic_skip, deterministic_reason = deterministic_mode_can_skip_llm(response_mode, str(state.get("deterministic_mode") or "expanded"))
    stage_timings_ms["deterministic_planner_ms"] = _elapsed_ms(stage)

    stage = _now()
    prompt_messages = v25.render_prompt(query, plan, retrieval, guidance)
    stage_timings_ms["context_prompt_pack_ms"] = _elapsed_ms(stage)

    mode = llm_mode or str(state.get("llm_mode") or "simulate")
    draft = ""
    llm_status = "LLM_NOT_CALLED"
    llm_metadata: Dict[str, Any] = {}
    error = ""
    llm_called = False

    stage = _now()
    if deterministic_skip:
        draft = "TRACE-Net deterministic planner used; final answer is rebuilt from direct source-truth evidence or audit-only no-evidence state."
        llm_status = "LLM_SKIPPED_DETERMINISTIC_PLANNER"
        llm_metadata = {"deterministic_reason": deterministic_reason, "response_mode": response_mode}
        stage_timings_ms["llm_draft_ms"] = _elapsed_ms(stage)
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
                llm_status = "LLM_CALL_SUCCEEDED"
            else:
                draft = v25.simulate_llm_draft(query, retrieval)
                llm_status = "LLM_SIMULATED"
        except Exception as exc:
            error = str(exc)
            draft = v25.simulate_llm_draft(query, retrieval)
            llm_status = "LLM_CALL_FAILED_SIMULATED_FALLBACK"
            llm_metadata = {"error": error}
        stage_timings_ms["llm_draft_ms"] = _elapsed_ms(stage)

    stage = _now()
    if deterministic_skip:
        final_answer, final_meta = build_deterministic_answer(query, plan, retrieval, response_mode)
    else:
        final_answer, final_meta = v25.build_final_answer(query, plan, retrieval)
        final_answer = _polish_answer_text(final_answer)
        final_meta = dict(final_meta)
        final_meta["response_mode"] = response_mode
    stage_timings_ms["final_gate_ms"] = _elapsed_ms(stage)

    total_latency_ms = _elapsed_ms(total_start)
    stage_timings_ms["total_request_ms"] = total_latency_ms
    non_llm_ms = round(total_latency_ms - float(stage_timings_ms.get("llm_draft_ms", 0.0)), 3)
    answerable = bool(final_meta.get("answerable"))

    return {
        "user_query": query,
        "query_plan": plan,
        "response_mode": response_mode,
        "deterministic_answer_planner_used": deterministic_skip,
        "deterministic_answer_reason": deterministic_reason,
        "retrieval": retrieval,
        "guidance": guidance,
        "prompt_message_count": len(prompt_messages),
        "llm_mode": mode,
        "llm_status": llm_status,
        "llm_draft_text": draft,
        "llm_metadata": llm_metadata,
        "llm_error": error,
        "llm_called": llm_called,
        "stage_timings_ms": stage_timings_ms,
        "latency_summary": {
            "total_request_ms": total_latency_ms,
            "llm_draft_ms": stage_timings_ms.get("llm_draft_ms", 0.0),
            "non_llm_ms": non_llm_ms,
            "stage_timing_sum_ms": _sum_timing({k: v for k, v in stage_timings_ms.items() if k != "total_request_ms"}),
        },
        "final_gate_status": "LIVE_ORCHESTRATOR_FINAL_GATE_PASS" if answerable else "LIVE_ORCHESTRATOR_AUDIT_ONLY",
        "final_answer": final_answer,
        "final_answer_ready_for_webui": answerable,
        "unsupported_claim_count": final_meta.get("unsupported_claim_count", 0),
        "citation_like_count": final_meta.get("citation_like_count", 0),
        "cap_disclosure_required": bool(retrieval.get("result_was_capped")),
        "cap_disclosure_in_final_answer": "Results were capped" in final_answer,
        "drilldown_axis": final_meta.get("drilldown_axis"),
        "drilldown_group_count": final_meta.get("drilldown_group_count", 0),
        "raw_candidate_match_count": retrieval.get("raw_candidate_match_count"),
        "target_unique_match_count": retrieval.get("target_unique_match_count"),
        "target_occurrence_count": retrieval.get("target_occurrence_count"),
        "collapsed_duplicate_record_count": retrieval.get("collapsed_duplicate_record_count"),
        "safety": standard_safety(response_is_final_gated=answerable, llm_called=llm_called),
    }


def build_state(
    table_exact_search_adapter_path: Path,
    output_dir: Optional[Path] = None,
    page_context_v2_path: Optional[Path] = None,
    leiden_communities_path: Optional[Path] = None,
    host: str = "127.0.0.1",
    port: int = 8023,
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
    include_standard_demo_queries: bool = False,
) -> Dict[str, Any]:
    docs = v25.load_exact_docs(table_exact_search_adapter_path)
    page_summaries = v25.load_optional_page_summaries(page_context_v2_path)
    page_to_community, community_to_pages = v25.load_optional_leiden(leiden_communities_path)
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
        "deterministic_mode": deterministic_mode,
        "exact_search_documents": docs,
        "page_summaries": page_summaries,
        "page_to_community": page_to_community,
        "community_to_pages": community_to_pages,
        "contract": {
            "stage_timing_enabled": True,
            "expanded_deterministic_answer_planner_enabled": deterministic_mode not in {"off", "disabled", "none"},
            "drilldown_supported": True,
            "llm_reserved_for_relationship_or_synthesis": True,
            "llm_output_is_draft_only": True,
            "final_answer_rebuilt_from_source_truth": True,
            "source_truth_evidence_required_for_final_claims": True,
            "graph_leiden_guidance_only": True,
            "v2_summaries_guidance_only": True,
            "raw_5tb_scan_at_query_time": False,
            "graph_rebuild_at_query_time": False,
            "source_truth_mutation_allowed": False,
            "answer_permission": False,
        },
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
    }
    if include_standard_demo_queries:
        samples = [run_live_query_v28(q, state, llm_mode=llm_mode, request_timeout=request_timeout) for q in DEFAULT_SAMPLE_QUERIES]
        state["sample_results"] = samples
        state["sample_query_count"] = len(samples)
        state["sample_success_count"] = sum(1 for r in samples if r.get("final_gate_status") in {"LIVE_ORCHESTRATOR_FINAL_GATE_PASS", "LIVE_ORCHESTRATOR_AUDIT_ONLY"})
        state["stage_timing_record_count"] = sum(1 for r in samples if isinstance(r.get("stage_timings_ms"), Mapping) and r["stage_timings_ms"].get("total_request_ms") is not None)
        state["deterministic_answer_sample_count"] = sum(1 for r in samples if r.get("deterministic_answer_planner_used"))
        state["drilldown_sample_count"] = sum(1 for r in samples if r.get("response_mode") == "drilldown_request")
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
            "deterministic_answer_sample_count": 0,
            "drilldown_sample_count": 0,
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
    min_deterministic_answer_samples: int = 0,
    min_drilldown_samples: int = 0,
    max_sample_llm_calls: Optional[int] = None,
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
        ("deterministic_answer_sample_count", state.get("deterministic_answer_sample_count", 0), ">=", min_deterministic_answer_samples),
        ("drilldown_sample_count", state.get("drilldown_sample_count", 0), ">=", min_drilldown_samples),
        ("answer_permission_count", state.get("answer_permission_count", 0), "<=", max_answer_permission_count),
        ("source_truth_mutation_allowed_count", state.get("source_truth_mutation_allowed_count", 0), "<=", max_source_truth_mutation_allowed),
        ("contract_raw_5tb_scan_at_query_time", state.get("contract", {}).get("raw_5tb_scan_at_query_time"), "is", False),
        ("contract_graph_rebuild_at_query_time", state.get("contract", {}).get("graph_rebuild_at_query_time"), "is", False),
        ("contract_final_answer_rebuilt_from_source_truth", state.get("contract", {}).get("final_answer_rebuilt_from_source_truth"), "is", True),
        ("contract_drilldown_supported", state.get("contract", {}).get("drilldown_supported"), "is", True),
    ]
    if max_sample_llm_calls is not None:
        checks.append(("llm_called_sample_count", state.get("llm_called_sample_count", 0), "<=", max_sample_llm_calls))
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
    out = dict(state)
    out["exact_search_documents"] = list(state.get("exact_search_documents") or [])[:25]
    out["page_summaries"] = {k: state.get("page_summaries", {}).get(k) for k in list((state.get("page_summaries") or {}).keys())[:25]}
    out["page_to_community"] = {k: state.get("page_to_community", {}).get(k) for k in list((state.get("page_to_community") or {}).keys())[:25]}
    out["community_to_pages"] = {k: list(v)[:10] for k, v in list((state.get("community_to_pages") or {}).items())[:25]}
    return out


def render_markdown_report(state: Mapping[str, Any]) -> str:
    lines = [
        "# TRACE-Net E2E Live Deterministic Answer Planner + Drilldown v28",
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
        "deterministic_answer_sample_count",
        "drilldown_sample_count",
        "llm_called_sample_count",
        "sample_avg_latency_ms",
        "sample_avg_llm_ms",
        "deterministic_mode",
        "response_mode_counts",
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
        "- Expanded deterministic answer planner may skip the LLM for exact values, field listings, capped listings, and drill-down requests.",
        "- Relationship/synthesis questions remain eligible for the LLM.",
        "- Final answers are rebuilt/gated from direct source-truth evidence.",
        "- Graph/Leiden, v2 summaries, nearby OCR, and aggregation metadata remain guidance/disclosure only.",
        "- The endpoint reads prebuilt artifacts and does not scan raw 5TB data or rebuild the graph.",
        "",
        "## Sample query results",
    ])
    for result in state.get("sample_results", []):
        latency = result.get("latency_summary") or {}
        lines.append(f"### {result.get('user_query')}")
        lines.append(f"- response_mode: {result.get('response_mode')}")
        lines.append(f"- final_gate_status: {result.get('final_gate_status')}")
        lines.append(f"- llm_status: {result.get('llm_status')}")
        lines.append(f"- deterministic_answer_planner_used: {result.get('deterministic_answer_planner_used')}")
        lines.append(f"- deterministic_answer_reason: {result.get('deterministic_answer_reason')}")
        lines.append(f"- total_request_ms: {latency.get('total_request_ms')}")
        lines.append(f"- llm_draft_ms: {latency.get('llm_draft_ms')}")
        if result.get("raw_candidate_match_count") is not None:
            lines.append(f"- raw_candidate_match_count: {result.get('raw_candidate_match_count')}")
            lines.append(f"- target_unique_match_count: {result.get('target_unique_match_count')}")
            lines.append(f"- target_occurrence_count: {result.get('target_occurrence_count')}")
            lines.append(f"- collapsed_duplicate_record_count: {result.get('collapsed_duplicate_record_count')}")
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
    report_path = output_dir / "trace_net_e2e_live_deterministic_answer_planner_v28.json"
    sample_jsonl_path = output_dir / "trace_net_e2e_live_deterministic_answer_planner_samples_v28.jsonl"
    inspect_md_path = output_dir / "trace_net_e2e_live_deterministic_answer_planner_v28.md"
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
        "deterministic_mode": state.get("deterministic_mode"),
        "safety": standard_safety(response_is_final_gated=True, llm_called=False),
    }


def chat_completion_response(state: Mapping[str, Any], request_payload: Mapping[str, Any]) -> Dict[str, Any]:
    query = v25.extract_user_message(request_payload.get("messages"))
    result = run_live_query_v28(query, state)
    return {
        "id": "chatcmpl-tracenet-v28-" + uuid.uuid4().hex[:16],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": state.get("model_id", MODEL_ID),
        "choices": [{"index": 0, "message": {"role": "assistant", "content": result["final_answer"]}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "trace_net": {
            "endpoint_version": "live_deterministic_answer_planner_v28",
            "query_intent": result.get("query_plan", {}).get("query_intent"),
            "response_mode": result.get("response_mode"),
            "llm_status": result.get("llm_status"),
            "llm_mode": result.get("llm_mode"),
            "llm_called": result.get("llm_called"),
            "deterministic_answer_planner_used": result.get("deterministic_answer_planner_used"),
            "deterministic_answer_reason": result.get("deterministic_answer_reason"),
            "final_gate_status": result.get("final_gate_status"),
            "citation_like_count": result.get("citation_like_count"),
            "total_match_count": result.get("retrieval", {}).get("total_match_count"),
            "returned_match_count": result.get("retrieval", {}).get("returned_match_count"),
            "result_was_capped": result.get("retrieval", {}).get("result_was_capped"),
            "raw_candidate_match_count": result.get("raw_candidate_match_count"),
            "target_unique_match_count": result.get("target_unique_match_count"),
            "target_occurrence_count": result.get("target_occurrence_count"),
            "collapsed_duplicate_record_count": result.get("collapsed_duplicate_record_count"),
            "drilldown_axis": result.get("drilldown_axis"),
            "drilldown_group_count": result.get("drilldown_group_count"),
            "stage_timings_ms": result.get("stage_timings_ms"),
            "latency_summary": result.get("latency_summary"),
            "safety": result.get("safety"),
        },
    }


class TraceNetV28Handler(BaseHTTPRequestHandler):
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
    TraceNetV28Handler.state = state
    server = HTTPServer((host, port), TraceNetV28Handler)
    print(f"TRACE-Net v28 serving {state.get('model_id', MODEL_ID)} at http://{host}:{port}/v1", flush=True)
    server.serve_forever()
