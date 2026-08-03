from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_e2e_live_self_rag_crag_evaluator_v20 import add_common_args, evaluate_quality, load_json, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net live Self-RAG + CRAG evaluator v20 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    add_common_args(parser)
    args = parser.parse_args()

    report = load_json(args.report_path)
    checks = evaluate_quality(report, args)
    quality_status = "PASS" if all(c["passed"] for c in checks) else "FAIL"
    report["quality_status"] = quality_status
    report["quality_checks"] = checks
    if args.write_json:
        write_json(args.report_path, report)

    print("TRACE-Net E2E Live Self-RAG + CRAG Evaluator v20 Quality")
    print(f" quality_status: {quality_status}")
    for check in checks:
        status = "PASS" if check["passed"] else "FAIL"
        print(
            f" {status} {check['name']}: observed={check['observed']} expected={check['op']} {check['expected']}"
        )
    return 0 if quality_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
