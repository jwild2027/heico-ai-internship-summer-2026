#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff.trace_net_e2e_dynamic_query_endpoint_v1 import quality_check


def main() -> int:
    ap = argparse.ArgumentParser(description="Check TRACE-Net E2E dynamic query endpoint manifest quality v1")
    ap.add_argument("--report-path", type=Path, required=True)
    ap.add_argument("--min-exact-search-documents", type=int, default=1000)
    ap.add_argument("--min-bridge-records", type=int, default=1000)
    ap.add_argument("--min-field-count", type=int, default=3)
    ap.add_argument("--max-answer-permission-count", type=int, default=0)
    ap.add_argument("--max-source-truth-mutation-allowed", type=int, default=0)
    ap.add_argument("--require-no-answer-permission", action="store_true")
    ap.add_argument("--write-json", action="store_true")
    args = ap.parse_args()
    data = json.loads(args.report_path.read_text(encoding="utf-8"))
    status, lines = quality_check(data, args)
    print("TRACE-Net E2E Dynamic Query Endpoint v1 Quality")
    print(" quality_status:", status)
    for line in lines:
        print("", line)
    if args.write_json:
        out = args.report_path.with_name(args.report_path.stem + "_quality.json")
        out.write_text(json.dumps({"quality_status": status, "checks": lines}, indent=2) + "\n", encoding="utf-8")
    return 0 if status == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
