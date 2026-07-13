from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_engineering_engram_memory_layers_v1 import (
    MEMORY_LAYERS,
    build_memory_layer_manifest,
    check_memory_layer_manifest,
    infer_memory_layer,
    validate_layered_manifest,
)


def test_infer_memory_layer_examples():
    assert infer_memory_layer({"atom_id": "policy_no_interchangeability_without_authority_v1"}) == "procedural_memory"
    assert infer_memory_layer({"atom_id": "route_visual_link_vs_ocr_nomenclature_v1"}) == "semantic_memory"
    assert infer_memory_layer({"atom_id": "episode_h13_generic_not_proven_v1"}) == "episodic_memory"
    assert infer_memory_layer({"atom_id": "style_engineering_answer_shape_v1"}) == "trait_memory"
    assert infer_memory_layer({"atom_id": "critic_safe_but_too_generic_repair_v1"}) == "critic_memory"


def test_build_memory_layer_manifest_covers_all_layers(tmp_path: Path):
    core = {
        "engram_atoms": [
            {"atom_id": "policy_no_interchangeability_without_authority_v1", "rule": "Require explicit authority."},
            {"atom_id": "route_visual_link_vs_ocr_nomenclature_v1", "rule": "Visual link and OCR proof are different."},
            {"atom_id": "episode_h13_generic_not_proven_v1", "rule": "Past eval failure."},
            {"atom_id": "style_engineering_answer_shape_v1", "rule": "Use clear answer shape."},
            {"atom_id": "critic_safe_but_too_generic_repair_v1", "rule": "Retrieve repair pattern."},
        ]
    }
    core_path = tmp_path / "core.json"
    core_path.write_text(json.dumps(core), encoding="utf-8")
    manifest = build_memory_layer_manifest(engram_core_path=core_path, output_dir=tmp_path / "out")
    assert manifest["quality_status"] == "PASS"
    counts = manifest["summary"]["layer_counts"]
    assert set(counts) == set(MEMORY_LAYERS)
    assert all(counts[layer] > 0 for layer in MEMORY_LAYERS)
    assert manifest["summary"]["answer_permission_count"] == 0
    assert manifest["summary"]["write_attempt_count"] == 0


def test_validate_rejects_non_guidance_non_working_atom():
    manifest = {
        "memory_atoms": [
            {"atom_id": "bad", "memory_layer": "semantic_memory", "proof_role": "source_truth"},
        ],
        "summary": {"answer_permission_count": 0},
    }
    passed, errors, metrics = validate_layered_manifest(manifest, min_atoms=1, require_all_layers=False)
    assert not passed
    assert any("non-working memory must be guidance_only" in e for e in errors)


def test_check_memory_layer_manifest_writes_quality_check(tmp_path: Path):
    core_path = tmp_path / "core.json"
    core_path.write_text(json.dumps({"engram_atoms": []}), encoding="utf-8")
    manifest = build_memory_layer_manifest(engram_core_path=core_path, output_dir=tmp_path / "out")
    path = tmp_path / "out" / "trace_net_engineering_engram_memory_layers_v1.json"
    result = check_memory_layer_manifest(memory_layers_path=path, min_atoms=6, require_all_layers=True, require_quality_pass=True)
    assert result["quality_status"] == "PASS"
    assert path.with_name("trace_net_engineering_engram_memory_layers_v1_quality_check.json").exists()

def test_engineer_query_clarification_profile_becomes_working_memory_atom():
    from tiff.trace_net_engineering_engram_memory_layers_v1 import build_layered_atoms

    planner_manifest = {
        "records": [
            {
                "question": "Looking for elegibility documents for PN DF250040-501 Paper towel dispenser.",
                "engineer_clarification_profile": {
                    "profile_type": "engineer_query_clarification_profile_v1",
                    "memory_layer": "working_memory",
                    "secondary_memory_layers": ["procedural_memory", "semantic_memory", "critic_memory"],
                    "proof_role": "guidance_only",
                    "can_be_used_as_proof": False,
                    "guidance_only": True,
                    "extracted_engineer_clues": {
                        "part_number_candidates": ["DF250040-501"],
                        "fleet_candidates": ["A319", "A320", "A321", "B737", "B787"],
                        "ata_candidates": ["25"],
                        "eligibility_or_applicability_intent": True,
                    },
                    "facet_filters": {
                        "part_number": ["DF250040-501"],
                        "fleet_or_aircraft": ["A319", "A320", "A321", "B737", "B787"],
                        "ata": ["25"],
                        "evidence_language": ["eligibility", "applicability", "effectivity"],
                    },
                    "clarifying_questions": [
                        "Do you need eligibility by aircraft platform, document type, or approval/effectivity proof?"
                    ],
                    "risk_flags": [
                        "source_evidence_required",
                        "eligibility_requires_authority_not_mention_only",
                    ],
                    "recommended_first_pass": [
                        "resolve candidate result back to OCR/table/visual/source-trace evidence before answering"
                    ],
                    "answer_permission": False,
                    "can_answer_directly": False,
                    "can_prove_claims": False,
                    "source_truth_mutation_allowed": False,
                },
            }
        ]
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
    assert atom["memory_layer"] == "working_memory"
    assert atom["memory_type"] == "engineer_query_clarification"
    assert atom["proof_role"] == "guidance_only"
    assert atom["can_be_used_as_proof"] is False
    assert atom["answer_permission"] is False
    assert atom["source_truth_mutation_allowed"] is False
    assert atom["payload"]["extracted_engineer_clues"]["part_number_candidates"] == ["DF250040-501"]
    assert "eligibility_requires_authority_not_mention_only" in atom["payload"]["risk_flags"]
    assert "DF250040-501" in atom["triggers"]
