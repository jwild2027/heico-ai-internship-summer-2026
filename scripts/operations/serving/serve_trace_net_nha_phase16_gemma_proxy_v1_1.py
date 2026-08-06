#!/usr/bin/env python3
"""NHA public proxy v1.1 with resident Gemma and safe progress SSE.

The answer/evidence/limits contract and all NHA decision logic remain owned by
``serve_trace_net_nha_phase16_gemma_proxy_v1``. This revision adds accurate
residency readiness, startup/request preloading, stage timing, and non-answer
progress events before the final validated answer is released.
"""
from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping, Sequence

from scripts.operations.s3_graph_store import serve_trace_net_nha_phase16_gemma_proxy_v1 as base
from src.trace_net.serving.trace_net_h30_gemma_residency_watchdog_v2 import (
    install_nha_runtime_residency_watchdog,
    progress_event,
    safe_stream_write,
)

MODULE = "trace_net_nha_phase16_gemma_proxy_v1_1"


class Runtime(base.Runtime):
    pass


install_nha_runtime_residency_watchdog(Runtime)


def _safe_stream_error(handler: Any, model: str, message: str) -> None:
    safe_stream_write(
        handler,
        progress_event("request_failed", message, model=model),
    )
    safe_stream_write(handler, b"data: [DONE]\n\n")


def _preview_action(packet: Mapping[str, Any], mode: str) -> str:
    if packet.get("synthetic_blocked"):
        return "synthetic_blocked"
    if packet.get("eligible") and mode == "gated":
        return "gemma_override"
    if packet.get("eligible") and mode == "shadow":
        return "shadow_candidate"
    return "passthrough"


def _begin_stream(
    handler: Any,
    *,
    runtime: Runtime,
    packet: Mapping[str, Any],
    action: str,
) -> bool:
    headers = base.decision_headers(packet, action=action)
    dynamic_headers = {
        "X-Trace-Net-NHA-Gemma-Calls",
        "X-Trace-Net-NHA-Writer-Source",
        "X-Trace-Net-NHA-Self-RAG",
        "X-Trace-Net-Model-Calls",
        "X-Trace-Net-Model-Path",
        "X-Trace-Net-Upstream-Calls",
        "X-Trace-Net-Model-Prompt-Tokens",
        "X-Trace-Net-Model-Completion-Tokens",
        "X-Trace-Net-Upstream-Gemma-Status",
        "X-Trace-Net-Upstream-Writer-Mode",
    }
    headers = {key: value for key, value in headers.items() if key not in dynamic_headers}
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "close")
    handler.send_header("X-Accel-Buffering", "no")
    handler.send_header("X-Trace-Net-Streaming-Mode", "validated-progress-then-answer")
    handler.send_header("X-Trace-Net-Raw-Unvalidated-Tokens", "false")
    for key, value in headers.items():
        handler.send_header(str(key), str(value))
    handler.end_headers()
    handler.close_connection = True
    return safe_stream_write(
        handler,
        progress_event(
            "request_accepted",
            "TRACE-Net accepted the request and is preparing evidence.",
            model=runtime.public_model,
        ),
    )


