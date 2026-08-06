from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_table_route_retrieval_readiness_report_v1 import (  # noqa: E402
    add_threshold_args,
    check_report_quality,
    thresholds_from_args,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net table route retrieval readiness report v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    add_threshold_args(parser)
    args = parser.parse_args()
    result = check_report_quality(args.report_path, thresholds_from_args(args), write_json=args.write_json)
    print("TRACE-Net Table Route Retrieval Readiness Report v1 Quality")
    print(" quality_status:", result["quality_status"])
    for check in result["quality_checks"]:
        mark = "PASS" if check["passed"] else "FAIL"
        print(f" {mark} {check['name']}: observed={check['observed']} expected={check['expected']}")
    return 0 if result["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
