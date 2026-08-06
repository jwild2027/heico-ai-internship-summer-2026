from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

from src.trace_net.retrieval.trace_net_h30_part_intent_source_resolution_v1 import (
    apply_intent_to_atoms,
    build_claim_evidence,
    build_source_resolution,
    candidate_matches_intent,
    derive_part_intent,
    identifier_is_well_formed,
    install_part_intent_source_resolution,
    part_intent_source_resolution_health,
)


def test_exact_identifier_mode_preserves_full_part_number():
    intent = derive_part_intent("Find part 120-41824-003")
    assert intent["identifier_mode"] == "exact"
    assert intent["requested_identifier"] == "120-41824-003"
    assert intent["normalized_identifier"] == "12041824003"
    assert intent["strict_exact_equality"] is True


def test_explicit_contains_overrides_exact_looking_identifier():
    intent = derive_part_intent("The P/N contains 120-41824-003")
    assert intent["identifier_mode"] == "contains"
    assert intent["allow_partial_candidates"] is True
    assert intent["strict_exact_equality"] is False


def test_prefix_mode_preserves_alphanumeric_prefix():
    intent = derive_part_intent("The P/N starts with MS49")
    assert intent["identifier_mode"] == "prefix"
    assert intent["requested_identifier"] == "MS49"
    assert candidate_matches_intent("MS4956", intent) is True
    assert candidate_matches_intent("120-MS49-001", intent) is False


def test_suffix_mode_is_distinct():
    intent = derive_part_intent("The part number ends with 003")
    assert intent["identifier_mode"] == "suffix"
    assert candidate_matches_intent("120-41824-003", intent) is True
    assert candidate_matches_intent("003-41824-120", intent) is False


def test_family_expansion_requires_explicit_family_wording():
    intent = derive_part_intent("Find the 120-41824 family")
    assert intent["identifier_mode"] == "family"
    assert intent["allow_family_expansion"] is True
    assert candidate_matches_intent("120-41824-003", intent) is True
    assert candidate_matches_intent("120-99999-003", intent) is False


def test_alphanumeric_exact_part_is_preserved():
    intent = derive_part_intent("Find part MS4956")
    assert intent["identifier_mode"] == "exact"
    assert intent["requested_identifier"] == "MS4956"
    assert candidate_matches_intent("MS4956", intent) is True


def test_generic_partial_wording_demotes_exact_to_partial():
    intent = derive_part_intent("I only remember a partial part 120-41824-003")
    assert intent["identifier_mode"] == "partial"
    assert intent["explicit_partial_wording"] is True




def test_ata_prefix_is_not_reclassified_as_part_prefix():
    atoms = SimpleNamespace(
        ata_prefix="25",
        ata_exact=[],
        exact_part_numbers=[],
        part_prefix=None,
        part_contains=None,
        part_suffix=None,
    )
    intent = derive_part_intent(
        "I have a part I want to find, ATA number starts with 25",
        atoms,
    )
    apply_intent_to_atoms(atoms, intent)
    assert intent["identifier_mode"] == "none"
    assert intent["ata_fragment_suppressed"] is True
    assert atoms.part_prefix is None
    assert atoms.ata_prefix == "25"


def test_full_ata_code_is_not_treated_as_exact_part_identifier():
    atoms = SimpleNamespace(
        ata_prefix="25",
        ata_exact=["25-21-00"],
        exact_part_numbers=[],
        part_prefix=None,
        part_contains=None,
        part_suffix=None,
    )
    intent = derive_part_intent("Find ATA 25-21-00", atoms)
    assert intent["identifier_mode"] == "none"
    assert intent["requested_identifier"] is None
    assert intent["ata_fragment_suppressed"] is True


def test_standalone_ata_prefix_phrase_has_no_part_intent():
    intent = derive_part_intent("ATA number starts with 25")
    assert intent["identifier_mode"] == "none"
    assert intent["requested_identifier"] is None


def test_mixed_ata_and_part_prefix_preserves_real_part_clue():
    atoms = SimpleNamespace(
        ata_prefix="25",
        ata_exact=[],
        exact_part_numbers=[],
        part_prefix="MS49",
        part_contains=None,
        part_suffix=None,
    )
    intent = derive_part_intent("In ATA 25, the P/N starts with MS49", atoms)
    assert intent["identifier_mode"] == "prefix"
    assert intent["requested_identifier"] == "MS49"
    assert intent["ata_fragment_suppressed"] is False


def test_exact_mode_rejects_family_member_fallback():
    intent = derive_part_intent("Find part 120-41824-003")
    assert candidate_matches_intent("120-41824-003", intent) is True
    assert candidate_matches_intent("120-41824-007", intent) is False
    assert candidate_matches_intent("120-41824", intent) is False


