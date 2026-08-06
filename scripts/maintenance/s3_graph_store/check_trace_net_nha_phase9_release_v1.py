#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from src.trace_net.graph.trace_net_nha_phase9_12_release_v1 import check_promoted_release

def main() -> int:
    parser = argparse.ArgumentParser(description="Check the promoted real NHA release bundle.")
    parser.add_argument("--release-dir", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    result = check_promoted_release(args.release_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.strict and result["quality_status"] != "PASS":
        raise SystemExit("TRACE_NET_NHA_PHASE9_RELEASE_CHECK=FAIL")
    print("TRACE_NET_NHA_PHASE9_RELEASE_CHECK=PASS" if result["quality_status"] == "PASS" else "TRACE_NET_NHA_PHASE9_RELEASE_CHECK=WARN")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
