#!/usr/bin/env python3
"""Serve TRACE-Net NHA N7 shadow or N8 gated OpenAI-compatible sidecar."""
from __future__ import annotations

import argparse
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trace_net.graph.trace_net_nha_phase7_8_runtime_v1 import (
    MODULE,
    NHAIntegrationAdapter,
    extract_answer,
    extract_user_query,
    http_json,
    load_real_engine,
    openai_completion,
    stream_body,
)

DEFAULT_PUBLIC_MODEL = "trace-net-gemma4-cognitive-rag-nha-v1"
DEFAULT_UPSTREAM_MODEL = "trace-net-gemma4-cognitive-rag-v1"


def error_payload(message: str, code: str) -> dict[str, Any]:
    return {"error": {"message": message, "type": "trace_net_error", "param": None, "code": code}}


class Runtime:
    def __init__(
        self,
        *,
        adapter: NHAIntegrationAdapter,
        upstream_url: str,
        upstream_api_key: str,
        public_api_key: str,
        public_model: str,
        upstream_model: str,
        timeout: float,
        relationship_count: int,
    ) -> None:
        self.adapter = adapter
        self.upstream_url = upstream_url.rstrip("/")
        self.upstream_api_key = upstream_api_key
        self.public_api_key = public_api_key
        self.public_model = public_model
        self.upstream_model = upstream_model
        self.timeout = timeout
        self.relationship_count = relationship_count

    def health(self) -> dict[str, Any]:
        status, upstream = http_json(
            self.upstream_url + "/health",
            None,
            api_key=self.upstream_api_key,
            timeout=min(8.0, self.timeout),
        )
        upstream_ready = status == 200 and upstream.get("quality_status") == "PASS"
        return {
            "quality_status": "PASS" if upstream_ready and self.relationship_count > 0 else "FAIL",
            "module": MODULE,
            "mode": self.adapter.mode,
            "model": self.public_model,
            "upstream_model": self.upstream_model,
            "upstream_ready": upstream_ready,
            "real_relationship_count": self.relationship_count,
            "synthetic_artifacts_loaded": False,
            "synthetic_identifier_blocked": True,
            "stream_normalization": True,
        }


def make_handler(runtime: Runtime):
    class Handler(BaseHTTPRequestHandler):
        server_version = "TraceNetNHASidecar/1.0"

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
                    "owned_by": "trace-net-nha-local",
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
            query = extract_user_query(payload)
            decision = runtime.adapter.evaluate(query)
            if decision.get("override"):
                answer = str(decision.get("public_answer") or "")
                result = openai_completion(answer, runtime.public_model)
            else:
                upstream_payload = dict(payload)
                upstream_payload["model"] = runtime.upstream_model
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
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    self.close_connection = True
            else:
                self.send_json(200, result)

    return Handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8132)
    parser.add_argument("--mode", choices=("shadow", "gated"), default="shadow")
    parser.add_argument("--phase4-dir", required=True)
    parser.add_argument("--upstream-url", default="http://127.0.0.1:8131")
    parser.add_argument("--upstream-api-key", default="trace-net-openwebui-cognitive")
    parser.add_argument("--public-api-key", default="trace-net-openwebui-cognitive")
    parser.add_argument("--public-model", default=DEFAULT_PUBLIC_MODEL)
    parser.add_argument("--upstream-model", default=DEFAULT_UPSTREAM_MODEL)
    parser.add_argument("--telemetry-path", default="/data/trace_net_runs/nha_phase7_8_runtime_v1/telemetry.jsonl")
    parser.add_argument("--telemetry-include-query", action="store_true")
    parser.add_argument("--max-depth", type=int, default=8)
    parser.add_argument("--timeout-seconds", type=float, default=1200.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    engine, source = load_real_engine(args.phase4_dir, max_depth=args.max_depth)
    adapter = NHAIntegrationAdapter(
        engine,
        mode=args.mode,
        telemetry_path=Path(args.telemetry_path),
        telemetry_include_query=args.telemetry_include_query,
    )
    runtime = Runtime(
        adapter=adapter,
        upstream_url=args.upstream_url,
        upstream_api_key=args.upstream_api_key,
        public_api_key=args.public_api_key,
        public_model=args.public_model,
        upstream_model=args.upstream_model,
        timeout=args.timeout_seconds,
        relationship_count=len(source["relationships"]),
    )
    health = runtime.health()
    if health["quality_status"] != "PASS":
        print(json.dumps(health, indent=2, ensure_ascii=False))
        raise SystemExit("NHA sidecar refused to start because its upstream or N4 artifact is unhealthy")
    server = ThreadingHTTPServer((args.host, args.port), make_handler(runtime))
    print("status=TRACE_NET_NHA_PHASE8_GATED_PROXY_V1_READY")
    print("quality_status=PASS")
    print(f"mode={args.mode}")
    print(f"host={args.host}")
    print(f"port={args.port}")
    print(f"model={args.public_model}")
    print(f"real_relationship_count={len(source['relationships'])}")
    print("synthetic_artifacts_loaded=false")
    print("synthetic_identifier_blocked=true")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
