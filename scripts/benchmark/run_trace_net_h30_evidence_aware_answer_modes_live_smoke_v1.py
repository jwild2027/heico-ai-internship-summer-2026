#!/usr/bin/env python3
"""Run the Phase 5 live evidence-aware answer-mode gate."""
from __future__ import annotations

import argparse
import json
import urllib.request


CASES = [
    (
        "exact_visual_or_candidate",
        "Find part 120-41824-003",
        {"visual_guidance", "candidate_discovery", "confirmed_direct"},
    ),
    (
        "partial_candidate",
        "The P/N contains 41824",
        {"candidate_discovery", "conflict_limited"},
    ),
    (
        "nomenclature_guidance",
        "Find the locking ring near the seat",
        {
            "visual_guidance",
            "candidate_discovery",
            "semantic_graph_summary_guidance",
            "conflict_limited",
        },
    ),
    (
        "authority_missing",
        "Is part 120-41824-003 an approved replacement?",
        {"authority_not_found", "confirmed_direct"},
    ),
]


def call(url, key, query, timeout):
    request = urllib.request.Request(
        url.rstrip("/") + "/api/trace-net/ask",
        data=json.dumps({"query": query}).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(
        request,
        timeout=timeout,
    ) as response:
        return json.load(response)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8128",
    )
    parser.add_argument(
        "--api-key",
        default="trace-net-gemma-cognitive-local",
    )
    parser.add_argument("--timeout", type=float, default=1200.0)
    args = parser.parse_args(argv)

    records = []
    failures = []
    deterministic_non_direct_count = 0
    confirmed_count = 0

    for label, query, allowed_modes in CASES:
        result = call(
            args.base_url,
            args.api_key,
            query,
            args.timeout,
        )
        decision = result.get("answer_mode") or {}
        validation = result.get("answer_mode_validation") or {}
        mode = str(decision.get("mode") or "")
        non_direct = mode != "confirmed_direct"
        deterministic = bool(
            decision.get("deterministic_rendering_required")
        )
        if non_direct and deterministic:
            deterministic_non_direct_count += 1
        if mode == "confirmed_direct":
            confirmed_count += 1

        passed = (
            result.get(
                "evidence_aware_answer_modes_enabled"
            ) is True
            and mode in allowed_modes
            and validation.get("quality_status") == "PASS"
            and result.get("answer_permission") is False
            and result.get(
                "source_truth_mutation_allowed"
            ) is False
        )
        if non_direct:
            passed = (
                passed
                and decision.get("gemma_writing_allowed") is False
                and deterministic is True
                and str(
                    result.get("writer_mode") or ""
                ).startswith("evidence_aware_")
            )
        if not passed:
            failures.append(label)

        records.append({
            "label": label,
            "query": query,
            "route": result.get("route"),
            "answer_mode": mode,
            "writer_mode": result.get("writer_mode"),
            "gemma_status": result.get("gemma_status"),
            "gemma_writing_allowed": decision.get(
                "gemma_writing_allowed"
            ),
            "deterministic_rendering_required": deterministic,
            "claim_support_allowed_count": decision.get(
                "claim_support_allowed_count"
            ),
            "candidate_count": decision.get("candidate_count"),
            "visual_count": decision.get("visual_count"),
            "conflict_count": decision.get("conflict_count"),
            "validation_quality": validation.get(
                "quality_status"
            ),
            "content_preview": str(
                result.get("content") or ""
            )[:300],
            "passed": passed,
        })

    output = {
        "status": "TRACE_NET_PHASE5_EVIDENCE_AWARE_ANSWER_MODES_LIVE_SMOKE",
        "quality_status": "PASS" if not failures else "FAIL",
        "record_count": len(records),
        "deterministic_non_direct_count": (
            deterministic_non_direct_count
        ),
        "confirmed_direct_count": confirmed_count,
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
