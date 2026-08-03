"""Quality checker for TRACE-Net final return policy Hybrid v3 v2.2."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from tiff.trace_net_ask_api_final_return_policy_hybrid_v3_v22 import (
    QUALITY_SCHEMA_VERSION,
    build_quality_report,
    read_json,
    write_json,
)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net final return policy Hybrid v3 v2.2 quality.")
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--require-hybrid-v3-quality-pass", action="store_true")
    parser.add_argument("--write-json", action="store_true")
    args = parser.parse_args(argv)

    report = read_json(args.report_path)
    quality = build_quality_report(report, require_hybrid_v3_quality_pass=args.require_hybrid_v3_quality_pass)
    if args.write_json:
        write_json(args.report_path.with_name("trace_net_ask_api_final_return_policy_hybrid_v3_v22_quality.json"), quality)
    print(json.dumps(quality, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if quality.get("quality_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
