#!/usr/bin/env python
"""Run realistic prompt-to-graph traceability regression tests."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.realistic_query_trace_tests import (  # noqa: E402
    default_realistic_trace_cases,
    run_realistic_trace_case,
    select_cases,
    summarize_realistic_trace_results,
    write_realistic_trace_results_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="local_config.yaml", help="Config path passed to ask_tiff_rag.py checks.")
    parser.add_argument("--case", action="append", default=[], help="Run only this case id. May be repeated.")
    parser.add_argument("--include-slow", action="store_true", help="Include slow LLM/RAG summary cases.")
    parser.add_argument("--list", action="store_true", help="List available cases and exit.")
    parser.add_argument("--write-json", action="store_true", help="Write JSON results.")
    parser.add_argument(
        "--json-output",
        default="local_data/evals/realistic_query_trace/realistic_query_trace_results.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    all_cases = default_realistic_trace_cases(include_slow=args.include_slow)
    if args.list:
        print("Realistic query trace test cases")
        for case in all_cases:
            slow = " slow" if case.slow else ""
            print(f"  {case.id} [{case.category}{slow}] - {case.description}")
            print(f"      prompt: {case.user_prompt}")
        return 0

    try:
        cases = select_cases(all_cases, args.case)
    except KeyError as exc:
        print("Realistic query trace tests")
        print("  Status: FAIL")
        print(f"  Error: {exc}")
        return 2

    print("Realistic query trace tests")
    print(f"  Cases selected: {len(cases)}")
    print(f"  Config: {args.config}")
    print("")

    results = []
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case.id}")
        print(f"  Prompt: {case.user_prompt}")
        result = run_realistic_trace_case(case, repo_root=REPO_ROOT, config=args.config)
        results.append(result)
        print(f"  {result.status} elapsed={result.elapsed_seconds:.2f}s checks={len(result.checks)}")
        for check in result.checks:
            print(f"    - {check.label}: {check.status} elapsed={check.elapsed_seconds:.2f}s returncode={check.returncode}")
            if check.missing_expected:
                print("      missing expected text:")
                for text in check.missing_expected:
                    print(f"        - {text}")
            if check.forbidden_found:
                print("      forbidden text found:")
                for text in check.forbidden_found:
                    print(f"        - {text}")
            if check.status != "pass" and check.stderr_preview:
                print("      stderr preview:")
                print(_indent(check.stderr_preview, "        "))

    summary = summarize_realistic_trace_results(results)
    print("\nRealistic query trace tests complete")
    print(f"  Total cases: {summary['total']}")
    print(f"  Case status counts: {summary['status_counts']}")
    print(f"  Command checks: {summary['check_pass']}/{summary['check_total']} passed")
    print(f"  Elapsed: {summary['elapsed_seconds']}s")

    if args.write_json:
        write_realistic_trace_results_json(results, args.json_output)
        print(f"  JSON: {args.json_output}")

    return 0 if summary.get("fail", 0) == 0 and summary.get("check_fail", 0) == 0 else 1


def _indent(text: str, prefix: str) -> str:
    return "\n".join(prefix + line for line in text.splitlines())


if __name__ == "__main__":
    raise SystemExit(main())
