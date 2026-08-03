from scripts.benchmark.serving.serve_trace_net_full_gemma_user_query_canary_v1 import (
    validate_composed_answer,
)


def test_composer_rejects_invented_part_number():
    trace = {
        "citations": [{"citation_id": 1, "page_id": "p1"}],
    }
    failures = validate_composed_answer(
        "Use part 999-99999-999 [1].",
        upstream_answer="TRACE-Net found part 120-41824-003 [1].",
        trace=trace,
    )
    assert any(value.startswith("unsupported_part_number:") for value in failures)


def test_composer_accepts_grounded_answer():
    trace = {
        "citations": [{"citation_id": 1, "page_id": "p1"}],
    }
    failures = validate_composed_answer(
        "TRACE-Net found part 120-41824-003 [1].",
        upstream_answer="TRACE-Net found part 120-41824-003 [1].",
        trace=trace,
    )
    assert failures == []
