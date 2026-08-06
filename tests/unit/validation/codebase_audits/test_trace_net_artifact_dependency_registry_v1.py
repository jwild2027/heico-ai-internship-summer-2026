from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_artifact_dependency_registry_v1 import (
    build_artifact_dependency_registry,
    detect_cycles,
    read_json,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def make_artifact(root: Path, stage: str, name: str, summary: dict | None = None, quality: str = "PASS") -> Path:
    stage_dir = root / stage
    report_path = stage_dir / name
    quality_path = stage_dir / f"{report_path.stem}_quality.json"
    payload = {
        "schema_version": report_path.stem,
        "status": "BUILT",
        "quality_status": quality,
        "summary": {"status": quality, **(summary or {})},
        "quality_path": quality_path.as_posix(),
        "records": [{"page_id": "p1"}],
    }
    write_json(report_path, payload)
    write_json(quality_path, {"status": quality})
    return report_path


def synthetic_root(tmp_path: Path) -> Path:
    root = tmp_path / "trace_net"
    make_artifact(root, "page_element_registry", "trace_net_page_element_registry_v1.json", {"page_count": 2, "page_registry_record_count": 2})
    make_artifact(root, "table_cell_normalizer", "trace_net_table_cell_normalizer_v1.json", {"normalized_row_count": 3, "normalized_cell_count": 5})
    make_artifact(root, "element_graph_attachment", "trace_net_element_graph_attachment_plan_v1.json", {"node_plan_count": 10, "edge_plan_count": 11})
    make_artifact(root, "opensearch_adapter", "trace_net_opensearch_adapter_v1.json", {"opensearch_document_count": 7})
    return root


def test_build_artifact_dependency_registry(tmp_path: Path) -> None:
    root = synthetic_root(tmp_path)
    report = build_artifact_dependency_registry(
        trace_net_root=root,
        output_dir=tmp_path / "out",
        min_artifacts=4,
        min_dependency_edges=1,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["artifact_record_count"] == 4
    assert report["summary"]["dependency_edge_count"] >= 1
    assert report["summary"]["dependency_cycle_count"] == 0
    assert report["summary"]["source_truth_mutation_allowed_count"] == 0
    assert (tmp_path / "out" / "trace_net_artifact_dependency_registry_v1.json").exists()
    assert (tmp_path / "out" / "trace_net_artifact_dependency_registry_v1_records.jsonl").exists()


def test_registry_records_include_cache_keys_and_dependency_ids(tmp_path: Path) -> None:
    root = synthetic_root(tmp_path)
    report = build_artifact_dependency_registry(root, tmp_path / "out")
    records = report["artifact_records"]
    assert all(r.get("artifact_cache_key") for r in records)
    graph = next(r for r in records if r["stage_id"] == "element_graph_attachment")
    assert graph["input_artifact_count"] >= 1
    assert graph["resolved_input_artifact_ids"]


def test_skips_quality_summary_and_self_output_files(tmp_path: Path) -> None:
    root = synthetic_root(tmp_path)
    write_json(root / "page_element_registry" / "trace_net_page_element_registry_v1_summary.json", {"quality_status": "FAIL"})
    write_json(root / "artifact_dependency_registry" / "trace_net_artifact_dependency_registry_v1.json", {"quality_status": "FAIL"})
    report = build_artifact_dependency_registry(root, tmp_path / "out")
    rels = {r["relative_path"] for r in report["artifact_records"]}
    assert not any("summary" in rel for rel in rels)
    assert not any(rel.startswith("artifact_dependency_registry") for rel in rels)


def test_cycle_detector_finds_cycle() -> None:
    edges = [
        {"source_artifact_id": "a", "target_artifact_id": "b"},
        {"source_artifact_id": "b", "target_artifact_id": "c"},
        {"source_artifact_id": "c", "target_artifact_id": "a"},
    ]
    cycles = detect_cycles(edges)
    assert cycles


def test_page_profiles_and_page_registry_dependency_is_acyclic(tmp_path: Path) -> None:
    root = tmp_path / "trace_net"
    make_artifact(root, "graph_context_v2_nomenclature_v1", "trace_net_graph_baseline_checkpoint_v1.json", {"page_count": 2})
    make_artifact(root, "context_retrieval_helpers", "trace_net_context_retrieval_helpers_v1.json", {"context_helper_record_count": 2})
    make_artifact(root, "page_retrieval_profiles", "trace_net_page_retrieval_profiles_v1.json", {"page_profile_record_count": 2})
    make_artifact(root, "embedding_candidates", "trace_net_embedding_candidates_v1.json", {"embedding_candidate_count": 2})
    make_artifact(root, "page_element_registry", "trace_net_page_element_registry_v1.json", {"page_registry_record_count": 2})

    report = build_artifact_dependency_registry(root, tmp_path / "out", min_artifacts=5, min_dependency_edges=2)

    assert report["quality_status"] == "PASS"
    assert report["summary"]["dependency_cycle_count"] == 0

    profiles = next(r for r in report["artifact_records"] if r["stage_id"] == "page_retrieval_profiles")
    registry = next(r for r in report["artifact_records"] if r["stage_id"] == "page_element_registry")
    assert "page_element_registry" not in profiles["input_stage_ids"]
    assert "page_retrieval_profiles" in registry["input_stage_ids"]


def test_opensearch_mapping_file_is_not_primary_artifact(tmp_path: Path) -> None:
    root = synthetic_root(tmp_path)
    write_json(root / "opensearch_adapter" / "trace_net_opensearch_mapping_v1.json", {"mappings": {"properties": {}}})

    report = build_artifact_dependency_registry(root, tmp_path / "out")
    rels = {r["relative_path"] for r in report["artifact_records"]}

    assert "opensearch_adapter/trace_net_opensearch_mapping_v1.json" not in rels


def test_helper_matrix_file_is_not_primary_artifact(tmp_path: Path) -> None:
    root = synthetic_root(tmp_path)
    write_json(root / "page_element_registry" / "trace_net_core_algorithm_matrix_v1.json", {"not": "a primary stage report"})

    report = build_artifact_dependency_registry(root, tmp_path / "out")
    rels = {r["relative_path"] for r in report["artifact_records"]}

    assert "page_element_registry/trace_net_core_algorithm_matrix_v1.json" not in rels
    assert report["summary"]["missing_quality_status_count"] == 0
    assert report["summary"]["quality_not_pass_count"] == 0


def test_legacy_evidence_consensus_summary_is_normalized(tmp_path: Path) -> None:
    root = tmp_path / "trace_net"
    write_json(
        root / "evidence_consensus" / "evidence_consensus_summary.json",
        {
            "schema_version": "trace_net_evidence_consensus_summary_v1",
            "status": "OK",
            "summary": {"status": "OK", "record_count": 3, "page_count": 2},
        },
    )
    make_artifact(root, "graph_context_v2_nomenclature_v1", "trace_net_graph_baseline_checkpoint_v1.json", {"page_count": 2})
    make_artifact(root, "context_retrieval_helpers", "trace_net_context_retrieval_helpers_v1.json", {"context_helper_record_count": 2})
    make_artifact(root, "page_retrieval_profiles", "trace_net_page_retrieval_profiles_v1.json", {"page_profile_record_count": 2})
    make_artifact(root, "embedding_candidates", "trace_net_embedding_candidates_v1.json", {"embedding_candidate_count": 2})
    make_artifact(root, "page_element_registry", "trace_net_page_element_registry_v1.json", {"page_registry_record_count": 2})

    report = build_artifact_dependency_registry(root, tmp_path / "out", min_artifacts=5, min_dependency_edges=2)
    evidence = next(r for r in report["artifact_records"] if r["stage_id"] == "evidence_consensus")
    embedding = next(r for r in report["artifact_records"] if r["stage_id"] == "embedding_candidates")
    registry = next(r for r in report["artifact_records"] if r["stage_id"] == "page_element_registry")

    assert evidence["quality_status"] == "OK"
    assert "evidence_consensus" not in embedding["missing_input_stage_ids"]
    assert "evidence_consensus" not in registry["missing_input_stage_ids"]
    assert report["summary"]["missing_dependency_reference_count"] == 0


def test_optional_missing_dependencies_are_reported_separately(tmp_path: Path) -> None:
    root = tmp_path / "trace_net"
    write_json(
        root / "evidence_consensus" / "evidence_consensus_summary.json",
        {"status": "OK", "summary": {"status": "OK", "record_count": 1}},
    )
    make_artifact(root, "graph_context_v2_nomenclature_v1", "trace_net_graph_baseline_checkpoint_v1.json", {"page_count": 2})
    make_artifact(root, "context_retrieval_helpers", "trace_net_context_retrieval_helpers_v1.json", {"context_helper_record_count": 2})
    make_artifact(root, "embedding_candidates", "trace_net_embedding_candidates_v1.json", {"embedding_candidate_count": 2})
    make_artifact(root, "page_retrieval_profiles", "trace_net_page_retrieval_profiles_v1.json", {"page_profile_record_count": 2})
    make_artifact(root, "vector_search_smoke", "trace_net_vector_search_smoke_v1.json", {"query_count": 1})

    report = build_artifact_dependency_registry(root, tmp_path / "out", min_artifacts=6)
    smoke = next(r for r in report["artifact_records"] if r["stage_id"] == "vector_search_smoke")

    assert "qdrant_loader" not in smoke["missing_input_stage_ids"]
    assert "qdrant_loader" in smoke["optional_missing_input_stage_ids"]
    assert report["summary"]["missing_dependency_reference_count"] == 0
    assert report["summary"]["optional_missing_dependency_reference_count"] >= 1
