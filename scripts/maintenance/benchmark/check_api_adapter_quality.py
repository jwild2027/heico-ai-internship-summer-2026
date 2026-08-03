from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.api_adapter_quality import (  # noqa: E402
    DEFAULT_API_ADAPTER_QUALITY_JSON,
    DEFAULT_API_READY_JSON,
    DEFAULT_STORAGE_READY_JSON,
    build_api_adapter_quality_report,
    write_api_adapter_quality_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TIFF API + storage-adapter readiness quality.")
    parser.add_argument("--api-ready-json", type=Path, default=DEFAULT_API_READY_JSON)
    parser.add_argument("--storage-ready-json", type=Path, default=DEFAULT_STORAGE_READY_JSON)
    parser.add_argument("--write-json", action="store_true")
    parser.add_argument("--json-output", type=Path, default=DEFAULT_API_ADAPTER_QUALITY_JSON)
    args = parser.parse_args()

    report = build_api_adapter_quality_report(args.api_ready_json, args.storage_ready_json)

    print("API/adapter quality gate")
    print(f"  Status: {report.status}")
    print("  Summary:")
    for key, value in report.summary.items():
        print(f"    {key}: {value}")
    print("  Checks:")
    for check in report.checks:
        print(f"    {check.status} {check.name}: {check.message}")
    if report.warnings:
        print("\nWarnings:")
        for warning in report.warnings:
            print(f"  - {warning}")

    if args.write_json:
        output = write_api_adapter_quality_report(report, args.json_output)
        print(f"\nJSON: {output}")

    return 0 if report.status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
