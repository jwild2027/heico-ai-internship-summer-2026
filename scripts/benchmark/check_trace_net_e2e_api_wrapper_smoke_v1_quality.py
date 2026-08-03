#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_api_wrapper_smoke_v1 import add_common_args, evaluate_quality, thresholds_from_args


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net E2E API Wrapper Smoke v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    add_common_args(parser)
    args = parser.parse_args()

    path = Path(args.report_path)
    report = json.loads(path.read_text(encoding="utf-8"))
    quality = evaluate_quality(report, thresholds_from_args(args))
    print("TRACE-Net E2E API Wrapper Smoke v1 Quality")
    print(f" quality_status: {quality['quality_status']}")
    for check in quality["checks"]:
        status = "PASS" if check["passed"] else "FAIL"
        print(f" {status} {check['name']}: observed={check['observed']} expected={check['operator']} {check['expected']}")
    if args.write_json:
        out = path.with_name("trace_net_e2e_api_wrapper_smoke_v1_quality.json")
        out.write_text(json.dumps(quality, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if quality["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
