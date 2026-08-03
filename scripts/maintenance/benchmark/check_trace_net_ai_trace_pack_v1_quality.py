#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_ai_trace_pack_v1 import (
    check_trace_pack_quality,
    load_json,
    print_trace_pack_summary,
    thresholds_from_args,
    add_threshold_args,
    write_json,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net AI Trace Pack v1 quality")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--write-json", action="store_true")
    add_threshold_args(parser)
    args = parser.parse_args(argv)

    report = load_json(args.report_path)
    quality = check_trace_pack_quality(report, thresholds_from_args(args))
    if args.write_json:
        out = Path(args.report_path).with_name("trace_net_ai_trace_pack_v1_quality.json")
        write_json(out, quality)
    print_trace_pack_summary(report | {"quality_status": quality["quality_status"]})
    if quality.get("failures"):
        print(" Failures:")
        for failure in quality["failures"]:
            print("  -", failure)
    return 0 if quality["quality_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
