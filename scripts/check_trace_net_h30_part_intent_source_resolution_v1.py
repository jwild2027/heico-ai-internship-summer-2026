#!/usr/bin/env python3
"""Quality check for TRACE-Net H30 Phase 4.3 part intent/source resolution."""
from __future__ import annotations

import json
from types import SimpleNamespace

from scripts.trace_net_h30_part_intent_source_resolution_v1 import (
    apply_intent_to_atoms,
    build_claim_evidence,
    candidate_matches_intent,
    derive_part_intent,
    identifier_is_well_formed,
    part_intent_source_resolution_health,
)


def main() -> int:
    failures = []

    exact = derive_part_intent("Find part 120-41824-003")
    contains = derive_part_intent("The P/N contains 120-41824-003")
    prefix = derive_part_intent("The P/N starts with MS49")
    family = derive_part_intent("Find the 120-41824 family")
    alpha = derive_part_intent("Find part MS4956")

    checks = {
        "exact_mode": exact["identifier_mode"] == "exact",
        "contains_overrides_exact": contains["identifier_mode"] == "contains",
        "prefix_preserved": prefix["requested_identifier"] == "MS49",
        "family_expansion_explicit": family["identifier_mode"] == "family" and family["allow_family_expansion"],
        "alphanumeric_exact_preserved": alpha["identifier_mode"] == "exact" and alpha["requested_identifier"] == "MS4956",
        "exact_rejects_family_member": not candidate_matches_intent("120-41824-007", exact),
        "exact_accepts_exact": candidate_matches_intent("120-41824-003", exact),
        "contains_accepts_match": candidate_matches_intent("120-41824-003", derive_part_intent("P/N contains 41824")),
        "contains_rejects_unrelated": not candidate_matches_intent("120-99999-001", derive_part_intent("P/N contains 41824")),
        "ocr_noise_rejected": not identifier_is_well_formed("||--__"),
        "compound_candidate_rejected": not identifier_is_well_formed("120-41824-003/007"),
    }
    for name, passed in checks.items():
        if not passed:
            failures.append(name)

    atoms = SimpleNamespace(
        exact_part_numbers=["120-41824-003"],
        part_prefix=None,
        part_contains=None,
        part_suffix=None,
    )
    apply_intent_to_atoms(atoms, contains)
    if atoms.exact_part_numbers or atoms.part_contains != "120-41824-003":
        failures.append("partial_intent_atom_rebind")

    buckets = build_claim_evidence([
        {"field_name": "part_number", "normalized_value": "120-41824-003"},
        {"field_name": "nomenclature", "value": "RING, LOCKING"},
        {"field_name": "effectivity", "value": "AIRCRAFT SET"},
    ])
    if set(buckets) != {"part_identity", "nomenclature", "authority"}:
        failures.append("claim_specific_buckets")

    health = part_intent_source_resolution_health()
    for key in (
        "answer_permission", "final_answer_allowed", "can_answer_directly",
        "can_prove_claims", "source_truth_mutation_allowed", "postgres_write_attempt",
        "qdrant_write_attempt", "opensearch_write_attempt",
    ):
        if health.get(key) is not False:
            failures.append(f"unsafe_health_flag:{key}")

    result = {
        "module": health["part_intent_source_resolution_v1"] and "trace_net_h30_part_intent_source_resolution_v1",
        "patch_id": "trace_net_h30_phase4_3_part_intent_source_resolution_v1",
        "quality_status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
        "exact_intent": exact,
        "partial_override_intent": contains,
        "family_intent": family,
        "claim_bucket_names": sorted(buckets),
        "health": health,
        "read_only": True,
        "postgres_write_attempt": False,
        "qdrant_write_attempt": False,
        "opensearch_write_attempt": False,
        "source_truth_mutation_allowed": False,
        "answer_permission": False,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
