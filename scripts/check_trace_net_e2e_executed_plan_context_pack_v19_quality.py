from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse

from tiff.trace_net_e2e_executed_plan_context_pack_v19 import (
    QUALITY_PASS,
    add_common_quality_args,
    evaluate_quality,
    load_json,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net E2E executed-plan context pack v19 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    add_common_quality_args(parser)
    args = parser.parse_args()

    report = load_json(args.report_path)
    status, checks = evaluate_quality(report, args)
    report["quality_status"] = status
    report["quality_checks"] = checks
    if args.write_json:
        write_json(args.report_path, report)

    print("TRACE-Net E2E Executed Plan Context Pack v19 Quality")
    print(f" quality_status: {status}")
    for check in checks:
        prefix = "PASS" if check["passed"] else "FAIL"
        print(f" {prefix} {check['name']}: observed={check['observed']} expected={check['op']} {check['expected']}")
    return 0 if status == QUALITY_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
