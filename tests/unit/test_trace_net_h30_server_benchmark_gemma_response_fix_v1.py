from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPO / "scripts/benchmark/validation/run_trace_net_h30_server_benchmark_200_v1.py"
LAUNCHER_PATH = REPO / "scripts/benchmark/operations/launch_trace_net_h30_server_benchmark_200_v1.sh"


def load_runner(name: str):
    spec = importlib.util.spec_from_file_location(name, RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def safe_result():
    return {
        "route": "safe_general_chat",
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "writer_mode": "deterministic_fail_closed",
        "post_answer_validation": {"accepted": True, "quality_status": "PASS", "failures": []},
        "evidence_envelope": {
            "direct_evidence": [],
            "candidate_evidence": [],
            "visual_guidance": [],
            "semantic_guidance": [],
            "authority_evidence": [],
            "contradictions": [],
            "uncertainties": [],
            "retrieval_tunnels_used": ["restricted_conversation_template"],
        },
    }


def rendered(answer: str = "Hello.") -> str:
    return json.dumps({
        "answer": answer,
        "follow_up_questions": [],
        "review": {
            "clue_satisfaction": "PASS",
            "source_support": "PASS",
            "citation_alignment": "PASS",
            "safety_boundary": "PASS",
            "notes": [],
        },
    })


def test_extract_ollama_chat_text_prefers_parseable_message_content():
    runner = load_runner("gemma_response_fix_content")
    text, source = runner.extract_ollama_chat_text({
        "message": {"content": rendered("Hello from content."), "thinking": rendered("Wrong field.")}
    })
    assert source == "message.content"
    assert runner.parse_gemma_json(text)["answer"] == "Hello from content."


def test_extract_ollama_chat_text_recovers_structured_thinking_field():
    runner = load_runner("gemma_response_fix_thinking")
    text, source = runner.extract_ollama_chat_text({
        "message": {"content": "", "thinking": rendered("Recovered safely.")}
    })
    assert source == "message.thinking"
    assert runner.parse_gemma_json(text)["answer"] == "Recovered safely."


def test_call_gemma_disables_thinking_and_retries_empty_response():
    runner = load_runner("gemma_response_fix_retry")
    calls = []

    def fake_post(url, api_key, payload, timeout):
        calls.append(payload)
        if len(calls) == 1:
            return 200, {"model": "gemma4:26b", "message": {"content": "", "thinking": ""}}
        return 200, {"model": "gemma4:26b", "message": {"content": rendered("Second attempt worked.")}}

    runner.post_json = fake_post
    result = runner.call_gemma_every_question(
        gemma_url="http://127.0.0.1:11434/api/chat",
        gemma_model="gemma4:26b",
        gemma_timeout=1200,
        question="hello",
        expected_route="safe_general_chat",
        result=safe_result(),
        safe_answer="Hello!",
    )
    assert len(calls) == 2
    assert all(call["think"] is False for call in calls)
    assert result["thinking_disabled"] is True
    assert result["attempt_count"] == 2
    assert result["answer"] == "Second attempt worked."
    assert result["content_source"] == "message.content"


def test_preflight_fails_closed_when_structured_answers_are_empty():
    runner = load_runner("gemma_response_fix_preflight_fail")

    def fake_call(**kwargs):
        return {
            "http_status_code": 200,
            "answer": "",
            "thinking_disabled": True,
            "content_source": "none",
            "attempt_count": 2,
            "elapsed_seconds": 0.1,
            "response_diagnostic": {"message_content_chars": 0},
        }

    runner.call_gemma_every_question = fake_call
    result = runner.preflight_gemma_structured_output(
        gemma_url="http://127.0.0.1:11434/api/chat",
        gemma_model="gemma4:26b",
        gemma_timeout=1200,
        probe_count=3,
    )
    assert result["quality_status"] == "FAIL"
    assert result["pass_count"] == 0
    assert result["probe_count"] == 3


def test_preflight_passes_only_with_nonempty_answers_and_thinking_disabled():
    runner = load_runner("gemma_response_fix_preflight_pass")

    def fake_call(**kwargs):
        return {
            "http_status_code": 200,
            "answer": "Hello.",
            "thinking_disabled": True,
            "content_source": "message.content",
            "attempt_count": 1,
            "elapsed_seconds": 0.1,
            "response_diagnostic": {"message_content_chars": 6},
        }

    runner.call_gemma_every_question = fake_call
    result = runner.preflight_gemma_structured_output(
        gemma_url="http://127.0.0.1:11434/api/chat",
        gemma_model="gemma4:26b",
        gemma_timeout=1200,
        probe_count=3,
    )
    assert result["quality_status"] == "PASS"
    assert result["pass_count"] == 3


def test_launcher_uses_fresh_runtime_and_structured_preflight():
    text = LAUNCHER_PATH.read_text(encoding="utf-8")
    assert "cognitive_benchmark_200_failure_repair_v1" in text
    assert "--gemma-preflight-count 3" in text
    assert "think=false" in text
