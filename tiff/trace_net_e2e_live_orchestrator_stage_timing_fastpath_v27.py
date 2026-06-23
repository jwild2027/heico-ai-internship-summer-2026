"""TRACE-Net E2E Live Orchestrator Stage Timing + Fast Path v27.

This module wraps the v25 live orchestrator with two production-facing additions:

1. Stage timing telemetry for query planning, retrieval, graph/v2 guidance,
   prompt packing, LLM draft generation, and final-gate repair.
2. A deterministic fast path for simple exact lookups and audit-only misses.

The fast path is intentionally conservative. It skips the local LLM only when the
retrieved direct source-truth evidence is already enough to build the final gated
answer, or when a strict exact lookup has zero direct evidence and must return an
audit-only answer. Graph/Leiden and v2 summaries remain guidance only. The module
never scans raw 5TB source data, rebuilds graph artifacts, reruns OCR, mutates
source truth, or writes to Postgres/Qdrant/OpenSearch.
"""
from __future__ import annotations

import json
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from tiff import trace_net_e2e_live_orchestrator_endpoint_v25 as v25

MODULE = "trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27"
VERSION = "v27"
MODEL_ID = "trace-net-e2e-live-orchestrator-fastpath-gemma-v27"
STATUS_READY = "E2E_LIVE_ORCHESTRATOR_STAGE_TIMING_FASTPATH_READY"
STATUS_NEEDS_REPAIR = "E2E_LIVE_ORCHESTRATOR_STAGE_TIMING_FASTPATH_NEEDS_REPAIR"
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
]
FAST_PATH_INTENTS = {"part_number", "manual_page_reference", "table_text"}


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


def _to_bool(value: Any) -> bool:
    return v25._to_bool(value)


def _sum_timing(stage_timings_ms: Mapping[str, Any]) -> float:
    total = 0.0
    for value in stage_timings_ms.values():
        try:
            total += float(value)
        except Exception:
            continue
    return round(total, 3)


def should_use_fast_path(plan: Mapping[str, Any], retrieval: Mapping[str, Any], fast_path_mode: str = "exact") -> Tuple[bool, str]:
    """Decide whether v27 can skip the LLM for this request.

    Conservative policy:
    - Only exact/strict intents are eligible by default.
    - If direct source-truth exists, final answer can be deterministically gated.
    - If strict exact target lookup has no direct evidence, return audit-only without
      paying an LLM latency cost.
    - Broad inventory/relationship questions are left to the LLM unless a later
      phase explicitly allows a broader deterministic mode.
    """
    if fast_path_mode in {"off", "disabled", "none"}:
        return False, "fast_path_disabled"
    intent = str(plan.get("query_intent") or "")
    strict = bool(plan.get("strict_target_match_required"))
    direct_count = len(retrieval.get("direct_evidence") or [])
    if fast_path_mode == "all_direct" and direct_count > 0:
        return True, "direct_source_truth_answer_ready"
    if intent in FAST_PATH_INTENTS and strict:
        if direct_count > 0:
            return True, "exact_lookup_direct_source_truth_answer_ready"
        return True, "strict_exact_lookup_audit_only_no_evidence"
    return False, "requires_llm_for_non_exact_or_broad_query"


