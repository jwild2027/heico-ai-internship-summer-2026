#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tiff.trace_net_nha_engram_v1 import build_100_question_bank, build_nha_skill_library, evaluate_question_bank, validate_nha_engram, build_nha_memory_atoms, build_engram_core_overlay, build_skill_library_overlay

def main() -> int:
    parser = argparse.ArgumentParser(description="Run the standalone NHA Engram 20-core and 100-question regression benchmark.")
    parser.add_argument("--base-engram-core", required=True)
    parser.add_argument("--base-skill-library", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    base_core = json.loads(Path(args.base_engram_core).read_text(encoding="utf-8"))
    base_library = json.loads(Path(args.base_skill_library).read_text(encoding="utf-8"))
    skill_library = build_nha_skill_library()
    questions = build_100_question_bank()
    results = evaluate_question_bank(questions, library=skill_library)
    quality = validate_nha_engram(
        skill_library=skill_library,
        overlay_library=build_skill_library_overlay(base_library),
        memory_atoms=build_nha_memory_atoms(),
        core_overlay=build_engram_core_overlay(base_core),
        benchmark_results=results,
    )
    payload = {"quality": quality, "records": results}
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(quality, indent=2, ensure_ascii=False))
    print("TRACE_NET_NHA_ENGRAM_100Q=PASS" if quality["quality_status"] == "PASS" else "TRACE_NET_NHA_ENGRAM_100Q=FAIL")
    return 1 if args.strict and quality["quality_status"] != "PASS" else 0

if __name__ == "__main__":
    raise SystemExit(main())
