#!/usr/bin/env python3
"""Deterministic checker for final TRACE-Net roadmap Phases 6 through 10."""
from __future__ import annotations

import json

from scripts.trace_net_h30_final_engram_rollout_v1 import (
    MODE_AUTHORITY_MISSING,
    MODE_CANDIDATE,
    MODE_CONFLICT,
    MODE_NO_EVIDENCE,
    MODE_VISUAL,
    apply_followup_section,
    build_information_gain_followups,
    run_bounded_final_repair,
    run_final_self_rag_critic,
    select_primary_skill,
)


def base_result(mode, route, *, candidates=0, atoms=None):
    return {
        "route": route,
        "query_atoms": dict(atoms or {}),
        "answer_mode": {
            "mode": mode,
            "candidate_count": candidates,
            "claim_support_allowed_count": 0,
        },
        "answer_mode_validation": {"quality_status": "PASS"},
        "evidence_envelope": {
            "typed_evidence": [],
            "typed_evidence_validation": {"quality_status": "PASS"},
        },
        "content": {
            MODE_CANDIDATE: (
                "TRACE-Net found candidate matches, not a final identification."
            ),
            MODE_VISUAL: (
                "TRACE-Net found visual guidance, but no citation-ready "
                "direct source proof."
            ),
            MODE_CONFLICT: (
                "TRACE-Net found unresolved conflicting evidence, so no "
                "positive technical conclusion is allowed."
            ),
            MODE_AUTHORITY_MISSING: (
                "TRACE-Net did not find direct authority evidence for the "
                "requested approval claim."
            ),
            MODE_NO_EVIDENCE: (
                "No technical conclusion is provided."
            ),
        }.get(mode, ""),
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
    }


def main():
    cases = [
        base_result(
            MODE_CANDIDATE,
            "guided_part_discovery",
            candidates=8,
            atoms={
                "identifier_mode": "contains",
                "normalized_identifier": "41824",
            },
        ),
        base_result(
            MODE_VISUAL,
            "nomenclature_function_search",
            atoms={"nomenclature_terms": ["locking", "ring"]},
        ),
        base_result(
            MODE_NO_EVIDENCE,
            "ata_system_discovery",
            atoms={"ata_prefix": "25"},
        ),
        base_result(
            MODE_NO_EVIDENCE,
            "nomenclature_function_search",
            atoms={"manufacturer_terms": ["ACME"]},
        ),
        base_result(
            MODE_AUTHORITY_MISSING,
            "authority_eligibility_verification",
            atoms={
                "identifier_mode": "exact",
                "normalized_identifier": "120-41824-003",
            },
        ),
        base_result(
            MODE_CONFLICT,
            "guided_part_discovery",
            candidates=4,
            atoms={"identifier_mode": "prefix", "part_prefix": "123"},
        ),
    ]

    records = []
    failures = []
    for index, sample in enumerate(cases, 1):
        skill = select_primary_skill(sample)
        plan = build_information_gain_followups(sample, maximum=3)
        sample["content"] = apply_followup_section(
            sample["content"],
            plan["questions"],
        )
        critic = run_final_self_rag_critic(
            sample,
            maximum_followups=3,
        )
        passed = (
            critic["quality_status"] == "PASS"
            and plan["selected_count"] <= 3
            and plan["generic_question_count"] == 0
            and sample["answer_permission"] is False
            and sample["source_truth_mutation_allowed"] is False
        )
        if not passed:
            failures.append(f"case_{index}")
        records.append({
            "case": index,
            "mode": sample["answer_mode"]["mode"],
            "selected_skill_id": skill["skill_id"],
            "followup_topics": [
                row["topic"] for row in plan["records"]
            ],
            "critic_quality_status": critic["quality_status"],
            "passed": passed,
        })

    unsafe = base_result(
        MODE_CANDIDATE,
        "guided_part_discovery",
        candidates=3,
        atoms={
            "identifier_mode": "contains",
            "normalized_identifier": "41824",
        },
    )
    unsafe["content"] = (
        "The part number is 120-41824-003 and it is confirmed."
    )
    plan = build_information_gain_followups(unsafe, maximum=3)
    repair = run_bounded_final_repair(
        unsafe,
        followup_plan=plan,
        maximum_repairs=1,
        maximum_followups=3,
    )
    repair_passed = (
        repair["repair_count"] == 1
        and repair["final_critic"]["quality_status"] == "PASS"
    )
    if not repair_passed:
        failures.append("bounded_repair")

    output = {
        "quality_status": "PASS" if not failures else "FAIL",
        "phase_count": 5,
        "completed_phases": [6, 7, 8, 9, 10],
        "skill_case_count": len(records),
        "bounded_repair_passed": repair_passed,
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
