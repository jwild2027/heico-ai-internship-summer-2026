#!/usr/bin/env python3
"""Run the Phase 3 live planner-guidance gate against port 8118."""
from __future__ import annotations

import argparse
import json
import urllib.request


CASES = [
    (
        "prefix_123",
        "I only know the part starts with 123",
        True,
        "partial_identifier_discovery",
    ),
    (
        "contains_41824",
        "The P/N contains 41824",
        True,
        "partial_identifier_discovery",
    ),
    (
        "prefix_120_4",
        "The part number begins with 120-4",
        True,
        "partial_identifier_discovery",
    ),
    (
        "exact",
        "Find part 120-41824-003",
        False,
        "",
    ),
    (
        "ata",
        "Find a hinge in ATA 25-21-00",
        False,
        "",
    ),
]


def post_json(url, payload, api_key, timeout):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(
        request,
        timeout=timeout,
    ) as response:
        return json.load(response)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8118",
    )
    parser.add_argument(
        "--api-key",
        default="trace-net-cognitive-local",
    )
    parser.add_argument("--timeout", type=float, default=1200.0)
    args = parser.parse_args(argv)

    records = []
    failures = []
    partial_applied = 0
    nonpartial_applied = 0
    accepted_alignment_failures = 0

    for label, query, expected, skill in CASES:
        data = post_json(
            args.base_url.rstrip("/")
            + "/api/trace-net/planner-decision",
            {"query": query},
            args.api_key,
            args.timeout,
        )
        shadow = data.get("shadow_planner") or {}
        seed = shadow.get("seed") or {}
        guidance = (
            seed.get("engram_skill_planner_guidance") or {}
        )
        decision = data.get("planner_execution") or {}
        alignment = (
            decision.get(
                "engram_skill_planner_guidance_validation"
            )
            or {}
        )
        applied = bool(guidance.get("applied"))
        partial_applied += int(expected and applied)
        nonpartial_applied += int((not expected) and applied)

        passed = applied == expected
        if skill:
            passed = (
                passed
                and guidance.get("skill_id") == skill
            )
        generic_accepted = bool(
            (decision.get("planner_validation") or {}).get(
                "accepted"
            )
        )
        if (
            generic_accepted
            and alignment.get("applied")
            and alignment.get("quality_status") != "PASS"
        ):
            accepted_alignment_failures += 1
            passed = False
        if not passed:
            failures.append(label)

        records.append({
            "label": label,
            "query": query,
            "expected_guidance": expected,
            "guidance_applied": applied,
            "guidance_reason": guidance.get("reason"),
            "skill_id": guidance.get("skill_id"),
            "required_identifier_mode": guidance.get(
                "required_identifier_mode"
            ),
            "required_identifier": guidance.get(
                "required_identifier"
            ),
            "planner_call_status": shadow.get("call_status"),
            "planner_validation_accepted": generic_accepted,
            "skill_alignment_status": alignment.get(
                "quality_status"
            ),
            "planner_plan_adopted": decision.get(
                "planner_plan_adopted"
            ),
            "deterministic_fallback_used": decision.get(
                "deterministic_fallback_used"
            ),
            "passed": passed,
        })

    quality = (
        "PASS"
        if not failures
        and partial_applied == 3
        and nonpartial_applied == 0
        and accepted_alignment_failures == 0
        else "FAIL"
    )
    output = {
        "status": "TRACE_NET_PHASE3_PARTIAL_IDENTIFIER_PLANNER_GUIDANCE_SMOKE",
        "quality_status": quality,
        "record_count": len(records),
        "partial_guidance_applied_count": partial_applied,
        "nonpartial_guidance_applied_count": nonpartial_applied,
        "accepted_skill_alignment_failure_count": (
            accepted_alignment_failures
        ),
        "failure_count": len(failures),
        "failures": failures,
        "records": records,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "write_attempt_count": 0,
    }
    print(json.dumps(output, indent=2))
    return 0 if quality == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
