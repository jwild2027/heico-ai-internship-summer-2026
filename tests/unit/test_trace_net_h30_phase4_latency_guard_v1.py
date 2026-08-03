import json

from scripts import trace_net_h30_constrained_gemma_writer_v1 as writer


CONTENT = """## Answer

`120-26948-003` appears in the available IPL/table evidence on page `t_p_120_1176_p000030` [1].

## Evidence

- Source-backed record: `120-26948-003` — page `t_p_120_1176_p000030` [1]

## Limits

- This record does not establish effectivity or installation suitability [1]."""

REGISTRY = [{
    "citation_id": 1,
    "class": "direct_source",
    "authority": "proof",
    "can_prove_claims": True,
    "claim_scope": "confirmed",
    "candidate_value": "120-26948-003",
    "page_id": "t_p_120_1176_p000030",
    "nomenclature": ["Support"],
    "value": "120-26948-003",
}]


def _result():
    return {
        "route": "exact_table_ipl_lookup",
        "content": CONTENT,
        "citation_registry": [dict(REGISTRY[0])],
        "post_answer_validation": {"quality_status": "PASS", "accepted": True, "failures": []},
        "answer_mode": {"mode": "confirmed_direct"},
        "legacy_freeform_gemma_suppressed": True,
        "writer_mode": "public_answer_contract_v1",
    }


def _good_output():
    packet = writer.build_writer_packet(
        query="Locate part 120-26948-003 in the IPL table.",
        result=_result(),
        registry=REGISTRY,
    )
    d = packet["deterministic_sections"]
    return json.dumps({
        "schema_version": writer.OUTPUT_SCHEMA_VERSION,
        "answer": d["answer"],
        "evidence": d["evidence"],
        "limits": d["limits"],
    })


def _namespace(clock, http_behavior, upstream_elapsed):
    calls = []

    class Runtime:
        gemma_model = "gemma4:26b"
        gemma_base_url = "http://127.0.0.1:11434/v1"
        gemma_api_key = "ollama"
        timeout = 210

        def process(self, payload):
            clock["now"] += upstream_elapsed
            return _result()

        def health(self):
            return {"quality_status": "PASS"}

    def http_json(url, payload, api_key=None, timeout=0):
        calls.append({"url": url, "payload": payload, "timeout": timeout})
        return http_behavior(payload, timeout)

    namespace = {
        "Runtime": Runtime,
        "citation_registry": lambda result: [dict(row) for row in result.get("citation_registry", [])],
        "citation_registry_digest": lambda registry: "digest",
        "validate_answer": lambda *args, **kwargs: {
            "quality_status": "PASS", "accepted": True, "failures": []
        },
        "extract_latest_user": lambda payload: payload.get("query", ""),
        "http_json": http_json,
    }
    return namespace, Runtime, calls


def test_config_clamps_latency_and_output_limits():
    config = writer.load_constrained_writer_config({
        "TRACE_NET_H30_CONSTRAINED_WRITER_ENABLED": "1",
        "TRACE_NET_H30_CONSTRAINED_WRITER_MODEL_TIMEOUT_SECONDS": "9999",
        "TRACE_NET_H30_CONSTRAINED_WRITER_OVERALL_BUDGET_SECONDS": "5",
        "TRACE_NET_H30_CONSTRAINED_WRITER_RESPONSE_RESERVE_SECONDS": "9999",
        "TRACE_NET_H30_CONSTRAINED_WRITER_MIN_CALL_SECONDS": "9999",
        "TRACE_NET_H30_CONSTRAINED_WRITER_MAX_TOKENS": "99999",
    })
    assert config["model_timeout_seconds"] == 120.0
    assert config["overall_budget_seconds"] == 30.0
    assert config["response_reserve_seconds"] < config["overall_budget_seconds"]
    assert config["minimum_call_seconds"] < config["overall_budget_seconds"]
    assert config["max_tokens"] == 2048


def test_budget_guard_skips_model_and_returns_phase3(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_CONSTRAINED_WRITER_ENABLED", "1")
    monkeypatch.setenv("TRACE_NET_H30_CONSTRAINED_WRITER_OVERALL_BUDGET_SECONDS", "30")
    monkeypatch.setenv("TRACE_NET_H30_CONSTRAINED_WRITER_RESPONSE_RESERVE_SECONDS", "10")
    monkeypatch.setenv("TRACE_NET_H30_CONSTRAINED_WRITER_MIN_CALL_SECONDS", "8")
    clock = {"now": 0.0}
    monkeypatch.setattr(writer.time, "monotonic", lambda: clock["now"])

    def must_not_call(payload, timeout):
        raise AssertionError("Gemma must be skipped when too little budget remains")

    namespace, Runtime, calls = _namespace(clock, must_not_call, upstream_elapsed=25.0)
    writer.install_constrained_gemma_writer(namespace)
    result = Runtime().process({"query": "Locate part 120-26948-003 in the IPL table."})
    telemetry = result["constrained_gemma_writer"]
    assert calls == []
    assert telemetry["reason"] == "insufficient_remaining_budget"
    assert telemetry["call_count"] == 0
    assert telemetry["phase3_fallback_used"]
    assert result["content"] == CONTENT
    assert result["post_answer_validation"]["accepted"]


def test_model_timeout_is_bounded_and_falls_back(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_CONSTRAINED_WRITER_ENABLED", "1")
    monkeypatch.setenv("TRACE_NET_H30_CONSTRAINED_WRITER_MODEL_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("TRACE_NET_H30_CONSTRAINED_WRITER_OVERALL_BUDGET_SECONDS", "210")
    monkeypatch.setenv("TRACE_NET_H30_CONSTRAINED_WRITER_RESPONSE_RESERVE_SECONDS", "20")
    clock = {"now": 0.0}
    monkeypatch.setattr(writer.time, "monotonic", lambda: clock["now"])

    def timeout_response(payload, timeout):
        assert timeout <= 45.0
        clock["now"] += timeout
        return 599, {"error": "TimeoutError: timed out"}

    namespace, Runtime, calls = _namespace(clock, timeout_response, upstream_elapsed=20.0)
    writer.install_constrained_gemma_writer(namespace)
    result = Runtime().process({"query": "Locate part 120-26948-003 in the IPL table."})
    telemetry = result["constrained_gemma_writer"]
    assert len(calls) == 1
    assert telemetry["reason"] == "gemma_call_timeout"
    assert telemetry["model_call_timed_out"]
    assert telemetry["phase3_fallback_used"]
    assert telemetry["model_timeout_used_seconds"] <= 45.0
    assert result["content"] == CONTENT


def test_success_payload_bounds_generation(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_CONSTRAINED_WRITER_ENABLED", "1")
    monkeypatch.setenv("TRACE_NET_H30_CONSTRAINED_WRITER_MODEL_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("TRACE_NET_H30_CONSTRAINED_WRITER_MAX_TOKENS", "512")
    clock = {"now": 0.0}
    monkeypatch.setattr(writer.time, "monotonic", lambda: clock["now"])

    def success(payload, timeout):
        clock["now"] += 5.0
        return 200, {"choices": [{"message": {"content": _good_output()}}]}

    namespace, Runtime, calls = _namespace(clock, success, upstream_elapsed=10.0)
    writer.install_constrained_gemma_writer(namespace)
    result = Runtime().process({"query": "Locate part 120-26948-003 in the IPL table."})
    assert len(calls) == 1
    assert calls[0]["payload"]["max_tokens"] == 512
    assert calls[0]["timeout"] <= 45.0
    assert result["constrained_gemma_writer"]["structured_output_accepted"]
