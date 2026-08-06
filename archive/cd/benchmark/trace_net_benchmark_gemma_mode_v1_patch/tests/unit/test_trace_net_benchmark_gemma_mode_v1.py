import importlib.util
import sys
from pathlib import Path


SCRIPT = Path("scripts/benchmark/run_trace_net_router_followup_retrieval_benchmark_v1.py")


def load():
    spec = importlib.util.spec_from_file_location("benchmark_gemma_mode_v1", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["benchmark_gemma_mode_v1"] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_parser_accepts_ollama_gemma_mode():
    mod = load()
    args = mod.build_parser().parse_args([
        "--llm-mode", "ollama",
        "--llm-model", "gemma4:26b",
        "--llm-base-url", "http://127.0.0.1:11434/v1",
        "--request-timeout", "600",
    ])
    assert args.llm_mode == "ollama"
    assert args.llm_model == "gemma4:26b"
    assert args.request_timeout == 600


def test_evaluate_record_keeps_retrieval_config_optional():
    mod = load()
    row = {
        "question_id": "q001",
        "category": "exact_part_lookup",
        "query": "Find part number 120-41824-003",
        "expected_execution_route": "normal_ask",
        "expected_tunnel": "exact_source_lookup",
        "min_follow_up_questions": 0,
        "required_follow_up_topics": [],
        "retrieval_expectation": "not_checked",
    }
    result = mod.evaluate_record(
        row,
        retrieval_state=None,
        retrieval_config={"llm_mode": "ollama", "llm_model": "gemma4:26b"},
    )
    assert result["quality_status"] == "PASS"
