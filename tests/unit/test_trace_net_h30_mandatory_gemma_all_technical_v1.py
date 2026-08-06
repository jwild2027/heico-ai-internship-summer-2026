import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = Path(
    "src/trace_net/writing/constrained_writer/trace_net_h30_constrained_gemma_writer_v1.py"
)
PUBLIC_CONTRACT_PATH = Path(
    "src/trace_net/writing/answer_contracts/trace_net_h30_public_answer_contract_v1.py"
)
RESIDENT_LAUNCHER = Path(
    "scripts/operations/launch_trace_net_gemma_resident_openwebui_v2_1.sh"
)
COGNITIVE_LAUNCHER = Path(
    "scripts/operations/launch_trace_net_cognitive_openwebui_v1.sh"
)


def load_path(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def load_module():
    return load_path("mandatory_gemma_writer_test", MODULE_PATH)


def canonical_result(route="visual_figure_callout_lookup"):
    return {
        "route": route,
        "content": (
            "## Answer\n\n"
            "No source-supported result can be confirmed for this request.\n\n"
            "## Evidence\n\n"
            "- No citation-ready source evidence was recovered.\n\n"
            "## Limits\n\n"
            "- The requested technical claim remains unconfirmed."
        ),
        "post_answer_validation": {
            "quality_status": "PASS",
            "accepted": True,
            "failures": [],
        },
        "evidence_envelope": {},
        "answer_mode": {"mode": "no_evidence"},
        "gemma_status": "SKIPPED_BY_TYPED_EVIDENCE_MODE",
        "writer_mode": "public_answer_contract_v1",
    }


def test_config_parses_mandatory_technical_switch():
    module = load_module()
    config = module.load_constrained_writer_config({
        "TRACE_NET_H30_CONSTRAINED_WRITER_ENABLED": "1",
        module.MANDATORY_TECHNICAL_ENV: "1",
    })
    assert config["enabled"] is True
    assert config["mandatory_technical_routes"] is True


def test_every_public_technical_route_is_eligible_without_registry_or_citations():
    module = load_module()
    public_contract = load_path("mandatory_public_contract_test", PUBLIC_CONTRACT_PATH)
    config = module.load_constrained_writer_config({
        "TRACE_NET_H30_CONSTRAINED_WRITER_ENABLED": "1",
        module.MANDATORY_TECHNICAL_ENV: "1",
    })
    assert set(module.MANDATORY_TECHNICAL_ROUTES) == set(
        public_contract.TECHNICAL_ROUTES
    )
    for route in sorted(public_contract.TECHNICAL_ROUTES):
        eligible, reason = module._eligible_for_call(
            result=canonical_result(route),
            config=config,
            registry=[],
        )
        assert eligible is True, (route, reason)
        assert reason == "eligible_mandatory_validated_technical_route"


def test_nontechnical_route_is_not_forced_into_writer():
    module = load_module()
    config = module.load_constrained_writer_config({
        "TRACE_NET_H30_CONSTRAINED_WRITER_ENABLED": "1",
        module.MANDATORY_TECHNICAL_ENV: "1",
    })
    eligible, reason = module._eligible_for_call(
        result=canonical_result("safe_general_chat"),
        config=config,
        registry=[],
    )
    assert eligible is False
    assert reason == "non_technical_route"


def test_legacy_canary_behavior_remains_when_mandatory_switch_is_off():
    module = load_module()
    config = module.load_constrained_writer_config({
        "TRACE_NET_H30_CONSTRAINED_WRITER_ENABLED": "1",
        module.MANDATORY_TECHNICAL_ENV: "0",
    })
    eligible, reason = module._eligible_for_call(
        result=canonical_result("visual_figure_callout_lookup"),
        config=config,
        registry=[],
    )
    assert eligible is False
    assert reason == "route_not_in_canary"


def install_fake_runtime(module, *, response_text):
    calls = []

    class FakeRuntime:
        gemma_model = "gemma4:26b"
        gemma_base_url = "http://127.0.0.1:11434/v1"
        gemma_api_key = "ollama"

        def process(self, payload):
            return canonical_result()

        def health(self):
            return {"quality_status": "PASS"}

    def fake_http_json(url, payload, *, api_key, timeout):
        calls.append({
            "url": url,
            "payload": payload,
            "api_key": api_key,
            "timeout": timeout,
        })
        return 200, {
            "choices": [{
                "message": {"content": response_text}
            }]
        }

    module_dict = {
        "Runtime": FakeRuntime,
        "citation_registry": lambda result: [],
        "citation_registry_digest": lambda registry: "empty-registry",
        "validate_answer": lambda *args, **kwargs: {
            "quality_status": "PASS",
            "accepted": True,
            "failures": [],
        },
        "extract_latest_user": lambda payload: "Show the requested diagram.",
        "synthesis_allowed_identifiers": lambda query, result: {
            "parts": set(), "atas": set(), "pages": set()
        },
        "http_json": fake_http_json,
    }
    module.install_constrained_gemma_writer(module_dict)
    return FakeRuntime, calls


def test_mandatory_mode_attempts_exactly_one_call_without_registry(monkeypatch):
    module = load_module()
    monkeypatch.setenv("TRACE_NET_H30_CONSTRAINED_WRITER_ENABLED", "1")
    monkeypatch.setenv(module.MANDATORY_TECHNICAL_ENV, "1")
    monkeypatch.setenv(
        "TRACE_NET_H30_CONSTRAINED_WRITER_OVERALL_BUDGET_SECONDS", "30"
    )
    monkeypatch.setenv(
        "TRACE_NET_H30_CONSTRAINED_WRITER_RESPONSE_RESERVE_SECONDS", "1"
    )
    monkeypatch.setenv(
        "TRACE_NET_H30_CONSTRAINED_WRITER_MIN_CALL_SECONDS", "1"
    )
    response = json.dumps({
        "schema_version": module.OUTPUT_SCHEMA_VERSION,
        "answer": [
            "No source-supported result can be confirmed for this request."
        ],
    })
    runtime_cls, calls = install_fake_runtime(module, response_text=response)
    output = runtime_cls().process({"query": "Show the requested diagram."})
    telemetry = output["constrained_gemma_writer"]
    assert len(calls) == 1
    assert telemetry["call_count"] == 1
    assert telemetry["mandatory_call_required"] is True
    assert telemetry["mandatory_call_satisfied"] is True
    assert telemetry["structured_output_accepted"] is True
    assert output["gemma_status"] == (
        "CONSTRAINED_GEMMA_CALL_SUCCEEDED_AND_VALIDATED"
    )
    assert "## Evidence" in output["content"]
    assert "## Limits" in output["content"]


def test_rejected_model_output_still_uses_one_attempt_and_safe_fallback(monkeypatch):
    module = load_module()
    monkeypatch.setenv("TRACE_NET_H30_CONSTRAINED_WRITER_ENABLED", "1")
    monkeypatch.setenv(module.MANDATORY_TECHNICAL_ENV, "1")
    monkeypatch.setenv(
        "TRACE_NET_H30_CONSTRAINED_WRITER_OVERALL_BUDGET_SECONDS", "30"
    )
    monkeypatch.setenv(
        "TRACE_NET_H30_CONSTRAINED_WRITER_RESPONSE_RESERVE_SECONDS", "1"
    )
    monkeypatch.setenv(
        "TRACE_NET_H30_CONSTRAINED_WRITER_MIN_CALL_SECONDS", "1"
    )
    runtime_cls, calls = install_fake_runtime(
        module,
        response_text="not valid structured JSON",
    )
    output = runtime_cls().process({"query": "Show the requested diagram."})
    telemetry = output["constrained_gemma_writer"]
    assert len(calls) == 1
    assert telemetry["call_count"] == 1
    assert telemetry["mandatory_call_satisfied"] is True
    assert telemetry["phase3_fallback_used"] is True
    assert "No source-supported result" in output["content"]
    assert "## Evidence" in output["content"]


def test_health_exposes_mandatory_policy():
    module = load_module()
    health = module.constrained_writer_health({
        "TRACE_NET_H30_CONSTRAINED_WRITER_ENABLED": "1",
        module.MANDATORY_TECHNICAL_ENV: "1",
    })
    assert health["mandatory_technical_routes_enabled"] is True
    assert health["validated_technical_route_call_policy"] == (
        "exactly_one_constrained_attempt"
    )
    assert set(health["mandatory_technical_routes"]) == set(
        module.MANDATORY_TECHNICAL_ROUTES
    )


def test_launchers_enable_and_export_mandatory_policy():
    for path in (RESIDENT_LAUNCHER, COGNITIVE_LAUNCHER):
        text = path.read_text(encoding="utf-8")
        assert (
            "TRACE_NET_H30_CONSTRAINED_WRITER_MANDATORY_TECHNICAL_ROUTES"
            in text
        )
    resident = RESIDENT_LAUNCHER.read_text(encoding="utf-8")
    assert "mandatory_technical_gemma_enabled" in resident
