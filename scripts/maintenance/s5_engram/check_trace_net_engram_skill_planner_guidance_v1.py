#!/usr/bin/env python3
"""Inspect deterministic Phase 3 partial-identifier planner guidance."""
from __future__ import annotations

import argparse
import json

from src.trace_net.engram.trace_net_h30_engram_skill_planner_guidance_v1 import (
    augment_shadow_planner_seed,
    validate_skill_guided_planner_proposal,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True)
    parser.add_argument(
        "--identifier-mode",
        choices=("prefix", "contains", "suffix", "family"),
        required=True,
    )
    parser.add_argument("--identifier", required=True)
    args = parser.parse_args(argv)

    key = {
        "prefix": "part_prefix",
        "contains": "part_contains",
        "suffix": "part_suffix",
        "family": "family_identifier",
    }[args.identifier_mode]
    atoms = {
        "identifier_mode": args.identifier_mode,
        "normalized_identifier": args.identifier,
        key: args.identifier,
        "manufacturer": None,
        "ata_prefix": None,
        "nomenclature_terms": [],
    }
    seed = {
        "query": args.query,
        "deterministic_atoms": atoms,
        "deterministic_plan": {
            "primary_route": "guided_part_discovery",
            "retrieval_tunnels": [
                "guided_candidate_discovery",
                "normal_source_resolution",
                "phase4_3_candidate_source_resolution",
                "qdrant_guidance",
            ],
        },
        "retrieved_evidence_in_seed": False,
    }
    seed = augment_shadow_planner_seed(
        seed,
        environ={
            "TRACE_NET_H30_ENGRAM_SKILL_PLANNER_GUIDANCE_ENABLED": "1",
        },
    )
    proposal = {
        "identifier_mode": args.identifier_mode,
        "identifier": args.identifier,
        "entity_type": "part_number",
        "requested_claims": ["part_identity"],
        "suggested_routes": ["guided_part_discovery"],
        "suggested_tunnels": [
            "guided_candidate_discovery",
            "normal_source_resolution",
        ],
        "uncertainties": [
            "The supplied identifier is incomplete."
        ],
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }
    validation = validate_skill_guided_planner_proposal(
        proposal=proposal,
        seed=seed,
    )
    guidance = seed["engram_skill_planner_guidance"]
    output = {
        "quality_status": (
            "PASS"
            if guidance.get("applied")
            and validation.get("quality_status") == "PASS"
            else "FAIL"
        ),
        "guidance": guidance,
        "proposal_validation": validation,
        "answer_permission": False,
        "source_truth_mutation_allowed": False,
        "write_attempt_count": 0,
    }
    print(json.dumps(output, indent=2))
    return 0 if output["quality_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
