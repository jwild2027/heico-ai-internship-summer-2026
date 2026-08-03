from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_table_route_retrieval_demo_query_pack_v1 import (  # noqa: E402
    QUALITY_NAME,
    add_threshold_args,
    evaluate_quality,
    thresholds_from_args,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net table route retrieval demo query pack v1 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    add_threshold_args(parser)
    args = parser.parse_args()

    report_path = Path(args.report_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    summary = report.get("summary", {})
    checks = evaluate_quality(summary, thresholds_from_args(args))
    quality_status = "PASS" if all(check["passed"] for check in checks) else "FAIL"
    payload = {"quality_status": quality_status, "summary": summary, "quality_checks": checks}
    if args.write_json:
        (report_path.parent / QUALITY_NAME).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("TRACE-Net Table Route Retrieval Demo Query Pack v1 Quality")
    print(" quality_status:", quality_status)
    for check in checks:
        label = "PASS" if check["passed"] else "FAIL"
        print(f" {label} {check['name']}: observed={check['observed']} expected={check['expected']}")
    return 0 if quality_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
