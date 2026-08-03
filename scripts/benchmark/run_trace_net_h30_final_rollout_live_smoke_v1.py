#!/usr/bin/env python3
"""Small final rollout live gate; does not run the five critical route tests."""
from __future__ import annotations

import argparse
import json
import urllib.request


CASES = [
    "The P/N contains 41824",
    "Find the locking ring near the seat",
    "Is part 120-41824-003 an approved replacement?",
]


def call(base_url, api_key, query, timeout):
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/trace-net/ask",
        data=json.dumps({"query": query}).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8128")
    parser.add_argument(
        "--api-key",
        default="trace-net-gemma-cognitive-local",
    )
    parser.add_argument("--timeout", type=float, default=1200.0)
    args = parser.parse_args(argv)

    records = []
    failures = []
    for query in CASES:
        result = call(
            args.base_url,
            args.api_key,
            query,
            args.timeout,
        )
        rollout = result.get("final_engram_rollout") or {}
        critic = result.get("final_engram_critic") or {}
        repair = result.get("bounded_crag_repair") or {}
        followups = result.get("information_gain_followups") or {}
        passed = (
            result.get("final_engram_rollout_enabled") is True
            and rollout.get("quality_status") == "PASS"
            and critic.get("quality_status") == "PASS"
            and int(repair.get("repair_count") or 0) <= 1
            and int(followups.get("selected_count") or 0) <= 3
            and result.get("answer_permission") is False
            and result.get("source_truth_mutation_allowed") is False
        )
        if not passed:
            failures.append(query)
        records.append({
            "query": query,
            "route": result.get("route"),
            "answer_mode": (result.get("answer_mode") or {}).get("mode"),
            "selected_skill_id": rollout.get("selected_skill_id"),
            "followup_topics": [
                row.get("topic")
                for row in (followups.get("records") or [])
            ],
            "critic_quality_status": critic.get("quality_status"),
            "repair_count": repair.get("repair_count"),
            "passed": passed,
        })

    output = {
        "status": "TRACE_NET_H30_FINAL_ROLLOUT_LIVE_SMOKE_V1",
        "quality_status": "PASS" if not failures else "FAIL",
        "record_count": len(records),
        "critical_live_route_test_count": 0,
        "failure_count": len(failures),
        "failures": failures,
        "records": records,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "write_attempt_count": 0,
    }
    print(json.dumps(output, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
