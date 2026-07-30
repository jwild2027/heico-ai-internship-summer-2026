#!/usr/bin/env python3
"""Serve Engram-guided, evidence-constrained Gemma NHA answers on port 8132."""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.trace_net_nha_phase14_16_cognitive_v1 import (
    DEFAULT_GEMMA_MODEL,
    DEFAULT_OLLAMA_URL,
    MODULE,
    build_nha_writer_packet,
    load_nha_engram_bundle,
    packet_diagnostic,
    write_nha_answer_with_gemma,
)
from scripts.trace_net_nha_phase7_8_runtime_v1 import (
    extract_answer,
    extract_user_query,
    http_json,
    load_real_engine,
    openai_completion,
    stream_body,
)

DEFAULT_PUBLIC_MODEL = "trace-net-gemma4-cognitive-rag-nha-engram-v1"
DEFAULT_UPSTREAM_MODEL = "trace-net-gemma4-cognitive-rag-v1"


def error_payload(message: str, code: str) -> dict[str, Any]:
    return {
        "error": {
            "message": message,
            "type": "trace_net_error",
            "param": None,
            "code": code,
        }
    }


def synthetic_block_answer() -> str:
    return "\n".join([
        "## Answer",
        "",
        "This reserved benchmark identifier is unavailable to production NHA queries.",
        "",
        "## Evidence",
        "",
        "- No production relationship or synthetic benchmark artifact was queried.",
        "",
        "## Limits",
        "",
        "- Synthetic identifiers never support production claims.",
        "- The request was not sent to Gemma or the upstream cognitive model.",
    ])


def _short_join(values: Sequence[Any], limit: int = 6) -> str:
    return ",".join(str(value) for value in list(values)[:limit])


def decision_headers(
    packet: Mapping[str, Any],
    *,
    action: str,
    writer_source: str = "",
    gemma_calls: int = 0,
    self_rag: str = "",
) -> dict[str, str]:
    return {
        "X-Trace-Net-NHA-Action": action,
        "X-Trace-Net-NHA-Intent": str(packet.get("intent") or ""),
        "X-Trace-Net-NHA-Behavior": str((packet.get("evidence") or {}).get("behavior") or ""),
        "X-Trace-Net-Route": (
            "synthetic_identifier_blocked"
            if action == "synthetic_blocked"
            else "upstream"
            if action == "passthrough"
            else str(packet.get("route_id") or "assembly_relationship_reasoning")
        ),
        "X-Trace-Net-NHA-Engram-Skill": _short_join(packet.get("selected_skill_ids") or []),
        "X-Trace-Net-NHA-Engram-Atoms": str(len(packet.get("selected_memory_atom_ids") or [])),
        "X-Trace-Net-NHA-Gemma-Calls": str(int(gemma_calls)),
        "X-Trace-Net-NHA-Writer-Source": writer_source,
        "X-Trace-Net-NHA-Self-RAG": self_rag,
        "X-Trace-Net-NHA-Synthetic-Access": "0",
    }


