import importlib.util
import json
import sys
from pathlib import Path


SCRIPT = Path("scripts/run_trace_net_router_followup_retrieval_benchmark_v1.py")
BANK = Path("tests/data/trace_net_router_followup_question_bank_v1.json")


def load():
    spec = importlib.util.spec_from_file_location("router_bench_v1", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["router_bench_v1"] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_question_bank_has_180_questions():
    data = json.loads(BANK.read_text(encoding="utf-8"))
    assert data["question_count"] == 180
    assert len(data["records"]) == 180


def test_all_router_and_followup_expectations_pass_without_retrieval():
    mod = load()
    data = json.loads(BANK.read_text(encoding="utf-8"))
    results = [mod.evaluate_record(row, retrieval_state=None) for row in data["records"]]
    failed = [row for row in results if row["quality_status"] != "PASS"]
    assert failed == []
