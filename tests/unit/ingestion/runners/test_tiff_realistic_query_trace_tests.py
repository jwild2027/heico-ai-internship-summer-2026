from __future__ import annotations

import pytest

from tiff.realistic_query_trace_tests import (
    CommandCheck,
    CommandCheckResult,
    RealisticTraceResult,
    default_realistic_trace_cases,
    select_cases,
    summarize_realistic_trace_results,
)


def test_default_cases_include_vector_to_graph_case() -> None:
    cases = default_realistic_trace_cases()
    ids = {case.id for case in cases}
    assert "vector_payload_page_000495_to_graph_context" in ids
    vector_case = next(case for case in cases if case.id == "vector_payload_page_000495_to_graph_context")
    assert any("--vector-page" in check.command for check in vector_case.checks)
    assert vector_case.category == "vector_to_graph"


def test_default_cases_have_prompts_and_checks() -> None:
    cases = default_realistic_trace_cases()
    assert len(cases) >= 6
    for case in cases:
        assert case.user_prompt
        assert case.checks
        for check in case.checks:
            assert check.label
            assert check.command
            assert check.expected_contains or check.expected_not_contains


def test_include_slow_adds_rag_vector_case() -> None:
    fast_ids = {case.id for case in default_realistic_trace_cases(include_slow=False)}
    slow_cases = default_realistic_trace_cases(include_slow=True)
    slow_ids = {case.id for case in slow_cases}
    assert len(slow_ids) == len(fast_ids) + 1
    assert "slow_rag_summary_passenger_seat_back_to_graph" in slow_ids
    assert any(case.slow for case in slow_cases)


def test_select_cases_rejects_unknown() -> None:
    cases = default_realistic_trace_cases()
    with pytest.raises(KeyError):
        select_cases(cases, ["does_not_exist"])


def test_select_cases_preserves_requested_order() -> None:
    cases = default_realistic_trace_cases()
    selected = select_cases(cases, ["page_prompt_000083_to_part_context_source", "part_prompt_120_37313_001_to_graph"])
    assert [case.id for case in selected] == [
        "page_prompt_000083_to_part_context_source",
        "part_prompt_120_37313_001_to_graph",
    ]


def test_command_check_resolves_config_placeholder() -> None:
    check = CommandCheck(label="x", command=("script.py", "--config", "{config}", "prompt"))
    assert check.resolved_command("abc.yaml") == ["script.py", "--config", "abc.yaml", "prompt"]


def test_summarize_realistic_trace_results_counts_check_failures() -> None:
    results = [
        RealisticTraceResult(
            id="a",
            category="x",
            description="A",
            user_prompt="prompt",
            status="pass",
            elapsed_seconds=1.2,
            checks=[
                CommandCheckResult(label="a1", command=["python"], status="pass", elapsed_seconds=0.5, returncode=0),
                CommandCheckResult(label="a2", command=["python"], status="pass", elapsed_seconds=0.5, returncode=0),
            ],
        ),
        RealisticTraceResult(
            id="b",
            category="x",
            description="B",
            user_prompt="prompt",
            status="fail",
            elapsed_seconds=2.0,
            checks=[CommandCheckResult(label="b1", command=["python"], status="fail", elapsed_seconds=1.0, returncode=1)],
        ),
    ]
    summary = summarize_realistic_trace_results(results)
    assert summary["total"] == 2
    assert summary["pass"] == 1
    assert summary["fail"] == 1
    assert summary["check_total"] == 3
    assert summary["check_pass"] == 2
    assert summary["check_fail"] == 1
