#!/usr/bin/env python3
"""Run the Phase 4 live typed-evidence gate against the cognitive router."""
from __future__ import annotations

import argparse
import json
import urllib.request


QUERIES = [
    "Find part 120-41824-003",
    "The P/N contains 41824",
    "Find the locking ring near the seat",
]


def call(url: str, key: str, query: str, timeout: float):
    request = urllib.request.Request(
        url.rstrip("/") + "/api/trace-net/ask",
        data=json.dumps({"query": query}).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8118")
    parser.add_argument("--api-key", default="trace-net-cognitive-local")
    parser.add_argument("--timeout", type=float, default=1200.0)
    args = parser.parse_args(argv)

    records = []
    failures = []
    total_typed = 0
    total_support = 0
    total_guidance = 0

    for query in QUERIES:
        result = call(args.base_url, args.api_key, query, args.timeout)
        envelope = result.get("evidence_envelope") or {}
        typed = envelope.get("typed_evidence") or []
        coverage = envelope.get("typed_evidence_coverage") or {}
        validation = envelope.get("typed_evidence_validation") or {}
        unsafe_guidance = [
            row for row in typed
            if row.get("guidance_only")
            and row.get("claim_support_allowed")
        ]
        unsafe_conflict = [
            row for row in typed
            if row.get("conflicted")
            and row.get("claim_support_allowed")
        ]
        expected_count = sum(
            len(envelope.get(bucket) or [])
            for bucket in (
                "direct_evidence",
                "candidate_evidence",
                "visual_guidance",
                "semantic_guidance",
                "contradictions",
                "source_resolution",
            )
        )
        passed = (
            result.get("typed_evidence_enabled") is True
            and validation.get("quality_status") == "PASS"
            and len(typed) == expected_count
            and not unsafe_guidance
            and not unsafe_conflict
            and result.get("answer_permission") is False
            and result.get("source_truth_mutation_allowed") is False
        )
        if not passed:
            failures.append(query)
        total_typed += len(typed)
        total_support += int(coverage.get("claim_support_allowed_count") or 0)
        total_guidance += int(coverage.get("guidance_only_count") or 0)
        records.append(
            {
                "query": query,
                "route": result.get("route"),
                "typed_record_count": len(typed),
                "expected_record_count": expected_count,
                "claim_support_allowed_count": coverage.get(
                    "claim_support_allowed_count"
                ),
                "guidance_only_count": coverage.get(
                    "guidance_only_count"
                ),
                "conflict_count": coverage.get("conflict_count"),
                "validation_quality": validation.get("quality_status"),
                "guidance_support_violation_count": len(unsafe_guidance),
                "conflict_support_violation_count": len(unsafe_conflict),
                "passed": passed,
            }
        )

    quality = "PASS" if not failures else "FAIL"
    output = {
        "status": "TRACE_NET_PHASE4_TYPED_EVIDENCE_LIVE_SMOKE",
        "quality_status": quality,
        "record_count": len(records),
        "total_typed_evidence_record_count": total_typed,
        "total_claim_support_allowed_count": total_support,
        "total_guidance_only_count": total_guidance,
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
