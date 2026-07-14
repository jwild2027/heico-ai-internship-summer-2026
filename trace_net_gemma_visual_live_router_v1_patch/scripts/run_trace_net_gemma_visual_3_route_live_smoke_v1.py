#!/usr/bin/env python3
"""TRACE-Net Gemma visual 3-route live smoke v1.

Validates the live router after the Gemma visual route is installed.

Checks:
1. visual diagram query -> gemma_confirmed_image_visual
2. visual part diagram query -> gemma_confirmed_image_visual, exact page near top
3. normal exact part query -> not visual
4. partial part query -> guided/partial route
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


DEFAULT_QUERIES = [
    {
        "name": "visual_general",
        "query": "Show figure references for passenger seat assembly diagram",
        "expected_visual": True,
        "min_citations": 1,
    },
    {
        "name": "visual_exact_part_diagram",
        "query": "Find diagram for part number 120-41824-003",
        "expected_visual": True,
        "min_citations": 1,
        "expected_page_id": "t_p_120_1176_p000084",
    },
    {
        "name": "normal_exact_part",
        "query": "Find part number 120-41824-003",
        "expected_visual": False,
    },
    {
        "name": "guided_partial_part",
        "query": "I only know the part starts with 24",
        "expected_visual": False,
        "expected_partial": True,
    },
]


def post_json(url: str, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def validate_record(spec: Dict[str, Any], response: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    route = str(response.get("route") or "")
    visual_used = bool(response.get("visual_route_used")) or route == "gemma_confirmed_image_visual"
    citation_count = int(response.get("citation_count") or 0)

    if bool(spec.get("expected_visual")):
        if route != "gemma_confirmed_image_visual":
            failures.append(f"expected_visual_route_got:{route}")
        if not visual_used:
            failures.append("visual_route_used_false")
        if citation_count < int(spec.get("min_citations", 1)):
            failures.append(f"citation_count_below_min:{citation_count}")
    else:
        if route == "gemma_confirmed_image_visual" or visual_used:
            failures.append("unexpected_visual_route")

    expected_page = spec.get("expected_page_id")
    if expected_page:
        pages = [c.get("page_id") for c in response.get("citations", [])]
        if expected_page not in pages[:3]:
            failures.append(f"expected_page_not_top3:{expected_page}")

    if spec.get("expected_partial"):
        if not response.get("partial_part_lookup"):
            failures.append("partial_part_lookup_false")
        if response.get("visual_route_used"):
            failures.append("partial_part_used_visual_route")

    for key in ("answer_permission", "final_answer_allowed", "source_truth_mutation_allowed"):
        if response.get(key):
            failures.append(f"safety_true:{key}")

    return {
        "name": spec["name"],
        "query": spec["query"],
        "route": route,
        "visual_route_used": visual_used,
        "citation_count": citation_count,
        "quality_status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "response": response,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--endpoint-url", default="http://127.0.0.1:8017/api/trace-net/ask")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--timeout-seconds", type=float, default=180.0)
    p.add_argument("--sleep-seconds", type=float, default=0.2)
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    records: List[Dict[str, Any]] = []
    for spec in DEFAULT_QUERIES:
        print(f"[{spec['name']}] {spec['query']}")
        response = post_json(args.endpoint_url, {"query": spec["query"]}, timeout=args.timeout_seconds)
        record = validate_record(spec, response)
        print(f"  route={record['route']} visual={record['visual_route_used']} citations={record['citation_count']} status={record['quality_status']}")
        if record["failures"]:
            print("  failures=" + json.dumps(record["failures"]))
        records.append(record)
        time.sleep(args.sleep_seconds)

    fail_count = sum(1 for r in records if r["quality_status"] != "PASS")
    visual_pass_count = sum(1 for r in records if r["quality_status"] == "PASS" and r["route"] == "gemma_confirmed_image_visual")
    normal_nonvisual_pass_count = sum(1 for r in records if r["quality_status"] == "PASS" and r["name"] == "normal_exact_part")
    guided_pass_count = sum(1 for r in records if r["quality_status"] == "PASS" and r["name"] == "guided_partial_part")

    summary = {
        "status": "TRACE_NET_GEMMA_VISUAL_3_ROUTE_LIVE_SMOKE_V1_DONE",
        "quality_status": "PASS" if fail_count == 0 else "FAIL",
        "endpoint_url": args.endpoint_url,
        "record_count": len(records),
        "fail_count": fail_count,
        "visual_pass_count": visual_pass_count,
        "normal_nonvisual_pass_count": normal_nonvisual_pass_count,
        "guided_pass_count": guided_pass_count,
        "answer_permission_count": sum(1 for r in records if r["response"].get("answer_permission")),
        "final_answer_allowed_true_count": sum(1 for r in records if r["response"].get("final_answer_allowed")),
        "source_truth_mutation_allowed_count": sum(1 for r in records if r["response"].get("source_truth_mutation_allowed")),
    }

    (out_dir / "trace_net_gemma_visual_3_route_live_smoke_v1.jsonl").write_text(
        "\n".join(json.dumps(r, sort_keys=True, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for k, v in summary.items():
        print(f"{k}={v}")
    return 0 if summary["quality_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