def test_contains_mode_rejects_unrelated_candidates():
    intent = derive_part_intent("The P/N contains 41824")
    assert candidate_matches_intent("120-41824-003", intent) is True
    assert candidate_matches_intent("120-99999-001", intent) is False


def test_obvious_ocr_noise_is_rejected():
    for value in ("||--__", "IIII", "00OO11", "120-41824-003?", "120 41824 003"):
        assert identifier_is_well_formed(value) is False


def test_compound_part_candidate_is_not_silently_split_or_corrected():
    assert identifier_is_well_formed("120-41824-003/007") is False
    assert identifier_is_well_formed("120-41824-003") is True


def test_apply_intent_rebinds_atoms_without_leaving_exact_mode():
    atoms = SimpleNamespace(
        exact_part_numbers=["120-41824-003"],
        part_prefix=None,
        part_contains=None,
        part_suffix=None,
    )
    intent = derive_part_intent("The P/N contains 120-41824-003")
    apply_intent_to_atoms(atoms, intent)
    assert atoms.exact_part_numbers == []
    assert atoms.part_contains == "120-41824-003"
    assert atoms.identifier_mode == "contains"


def test_claim_specific_evidence_buckets_do_not_merge_claim_types():
    buckets = build_claim_evidence([
        {"page_id": "p1", "field_name": "part_number", "value": "120-41824-003"},
        {"page_id": "p1", "field_name": "nomenclature", "value": "RING, LOCKING"},
        {"page_id": "p2", "field_name": "effectivity", "value": "AIRCRAFT SET"},
        {"page_id": "p3", "field_name": "warning_text", "value": "CAUTION"},
    ])
    assert set(buckets) == {"part_identity", "nomenclature", "authority", "warning_or_caution"}
    assert len(buckets["part_identity"]) == 1


def test_source_resolution_marks_matching_direct_source_as_resolved():
    envelope = SimpleNamespace(
        direct_evidence=[{
            "page_id": "t_p_120_1176_p000202",
            "field_name": "part_number",
            "normalized_value": "120-41824-003",
        }],
        candidate_evidence=[{
            "candidate_value": "120-41824-003",
            "page_id": "t_p_120_1176_p000202",
        }],
        visual_guidance=[],
        semantic_guidance=[],
    )
    atoms = SimpleNamespace(
        normalized_identifier="12041824003",
        family_identifier=None,
    )
    records = build_source_resolution(envelope, atoms)
    assert records
    assert all(row["resolution_status"] == "resolved" for row in records)
    assert any("part_identity" in row["resolved_claim_types"] for row in records)


def test_source_resolution_leaves_unmatched_visual_guidance_unresolved():
    envelope = SimpleNamespace(
        direct_evidence=[],
        candidate_evidence=[],
        visual_guidance=[{
            "page_id": "t_p_120_1176_p000084",
            "part_numbers": ["120-41824-003"],
        }],
        semantic_guidance=[],
    )
    atoms = SimpleNamespace(normalized_identifier="12041824003", family_identifier=None)
    records = build_source_resolution(envelope, atoms)
    assert records
    assert all(row["resolution_status"] == "unresolved" for row in records)
    assert all(row["guidance_only"] is True for row in records)


def test_health_preserves_all_safety_flags_false():
    health = part_intent_source_resolution_health()
    for key in (
        "answer_permission", "final_answer_allowed", "can_answer_directly",
        "can_prove_claims", "source_truth_mutation_allowed", "postgres_write_attempt",
        "qdrant_write_attempt", "opensearch_write_attempt",
    ):
        assert health[key] is False
    assert health["candidate_discovery_is_guidance_only"] is True


@dataclass
class FakeEnvelope:
    route: str
    query_atoms: dict
    retrieval_tunnels_used: list = field(default_factory=list)
    direct_evidence: list = field(default_factory=list)
    candidate_evidence: list = field(default_factory=list)
    semantic_guidance: list = field(default_factory=list)
    visual_guidance: list = field(default_factory=list)
    authority_evidence: list = field(default_factory=list)
    contradictions: list = field(default_factory=list)
    uncertainties: list = field(default_factory=list)
    coverage: dict = field(default_factory=dict)
    upstream_results: list = field(default_factory=list)
    crag_repairs: list = field(default_factory=list)
    source_resolution: list = field(default_factory=list)
    claim_evidence: dict = field(default_factory=dict)
    safety_contract: dict = field(default_factory=lambda: {
        "answer_permission": False,
        "final_answer_allowed": False,
        "source_truth_mutation_allowed": False,
    })


