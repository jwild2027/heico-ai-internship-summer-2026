from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.api_contract_tests import (  # noqa: E402
    DEFAULT_BASE_URL,
    DEFAULT_OUTPUT,
    case_ids,
    default_contract_cases,
    run_api_contract_tests,
    write_contract_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TIFF FastAPI contract tests.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--in-process", action="store_true", help="Run against FastAPI TestClient instead of live HTTP.")
    parser.add_argument("--include-slow", action="store_true", help="Include slow LLM/RAG API cases.")
    parser.add_argument("--case", action="append", default=[], help="Run one case id; can be repeated.")
    parser.add_argument("--list", action="store_true", help="List available cases and exit.")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--json-output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if args.list:
        for case in default_contract_cases(include_slow=True):
            slow = " slow" if case.slow else ""
            print(f"{case.case_id}{slow}: {case.description}")
        return 0

    report = run_api_contract_tests(
        base_url=args.base_url,
        in_process=args.in_process,
        include_slow=args.include_slow,
        case_ids=args.case,
        timeout_seconds=args.timeout_seconds,
    )

    print("API contract tests")
    print(f"  Status: {str(report.get('status', '')).upper()}")
    print(f"  Mode: {report.get('mode_label')}")
    if not args.in_process:
        print(f"  Base URL: {report.get('base_url')}")
    print(f"  Cases selected: {report.get('total')}")
    print()

    cases = report.get("cases", []) or []
    for index, result in enumerate(cases, start=1):
        status = result.get("status")
        http_status = result.get("http_status")
        elapsed = float(result.get("elapsed_seconds") or 0.0)
        print(f"[{index}/{len(cases)}] {result.get('case_id')}")
        print(f"  {status} elapsed={elapsed:.2f}s status={http_status}")
        if result.get("error"):
            print(f"  error: {result.get('error')}")
        if result.get("missing_expected_text"):
            print("  missing expected text:")
            for item in result.get("missing_expected_text") or []:
                print(f"    - {item}")

    print()
    print("API contract tests complete")
    print(f"  Total: {report.get('total')}")
    print(f"  Status counts: {report.get('status_counts')}")
    print(f"  Elapsed: {float(report.get('elapsed_seconds') or 0.0):.3f}s")

    if args.write_json:
        path = write_contract_report(report, args.json_output)
        print(f"  JSON: {path}")

    return 0 if report.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
