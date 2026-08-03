#!/usr/bin/env python3
"""Quality gate for TRACE-Net Page Context Pack v3."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tiff.trace_net_page_context_pack_v3 import check_page_context_pack_v3_quality, load_json, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check TRACE-Net page context pack v3 quality.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--min-pages", type=int, default=1)
    parser.add_argument("--min-guidance-records", type=int, default=0)
    parser.add_argument("--min-source-trace-ready-pages", type=int, default=0)
    parser.add_argument("--min-source-locators", type=int, default=0)
    parser.add_argument("--require-no-answer-permission", action="store_true")
    parser.add_argument("--require-reasoning-work-order", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack = load_json(args.input, {})
    quality = check_page_context_pack_v3_quality(
        pack,
        min_pages=args.min_pages,
        require_no_answer_permission=args.require_no_answer_permission,
        require_reasoning_work_order=args.require_reasoning_work_order,
        min_guidance_records=args.min_guidance_records,
        min_source_trace_ready_pages=args.min_source_trace_ready_pages,
        min_source_locators=args.min_source_locators,
    )
    if args.output:
        write_json(args.output, quality)
        print(f"Wrote: {args.output}")
    print(f"quality_status: {quality.get('quality_status')}")
    print(f"failure_reasons: {quality.get('failure_reasons')}")
    print(f"summary: {quality.get('summary')}")
    return 0 if quality.get("quality_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
