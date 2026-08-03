#!/usr/bin/env python3
"""TRACE-Net full-Gemma user-query canary front door v1.

This wrapper sits in front of an existing unified TRACE-Net canary. Every request:

1. is forwarded to the real unified `/v1/chat/completions` route;
2. keeps the unified route, retrieval, citations, follow-ups, and safety metadata;
3. calls Gemma4 once to write the final user-facing answer;
4. validates that Gemma did not invent identifiers or citation numbers;
5. falls back to the upstream deterministic answer if validation fails.

It is intended for isolated benchmark ports and does not replace the live 8017
service.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

MODULE = "trace_net_full_gemma_user_query_canary_v1"
MODEL_ID = "trace-net-full-gemma-user-query-canary-v1"

PART_RE = re.compile(r"\b\d{2,3}-\d{5}(?:-\d{3})?\b")
MANUAL_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
PAGE_RE = re.compile(r"\bt_p_[A-Za-z0-9_]+\b")
FIGURE_RE = re.compile(
    r"(?<![A-Za-z])(?:figure|fig\.?|-igure)\s*(\d{1,4})"
    r"(?:\s*[,;:-]?\s*sheet\s*(\d{1,3}))?\b",
    re.I,
)
CITATION_RE = re.compile(r"\[(\d{1,3})\]")
DANGEROUS = (
    "interchangeable",
    "approved replacement",
    "safe to install",
    "fit approval",
    "effectivity",
    "eligibility",
    "installation safety",
)


def http_json(
    url: str,
    payload: Optional[Mapping[str, Any]],
    *,
    api_key: Optional[str],
    timeout: float,
) -> Tuple[int, Dict[str, Any], str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method="GET" if data is None else "POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8", errors="replace"))
            return response.status, value if isinstance(value, dict) else {}, ""
    except urllib.error.HTTPError as exc:
        try:
            value = json.loads(exc.read().decode("utf-8", errors="replace"))
        except Exception:
            value = {"error": str(exc)}
        return exc.code, value if isinstance(value, dict) else {}, str(exc)
    except Exception as exc:
        return 599, {}, f"{type(exc).__name__}: {exc}"


def latest_user_text(payload: Mapping[str, Any]) -> str:
    for key in ("query", "question", "input", "prompt"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if not isinstance(message, Mapping):
            continue
        if str(message.get("role") or "").lower() != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, Mapping):
                    value = block.get("text") or block.get("content")
                    if value:
                        parts.append(str(value))
            return "\n".join(parts).strip()
    return ""


def answer_text(response: Mapping[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0] if isinstance(choices[0], Mapping) else {}
    message = first.get("message") if isinstance(first.get("message"), Mapping) else {}
    return str(message.get("content") or "").strip()


def trace_payload(response: Mapping[str, Any]) -> Dict[str, Any]:
    value = response.get("trace_net")
    return dict(value) if isinstance(value, Mapping) else {}


def allowed_figure_refs(blob: str) -> set[str]:
    values = set()
    for match in FIGURE_RE.finditer(blob):
        number = match.group(1)
        values.add(f"figure {number}".lower())
        if match.group(2):
            values.add(f"figure {number} sheet {match.group(2)}".lower())
    return values


def validate_composed_answer(
    draft: str,
    *,
    upstream_answer: str,
    trace: Mapping[str, Any],
) -> List[str]:
    failures: List[str] = []
    text = str(draft or "").strip()
    if not text:
        return ["empty_composer_draft"]
    if text.startswith("{") or "TRACE-NET LIVE CONTEXT PACK" in text:
        failures.append("prompt_or_json_leak")

    evidence_blob = upstream_answer + " " + json.dumps(trace, ensure_ascii=False)
    allowed_parts = set(PART_RE.findall(evidence_blob))
    allowed_manuals = set(MANUAL_RE.findall(evidence_blob))
    allowed_pages = set(PAGE_RE.findall(evidence_blob))
    allowed_figures = allowed_figure_refs(evidence_blob)

    for value in PART_RE.findall(text):
        if value not in allowed_parts:
            failures.append(f"unsupported_part_number:{value}")
    for value in MANUAL_RE.findall(text):
        if value not in allowed_manuals:
            failures.append(f"unsupported_manual_reference:{value}")
    for value in PAGE_RE.findall(text):
        if value not in allowed_pages:
            failures.append(f"unsupported_page_id:{value}")
    for match in FIGURE_RE.finditer(text):
        number_only = f"figure {match.group(1)}".lower()
        with_sheet = (
            f"figure {match.group(1)} sheet {match.group(2)}".lower()
            if match.group(2)
            else ""
        )
        if number_only not in allowed_figures:
            failures.append(
                f"unsupported_figure_reference:figure {match.group(1)}"
                + (f" sheet {match.group(2)}" if match.group(2) else "")
            )
        elif with_sheet and with_sheet not in allowed_figures:
            failures.append(
                f"unsupported_figure_sheet:figure {match.group(1)} sheet {match.group(2)}"
            )

    citations = trace.get("citations")
    allowed_ids = {
        int(row.get("citation_id"))
        for row in citations
        if isinstance(citations, list)
        and isinstance(row, Mapping)
        and str(row.get("citation_id") or "").isdigit()
    }
    used_ids = {int(value) for value in CITATION_RE.findall(text)}
    if not used_ids.issubset(allowed_ids):
        failures.append("unsupported_citation_id")
    return failures


def preserve_sources(composed: str, upstream_answer: str) -> str:
    marker = "\n\nSources:\n"
    if marker not in upstream_answer or "Sources:" in composed:
        return composed
    raw_lines = upstream_answer.split(marker, 1)[1].strip().splitlines()
    compact=[]
    for raw in raw_lines[:10]:
        line=re.sub(r"\s+"," ",raw).strip()
        compact.append(line[:357].rstrip()+"..." if len(line)>360 else line)
    return composed.rstrip()+"\n\nSources:\n"+"\n".join(compact) if compact else composed


def append_followups(composed: str, questions: Sequence[str], *, should_append: bool) -> str:
    if not should_append:
        return composed
    body=re.sub(r"\s+"," ",composed.lower());clean=[];seen=set()
    for raw in questions:
        question=str(raw or "").strip();norm=re.sub(r"[^a-z0-9]+"," ",question.lower()).strip()
        if not norm or norm in seen:continue
        seen.add(norm);keywords=[w for w in norm.split() if len(w)>=5][:5]
        if keywords and sum(w in body for w in keywords)>=max(2,len(keywords)-1):continue
        clean.append(question)
    if not clean:return composed
    return "\n".join([composed.rstrip(),"","Helpful follow-up questions:"]+[f"- {q}" for q in clean[:5]]).strip()


def preserve_safety_boundary(composed: str, upstream_answer: str) -> str:
    marker = "Safety boundary:"
    if marker not in upstream_answer or marker in composed:
        return composed
    boundary = upstream_answer[upstream_answer.index(marker):].strip()
    return composed.rstrip() + "\n\n" + boundary


def compose_with_gemma(
    *,
    query: str,
    upstream_answer: str,
    trace: Mapping[str, Any],
    base_url: str,
    model: str,
    api_key: str,
    timeout: float,
) -> Tuple[str, Dict[str, Any]]:
    route = str(trace.get("route") or "")
    tunnel = str(trace.get("retrieval_tunnel") or "")
    followups = list(trace.get("follow_up_questions") or [])
    citations = list(trace.get("citations") or [])

    system = (
        "You are TRACE-Net's final response writer. Answer the user's exact query "
        "using only the validated TRACE-Net result supplied below. Do not invent "
        "part numbers, ATA/manual references, pages, figures, citations, candidates, "
        "approval, fit, effectivity, interchangeability, eligibility, or safety "
        "claims. Preserve uncertainty and no-evidence conclusions. Candidate and "
        "visual results are guidance only. Do not restate the supplied follow-up questions in your prose; TRACE-Net appends them once. "
        "Do not pretend a "
        "part has been identified. Do not output JSON or internal metadata."
    )
    context = {
        "user_query": query,
        "route": route,
        "retrieval_tunnel": tunnel,
        "validated_upstream_answer": upstream_answer,
        "citations": citations[:10],
        "required_follow_up_questions": followups[:5],
        "clarification_required": bool(trace.get("clarification_required")),
        "clarification_recommended": bool(trace.get("clarification_recommended")),
        "final_gate_status": trace.get("final_gate_status"),
        "safety_boundary_required": any(term in query.lower() for term in DANGEROUS),
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": "Write the final user-facing answer from this validated context:\n"
                + json.dumps(context, ensure_ascii=False, indent=2),
            },
        ],
        "temperature": 0,
        "stream": False,
    }

    start = time.perf_counter()
    status, response, error = http_json(
        base_url.rstrip("/") + "/chat/completions",
        payload,
        api_key=api_key,
        timeout=timeout,
    )
    latency_ms = round((time.perf_counter() - start) * 1000.0, 3)
    draft = answer_text(response)
    failures = validate_composed_answer(
        draft,
        upstream_answer=upstream_answer,
        trace=trace,
    )
    metadata = {
        "called": True,
        "status_code": status,
        "status": (
            "LLM_CALL_SUCCEEDED"
            if status == 200 and draft and not failures
            else "LLM_DRAFT_REJECTED_DETERMINISTIC_FALLBACK"
            if status == 200
            else "LLM_CALL_FAILED_DETERMINISTIC_FALLBACK"
        ),
        "model": model,
        "latency_ms": latency_ms,
        "validation_failures": failures,
        "error": error,
        "draft_preview": draft[:500],
    }
    if status != 200 or failures:
        return "", metadata

    draft = preserve_sources(draft, upstream_answer)
    should_append_followups = bool(
        trace.get("clarification_required")
        or trace.get("clarification_recommended")
        or route == "guided_discovery"
    )
    draft = append_followups(
        draft,
        followups,
        should_append=should_append_followups,
    )
    draft = preserve_safety_boundary(draft, upstream_answer)
    return draft, metadata


class Runtime:
    def __init__(
        self,
        *,
        upstream_base_url: str,
        upstream_api_key: str,
        api_key: str,
        gemma_base_url: str,
        gemma_model: str,
        gemma_api_key: str,
        timeout: float,
        max_request_bytes: int,
        max_concurrency: int,
    ):
        self.upstream_base_url = upstream_base_url.rstrip("/")
        self.upstream_api_key = upstream_api_key
        self.api_key = api_key
        self.gemma_base_url = gemma_base_url.rstrip("/")
        self.gemma_model = gemma_model
        self.gemma_api_key = gemma_api_key
        self.timeout = timeout
        self.max_request_bytes = max_request_bytes
        self.semaphore = threading.BoundedSemaphore(max(1, max_concurrency))

    def health(self) -> Dict[str, Any]:
        status, upstream, error = http_json(
            self.upstream_base_url + "/health",
            None,
            api_key=None,
            timeout=min(self.timeout, 5.0),
        )
        upstream_ok = (
            status == 200
            and upstream.get("module") == "trace_net_openwebui_unified_rag_v2"
            and upstream.get("quality_status") == "PASS"
        )
        return {
            "status": "ok" if upstream_ok else "needs_repair",
            "quality_status": "PASS" if upstream_ok else "FAIL",
            "module": MODULE,
            "model_id": MODEL_ID,
            "upstream": {
                "base_url": self.upstream_base_url,
                "status_code": status,
                "identity_ok": upstream_ok,
                "error": error,
            },
            "response_composer": {
                "enabled": True,
                "base_url": self.gemma_base_url,
                "model": self.gemma_model,
                "every_query": True,
            },
            "answer_permission": False,
            "final_answer_allowed": False,
            "source_truth_mutation_allowed": False,
        }

    def process(self, payload: Mapping[str, Any]) -> Tuple[int, Dict[str, Any]]:
        query = latest_user_text(payload)
        status, upstream, upstream_error = http_json(
            self.upstream_base_url + "/v1/chat/completions",
            payload,
            api_key=self.upstream_api_key,
            timeout=self.timeout,
        )
        if status != 200:
            return status, upstream or {
                "error": {
                    "message": upstream_error or "Upstream TRACE-Net failed.",
                    "type": "trace_net_upstream_error",
                }
            }

        upstream_answer = answer_text(upstream)
        trace = trace_payload(upstream)
        composed, metadata = compose_with_gemma(
            query=query,
            upstream_answer=upstream_answer,
            trace=trace,
            base_url=self.gemma_base_url,
            model=self.gemma_model,
            api_key=self.gemma_api_key,
            timeout=self.timeout,
        )
        final_answer = composed or upstream_answer

        followups = list(trace.get("follow_up_questions") or [])
        should_append_followups = bool(
            trace.get("clarification_required")
            or trace.get("clarification_recommended")
            or str(trace.get("route") or "") == "guided_discovery"
        )
        final_answer = append_followups(
            final_answer,
            followups,
            should_append=should_append_followups,
        )
        final_answer = preserve_safety_boundary(final_answer, upstream_answer)

        choices = upstream.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0] if isinstance(choices[0], Mapping) else {}
            message = first.get("message") if isinstance(first.get("message"), Mapping) else {}
            updated_message = dict(message)
            updated_message["role"] = "assistant"
            updated_message["content"] = final_answer
            updated_first = dict(first)
            updated_first["message"] = updated_message
            updated_choices = list(choices)
            updated_choices[0] = updated_first
            upstream["choices"] = updated_choices

        trace.update({
            "full_user_query_canary_module": MODULE,
            "response_composer_enabled": True,
            "response_composer_called": bool(metadata.get("called")),
            "response_composer_status": metadata.get("status"),
            "response_composer_model": metadata.get("model"),
            "response_composer_latency_ms": metadata.get("latency_ms"),
            "response_composer_validation_failures": metadata.get("validation_failures"),
            "response_composer_error": metadata.get("error"),
            "response_composer_draft_preview": metadata.get("draft_preview"),
            "upstream_answer_preserved_as_fallback": not bool(composed),
            "answer_permission": False,
            "final_answer_allowed": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
        })
        upstream["trace_net"] = trace
        upstream["model"] = MODEL_ID
        upstream["id"] = "chatcmpl-trace-full-gemma-" + uuid.uuid4().hex[:16]
        return 200, upstream


def openai_error(message: str, code: str, status: int) -> Dict[str, Any]:
    return {
        "error": {
            "message": message,
            "type": "trace_net_error",
            "param": None,
            "code": code,
        },
        "status": status,
    }


def make_handler(runtime: Runtime):
    class Handler(BaseHTTPRequestHandler):
        server_version = "TraceNetFullGemmaUserQueryCanaryV1/1.0"

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def send_json(self, status: int, payload: Mapping[str, Any]) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def authorized(self) -> bool:
            return self.headers.get("Authorization", "") == f"Bearer {runtime.api_key}"

        def read_payload(self) -> Tuple[Optional[Dict[str, Any]], Optional[Tuple[int, Dict[str, Any]]]]:
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
            except ValueError:
                length = 0
            if length <= 0:
                return None, (400, openai_error("Request body is required.", "invalid_request", 400))
            if length > runtime.max_request_bytes:
                return None, (413, openai_error("Request body is too large.", "request_too_large", 413))
            try:
                value = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception as exc:
                return None, (400, openai_error(f"Invalid JSON: {exc}", "invalid_json", 400))
            if not isinstance(value, dict):
                return None, (400, openai_error("JSON body must be an object.", "invalid_request", 400))
            return value, None

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/health":
                health = runtime.health()
                self.send_json(200 if health["quality_status"] == "PASS" else 503, health)
                return
            if not self.authorized():
                self.send_json(401, openai_error("Invalid or missing API key.", "unauthorized", 401))
                return
            if path == "/v1/models":
                self.send_json(200, {
                    "object": "list",
                    "data": [{
                        "id": MODEL_ID,
                        "object": "model",
                        "created": int(time.time()),
                        "owned_by": "trace-net-local",
                    }],
                })
                return
            self.send_json(404, openai_error("Route not found.", "not_found", 404))

        def do_POST(self) -> None:
            if not self.authorized():
                self.send_json(401, openai_error("Invalid or missing API key.", "unauthorized", 401))
                return
            if not runtime.semaphore.acquire(blocking=False):
                self.send_json(429, openai_error("Full-Gemma canary is busy.", "rate_limit", 429))
                return
            try:
                payload, error = self.read_payload()
                if error:
                    self.send_json(*error)
                    return
                assert payload is not None
                if not latest_user_text(payload):
                    self.send_json(400, openai_error("Missing user query.", "missing_query", 400))
                    return
                path = self.path.split("?", 1)[0]
                if path not in {"/v1/chat/completions", "/api/trace-net/ask"}:
                    self.send_json(404, openai_error("Route not found.", "not_found", 404))
                    return
                status, response = runtime.process(payload)
                self.send_json(status, response)
            except Exception as exc:
                self.send_json(500, openai_error(f"{type(exc).__name__}: {exc}", "internal_error", 500))
            finally:
                runtime.semaphore.release()

    return Handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8127)
    parser.add_argument("--upstream-base-url", default="http://127.0.0.1:8117")
    parser.add_argument("--upstream-api-key", default="trace-net-canary-local")
    parser.add_argument(
        "--api-key",
        default=os.environ.get(
            "TRACE_NET_FULL_GEMMA_CANARY_API_KEY",
            "trace-net-user-query-canary",
        ),
    )
    parser.add_argument("--gemma-base-url", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--gemma-model", default="gemma4:26b")
    parser.add_argument("--gemma-api-key", default="ollama")
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument("--max-request-bytes", type=int, default=1_000_000)
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=1,
        help="Keep at 1 for a serial GPU benchmark.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    runtime = Runtime(
        upstream_base_url=args.upstream_base_url,
        upstream_api_key=args.upstream_api_key,
        api_key=args.api_key,
        gemma_base_url=args.gemma_base_url,
        gemma_model=args.gemma_model,
        gemma_api_key=args.gemma_api_key,
        timeout=args.timeout_seconds,
        max_request_bytes=args.max_request_bytes,
        max_concurrency=args.max_concurrency,
    )
    health = runtime.health()
    if health["quality_status"] != "PASS":
        print(json.dumps(health, indent=2))
        raise SystemExit("Full-Gemma canary refused to start because the upstream unified canary is unhealthy.")

    server = ThreadingHTTPServer((args.host, args.port), make_handler(runtime))
    print("status=TRACE_NET_FULL_GEMMA_USER_QUERY_CANARY_V1_READY")
    print("quality_status=PASS")
    print(f"host={args.host}")
    print(f"port={args.port}")
    print(f"upstream_base_url={args.upstream_base_url}")
    print(f"gemma_model={args.gemma_model}")
    print("gemma_called_for_every_query=True")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
