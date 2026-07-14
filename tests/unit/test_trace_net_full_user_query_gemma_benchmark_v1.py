import importlib.util
import sys
from pathlib import Path


SCRIPT = Path("scripts/run_trace_net_full_user_query_gemma_benchmark_v1.py")


def load():
    spec = importlib.util.spec_from_file_location("full_user_query_bench_v1", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["full_user_query_bench_v1"] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_evaluate_requires_gemma_and_user_visible_followups():
    mod = load()
    record = {
        "question_id": "q001",
        "category": "descriptive_part_nomenclature",
        "query": "I would like a part that is a hinge",
        "expected_execution_route": "guided_discovery",
        "expected_tunnel": "descriptive_part_discovery",
        "min_follow_up_questions": 2,
        "retrieval_expectation": "not_checked",
    }
    response = {
        "choices": [{
            "message": {
                "content": "I can help narrow that down. Do you remember any part-number characters? Which company made it?",
            }
        }],
        "trace_net": {
            "route": "guided_discovery",
            "retrieval_tunnel": "descriptive_part_discovery",
            "follow_up_questions": [
                "Do you remember any part-number characters?",
                "Which company made it?",
            ],
            "response_composer_called": True,
            "response_composer_status": "LLM_CALL_SUCCEEDED",
            "response_composer_model": "gemma4:26b",
            "answer_permission": False,
            "final_answer_allowed": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
            "citation_count": 0,
        },
    }
    result = mod.evaluate(
        record,
        status_code=200,
        response=response,
        latency_ms=5000,
        transport_error="",
    )
    assert result["quality_status"] == "PASS"
