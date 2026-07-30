#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from scripts.trace_net_nha_phase9_12_release_v1 import promote_real_release

def main() -> int:
    parser = argparse.ArgumentParser(description="Promote validated real N4 NHA artifacts into a Git-trackable release directory.")
    parser.add_argument("--phase4-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    result = promote_real_release(args.phase4_dir, args.output_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"quality_status={result['quality_status']}")
    if args.strict and result["quality_status"] != "PASS":
        raise SystemExit("TRACE_NET_NHA_PHASE9_RELEASE=FAIL")
    print("TRACE_NET_NHA_PHASE9_RELEASE=PASS" if result["quality_status"] == "PASS" else "TRACE_NET_NHA_PHASE9_RELEASE=WARN")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
