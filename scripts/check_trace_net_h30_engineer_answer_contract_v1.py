#!/usr/bin/env python3
"""Deterministic quality check for TRACE-Net H30 Engineer Answer Contract v1."""
from __future__ import annotations

import json

from scripts.trace_net_h30_engineer_answer_contract_v1 import (
    MODULE,
    PATCH_ID,
    apply_engineer_answer_contract,
    engineer_answer_contract_health,
)


def main() -> int:
    sample = {
        "route": "exact_identifier_lookup",
        "selected_tunnel": "exact_identifier_lookup",
        "content": (
            "TRACE-Net found confirmed visual guidance for part AB12C-120-41824-003.\n"
            "||||~~~~^^^^\n"
            "Provide another identifying clue.\n"
            "Provide another identifying clue."
        ),
        "query_atoms": {"authority_requested": False},
        "route_plan": {"authority_required": False},
        "evidence_envelope": {
            "direct_evidence": [],
            "candidate_evidence": [],
            "semantic_guidance": [],
            "visual_guidance": [{
                "page_id": "t_p_120_1176_p000084",
                "part_numbers": ["AB12C-120-41824-003"],
            }],
            "authority_evidence": [],
            "contradictions": [],
            "uncertainties": [],
            "coverage": {},
        },
        "answer_permission": True,
        "final_answer_allowed": True,
        "can_answer_directly": True,
        "can_prove_claims": True,
        "source_truth_mutation_allowed": True,
    }
    output = apply_engineer_answer_contract(sample)
    text = str(output.get("content") or "")
    failures = []
    for heading in ("## Answer", "## Evidence", "## Engineering confidence", "## Limits"):
        if heading not in text:
            failures.append(f"missing_heading:{heading}")
    if "confirmed visual guidance" in text.lower():
        failures.append("misleading_confirmed_visual_guidance")
    if "AB12C-120-41824-003" not in text:
        failures.append("strict_prefix_not_preserved")
    if "||||~~~~^^^^" in text:
        failures.append("ocr_noise_not_rejected")
    if text.count("Provide another identifying clue.") != 1:
        failures.append("follow_up_not_deduplicated")
    if output.get("route") != "exact_identifier_lookup":
        failures.append("route_changed")
    if output.get("selected_tunnel") != "exact_identifier_lookup":
        failures.append("tunnel_changed")
    for flag in (
        "answer_permission",
        "final_answer_allowed",
        "can_answer_directly",
        "can_prove_claims",
        "source_truth_mutation_allowed",
    ):
        if output.get(flag) is not False:
            failures.append(f"{flag}_not_false")
    metadata = output.get("engineer_answer_contract")
    if not isinstance(metadata, dict) or metadata.get("evidence_mode") != "guidance_only":
        failures.append("guidance_mode_not_preserved")

    result = {
        "module": MODULE,
        "patch_id": PATCH_ID,
        "quality_status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
        "health": engineer_answer_contract_health(),
        "sample_evidence_mode": metadata.get("evidence_mode") if isinstance(metadata, dict) else None,
        "read_only": True,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
        "source_truth_mutation_allowed": False,
        "answer_permission": False,
    }
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
