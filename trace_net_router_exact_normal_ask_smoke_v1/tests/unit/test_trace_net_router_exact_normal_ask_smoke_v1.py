from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "run_trace_net_router_exact_normal_ask_smoke_v1.py"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "trace_net_router_exact_normal_ask_questions_v1.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("trace_net_router_exact_normal_ask_smoke_v1", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_exact_normal_ask_fixture_loads_with_expected_routes():
    mod = _load_module()
    questions = mod.load_questions(FIXTURE_PATH)
    assert len(questions) >= 8
    assert all(q["expected_route"] == "normal_ask" for q in questions)
    assert any("120-36833-001" in q["user_question"] for q in questions)


def test_extract_trace_payload_from_openai_style_response():
    mod = _load_module()
    response = {
        "choices": [{"message": {"content": "Clean assistant text"}}],
        "trace_net_payload": {
            "route": "normal_ask",
            "route_reason": "exact part lookup",
            "final_answer_allowed": False,
            "source_truth_mutation_allowed_count": 0,
        },
    }
    assert mod.extract_assistant_content(response) == "Clean assistant text"
    payload = mod.extract_trace_payload(response)
    assert payload["route"] == "normal_ask"


def test_json_blob_content_detector_flags_raw_payload_text():
    mod = _load_module()
    assert mod.looks_like_json_blob_content('{"trace_net_payload":{"route":"normal_ask"}}') is True
    assert mod.looks_like_json_blob_content("TRACE-Net found a candidate with citations.") is False


def test_route_record_passes_for_clean_normal_ask_payload():
    mod = _load_module()
    question = {
        "question_id": "exact_test",
        "challenge_type": "exact_known_covered_part",
        "user_question": "Find part number 120-36833-001",
        "expected_route": "normal_ask",
    }
    response = {
        "choices": [{"message": {"content": "Found a citation-backed draft. Final answer allowed: false."}}],
        "trace_net_payload": {
            "route": "normal_ask",
            "route_reason": "exact part lookup",
            "downstream_status_code": 200,
            "final_answer_allowed": False,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "citations": [{"page_id": "p000003"}],
        },
    }
    record = mod.route_record(question, response, 200, 0.01)
    assert record["quality_status"] == "PASS"
    assert record["route"] == "normal_ask"
    assert record["citation_backed_response"] is True
    assert record["assistant_content_looks_like_json_blob"] is False


def test_route_record_fails_for_guided_discovery_route_mismatch():
    mod = _load_module()
    question = {
        "question_id": "exact_test",
        "challenge_type": "exact_known_covered_part",
        "user_question": "Find part number 120-36833-001",
        "expected_route": "normal_ask",
    }
    response = {
        "choices": [{"message": {"content": "I need more details."}}],
        "trace_net_payload": {
            "route": "guided_discovery",
            "final_answer_allowed": False,
            "source_truth_mutation_allowed_count": 0,
        },
    }
    record = mod.route_record(question, response, 200, 0.01)
    assert record["quality_status"] == "FAIL"
    assert any("route_mismatch" in reason for reason in record["failure_reasons"])


def test_summary_requires_min_normal_ask_and_safety_clean():
    mod = _load_module()
    records = [
        {
            "quality_status": "PASS",
            "route": "normal_ask",
            "expected_route": "normal_ask",
            "trace_net_payload_present": True,
            "assistant_content_looks_like_json_blob": False,
            "citation_backed_response": True,
            "citation_count": 1,
            "final_answer_allowed": False,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "downstream_status_code": 200,
            "error": None,
        }
    ]
    summary = mod.summarize_records(
        records,
        question_file="fixture.json",
        endpoint_url="http://127.0.0.1:8017/v1/chat/completions",
        model="trace-net-router-proxy-v6",
        min_normal_ask_count=1,
        min_citation_backed_response_count=1,
        elapsed_seconds_total=0.01,
    )
    assert summary["quality_status"] == "PASS"
    assert summary["normal_ask_count"] == 1
    assert summary["citation_backed_response_count"] == 1
