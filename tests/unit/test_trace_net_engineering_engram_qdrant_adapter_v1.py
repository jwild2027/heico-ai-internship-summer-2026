from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_engineering_engram_qdrant_adapter_v1 import (
    build_qdrant_adapter_manifest,
    check_qdrant_adapter_manifest,
    local_search,
    normalize_qdrant_records,
)


def _vector_loader(tmp_path: Path) -> Path:
    layers = [
        "working_memory",
        "semantic_memory",
        "procedural_memory",
        "episodic_memory",
        "trait_memory",
        "critic_memory",
    ]
    records = []
    for i, layer in enumerate(layers):
        records.append({
            "atom_id": f"atom_{layer}",
            "memory_layer": layer,
            "proof_role": "guidance_only" if layer != "working_memory" else "current_proof_context_only",
            "point_id": f"point-{i}",
            "vector": [0.0] * 7 + [1.0] + [0.0] * 56,
            "vector_dim": 64,
            "text_for_embedding": f"{layer} interchangeability OCR proof_context critic repair guidance",
            "qdrant_payload": {
                "atom_id": f"atom_{layer}",
                "memory_layer": layer,
                "proof_role": "guidance_only",
                "text_for_embedding": f"{layer} route behavior proof context",
                "answer_permission": False,
            },
        })
    p = tmp_path / "vector_loader.json"
    p.write_text(json.dumps({
        "quality_status": "PASS",
        "summary": {"vector_dim": 64},
        "collection_plan": {"encoder": "trace_net_hashing_encoder_v1"},
        "qdrant_ready_records": records,
    }), encoding="utf-8")
    return p


def test_normalize_records_enforces_guidance_boundary(tmp_path: Path):
    source = json.loads(_vector_loader(tmp_path).read_text(encoding="utf-8"))
    records = normalize_qdrant_records(source, collection_name="c")
    assert len(records) == 6
    assert records[0]["payload"]["answer_permission"] is False
    assert records[0]["payload"]["engram_guidance_only"] is True
    assert records[0]["payload"]["manual_claims_require_proof_context"] is True


def test_local_search_returns_ranked_results(tmp_path: Path):
    source = json.loads(_vector_loader(tmp_path).read_text(encoding="utf-8"))
    records = normalize_qdrant_records(source, collection_name="c")
    results = local_search(records, "interchangeability requires proof_context", top_k=3, vector_dim=64)
    assert len(results) == 3
    assert results[0]["score"] >= results[-1]["score"]


def test_build_qdrant_adapter_dry_run_passes(tmp_path: Path):
    manifest = build_qdrant_adapter_manifest(
        vector_loader=_vector_loader(tmp_path),
        output_dir=tmp_path / "out",
        min_records=6,
        min_local_queries=3,
        require_all_layers=True,
        require_source_quality_pass=True,
        require_no_answer_permission=True,
        max_unsafe=0,
        max_write_attempts=0,
    )
    assert manifest["quality_status"] == "PASS"
    s = manifest["summary"]
    assert s["qdrant_point_record_count"] == 6
    assert s["qdrant_write_attempt_count"] == 0
    assert s["qdrant_read_attempt_count"] == 0
    assert s["write_attempt_count"] == 0


def test_check_qdrant_adapter(tmp_path: Path):
    manifest = build_qdrant_adapter_manifest(
        vector_loader=_vector_loader(tmp_path),
        output_dir=tmp_path / "out",
        min_records=6,
        require_all_layers=True,
        require_source_quality_pass=True,
        require_no_answer_permission=True,
    )
    path = tmp_path / "out" / "trace_net_engineering_engram_qdrant_adapter_v1.json"
    result = check_qdrant_adapter_manifest(
        qdrant_adapter=path,
        min_records=6,
        min_local_queries=3,
        require_quality_pass=True,
        require_all_layers=True,
        require_no_answer_permission=True,
    )
    assert result["quality_status"] == "PASS"
    assert result["qdrant_point_record_count"] == 6
