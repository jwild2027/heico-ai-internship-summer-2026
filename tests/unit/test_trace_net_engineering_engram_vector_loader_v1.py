from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_engineering_engram_vector_loader_v1 import (
    REQUIRED_MEMORY_LAYERS,
    build_vector_loader_manifest,
    check_vector_loader_manifest,
    deterministic_hash_vector,
)


def _sample_memory_layers(tmp_path: Path) -> Path:
    atoms = []
    for layer in REQUIRED_MEMORY_LAYERS:
        atoms.append({
            "atom_id": f"atom_{layer}",
            "memory_layer": layer,
            "proof_role": "current_proof_context_only" if layer == "working_memory" else "guidance_only",
            "title": f"Sample {layer}",
            "rule": f"Rule for {layer}: Engram guides behavior and does not prove manual claims.",
            "active": True,
        })
    data = {
        "status": "TRACE_NET_ENGINEERING_ENGRAM_MEMORY_LAYERS_BUILT",
        "quality_status": "PASS",
        "memory_atoms": atoms,
    }
    p = tmp_path / "memory_layers.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_deterministic_hash_vector_is_stable_and_normalized():
    v1 = deterministic_hash_vector("visual route OCR nomenclature", dim=16)
    v2 = deterministic_hash_vector("visual route OCR nomenclature", dim=16)
    assert v1 == v2
    assert len(v1) == 16
    norm = sum(x * x for x in v1) ** 0.5
    assert 0.99 <= norm <= 1.01


def test_build_vector_loader_manifest_creates_qdrant_ready_records(tmp_path: Path):
    source = _sample_memory_layers(tmp_path)
    out = tmp_path / "out"
    manifest = build_vector_loader_manifest(
        memory_layers=source,
        output_dir=out,
        vector_dim=32,
        min_records=6,
        require_all_layers=True,
        max_unsafe=0,
    )
    assert manifest["quality_status"] == "PASS"
    assert manifest["summary"]["qdrant_ready_record_count"] == 6
    assert manifest["summary"]["write_attempt_count"] == 0
    assert manifest["summary"]["answer_permission_count"] == 0
    assert (out / "trace_net_engineering_engram_vector_loader_v1.json").exists()
    assert (out / "trace_net_engineering_engram_vector_loader_v1.jsonl").exists()
    rec = manifest["qdrant_ready_records"][0]
    assert len(rec["vector"]) == 32
    assert rec["qdrant_payload"]["engram_memory_is_proof"] is False
    assert rec["qdrant_payload"]["qdrant_write_attempt"] is False


def test_check_vector_loader_manifest_passes_safe_manifest(tmp_path: Path):
    source = _sample_memory_layers(tmp_path)
    out = tmp_path / "out"
    build_vector_loader_manifest(
        memory_layers=source,
        output_dir=out,
        vector_dim=16,
        min_records=6,
        require_all_layers=True,
        max_unsafe=0,
    )
    result = check_vector_loader_manifest(
        vector_loader=out / "trace_net_engineering_engram_vector_loader_v1.json",
        min_records=6,
        require_all_layers=True,
        require_quality_pass=True,
        require_no_answer_permission=True,
        max_unsafe=0,
        max_write_attempts=0,
    )
    assert result["quality_status"] == "PASS"
    assert result["summary"]["unsafe_finding_count"] == 0


def test_check_vector_loader_manifest_fails_unsafe_payload(tmp_path: Path):
    source = _sample_memory_layers(tmp_path)
    out = tmp_path / "out"
    manifest = build_vector_loader_manifest(memory_layers=source, output_dir=out, min_records=6, require_all_layers=True)
    manifest["qdrant_ready_records"][0]["qdrant_payload"]["answer_permission"] = True
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(manifest), encoding="utf-8")
    result = check_vector_loader_manifest(
        vector_loader=bad,
        min_records=6,
        require_all_layers=True,
        require_no_answer_permission=True,
        max_unsafe=0,
        max_write_attempts=0,
    )
    assert result["quality_status"] == "FAIL"
    assert result["summary"]["unsafe_finding_count"] >= 1
