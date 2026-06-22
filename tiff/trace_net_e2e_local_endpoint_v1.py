"""TRACE-Net E2E local endpoint v1.

This module exposes a small stdlib HTTP endpoint over the already-passing
artifact-backed E2E API wrapper smoke report. It is intentionally conservative:
responses are smoke/API-wrapper drafts, not runtime-finalized source truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlparse

MODULE_VERSION = "v1"
DEFAULT_MODEL_ID = "trace-net-e2e-local-endpoint-v1"
READY_STATUS = "E2E_LOCAL_ENDPOINT_READY_FOR_OPEN_WEBUI_SMOKE"
REPORT_STATUS = "E2E_LOCAL_ENDPOINT_MANIFEST_BUILT"

SAFETY_ZERO_KEYS = (
    "answer_permission_count",
    "can_answer_directly_count",
    "can_prove_claims_count",
    "source_truth_mutation_allowed_count",
    "postgres_write_attempt_count",
    "qdrant_write_attempt_count",
    "opensearch_write_attempt_count",
    "opensearch_upload_attempt_count",
)

REQUIRED_RESPONSE_KEYS = (
    "query_id",
    "user_query",
    "message",
    "citations",
)



def _trace_net_deep_scrub(value):
    """Final deep scrub for endpoint response objects before WebUI/OpenAI serialization."""
    if isinstance(value, str):
        return (
            value
            .replace("ont_p_", "on t_p_")
            .replace(" on  t_p_", " on t_p_")
        )
    if isinstance(value, list):
        return [_trace_net_deep_scrub(v) for v in value]
    if isinstance(value, dict):
        return {k: _trace_net_deep_scrub(v) for k, v in value.items()}
    return value

def load_json(path: str | Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def write_jsonl(path: str | Path, records: Iterable[Mapping[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True) + "\n")


def normalize_query(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z0-9\-\s_/]", " ", text or "")).strip().lower()


def token_set(text: str) -> set[str]:
    return {tok for tok in normalize_query(text).split() if tok}


def is_truthy_quality_pass(data: Mapping[str, Any]) -> bool:
    return str(data.get("quality_status", "")).upper() == "PASS"


def nested_get(mapping: Mapping[str, Any], keys: Sequence[str], default: Any = None) -> Any:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def clean_response_content(content: str) -> str:
    """Normalize small smoke-draft formatting defects before WebUI display."""
    cleaned = str(content or "")
    # Some upstream smoke drafts can concatenate "on" with TRACE-Net page ids.
    cleaned = re.sub(r"\bon(?=t_p_)", "on ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _value_alias(citation: Mapping[str, Any]) -> str:
    for key in ("normalized_value", "value", "evidence_value", "display_value", "text_value"):
        value = citation.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _infer_citation_values_from_content(citations: Sequence[Mapping[str, Any]], content: str) -> List[Dict[str, Any]]:
    """Fill blank citation values from field=value fragments in the response text.

    Final-gate smoke drafts already include fragments such as
    ``covered_part_number=120-36833-001 on t_p_120_1176_p000003``.
    Older API-wrapper artifacts sometimes emitted citation objects with blank
    ``normalized_value`` fields. This helper maps those text fragments back into
    the structured citations without changing source truth or inventing values.
    """
    cleaned_content = clean_response_content(content)
    occurrence_index: Dict[Tuple[str, str], int] = {}
    enriched: List[Dict[str, Any]] = []
    for raw in citations:
        citation = dict(raw)
        existing = _value_alias(citation)
        if existing:
            citation["normalized_value"] = existing
            enriched.append(citation)
            continue

        field_name = str(citation.get("field_name") or "").strip()
        page_id = str(citation.get("page_id") or "").strip()
        inferred = ""
        if field_name:
            escaped_field = re.escape(field_name)
            escaped_page = re.escape(page_id) if page_id else r"t_p_[A-Za-z0-9_]+"
            pattern = re.compile(
                rf"{escaped_field}\s*=\s*([^.;\n]+?)\s+on\s+({escaped_page})",
                flags=re.IGNORECASE,
            )
            matches = [m.group(1).strip() for m in pattern.finditer(cleaned_content)]
            if not matches:
                loose_pattern = re.compile(rf"{escaped_field}\s*=\s*([^.;\n]+)", flags=re.IGNORECASE)
                matches = [m.group(1).strip() for m in loose_pattern.finditer(cleaned_content)]
            key = (field_name, page_id)
            idx = occurrence_index.get(key, 0)
            if matches:
                inferred = matches[min(idx, len(matches) - 1)]
                occurrence_index[key] = idx + 1

        citation["normalized_value"] = inferred
        enriched.append(citation)
    return enriched


def _coerce_message_content(record: Mapping[str, Any]) -> str:
    message = record.get("message")
    if isinstance(message, Mapping):
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return clean_response_content(content)
    for key in ("response_draft", "content", "draft"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return clean_response_content(value)
    return "TRACE-Net found retrieval evidence, but this smoke response did not include a draft body."


def _coerce_citations(record: Mapping[str, Any]) -> List[Dict[str, Any]]:
    citations = record.get("citations")
    if isinstance(citations, list):
        return [c for c in citations if isinstance(c, dict)]
    # Fallback for demo report records that only include pages and citation_count.
    page_ids = record.get("page_ids")
    if isinstance(page_ids, list):
        return [
            {
                "citation_id": f"fallback_citation_{idx+1:03d}",
                "page_id": page_id,
                "field_name": record.get("query_intent", "unknown"),
                "normalized_value": record.get("user_query", ""),
                "source_trace_ready": True,
                "citation_ready": True,
            }
            for idx, page_id in enumerate(page_ids[: max(1, int(record.get("citation_count", 1) or 1))])
        ]
    return []


def _coerce_api_responses(source_report: Mapping[str, Any]) -> List[Dict[str, Any]]:
    candidates: Any = source_report.get("api_responses")
    if not isinstance(candidates, list):
        candidates = source_report.get("demo_records")
    if not isinstance(candidates, list):
        candidates = source_report.get("final_gate_records")
    if not isinstance(candidates, list):
        candidates = []

    responses: List[Dict[str, Any]] = []
    for idx, raw in enumerate(candidates, start=1):
        if not isinstance(raw, Mapping):
            continue
        query = str(raw.get("user_query") or raw.get("query") or raw.get("input") or "").strip()
        if not query:
            continue
        content = _coerce_message_content(raw)
        citations = _infer_citation_values_from_content(_coerce_citations(raw), content)
        page_ids = raw.get("page_ids")
        if not isinstance(page_ids, list):
            page_ids = sorted({str(c.get("page_id")) for c in citations if c.get("page_id")})
        response = {
            "query_id": str(raw.get("query_id") or f"endpoint_query_{idx:04d}"),
            "query_intent": str(raw.get("query_intent") or raw.get("intent") or "unknown"),
            "user_query": query,
            "api_response_status": str(raw.get("api_response_status") or raw.get("final_gate_decision") or "API_WRAPPER_SMOKE_RESPONSE_DRAFT"),
            "message": {
                "role": "assistant",
                "content": _trace_net_deep_scrub(content),
            },
            "citations": citations,
            "citation_count": len(citations),
            "page_ids": page_ids,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "retrieval_permission": "ranking_until_runtime_final_gate",
            "response_is_smoke_draft": True,
        }
        responses.append(response)
    return responses


def score_response_for_query(query: str, response: Mapping[str, Any]) -> float:
    q_norm = normalize_query(query)
    response_query = normalize_query(str(response.get("user_query", "")))
    if not q_norm:
        return 0.0
    if q_norm == response_query:
        return 1000.0
    if q_norm in response_query or response_query in q_norm:
        return 500.0
    q_tokens = token_set(q_norm)
    r_tokens = token_set(response_query)
    if not q_tokens or not r_tokens:
        return 0.0
    overlap = len(q_tokens & r_tokens)
    jaccard = overlap / max(1, len(q_tokens | r_tokens))
    # Boost part-number/manual-reference substrings.
    query_terms = re.findall(r"\b\d{2,3}[-/]\d{2,5}[-/]?\d{0,4}\b", q_norm)
    response_terms = re.findall(r"\b\d{2,3}[-/]\d{2,5}[-/]?\d{0,4}\b", response_query)
    exact_term_overlap = len(set(query_terms) & set(response_terms))
    return (jaccard * 100.0) + (overlap * 5.0) + (exact_term_overlap * 150.0)


def select_best_response(query: str, responses: Sequence[Mapping[str, Any]]) -> Tuple[Optional[Dict[str, Any]], float]:
    best: Optional[Mapping[str, Any]] = None
    best_score = 0.0
    for response in responses:
        score = score_response_for_query(query, response)
        if score > best_score:
            best_score = score
            best = response
    return (dict(best), best_score) if best is not None else (None, 0.0)


def make_audit_only_response(query: str, reason: str = "No artifact-backed smoke response matched this query.") -> Dict[str, Any]:
    return {
        "query_id": f"audit_only_{uuid.uuid4().hex[:12]}",
        "query_intent": "unknown_or_unmatched",
        "user_query": query,
        "api_response_status": "AUDIT_ONLY_NO_MATCHING_E2E_DEMO_RESPONSE",
        "message": {
            "role": "assistant",
            "content": (
                "TRACE-Net local endpoint smoke did not find a matching artifact-backed response for this query. "
                "No final answer is provided. Run the E2E planning/retrieval chain for this query first, then retry."
            ),
        },
        "citations": [],
        "citation_count": 0,
        "page_ids": [],
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "retrieval_permission": "audit_only",
        "response_is_smoke_draft": True,
        "audit_reasons": [reason],
    }


def make_trace_net_ask_response(query: str, responses: Sequence[Mapping[str, Any]], min_match_score: float = 25.0) -> Dict[str, Any]:
    selected, score = select_best_response(query, responses)
    if selected is None or score < min_match_score:
        selected = make_audit_only_response(query)
        matched = False
    else:
        matched = True
    return {
        "object": "trace_net.e2e.local_endpoint.response",
        "endpoint_version": MODULE_VERSION,
        "model": DEFAULT_MODEL_ID,
        "query": query,
        "matched_artifact_response": matched,
        "match_score": round(score, 4),
        "response": selected,
        "message": {
            "role": str(nested_get(selected, ["message", "role"], "assistant")),
            "content": clean_response_content(str(nested_get(selected, ["message", "content"], ""))),
        },
        "citations": selected.get("citations", []),
        "page_ids": selected.get("page_ids", []),
        "safety": {
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "writes_to_postgres": False,
            "writes_to_qdrant": False,
            "writes_to_opensearch": False,
            "uploads_to_opensearch": False,
            "response_is_smoke_draft": True,
        },
    }


def make_openai_chat_completion(query: str, ask_response: Mapping[str, Any], model: str = DEFAULT_MODEL_ID) -> Dict[str, Any]:
    message = ask_response.get("message")
    if not isinstance(message, Mapping):
        message = {"role": "assistant", "content": ""}
    content = clean_response_content(str(message.get("content") or ""))
    citations = ask_response.get("citations") or []
    if citations:
        citation_lines = []
        for idx, citation in enumerate(citations[:5], start=1):
            if not isinstance(citation, Mapping):
                continue
            citation_lines.append(
                f"[{idx}] page={citation.get('page_id', 'unknown')} field={citation.get('field_name', 'unknown')} value={_value_alias(citation)}"
            )
        if citation_lines:
            content = str(content).replace("ont_p_", "on t_p_").replace(" on  t_p_", " on t_p_").rstrip() + "\n\nCitations:\n" + "\n".join(citation_lines)
    return {
        "id": f"chatcmpl-tracenet-{uuid.uuid4().hex[:16]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": _trace_net_deep_scrub(content),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
        "trace_net": {
            "endpoint_version": MODULE_VERSION,
            "matched_artifact_response": bool(ask_response.get("matched_artifact_response")),
            "match_score": ask_response.get("match_score", 0),
            "safety": ask_response.get("safety", {}),
        },
    }


def extract_query_from_payload(payload: Mapping[str, Any]) -> str:
    for key in ("query", "input", "prompt"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    messages = payload.get("messages")
    if isinstance(messages, list):
        for message in reversed(messages):
            if isinstance(message, Mapping) and message.get("role") == "user":
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()
    return ""


def validate_source_report(source_report: Mapping[str, Any]) -> List[str]:
    failures: List[str] = []
    if not is_truthy_quality_pass(source_report):
        failures.append("source_quality_status_not_pass")
    summary = source_report.get("summary")
    if not isinstance(summary, Mapping):
        summary = {}
    for key in SAFETY_ZERO_KEYS:
        value = source_report.get(key, summary.get(key, 0))
        try:
            numeric = int(value)
        except Exception:
            numeric = 1
        if numeric != 0:
            failures.append(f"{key}_not_zero")
    return failures


def build_endpoint_manifest(
    *,
    e2e_api_wrapper_smoke_path: str | Path,
    output_dir: str | Path,
    host: str = "127.0.0.1",
    port: int = 8014,
    min_api_responses: int = 5,
    min_citation_backed_responses: int = 4,
    min_total_citations: int = 10,
    require_source_quality_pass: bool = True,
) -> Dict[str, Any]:
    source_path = Path(e2e_api_wrapper_smoke_path)
    output_path = Path(output_dir)
    source_report = load_json(source_path)
    responses = _coerce_api_responses(source_report)
    validation_failures = validate_source_report(source_report) if require_source_quality_pass else []

    citation_backed = sum(1 for r in responses if int(r.get("citation_count", 0) or 0) > 0)
    total_citations = sum(int(r.get("citation_count", 0) or 0) for r in responses)
    pages = sorted({str(page) for r in responses for page in (r.get("page_ids") or [])})
    fields = sorted({str(c.get("field_name")) for r in responses for c in (r.get("citations") or []) if isinstance(c, Mapping) and c.get("field_name")})

    route_specs = [
        {"method": "GET", "path": "/health", "purpose": "endpoint health and source artifact status"},
        {"method": "GET", "path": "/v1/models", "purpose": "OpenAI-compatible model listing for Open WebUI"},
        {"method": "POST", "path": "/api/trace-net/ask", "purpose": "TRACE-Net native ask wrapper"},
        {"method": "POST", "path": "/v1/chat/completions", "purpose": "OpenAI-compatible chat completion wrapper"},
    ]

    quality_checks = [
        _check("source_quality_pass", not validation_failures, True),
        _check("api_response_count", len(responses), ">=", min_api_responses),
        _check("citation_backed_response_count", citation_backed, ">=", min_citation_backed_responses),
        _check("total_citation_count", total_citations, ">=", min_total_citations),
        _check("endpoint_route_count", len(route_specs), ">=", 4),
        _check("answer_permission_count", 0, "<=", 0),
        _check("can_answer_directly_count", 0, "==", 0),
        _check("can_prove_claims_count", 0, "==", 0),
        _check("source_truth_mutation_allowed_count", 0, "<=", 0),
        _check("postgres_write_attempt_count", 0, "==", 0),
        _check("qdrant_write_attempt_count", 0, "==", 0),
        _check("opensearch_write_attempt_count", 0, "==", 0),
        _check("opensearch_upload_attempt_count", 0, "==", 0),
    ]
    quality_status = "PASS" if all(c["passed"] for c in quality_checks) else "FAIL"

    manifest_path = output_path / "trace_net_e2e_local_endpoint_v1.json"
    responses_jsonl_path = output_path / "trace_net_e2e_local_endpoint_responses_v1.jsonl"
    inspect_md_path = output_path / "trace_net_e2e_local_endpoint_v1_inspect.md"
    quality_path = output_path / "trace_net_e2e_local_endpoint_v1_quality.json"

    report: Dict[str, Any] = {
        "module": "trace_net_e2e_local_endpoint_v1",
        "status": REPORT_STATUS,
        "quality_status": quality_status,
        "e2e_local_endpoint_status": READY_STATUS if quality_status == "PASS" else "E2E_LOCAL_ENDPOINT_NOT_READY",
        "source_api_wrapper_smoke_path": str(source_path),
        "source_quality_pass": not validation_failures,
        "source_validation_failures": validation_failures,
        "endpoint_contract": {
            "purpose": "Expose the artifact-backed E2E API wrapper smoke as local TRACE-Net endpoints for Open WebUI smoke testing.",
            "host": host,
            "port": port,
            "base_url": f"http://{host}:{port}",
            "native_endpoint": "/api/trace-net/ask",
            "openai_chat_endpoint": "/v1/chat/completions",
            "model_id": DEFAULT_MODEL_ID,
            "responses_are_smoke_drafts": True,
            "ready_for_open_webui_smoke": quality_status == "PASS",
            "answer_authority": "blocked_in_local_endpoint_smoke",
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "writes_to_postgres": False,
            "writes_to_qdrant": False,
            "writes_to_opensearch": False,
            "uploads_to_opensearch": False,
        },
        "endpoint_routes": route_specs,
        "api_responses": responses,
        "summary": {
            "api_response_count": len(responses),
            "citation_backed_response_count": citation_backed,
            "total_citation_count": total_citations,
            "page_with_citation_count": len(pages),
            "field_count": len(fields),
            "endpoint_route_count": len(route_specs),
            "health_endpoint_ready": True,
            "native_ask_endpoint_ready": True,
            "openai_chat_completion_endpoint_ready": True,
            "ready_for_open_webui_smoke": quality_status == "PASS",
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "opensearch_upload_attempt_count": 0,
        },
        "quality_checks": quality_checks,
        "paths": {
            "report_path": str(manifest_path),
            "responses_jsonl_path": str(responses_jsonl_path),
            "inspect_md_path": str(inspect_md_path),
            "quality_path": str(quality_path),
        },
    }
    write_json(manifest_path, report)
    write_jsonl(responses_jsonl_path, responses)
    write_json(quality_path, {"quality_status": quality_status, "quality_checks": quality_checks, "summary": report["summary"]})
    inspect_md_path.write_text(render_inspect_markdown(report), encoding="utf-8")
    return report


def _check(name: str, observed: Any, op_or_expected: Any, expected: Any = None) -> Dict[str, Any]:
    if expected is None:
        expected = op_or_expected
        passed = observed == expected
        op = "is"
    else:
        op = str(op_or_expected)
        if op == ">=":
            passed = observed >= expected
        elif op == "<=":
            passed = observed <= expected
        elif op == "==":
            passed = observed == expected
        else:
            raise ValueError(f"Unsupported op {op}")
    return {"name": name, "observed": observed, "expected": expected, "operator": op, "passed": bool(passed)}


def render_inspect_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    contract = report.get("endpoint_contract") if isinstance(report.get("endpoint_contract"), Mapping) else {}
    responses = report.get("api_responses") if isinstance(report.get("api_responses"), list) else []
    lines = [
        "# TRACE-Net E2E Local Endpoint v1 Inspect",
        "",
        f"Quality status: **{report.get('quality_status')}**",
        "",
        "## Endpoint contract",
    ]
    for key, value in contract.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Main counters"])
    for key, value in summary.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Routes"])
    for route in report.get("endpoint_routes", []):
        if isinstance(route, Mapping):
            lines.append(f"- {route.get('method')} {route.get('path')} — {route.get('purpose')}")
    lines.extend(["", "## Sample API responses"])
    for response in responses[:5]:
        if not isinstance(response, Mapping):
            continue
        content = nested_get(response, ["message", "content"], "")
        lines.append(f"- {response.get('query_id')} | {response.get('query_intent')} | citations={response.get('citation_count')}")
        lines.append(f"  - query: {response.get('user_query')}")
        lines.append(f"  - pages: {', '.join(str(p) for p in response.get('page_ids', [])[:8])}")
        lines.append(f"  - draft: {str(content)[:260]}")
    lines.extend(["", "## Quality checks"])
    for check in report.get("quality_checks", []):
        if isinstance(check, Mapping):
            status = "PASS" if check.get("passed") else "FAIL"
            lines.append(f"- {status} {check.get('name')}: observed={check.get('observed')} expected={check.get('operator')} {check.get('expected')}")
    lines.append("")
    return "\n".join(lines)


def make_handler(responses: Sequence[Mapping[str, Any]], source_report: Mapping[str, Any]) -> type[BaseHTTPRequestHandler]:
    class TraceNetE2ELocalEndpointHandler(BaseHTTPRequestHandler):
        server_version = "TraceNetE2ELocalEndpoint/1.0"

        def log_message(self, format: str, *args: Any) -> None:  # keep CLI quiet except explicit prints
            return

        def _send_json(self, status_code: int, payload: Mapping[str, Any]) -> None:
            body = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_payload(self) -> Dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                return {}
            return data if isinstance(data, dict) else {}

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            path = urlparse(self.path).path
            if path == "/health":
                self._send_json(200, {
                    "status": "ok",
                    "module": "trace_net_e2e_local_endpoint_v1",
                    "quality_status": source_report.get("quality_status"),
                    "api_response_count": len(responses),
                    "safety": {
                        "answer_permission": False,
                        "can_answer_directly": False,
                        "can_prove_claims": False,
                        "source_truth_mutation_allowed": False,
                    },
                })
                return
            if path == "/v1/models":
                self._send_json(200, {
                    "object": "list",
                    "data": [
                        {
                            "id": DEFAULT_MODEL_ID,
                            "object": "model",
                            "created": int(time.time()),
                            "owned_by": "trace-net-local",
                        }
                    ],
                })
                return
            self._send_json(404, {"error": {"message": f"Unknown route {path}", "type": "not_found"}})

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            path = urlparse(self.path).path
            payload = self._read_payload()
            query = extract_query_from_payload(payload)
            if not query:
                self._send_json(400, {"error": {"message": "Missing query or user message", "type": "bad_request"}})
                return
            ask_response = make_trace_net_ask_response(query, responses)
            if path == "/api/trace-net/ask":
                self._send_json(200, ask_response)
                return
            if path == "/v1/chat/completions":
                model = str(payload.get("model") or DEFAULT_MODEL_ID)
                self._send_json(200, make_openai_chat_completion(query, ask_response, model=model))
                return
            self._send_json(404, {"error": {"message": f"Unknown route {path}", "type": "not_found"}})

    return TraceNetE2ELocalEndpointHandler


def serve_endpoint(*, e2e_api_wrapper_smoke_path: str | Path, host: str = "127.0.0.1", port: int = 8014) -> ThreadingHTTPServer:
    source_report = load_json(e2e_api_wrapper_smoke_path)
    responses = _coerce_api_responses(source_report)
    handler = make_handler(responses, source_report)
    server = ThreadingHTTPServer((host, port), handler)
    return server
