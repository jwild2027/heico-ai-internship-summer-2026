#!/usr/bin/env python3
"""Final Engram rollout benchmark with durable JSONL and resume support.

The default contract mode is fast and local. Passing --base-url enables a live
endpoint benchmark. Neither mode invokes the launcher's five critical live
route tests.
"""
from __future__ import annotations

import argparse
import json
import signal
import time
import urllib.request
from pathlib import Path

from scripts.trace_net_h30_final_engram_rollout_v1 import (
    MODE_AUTHORITY_MISSING,
    MODE_CANDIDATE,
    MODE_CONFLICT,
    MODE_NO_EVIDENCE,
    MODE_VISUAL,
    apply_followup_section,
    build_information_gain_followups,
    run_final_self_rag_critic,
    select_primary_skill,
)

CASES = [
    {
        "id": "partial_contains",
        "query": "The P/N contains 41824",
        "route": "guided_part_discovery",
        "mode": MODE_CANDIDATE,
        "atoms": {
            "identifier_mode": "contains",
            "normalized_identifier": "41824",
        },
    },
    {
        "id": "partial_prefix",
        "query": "I only know the part starts with 123",
        "route": "guided_part_discovery",
        "mode": MODE_CANDIDATE,
        "atoms": {
            "identifier_mode": "prefix",
            "part_prefix": "123",
        },
    },
    {
        "id": "exact_lookup",
        "query": "Find part 120-41824-003",
        "route": "exact_identifier_lookup",
        "mode": MODE_VISUAL,
        "atoms": {
            "identifier_mode": "exact",
            "normalized_identifier": "120-41824-003",
        },
    },
    {
        "id": "nomenclature",
        "query": "Find the locking ring near the seat",
        "route": "nomenclature_function_search",
        "mode": MODE_VISUAL,
        "atoms": {"nomenclature_terms": ["locking", "ring", "seat"]},
    },
    {
        "id": "ata_description",
        "query": "I have a part and the ATA starts with 25",
        "route": "ata_system_discovery",
        "mode": MODE_NO_EVIDENCE,
        "atoms": {"ata_prefix": "25"},
    },
    {
        "id": "manufacturer_description",
        "query": "Find the ACME seat latch",
        "route": "nomenclature_function_search",
        "mode": MODE_NO_EVIDENCE,
        "atoms": {
            "manufacturer_terms": ["ACME"],
            "nomenclature_terms": ["seat", "latch"],
        },
    },
    {
        "id": "authority",
        "query": "Is part 120-41824-003 an approved replacement?",
        "route": "authority_eligibility_verification",
        "mode": MODE_AUTHORITY_MISSING,
        "atoms": {
            "identifier_mode": "exact",
            "normalized_identifier": "120-41824-003",
        },
    },
    {
        "id": "conflict",
        "query": "These sources disagree about part 120-41824-297",
        "route": "contradiction_resolution",
        "mode": MODE_CONFLICT,
        "atoms": {
            "identifier_mode": "exact",
            "normalized_identifier": "120-41824-297",
        },
    },
]


def synthetic_result(case):
    mode = case["mode"]
    content = {
        MODE_CANDIDATE: (
            "TRACE-Net found candidate matches, not a final identification."
        ),
        MODE_VISUAL: (
            "TRACE-Net found visual guidance, but no citation-ready direct "
            "source proof."
        ),
        MODE_CONFLICT: (
            "TRACE-Net found unresolved conflicting evidence, so no positive "
            "technical conclusion is allowed."
        ),
        MODE_AUTHORITY_MISSING: (
            "TRACE-Net did not find direct authority evidence."
        ),
        MODE_NO_EVIDENCE: "No technical conclusion is provided.",
    }[mode]
    return {
        "route": case["route"],
        "query_atoms": case["atoms"],
        "answer_mode": {
            "mode": mode,
            "candidate_count": 6 if mode == MODE_CANDIDATE else 0,
            "claim_support_allowed_count": 0,
        },
        "answer_mode_validation": {"quality_status": "PASS"},
        "evidence_envelope": {
            "typed_evidence": [],
            "typed_evidence_validation": {"quality_status": "PASS"},
        },
        "content": content,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }


def call_live(base_url, api_key, query, timeout):
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


def load_completed(path):
    completed = set()
    if not path.exists():
        return completed
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        if row.get("case_id"):
            completed.add(row["case_id"])
    return completed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--base-url", default="")
    parser.add_argument(
        "--api-key",
        default="trace-net-gemma-cognitive-local",
    )
    parser.add_argument("--timeout", type=float, default=1200.0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / "records.jsonl"
    summary_path = output_dir / "summary.json"
    completed = load_completed(jsonl_path) if args.resume else set()
    cases = CASES[:4] if args.quick else CASES

    interrupted = {"value": False}

    def stop(_signum, _frame):
        interrupted["value"] = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    records = []
    failures = []
    for case in cases:
        if interrupted["value"]:
            break
        if case["id"] in completed:
            continue
        started = time.monotonic()
        if args.base_url:
            result = call_live(
                args.base_url,
                args.api_key,
                case["query"],
                args.timeout,
            )
            rollout = result.get("final_engram_rollout") or {}
            critic = result.get("final_engram_critic") or {}
            followups = result.get("information_gain_followups") or {}
            skill_id = rollout.get("selected_skill_id")
            passed = (
                rollout.get("quality_status") == "PASS"
                and critic.get("quality_status") == "PASS"
                and int(followups.get("selected_count") or 0) <= 3
                and result.get("answer_permission") is False
                and result.get("source_truth_mutation_allowed") is False
            )
            actual_mode = (result.get("answer_mode") or {}).get("mode")
        else:
            result = synthetic_result(case)
            skill = select_primary_skill(result)
            plan = build_information_gain_followups(
                result,
                maximum=3,
            )
            result["content"] = apply_followup_section(
                result["content"],
                plan["questions"],
            )
            critic = run_final_self_rag_critic(
                result,
                maximum_followups=3,
            )
            skill_id = skill["skill_id"]
            actual_mode = case["mode"]
            passed = (
                critic["quality_status"] == "PASS"
                and plan["selected_count"] <= 3
            )

        row = {
            "case_id": case["id"],
            "query": case["query"],
            "benchmark_mode": "live" if args.base_url else "contract",
            "expected_route": case["route"],
            "actual_route": result.get("route"),
            "actual_answer_mode": actual_mode,
            "selected_skill_id": skill_id,
            "passed": passed,
            "latency_ms": round(
                (time.monotonic() - started) * 1000.0,
                3,
            ),
            "answer_permission": False,
            "source_truth_mutation_allowed": False,
        }
        with jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
            handle.flush()
        records.append(row)
        if not passed:
            failures.append(case["id"])

    summary = {
        "status": (
            "INTERRUPTED" if interrupted["value"] else "COMPLETE"
        ),
        "quality_status": (
            "PASS"
            if not failures and not interrupted["value"]
            else "FAIL"
        ),
        "benchmark_mode": "live" if args.base_url else "contract",
        "case_count": len(cases),
        "executed_count": len(records),
        "failure_count": len(failures),
        "failures": failures,
        "critical_live_route_test_count": 0,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "write_attempt_count": 0,
    }
    summary_path.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["quality_status"] == "PASS" else 130 if interrupted["value"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
