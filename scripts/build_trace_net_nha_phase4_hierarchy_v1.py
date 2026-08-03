#!/usr/bin/env python3
"""Build TRACE-Net NHA phase N4 hierarchy artifacts from N0-N3 output."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.trace_net_nha_phase4_hierarchy_v1 import build_phase4


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase0-3-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--minimum-supported", type=int, default=1)
    parser.add_argument("--minimum-attaching-supported", type=int, default=1)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = build_phase4(
        phase0_3_dir=args.phase0_3_dir,
        output_dir=args.output_dir,
        minimum_supported=args.minimum_supported,
        minimum_attaching_supported=args.minimum_attaching_supported,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"quality_status={summary['quality_status']}")
    print(f"summary={Path(args.output_dir).resolve() / 'trace_net_nha_phase4_summary_v1.json'}")
    if args.strict and summary["quality_status"] != "PASS":
        raise SystemExit("TRACE_NET_NHA_PHASE4=FAIL")
    print("TRACE_NET_NHA_PHASE4=PASS" if summary["quality_status"] == "PASS" else "TRACE_NET_NHA_PHASE4=WARN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
