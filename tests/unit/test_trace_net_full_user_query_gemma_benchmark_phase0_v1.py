import importlib.util
import json
import sys
from pathlib import Path


SCRIPT = Path("scripts/benchmark/validation/run_trace_net_full_user_query_gemma_benchmark_v1.py")


def load():
    spec = importlib.util.spec_from_file_location("full_user_query_bench_phase0_v1", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["full_user_query_bench_phase0_v1"] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def fake_result(record):
    return {
        "question_id": record["question_id"],
        "category": record["category"],
        "query": record["query"],
        "contract": "h30_mature_cognitive",
        "legacy_expected_route": "",
        "expected_route": "guided_part_discovery",
        "actual_route": "guided_part_discovery",
        "legacy_expected_tunnel": "",
        "expected_tunnels": ["part_prefix"],
        "planned_tunnels": ["part_prefix"],
        "used_tunnels": ["part_prefix"],
        "actual_tunnels": ["part_prefix"],
        "http_status": 200,
        "latency_ms": 10.0,
        "transport_error": "",
        "answer": f"Complete answer for {record['question_id']}",
        "answer_character_count": 24,
        "citation_count": 0,
        "direct_evidence_count": 0,
        "candidate_evidence_count": 1,
        "follow_up_questions": ["Do you remember more digits?"],
        "writer_contract": "h30_mature_cognitive",
        "writer_expected": False,
        "writer_called": False,
        "writer_successful": False,
        "writer_skipped_expected": True,
        "writer_status": "SKIPPED_NO_DIRECT_EVIDENCE",
        "writer_mode": "deterministic_candidate",
        "writer_model": "",
        "response_composer_called": False,
        "response_composer_status": "SKIPPED_NO_DIRECT_EVIDENCE",
        "response_composer_model": "",
        "quality_status": "PASS",
        "failures": [],
        "trace_net": {},
    }


def test_main_can_resume_without_repeating_completed_questions(tmp_path, monkeypatch):
    mod = load()
    bank = tmp_path / "bank.json"
    bank.write_text(json.dumps({"records": [
        {"question_id": "q001", "category": "partial", "query": "starts 123"},
        {"question_id": "q002", "category": "partial", "query": "starts 456"},
    ]}), encoding="utf-8")
    output = tmp_path / "run"
    calls = []

    monkeypatch.setattr(mod, "post_chat", lambda **kwargs: (200, {}, 10.0, ""))

    def evaluate(record, **kwargs):
        calls.append(record["question_id"])
        return fake_result(record)

    monkeypatch.setattr(mod, "evaluate", evaluate)

    first = mod.main([
        "--question-bank", str(bank),
        "--output-dir", str(output),
        "--limit", "1",
        "--report-every", "1",
    ])
    assert first == 0
    assert calls == ["q001"]

    second = mod.main([
        "--question-bank", str(bank),
        "--output-dir", str(output),
        "--resume",
        "--report-every", "1",
    ])
    assert second == 0
    assert calls == ["q001", "q002"]

    records = [json.loads(line) for line in (output / "records.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [row["question_id"] for row in records] == ["q001", "q002"]
    full_report = (output / "question_answer_report/full_question_answers.md").read_text(encoding="utf-8")
    assert "Complete answer for q001" in full_report
    assert "Complete answer for q002" in full_report


def test_resume_repairs_trailing_partial_json(tmp_path, monkeypatch):
    mod = load()
    bank = tmp_path / "bank.json"
    bank.write_text(json.dumps({"records": [
        {"question_id": "q001", "category": "partial", "query": "starts 123"},
        {"question_id": "q002", "category": "partial", "query": "starts 456"},
    ]}), encoding="utf-8")
    output = tmp_path / "run"
    output.mkdir()
    first = fake_result({"question_id": "q001", "category": "partial", "query": "starts 123"})
    (output / "records.jsonl").write_text(json.dumps(first) + "\n" + '{"question_id":"broken"', encoding="utf-8")

    monkeypatch.setattr(mod, "post_chat", lambda **kwargs: (200, {}, 10.0, ""))
    monkeypatch.setattr(mod, "evaluate", lambda record, **kwargs: fake_result(record))

    result = mod.main([
        "--question-bank", str(bank),
        "--output-dir", str(output),
        "--resume",
    ])
    assert result == 0
    rows = [json.loads(line) for line in (output / "records.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [row["question_id"] for row in rows] == ["q001", "q002"]
