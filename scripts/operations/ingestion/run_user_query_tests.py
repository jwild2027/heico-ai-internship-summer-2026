#!/usr/bin/env python
"""Run user-style query smoke tests against the local TIFF backend."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.user_query_tests import (  # noqa: E402
    default_user_query_cases,
    run_user_query_case,
    select_cases,
    summarize_results,
    write_results_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="local_config.yaml", help="Config path passed to ask_tiff_rag.py cases.")
    parser.add_argument("--case", action="append", default=[], help="Run only this case id. May be repeated.")
    parser.add_argument("--include-slow", action="store_true", help="Include broad LLM/RAG summary cases.")
    parser.add_argument("--list", action="store_true", help="List available cases and exit.")
    parser.add_argument("--write-json", action="store_true", help="Write JSON results.")
    parser.add_argument("--json-output", default="local_data/evals/user_query/user_query_test_results.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    all_cases = default_user_query_cases(include_slow=args.include_slow)
    if args.list:
        print("User query test cases")
        for case in all_cases:
            slow = " slow" if case.slow else ""
            print(f"  {case.id} [{case.category}{slow}] - {case.description}")
        return 0

    try:
        cases = select_cases(all_cases, args.case)
    except KeyError as exc:
        print(f"User query tests\n  Status: FAIL\n  Error: {exc}")
        return 2

    print("User query tests")
    print(f"  Cases selected: {len(cases)}")
    print(f"  Config: {args.config}")
    print("")

    results = []
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case.id}")
        result = run_user_query_case(case, repo_root=REPO_ROOT, config=args.config)
        results.append(result)
        print(f"  {result.status} elapsed={result.elapsed_seconds:.2f}s returncode={result.returncode}")
        if result.missing_expected:
            print("  missing expected text:")
            for text in result.missing_expected:
                print(f"    - {text}")
        if result.forbidden_found:
            print("  forbidden text found:")
            for text in result.forbidden_found:
                print(f"    - {text}")
        if result.status != "pass" and result.stderr_preview:
            print("  stderr preview:")
            print(_indent(result.stderr_preview, "    "))

    summary = summarize_results(results)
    print("\nUser query tests complete")
    print(f"  Total: {summary['total']}")
    print(f"  Status counts: {summary['status_counts']}")
    print(f"  Elapsed: {summary['elapsed_seconds']}s")

    if args.write_json:
        write_results_json(results, args.json_output)
        print(f"  JSON: {args.json_output}")

    return 0 if summary.get("fail", 0) == 0 and summary.get("timeout", 0) == 0 else 1


def _indent(text: str, prefix: str) -> str:
    return "\n".join(prefix + line for line in text.splitlines())


if __name__ == "__main__":
    raise SystemExit(main())
