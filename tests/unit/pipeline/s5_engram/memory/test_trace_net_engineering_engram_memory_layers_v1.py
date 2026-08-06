from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_engineering_engram_memory_layers_v1 import (
    MEMORY_LAYERS,
    PERSISTED_MEMORY_LAYERS,
    build_layered_atoms,
    build_memory_layer_manifest,
    check_memory_layer_manifest,
    infer_memory_layer,
    normalize_atom,
    validate_layered_manifest,
)


def test_infer_memory_layer_examples():
    assert infer_memory_layer({
        "engram_id": "policy_no_interchangeability_without_authority_v1",
        "memory_type": "policy_trait",
    }) == "procedural_memory"
    assert infer_memory_layer({
        "engram_id": "policy_v2_summaries_guidance_not_proof_v1",
        "memory_type": "policy_trait",
    }) == "semantic_memory"
    assert infer_memory_layer({
        "engram_id": "route_visual_link_vs_ocr_nomenclature_v1",
        "memory_type": "route_behavior",
    }) == "semantic_memory"
    assert infer_memory_layer({
        "engram_id": "episode_h13_generic_not_proven_v1",
        "memory_type": "episodic_failure_memory",
    }) == "episodic_memory"
    assert infer_memory_layer({
        "engram_id": "style_engineering_answer_shape_v1",
        "memory_type": "style_trait",
    }) == "trait_memory"
    assert infer_memory_layer({
        "engram_id": "critic_answer_behavior_self_rag_v1",
        "memory_type": "critic_trait",
    }) == "critic_memory"


def test_normalize_uses_readable_core_id_and_behavior_fields():
    raw = {
        "engram_id": "policy_no_interchangeability_without_authority_v1",
        "memory_type": "policy_trait",
        "triggers": ["interchangeability"],
        "rule": "Require explicit authority.",
        "good_behavior": "State what is proven and what remains unproven.",
        "bad_behavior": "Do not infer approval from similarity.",
        "source": "unit",
        "status": "active",
    }
    atom = normalize_atom(raw, source_core_path="unit_core.json")
    assert atom["atom_id"] == "policy_no_interchangeability_without_authority_v1"
    assert atom["canonical_rule_id"] == atom["atom_id"]
    assert atom["title"] == "No interchangeability without authority"
    assert atom["memory_layer"] == "procedural_memory"
    assert atom["allowed_behavior"] == raw["good_behavior"]
    assert atom["forbidden_behavior"] == raw["bad_behavior"]
    assert atom["legacy_atom_ids"][0].startswith("h17_imported_")
    assert atom["proof_role"] == "guidance_only"


def test_build_manifest_keeps_working_memory_runtime_only(tmp_path: Path):
    core = {
        "records": [
            {
                "engram_id": "policy_no_interchangeability_without_authority_v1",
                "memory_type": "policy_trait",
                "rule": "Require explicit authority.",
                "good_behavior": "State the evidence boundary.",
                "bad_behavior": "Do not infer approval.",
            },
            {
                "engram_id": "route_visual_link_vs_ocr_nomenclature_v1",
                "memory_type": "route_behavior",
                "rule": "Visual and OCR evidence have different meanings.",
                "good_behavior": "Explain the distinction.",
                "bad_behavior": "Do not merge evidence roles.",
            },
            {
                "engram_id": "episode_h13_generic_not_proven_v1",
                "memory_type": "episodic_failure_memory",
                "rule": "Past generic-answer failure.",
                "good_behavior": "Use the repaired answer shape.",
                "bad_behavior": "Do not repeat the failure.",
            },
            {
                "engram_id": "style_engineering_answer_shape_v1",
                "memory_type": "style_trait",
                "rule": "Use a clear engineering answer shape.",
                "good_behavior": "Answer first.",
                "bad_behavior": "Do not dump records.",
            },
            {
                "engram_id": "critic_answer_behavior_self_rag_v1",
                "memory_type": "critic_trait",
                "rule": "Critique evidence and intent.",
                "good_behavior": "Run the critic.",
                "bad_behavior": "Do not skip weak-answer checks.",
            },
        ]
    }
    core_path = tmp_path / "core.json"
    core_path.write_text(json.dumps(core), encoding="utf-8")

    manifest = build_memory_layer_manifest(
        engram_core_path=core_path,
        output_dir=tmp_path / "out",
    )
    assert manifest["quality_status"] == "PASS"
    counts = manifest["summary"]["layer_counts"]
    assert set(counts) == set(MEMORY_LAYERS)
    assert counts["working_memory"] == 0
    assert all(counts[layer] > 0 for layer in PERSISTED_MEMORY_LAYERS)
    assert manifest["taxonomy"]["working_memory_storage"] == "runtime_only"
    assert manifest["summary"]["static_working_memory_atom_count"] == 0
    assert manifest["summary"]["readable_atom_id_count"] == len(
        manifest["memory_atoms"]
    )
    assert manifest["summary"]["allowed_behavior_populated_count"] == len(
        manifest["memory_atoms"]
    )
    assert manifest["summary"]["forbidden_behavior_populated_count"] == len(
        manifest["memory_atoms"]
    )


