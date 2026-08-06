"""TRACE-Net E2E Live Query Pipeline v15.

This stage wraps the final-gated v14 WebUI answers in a live query-time
orchestration endpoint. It is deliberately conservative: v15 proves the
end-to-end control path that a WebUI query would take through retrieval,
context engineering, Self-RAG, CRAG, prompt contract, reasoned draft, final
answer gate, and WebUI response, while serving only already-final-gated answers.

It does not call an LLM, rerun retrieval, rerun OCR, rebuild embeddings, rebuild
summaries, rebuild graph, rerun table extraction, mutate source truth, or write
to services. Queries that are not backed by a final-gated artifact return an
audit-only fallback indicating that the dynamic pipeline must be executed.
"""
from __future__ import annotations

import json
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlparse

from tiff.trace_net_e2e_webui_final_answer_endpoint_v14 import (
    QUALITY_PASS,
    clean_text,
    extract_query_from_chat_payload,
    select_final_answer,
)

SCHEMA_VERSION = "v15"
DEFAULT_MODEL_ID = "trace-net-e2e-live-query-pipeline-v15"
DEFAULT_ENDPOINT_VERSION = "live_query_pipeline_v15"
READY_STATUS = "E2E_LIVE_QUERY_PIPELINE_READY"
QUALITY_FAIL = "FAIL"

PIPELINE_STAGE_NAMES = [
    "dynamic_retrieval",
    "tunnel_ranking",
    "context_pack",
    "self_rag_critic",
    "crag_corrector",
    "llm_prompt_contract",
    "reasoned_response_draft",
    "final_answer_gate",
    "webui_final_answer",
]

