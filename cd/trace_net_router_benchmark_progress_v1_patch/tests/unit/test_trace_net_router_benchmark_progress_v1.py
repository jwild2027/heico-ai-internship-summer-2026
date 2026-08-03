import importlib.util
import json
import sys
from pathlib import Path


SCRIPT = Path("scripts/benchmark/run_trace_net_router_followup_retrieval_benchmark_v1.py")


def load():
    spec = importlib.util.spec_from_file_location("router_progress_v1", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["router_progress_v1"] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_progress_prints_question_fraction(tmp_path, capsys):
    mod = load()
    bank = {
        "records": [
            {
                "question_id": "q001",
                "category": "exact_part_lookup",
                "query": "Find part number 120-41824-003",
                "expected_execution_route": "normal_ask",
                "expected_tunnel": "exact_source_lookup",
                "min_follow_up_questions": 0,
                "required_follow_up_topics": [],
                "retrieval_expectation": "not_checked",
            },
            {
                "question_id": "q002",
                "category": "descriptive_part_nomenclature",
                "query": "I would like a part that is a hinge",
                "expected_execution_route": "guided_discovery",
                "expected_tunnel": "descriptive_part_discovery",
                "min_follow_up_questions": 4,
                "required_follow_up_topics": ["part_number", "manufacturer"],
                "retrieval_expectation": "not_checked",
            },
        ]
    }
    bank_path = tmp_path / "bank.json"
    out = tmp_path / "out"
    bank_path.write_text(json.dumps(bank), encoding="utf-8")

    code = mod.main([
        "--question-bank", str(bank_path),
        "--output-dir", str(out),
        "--limit", "2",
    ])
    captured = capsys.readouterr().out

    assert code == 0
    assert "[1/2] RUNNING q001" in captured
    assert "[1/2] PASS" in captured
    assert "[2/2] RUNNING q002" in captured
    assert "[2/2] PASS" in captured
