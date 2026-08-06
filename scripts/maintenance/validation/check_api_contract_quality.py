from __future__ import annotations

from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.api_contract_quality import DEFAULT_OUTPUT, DEFAULT_RESULTS, evaluate_api_contract_quality, write_api_contract_quality


def _print_report(report, output_path: Path | None = None) -> None:
    summary = report.summary
    print("API contract quality gate")
    print(f"  Status: {report.status.upper()}")
    print("  Summary:")
    for key in sorted(summary):
        print(f"    {key}: {summary[key]}")
    print("  Checks:")
    for check in report.checks:
        print(f"    {check.status} {check.name}: {check.message}")
    if output_path:
        print(f"\nJSON: {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check API contract test quality results.")
    parser.add_argument("--results", default=str(DEFAULT_RESULTS))
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--json-output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--require-slow", action="store_true")
    args = parser.parse_args()

    report = evaluate_api_contract_quality(args.results, require_slow=args.require_slow)
    output_path = None
    if args.write_json:
        output_path = write_api_contract_quality(report, args.json_output)
    _print_report(report, output_path)
    return 0 if report.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
