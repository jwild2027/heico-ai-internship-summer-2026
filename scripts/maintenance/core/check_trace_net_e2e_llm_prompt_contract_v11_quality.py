#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_e2e_llm_prompt_contract_v11 import (  # noqa: E402
    QUALITY_PASS,
    add_quality_args,
    evaluate_quality,
    print_quality_result,
    read_json,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net E2E LLM prompt contract v11 quality.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    add_quality_args(parser)
    args = parser.parse_args()

    report = read_json(args.report_path)
    quality_status, checks = evaluate_quality(report, args)
    report["quality_status"] = quality_status
    report.setdefault("summary", {})["quality_status"] = quality_status
    report["quality_checks"] = checks
    if args.write_json:
        write_json(args.report_path, report)
    print_quality_result(report, checks)
    return 0 if quality_status == QUALITY_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
