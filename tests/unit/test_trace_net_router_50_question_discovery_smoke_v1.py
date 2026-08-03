import json
from pathlib import Path

import importlib.util
import sys

SCRIPT_PATH = Path("scripts/benchmark/run_trace_net_router_50_question_discovery_smoke_v1.py")
FIXTURE_PATH = Path("tests/fixtures/trace_net_router_50_question_discovery_questions_v1.json")


def _load_module():
    spec = importlib.util.spec_from_file_location("router_50q", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_question_fixture_has_50_records_and_3_followups_each():
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert data["schema_version"] == "trace_net_router_50_question_discovery_questions_v1"
    records = data["records"]
    assert len(records) == 50
    seen = set()
    for record in records:
        assert record["id"] not in seen
        seen.add(record["id"])
        assert record["user_question"].strip()
        assert record["challenge_type"].strip()
        assert len(record["expected_followup_questions"]) == 3
        assert all(q.endswith("?") for q in record["expected_followup_questions"])


def test_count_assistant_questions_handles_numbered_questions():
    mod = _load_module()
    text = "Helpful details:\n1. Do you know the manufacturer?\n2. Was it in a table?\n3. Which page was it on?"
    assert mod.count_assistant_questions(text) == 3


def test_extract_assistant_content_from_openai_shape():
    mod = _load_module()
    payload = {"choices": [{"message": {"role": "assistant", "content": "hello"}}]}
    assert mod.extract_assistant_content(payload) == "hello"


def test_extract_router_payload_falls_back_to_response():
    mod = _load_module()
    router, trace_payload = mod.extract_router_payload({"quality_status": "PASS"})
    assert router == {}
    assert trace_payload["quality_status"] == "PASS"


def test_summarize_passes_when_safety_and_questions_are_good():
    mod = _load_module()
    record = mod.SmokeRecord(
        question_id="q001",
        challenge_type="partial_prefix",
        user_question="I only know the part starts with 24.",
        expected_followup_questions=["a?", "b?", "c?"],
        status="DONE",
        quality_status="PASS",
        route="guided_discovery",
        route_reason="weak",
        downstream_endpoint="http://127.0.0.1:8016/api/trace-net/guided-discovery",
        downstream_status_code=200,
        assistant_content="1. A?\n2. B?\n3. C?",
        assistant_question_count=3,
        final_answer_allowed=False,
        source_truth_mutation_allowed_count=0,
        elapsed_seconds=1.0,
        error=None,
    )
    summary = mod.summarize([record], Path("questions.json"), "http://localhost", "model")
    assert summary["quality_status"] == "PASS"
    assert summary["route_counts"] == {"guided_discovery": 1}
    assert summary["records_with_3plus_assistant_questions"] == 1


def test_summarize_fails_on_final_answer_permission():
    mod = _load_module()
    record = mod.SmokeRecord(
        question_id="q010",
        challenge_type="safety_sensitive_interchangeability",
        user_question="Can A replace B?",
        expected_followup_questions=["a?", "b?", "c?"],
        status="DONE",
        quality_status="PASS",
        route="normal_ask",
        route_reason="ordinary",
        downstream_endpoint="http://127.0.0.1:8014/api/trace-net/ask",
        downstream_status_code=200,
        assistant_content="1. A?\n2. B?\n3. C?",
        assistant_question_count=3,
        final_answer_allowed=True,
        source_truth_mutation_allowed_count=0,
        elapsed_seconds=1.0,
        error=None,
    )
    summary = mod.summarize([record], Path("questions.json"), "http://localhost", "model")
    assert summary["quality_status"] == "FAIL"
    assert summary["final_answer_allowed_true_count"] == 1


def test_write_outputs_creates_expected_files(tmp_path):
    mod = _load_module()
    record = mod.SmokeRecord(
        question_id="q001",
        challenge_type="partial_prefix",
        user_question="I only know the part starts with 24.",
        expected_followup_questions=["a?", "b?", "c?"],
        status="DONE",
        quality_status="PASS",
        route="guided_discovery",
        route_reason="weak",
        downstream_endpoint="http://127.0.0.1:8016/api/trace-net/guided-discovery",
        downstream_status_code=200,
        assistant_content="1. A?\n2. B?\n3. C?",
        assistant_question_count=3,
        final_answer_allowed=False,
        source_truth_mutation_allowed_count=0,
        elapsed_seconds=1.0,
        error=None,
    )
    summary = mod.summarize([record], Path("questions.json"), "http://localhost", "model")
    paths = mod.write_outputs([record], summary, tmp_path)
    assert Path(paths["results"]).exists()
    assert Path(paths["summary"]).exists()
    assert Path(paths["report"]).exists()
    assert "q001" in Path(paths["report"]).read_text(encoding="utf-8")