class Runtime:
    def __init__(
        self,
        *,
        engine: Any,
        engram_bundle: Mapping[str, Any],
        mode: str,
        upstream_url: str,
        upstream_api_key: str,
        public_api_key: str,
        public_model: str,
        upstream_model: str,
        ollama_url: str,
        gemma_model: str,
        timeout: float,
        gemma_timeout: float,
        gemma_max_tokens: int,
        relationship_count: int,
        telemetry_path: Path,
        telemetry_include_query: bool,
    ) -> None:
        self.engine = engine
        self.engram_bundle = dict(engram_bundle)
        self.mode = mode
        self.upstream_url = upstream_url.rstrip("/")
        self.upstream_api_key = upstream_api_key
        self.public_api_key = public_api_key
        self.public_model = public_model
        self.upstream_model = upstream_model
        self.ollama_url = ollama_url.rstrip("/")
        self.gemma_model = gemma_model
        self.timeout = timeout
        self.gemma_timeout = gemma_timeout
        self.gemma_max_tokens = gemma_max_tokens
        self.relationship_count = relationship_count
        self.telemetry_path = telemetry_path
        self.telemetry_include_query = telemetry_include_query
        self._telemetry_lock = threading.Lock()

    def health(self) -> dict[str, Any]:
        upstream_status, upstream = http_json(
            self.upstream_url + "/health",
            None,
            api_key=self.upstream_api_key,
            timeout=min(8.0, self.timeout),
        )
        tags_status, tags = http_json(
            self.ollama_url + "/api/tags",
            None,
            api_key="",
            timeout=min(8.0, self.timeout),
        )
        models = []
        if isinstance(tags, Mapping):
            for row in tags.get("models") or []:
                if isinstance(row, Mapping):
                    models.append(str(row.get("name") or row.get("model") or ""))
        upstream_ready = upstream_status == 200 and upstream.get("quality_status") == "PASS"
        gemma_ready = tags_status == 200 and self.gemma_model in models
        engram_ready = self.engram_bundle.get("quality_status") == "PASS"
        quality = (
            "PASS"
            if upstream_ready and gemma_ready and engram_ready and self.relationship_count > 0
            else "FAIL"
        )
        return {
            "quality_status": quality,
            "module": MODULE,
            "release_proxy": "trace_net_nha_phase16_gemma_proxy_v1",
            "mode": self.mode,
            "model": self.public_model,
            "upstream_model": self.upstream_model,
            "answer_model": self.gemma_model,
            "upstream_ready": upstream_ready,
            "gemma_ready": gemma_ready,
            "engram_ready": engram_ready,
            "nha_memory_atom_count": int(self.engram_bundle.get("nha_memory_atom_count") or 0),
            "nha_skill_card_count": int(self.engram_bundle.get("nha_skill_card_count") or 0),
            "real_relationship_count": self.relationship_count,
            "single_gemma_call_maximum": True,
            "deterministic_fallback_preserved": True,
            "synthetic_artifacts_loaded": False,
            "synthetic_identifier_blocked": True,
            "validated_buffered_streaming": True,
        }

    def record(self, row: Mapping[str, Any], query: str) -> None:
        payload = dict(row)
        payload["timestamp_unix"] = round(time.time(), 3)
        if self.telemetry_include_query:
            payload["query"] = query
        self.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        with self._telemetry_lock:
            with self.telemetry_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def make_handler(runtime: Runtime):
    class Handler(BaseHTTPRequestHandler):
        server_version = "TraceNetNHAGemmaProxy/1.0"

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def authorized(self) -> bool:
            return self.headers.get("Authorization", "") == f"Bearer {runtime.public_api_key}"

        def send_json(
            self,
            status: int,
            payload: Mapping[str, Any],
            *,
            headers: Mapping[str, str] | None = None,
        ) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
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
            if length <= 0 or length > 2_000_000:
                self.send_json(400, error_payload("Invalid request body.", "invalid_request"))
                return None
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception as exc:
                self.send_json(400, error_payload(f"Invalid JSON: {exc}", "invalid_json"))
                return None
            if not isinstance(payload, dict):
                self.send_json(400, error_payload("JSON body must be an object.", "invalid_request"))
                return None
            return payload

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
                self.send_json(200, {
                    "object": "list",
                    "data": [{
                        "id": runtime.public_model,
                        "object": "model",
                        "created": int(time.time()),
                        "owned_by": "trace-net-nha-engram-gemma-local",
                    }],
                })
                return
            self.send_json(404, error_payload("Route not found.", "not_found"))

        def do_POST(self) -> None:
            if not self.authorized():
                self.send_json(401, error_payload("Invalid or missing API key.", "unauthorized"))
                return
            path = self.path.split("?", 1)[0]
            if path not in {"/v1/chat/completions", "/v1/nha/decision"}:
                self.send_json(404, error_payload("Route not found.", "not_found"))
                return
            payload = self.read_payload()
            if payload is None:
                return
            query = extract_user_query(payload)
            started = time.perf_counter()
            packet = build_nha_writer_packet(
                query=query,
                engine=runtime.engine,
                engram_bundle=runtime.engram_bundle,
            )

            if path == "/v1/nha/decision":
                action = (
                    "synthetic_blocked"
                    if packet.get("synthetic_blocked")
                    else "shadow_candidate"
                    if packet.get("eligible")
                    else "passthrough"
                )
                headers = decision_headers(packet, action=action)
                self.send_json(200, packet_diagnostic(packet), headers=headers)
                return

            wants_stream = bool(payload.get("stream"))
            action = "passthrough"
            writer_source = ""
            gemma_calls = 0
            self_rag = ""
            prompt_tokens = 0
            completion_tokens = 0

            if packet.get("synthetic_blocked"):
                action = "synthetic_blocked"
                answer = synthetic_block_answer()
                result = openai_completion(answer, runtime.public_model)
            elif packet.get("eligible") and runtime.mode == "gated":
                action = "gemma_override"
                write = write_nha_answer_with_gemma(
                    packet,
                    ollama_url=runtime.ollama_url,
                    model=runtime.gemma_model,
                    timeout=runtime.gemma_timeout,
                    max_tokens=runtime.gemma_max_tokens,
                )
                answer = write.answer
                writer_source = write.writer_source
                gemma_calls = write.gemma_call_count
                self_rag = "PASS" if write.self_rag_pass else "FAIL"
                prompt_tokens = write.prompt_tokens
                completion_tokens = write.completion_tokens
                result = openai_completion(answer, runtime.public_model)
                result["usage"] = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                }
            elif packet.get("eligible") and runtime.mode == "shadow":
                action = "shadow_candidate"
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
                    self.send_json(status, result, headers=decision_headers(packet, action=action))
                    return
                answer = extract_answer(result)
                result["model"] = runtime.public_model
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
                    self.send_json(status, result, headers=decision_headers(packet, action=action))
                    return
                answer = extract_answer(result)
                result["model"] = runtime.public_model

            if not answer:
                self.send_json(
                    502,
                    error_payload("Response did not contain assistant content.", "empty_answer"),
                    headers=decision_headers(packet, action=action),
                )
                return

            headers = decision_headers(
                packet,
                action=action,
                writer_source=writer_source,
                gemma_calls=gemma_calls,
                self_rag=self_rag,
            )
            runtime.record({
                "schema_version": "trace_net_nha_phase16_telemetry_v1",
                "query_sha256": packet.get("query_sha256"),
                "action": action,
                "intent": packet.get("intent"),
                "behavior": (packet.get("evidence") or {}).get("behavior"),
                "selected_skill_ids": packet.get("selected_skill_ids") or [],
                "selected_memory_atom_ids": packet.get("selected_memory_atom_ids") or [],
                "gemma_call_count": gemma_calls,
                "writer_source": writer_source,
                "self_rag_pass": self_rag == "PASS" if self_rag else None,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "latency_seconds": round(time.perf_counter() - started, 3),
                "production_graph_write_count": 0,
                "source_artifact_mutation_count": 0,
                "synthetic_artifact_access_count": 0,
            }, query)

            if wants_stream:
                body = stream_body(answer, runtime.public_model)
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
            else:
                self.send_json(200, result, headers=headers)

    return Handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8132)
    parser.add_argument("--mode", choices=("shadow", "gated"), default="shadow")
    parser.add_argument("--phase4-dir", required=True)
    parser.add_argument("--nha-engram-dir", required=True)
    parser.add_argument("--upstream-url", default="http://127.0.0.1:8131")
    parser.add_argument("--upstream-api-key", default="trace-net-openwebui-cognitive")
    parser.add_argument("--public-api-key", default="trace-net-openwebui-cognitive")
    parser.add_argument("--public-model", default=DEFAULT_PUBLIC_MODEL)
    parser.add_argument("--upstream-model", default=DEFAULT_UPSTREAM_MODEL)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--gemma-model", default=DEFAULT_GEMMA_MODEL)
    parser.add_argument("--telemetry-path", default="/data/trace_net_runs/nha_phase16_gemma_v1/telemetry.jsonl")
    parser.add_argument("--telemetry-include-query", action="store_true")
    parser.add_argument("--max-depth", type=int, default=8)
    parser.add_argument("--timeout-seconds", type=float, default=1200.0)
    parser.add_argument("--gemma-timeout-seconds", type=float, default=180.0)
    parser.add_argument("--gemma-max-tokens", type=int, default=512)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    engine, source = load_real_engine(args.phase4_dir, max_depth=args.max_depth)
    engram_bundle = load_nha_engram_bundle(args.nha_engram_dir)
    if engram_bundle["quality_status"] != "PASS":
        print(json.dumps(engram_bundle, indent=2, ensure_ascii=False))
        raise SystemExit("NHA Gemma proxy refused to start because N13 Engram artifacts are unhealthy")
    runtime = Runtime(
        engine=engine,
        engram_bundle=engram_bundle,
        mode=args.mode,
        upstream_url=args.upstream_url,
        upstream_api_key=args.upstream_api_key,
        public_api_key=args.public_api_key,
        public_model=args.public_model,
        upstream_model=args.upstream_model,
        ollama_url=args.ollama_url,
        gemma_model=args.gemma_model,
        timeout=args.timeout_seconds,
        gemma_timeout=args.gemma_timeout_seconds,
        gemma_max_tokens=args.gemma_max_tokens,
        relationship_count=len(source["relationships"]),
        telemetry_path=Path(args.telemetry_path),
        telemetry_include_query=args.telemetry_include_query,
    )
    health = runtime.health()
    if health["quality_status"] != "PASS":
        print(json.dumps(health, indent=2, ensure_ascii=False))
        raise SystemExit("NHA Gemma proxy refused to start because upstream, Gemma, Engram, or release is unhealthy")
    server = ThreadingHTTPServer((args.host, args.port), make_handler(runtime))
    print("status=TRACE_NET_NHA_PHASE16_GEMMA_PROXY_V1_READY")
    print("quality_status=PASS")
    print(f"mode={args.mode}")
    print(f"host={args.host}")
    print(f"port={args.port}")
    print(f"model={args.public_model}")
    print(f"answer_model={args.gemma_model}")
    print(f"real_relationship_count={len(source['relationships'])}")
    print(f"nha_memory_atom_count={engram_bundle['nha_memory_atom_count']}")
    print(f"nha_skill_card_count={engram_bundle['nha_skill_card_count']}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
