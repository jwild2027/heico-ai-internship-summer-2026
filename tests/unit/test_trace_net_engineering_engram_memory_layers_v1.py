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
