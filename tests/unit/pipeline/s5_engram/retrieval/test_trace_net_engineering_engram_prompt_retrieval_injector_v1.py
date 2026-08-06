from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_engineering_engram_prompt_retrieval_injector_v1 import (
    build_prompt_guidance_block,
    build_prompt_retrieval_injector_manifest,
    check_prompt_retrieval_injector_manifest,
    select_prompt_atoms,
)


def _item(atom_id, layer, score=0.5, proof_role="guidance_only", answer_permission=False):
    return {
        "rank": 1,
        "atom_id": atom_id,
        "point_id": atom_id + "_point",
        "memory_layer": layer,
        "proof_role": proof_role,
        "title": atom_id,
        "retrieval_score": score,
        "similarity_score": score,
        "keyword_overlap_score": 0.1,
        "text_preview": f"{atom_id} rule for {layer} with source-trace caution",
        "answer_permission": answer_permission,
        "source_truth_mutation_allowed": False,
        "qdrant_write_attempt": False,
    }


def test_select_prompt_atoms_filters_unsafe_and_caps():
    items = [
        _item("a", "procedural_memory", 0.8),
        _item("bad", "trait_memory", 0.9, answer_permission=True),
        _item("b", "semantic_memory", 0.7),
        _item("c", "critic_memory", 0.6),
    ]
    selected = select_prompt_atoms(items, max_atoms=2)
    assert [x["atom_id"] for x in selected] == ["a", "b"]
    assert all(not x["answer_permission"] for x in selected)


def test_prompt_guidance_block_has_not_proof_boundary():
    atoms = [_item("policy", "procedural_memory", 0.8)]
    text = build_prompt_guidance_block(
        query_id="q",
        task_type="approval_boundary",
        query_text="Is this approved?",
        selected_atoms=atoms,
        max_prompt_chars=1200,
    )
    assert "BEHAVIOR ONLY, NOT PROOF" in text
    assert "proof_context" in text
    assert "Forbidden" in text
    assert "policy" in text


def test_build_and_check_prompt_injector_manifest(tmp_path: Path):
    retrieval_records = []
    layers = ["working_memory", "semantic_memory", "procedural_memory", "episodic_memory", "trait_memory", "critic_memory"]
    for idx, layer in enumerate(layers):
        retrieval_records.append({
            "query_id": f"q{idx}",
            "task_type": "unit_test",
            "query_text": f"query {idx}",
            "results": [_item(f"atom_{idx}_{j}", layers[(idx + j) % len(layers)], 0.9 - (j * 0.1)) for j in range(3)],
        })
    source = tmp_path / "retriever.json"
    source.write_text(json.dumps({"quality_status": "PASS", "retrieval_records": retrieval_records}), encoding="utf-8")
    manifest = build_prompt_retrieval_injector_manifest(
        vector_retriever_path=source,
        output_dir=tmp_path / "out",
        max_atoms_per_query=3,
        min_queries=6,
        min_injected_atoms=2,
        require_guidance_only=True,
        require_no_answer_permission=True,
    )
    assert manifest["quality_status"] == "PASS"
    assert manifest["summary"]["prompt_bundle_count"] == 6
    assert manifest["summary"]["answer_permission_count"] == 0
    assert manifest["summary"]["write_attempt_count"] == 0
    check = check_prompt_retrieval_injector_manifest(
        prompt_injector_path=manifest["output_path"],
        min_queries=6,
        min_injected_atoms=6,
        require_quality_pass=True,
        require_guidance_only=True,
        require_no_answer_permission=True,
    )
    assert check["quality_status"] == "PASS"


def test_check_fails_for_missing_not_proof_banner(tmp_path: Path):
    bad = {
        "quality_status": "PASS",
        "prompt_bundles": [{"query_id": "q", "prompt_guidance_text": "no boundary here"}],
        "summary": {
            "query_count": 1,
            "prompt_bundle_count": 1,
            "selected_atom_count": 1,
            "selected_proof_role_counts": {"guidance_only": 1},
            "answer_permission_count": 0,
            "write_attempt_count": 0,
            "unsafe_finding_count": 0,
        },
    }
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    check = check_prompt_retrieval_injector_manifest(
        prompt_injector_path=p,
        require_quality_pass=True,
        require_guidance_only=True,
        require_no_answer_permission=True,
    )
    assert check["quality_status"] == "FAIL"
    assert any("missing_not_proof_banner" in f for f in check["failures"])
