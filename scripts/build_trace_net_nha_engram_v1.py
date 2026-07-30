#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tiff.trace_net_nha_engram_v1 import build_nha_engram_artifacts

def main() -> int:
    parser = argparse.ArgumentParser(description="Build TRACE-Net NHA Engram atoms, skill overlays, and 100-question benchmark.")
    parser.add_argument("--base-engram-core", required=True)
    parser.add_argument("--base-skill-library", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    summary = build_nha_engram_artifacts(
        base_engram_core_path=args.base_engram_core,
        base_skill_library_path=args.base_skill_library,
        output_dir=args.output_dir,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"quality_status={summary['quality_status']}")
    marker = "TRACE_NET_NHA_ENGRAM=PASS" if summary["quality_status"] == "PASS" else "TRACE_NET_NHA_ENGRAM=FAIL"
    print(marker)
    return 1 if args.strict and summary["quality_status"] != "PASS" else 0

if __name__ == "__main__":
    raise SystemExit(main())
