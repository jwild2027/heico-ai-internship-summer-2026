"""TRACE-Net E2E Tool Usage Audit v1.

Runs one OpenAI-compatible TRACE-Net/WebUI question (or audits a saved response)
and writes a checklist showing which evidence/tool routes were actually visible in
that answer versus merely available on disk.

Safety:
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

MODULE_VERSION = "trace_net_e2e_tool_usage_audit_v1"
REPORT_NAME = "trace_net_e2e_tool_usage_audit_v1.json"
DEFAULT_MODEL_ID = "trace-net-engineering-webui-v1"
DEFAULT_ENDPOINT_URL = "http://127.0.0.1:8044/v1/chat/completions"

STATUS_USED = "used"
STATUS_AVAILABLE_NOT_USED = "available_not_used"
STATUS_NOT_AVAILABLE_NOT_USED = "not_available_not_used"
STATUS_UNKNOWN = "unknown"

TOOL_ORDER = [
    "webui_endpoint",
    "gemma_llm",
    "ocr_fishnet",
    "page_context_v2",
    "route_dispatch",
    "table_route",
    "embedding_vector",
    "graph_leiden",
    "visual_image_route",
    "self_rag",
    "crag_retry",
    "final_gate",
]

DEFAULT_ARTIFACT_PATHS: Dict[str, List[str]] = {
    "ocr_fishnet": [
        "local_data/organization/trace_net/fishnet_ocr_grid/trace_net_fishnet_ocr_grid_v1.json",
    ],
    "page_context_v2": [
        "local_data/organization/trace_net/page_context_v2/trace_net_page_context_v2.json",
    ],
    "route_dispatch": [
        "local_data/organization/trace_net/fishnet_route_dispatch_handoff/trace_net_fishnet_route_dispatch_handoff_v1.json",
        "local_data/organization/trace_net/fishnet_accepted_route_manifest/trace_net_fishnet_accepted_route_manifest_v1.json",
    ],
    "table_route": [
        "local_data/organization/trace_net/table_exact_search_adapter/trace_net_table_exact_search_adapter_v1.json",
        "local_data/organization/trace_net/table_route_evidence_packager/trace_net_table_route_evidence_packager_v1.json",
        "local_data/organization/trace_net/table_route_value_audit/trace_net_table_route_value_audit_v1.json",
    ],
    "embedding_vector": [
        "local_data/organization/trace_net/hybrid_retrieval_v3/trace_net_hybrid_retrieval_v3.json",
        "local_data/organization/trace_net/vector_retrieval/trace_net_vector_retrieval_v1.json",
        "local_data/organization/trace_net/qdrant_adapter/trace_net_qdrant_adapter_v1.json",
    ],
    "graph_leiden": [
        "local_data/organization/trace_net/leiden_communities/trace_net_leiden_communities_v1.json",
        "local_data/organization/trace_net/community_aware_retrieval/trace_net_community_aware_retrieval_v1.json",
    ],
    "visual_image_route": [
        "local_data/organization/trace_net/image_visual_observer/trace_net_image_visual_observer_v1.json",
        "local_data/organization/trace_net/callout_visual_part_verifier/trace_net_callout_visual_part_verifier_v1.json",
        "local_data/organization/trace_net/visual_ink_layout_calibrator/trace_net_visual_ink_layout_calibrator_v1.json",
    ],
    "self_rag": [
        "local_data/organization/trace_net/engineering_context_self_rag_check/trace_net_engineering_context_self_rag_check_v1.json",
    ],
    "crag_retry": [
        "local_data/organization/trace_net/engineering_context_crag_retry_plan/trace_net_engineering_context_crag_retry_plan_v1.json",
    ],
    "final_gate": [
        "local_data/organization/trace_net/engineering_draft_final_gate_retry_micro/trace_net_engineering_draft_final_gate_v1.json",
        "local_data/organization/trace_net/engineering_draft_final_gate/trace_net_engineering_draft_final_gate_v1.json",
    ],
}

KEYWORD_SIGNALS: Dict[str, List[str]] = {
    "ocr_fishnet": ["ocr", "fishnet", "word_box", "page_context_v2_or_fishnet", "router_classifier_input_only"],
    "page_context_v2": ["page_context_v2", "page_context_v2_or_fishnet", "v2_summary", "page_summary"],
    "route_dispatch": ["route_dispatch", "route_handoff", "accepted_route", "route="],
    "table_route": ["table_route", "table_exact", "table evidence", "table", "covered_part_number", "ipl_part_number"],
    "embedding_vector": ["embedding", "vector", "qdrant", "hybrid", "semantic", "similarity"],
    "graph_leiden": ["graph", "leiden", "community", "graph_community", "community_aware"],
    "visual_image_route": ["image_visual", "visual", "callout", "figure", "diagram", "illustrated"],
    "self_rag": ["self_rag", "self-rag", "evidence check", "self rag"],
    "crag_retry": ["crag", "retry_plan", "retry action", "context_crag"],
    "final_gate": ["final_gate", "manual_review_ready", "source_runner_record_id", "source_draft_packet_id"],
}


@dataclass(frozen=True)
class AuditConfig:
    endpoint_url: str = DEFAULT_ENDPOINT_URL
    model: str = DEFAULT_MODEL_ID
    api_key: str = ""
    request_timeout: int = 300


def _read_json(path: Path, *, required: bool = False) -> Dict[str, Any]:
    if not path.exists():
        if required:
            raise FileNotFoundError(f"missing JSON file: {path}")
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _clean(text: Any, *, max_chars: int = 5000) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())[:max_chars]


def _flatten_for_search(value: Any, *, max_chars: int = 90000) -> str:
    parts: List[str] = []

    def walk(v: Any) -> None:
        if sum(len(p) for p in parts) >= max_chars:
            return
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, Mapping):
            for key, child in v.items():
                if key in {"embedding", "vector", "pixels", "image_bytes", "raw_image"}:
                    parts.append(str(key))
                    continue
                parts.append(str(key))
                walk(child)
        elif isinstance(v, list):
            for item in v[:80]:
                walk(item)
        elif isinstance(v, (int, float, bool)) or v is None:
            parts.append(str(v))

    walk(value)
    return _clean(" ".join(parts), max_chars=max_chars).lower()


def _records_from_payload(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    for key in ["records", "pages", "page_records", "items", "documents", "workbench_cards", "policy_records", "tool_checklist"]:
        value = payload.get(key)
        if isinstance(value, list):
            return [dict(v) for v in value if isinstance(v, dict)]
    return []


def _artifact_availability(extra_artifact_paths: Optional[Mapping[str, Sequence[str]]] = None) -> Dict[str, Dict[str, Any]]:
    merged: Dict[str, List[str]] = {k: list(v) for k, v in DEFAULT_ARTIFACT_PATHS.items()}
    for tool, paths in (extra_artifact_paths or {}).items():
        merged.setdefault(tool, [])
        merged[tool].extend(str(p) for p in paths)
    out: Dict[str, Dict[str, Any]] = {}
    for tool in TOOL_ORDER:
        paths = merged.get(tool, [])
        existing = [p for p in paths if Path(p).exists()]
        out[tool] = {
            "available": bool(existing) if paths else None,
            "existing_paths": existing,
            "checked_paths": paths,
        }
    return out


def _post_question(config: AuditConfig, question: str) -> Dict[str, Any]:
    payload = {
        "model": config.model,
        "messages": [{"role": "user", "content": question}],
        "stream": False,
    }
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    req = urllib.request.Request(
        config.endpoint_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=config.request_timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _extract_assistant_text(response: Mapping[str, Any]) -> str:
    choices = response.get("choices") or []
    if choices and isinstance(choices[0], Mapping):
        msg = choices[0].get("message") or {}
        if isinstance(msg, Mapping):
            return str(msg.get("content") or "")
        if choices[0].get("text"):
            return str(choices[0].get("text") or "")
    return str(response.get("response_text") or response.get("answer") or "")


def _trace_payload(response: Mapping[str, Any]) -> Dict[str, Any]:
    trace = response.get("trace_net")
    if isinstance(trace, Mapping):
        return dict(trace)
    return {}


def _citations(trace: Mapping[str, Any], response: Mapping[str, Any]) -> List[Dict[str, Any]]:
    for owner in (trace, response):
        c = owner.get("citations") if isinstance(owner, Mapping) else None
        if isinstance(c, list):
            return [dict(x) for x in c if isinstance(x, Mapping)]
    return []


def _contains_any(haystack: str, needles: Iterable[str]) -> Optional[str]:
    for needle in needles:
        n = needle.lower()
        if n and n in haystack:
            return needle
    return None


def _tool_status(
    tool: str,
    *,
    response: Mapping[str, Any],
    artifact_info: Mapping[str, Any],
    response_search_text: str,
    citations: Sequence[Mapping[str, Any]],
) -> Tuple[str, str, List[str]]:
    trace = _trace_payload(response)
    reasons: List[str] = []

    if tool == "webui_endpoint":
        if response.get("choices") or trace:
            return STATUS_USED, "OpenAI-compatible response returned choices and/or trace_net payload.", ["response_received"]
        return STATUS_UNKNOWN, "No choices or trace_net payload were visible in the response.", []

    if tool == "gemma_llm":
        if trace.get("llm_called") is True:
            return STATUS_USED, f"trace_net.llm_called=true; model={trace.get('llm_model')!r}.", ["llm_called"]
        if trace.get("llm_model") or "gemma" in response_search_text:
            return STATUS_USED, "LLM model signal was visible in trace/text.", ["llm_model"]
        return STATUS_NOT_AVAILABLE_NOT_USED, "No llm_called or model signal was visible for this answer.", []

    if tool == "route_dispatch":
        known_routes = []
        for c in citations:
            route = str(c.get("route") or "").strip()
            if route and route.lower() != "unknown":
                known_routes.append(route)
        if known_routes:
            return STATUS_USED, f"Citation route metadata was present: {sorted(set(known_routes))}.", ["citation_route"]

    if tool == "table_route":
        for c in citations:
            if str(c.get("route") or "").lower() == "table":
                return STATUS_USED, "A citation had route=table.", ["route=table"]

    if tool == "visual_image_route":
        for c in citations:
            if str(c.get("route") or "").lower() == "image_visual":
                return STATUS_USED, "A citation had route=image_visual.", ["route=image_visual"]

    if tool == "final_gate":
        if any("final_gate" in str(c).lower() for c in citations):
            return STATUS_USED, "A citation referenced a final_gate record.", ["final_gate_citation"]
        kind = str(trace.get("response_kind") or "").lower()
        if "gated" in kind or "manual_review" in kind or "final_gate" in kind:
            return STATUS_USED, f"response_kind={trace.get('response_kind')!r} indicates gated/final-gate evidence.", ["response_kind"]

    hit = _contains_any(response_search_text, KEYWORD_SIGNALS.get(tool, []))
    if hit:
        return STATUS_USED, f"Visible response/trace/citation signal matched {hit!r}.", [hit]

    available = artifact_info.get("available")
    if available is True:
        return STATUS_AVAILABLE_NOT_USED, "Artifact path exists, but this answer did not expose a usage signal for it.", []
    if available is False:
        return STATUS_NOT_AVAILABLE_NOT_USED, "No artifact path exists and this answer did not expose a usage signal.", []
    return STATUS_NOT_AVAILABLE_NOT_USED, "This tool has no local artifact path and no usage signal was visible.", []


def build_tool_usage_checklist(
    *,
    question: str,
    response: Mapping[str, Any],
    extra_artifact_paths: Optional[Mapping[str, Sequence[str]]] = None,
) -> List[Dict[str, Any]]:
    artifact_map = _artifact_availability(extra_artifact_paths)
    trace = _trace_payload(response)
    citations = _citations(trace, response)
    assistant_text = _extract_assistant_text(response)
    response_search_text = _flatten_for_search({"response": response, "assistant_text": assistant_text, "trace_net": trace, "citations": citations})
    checklist: List[Dict[str, Any]] = []
    for tool in TOOL_ORDER:
        artifact_info = artifact_map.get(tool, {"available": None, "existing_paths": [], "checked_paths": []})
        status, reason, signals = _tool_status(
            tool,
            response=response,
            artifact_info=artifact_info,
            response_search_text=response_search_text,
            citations=citations,
        )
        checklist.append(
            {
                "tool": tool,
                "status": status,
                "used": status == STATUS_USED,
                "available": artifact_info.get("available"),
                "existing_artifact_paths": artifact_info.get("existing_paths") or [],
                "checked_artifact_paths": artifact_info.get("checked_paths") or [],
                "signals": signals,
                "reason": reason,
            }
        )
    return checklist


def checklist_text(checklist: Sequence[Mapping[str, Any]]) -> str:
    labels = {
        "webui_endpoint": "webui endpoint",
        "gemma_llm": "gemma llm",
        "ocr_fishnet": "ocr/fishnet",
        "page_context_v2": "page context v2",
        "route_dispatch": "route dispatch",
        "table_route": "table route",
        "embedding_vector": "embedding/vector",
        "graph_leiden": "graph/leiden",
        "visual_image_route": "visual/image route",
        "self_rag": "self-rag",
        "crag_retry": "crag retry",
        "final_gate": "final gate",
    }
    lines = []
    for item in checklist:
        tool = str(item.get("tool"))
        status = str(item.get("status"))
        available = item.get("available")
        if status == STATUS_USED:
            state = "used"
        elif status == STATUS_AVAILABLE_NOT_USED:
            state = "available, not used"
        else:
            state = "not used"
        suffix = ""
        if available is False and status != STATUS_USED:
            suffix = " (artifact missing)"
        lines.append(f"{labels.get(tool, tool)}: {state}{suffix}")
    return "\n".join(lines)


def build_audit_report(
    *,
    question: str,
    output_dir: Path,
    endpoint_url: str = DEFAULT_ENDPOINT_URL,
    model: str = DEFAULT_MODEL_ID,
    api_key: str = "",
    request_timeout: int = 300,
    response_json_path: Optional[Path] = None,
    extra_artifact_paths: Optional[Mapping[str, Sequence[str]]] = None,
) -> Dict[str, Any]:
    started = time.time()
    if response_json_path:
        response = _read_json(response_json_path, required=True)
        call_status = "saved_response_loaded"
        call_error = None
    else:
        try:
            response = _post_question(AuditConfig(endpoint_url=endpoint_url, model=model, api_key=api_key, request_timeout=request_timeout), question)
            call_status = "endpoint_response_received"
            call_error = None
        except Exception as exc:  # still write an audit record for debugging
            response = {"error": f"{type(exc).__name__}: {exc}"}
            call_status = "endpoint_call_failed"
            call_error = response["error"]

    trace = _trace_payload(response)
    assistant_text = _extract_assistant_text(response)
    checklist = build_tool_usage_checklist(question=question, response=response, extra_artifact_paths=extra_artifact_paths)
    used_tools = [r["tool"] for r in checklist if r.get("used")]
    available_not_used_tools = [r["tool"] for r in checklist if r.get("status") == STATUS_AVAILABLE_NOT_USED]
    not_used_tools = [r["tool"] for r in checklist if not r.get("used")]

    summary = {
        "question": question,
        "endpoint_url": endpoint_url if not response_json_path else None,
        "model": model,
        "call_status": call_status,
        "call_error": call_error,
        "assistant_response_char_count": len(assistant_text),
        "trace_net_present": bool(trace),
        "trace_response_kind": trace.get("response_kind"),
        "trace_intent": trace.get("intent"),
        "trace_llm_called": trace.get("llm_called"),
        "trace_llm_model": trace.get("llm_model"),
        "trace_llm_error": trace.get("llm_error"),
        "citation_count": len(_citations(trace, response)),
        "tool_checklist_count": len(checklist),
        "used_tool_count": len(used_tools),
        "available_not_used_tool_count": len(available_not_used_tools),
        "not_used_tool_count": len(not_used_tools),
        "used_tools": used_tools,
        "available_not_used_tools": available_not_used_tools,
        "not_used_tools": not_used_tools,
        "answer_permission_count": int(bool(trace.get("answer_permission"))),
        "can_answer_directly_count": int(bool(trace.get("can_answer_directly"))),
        "can_prove_claims_count": int(bool(trace.get("can_prove_claims"))),
        "source_truth_mutation_allowed_count": int(bool(trace.get("source_truth_mutation_allowed"))),
        "postgres_write_attempt_count": int(bool(trace.get("postgres_write_attempt"))),
        "qdrant_write_attempt_count": int(bool(trace.get("qdrant_write_attempt"))),
        "opensearch_write_attempt_count": int(bool(trace.get("opensearch_write_attempt"))),
        "unsafe_record_count": int(bool(trace.get("unsafe"))),
        "elapsed_seconds": round(time.time() - started, 3),
    }
    quality_status = "PASS" if call_error is None and checklist and summary["answer_permission_count"] == 0 and summary["source_truth_mutation_allowed_count"] == 0 else "FAIL"
    payload = {
        "module": MODULE_VERSION,
        "status": "TRACE_NET_E2E_TOOL_USAGE_AUDIT_BUILT",
        "quality_status": quality_status,
        "summary": summary,
        "question": question,
        "checklist_text": checklist_text(checklist),
        "tool_checklist": checklist,
        "assistant_response_text": assistant_text,
        "trace_net": trace,
        "raw_response": response,
        "safety_contract": {
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
            "postgres_write_allowed": False,
            "qdrant_write_allowed": False,
            "opensearch_write_allowed": False,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / REPORT_NAME, payload)
    _write_json(output_dir / "trace_net_e2e_tool_usage_audit_v1_summary.json", summary)
    _write_json(output_dir / "trace_net_e2e_tool_usage_audit_v1_raw_response.json", response)
    (output_dir / "trace_net_e2e_tool_usage_audit_v1_checklist.txt").write_text(payload["checklist_text"] + "\n", encoding="utf-8")
    return payload


def check_audit_quality(
    *,
    report_path: Path,
    min_checklist_count: int = 10,
    min_used_tool_count: int = 1,
    require_trace_net: bool = False,
    require_llm_called: bool = False,
    require_tool_statuses: Optional[Mapping[str, str]] = None,
    require_no_answer_permission: bool = False,
    require_no_source_truth_mutation: bool = False,
    require_no_write_attempts: bool = False,
) -> Dict[str, Any]:
    payload = _read_json(report_path, required=True)
    summary = payload.get("summary") or {}
    checklist = payload.get("tool_checklist") or []
    by_tool = {str(item.get("tool")): str(item.get("status")) for item in checklist if isinstance(item, Mapping)}
    failures: List[str] = []

    def fail_if(condition: bool, message: str) -> None:
        if condition:
            failures.append(message)

    fail_if(payload.get("quality_status") != "PASS", "audit report quality_status is not PASS")
    fail_if(len(checklist) < min_checklist_count, "not enough tool checklist rows")
    fail_if(int(summary.get("used_tool_count") or 0) < min_used_tool_count, "not enough used tools")
    if require_trace_net:
        fail_if(not summary.get("trace_net_present"), "trace_net payload was not present")
    if require_llm_called:
        fail_if(summary.get("trace_llm_called") is not True, "trace_net.llm_called was not true")
    for tool, expected_status in (require_tool_statuses or {}).items():
        fail_if(by_tool.get(tool) != expected_status, f"tool {tool!r} status {by_tool.get(tool)!r} != {expected_status!r}")
    if require_no_answer_permission:
        fail_if(int(summary.get("answer_permission_count") or 0) != 0, "answer_permission_count is not zero")
        fail_if(int(summary.get("can_answer_directly_count") or 0) != 0, "can_answer_directly_count is not zero")
        fail_if(int(summary.get("can_prove_claims_count") or 0) != 0, "can_prove_claims_count is not zero")
    if require_no_source_truth_mutation:
        fail_if(int(summary.get("source_truth_mutation_allowed_count") or 0) != 0, "source_truth_mutation_allowed_count is not zero")
    if require_no_write_attempts:
        for key in ["postgres_write_attempt_count", "qdrant_write_attempt_count", "opensearch_write_attempt_count"]:
            fail_if(int(summary.get(key) or 0) != 0, f"{key} is not zero")
    return {
        "quality_status": "FAIL" if failures else "PASS",
        "summary": summary,
        "tool_statuses": by_tool,
        "failures": failures,
        "checked_report_path": str(report_path),
    }


def _parse_tool_status(values: Sequence[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"expected TOOL=STATUS, got {value!r}")
        tool, status = value.split("=", 1)
        tool = tool.strip()
        status = status.strip()
        if tool not in TOOL_ORDER:
            raise ValueError(f"unknown tool {tool!r}; expected one of {TOOL_ORDER}")
        if status not in {STATUS_USED, STATUS_AVAILABLE_NOT_USED, STATUS_NOT_AVAILABLE_NOT_USED, STATUS_UNKNOWN}:
            raise ValueError(f"unknown status {status!r}")
        out[tool] = status
    return out


def main_build(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run a TRACE-Net E2E question and audit visible tool usage.")
    parser.add_argument("--question", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--endpoint-url", default=DEFAULT_ENDPOINT_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL_ID)
    parser.add_argument("--api-key", default="")
    parser.add_argument("--request-timeout", type=int, default=300)
    parser.add_argument("--response-json", help="Audit a saved OpenAI-compatible response instead of calling the endpoint.")
    parser.add_argument("--quality", action="store_true")
    args = parser.parse_args(argv)
    payload = build_audit_report(
        question=args.question,
        output_dir=Path(args.output_dir),
        endpoint_url=args.endpoint_url,
        model=args.model,
        api_key=args.api_key,
        request_timeout=args.request_timeout,
        response_json_path=Path(args.response_json) if args.response_json else None,
    )
    print("Status:", payload["status"])
    print("Quality status:", payload["quality_status"])
    print("Summary:", json.dumps(payload["summary"], sort_keys=True))
    print("Checklist:\n" + payload["checklist_text"])
    return 0 if payload["quality_status"] == "PASS" else 1


def main_check(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net E2E tool usage audit quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--min-checklist-count", type=int, default=10)
    parser.add_argument("--min-used-tool-count", type=int, default=1)
    parser.add_argument("--require-trace-net", action="store_true")
    parser.add_argument("--require-llm-called", action="store_true")
    parser.add_argument("--require-tool-status", action="append", default=[], help="Expected status as TOOL=STATUS, e.g. graph_leiden=used")
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-no-source-truth-mutation", action="store_true")
    parser.add_argument("--require-no-write-attempts", action="store_true")
    args = parser.parse_args(argv)
    result = check_audit_quality(
        report_path=Path(args.report_path),
        min_checklist_count=args.min_checklist_count,
        min_used_tool_count=args.min_used_tool_count,
        require_trace_net=args.require_trace_net,
        require_llm_called=args.require_llm_called,
        require_tool_statuses=_parse_tool_status(args.require_tool_status),
        require_no_answer_permission=args.require_no_answer_permission,
        require_no_source_truth_mutation=args.require_no_source_truth_mutation,
        require_no_write_attempts=args.require_no_write_attempts,
    )
    print("Quality status:", result["quality_status"])
    print("Summary:", json.dumps(result["summary"], sort_keys=True))
    print("Tool statuses:", json.dumps(result["tool_statuses"], sort_keys=True))
    if result["failures"]:
        print("Failures:", json.dumps(result["failures"], indent=2))
    if args.write_json:
        out = Path(args.report_path).with_name("trace_net_e2e_tool_usage_audit_v1_quality_check.json")
        _write_json(out, result)
        print("Wrote:", out)
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main_build())
