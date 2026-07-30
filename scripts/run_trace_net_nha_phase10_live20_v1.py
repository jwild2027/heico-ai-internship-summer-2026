#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from scripts.trace_net_nha_phase9_12_release_v1 import (
    build_live20_bank, evaluate_live_case, post_chat, validate_live20, write_live20_artifacts,
)

def main() -> int:
    parser = argparse.ArgumentParser(description="Run the TRACE-Net real NHA live 20-question endpoint gate.")
    parser.add_argument("--phase4-dir", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8132")
    parser.add_argument("--api-key", default="trace-net-openwebui-cognitive")
    parser.add_argument("--model", default="trace-net-gemma4-cognitive-rag-nha-v1")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--expected-count", type=int, default=20)
    parser.add_argument("--max-depth", type=int, default=8)
    parser.add_argument("--request-timeout", type=float, default=240.0)
    parser.add_argument("--latency-hard-limit", type=float, default=180.0)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    bank = build_live20_bank(args.phase4_dir, total=args.expected_count, max_depth=args.max_depth)
    results = []
    for case in bank:
        response = post_chat(
            args.base_url,
            api_key=args.api_key,
            model=args.model,
            query=str(case.get("query") or ""),
            stream=bool(case.get("stream")),
            timeout=args.request_timeout,
        )
        results.append(evaluate_live_case(case, response, latency_hard_limit=args.latency_hard_limit))
    quality = validate_live20(results, expected_count=args.expected_count)
    summary = write_live20_artifacts(args.output_dir, bank, results, quality)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"quality_status={summary['quality_status']}")
    if args.strict and summary["quality_status"] != "PASS":
        raise SystemExit("TRACE_NET_NHA_PHASE10_LIVE20=FAIL")
    print("TRACE_NET_NHA_PHASE10_LIVE20=PASS" if summary["quality_status"] == "PASS" else "TRACE_NET_NHA_PHASE10_LIVE20=WARN")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