def run_live_query_v27(
    query: str,
    state: Mapping[str, Any],
    llm_mode: Optional[str] = None,
    request_timeout: Optional[int] = None,
) -> Dict[str, Any]:
    total_start = _now()
    stage_timings_ms: Dict[str, float] = {}

    stage = _now()
    plan = v25.detect_query_plan(query)
    stage_timings_ms["query_planning_ms"] = _elapsed_ms(stage)

    stage = _now()
    retrieval = v25.retrieve_source_truth_evidence(
        state.get("exact_search_documents") or [],
        plan,
        query,
        top_k=_to_int(state.get("top_k"), 10),
    )
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
    prompt_messages = v25.render_prompt(query, plan, retrieval, guidance)
    stage_timings_ms["context_prompt_pack_ms"] = _elapsed_ms(stage)

    stage = _now()
    fast_path_used, fast_path_reason = should_use_fast_path(plan, retrieval, str(state.get("fast_path_mode") or "exact"))
    stage_timings_ms["fast_path_decision_ms"] = _elapsed_ms(stage)

    mode = llm_mode or str(state.get("llm_mode") or "simulate")
    draft = ""
    llm_status = "LLM_NOT_CALLED"
    llm_metadata: Dict[str, Any] = {}
    error = ""
    llm_called = False

    stage = _now()
    if fast_path_used:
        draft = "TRACE-Net deterministic fast path used; final answer is rebuilt from direct source-truth evidence or audit-only no-evidence state."
        llm_status = "LLM_SKIPPED_FAST_PATH"
        llm_metadata = {"fast_path_reason": fast_path_reason}
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
    final_answer, final_meta = v25.build_final_answer(query, plan, retrieval)
    stage_timings_ms["final_gate_ms"] = _elapsed_ms(stage)

    total_latency_ms = _elapsed_ms(total_start)
    stage_timings_ms["total_request_ms"] = total_latency_ms
    non_llm_ms = round(total_latency_ms - float(stage_timings_ms.get("llm_draft_ms", 0.0)), 3)

    answerable = bool(final_meta["answerable"])
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
        "llm_error": error,
        "fast_path_used": fast_path_used,
        "fast_path_reason": fast_path_reason,
        "llm_called": llm_called,
        "llm_skipped_by_fast_path": bool(fast_path_used),
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
        "unsupported_claim_count": final_meta["unsupported_claim_count"],
        "citation_like_count": final_meta["citation_like_count"],
        "cap_disclosure_required": bool(retrieval.get("result_was_capped")),
        "cap_disclosure_in_final_answer": "Results were capped" in final_answer,
        "safety": standard_safety(response_is_final_gated=answerable, llm_called=llm_called),
    }


def standard_safety(response_is_final_gated: bool = True, llm_called: bool = False) -> Dict[str, Any]:
    base = v25.standard_safety(response_is_final_gated=response_is_final_gated, llm_called=llm_called)
    base["fast_path_can_skip_llm"] = True
    return base


def build_state(
    table_exact_search_adapter_path: Path,
    output_dir: Optional[Path] = None,
    page_context_v2_path: Optional[Path] = None,
    leiden_communities_path: Optional[Path] = None,
    host: str = "127.0.0.1",
    port: int = 8022,
    model_id: str = MODEL_ID,
    llm_mode: str = "simulate",
    llm_base_url: str = "http://127.0.0.1:11434/v1",
    llm_model: str = "gemma4:26b",
    llm_api_key: str = "ollama",
    temperature: float = 0.0,
    request_timeout: int = 240,
    top_k: int = 10,
    max_pages_per_community: int = 25,
    fast_path_mode: str = "exact",
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
        "fast_path_mode": fast_path_mode,
        "exact_search_documents": docs,
        "page_summaries": page_summaries,
        "page_to_community": page_to_community,
        "community_to_pages": community_to_pages,
        "contract": {
            "stage_timing_enabled": True,
            "deterministic_fast_path_enabled": fast_path_mode not in {"off", "disabled", "none"},
            "fast_path_skips_llm_only_for_strict_exact_or_direct_source_truth": True,
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
        samples = [run_live_query_v27(q, state, llm_mode=llm_mode, request_timeout=request_timeout) for q in DEFAULT_SAMPLE_QUERIES]
        state["sample_results"] = samples
        state["sample_query_count"] = len(samples)
        state["sample_success_count"] = sum(1 for r in samples if r.get("final_gate_status") in {"LIVE_ORCHESTRATOR_FINAL_GATE_PASS", "LIVE_ORCHESTRATOR_AUDIT_ONLY"})
        state["stage_timing_record_count"] = sum(1 for r in samples if isinstance(r.get("stage_timings_ms"), Mapping) and r["stage_timings_ms"].get("total_request_ms") is not None)
        state["fast_path_sample_count"] = sum(1 for r in samples if r.get("fast_path_used"))
        state["llm_called_sample_count"] = sum(1 for r in samples if r.get("llm_called"))
        state["sample_total_latency_ms"] = round(sum(float((r.get("latency_summary") or {}).get("total_request_ms") or 0.0) for r in samples), 3)
        state["sample_avg_latency_ms"] = round(state["sample_total_latency_ms"] / len(samples), 3) if samples else 0.0
        state["sample_avg_llm_ms"] = round(sum(float((r.get("latency_summary") or {}).get("llm_draft_ms") or 0.0) for r in samples) / len(samples), 3) if samples else 0.0
    else:
        state.update({
            "sample_results": [],
            "sample_query_count": 0,
            "sample_success_count": 0,
            "stage_timing_record_count": 0,
            "fast_path_sample_count": 0,
            "llm_called_sample_count": 0,
            "sample_total_latency_ms": 0.0,
            "sample_avg_latency_ms": 0.0,
            "sample_avg_llm_ms": 0.0,
        })
    return state


def evaluate_quality(
    state: Mapping[str, Any],
    min_exact_search_documents: int = 10,
    min_endpoint_routes: int = 4,
    min_sample_queries: int = 0,
    min_sample_successes: int = 0,
    min_stage_timing_records: int = 0,
    min_fast_path_samples: int = 0,
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
        ("fast_path_sample_count", state.get("fast_path_sample_count", 0), ">=", min_fast_path_samples),
        ("answer_permission_count", state.get("answer_permission_count", 0), "<=", max_answer_permission_count),
        ("source_truth_mutation_allowed_count", state.get("source_truth_mutation_allowed_count", 0), "<=", max_source_truth_mutation_allowed),
        ("contract_raw_5tb_scan_at_query_time", state.get("contract", {}).get("raw_5tb_scan_at_query_time"), "is", False),
        ("contract_graph_rebuild_at_query_time", state.get("contract", {}).get("graph_rebuild_at_query_time"), "is", False),
        ("contract_final_answer_rebuilt_from_source_truth", state.get("contract", {}).get("final_answer_rebuilt_from_source_truth"), "is", True),
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
        "# TRACE-Net E2E Live Orchestrator Stage Timing + Fast Path v27",
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
        "fast_path_sample_count",
        "llm_called_sample_count",
        "sample_avg_latency_ms",
        "sample_avg_llm_ms",
        "fast_path_mode",
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
        "- Stage timings are attached to each live response.",
        "- Deterministic fast path may skip the LLM for strict exact lookups and audit-only exact misses.",
        "- LLM output remains draft only; final answers are rebuilt/gated from direct source-truth evidence.",
        "- Graph/Leiden and v2 summaries remain guidance only.",
        "- The endpoint reads prebuilt artifacts and does not scan raw 5TB data or rebuild the graph.",
        "",
        "## Sample query results",
    ])
    for result in state.get("sample_results", []):
        latency = result.get("latency_summary") or {}
        lines.append(f"### {result.get('user_query')}")
        lines.append(f"- final_gate_status: {result.get('final_gate_status')}")
        lines.append(f"- llm_status: {result.get('llm_status')}")
        lines.append(f"- fast_path_used: {result.get('fast_path_used')} ({result.get('fast_path_reason')})")
        lines.append(f"- total_request_ms: {latency.get('total_request_ms')}")
        lines.append(f"- llm_draft_ms: {latency.get('llm_draft_ms')}")
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
    report_path = output_dir / "trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27.json"
    sample_jsonl_path = output_dir / "trace_net_e2e_live_orchestrator_stage_timing_fastpath_samples_v27.jsonl"
    inspect_md_path = output_dir / "trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27.md"
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
        "fast_path_mode": state.get("fast_path_mode"),
        "safety": standard_safety(response_is_final_gated=True, llm_called=False),
    }


