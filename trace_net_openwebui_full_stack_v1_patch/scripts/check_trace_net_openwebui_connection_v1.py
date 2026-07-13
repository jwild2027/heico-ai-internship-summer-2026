#!/usr/bin/env python3
"""TRACE-Net OpenWebUI connection check v1.

Checks that the 8017 router front door is usable through the OpenAI-compatible
/v1/chat/completions path that OpenWebUI uses.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


DEFAULT_PROMPTS = [
    ("visual_general", "Show figure references for passenger seat assembly diagram", "gemma_confirmed_image_visual"),
    ("visual_exact_part_diagram", "Find diagram for part number 120-41824-003", "gemma_confirmed_image_visual"),
    ("normal_exact_part", "Find part number 120-41824-003", "normal_ask"),
    ("guided_partial_part", "I only know the part starts with 24", "guided_discovery"),
]


def post_json(url: str, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def extract_assistant_json(response: Dict[str, Any]) -> Dict[str, Any]:
    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message") if isinstance(choices[0], dict) else {}
        content = msg.get("content") if isinstance(msg, dict) else ""
        if isinstance(content, str):
            start, end = content.find("{"), content.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(content[start : end + 1])
                except Exception:
                    return {"raw_content": content}
    return {"raw_response": response}


def run_check(args: argparse.Namespace) -> Dict[str, Any]:
    url = args.base_url.rstrip("/") + "/chat/completions"
    records: List[Dict[str, Any]] = []

    for name, prompt, expected_route in DEFAULT_PROMPTS:
        payload = {
            "model": args.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }
        response = post_json(url, payload, timeout=args.timeout_seconds)
        routed = extract_assistant_json(response)
        route = routed.get("route") or routed.get("trace_net_route")
        ok = route == expected_route
        if expected_route == "normal_ask" and route not in {"normal_ask", "exact", "all_direct"}:
            ok = False
        record = {
            "name": name,
            "prompt": prompt,
            "expected_route": expected_route,
            "route": route,
            "quality_status": "PASS" if ok else "FAIL",
            "citation_count": routed.get("citation_count"),
            "answer_permission": routed.get("answer_permission"),
            "final_answer_allowed": routed.get("final_answer_allowed"),
            "routed_payload": routed,
        }
        print(f"{name}: route={route} expected={expected_route} status={record['quality_status']}")
        records.append(record)

    fail_count = sum(1 for r in records if r["quality_status"] != "PASS")
    summary = {
        "status": "TRACE_NET_OPENWEBUI_CONNECTION_CHECK_V1_DONE",
        "quality_status": "PASS" if fail_count == 0 else "FAIL",
        "base_url": args.base_url,
        "model": args.model,
        "record_count": len(records),
        "fail_count": fail_count,
        "records": records,
    }
    return summary


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default="http://127.0.0.1:8017/v1")
    p.add_argument("--model", default="trace-net-router-proxy-v6-gemma-visual-v1")
    p.add_argument("--timeout-seconds", type=float, default=180.0)
    p.add_argument("--output-dir", default="local_data/organization/trace_net/openwebui_connection_check_v1")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    summary = run_check(args)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    for key in ("status", "quality_status", "base_url", "model", "record_count", "fail_count"):
        print(f"{key}={summary[key]}")
    return 0 if summary["quality_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
