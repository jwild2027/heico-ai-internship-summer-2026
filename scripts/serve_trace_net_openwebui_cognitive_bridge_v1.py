#!/usr/bin/env python3
"""OpenWebUI streaming bridge for TRACE-Net cognitive Gemma v1."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from scripts.trace_net_h30_cold_start_streaming_v1 import install_bridge_streaming_support

MODULE = "trace_net_openwebui_cognitive_bridge_v1"
DEFAULT_MODEL = "trace-net-gemma4-cognitive-rag-v1"


def error_payload(message: str, code: str) -> Dict[str, Any]:
    return {"error": {"message": message, "type": "trace_net_error", "param": None, "code": code}}


def http_json(url: str, payload: Optional[Mapping[str, Any]], *, api_key: str, timeout: float) -> Tuple[int, Dict[str, Any]]:
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="GET" if data is None else "POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8", errors="replace"))
            return response.status, value if isinstance(value, dict) else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            value = json.loads(raw)
        except Exception:
            value = {"error": raw or str(exc)}
        return exc.code, value if isinstance(value, dict) else {}
    except Exception as exc:
        return 599, {"error": f"{type(exc).__name__}: {exc}"}


def extract_answer(response: Mapping[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
        return ""
    message = choices[0].get("message")
    return str(message.get("content") or "") if isinstance(message, Mapping) else ""


def stream_body(answer: str, model: str) -> bytes:
    completion_id = "chatcmpl-trace-cognitive-" + uuid.uuid4().hex[:16]
    created = int(time.time())
    events = []
    events.append("data: " + json.dumps({
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
    }, ensure_ascii=False) + "\n\n")
    for offset in range(0, len(answer), 240):
        events.append("data: " + json.dumps({
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"content": answer[offset:offset + 240]}, "finish_reason": None}],
        }, ensure_ascii=False) + "\n\n")
    events.append("data: " + json.dumps({
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }, ensure_ascii=False) + "\n\n")
    events.append("data: [DONE]\n\n")
    return "".join(events).encode("utf-8")


class Runtime:
    def __init__(self, *, upstream_url: str, upstream_api_key: str, public_api_key: str, public_model: str, timeout: float) -> None:
        self.upstream_url = upstream_url.rstrip("/")
        self.upstream_api_key = upstream_api_key
        self.public_api_key = public_api_key
        self.public_model = public_model
        self.timeout = timeout

    def health(self) -> Dict[str, Any]:
        status, upstream = http_json(self.upstream_url + "/health", None, api_key=self.upstream_api_key, timeout=min(8.0, self.timeout))
        ready = status == 200 and upstream.get("quality_status") == "PASS"
        return {
            "quality_status": "PASS" if ready else "FAIL",
            "module": MODULE,
            "model": self.public_model,
            "answer_model": upstream.get("answer_model", "gemma4:26b"),
            "upstream_ready": ready,
            "stream_normalization": True,
        }


def make_handler(runtime: Runtime):
    class Handler(BaseHTTPRequestHandler):
        server_version = "TraceNetOpenWebUICognitiveBridge/1.0"

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def authorized(self) -> bool:
            return self.headers.get("Authorization", "") == f"Bearer {runtime.public_api_key}"

        def send_json(self, status: int, payload: Mapping[str, Any]) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            # TRACE_NET_H30_DISCONNECTED_CLIENT_WRITE_GUARD_V1
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/health":
                health = runtime.health()
                self.send_json(200 if health["quality_status"] == "PASS" else 503, health)
                return
            if not self.authorized():
                self.send_json(401, error_payload("Invalid or missing API key.", "unauthorized"))
                return
            if path == "/v1/models":
                self.send_json(200, {"object": "list", "data": [{
                    "id": runtime.public_model,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "trace-net-gemma4-local",
                }]})
                return
            self.send_json(404, error_payload("Route not found.", "not_found"))

        def do_POST(self) -> None:
            if not self.authorized():
                self.send_json(401, error_payload("Invalid or missing API key.", "unauthorized"))
                return
            path = self.path.split("?", 1)[0]
            if path != "/v1/chat/completions":
                self.send_json(404, error_payload("Route not found.", "not_found"))
                return
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
            except ValueError:
                length = 0
            if length <= 0 or length > 2_000_000:
                self.send_json(400, error_payload("Invalid request body.", "invalid_request"))
                return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception as exc:
                self.send_json(400, error_payload(f"Invalid JSON: {exc}", "invalid_json"))
                return
            if not isinstance(payload, dict):
                self.send_json(400, error_payload("JSON body must be an object.", "invalid_request"))
                return

            wants_stream = bool(payload.get("stream"))
            upstream_payload = dict(payload)
            upstream_payload["model"] = "trace-net-gemma4-cognitive-rag-v1"
            upstream_payload["stream"] = False
            status, result = http_json(
                runtime.upstream_url + "/v1/chat/completions",
                upstream_payload,
                api_key=runtime.upstream_api_key,
                timeout=runtime.timeout,
            )
            if status != 200:
                self.send_json(status, result)
                return
            answer = extract_answer(result)
            if not answer:
                self.send_json(502, error_payload("Upstream response did not contain assistant content.", "empty_upstream_answer"))
                return
            result["model"] = runtime.public_model
            if wants_stream:
                body = stream_body(answer, runtime.public_model)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("X-Accel-Buffering", "no")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_json(200, result)

    return Handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=8131)
    parser.add_argument("--upstream-url", default="http://127.0.0.1:8128")
    parser.add_argument("--upstream-api-key", default="trace-net-gemma-cognitive-local")
    parser.add_argument("--public-api-key", default="trace-net-openwebui-cognitive")
    parser.add_argument("--public-model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout-seconds", type=float, default=1200.0)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    runtime = Runtime(
        upstream_url=args.upstream_url,
        upstream_api_key=args.upstream_api_key,
        public_api_key=args.public_api_key,
        public_model=args.public_model,
        timeout=args.timeout_seconds,
    )
    health = runtime.health()
    if health["quality_status"] != "PASS":
        print(json.dumps(health, indent=2))
        raise SystemExit("OpenWebUI cognitive bridge refused to start because upstream is unhealthy")
    server = ThreadingHTTPServer((args.host, args.port), make_handler(runtime))
    print("status=TRACE_NET_OPENWEBUI_COGNITIVE_BRIDGE_V1_READY")
    print("quality_status=PASS")
    print(f"host={args.host}")
    print(f"port={args.port}")
    print(f"model={args.public_model}")
    print("stream_normalization=true")
    server.serve_forever()
    return 0


install_bridge_streaming_support(globals())


if __name__ == "__main__":
    raise SystemExit(main())
