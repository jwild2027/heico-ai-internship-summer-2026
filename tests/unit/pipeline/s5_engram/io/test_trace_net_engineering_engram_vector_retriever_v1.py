from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_engineering_engram_vector_retriever_v1 import (
    REQUIRED_LAYERS,
    build_vector_retriever_manifest,
    check_vector_retriever_manifest,
    hashing_vector,
    retrieve_for_query,
)


def _record(atom_id: str, layer: str, text: str, dim: int = 32):
    return {
        "atom_id": atom_id,
        "point_id": atom_id + "_point",
        "memory_layer": layer,
        "proof_role": "guidance_only" if layer != "working_memory" else "current_proof_context_only",
        "vector_dim": dim,
        "text_for_embedding": text,
        "vector": hashing_vector(text, dim=dim),
        "qdrant_payload": {
            "atom_id": atom_id,
            "memory_layer": layer,
            "proof_role": "guidance_only" if layer != "working_memory" else "current_proof_context_only",
            "answer_permission": False,
            "qdrant_write_attempt": False,
            "source_truth_mutation_allowed": False,
            "rule": text,
        },
    }


def _loader(tmp_path: Path):
    records = [
        _record("p1", "procedural_memory", "interchangeability replacement approval requires explicit source authority"),
        _record("s1", "semantic_memory", "visual route establishes figure to part identity OCR nomenclature provides line text proof"),
        _record("w1", "working_memory", "current proof_context citations only no proof means not source trace ready"),
        _record("e1", "episodic_memory", "H13 generic not proven repaired by H14C route specific explanation"),
        _record("t1", "trait_memory", "cautious source trace first helpful but not overclaiming answer style"),
        _record("c1", "critic_memory", "Self RAG CRAG safe but too generic retrieve repair pattern before regenerating"),
    ]
    data = {
        "quality_status": "PASS",
        "collection_plan": {"collection_name": "test", "vector_dim": 32, "distance": "Cosine", "encoder": "trace_net_hashing_encoder_v1"},
        "summary": {"vector_dim": 32, "qdrant_ready_record_count": len(records)},
        "qdrant_ready_records": records,
    }
    p = tmp_path / "loader.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_retrieve_for_query_ranks_relevant_layer():
    records = [
        _record("p1", "procedural_memory", "interchangeability replacement approval requires explicit source authority"),
        _record("s1", "semantic_memory", "visual OCR nomenclature route behavior"),
    ]
    q = {"query_id": "q", "text": "approved replacement interchangeability explicit authority", "expected_layers": ["procedural_memory"]}
    result = retrieve_for_query(q, records, top_k=2, vector_dim=32)
    assert result["result_count"] == 2
    assert result["results"][0]["memory_layer"] == "procedural_memory"
    assert result["results"][0]["answer_permission"] is False


def test_build_manifest_passes_with_all_layers(tmp_path):
    loader = _loader(tmp_path)
    out = tmp_path / "out"
    manifest = build_vector_retriever_manifest(
        vector_loader_path=loader,
        output_dir=out,
        top_k=3,
        min_queries=3,
        min_results_per_query=1,
        require_all_layers=True,
        max_unsafe=0,
    )
    assert manifest["quality_status"] == "PASS"
    assert manifest["summary"]["query_count"] >= 3
    assert manifest["summary"]["answer_permission_count"] == 0
    assert manifest["summary"]["write_attempt_count"] == 0
    assert set(REQUIRED_LAYERS).issubset(set(manifest["summary"]["indexed_memory_layer_counts"].keys()))
    assert (out / "trace_net_engineering_engram_vector_retriever_v1.json").exists()


def test_check_manifest_passes(tmp_path):
    loader = _loader(tmp_path)
    out = tmp_path / "out"
    manifest = build_vector_retriever_manifest(
        vector_loader_path=loader,
        output_dir=out,
        top_k=3,
        min_queries=3,
        min_results_per_query=1,
        require_all_layers=True,
        max_unsafe=0,
    )
    check = check_vector_retriever_manifest(
        vector_retriever_path=manifest["output_path"],
        min_queries=3,
        min_results_per_query=1,
        require_all_layers=True,
        require_quality_pass=True,
        require_no_answer_permission=True,
        max_unsafe=0,
        max_write_attempts=0,
    )
    assert check["quality_status"] == "PASS"
    assert check["write_attempt_count"] == 0


def test_answer_permission_is_failure(tmp_path):
    loader = _loader(tmp_path)
    data = json.loads(loader.read_text())
    data["qdrant_ready_records"][0]["qdrant_payload"]["answer_permission"] = True
    loader.write_text(json.dumps(data), encoding="utf-8")
    manifest = build_vector_retriever_manifest(
        vector_loader_path=loader,
        output_dir=tmp_path / "out_bad",
        min_queries=1,
        min_results_per_query=1,
        require_all_layers=False,
        max_unsafe=0,
    )
    assert manifest["quality_status"] == "FAIL"
    assert manifest["summary"]["answer_permission_count"] > 0