class FakeRuntime:
    def gather_initial(self, plan, atoms):
        return FakeEnvelope(
            route=plan.primary_route,
            query_atoms={},
            candidate_evidence=[
                {"candidate_value": "120-41824-003", "page_id": "p1", "guidance_only": True},
                {"candidate_value": "120-41824-007", "page_id": "p2", "guidance_only": True},
            ],
            visual_guidance=[{"page_id": "p1", "part_numbers": ["120-41824-003"]}],
            coverage={},
        )

    def add_unified(self, envelope, query, label):
        envelope.retrieval_tunnels_used.append(label)
        envelope.upstream_results.append({"tunnel": label, "query": query})
        if "120-41824-003" in query:
            envelope.direct_evidence.append({
                "page_id": "p1",
                "field_name": "part_number",
                "normalized_value": "120-41824-003",
            })
        return {}

    def critic(self, plan, atoms, envelope):
        return {
            "quality_status": "PASS",
            "failures": [],
            "warnings": [],
            "retry_required": False,
            "dimensions": {},
        }

    def health(self):
        return {"quality_status": "PASS"}


def _fake_atoms(query):
    return SimpleNamespace(
        latest_query=query,
        normalized_query=query.lower(),
        exact_part_numbers=["120-41824-003"],
        part_prefix=None,
        part_contains=None,
        part_suffix=None,
        requested_claims=["exact_identifier"],
        identifier_mode="none",
        normalized_identifier="",
        family_identifier=None,
        allow_family_expansion=False,
        allow_partial_candidates=False,
        explicit_partial_wording=False,
    )


def _fake_plan(atoms):
    return SimpleNamespace(
        primary_route="exact_identifier_lookup",
        secondary_routes=[],
        retrieval_tunnels=["normal_source_truth"],
        rationale=[],
    )


def _unique_dicts(rows, keys):
    output = []
    seen = set()
    for row in rows:
        key = tuple(str(row.get(name, "")) for name in keys)
        if key not in seen:
            seen.add(key)
            output.append(dict(row))
    return output


def _original_extract_candidates(result, atoms, allow_broad=False):
    return [dict(row) for row in result.get("candidate_routes", [])]


def _module_fixture():
    return {
        "extract_query_atoms": _fake_atoms,
        "plan_route": _fake_plan,
        "candidate_matches_atoms": lambda value, atoms: True,
        "extract_candidates": _original_extract_candidates,
        "CognitiveRuntime": FakeRuntime,
        "unique_dicts": _unique_dicts,
        "apply_exact_entity_gate": lambda envelope, atoms: None,
    }


def test_overlay_routes_exact_and_partial_intents_differently():
    module = _module_fixture()
    install_part_intent_source_resolution(module)

    exact_atoms = module["extract_query_atoms"]("Find part 120-41824-003")
    exact_plan = module["plan_route"](exact_atoms)
    partial_atoms = module["extract_query_atoms"]("The P/N contains 120-41824-003")
    partial_plan = module["plan_route"](partial_atoms)

    assert exact_plan.primary_route == "exact_identifier_lookup"
    assert partial_plan.primary_route == "guided_part_discovery"
    assert exact_atoms.exact_part_numbers == ["120-41824-003"]
    assert partial_atoms.exact_part_numbers == []


def test_overlay_filters_unrelated_exact_candidates_even_when_broad_is_requested():
    module = _module_fixture()
    install_part_intent_source_resolution(module)
    atoms = module["extract_query_atoms"]("Find part 120-41824-003")
    rows = module["extract_candidates"](
        {"candidate_routes": [
            {"candidate_part_number": "120-41824-003", "page_id": "p1"},
            {"candidate_part_number": "120-41824-007", "page_id": "p2"},
            {"candidate_part_number": "||--__", "page_id": "p3"},
        ]},
        atoms,
        allow_broad=True,
    )
    assert [row["candidate_value"] for row in rows] == ["120-41824-003"]
    assert rows[0]["final_answer_allowed"] is False


def test_overlay_performs_bounded_source_resolution_and_keeps_safety_false():
    module = _module_fixture()
    install_part_intent_source_resolution(module)
    runtime = FakeRuntime()
    atoms = module["extract_query_atoms"]("Find part 120-41824-003")
    plan = module["plan_route"](atoms)
    envelope = runtime.gather_initial(plan, atoms)

    assert [row["candidate_value"] for row in envelope.candidate_evidence] == ["120-41824-003"]
    assert envelope.direct_evidence[0]["normalized_value"] == "120-41824-003"
    assert envelope.coverage["phase4_3_bounded_resolution_call_count"] == 1
    assert envelope.coverage["source_resolution_resolved_count"] >= 1
    assert "part_identity" in envelope.claim_evidence
    assert envelope.safety_contract["answer_permission"] is False
    assert envelope.safety_contract["final_answer_allowed"] is False
    assert envelope.safety_contract["source_truth_mutation_allowed"] is False