def make_handler(runtime: Runtime):
    class Handler(BaseHTTPRequestHandler):
        server_version = "TraceNetNHAGemmaProxy/1.1"

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
                self.send_json(400, base.error_payload("Invalid request body.", "invalid_request"))
                return None
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception as exc:
                self.send_json(400, base.error_payload(f"Invalid JSON: {exc}", "invalid_json"))
                return None
            if not isinstance(payload, dict):
                self.send_json(400, base.error_payload("JSON body must be an object.", "invalid_request"))
                return None
            return payload

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/health":
                health = runtime.health()
                self.send_json(200 if health["quality_status"] == "PASS" else 503, health)
                return
            if not self.authorized():
                self.send_json(401, base.error_payload("Invalid or missing API key.", "unauthorized"))
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
            self.send_json(404, base.error_payload("Route not found.", "not_found"))

        def do_POST(self) -> None:
            if not self.authorized():
                self.send_json(401, base.error_payload("Invalid or missing API key.", "unauthorized"))
                return
            path = self.path.split("?", 1)[0]
            if path not in {"/v1/chat/completions", "/v1/nha/decision"}:
                self.send_json(404, base.error_payload("Route not found.", "not_found"))
                return
            payload = self.read_payload()
            if payload is None:
                return

            request_started = time.perf_counter()
            query = base.extract_user_query(payload)
            packet_started = time.perf_counter()
            packet = base.build_nha_writer_packet(
                query=query,
                engine=runtime.engine,
                engram_bundle=runtime.engram_bundle,
            )
            packet_ms = round((time.perf_counter() - packet_started) * 1000.0, 3)

            if path == "/v1/nha/decision":
                action = _preview_action(packet, runtime.mode)
                self.send_json(
                    200,
                    base.packet_diagnostic(packet),
                    headers=base.decision_headers(packet, action=action),
                )
                return

            wants_stream = bool(payload.get("stream"))
            action = _preview_action(packet, runtime.mode)
            stream_connected = False
            if wants_stream:
                stream_connected = _begin_stream(
                    self,
                    runtime=runtime,
                    packet=packet,
                    action=action,
                )
                if stream_connected:
                    stream_connected = safe_stream_write(
                        self,
                        progress_event(
                            "route_and_memory_ready",
                            "TRACE-Net selected the bounded NHA behavior and Engram guidance.",
                            model=runtime.public_model,
                        ),
                    )

            writer_source = ""
            gemma_calls = 0
            self_rag = ""
            prompt_tokens = 0
            completion_tokens = 0
            model_calls = 0
            model_path = ""
            upstream_calls = 0
            upstream_gemma_status = ""
            upstream_writer_mode = ""
            model_ms = 0.0
            upstream_ms = 0.0
            residency_ms = 0.0
            residency_recovery: Mapping[str, Any] = {}

            try:
                residency_started = time.perf_counter()
                residency_recovery = runtime.gemma_residency_manager.ensure_resident(
                    "nha_public_request"
                )
                residency_ms = round((time.perf_counter() - residency_started) * 1000.0, 3)
                if not residency_recovery.get("success"):
                    raise RuntimeError(
                        "Gemma residency could not be established: "
                        + str(residency_recovery.get("error") or "unknown error")
                    )
                if wants_stream and stream_connected:
                    stream_connected = safe_stream_write(
                        self,
                        progress_event(
                            "gemma_resident",
                            "Gemma is resident; TRACE-Net is executing the approved path.",
                            model=runtime.public_model,
                        ),
                    )

                if packet.get("synthetic_blocked"):
                    answer = base.synthetic_block_answer()
                    result = base.openai_completion(answer, runtime.public_model)
                elif packet.get("eligible") and runtime.mode == "gated":
                    if wants_stream and stream_connected:
                        stream_connected = safe_stream_write(
                            self,
                            progress_event(
                                "gemma_writing",
                                "Gemma is wording only the approved NHA evidence.",
                                model=runtime.public_model,
                            ),
                        )
                    model_started = time.perf_counter()
                    write = base.write_nha_answer_with_gemma(
                        packet,
                        ollama_url=runtime.ollama_url,
                        model=runtime.gemma_model,
                        timeout=runtime.gemma_timeout,
                        max_tokens=runtime.gemma_max_tokens,
                    )
                    model_ms = round((time.perf_counter() - model_started) * 1000.0, 3)
                    answer = write.answer
                    writer_source = write.writer_source
                    gemma_calls = write.gemma_call_count
                    self_rag = "PASS" if write.self_rag_pass else "FAIL"
                    prompt_tokens = write.prompt_tokens
                    completion_tokens = write.completion_tokens
                    result = base.openai_completion(answer, runtime.public_model)
                    model_calls = 1
                    model_path = "nha_constrained_gemma"
                    result["usage"] = {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": prompt_tokens + completion_tokens,
                    }
                else:
                    if wants_stream and stream_connected:
                        stream_connected = safe_stream_write(
                            self,
                            progress_event(
                                "upstream_cognitive",
                                "TRACE-Net is retrieving and validating source evidence.",
                                model=runtime.public_model,
                            ),
                        )
                    upstream_payload = dict(payload)
                    upstream_payload["model"] = runtime.upstream_model
                    upstream_payload["stream"] = False
                    upstream_started = time.perf_counter()
                    status, result = base.http_json(
                        runtime.upstream_url + "/v1/chat/completions",
                        upstream_payload,
                        api_key=runtime.upstream_api_key,
                        timeout=runtime.timeout,
                    )
                    upstream_ms = round((time.perf_counter() - upstream_started) * 1000.0, 3)
                    if status != 200:
                        if wants_stream:
                            _safe_stream_error(
                                self,
                                runtime.public_model,
                                f"TRACE-Net upstream returned status {status}.",
                            )
                        else:
                            self.send_json(
                                status,
                                result,
                                headers=base.decision_headers(packet, action=action),
                            )
                        return
                    answer = base.extract_answer(result)
                    result["model"] = runtime.public_model
                    usage = result.get("usage") if isinstance(result.get("usage"), Mapping) else {}
                    prompt_tokens = int(usage.get("prompt_tokens") or 0)
                    completion_tokens = int(usage.get("completion_tokens") or 0)
                    observation = base.observe_upstream_model(result)
                    model_calls = int(observation["model_call_count"])
                    upstream_calls = 1
                    model_path = (
                        "upstream_cognitive_shadow"
                        if packet.get("eligible") and runtime.mode == "shadow" and model_calls
                        else "upstream_cognitive_deterministic_shadow"
                        if packet.get("eligible") and runtime.mode == "shadow"
                        else str(observation["model_path"])
                    )
                    upstream_gemma_status = str(observation["gemma_status"])
                    upstream_writer_mode = str(observation["writer_mode"])

                if not answer:
                    if wants_stream:
                        _safe_stream_error(
                            self,
                            runtime.public_model,
                            "TRACE-Net produced no validated assistant content.",
                        )
                    else:
                        self.send_json(
                            502,
                            base.error_payload(
                                "Response did not contain assistant content.", "empty_answer"
                            ),
                            headers=base.decision_headers(packet, action=action),
                        )
                    return

                total_ms = round((time.perf_counter() - request_started) * 1000.0, 3)
                timing = {
                    "packet_build_ms": packet_ms,
                    "gemma_residency_preflight_ms": residency_ms,
                    "gemma_preload_before_request": bool(
                        residency_recovery.get("attempted")
                    ),
                    "gemma_preload_before_request_ms": residency_recovery.get("preload_ms"),
                    "nha_gemma_writer_ms": model_ms,
                    "upstream_cognitive_ms": upstream_ms,
                    "public_proxy_total_ms": total_ms,
                }
                result["trace_net_public_timing"] = timing

                headers = base.decision_headers(
                    packet,
                    action=action,
                    writer_source=writer_source,
                    gemma_calls=gemma_calls,
                    self_rag=self_rag,
                    model_calls=model_calls,
                    model_path=model_path,
                    upstream_calls=upstream_calls,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    upstream_gemma_status=upstream_gemma_status,
                    upstream_writer_mode=upstream_writer_mode,
                )
                runtime.record({
                    "schema_version": "trace_net_nha_phase16_telemetry_v1_1",
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
                    "model_call_count": model_calls,
                    "model_path": model_path,
                    "upstream_call_count": upstream_calls,
                    "upstream_gemma_status": upstream_gemma_status,
                    "upstream_writer_mode": upstream_writer_mode,
                    **timing,
                    "production_graph_write_count": 0,
                    "source_artifact_mutation_count": 0,
                    "synthetic_artifact_access_count": 0,
                }, query)

                if wants_stream:
                    if stream_connected:
                        safe_stream_write(
                            self,
                            progress_event(
                                "answer_validated",
                                "TRACE-Net validated the answer and is releasing it.",
                                model=runtime.public_model,
                            ),
                        )
                        safe_stream_write(
                            self,
                            base.stream_body(answer, runtime.public_model),
                        )
                else:
                    self.send_json(200, result, headers=headers)
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as exc:
                if wants_stream:
                    _safe_stream_error(
                        self,
                        runtime.public_model,
                        f"TRACE-Net request failed safely: {type(exc).__name__}.",
                    )
                else:
                    self.send_json(
                        503,
                        base.error_payload(
                            f"TRACE-Net request failed safely: {type(exc).__name__}: {exc}",
                            "resident_request_failure",
                        ),
                    )

    return Handler


def main(argv: Sequence[str] | None = None) -> int:
    args = base.build_parser().parse_args(argv)
    engine, source = base.load_real_engine(args.phase4_dir, max_depth=args.max_depth)
    engram_bundle = base.load_nha_engram_bundle(args.nha_engram_dir)
    if engram_bundle["quality_status"] != "PASS":
        print(json.dumps(engram_bundle, indent=2, ensure_ascii=False))
        raise SystemExit(
            "NHA Gemma proxy refused to start because N13 Engram artifacts are unhealthy"
        )
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
        raise SystemExit(
            "NHA Gemma proxy refused to start because Gemma is not resident or a required upstream is unhealthy"
        )
    server = ThreadingHTTPServer((args.host, args.port), make_handler(runtime))
    print("status=TRACE_NET_NHA_PHASE16_GEMMA_PROXY_V1_1_READY")
    print("quality_status=PASS")
    print(f"mode={args.mode}")
    print(f"host={args.host}")
    print(f"port={args.port}")
    print(f"model={args.public_model}")
    print(f"answer_model={args.gemma_model}")
    print("gemma_model_resident=true")
    print("validated_progress_streaming=true")
    print("raw_unvalidated_tokens_exposed=false")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