def test_validate_rejects_non_guidance_non_working_atom():
    manifest = {
        "memory_atoms": [{
            "atom_id": "bad",
            "canonical_rule_id": "bad",
            "title": "Bad",
            "memory_layer": "semantic_memory",
            "proof_role": "source_truth",
            "allowed_behavior": "Nothing",
            "forbidden_behavior": "Nothing",
        }],
        "summary": {"answer_permission_count": 0},
    }
    passed, errors, _ = validate_layered_manifest(
        manifest,
        min_atoms=1,
        require_all_layers=False,
    )
    assert not passed
    assert any(
        "non-working memory must be guidance_only" in error
        for error in errors
    )


def test_validate_rejects_persisted_static_working_memory():
    manifest = {
        "memory_atoms": [{
            "atom_id": "static_working_rule",
            "canonical_rule_id": "static_working_rule",
            "title": "Static working rule",
            "memory_layer": "working_memory",
            "proof_role": "current_proof_context_only",
            "allowed_behavior": "Use the current question.",
            "forbidden_behavior": "Do not persist source truth.",
        }],
        "summary": {"answer_permission_count": 0},
    }
    passed, errors, metrics = validate_layered_manifest(
        manifest,
        min_atoms=1,
        require_all_layers=False,
    )
    assert not passed
    assert metrics["static_working_memory_atom_count"] == 1
    assert any(
        "working_memory is runtime-only" in error
        for error in errors
    )


def test_check_memory_layer_manifest_writes_quality_check(tmp_path: Path):
    core_path = tmp_path / "core.json"
    core_path.write_text(
        json.dumps({"records": []}),
        encoding="utf-8",
    )
    manifest = build_memory_layer_manifest(
        engram_core_path=core_path,
        output_dir=tmp_path / "out",
    )
    path = (
        tmp_path
        / "out"
        / "trace_net_engineering_engram_memory_layers_v1.json"
    )
    result = check_memory_layer_manifest(
        memory_layers_path=path,
        min_atoms=6,
        require_all_layers=True,
        require_quality_pass=True,
    )
    assert manifest["quality_status"] == "PASS"
    assert result["quality_status"] == "PASS"
    assert result["summary"]["static_working_memory_atom_count"] == 0
    assert path.with_name(
        "trace_net_engineering_engram_memory_layers_v1_quality_check.json"
    ).exists()


def test_query_clarification_profile_becomes_episodic_memory():
    planner_manifest = {
        "records": [{
            "question": (
                "Looking for eligibility documents for "
                "PN DF250040-501 Paper towel dispenser."
            ),
            "engineer_clarification_profile": {
                "profile_type": "engineer_query_clarification_profile_v1",
                "memory_layer": "working_memory",
                "secondary_memory_layers": [
                    "procedural_memory",
                    "semantic_memory",
                    "critic_memory",
                ],
                "proof_role": "guidance_only",
                "can_be_used_as_proof": False,
                "guidance_only": True,
                "extracted_engineer_clues": {
                    "part_number_candidates": ["DF250040-501"],
                    "fleet_candidates": [
                        "A319", "A320", "A321", "B737", "B787",
                    ],
                    "ata_candidates": ["25"],
                    "eligibility_or_applicability_intent": True,
                },
                "facet_filters": {
                    "part_number": ["DF250040-501"],
                    "fleet_or_aircraft": [
                        "A319", "A320", "A321", "B737", "B787",
                    ],
                    "ata": ["25"],
                    "evidence_language": [
                        "eligibility", "applicability", "effectivity",
                    ],
                },
                "clarifying_questions": [
                    "Do you need eligibility by aircraft platform, "
                    "document type, or approval/effectivity proof?"
                ],
                "risk_flags": [
                    "source_evidence_required",
                    "eligibility_requires_authority_not_mention_only",
                ],
                "recommended_first_pass": [
                    "resolve candidate result back to source evidence"
                ],
                "answer_permission": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            },
        }]
    }

    atoms = build_layered_atoms(
        {"records": []},
        source_core_path="unit_core.json",
        include_seed_atoms=False,
        query_planner_manifests=[planner_manifest],
        query_planner_source_paths=["unit_planner.json"],
    )
    assert len(atoms) == 1
    atom = atoms[0]
    assert atom["atom_id"].startswith(
        "episode_engineer_query_clarification_"
    )
    assert atom["legacy_atom_ids"][0].startswith(
        "working_engineer_query_clarification_"
    )
    assert atom["memory_layer"] == "episodic_memory"
    assert atom["memory_type"] == "engineer_query_clarification_episode"
    assert atom["proof_role"] == "guidance_only"
    assert atom["can_be_used_as_proof"] is False
    assert atom["answer_permission"] is False
    assert atom["source_truth_mutation_allowed"] is False
    assert atom["allowed_behavior"]
    assert atom["forbidden_behavior"]
    assert "DF250040-501" in atom["triggers"]
