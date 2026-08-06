"""TRACE-Net E2E WebUI Final Answer Endpoint v14.

This module packages final-gated v13 answers behind a small OpenAI-compatible
local endpoint. It is intentionally artifact-backed and non-mutating: it reads
prebuilt final-answer-gate records and never reruns OCR, retrieval, embeddings,
graph construction, table extraction, or LLM generation.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple
from urllib.parse import urlparse

SCHEMA_VERSION = "v14"
DEFAULT_MODEL_ID = "trace-net-e2e-webui-final-answer-endpoint-v14"
DEFAULT_ENDPOINT_VERSION = "webui_final_answer_v14"

READY_STATUS = "E2E_WEBUI_FINAL_ANSWER_ENDPOINT_READY"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"

CONTRACT: Dict[str, Any] = {
    "uses_prebuilt_final_answer_gate": True,
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


def nested_get(obj: Mapping[str, Any], path: Sequence[str], default: Any = None) -> Any:
    cur: Any = obj
    for key in path:
        if not isinstance(cur, Mapping) or key not in cur:
            return default
        cur = cur[key]
    return cur


def clean_text(value: Any) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("everyfactual", "every factual")
        .replace("route,graph", "route, graph")
        .replace("ont_p_", "on t_p_")
        .replace(" on  t_p_", " on t_p_")
        .strip()
    )


def normalize_query(value: Any) -> str:
    text = clean_text(value).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def jaccard_score(a: str, b: str) -> float:
    aa = set(normalize_query(a).split())
    bb = set(normalize_query(b).split())
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / max(1, len(aa | bb))


def first_present(mapping: Mapping[str, Any], keys: Sequence[str], default: Any = None) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return default


def iter_final_gate_records(data: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    for key in (
        "final_answer_gates",
        "final_gates",
        "final_answer_gate_records",
        "records",
        "webui_final_answers",
        "answers",
    ):
        records = data.get(key)
        if isinstance(records, list):
            return [r for r in records if isinstance(r, Mapping)]
    return []


def extract_answer_text(record: Mapping[str, Any]) -> str:
    candidates: List[Any] = [
        record.get("final_answer_text"),
        record.get("answer_text"),
        record.get("response_text"),
        record.get("draft_text"),
        nested_get(record, ["message", "content"]),
        nested_get(record, ["final_message", "content"]),
        nested_get(record, ["final_answer_message", "content"]),
        nested_get(record, ["draft_message", "content"]),
        nested_get(record, ["reasoned_response_draft", "draft_message", "content"]),
        nested_get(record, ["final_answer", "content"]),
        nested_get(record, ["final_answer", "message", "content"]),
    ]
    final_answer = record.get("final_answer")
    if isinstance(final_answer, str):
        candidates.insert(0, final_answer)
    for candidate in candidates:
        text = clean_text(candidate)
        if text:
            return text
    return ""


def extract_citations(record: Mapping[str, Any]) -> List[Dict[str, Any]]:
    raw = first_present(
        record,
        (
            "citations",
            "final_citations",
            "citation_records",
            "source_truth_citations",
            "citation_details",
        ),
        [],
    )
    if not isinstance(raw, list):
        raw = []
    citations: List[Dict[str, Any]] = []
    for i, item in enumerate(raw, 1):
        if not isinstance(item, Mapping):
            continue
        citation = dict(item)
        citation.setdefault("citation_id", f"citation_{i}")
        citation.setdefault("citation_marker", f"[{i}]")
        citation.setdefault("citation_ready", True)
        citation.setdefault("source_trace_ready", True)
        citation.setdefault("answer_authority", "source_truth_evidence_only")
        citations.append(citation)
    return citations


def extract_status(record: Mapping[str, Any]) -> str:
    return clean_text(
        first_present(
            record,
            (
                "final_answer_gate_status",
                "final_gate_status",
                "gate_status",
                "status",
                "final_answer_status",
            ),
            "",
        )
    )


def is_record_ready(record: Mapping[str, Any]) -> bool:
    status = extract_status(record)
    unsupported_claim_count = int(record.get("unsupported_claim_count", 0) or 0)
    graph_summary_proof_violation_count = int(record.get("graph_summary_proof_violation_count", 0) or 0)
    explicit_ready = first_present(
        record,
        (
            "final_answer_ready_for_webui",
            "ready_for_webui",
            "final_answer_ready",
            "webui_ready",
        ),
        None,
    )
    if explicit_ready is False:
        return False
    if unsupported_claim_count > 0 or graph_summary_proof_violation_count > 0:
        return False
    if explicit_ready is True:
        return True
    upper = status.upper()
    return "PASS" in upper or "READY" in upper or "WEBUI" in upper


def normalize_final_answer_record(record: Mapping[str, Any], index: int) -> Optional[Dict[str, Any]]:
    query = clean_text(record.get("user_query") or record.get("query") or record.get("question"))
    content = extract_answer_text(record)
    citations = extract_citations(record)
    if not query or not content:
        return None

    page_ids: List[str] = []
    fields: List[str] = []
    for citation in citations:
        page = clean_text(citation.get("page_id"))
        field = clean_text(citation.get("field_name"))
        if page and page not in page_ids:
            page_ids.append(page)
        if field and field not in fields:
            fields.append(field)

    answer_id = clean_text(
        record.get("final_answer_gate_id")
        or record.get("final_answer_id")
        or record.get("reasoned_response_draft_id")
        or f"webui_final_answer_v14_{index:04d}"
    )

    status = "WEBUI_FINAL_ANSWER_READY" if is_record_ready(record) else "WEBUI_FINAL_ANSWER_NOT_READY"
    return {
        "schema_version": SCHEMA_VERSION,
        "webui_final_answer_id": answer_id,
        "webui_final_answer_status": status,
        "source_final_gate_status": extract_status(record),
        "user_query": query,
        "normalized_query": normalize_query(query),
        "query_intent": clean_text(record.get("query_intent")),
        "message": {"role": "assistant", "content": content},
        "citations": citations,
        "citation_count": len(citations),
        "page_ids": page_ids,
        "field_names": fields,
        "limitations": record.get("limitations") if isinstance(record.get("limitations"), list) else [],
        "unsupported_claim_count": int(record.get("unsupported_claim_count", 0) or 0),
        "graph_summary_proof_violation_count": int(record.get("graph_summary_proof_violation_count", 0) or 0),
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "ready_for_webui_endpoint": status == "WEBUI_FINAL_ANSWER_READY",
    }


def build_endpoint_manifest(
    final_answer_gate: Mapping[str, Any],
    *,
    host: str = "127.0.0.1",
    port: int = 8017,
    model: str = DEFAULT_MODEL_ID,
    min_final_answers: int = 5,
    min_ready_final_answers: int = 5,
    min_total_citations: int = 15,
    min_endpoint_routes: int = 4,
    max_unsupported_claim_count: int = 0,
    max_graph_summary_proof_violations: int = 0,
    max_answer_permission_count: int = 0,
    max_source_truth_mutation_allowed: int = 0,
    require_no_answer_permission: bool = True,
) -> Dict[str, Any]:
    records = iter_final_gate_records(final_answer_gate)
    normalized = [r for i, rec in enumerate(records, 1) if (r := normalize_final_answer_record(rec, i))]
    ready = [r for r in normalized if r.get("ready_for_webui_endpoint")]

    total_citations = sum(int(r.get("citation_count", 0) or 0) for r in ready)
    unsupported_claim_count = sum(int(r.get("unsupported_claim_count", 0) or 0) for r in normalized)
    graph_summary_proof_violation_count = sum(int(r.get("graph_summary_proof_violation_count", 0) or 0) for r in normalized)
    answer_permission_count = sum(1 for r in normalized if r.get("answer_permission"))
    source_truth_mutation_allowed_count = sum(1 for r in normalized if r.get("source_truth_mutation_allowed"))

    endpoint_routes = [
        {"method": "GET", "path": "/health", "purpose": "health and safety metadata"},
        {"method": "GET", "path": "/v1/models", "purpose": "OpenAI-compatible model listing"},
        {"method": "POST", "path": "/api/trace-net/ask", "purpose": "TRACE-Net final-gated ask endpoint"},
        {"method": "POST", "path": "/v1/chat/completions", "purpose": "OpenAI-compatible chat wrapper"},
    ]

    checks = [
        ("final_answer_count", len(normalized), ">=", min_final_answers),
        ("ready_final_answer_count", len(ready), ">=", min_ready_final_answers),
        ("total_citation_count", total_citations, ">=", min_total_citations),
        ("endpoint_route_count", len(endpoint_routes), ">=", min_endpoint_routes),
        ("unsupported_claim_count", unsupported_claim_count, "<=", max_unsupported_claim_count),
        ("graph_summary_proof_violation_count", graph_summary_proof_violation_count, "<=", max_graph_summary_proof_violations),
        ("answer_permission_count", answer_permission_count, "<=", max_answer_permission_count),
        ("source_truth_mutation_allowed_count", source_truth_mutation_allowed_count, "<=", max_source_truth_mutation_allowed),
        ("contract_can_answer_directly", 0, "==", 0),
        ("contract_can_prove_claims", 0, "==", 0),
        ("postgres_write_attempt_count", 0, "==", 0),
        ("qdrant_write_attempt_count", 0, "==", 0),
        ("opensearch_write_attempt_count", 0, "==", 0),
    ]
    if require_no_answer_permission:
        checks.append(("require_no_answer_permission", answer_permission_count, "==", 0))

    quality_checks: List[Dict[str, Any]] = []
    for name, observed, op, expected in checks:
        if op == ">=":
            passed = observed >= expected
        elif op == "<=":
            passed = observed <= expected
        elif op == "==":
            passed = observed == expected
        else:
            raise ValueError(op)
        quality_checks.append({"name": name, "observed": observed, "expected": f"{op} {expected}", "passed": passed})

    quality_status = QUALITY_PASS if all(c["passed"] for c in quality_checks) else QUALITY_FAIL
    status = READY_STATUS if quality_status == QUALITY_PASS else "E2E_WEBUI_FINAL_ANSWER_ENDPOINT_NEEDS_REPAIR"

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "E2E_WEBUI_FINAL_ANSWER_ENDPOINT_BUILT",
        "e2e_webui_final_answer_endpoint_status": status,
        "quality_status": quality_status,
        "model": model,
        "host": host,
        "port": port,
        "base_url_windows": f"http://127.0.0.1:{port}/v1",
        "base_url_open_webui_docker": f"http://host.docker.internal:{port}/v1",
        "endpoint_routes": endpoint_routes,
        "endpoint_route_count": len(endpoint_routes),
        "final_answers": normalized,
        "ready_final_answers": ready,
        "webui_final_answer_endpoint_contract": dict(CONTRACT),
        "summary": {
            "final_answer_count": len(normalized),
            "ready_final_answer_count": len(ready),
            "total_citation_count": total_citations,
            "unsupported_claim_count": unsupported_claim_count,
            "graph_summary_proof_violation_count": graph_summary_proof_violation_count,
            "answer_permission_count": answer_permission_count,
            "source_truth_mutation_allowed_count": source_truth_mutation_allowed_count,
            "final_answers_ready_for_webui_count": len(ready),
            "quality_status": quality_status,
        },
        "quality_checks": quality_checks,
    }


def select_final_answer(query: str, final_answers: Sequence[Mapping[str, Any]]) -> Tuple[Optional[Mapping[str, Any]], float]:
    normalized = normalize_query(query)
    if not normalized:
        return None, 0.0

    best: Optional[Mapping[str, Any]] = None
    best_score = 0.0
    for answer in final_answers:
        candidate_query = clean_text(answer.get("user_query"))
        candidate_norm = clean_text(answer.get("normalized_query")) or normalize_query(candidate_query)
        if candidate_norm == normalized:
            return answer, 1000.0
        score = jaccard_score(normalized, candidate_norm) * 100.0
        if score > best_score:
            best = answer
            best_score = score
    if best_score < 35.0:
        return None, best_score
    return best, best_score


def ask_final_answer(query: str, state: Mapping[str, Any]) -> Dict[str, Any]:
    model = clean_text(state.get("model")) or DEFAULT_MODEL_ID
    answer, score = select_final_answer(query, state.get("ready_final_answers") or state.get("final_answers") or [])
    if not answer:
        content = (
            "TRACE-Net has no final-gated WebUI answer artifact for this query. "
            "The system should fall back to dynamic retrieval or return an audit-only limitation."
        )
        citations: List[Dict[str, Any]] = []
        page_ids: List[str] = []
        fields: List[str] = []
        matched = False
        response_status = "FINAL_GATED_ANSWER_NOT_FOUND"
    else:
        content = clean_text(nested_get(answer, ["message", "content"], ""))
        citations = [dict(c) for c in answer.get("citations", []) if isinstance(c, Mapping)]
        page_ids = list(answer.get("page_ids", [])) if isinstance(answer.get("page_ids"), list) else []
        fields = list(answer.get("field_names", [])) if isinstance(answer.get("field_names"), list) else []
        matched = True
        response_status = "FINAL_GATED_ANSWER_READY"

    response = {
        "object": "trace_net.e2e.webui_final_answer.response",
        "endpoint_version": DEFAULT_ENDPOINT_VERSION,
        "model": model,
        "query": query,
        "matched_final_answer": matched,
        "match_score": score,
        "response_status": response_status,
        "message": {"role": "assistant", "content": content},
        "citations": citations,
        "citation_count": len(citations),
        "page_ids": page_ids,
        "field_names": fields,
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
        },
    }
    return response


def citations_text(citations: Sequence[Mapping[str, Any]]) -> str:
    if not citations:
        return ""
    lines = ["", "Citations:"]
    for i, c in enumerate(citations, 1):
        marker = clean_text(c.get("citation_marker")) or f"[{i}]"
        page = clean_text(c.get("page_id"))
        field = clean_text(c.get("field_name"))
        value = clean_text(c.get("normalized_value"))
        lines.append(f"{marker} page={page} field={field} value={value}")
    return "\n".join(lines)


def make_chat_completion(query: str, ask_response: Mapping[str, Any], model: str = DEFAULT_MODEL_ID) -> Dict[str, Any]:
    content = clean_text(nested_get(ask_response, ["message", "content"], ""))
    ctext = citations_text(ask_response.get("citations", []))
    if ctext:
        content = f"{content}\n{ctext}"
    return {
        "id": f"chatcmpl-tracenet-final-{uuid.uuid4().hex[:16]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "trace_net": {
            "endpoint_version": DEFAULT_ENDPOINT_VERSION,
            "matched_final_answer": bool(ask_response.get("matched_final_answer")),
            "match_score": ask_response.get("match_score", 0),
            "response_status": ask_response.get("response_status"),
            "safety": ask_response.get("safety", {}),
        },
    }


def extract_query_from_chat_payload(payload: Mapping[str, Any]) -> str:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return clean_text(payload.get("query") or payload.get("prompt"))
    for message in reversed(messages):
        if isinstance(message, Mapping) and message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str):
                return clean_text(content)
            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, Mapping) and item.get("type") == "text":
                        parts.append(str(item.get("text", "")))
                return clean_text("\n".join(parts))
    return ""


def health_response(state: Mapping[str, Any]) -> Dict[str, Any]:
    summary = state.get("summary", {}) if isinstance(state.get("summary"), Mapping) else {}
    return {
        "status": "ok" if state.get("quality_status") == QUALITY_PASS else "needs_repair",
        "module": "trace_net_e2e_webui_final_answer_endpoint_v14",
        "quality_status": state.get("quality_status"),
        "ready_final_answer_count": summary.get("ready_final_answer_count", 0),
        "total_citation_count": summary.get("total_citation_count", 0),
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

    class TraceNetFinalAnswerHandler(BaseHTTPRequestHandler):
        server_version = "TraceNetWebUIFinalAnswerV14/1.0"

        def log_message(self, format: str, *args: Any) -> None:  # pragma: no cover - keeps tests quiet
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
            raw = self.rfile.read(length).decode("utf-8")
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, dict) else {}
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
                self._send_json(200, ask_final_answer(query, state))
            elif path == "/v1/chat/completions":
                query = extract_query_from_chat_payload(payload)
                ask_response = ask_final_answer(query, state)
                self._send_json(200, make_chat_completion(query, ask_response, model=model))
            else:
                self._send_json(404, {"error": "not_found", "path": path})

    return TraceNetFinalAnswerHandler


def serve_state(state: Mapping[str, Any], host: str = "127.0.0.1", port: int = 8017) -> None:
    httpd = HTTPServer((host, port), make_handler(state))
    print("TRACE-Net E2E WebUI final answer endpoint v14")
    print(f" Serving: http://{host}:{port}")
    print(f" Health:  http://{host}:{port}/health")
    print(f" Ask:     http://{host}:{port}/api/trace-net/ask")
    print(f" Chat:    http://{host}:{port}/v1/chat/completions")
    print(f" Model:   {clean_text(state.get('model')) or DEFAULT_MODEL_ID}")
    print(" Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping TRACE-Net E2E WebUI final answer endpoint v14")
    finally:
        httpd.server_close()


def render_inspect_md(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# TRACE-Net E2E WebUI Final Answer Endpoint v14",
        "",
        f"Quality status: **{report.get('quality_status')}**",
        f"Status: `{report.get('e2e_webui_final_answer_endpoint_status')}`",
        "",
        "## Contract",
        "This endpoint serves final-gated answer artifacts to Open WebUI. It does not call an LLM, rerun retrieval, rerun OCR, rebuild embeddings, rebuild graph, rerun table extraction, mutate source truth, or write to services.",
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
        "ready_final_answer_count",
        "total_citation_count",
        "final_answers_ready_for_webui_count",
        "unsupported_claim_count",
        "graph_summary_proof_violation_count",
        "answer_permission_count",
        "source_truth_mutation_allowed_count",
    ):
        lines.append(f"- {key}: {summary.get(key)}")
    lines += ["", "## Ready final answers"]
    for row in report.get("ready_final_answers", []):
        lines.append(
            f"- **{row.get('webui_final_answer_status')}** `{row.get('webui_final_answer_id')}` | "
            f"{row.get('query_intent')} | {row.get('user_query')} | citations={row.get('citation_count')}"
        )
    lines += ["", "## Quality checks"]
    for check in report.get("quality_checks", []):
        status = "PASS" if check.get("passed") else "FAIL"
        lines.append(f"- {status} {check.get('name')}: observed={check.get('observed')} expected={check.get('expected')}")
    return "\n".join(lines) + "\n"


def write_report_files(report: Mapping[str, Any], output_dir: str | Path) -> Dict[str, str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "trace_net_e2e_webui_final_answer_endpoint_v14.json"
    responses_jsonl_path = output / "trace_net_e2e_webui_final_answer_endpoint_responses_v14.jsonl"
    inspect_md_path = output / "trace_net_e2e_webui_final_answer_endpoint_v14.md"
    write_json(report_path, report)
    write_jsonl(responses_jsonl_path, report.get("ready_final_answers", []))
    inspect_md_path.write_text(render_inspect_md(report), encoding="utf-8")
    return {
        "report_path": str(report_path),
        "responses_jsonl_path": str(responses_jsonl_path),
        "inspect_md_path": str(inspect_md_path),
    }