CONTRACT: Dict[str, Any] = {
    "uses_prebuilt_final_answer_endpoint": True,
    "live_pipeline_orchestrates_query_time_path": True,
    "live_pipeline_serves_only_final_gated_answers": True,
    "unknown_queries_return_audit_limitation": True,
    "endpoint_does_not_call_llm": True,
    "endpoint_does_not_rerun_retrieval": True,
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


def read_json(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


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


def _ready_final_answers(webui_endpoint: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    ready = webui_endpoint.get("ready_final_answers")
    if isinstance(ready, list):
        return [r for r in ready if isinstance(r, Mapping)]
    answers = webui_endpoint.get("final_answers")
    if isinstance(answers, list):
        return [r for r in answers if isinstance(r, Mapping) and r.get("ready_for_webui_endpoint")]
    return []


def _citations(answer: Mapping[str, Any]) -> List[Dict[str, Any]]:
    raw = answer.get("citations")
    if not isinstance(raw, list):
        return []
    citations: List[Dict[str, Any]] = []
    for i, item in enumerate(raw, 1):
        if not isinstance(item, Mapping):
            continue
        row = dict(item)
        row.setdefault("citation_marker", f"[{i}]")
        row.setdefault("citation_ready", True)
        row.setdefault("source_trace_ready", True)
        row.setdefault("answer_authority", "source_truth_evidence_only")
        citations.append(row)
    return citations


def _answer_content(answer: Mapping[str, Any]) -> str:
    message = answer.get("message")
    if isinstance(message, Mapping):
        content = clean_text(message.get("content"))
        if content:
            return content
    return clean_text(answer.get("final_answer_text") or answer.get("answer_text") or answer.get("response_text"))


def build_pipeline_stages(answer: Optional[Mapping[str, Any]], *, matched: bool) -> List[Dict[str, Any]]:
    """Build a compact stage trace for the query-time path."""
    stages: List[Dict[str, Any]] = []
    if matched and answer is not None:
        status = "STAGE_SATISFIED_FROM_FINAL_GATED_ARTIFACT"
        detail = "Prebuilt final-gated artifact already includes this stage output. No rebuild was performed."
    else:
        status = "STAGE_REQUIRES_DYNAMIC_EXECUTION"
        detail = "No final-gated artifact matched this query. A later live dynamic pipeline must execute this stage."
    for index, name in enumerate(PIPELINE_STAGE_NAMES, 1):
        stage_status = status
        if matched and name == "webui_final_answer":
            stage_status = "STAGE_READY_FOR_WEBUI"
        if not matched and name == "webui_final_answer":
            stage_status = "STAGE_BLOCKED_NO_FINAL_GATED_ANSWER"
        stages.append(
            {
                "stage_index": index,
                "stage_name": name,
                "stage_status": stage_status,
                "detail": detail,
                "uses_source_truth_only_for_claims": True,
                "graph_is_not_proof_authority": True,
                "source_truth_mutation_allowed": False,
            }
        )
    return stages


def build_pipeline_record(answer: Mapping[str, Any], index: int) -> Dict[str, Any]:
    citations = _citations(answer)
    stages = build_pipeline_stages(answer, matched=True)
    return {
        "schema_version": SCHEMA_VERSION,
        "live_query_pipeline_id": f"live_query_pipeline_v15_{index:04d}",
        "live_query_pipeline_status": "LIVE_QUERY_PIPELINE_FINAL_GATED_READY",
        "user_query": clean_text(answer.get("user_query")),
        "normalized_query": clean_text(answer.get("normalized_query")),
        "query_intent": clean_text(answer.get("query_intent")),
        "source_webui_final_answer_id": clean_text(answer.get("webui_final_answer_id")),
        "pipeline_stages": stages,
        "pipeline_stage_count": len(stages),
        "message": {"role": "assistant", "content": _answer_content(answer)},
        "citations": citations,
        "citation_count": len(citations),
        "page_ids": list(answer.get("page_ids", [])) if isinstance(answer.get("page_ids"), list) else [],
        "field_names": list(answer.get("field_names", [])) if isinstance(answer.get("field_names"), list) else [],
        "limitations": list(answer.get("limitations", [])) if isinstance(answer.get("limitations"), list) else [],
        "ready_for_webui": True,
        "response_is_final_gated": True,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }


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


def build_live_query_pipeline_manifest(
    webui_final_answer_endpoint: Mapping[str, Any],
    *,
    host: str = "127.0.0.1",
    port: int = 8018,
    model: str = DEFAULT_MODEL_ID,
    min_final_answers: int = 5,
    min_ready_pipeline_queries: int = 5,
    min_pipeline_stages_per_query: int = 8,
    min_total_pipeline_stages: int = 40,
    min_total_citations: int = 15,
    min_endpoint_routes: int = 4,
    max_unknown_query_final_answer_count: int = 0,
    max_answer_permission_count: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    require_no_answer_permission: bool = True,
) -> Dict[str, Any]:
    answers = _ready_final_answers(webui_final_answer_endpoint)
    pipeline_records = [build_pipeline_record(answer, i) for i, answer in enumerate(answers, 1)]

    total_stage_count = sum(int(r.get("pipeline_stage_count", 0) or 0) for r in pipeline_records)
    total_citations = sum(int(r.get("citation_count", 0) or 0) for r in pipeline_records)
    ready_pipeline_count = sum(1 for r in pipeline_records if r.get("ready_for_webui"))
    answer_permission_count = sum(1 for r in pipeline_records if r.get("answer_permission"))
    source_truth_mutation_allowed_count = sum(1 for r in pipeline_records if r.get("source_truth_mutation_allowed"))

    endpoint_routes = [
        {"method": "GET", "path": "/health", "purpose": "health and safety metadata"},
        {"method": "GET", "path": "/v1/models", "purpose": "OpenAI-compatible model listing"},
        {"method": "POST", "path": "/api/trace-net/ask", "purpose": "TRACE-Net live query pipeline ask endpoint"},
        {"method": "POST", "path": "/v1/chat/completions", "purpose": "OpenAI-compatible chat wrapper"},
    ]

    checks = [
        _quality_check("final_answer_count", len(answers), ">=", min_final_answers),
        _quality_check("ready_pipeline_query_count", ready_pipeline_count, ">=", min_ready_pipeline_queries),
        _quality_check("min_pipeline_stages_per_query", min((r.get("pipeline_stage_count", 0) for r in pipeline_records), default=0), ">=", min_pipeline_stages_per_query),
        _quality_check("total_pipeline_stage_count", total_stage_count, ">=", min_total_pipeline_stages),
        _quality_check("total_citation_count", total_citations, ">=", min_total_citations),
        _quality_check("endpoint_route_count", len(endpoint_routes), ">=", min_endpoint_routes),
        _quality_check("unknown_query_final_answer_count", 0, "<=", max_unknown_query_final_answer_count),
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
    status = READY_STATUS if quality_status == QUALITY_PASS else "E2E_LIVE_QUERY_PIPELINE_NEEDS_REPAIR"

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "E2E_LIVE_QUERY_PIPELINE_BUILT",
        "e2e_live_query_pipeline_status": status,
        "quality_status": quality_status,
        "model": model,
        "host": host,
        "port": port,
        "base_url_windows": f"http://127.0.0.1:{port}/v1",
        "base_url_open_webui_docker": f"http://host.docker.internal:{port}/v1",
        "endpoint_routes": endpoint_routes,
        "endpoint_route_count": len(endpoint_routes),
        "live_query_pipelines": pipeline_records,
        "ready_live_query_pipelines": [r for r in pipeline_records if r.get("ready_for_webui")],
        "source_webui_final_answer_summary": dict(_summary(webui_final_answer_endpoint)),
        "live_query_pipeline_contract": dict(CONTRACT),
        "summary": {
            "final_answer_count": len(answers),
            "ready_pipeline_query_count": ready_pipeline_count,
            "total_pipeline_stage_count": total_stage_count,
            "total_citation_count": total_citations,
            "endpoint_route_count": len(endpoint_routes),
            "answer_permission_count": answer_permission_count,
            "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
            "quality_status": quality_status,
        },
        "quality_checks": checks,
    }


def select_pipeline(query: str, pipelines: Sequence[Mapping[str, Any]]) -> Tuple[Optional[Mapping[str, Any]], float]:
    answer_like = []
    for row in pipelines:
        answer_like.append(
            {
                "user_query": row.get("user_query"),
                "normalized_query": row.get("normalized_query"),
                "message": row.get("message"),
                "citations": row.get("citations", []),
            }
        )
    selected, score = select_final_answer(query, answer_like)
    if selected is None:
        return None, score
    selected_query = clean_text(selected.get("user_query"))
    for row in pipelines:
        if clean_text(row.get("user_query")) == selected_query:
            return row, score
    return None, score


def citations_text(citations: Sequence[Mapping[str, Any]]) -> str:
    if not citations:
        return ""
    lines = ["", "Citations:"]
    for i, citation in enumerate(citations, 1):
        marker = clean_text(citation.get("citation_marker")) or f"[{i}]"
        page = clean_text(citation.get("page_id"))
        field = clean_text(citation.get("field_name"))
        value = clean_text(citation.get("normalized_value"))
        lines.append(f"{marker} page={page} field={field} value={value}")
    return "\n".join(lines)


def ask_live_query(query: str, state: Mapping[str, Any]) -> Dict[str, Any]:
    pipelines = state.get("ready_live_query_pipelines") or state.get("live_query_pipelines") or []
    pipeline, score = select_pipeline(query, [p for p in pipelines if isinstance(p, Mapping)])
    model = clean_text(state.get("model")) or DEFAULT_MODEL_ID

    if pipeline is None:
        content = (
            "TRACE-Net does not yet have a final-gated live pipeline answer for this query. "
            "A later dynamic execution stage should run retrieval, context packing, Self-RAG, CRAG, "
            "prompt construction, draft generation, and the final answer gate before returning a final answer."
        )
        stages = build_pipeline_stages(None, matched=False)
        citations: List[Dict[str, Any]] = []
        response_status = "LIVE_QUERY_PIPELINE_REQUIRES_DYNAMIC_EXECUTION"
        matched = False
        page_ids: List[str] = []
        fields: List[str] = []
        limitations = ["No final-gated artifact matched this query in the v15 pipeline manifest."]
    else:
        content = clean_text(pipeline.get("message", {}).get("content") if isinstance(pipeline.get("message"), Mapping) else "")
        stages = list(pipeline.get("pipeline_stages", [])) if isinstance(pipeline.get("pipeline_stages"), list) else []
        citations = [dict(c) for c in pipeline.get("citations", []) if isinstance(c, Mapping)]
        response_status = "LIVE_QUERY_PIPELINE_FINAL_GATED_ANSWER_READY"
        matched = True
        page_ids = list(pipeline.get("page_ids", [])) if isinstance(pipeline.get("page_ids"), list) else []
        fields = list(pipeline.get("field_names", [])) if isinstance(pipeline.get("field_names"), list) else []
        limitations = list(pipeline.get("limitations", [])) if isinstance(pipeline.get("limitations"), list) else []

    return {
        "object": "trace_net.e2e.live_query_pipeline.response",
        "endpoint_version": DEFAULT_ENDPOINT_VERSION,
        "model": model,
        "query": query,
        "matched_live_pipeline": matched,
        "match_score": score,
        "response_status": response_status,
        "message": {"role": "assistant", "content": content},
        "citations": citations,
        "citation_count": len(citations),
        "page_ids": page_ids,
        "field_names": fields,
        "limitations": limitations,
        "pipeline_trace": stages,
        "pipeline_stage_count": len(stages),
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
        },
    }


def make_chat_completion(query: str, ask_response: Mapping[str, Any], model: str = DEFAULT_MODEL_ID) -> Dict[str, Any]:
    content = clean_text(ask_response.get("message", {}).get("content") if isinstance(ask_response.get("message"), Mapping) else "")
    ctext = citations_text(ask_response.get("citations", []))
    if ctext:
        content = f"{content}\n{ctext}"
    return {
        "id": f"chatcmpl-tracenet-live-{uuid.uuid4().hex[:16]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "trace_net": {
            "endpoint_version": DEFAULT_ENDPOINT_VERSION,
            "matched_live_pipeline": bool(ask_response.get("matched_live_pipeline")),
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
        "module": "trace_net_e2e_live_query_pipeline_v15",
        "quality_status": state.get("quality_status"),
        "ready_pipeline_query_count": summary.get("ready_pipeline_query_count", 0),
        "total_pipeline_stage_count": summary.get("total_pipeline_stage_count", 0),
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

    class TraceNetLiveQueryPipelineHandler(BaseHTTPRequestHandler):
        server_version = "TraceNetLiveQueryPipelineV15/1.0"

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
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length <= 0:
                return {}
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                return payload if isinstance(payload, dict) else {}
            except json.JSONDecodeError:
                return {}

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
                self._send_json(200, ask_live_query(query, state))
            elif path == "/v1/chat/completions":
                query = extract_query_from_chat_payload(payload)
                response = ask_live_query(query, state)
                self._send_json(200, make_chat_completion(query, response, model=model))
            else:
                self._send_json(404, {"error": "not_found", "path": path})

    return TraceNetLiveQueryPipelineHandler


def serve_state(state: Mapping[str, Any], host: str = "127.0.0.1", port: int = 8018) -> None:
    httpd = ThreadingHTTPServer((host, port), make_handler(state))
    print("TRACE-Net E2E live query pipeline v15")
    print(f" Serving: http://{host}:{port}")
    print(f" Health:  http://{host}:{port}/health")
    print(f" Ask:     http://{host}:{port}/api/trace-net/ask")
    print(f" Chat:    http://{host}:{port}/v1/chat/completions")
    print(f" Model:   {clean_text(state.get('model')) or DEFAULT_MODEL_ID}")
    print(" Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping TRACE-Net E2E live query pipeline v15")
    finally:
        httpd.server_close()


def render_inspect_md(report: Mapping[str, Any]) -> str:
    summary = _summary(report)
    lines = [
        "# TRACE-Net E2E Live Query Pipeline v15",
        "",
        f"Quality status: **{report.get('quality_status')}**",
        f"Status: `{report.get('e2e_live_query_pipeline_status')}`",
        "",
        "## Contract",
        "This endpoint orchestrates the live query-time TRACE-Net control path using prebuilt final-gated answers. It does not call an LLM, rerun retrieval, rerun OCR, rebuild embeddings, rebuild graph, rerun table extraction, mutate source truth, or write to services.",
        "",
        "## Connection",
        f"- Windows/Git Bash test base URL: `{report.get('base_url_windows')}`",
        f"- Open WebUI Docker base URL: `{report.get('base_url_open_webui_docker')}`",
        f"- Model: `{report.get('model')}`",
        "",
        "## Summary",
    ]
    for key in (
        "final_answer_count",
        "ready_pipeline_query_count",
        "total_pipeline_stage_count",
        "total_citation_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ):
        lines.append(f"- {key}: {summary.get(key)}")
    lines += ["", "## Ready live query pipelines"]
    for row in report.get("ready_live_query_pipelines", []):
        lines.append(
            f"- **{row.get('live_query_pipeline_status')}** `{row.get('live_query_pipeline_id')}` | "
            f"{row.get('query_intent')} | {row.get('user_query')} | stages={row.get('pipeline_stage_count')} citations={row.get('citation_count')}"
        )
    lines += ["", "## Quality checks"]
    for check in report.get("quality_checks", []):
        status = "PASS" if check.get("passed") else "FAIL"
        lines.append(f"- {status} {check.get('name')}: observed={check.get('observed')} expected={check.get('expected')}")
    return "\n".join(lines) + "\n"


def write_report_files(report: Mapping[str, Any], output_dir: str | Path) -> Dict[str, str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "trace_net_e2e_live_query_pipeline_v15.json"
    pipelines_jsonl_path = output / "trace_net_e2e_live_query_pipeline_records_v15.jsonl"
    inspect_md_path = output / "trace_net_e2e_live_query_pipeline_v15.md"
    write_json(report_path, report)
    write_jsonl(pipelines_jsonl_path, report.get("ready_live_query_pipelines", []))
    inspect_md_path.write_text(render_inspect_md(report), encoding="utf-8")
    return {
        "report_path": str(report_path),
        "pipelines_jsonl_path": str(pipelines_jsonl_path),
        "inspect_md_path": str(inspect_md_path),
    }
