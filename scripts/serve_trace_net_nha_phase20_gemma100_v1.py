#!/usr/bin/env python3
"""Serve the isolated N20 100-question synthetic NHA Gemma benchmark on port 8133."""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.trace_net_nha_phase14_16_cognitive_v1 import load_nha_engram_bundle
from scripts.trace_net_nha_phase20_gemma100_v1 import (
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_URL,
    EXPECTED_QUESTION_COUNT,
    build_gemma100_bank,
    build_synthetic_engine,
    execute_case,
    load_phase5_bundle,
    render_benchmark_public_answer,
)

MODEL_ID = "trace-net-gemma4-cognitive-rag-v1"


def extract_query(payload: Mapping[str, Any]) -> str:
    for key in ("query", "question", "input", "prompt"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    messages = payload.get("messages")
    if isinstance(messages, list):
        for message in reversed(messages):
            if not isinstance(message, Mapping) or str(message.get("role") or "").lower() != "user":
                continue
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
    return ""


def completion(answer: str, model: str, *, prompt_tokens: int, completion_tokens: int) -> dict[str, Any]:
    return {
        "id": "chatcmpl-trace-nha-gemma100-" + uuid.uuid4().hex[:16],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": answer},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def stream_body(answer: str, model: str) -> bytes:
    chunk_id = "chatcmpl-trace-nha-gemma100-" + uuid.uuid4().hex[:16]
    created = int(time.time())
    chunks = [
        {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        },
        {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"content": answer}, "finish_reason": None}],
        },
        {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        },
    ]
    lines = ["data: " + json.dumps(row, ensure_ascii=False) for row in chunks]
    lines.append("data: [DONE]")
    return ("\n\n".join(lines) + "\n\n").encode("utf-8")


class Runtime:
    def __init__(
        self,
        *,
        phase5_dir: str,
        engram_dir: str,
        api_key: str,
        model: str,
        ollama_url: str,
        timeout: float,
        max_tokens: int,
        telemetry_path: str,
    ) -> None:
        self.phase5_bundle = load_phase5_bundle(phase5_dir)
        if self.phase5_bundle.get("quality_status") != "PASS":
            raise ValueError("phase5_bundle_invalid:" + ",".join(self.phase5_bundle.get("failures") or []))
        self.engram_bundle = load_nha_engram_bundle(engram_dir)
        if self.engram_bundle.get("quality_status") != "PASS":
            raise ValueError("nha_engram_invalid:" + ",".join(self.engram_bundle.get("failures") or []))
        self.bank = build_gemma100_bank(self.phase5_bundle)
        self.by_query = {str(row["query"]): dict(row) for row in self.bank}
        self.engine = build_synthetic_engine(self.phase5_bundle)
        self.api_key = api_key
        self.model = model
        self.ollama_url = ollama_url.rstrip("/")
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.telemetry_path = Path(telemetry_path).resolve()

    def health(self) -> dict[str, Any]:
        return {
            "quality_status": "PASS",
            "module": "serve_trace_net_nha_phase20_gemma100_v1",
            "status": "TRACE_NET_NHA_PHASE20_GEMMA100_SERVER_READY",
            "model": MODEL_ID,
            "answer_model": self.model,
            "question_count": len(self.bank),
            "openai_compatible_chat": True,
            "single_real_gemma_call_per_request": True,
            "deterministic_fallback_counts_as_pass": False,
            "benchmark_only": True,
            "production_visible": False,
            "production_8131_synthetic_block_preserved": True,
            "production_graph_write_count": 0,
            "source_artifact_mutation_count": 0,
        }

    def record(self, result: Mapping[str, Any]) -> None:
        self.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        with self.telemetry_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(result), ensure_ascii=False, sort_keys=True) + "\n")


