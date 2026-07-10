#!/usr/bin/env python3
"""TRACE-Net guided discovery router proxy v2.

A small read-only HTTP proxy that gives the web UI one endpoint while routing to:
- normal TRACE-Net ask/chat endpoint for ordinary questions
- guided candidate discovery endpoint for weak/partial part-number lookup questions

Safety contract:
- no writes to Postgres, Qdrant, OpenSearch, or source artifacts
- guided discovery remains candidate-discovery-only and final_answer_allowed=false
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Iterable, List, Optional, Tuple

STATUS_READY = "TRACE_NET_GUIDED_DISCOVERY_ROUTER_PROXY_V2_READY"
STATUS_DONE = "TRACE_NET_GUIDED_DISCOVERY_ROUTER_PROXY_V2_DONE"
QUALITY_PASS = "PASS"
QUALITY_WARN = "WARN"
QUALITY_FAIL = "FAIL"

DEFAULT_NORMAL_BASE_URL = "http://127.0.0.1:8014"
DEFAULT_GUIDED_BASE_URL = "http://127.0.0.1:8016"
DEFAULT_MODEL = "trace-net-router-proxy-v2"

PART_WORDS = (
    "part",
    "p/n",
    "pn",
    "part number",
    "item number",
    "nomenclature",
    "component",
)
LOW_CONTEXT_MARKERS = (
    "only know",
    "dont know",
    "don't know",
    "do not know",
    "not have the rest",
    "missing the rest",
    "partial",
    "starts with",
    "start with",
    "begins with",
    "begin with",
    "contains",
    "has digits",
    "has numbers",
    "looked like",
    "might be",
)
GUIDED_INTENT_PATTERNS = [
    re.compile(r"\bpart\b.{0,80}\b(start(?:s)?|begin(?:s)?)\s+with\b", re.IGNORECASE),
    re.compile(r"\b(start(?:s)?|begin(?:s)?)\s+with\b.{0,80}\b(part|number|digits?)\b", re.IGNORECASE),
    re.compile(r"\bpart\b.{0,80}\b(contains|has)\b.{0,40}\b(digits?|numbers?|\d{1,6})\b", re.IGNORECASE),
    re.compile(r"\b(only know|not have the rest|missing the rest|partial)\b.{0,120}\b(part|p/n|pn|number)\b", re.IGNORECASE),
]


@dataclass(frozen=True)
class RouteDecision:
    route: str
    reason: str
    confidence: str
    weak_query: bool
    partial_part_lookup: bool


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def latest_user_message(messages: Iterable[Dict[str, Any]]) -> str:
    latest = ""
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", "")).lower()
        if role == "user":
            content = msg.get("content", "")
            if isinstance(content, list):
                parts: List[str] = []
                for item in content:
                    if isinstance(item, dict):
                        if "text" in item:
                            parts.append(str(item.get("text") or ""))
                        elif item.get("type") == "text":
                            parts.append(str(item.get("content") or ""))
                    else:
                        parts.append(str(item))
                latest = "\n".join(p for p in parts if p)
            else:
                latest = str(content)
    return latest.strip()


def extract_question(payload: Dict[str, Any]) -> str:
    for key in ("question", "query", "input", "prompt"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    messages = payload.get("messages")
    if isinstance(messages, list):
        msg = latest_user_message(messages)
        if msg:
            return msg
    return ""


def looks_like_partial_part_lookup(question: str) -> bool:
    q = question.lower()
    if not q:
        return False
    has_part_word = any(word in q for word in PART_WORDS)
    has_low_context = any(marker in q for marker in LOW_CONTEXT_MARKERS)
    if has_part_word and has_low_context:
        return True
    return any(pattern.search(question) for pattern in GUIDED_INTENT_PATTERNS)


def route_question(question: str, requested_mode: Optional[str] = None) -> RouteDecision:
    mode = (requested_mode or "auto").strip().lower()
    if mode in {"guided", "guided_discovery", "candidate_discovery", "guided_candidate_discovery"}:
        return RouteDecision(
            route="guided_discovery",
            reason="requested mode forced guided candidate discovery",
            confidence="high",
            weak_query=True,
            partial_part_lookup=True,
        )
    if mode in {"normal", "ask", "qa", "chat"}:
        return RouteDecision(
            route="normal_ask",
            reason="requested mode forced normal TRACE-Net ask",
            confidence="high",
            weak_query=False,
            partial_part_lookup=False,
        )
    is_guided = looks_like_partial_part_lookup(question)
    if is_guided:
        return RouteDecision(
            route="guided_discovery",
            reason="auto-detected weak or partial part-number lookup",
            confidence="high",
            weak_query=True,
            partial_part_lookup=True,
        )
    return RouteDecision(
        route="normal_ask",
        reason="auto-detected ordinary TRACE-Net question",
        confidence="medium",
        weak_query=False,
        partial_part_lookup=False,
    )


def http_post_json(url: str, payload: Dict[str, Any], timeout_seconds: float = 300.0) -> Tuple[int, Dict[str, Any]]:
    encoded = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=encoded,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:  # nosec B310 - local user-configured endpoint proxy
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError:
                parsed = {"raw_response": raw}
            return int(resp.status), parsed
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            parsed = {"raw_response": raw}
        parsed.setdefault("error", f"HTTPError {exc.code}")
        return int(exc.code), parsed
    except Exception as exc:  # pragma: no cover - network dependent
        return 599, {"error": type(exc).__name__, "message": str(exc)}


def compact_candidate(candidate: Dict[str, Any]) -> str:
    part = candidate.get("candidate_part_number", "unknown")
    nom = candidate.get("nomenclature", "unknown")
    page = candidate.get("page_id", "unknown")
    why = candidate.get("why_matched", "candidate route")
    conf = candidate.get("confidence", "unknown")
    return f"- {part} | {nom} | page {page} | {conf} | {why}"


def guided_payload_to_chat_content(payload: Dict[str, Any]) -> str:
    question = payload.get("question", "")
    strict = payload.get("strict_prefix_candidates") or []
    loose = payload.get("loose_candidates") or []
    clarifying = payload.get("clarifying_questions") or []
    prefix = (payload.get("known_clues") or {}).get("part_prefix")

    lines: List[str] = []
    lines.append("I found possible candidate routes, not a final part identification yet.")
    lines.append(f"Source-trace status: {payload.get('source_trace_status', 'candidate-discovery-only')}")
    lines.append(f"Final answer allowed: {str(payload.get('final_answer_allowed', False)).lower()}")
    if prefix:
        lines.append(f"Requested part prefix: {prefix}")
    lines.append("")
    if clarifying:
        lines.append("Helpful details to narrow this:")
        for idx, question_text in enumerate(clarifying[:5], 1):
            lines.append(f"{idx}. {question_text}")
        lines.append("")
    lines.append(f"Strict prefix candidates: {len(strict)}")
    for candidate in strict[:8]:
        lines.append(compact_candidate(candidate))
    lines.append("")
    lines.append(f"Weaker related candidates: {len(loose)}")
    for candidate in loose[:8]:
        lines.append(compact_candidate(candidate))
    lines.append("")
    lines.append("Safety note: candidate routes are discovery hints only and do not prove eligibility, fit, approval, interchangeability, installation approval, or effectivity.")
    return "\n".join(lines).strip()


def normal_payload_to_chat_content(payload: Dict[str, Any]) -> str:
    for key in ("answer", "content", "message", "response"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            return msg["content"].strip()
    return json.dumps(payload, indent=2)[:12000]


def openai_chat_response(model: str, content: str, routed_payload: Dict[str, Any], route_decision: RouteDecision) -> Dict[str, Any]:
    now = int(time.time())
    return {
        "id": f"trace-net-router-proxy-v2-{now}",
        "object": "chat.completion",
        "created": now,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "trace_net_router": {
            "route": route_decision.route,
            "reason": route_decision.reason,
            "confidence": route_decision.confidence,
            "weak_query": route_decision.weak_query,
            "partial_part_lookup": route_decision.partial_part_lookup,
        },
        "trace_net_payload": routed_payload,
    }


@dataclass
class ServerConfig:
    host: str
    port: int
    normal_base_url: str
    guided_base_url: str
    model: str
    timeout_seconds: float
    default_top_k: int
    default_loose_top_k: int


def build_guided_request(payload: Dict[str, Any], question: str, config: ServerConfig) -> Dict[str, Any]:
    return {
        "question": question,
        "top_k": int(payload.get("top_k") or payload.get("topK") or config.default_top_k),
        "loose_top_k": int(payload.get("loose_top_k") or payload.get("looseTopK") or config.default_loose_top_k),
    }


def build_normal_request(payload: Dict[str, Any], question: str) -> Dict[str, Any]:
    """Build a request compatible with the older normal ask endpoint.

    The E2E normal endpoint has used multiple schema variants across patches.
    In the latest server smoke it rejected a payload containing only
    {"question": ...} with "Missing query or user message".  To keep the
    router stable, send the user text in all accepted read-only shapes:
    - query: used by /api/trace-net/ask
    - question: preserved for newer callers
    - messages: OpenAI-style user message fallback

    Extra fields remain read-only routing metadata and do not grant answer
    permission or source-truth mutation rights.
    """
    normal = dict(payload)
    normal.pop("mode", None)
    normal["query"] = str(normal.get("query") or question)
    normal["question"] = str(normal.get("question") or question)
    if not isinstance(normal.get("messages"), list) or not latest_user_message(normal.get("messages") or []):
        normal["messages"] = [{"role": "user", "content": question}]
    return normal


def route_payload(payload: Dict[str, Any], config: ServerConfig) -> Dict[str, Any]:
    start = time.time()
    question = extract_question(payload)
    if not question:
        return {
            "status": STATUS_DONE,
            "quality_status": QUALITY_FAIL,
            "error": "missing_question",
            "message": "Provide a non-empty question, query, prompt, input, or chat messages payload.",
            "final_answer_allowed": False,
            "elapsed_seconds": round(time.time() - start, 3),
        }
    decision = route_question(question, payload.get("mode"))
    if decision.route == "guided_discovery":
        endpoint = config.guided_base_url.rstrip("/") + "/api/trace-net/guided-discovery"
        downstream_request = build_guided_request(payload, question, config)
    else:
        endpoint = config.normal_base_url.rstrip("/") + "/api/trace-net/ask"
        downstream_request = build_normal_request(payload, question)
    status_code, downstream = http_post_json(endpoint, downstream_request, timeout_seconds=config.timeout_seconds)
    ok = 200 <= status_code < 300 and not downstream.get("error")
    response: Dict[str, Any] = {
        "status": STATUS_DONE,
        "quality_status": QUALITY_PASS if ok else QUALITY_WARN,
        "router": "guided_discovery_router_proxy_v2",
        "route": decision.route,
        "route_reason": decision.reason,
        "route_confidence": decision.confidence,
        "weak_query": decision.weak_query,
        "partial_part_lookup": decision.partial_part_lookup,
        "question": question,
        "downstream_status_code": status_code,
        "downstream_endpoint": endpoint,
        "downstream_request": downstream_request,
        "downstream_response": downstream,
        "final_answer_allowed": bool(downstream.get("final_answer_allowed", False)) if decision.route == "guided_discovery" else bool(downstream.get("final_answer_allowed", downstream.get("can_answer_directly", False))),
        "source_trace_status": downstream.get("source_trace_status"),
        "safety_contract": {
            "read_only": True,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
        "elapsed_seconds": round(time.time() - start, 3),
    }
    if decision.route == "guided_discovery":
        # Surface UI-friendly fields at top level so the web UI does not need to drill into downstream_response.
        for key in (
            "intent",
            "known_clues",
            "missing_clues",
            "clarifying_questions",
            "strict_prefix_candidates",
            "contains_candidates",
            "loose_candidates",
            "candidate_routes",
            "strict_prefix_candidate_count",
            "contains_candidate_count",
            "loose_candidate_count",
            "total_candidate_route_count",
            "evidence_record_count",
            "rejected_noise_token_count",
            "weak_token_count",
            "view_text",
            "output_paths",
        ):
            if key in downstream:
                response[key] = downstream[key]
        response["final_answer_allowed"] = False
        response["source_trace_status"] = downstream.get("source_trace_status", "candidate-discovery-only")
    return response


class RouterProxyHandler(BaseHTTPRequestHandler):
    server_version = "TraceNetGuidedDiscoveryRouterProxyV2/1.0"

    def _config(self) -> ServerConfig:
        return self.server.config  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:  # quieter, still visible for errors if needed
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), fmt % args))

    def _send_json(self, payload: Dict[str, Any], status_code: int = 200) -> None:
        raw = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        if not raw.strip():
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            return {"_json_error": str(exc), "_raw": raw}
        return parsed if isinstance(parsed, dict) else {"input": parsed}

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_json({"status": "ok"})

    def do_GET(self) -> None:  # noqa: N802
        config = self._config()
        if self.path in {"/health", "/api/trace-net/router/health", "/api/trace-net/guided-router/health"}:
            self._send_json(
                {
                    "status": STATUS_READY,
                    "quality_status": QUALITY_PASS,
                    "router": "guided_discovery_router_proxy_v2",
                    "normal_base_url": config.normal_base_url,
                    "guided_base_url": config.guided_base_url,
                    "routes": {
                        "router": "/api/trace-net/router",
                        "chat": "/v1/chat/completions",
                    },
                    "safety_contract": {
                        "read_only": True,
                        "source_truth_mutation_allowed_count": 0,
                        "postgres_write_attempt_count": 0,
                        "qdrant_write_attempt_count": 0,
                        "opensearch_write_attempt_count": 0,
                    },
                }
            )
            return
        self._send_json({"error": "not_found", "path": self.path}, status_code=404)

    def do_POST(self) -> None:  # noqa: N802
        config = self._config()
        payload = self._read_json()
        if payload.get("_json_error"):
            self._send_json({"status": STATUS_DONE, "quality_status": QUALITY_FAIL, "error": "invalid_json", "detail": payload.get("_json_error")}, status_code=400)
            return
        if self.path in {"/api/trace-net/router", "/api/trace-net/guided-router"}:
            routed = route_payload(payload, config)
            code = 200 if routed.get("quality_status") != QUALITY_FAIL else 400
            self._send_json(routed, status_code=code)
            return
        if self.path == "/v1/chat/completions":
            routed = route_payload(payload, config)
            if routed.get("quality_status") == QUALITY_FAIL:
                self._send_json(routed, status_code=400)
                return
            downstream = routed.get("downstream_response") if isinstance(routed.get("downstream_response"), dict) else {}
            decision = RouteDecision(
                route=str(routed.get("route")),
                reason=str(routed.get("route_reason")),
                confidence=str(routed.get("route_confidence")),
                weak_query=bool(routed.get("weak_query")),
                partial_part_lookup=bool(routed.get("partial_part_lookup")),
            )
            if decision.route == "guided_discovery":
                content = guided_payload_to_chat_content(downstream)
            else:
                content = normal_payload_to_chat_content(downstream)
            self._send_json(openai_chat_response(str(payload.get("model") or config.model), content, routed, decision))
            return
        self._send_json({"error": "not_found", "path": self.path}, status_code=404)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve TRACE-Net guided discovery router proxy v2.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8017)
    parser.add_argument("--normal-base-url", default=DEFAULT_NORMAL_BASE_URL)
    parser.add_argument("--guided-base-url", default=DEFAULT_GUIDED_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--loose-top-k", type=int, default=8)
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    config = ServerConfig(
        host=args.host,
        port=args.port,
        normal_base_url=args.normal_base_url.rstrip("/"),
        guided_base_url=args.guided_base_url.rstrip("/"),
        model=args.model,
        timeout_seconds=args.timeout_seconds,
        default_top_k=args.top_k,
        default_loose_top_k=args.loose_top_k,
    )
    server = ThreadingHTTPServer((config.host, config.port), RouterProxyHandler)
    server.config = config  # type: ignore[attr-defined]
    print(f"status={STATUS_READY}")
    print(f"quality_status={QUALITY_PASS}")
    print("router=guided_discovery_router_proxy_v2")
    print(f"url=http://{config.host}:{config.port}/api/trace-net/router")
    print(f"chat=http://{config.host}:{config.port}/v1/chat/completions")
    print(f"normal_base_url={config.normal_base_url}")
    print(f"guided_base_url={config.guided_base_url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping TRACE-Net guided discovery router proxy v2")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
