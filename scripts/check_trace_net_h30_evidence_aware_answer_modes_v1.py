#!/usr/bin/env python3
"""Check all Phase 5 answer modes with deterministic typed evidence."""
from __future__ import annotations

import json

from scripts.trace_net_h30_evidence_aware_answer_modes_v1 import (
    MODE_AUTHORITY_MISSING,
    MODE_CANDIDATE,
    MODE_CONFIRMED_DIRECT,
    MODE_CONFLICT,
    MODE_NO_EVIDENCE,
    MODE_SEMANTIC,
    MODE_VISUAL,
    classify_answer_mode,
    render_deterministic_mode,
    validate_mode_result,
)


def record(
    bucket,
    *,
    modality="textual_source",
    support=False,
    conflict=False,
    candidate="",
    page="",
    excerpt="",
    claims=None,
):
    return {
        "source_bucket": bucket,
        "modality": modality,
        "claim_support_allowed": support,
        "guidance_only": not support,
        "conflicted": conflict,
        "claim_types": list(claims or []),
        "identity": {
            "candidate": candidate,
            "part_numbers": [candidate] if candidate else [],
            "figure_refs": ["2"] if modality == "visual" else [],
        },
        "source_trace": {
            "page_id": page,
            "ready": support,
        },
        "excerpt": excerpt,
    }


def result(route, records):
    return {
        "route": route,
        "writer_mode": "deterministic_fail_closed",
        "query_atoms": {
            "identifier_mode": "contains",
            "normalized_identifier": "41824",
        },
        "evidence_envelope": {
            "typed_evidence": records,
        },
        "follow_up_questions": [
            "What additional part-number characters do you remember?"
        ],
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }


def main():
    cases = [
        (
            MODE_CONFIRMED_DIRECT,
            result(
                "exact_identifier_lookup",
                [
                    record(
                        "direct_evidence",
                        support=True,
                        candidate="120-41824-003",
                        page="t_p_demo_p1",
                        claims=["part_identity"],
                    )
                ],
            ),
        ),
        (
            MODE_CANDIDATE,
            result(
                "guided_part_discovery",
                [
                    record(
                        "candidate_evidence",
                        candidate="120-41824-003",
                    )
                ],
            ),
        ),
        (
            MODE_VISUAL,
            result(
                "visual_figure_callout_lookup",
                [
                    record(
                        "visual_guidance",
                        modality="visual",
                        page="t_p_demo_p2",
                    )
                ],
            ),
        ),
        (
            MODE_SEMANTIC,
            result(
                "semantic_discovery",
                [
                    record(
                        "semantic_guidance",
                        modality="graph",
                        page="t_p_demo_p3",
                    )
                ],
            ),
        ),
        (
            MODE_CONFLICT,
            result(
                "contradiction_resolution",
                [
                    record(
                        "contradictions",
                        modality="conflict",
                        conflict=True,
                        excerpt="ATA/document mismatch",
                    )
                ],
            ),
        ),
        (
            MODE_AUTHORITY_MISSING,
            result(
                "authority_eligibility_verification",
                [
                    record(
                        "candidate_evidence",
                        candidate="120-41824-003",
                    )
                ],
            ),
        ),
        (
            MODE_NO_EVIDENCE,
            result("clarification_no_evidence", []),
        ),
    ]

    records = []
    failures = []
    for expected, sample in cases:
        decision = classify_answer_mode(sample)
        rendered = (
            ""
            if expected == MODE_CONFIRMED_DIRECT
            else render_deterministic_mode(sample, decision)
        )
        validation = validate_mode_result(sample, decision)
        passed = (
            decision["mode"] == expected
            and validation["quality_status"] == "PASS"
            and (
                expected == MODE_CONFIRMED_DIRECT
                or bool(rendered.strip())
            )
        )
        if expected != MODE_CONFIRMED_DIRECT:
            passed = (
                passed
                and decision["gemma_writing_allowed"] is False
                and decision["deterministic_rendering_required"] is True
            )
        if not passed:
            failures.append(expected)
        records.append({
            "expected_mode": expected,
            "actual_mode": decision["mode"],
            "gemma_writing_allowed": decision[
                "gemma_writing_allowed"
            ],
            "deterministic_rendering_required": decision[
                "deterministic_rendering_required"
            ],
            "rendered_preview": rendered[:200],
            "validation_quality": validation["quality_status"],
            "passed": passed,
        })

    output = {
        "quality_status": "PASS" if not failures else "FAIL",
        "mode_count": len(records),
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