def test_overlay_health_is_inspectable_and_idempotent():
    module = _module_fixture()
    install_part_intent_source_resolution(module)
    first_extract = module["extract_query_atoms"]
    install_part_intent_source_resolution(module)
    assert module["extract_query_atoms"] is first_extract
    health = FakeRuntime().health()
    assert health["quality_status"] == "PASS"
    assert health["part_intent_source_resolution_v1"] is True
    assert health["answer_permission"] is False


def _response_for_semantic_test(*, query_atoms, candidates=None, direct=None, citations=None, content="## Answer\n\nGuidance only.\n\n## Evidence\n\nNo proof.\n\n## Engineering confidence\n\nGuidance only.\n\n## Limits\n\n- Source proof required."):
    candidates = candidates or []
    direct = direct or []
    citations = citations or []
    trace = {
        "route": "exact_identifier_lookup",
        "query_atoms": query_atoms,
        "evidence_envelope": {
            "candidate_evidence": candidates,
            "direct_evidence": direct,
            "source_resolution": [{
                "lead_type": "requested_identifier",
                "resolution_status": "resolved" if direct else "unresolved",
                "source_truth_mutation_allowed": False,
            }],
            "claim_evidence": {"part_identity": direct} if direct else {},
        },
        "citations": citations,
        "citation_count": len(citations),
        "answer_permission": False,
        "final_answer_allowed": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }
    return {
        "choices": [{"message": {"content": content}}],
        "trace_net": trace,
    }


def test_semantic_benchmark_accepts_fail_closed_exact_guidance():
    from scripts.benchmark.run_trace_net_h30_phase4_3_semantic_benchmark_v1 import evaluate_semantic_response

    response = _response_for_semantic_test(
        query_atoms={"identifier_mode": "exact"},
        candidates=[{
            "candidate_value": "120-41824-003",
            "guidance_only": True,
            "final_answer_allowed": False,
        }],
    )
    result = evaluate_semantic_response(
        query="Find part 120-41824-003",
        status_code=200,
        response=response,
    )
    assert result["quality_status"] == "PASS"


def test_semantic_benchmark_rejects_unrelated_exact_candidate():
    from scripts.benchmark.run_trace_net_h30_phase4_3_semantic_benchmark_v1 import evaluate_semantic_response

    response = _response_for_semantic_test(
        query_atoms={"identifier_mode": "exact"},
        candidates=[{
            "candidate_value": "120-41824-007",
            "guidance_only": True,
            "final_answer_allowed": False,
        }],
    )
    result = evaluate_semantic_response(
        query="Find part 120-41824-003",
        status_code=200,
        response=response,
    )
    assert result["quality_status"] == "FAIL"
    assert any(item.startswith("candidate_violates_exact_clue") for item in result["failures"])


def test_semantic_benchmark_rejects_ocr_noise_and_duplicate_lines():
    from scripts.benchmark.run_trace_net_h30_phase4_3_semantic_benchmark_v1 import evaluate_semantic_response

    content = "## Answer\n\nPlease provide the exact missing part-number fragment?\nPlease provide the exact missing part-number fragment?\n\n## Evidence\n\nNo proof.\n\n## Engineering confidence\n\nGuidance only.\n\n## Limits\n\n- Source proof required."
    response = _response_for_semantic_test(
        query_atoms={"identifier_mode": "contains"},
        candidates=[{
            "candidate_value": "||--__",
            "guidance_only": True,
            "final_answer_allowed": False,
        }],
        content=content,
    )
    result = evaluate_semantic_response(
        query="The P/N contains 41824",
        status_code=200,
        response=response,
    )
    assert result["quality_status"] == "FAIL"
    assert any(item.startswith("invalid_or_ocr_noise_candidate") for item in result["failures"])
    assert any(item.startswith("duplicated_answer_lines") for item in result["failures"])


def test_semantic_benchmark_requires_visible_citation_alignment():
    from scripts.benchmark.run_trace_net_h30_phase4_3_semantic_benchmark_v1 import evaluate_semantic_response

    direct = [{"page_id": "p1", "field_name": "part_number", "normalized_value": "120-41824-003"}]
    response = _response_for_semantic_test(
        query_atoms={"identifier_mode": "exact"},
        direct=direct,
        citations=direct,
        content="## Answer\n\nPart 120-41824-003 is listed.\n\n## Evidence\n\nDirect source.\n\n## Engineering confidence\n\nSource-backed.\n\n## Limits\n\n- Cited claim only.",
    )
    result = evaluate_semantic_response(
        query="Find part 120-41824-003",
        status_code=200,
        response=response,
    )
    assert result["quality_status"] == "FAIL"
    assert "citation_not_visible_in_answer" in result["failures"]