def chat_completion_response(state: Mapping[str, Any], request_payload: Mapping[str, Any]) -> Dict[str, Any]:
    query = v25.extract_user_message(request_payload.get("messages"))
    result = run_live_query_v27(query, state)
    return {
        "id": "chatcmpl-tracenet-v27-" + uuid.uuid4().hex[:16],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": state.get("model_id", MODEL_ID),
        "choices": [{"index": 0, "message": {"role": "assistant", "content": result["final_answer"]}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "trace_net": {
            "endpoint_version": "live_orchestrator_stage_timing_fastpath_v27",
            "query_intent": result.get("query_plan", {}).get("query_intent"),
            "llm_status": result.get("llm_status"),
            "llm_mode": result.get("llm_mode"),
            "llm_called": result.get("llm_called"),
            "fast_path_used": result.get("fast_path_used"),
            "fast_path_reason": result.get("fast_path_reason"),
            "final_gate_status": result.get("final_gate_status"),
            "citation_like_count": result.get("citation_like_count"),
            "total_match_count": result.get("retrieval", {}).get("total_match_count"),
            "returned_match_count": result.get("retrieval", {}).get("returned_match_count"),
            "result_was_capped": result.get("retrieval", {}).get("result_was_capped"),
            "stage_timings_ms": result.get("stage_timings_ms"),
            "latency_summary": result.get("latency_summary"),
            "safety": result.get("safety"),
        },
    }


class TraceNetV27Handler(BaseHTTPRequestHandler):
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
    TraceNetV27Handler.state = state
    server = HTTPServer((host, port), TraceNetV27Handler)
    print(f"TRACE-Net v27 serving {state.get('model_id', MODEL_ID)} at http://{host}:{port}/v1", flush=True)
    server.serve_forever()