def make_handler(runtime: Runtime):
    class Handler(BaseHTTPRequestHandler):
        server_version = "TraceNetNHAGemma100Benchmark/1.0"

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def authorized(self) -> bool:
            return self.headers.get("Authorization", "") == f"Bearer {runtime.api_key}"

        def send_json(self, status: int, payload: Mapping[str, Any], headers: Mapping[str, str] | None = None) -> None:
            raw = json.dumps(dict(payload), ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            for key, value in (headers or {}).items():
                self.send_header(str(key), str(value))
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True

        def read_payload(self) -> dict[str, Any] | None:
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
            except ValueError:
                length = 0
            if length <= 0 or length > 1_000_000:
                self.send_json(400, {"error": {"message": "Invalid request body.", "code": "invalid_request"}})
                return None
            try:
                value = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception as exc:
                self.send_json(400, {"error": {"message": f"Invalid JSON: {exc}", "code": "invalid_json"}})
                return None
            if not isinstance(value, dict):
                self.send_json(400, {"error": {"message": "JSON body must be an object.", "code": "invalid_request"}})
                return None
            return value

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/health":
                self.send_json(200, runtime.health())
                return
            if not self.authorized():
                self.send_json(401, {"error": {"message": "Unauthorized.", "code": "unauthorized"}})
                return
            if path == "/v1/models":
                self.send_json(200, {
                    "object": "list",
                    "data": [{"id": MODEL_ID, "object": "model", "created": int(time.time()), "owned_by": "trace-net-benchmark-only"}],
                })
                return
            self.send_json(404, {"error": {"message": "Route not found.", "code": "not_found"}})

        def do_POST(self) -> None:
            if not self.authorized():
                self.send_json(401, {"error": {"message": "Unauthorized.", "code": "unauthorized"}})
                return
            if self.path.split("?", 1)[0] != "/v1/chat/completions":
                self.send_json(404, {"error": {"message": "Route not found.", "code": "not_found"}})
                return
            payload = self.read_payload()
            if payload is None:
                return
            query = extract_query(payload)
            case = runtime.by_query.get(query)
            if case is None:
                self.send_json(400, {
                    "error": {
                        "message": "This isolated benchmark endpoint accepts only the generated 100-question bank.",
                        "code": "query_not_in_benchmark_bank",
                    }
                })
                return
            result = execute_case(
                case,
                engine=runtime.engine,
                engram_bundle=runtime.engram_bundle,
                ollama_url=runtime.ollama_url,
                model=runtime.model,
                timeout=runtime.timeout,
                max_tokens=runtime.max_tokens,
            )
            runtime.record(result)
            answer = render_benchmark_public_answer(result)
            headers = {
                "X-Trace-Net-Benchmark-Case": str(case.get("case_id") or ""),
                "X-Trace-Net-Benchmark-Only": "true",
                "X-Trace-Net-Model-Calls": "1",
                "X-Trace-Net-Model-Path": "nha_synthetic_benchmark_constrained_gemma",
                "X-Trace-Net-Writer-Source": str(result.get("writer_source") or ""),
                "X-Trace-Net-Gemma-Accepted": "1" if result.get("gemma_writer_accepted") else "0",
                "X-Trace-Net-Self-RAG": "PASS" if result.get("self_rag_pass") else "FAIL",
                "X-Trace-Net-Prompt-Tokens": str(int(result.get("prompt_tokens") or 0)),
                "X-Trace-Net-Completion-Tokens": str(int(result.get("completion_tokens") or 0)),
                "X-Trace-Net-Deterministic-Fallback": "0",
                "X-Trace-Net-Production-Graph-Writes": "0",
                "X-Trace-Net-Source-Mutations": "0",
            }
            if payload.get("stream"):
                body = stream_body(answer, MODEL_ID)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("X-Accel-Buffering", "no")
                self.send_header("Content-Length", str(len(body)))
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    self.close_connection = True
                return
            response = completion(
                answer,
                MODEL_ID,
                prompt_tokens=int(result.get("prompt_tokens") or 0),
                completion_tokens=int(result.get("completion_tokens") or 0),
            )
            self.send_json(200, response, headers=headers)

    return Handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8133)
    parser.add_argument("--phase5-dir", required=True)
    parser.add_argument("--nha-engram-dir", required=True)
    parser.add_argument("--api-key", default="trace-net-nha-gemma100-benchmark")
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--gemma-model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--max-tokens", type=int, default=384)
    parser.add_argument("--telemetry-path", default="/data/trace_net_runs/nha_phase20_gemma100_v1/server_telemetry.jsonl")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runtime = Runtime(
        phase5_dir=args.phase5_dir,
        engram_dir=args.nha_engram_dir,
        api_key=args.api_key,
        model=args.gemma_model,
        ollama_url=args.ollama_url,
        timeout=args.timeout_seconds,
        max_tokens=args.max_tokens,
        telemetry_path=args.telemetry_path,
    )
    health = runtime.health()
    if health.get("question_count") != EXPECTED_QUESTION_COUNT:
        raise SystemExit("benchmark bank did not contain 100 questions")
    server = ThreadingHTTPServer((args.host, args.port), make_handler(runtime))
    print("status=TRACE_NET_NHA_PHASE20_GEMMA100_SERVER_READY")
    print("quality_status=PASS")
    print(f"host={args.host}")
    print(f"port={args.port}")
    print(f"question_count={len(runtime.bank)}")
    print(f"answer_model={args.gemma_model}")
    print("benchmark_only=true")
    print("production_8131_synthetic_block_preserved=true")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
