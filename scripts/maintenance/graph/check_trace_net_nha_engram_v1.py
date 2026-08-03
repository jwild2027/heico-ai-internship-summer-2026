#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tiff.trace_net_nha_engram_v1 import check_nha_engram_artifacts

def main() -> int:
    parser = argparse.ArgumentParser(description="Check TRACE-Net NHA Engram artifacts and rerun the 100-question deterministic gate.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    quality = check_nha_engram_artifacts(args.output_dir)
    print(json.dumps(quality, indent=2, ensure_ascii=False))
    marker = "TRACE_NET_NHA_ENGRAM_CHECK=PASS" if quality.get("quality_status") == "PASS" else "TRACE_NET_NHA_ENGRAM_CHECK=FAIL"
    print(marker)
    return 1 if args.strict and quality.get("quality_status") != "PASS" else 0

if __name__ == "__main__":
    raise SystemExit(main())
