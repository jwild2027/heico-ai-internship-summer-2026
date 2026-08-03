#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys, urllib.request, urllib.error
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from src.trace_net.graph.trace_net_nha_phase9_12_release_v1 import build_live20_bank

def call(base_url: str, api_key: str, query: str, timeout: float) -> dict:
    payload = {"messages": [{"role": "user", "content": query}]}
    request = urllib.request.Request(
        base_url.rstrip("/") + "/v1/nha/decision",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {
                "http_status": response.status,
                "headers": {key.casefold(): value for key, value in response.headers.items()},
                "body": json.loads(response.read().decode("utf-8")),
            }
    except urllib.error.HTTPError as exc:
        return {"http_status": exc.code, "headers": {}, "body": {"error": exc.read().decode("utf-8", errors="replace")}}

def main() -> int:
    parser = argparse.ArgumentParser(description="Run no-LLM HTTP decision smoke against the NHA shadow proxy.")
    parser.add_argument("--phase4-dir", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8132")
    parser.add_argument("--api-key", default="trace-net-openwebui-cognitive")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    bank = build_live20_bank(args.phase4_dir, total=20)
    real_query = next(str(row["query"]) for row in bank if row.get("expected_action") == "override")
    cases = [
        ("real_shadow", real_query, "shadow_candidate"),
        ("non_nha", "What can TRACE-Net do?", "passthrough"),
        ("synthetic", "What is the direct NHA of synthetic part 990-91001-001?", "synthetic_blocked"),
    ]
    results = []
    for name, query, action in cases:
        response = call(args.base_url, args.api_key, query, args.timeout)
        actual = response.get("headers", {}).get("x-trace-net-nha-action", "")
        failures = []
        if response.get("http_status") != 200:
            failures.append(f"http_status:{response.get('http_status')}")
        if actual != action:
            failures.append(f"action expected={action} actual={actual}")
        results.append({"name": name, "query": query, "expected_action": action, "actual_action": actual, "passed": not failures, "failures": failures, "response": response})
    failures = [row for row in results if not row["passed"]]
    summary = {
        "schema_version": "trace_net_nha_phase9_12_release_v1",
        "status": "TRACE_NET_NHA_PHASE11_SHADOW_HTTP_SMOKE_V1",
        "quality_status": "PASS" if not failures else "FAIL",
        "counts": {"case_count": len(results), "pass_count": len(results) - len(failures), "fail_count": len(failures), "llm_call_count": 0},
        "results": results,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if args.strict and failures:
        raise SystemExit("TRACE_NET_NHA_PHASE11_SHADOW_HTTP_SMOKE=FAIL")
    print("TRACE_NET_NHA_PHASE11_SHADOW_HTTP_SMOKE=PASS" if not failures else "TRACE_NET_NHA_PHASE11_SHADOW_HTTP_SMOKE=WARN")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
