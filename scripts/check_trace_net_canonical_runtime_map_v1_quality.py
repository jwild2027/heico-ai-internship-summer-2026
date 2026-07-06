#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tiff.trace_net_canonical_runtime_map_v1 import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_JSON_NAME,
    DEFAULT_QUALITY_NAME,
    check_runtime_map,
)

def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net canonical runtime map v1 quality.")
    parser.add_argument(
        "--input",
        default=str(Path(DEFAULT_OUTPUT_DIR) / DEFAULT_JSON_NAME),
        help="Canonical runtime map JSON.",
    )
    parser.add_argument(
        "--output",
        default=str(Path(DEFAULT_OUTPUT_DIR) / DEFAULT_QUALITY_NAME),
        help="Output quality JSON.",
    )
    parser.add_argument("--min-active-support", type=int, default=5)
    parser.add_argument("--require-primary-openwebui-path", action="store_true")
    parser.add_argument("--require-no-cleanup-allowed", action="store_true")
    args = parser.parse_args()

    quality = check_runtime_map(
        manifest_path=args.input,
        output_path=args.output,
        min_active_support=args.min_active_support,
        require_primary_openwebui_path=args.require_primary_openwebui_path,
        require_no_cleanup_allowed=args.require_no_cleanup_allowed,
    )
    print(f"Wrote: {args.output}")
    print(f"quality_status: {quality['quality_status']}")
    print(f"failure_reasons: {quality['failure_reasons']}")
    print(f"summary: {json.dumps(quality['summary'], sort_keys=True)}")
    return 0 if quality["quality_status"] == "PASS" else 2

if __name__ == "__main__":
    raise SystemExit(main())
