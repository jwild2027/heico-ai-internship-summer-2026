import json
from types import SimpleNamespace

import pytest

from scripts.trace_net_h30_constrained_gemma_writer_v1 import (
    OUTPUT_SCHEMA_VERSION,
    build_writer_packet,
    install_constrained_gemma_writer,
    legacy_freeform_writer_should_be_suppressed,
    load_constrained_writer_config,
    parse_structured_writer_output,
    validate_packet,
    validate_structured_output,
)


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


def _result(route="exact_table_ipl_lookup"):
    return {
        "route": route,
        "content": CONTENT,
        "citation_registry": [dict(REGISTRY[0])],
        "post_answer_validation": {"quality_status": "PASS", "accepted": True, "failures": []},
        "answer_mode": {"mode": "confirmed_direct"},
        "legacy_freeform_gemma_suppressed": True,
        "writer_mode": "public_answer_contract_v1",
    }


def _packet():
    return build_writer_packet(
        query="Locate part 120-26948-003 in the IPL table.",
        result=_result(),
        registry=REGISTRY,
    )


def _good_output(packet):
    d = packet["deterministic_sections"]
    return json.dumps({
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "answer": d["answer"],
        "evidence": d["evidence"],
        "limits": d["limits"],
    })


def test_config_and_legacy_suppression():
    assert not load_constrained_writer_config({})["enabled"]
    assert legacy_freeform_writer_should_be_suppressed({"TRACE_NET_H30_CONSTRAINED_WRITER_ENABLED": "1"})


def test_packet_is_compact_and_excludes_raw_evidence():
    packet = _packet()
    validation = validate_packet(packet)
    assert validation["accepted"]
    blob = json.dumps(packet)
    for forbidden in ("evidence_envelope", "typed_evidence", "claim_ready_evidence", "identifier_blob"):
        assert forbidden not in blob
    assert packet["allowed"]["citations"] == [1]
    assert packet["citation_registry"][0]["page_id"] == "t_p_120_1176_p000030"


def test_structured_output_accepts_exact_support_copy():
    packet = _packet()
    structured = parse_structured_writer_output(_good_output(packet))
    validation = validate_structured_output(structured, packet=packet)
    assert validation["accepted"], validation
    assert "## Evidence" in validation["rendered"]


def test_structured_output_rejects_changed_evidence():
    packet = _packet()
    value = json.loads(_good_output(packet))
    value["evidence"] = ["Different evidence [1]"]
    validation = validate_structured_output(parse_structured_writer_output(json.dumps(value)), packet=packet)
    assert not validation["accepted"]
    assert "evidence_section_not_exact_copy" in validation["failures"]


def test_structured_output_rejects_new_identifier():
    packet = _packet()
    value = json.loads(_good_output(packet))
    value["answer"] = ["Part 999-99999-999 is listed [1]."]
    validation = validate_structured_output(parse_structured_writer_output(json.dumps(value)), packet=packet)
    assert not validation["accepted"]
    assert "structured_output_added_parts" in validation["failures"]


def _module_namespace(http_response):
    calls = []

    class Runtime:
        gemma_model = "gemma4:26b"
        gemma_base_url = "http://127.0.0.1:11434/v1"
        gemma_api_key = "ollama"
        timeout = 10

        def process(self, payload):
            return _result(payload.get("route", "exact_table_ipl_lookup"))

        def health(self):
            return {"quality_status": "PASS"}

    def http_json(url, payload, api_key=None, timeout=0):
        calls.append((url, payload))
        return http_response(payload)

    def citation_registry(result):
        return [dict(row) for row in result.get("citation_registry", [])]

    def validate_answer(answer, query, result, extra_allowed=None, registry=None):
        return {"quality_status": "PASS", "accepted": True, "failures": []}

    namespace = {
        "Runtime": Runtime,
        "citation_registry": citation_registry,
        "citation_registry_digest": lambda registry: "digest",
        "validate_answer": validate_answer,
        "extract_latest_user": lambda payload: payload.get("query", ""),
        "http_json": http_json,
    }
    return namespace, Runtime, calls


def test_installed_writer_makes_exactly_one_call_and_accepts(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_CONSTRAINED_WRITER_ENABLED", "1")

    def response(payload):
        # The prompt contains a JSON packet, but for this integration test the
        # deterministic sections are stable and known.
        packet = _packet()
        return 200, {"choices": [{"message": {"content": _good_output(packet)}}]}

    namespace, Runtime, calls = _module_namespace(response)
    install_constrained_gemma_writer(namespace)
    result = Runtime().process({"query": "Locate part 120-26948-003 in the IPL table."})
    telemetry = result["constrained_gemma_writer"]
    assert len(calls) == 1
    assert telemetry["call_count"] == 1
    assert telemetry["structured_output_accepted"]
    assert not telemetry["phase3_fallback_used"]
    assert result["writer_mode"] == "constrained_gemma_structured_output_validated"


def test_installed_writer_falls_back_on_bad_schema(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_CONSTRAINED_WRITER_ENABLED", "1")

    def response(payload):
        return 200, {"choices": [{"message": {"content": '{"answer":["new"]}'}}]}

    namespace, Runtime, calls = _module_namespace(response)
    install_constrained_gemma_writer(namespace)
    result = Runtime().process({"query": "Locate part 120-26948-003 in the IPL table."})
    telemetry = result["constrained_gemma_writer"]
    assert len(calls) == 1
    assert telemetry["phase3_fallback_used"]
    assert not telemetry["structured_output_accepted"]
    assert result["content"] == CONTENT
    assert result["post_answer_validation"]["accepted"]


def test_non_canary_route_does_not_call_model(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_CONSTRAINED_WRITER_ENABLED", "1")

    def response(payload):
        raise AssertionError("model must not be called")

    namespace, Runtime, calls = _module_namespace(response)
    install_constrained_gemma_writer(namespace)
    result = Runtime().process({
        "query": "Show the diagram",
        "route": "visual_figure_callout_lookup",
    })
    telemetry = result["constrained_gemma_writer"]
    assert calls == []
    assert telemetry["call_count"] == 0
    assert telemetry["reason"] == "route_not_in_canary"


def test_install_is_idempotent(monkeypatch):
    monkeypatch.setenv("TRACE_NET_H30_CONSTRAINED_WRITER_ENABLED", "0")
    namespace, Runtime, calls = _module_namespace(lambda payload: (500, {}))
    install_constrained_gemma_writer(namespace)
    first = Runtime.process
    install_constrained_gemma_writer(namespace)
    assert Runtime.process is first
