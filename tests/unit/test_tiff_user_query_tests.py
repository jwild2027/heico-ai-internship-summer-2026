from __future__ import annotations

from tiff.user_query_tests import (
    UserQueryCase,
    default_user_query_cases,
    run_user_query_case,
    select_cases,
    summarize_results,
)


def test_default_user_query_cases_have_core_rag_and_org_cases():
    cases = default_user_query_cases()
    ids = {case.id for case in cases}
    assert "org_part_120_37313_001" in ids
    assert "rag_exact_part_120_37313_001" in ids
    assert "rag_ata_25_21_00" in ids
    assert all(case.expected_contains for case in cases)


def test_include_slow_adds_broad_summary_case():
    cases = default_user_query_cases(include_slow=True)
    slow = [case for case in cases if case.slow]
    assert any(case.id == "rag_broad_summary_passenger_seat_back" for case in slow)


def test_select_cases_rejects_unknown_id():
    try:
        select_cases(default_user_query_cases(), ["does_not_exist"])
    except KeyError as exc:
        assert "does_not_exist" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected KeyError")


def test_run_user_query_case_passes_with_python_inline_command():
    case = UserQueryCase(
        id="inline_ok",
        category="unit",
        description="unit inline command",
        command=["-c", "print('hello user query')"],
        expected_contains=("hello user query",),
        timeout_seconds=5,
    )
    result = run_user_query_case(case)
    assert result.status == "pass"
    assert result.returncode == 0


def test_run_user_query_case_fails_when_expected_text_missing():
    case = UserQueryCase(
        id="inline_fail",
        category="unit",
        description="unit inline command",
        command=["-c", "print('hello')"],
        expected_contains=("not present",),
        timeout_seconds=5,
    )
    result = run_user_query_case(case)
    assert result.status == "fail"
    assert result.missing_expected == ["not present"]


def test_summarize_results_counts_statuses():
    case = UserQueryCase(id="x", category="unit", description="x", command=["-c", "print('x')"])
    r1 = run_user_query_case(case)
    summary = summarize_results([r1])
    assert summary["total"] == 1
    assert summary["pass"] == 1
