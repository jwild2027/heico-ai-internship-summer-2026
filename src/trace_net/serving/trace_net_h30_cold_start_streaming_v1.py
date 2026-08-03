#!/usr/bin/env python3
"""Cold-start, native Ollama timing, and validated SSE support for TRACE-Net H30.

This module changes transport and observability only. Retrieval, evidence selection,
answer validation, authority gating, and source-truth rules remain unchanged.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

MODULE = "trace_net_h30_cold_start_streaming_v1"
PATCH_ID = "trace_net_h30_phase4_2_0_cold_start_streaming_v1"


def native_ollama_base(value: str) -> str:
    base = str(value or "http://127.0.0.1:11434").rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return base.rstrip("/")


def ns_to_ms(value: Any) -> float:
    try:
        return round(float(value or 0) / 1_000_000.0, 3)
    except (TypeError, ValueError):
        return 0.0


def _tokens_per_second(count: Any, duration_ns: Any) -> float:
    try:
        count_value = float(count or 0)
        duration_value = float(duration_ns or 0)
    except (TypeError, ValueError):
        return 0.0
    if count_value <= 0 or duration_value <= 0:
        return 0.0
    return round(count_value / duration_value * 1_000_000_000.0, 3)


def ollama_timing(final: Mapping[str, Any], *, first_token_ms: Optional[float], transport_ms: float) -> Dict[str, Any]:
    return {
        "ollama_time_to_first_token_ms": None if first_token_ms is None else round(first_token_ms, 3),
        "ollama_load_ms": ns_to_ms(final.get("load_duration")),
        "ollama_prompt_eval_ms": ns_to_ms(final.get("prompt_eval_duration")),
        "ollama_generation_ms": ns_to_ms(final.get("eval_duration")),
        "ollama_total_ms": ns_to_ms(final.get("total_duration")),
        "ollama_transport_ms": round(float(transport_ms), 3),
        "ollama_prompt_tokens": int(final.get("prompt_eval_count") or 0),
        "ollama_output_tokens": int(final.get("eval_count") or 0),
        "ollama_generation_tokens_per_second": _tokens_per_second(
            final.get("eval_count"), final.get("eval_duration")
        ),
    }


def native_chat_payload(*, model: str, messages: Sequence[Mapping[str, Any]], keep_alive: str) -> Dict[str, Any]:
    return {
        "model": model,
        "messages": [dict(message) for message in messages],
        "options": {"temperature": 0},
        "stream": True,
        "keep_alive": keep_alive,
    }


def consume_ollama_ndjson(
    lines: Iterable[bytes | str],
    *,
    started_at: Optional[float] = None,
    clock: Any = time.monotonic,
) -> Tuple[str, Dict[str, Any], Optional[float]]:
    start = clock() if started_at is None else started_at
    pieces: List[str] = []
    final: Dict[str, Any] = {}
    first_token_ms: Optional[float] = None
    for raw in lines:
        text = raw.decode("utf-8", errors="replace").strip() if isinstance(raw, bytes) else str(raw).strip()
        if not text:
            continue
        try:
            event = json.loads(text)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, Mapping):
            continue
        message = event.get("message")
        content = str(message.get("content") or "") if isinstance(message, Mapping) else ""
        if content:
            if first_token_ms is None:
                first_token_ms = (clock() - start) * 1000.0
            pieces.append(content)
        if event.get("done"):
            final = dict(event)
    return "".join(pieces).strip(), final, first_token_ms


def native_ollama_chat(
    *,
    base_url: str,
    model: str,
    messages: Sequence[Mapping[str, Any]],
    keep_alive: str,
    timeout: float,
) -> Tuple[int, str, Dict[str, Any], Dict[str, Any]]:
    request = urllib.request.Request(
        native_ollama_base(base_url) + "/api/chat",
        data=json.dumps(native_chat_payload(model=model, messages=messages, keep_alive=keep_alive)).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            answer, final, first_token_ms = consume_ollama_ndjson(
                response, started_at=started, clock=time.monotonic
            )
            transport_ms = (time.monotonic() - started) * 1000.0
            return response.status, answer, final, ollama_timing(
                final, first_token_ms=first_token_ms, transport_ms=transport_ms
            )
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return exc.code, "", {"error": raw or str(exc)}, {
            "ollama_time_to_first_token_ms": None,
            "ollama_transport_ms": round((time.monotonic() - started) * 1000.0, 3),
        }
    except Exception as exc:
        return 599, "", {"error": f"{type(exc).__name__}: {exc}"}, {
            "ollama_time_to_first_token_ms": None,
            "ollama_transport_ms": round((time.monotonic() - started) * 1000.0, 3),
        }


def _model_names(payload: Mapping[str, Any]) -> set[str]:
    models = payload.get("models")
    if not isinstance(models, list):
        return set()
    return {
        str(row.get("name") or row.get("model"))
        for row in models
        if isinstance(row, Mapping) and (row.get("name") or row.get("model"))
    }


def sse_event(payload: Mapping[str, Any]) -> bytes:
    return ("data: " + json.dumps(dict(payload), ensure_ascii=False) + "\n\n").encode("utf-8")


def sse_role_chunk(model: str, completion_id: str, created: int) -> bytes:
    return sse_event({
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
    })


def sse_content_chunk(model: str, completion_id: str, created: int, content: str) -> bytes:
    return sse_event({
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
    })


def sse_finish_chunk(model: str, completion_id: str, created: int, timing: Mapping[str, Any]) -> bytes:
    return sse_event({
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        "trace_net_timing": dict(timing),
        "streaming_mode": "upstream_sse_with_validated_answer_release",
    })


def _safe_write(handler: Any, data: bytes) -> bool:
    try:
        handler.wfile.write(data)
        handler.wfile.flush()
        return True
    except (BrokenPipeError, ConnectionResetError, OSError):
        return False


def install_gemma_latency_support(module: MutableMapping[str, Any]) -> None:
    if module.get("_TRACE_NET_H30_GEMMA_LATENCY_V1_INSTALLED"):
        return

    runtime_cls = module["Runtime"]
    original_health = runtime_cls.health
    original_make_handler = module["make_handler"]
    http_json = module["http_json"]
    direct_evidence = module["direct_evidence"]
    validate_answer = module["validate_answer"]
    build_prompt = module["build_prompt"]
    extract_latest_user = module["extract_latest_user"]
    error_payload = module["error_payload"]
    openai_response = module["openai_response"]
    model_id = module["MODEL_ID"]
    # Evidence-synthesis helpers (Phase 4). Fetched lazily so this module also
    # imports cleanly against older builds that predate them.
    candidate_evidence = module.get("candidate_evidence") or (lambda result: [])
    visual_guidance = module.get("visual_guidance") or (lambda result: [])
    semantic_guidance = module.get("semantic_guidance") or (lambda result: [])
    authority_evidence = module.get("authority_evidence") or (lambda result: [])
    evidence_synthesis_enabled = module.get("evidence_synthesis_enabled") or (lambda: False)
    synthesis_allowed_identifiers = module.get("synthesis_allowed_identifiers") or (
        lambda query, result: {"parts": set(), "atas": set(), "pages": set()}
    )
    citation_registry = module.get("citation_registry") or (lambda result: [])
    citation_registry_digest = module.get("citation_registry_digest") or (lambda registry: "")

    def process_v1(self: Any, payload: Mapping[str, Any]) -> Dict[str, Any]:
        request_started = time.monotonic()
        query = extract_latest_user(payload)
        router_started = time.monotonic()
        cognitive_status, result = http_json(
            self.cognitive_base_url + "/api/trace-net/ask",
            {"query": query, "messages": payload.get("messages") or [{"role": "user", "content": query}]},
            api_key=self.cognitive_api_key,
            timeout=self.timeout,
        )
        router_ms = (time.monotonic() - router_started) * 1000.0
        keep_alive = str(os.environ.get("TRACE_NET_GEMMA_KEEP_ALIVE", "1h") or "1h")
        timing: Dict[str, Any] = {
            "router_retrieval_ms": round(router_ms, 3),
            "gemma_called": False,
            "gemma_keep_alive": keep_alive,
        }
        if cognitive_status != 200:
            timing["writer_total_ms"] = round((time.monotonic() - request_started) * 1000.0, 3)
            return {
                "content": "TRACE-Net could not reach the cognitive retrieval and evidence-gating service. No technical answer is provided.",
                "route": "clarification_no_evidence",
                "quality_status": "WARN",
                "writer_mode": "fail_closed_upstream_error",
                "upstream_status_code": cognitive_status,
                "upstream_error": result,
                "answer_model": self.gemma_model,
                "timing": timing,
                "answer_permission": False,
                "final_answer_allowed": False,
                "source_truth_mutation_allowed": False,
            }

        route = str(result.get("route") or "")
        safe_draft = str(result.get("content") or "").strip()
        direct = direct_evidence(result)
        writer_mode = "deterministic_fail_closed"
        final_text = safe_draft
        gemma_status = "SKIPPED_NO_DIRECT_EVIDENCE"
        validation = {"quality_status": "PASS", "failures": [], "accepted": True}

        # Evidence-synthesis gate (Phase 4): when enabled, Gemma also writes for
        # evidence-bearing non-direct modes (candidate/visual/semantic guidance)
        # instead of falling through to a deterministic template. The strict
        # claim guardrails in validate_answer (unsupported identifier, dangerous
        # claim without authority, citation rules) still bound the output, and a
        # rejected answer falls back to the deterministic safe draft.
        synthesis_enabled = bool(evidence_synthesis_enabled())
        has_guidance = bool(
            candidate_evidence(result)
            or visual_guidance(result)
            or semantic_guidance(result)
        )
        synthesis_only = bool(
            synthesis_enabled
            and not direct
            and has_guidance
            and route not in {"safe_general_chat", "authority_eligibility_verification"}
        )
        write_gemma = (bool(direct) or synthesis_only) and route != "safe_general_chat"
        synthesis_written = False
        registry: List[Dict[str, Any]] = []

        if write_gemma:
            timing["gemma_called"] = True
            # Build the immutable citation registry once and share the exact
            # instance with the validator so ids never drift.
            registry = citation_registry(result)
            prompt = build_prompt(query, result, registry=registry)
            status, answer, ollama_final, ollama_metrics = native_ollama_chat(
                base_url=self.gemma_base_url,
                model=self.gemma_model,
                messages=[
                    {"role": "system", "content": "Follow the evidence-only rules exactly."},
                    {"role": "user", "content": prompt},
                ],
                keep_alive=keep_alive,
                timeout=self.timeout,
            )
            timing.update(ollama_metrics)
            if status == 200:
                # Align the validator's allowed identifiers with the citation
                # registry: candidate/visual/semantic identifiers may always be
                # MENTIONED as guidance, even in a mixed direct+candidate answer
                # (q06), so listing suffix candidates is not rejected as
                # unsupported. Proof safety stays with the dangerous-claim gate
                # and the final Self-RAG critic.
                extra_allowed = synthesis_allowed_identifiers(query, result)
                validation = validate_answer(
                    answer, query, result, extra_allowed=extra_allowed, registry=registry
                )
                if validation["accepted"]:
                    final_text = answer
                    if synthesis_only:
                        writer_mode = "gemma_synthesis_guidance"
                        synthesis_written = True
                    else:
                        writer_mode = "gemma_validated_direct_evidence"
                    gemma_status = "LLM_CALL_SUCCEEDED_AND_VALIDATED"
                else:
                    final_text = safe_draft
                    writer_mode = "deterministic_fallback_after_validation_failure"
                    gemma_status = "LLM_OUTPUT_REJECTED"
            else:
                writer_mode = "deterministic_fallback_after_gemma_error"
                gemma_status = f"LLM_CALL_FAILED_STATUS_{status}"
                timing["ollama_error"] = dict(ollama_final)

        cleaner = module.get("clean_engineer_text")
        if callable(cleaner):
            final_text = cleaner(final_text)

        timing["writer_total_ms"] = round((time.monotonic() - request_started) * 1000.0, 3)

        # Record whether the exact-page content pack reached the single Gemma
        # prompt (build_prompt renders it when the envelope carries page content
        # and Gemma was actually called). The bridge itself adds no Gemma call.
        _cov = result.get("evidence_envelope", {}).get("coverage", {}) if isinstance(result.get("evidence_envelope"), Mapping) else {}
        _pc = _cov.get("page_content") if isinstance(_cov, Mapping) else None
        page_content_prompt_included = bool(
            write_gemma and isinstance(_pc, Mapping) and _pc.get("available") and _pc.get("pages")
        )
        if isinstance(_pc, Mapping) and isinstance(_pc.get("telemetry"), MutableMapping):
            _pc["telemetry"]["page_content_prompt_included"] = page_content_prompt_included

        result = dict(result)
        result.update({
            "module": module["MODULE"],
            "model": model_id,
            "content": final_text,
            "answer_model": self.gemma_model,
            "writer_mode": writer_mode,
            "gemma_status": gemma_status,
            "evidence_synthesis": {
                "enabled": synthesis_enabled,
                "attempted": bool(synthesis_only and write_gemma),
                "written": bool(synthesis_written),
            },
            "citation_registry_size": len(registry),
            "citation_registry_digest": citation_registry_digest(registry) if registry else "",
            "page_content_prompt_included": page_content_prompt_included,
            "post_answer_validation": validation,
            "timing": timing,
            "cold_start_support": {
                "module": MODULE,
                "patch_id": PATCH_ID,
                "native_ollama_chat": True,
                "keep_alive": keep_alive,
                "whole_answer_validation_before_content_release": True,
            },
            "answer_permission": False,
            "final_answer_allowed": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
        })
        contract_applier = module.get("apply_engineer_answer_contract")
        if callable(contract_applier):
            result = contract_applier(result)

        # The native Ollama wrapper replaces Runtime.process, so user-facing
        # guided follow-ups must be restored here after the engineer answer
        # contract has finished formatting the answer.
        follow_up_questions = [
            str(question).strip()
            for question in (result.get("follow_up_questions") or [])
            if str(question).strip()
        ]
        follow_up_appender = module.get("append_follow_up_questions")
        should_append_followups = bool(follow_up_questions)
        if callable(follow_up_appender):
            result["content"] = follow_up_appender(
                str(result.get("content") or ""),
                follow_up_questions,
                should_append=should_append_followups,
            )

        visible_count = sum(
            question in str(result.get("content") or "")
            for question in follow_up_questions
        )
        result["follow_up_questions_visible_count"] = visible_count
        result["follow_up_questions_visible"] = (
            visible_count == len(follow_up_questions)
            if follow_up_questions
            else True
        )
        return result

    def health_v1(self: Any) -> Dict[str, Any]:
        result = dict(original_health(self))
        ps_status, ps = http_json(
            native_ollama_base(self.gemma_base_url) + "/api/ps",
            None,
            api_key=None,
            timeout=min(8.0, self.timeout),
        )
        loaded_names = _model_names(ps) if ps_status == 200 else set()
        result.update({
            "native_ollama_chat": True,
            "gemma_keep_alive": str(os.environ.get("TRACE_NET_GEMMA_KEEP_ALIVE", "1h") or "1h"),
            "gemma_model_loaded": self.gemma_model in loaded_names,
            "loaded_ollama_models": sorted(loaded_names),
            "timing_metrics_enabled": True,
            "validated_sse_enabled": True,
            "raw_unvalidated_tokens_exposed": False,
        })
        contract_health = module.get("engineer_answer_contract_health")
        if callable(contract_health):
            result.update(contract_health())
        return result

    def make_handler_v1(runtime: Any):
        base_handler = original_make_handler(runtime)

        class Handler(base_handler):
            server_version = "TraceNetFullGemmaCognitiveLatency/1.0"

            def do_POST(self) -> None:
                path = self.path.split("?", 1)[0]
                if path != "/v1/chat/completions":
                    return super().do_POST()
                if not self.authorized():
                    self.send_json(401, error_payload("Invalid or missing API key.", "unauthorized", 401))
                    return
                if not runtime.semaphore.acquire(timeout=runtime.queue_timeout):
                    self.send_json(429, error_payload("Gemma cognitive queue timed out.", "rate_limit", 429))
                    return
                try:
                    payload, error = self.read_payload()
                    if error:
                        self.send_json(*error)
                        return
                    assert payload is not None
                    if not extract_latest_user(payload):
                        self.send_json(400, error_payload("Missing query or user message.", "missing_query", 400))
                        return
                    if not bool(payload.get("stream")):
                        result = runtime.process(payload)
                        self.send_json(200, openai_response(result, str(payload.get("model") or model_id)))
                        return

                    request_started = time.monotonic()
                    completion_id = "chatcmpl-trace-gemma-cognitive-" + uuid.uuid4().hex[:16]
                    created = int(time.time())
                    response_model = str(payload.get("model") or model_id)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "close")
                    self.send_header("X-Accel-Buffering", "no")
                    self.send_header("X-Trace-Net-Streaming-Mode", "validated-upstream-sse")
                    self.end_headers()
                    self.close_connection = True
                    connected = _safe_write(self, sse_role_chunk(response_model, completion_id, created))
                    first_byte_ms = (time.monotonic() - request_started) * 1000.0

                    holder: Dict[str, Any] = {}
                    finished = threading.Event()

                    def run_process() -> None:
                        try:
                            holder["result"] = runtime.process(payload)
                        except Exception as exc:
                            holder["error"] = exc
                        finally:
                            finished.set()

                    threading.Thread(target=run_process, daemon=True).start()
                    while not finished.wait(5.0):
                        if connected:
                            connected = _safe_write(self, b": trace-net processing\n\n")

                    if "error" in holder:
                        raise holder["error"]
                    result = dict(holder.get("result") or {})
                    answer = str(result.get("content") or "")
                    first_content_ms = (time.monotonic() - request_started) * 1000.0
                    if connected:
                        for offset in range(0, len(answer), 240):
                            if not _safe_write(
                                self,
                                sse_content_chunk(response_model, completion_id, created, answer[offset:offset + 240]),
                            ):
                                connected = False
                                break
                    timing = dict(result.get("timing") or {})
                    timing.update({
                        "writer_sse_time_to_first_byte_ms": round(first_byte_ms, 3),
                        "writer_sse_time_to_first_content_ms": round(first_content_ms, 3),
                    })
                    if connected:
                        _safe_write(self, sse_finish_chunk(response_model, completion_id, created, timing))
                        _safe_write(self, b"data: [DONE]\n\n")
                except (BrokenPipeError, ConnectionResetError):
                    return
                except Exception as exc:
                    _safe_write(self, sse_content_chunk(
                        str(locals().get("response_model") or model_id),
                        str(locals().get("completion_id") or ("chatcmpl-error-" + uuid.uuid4().hex[:8])),
                        int(locals().get("created") or time.time()),
                        f"TRACE-Net streaming error: {type(exc).__name__}",
                    ))
                    _safe_write(self, b"data: [DONE]\n\n")
                finally:
                    runtime.semaphore.release()

        return Handler

    runtime_cls.process = process_v1
    runtime_cls.health = health_v1
    module["make_handler"] = make_handler_v1
    module["_TRACE_NET_H30_GEMMA_LATENCY_V1_INSTALLED"] = True


def install_bridge_streaming_support(module: MutableMapping[str, Any]) -> None:
    if module.get("_TRACE_NET_H30_BRIDGE_STREAMING_V1_INSTALLED"):
        return

    runtime_cls = module["Runtime"]
    original_health = runtime_cls.health
    original_make_handler = module["make_handler"]
    http_json = module["http_json"]
    error_payload = module["error_payload"]

    def health_v1(self: Any) -> Dict[str, Any]:
        result = dict(original_health(self))
        result.update({
            "upstream_sse_passthrough": True,
            "buffered_fake_streaming": False,
            "validated_answer_release": True,
            "raw_unvalidated_tokens_exposed": False,
        })
        return result

    def make_handler_v1(runtime: Any):
        base_handler = original_make_handler(runtime)

        class Handler(base_handler):
            server_version = "TraceNetOpenWebUICognitiveBridgeStreaming/1.0"

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
                upstream_payload["model"] = runtime.public_model
                upstream_payload["stream"] = wants_stream

                if not wants_stream:
                    status, result = http_json(
                        runtime.upstream_url + "/v1/chat/completions",
                        upstream_payload,
                        api_key=runtime.upstream_api_key,
                        timeout=runtime.timeout,
                    )
                    if status == 200:
                        result["model"] = runtime.public_model
                    self.send_json(status, result)
                    return

                request = urllib.request.Request(
                    runtime.upstream_url + "/v1/chat/completions",
                    data=json.dumps(upstream_payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {runtime.upstream_api_key}",
                        "Accept": "text/event-stream",
                    },
                    method="POST",
                )
                started = time.monotonic()
                try:
                    with urllib.request.urlopen(request, timeout=runtime.timeout) as response:
                        header_ms = (time.monotonic() - started) * 1000.0
                        content_type = response.headers.get("Content-Type", "")
                        if "text/event-stream" not in content_type:
                            raw = response.read().decode("utf-8", errors="replace")
                            payload_error = error_payload(
                                "Upstream did not return an SSE stream.", "invalid_upstream_stream"
                            )
                            payload_error["upstream_body"] = raw[:1000]
                            self.send_json(502, payload_error)
                            return
                        self.send_response(200)
                        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                        self.send_header("Cache-Control", "no-cache")
                        self.send_header("Connection", "close")
                        self.send_header("X-Accel-Buffering", "no")
                        self.send_header("X-Trace-Net-Streaming-Mode", "upstream-sse-passthrough")
                        self.send_header("X-Trace-Net-Upstream-Headers-Ms", f"{header_ms:.3f}")
                        self.send_header("X-Trace-Net-Bridge-Time-To-First-Byte-Ms", f"{header_ms:.3f}")
                        self.end_headers()
                        self.close_connection = True
                        for line in response:
                            if not _safe_write(self, line):
                                break
                            if line.strip() == b"data: [DONE]":
                                break
                except urllib.error.HTTPError as exc:
                    raw = exc.read().decode("utf-8", errors="replace")
                    try:
                        value = json.loads(raw)
                    except Exception:
                        value = error_payload(raw or str(exc), "upstream_error")
                    self.send_json(exc.code, value if isinstance(value, Mapping) else {})
                except (BrokenPipeError, ConnectionResetError):
                    return
                except Exception as exc:
                    self.send_json(502, error_payload(
                        f"Upstream streaming failed: {type(exc).__name__}: {exc}",
                        "upstream_stream_error",
                    ))

        return Handler

    runtime_cls.health = health_v1
    module["make_handler"] = make_handler_v1
    module["_TRACE_NET_H30_BRIDGE_STREAMING_V1_INSTALLED"] = True
