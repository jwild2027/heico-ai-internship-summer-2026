import json
from pathlib import Path

from tiff.trace_net_artifact_dirty_planner_v1 import (
    PlannerThresholds,
    build_dirty_planner,
    check_dirty_planner_quality,
    normalize_edges,
    slug,
)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def sample_registry() -> dict:
    return {
        "quality_status": "PASS",
        "artifacts": [
            {"artifact_id": "opensearch_adapter", "quality_status": "PASS", "path": "local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_adapter_v1.json"},
            {"artifact_id": "hybrid_retrieval_v2", "quality_status": "PASS", "path": "local_data/organization/trace_net/hybrid_retrieval_v2/trace_net_hybrid_retrieval_v2.json"},
            {"artifact_id": "dynamic_final_gate_execution", "quality_status": "PASS", "path": "local_data/organization/trace_net/dynamic_final_gate_execution/trace_net_dynamic_final_gate_execution_v1.json"},
            {"artifact_id": "retrieval_critic", "quality_status": "PASS", "path": "local_data/organization/trace_net/retrieval_critic/trace_net_retrieval_critic_v1.json"},
        ],
        "dependency_edges": [
            {"upstream_artifact_id": "opensearch_adapter", "downstream_artifact_id": "hybrid_retrieval_v2"},
            {"upstream_artifact_id": "hybrid_retrieval_v2", "downstream_artifact_id": "dynamic_final_gate_execution"},
            {"upstream_artifact_id": "dynamic_final_gate_execution", "downstream_artifact_id": "retrieval_critic"},
        ],
    }


def test_slug_normalizes_trace_net_names():
    assert slug("trace_net_hybrid_retrieval_v2.json") == "hybrid_retrieval_v2"
    assert slug("local_data/x/trace_net_opensearch_adapter_v1_quality.json") == "opensearch_adapter"


def test_normalize_edges_supports_registry_shape():
    edges = normalize_edges(sample_registry())
    assert {e["upstream_artifact_id"] for e in edges} >= {"opensearch_adapter", "hybrid_retrieval_v2", "dynamic_final_gate_execution"}


def test_build_dirty_planner_follows_downstream_registry_edges(tmp_path):
    registry = tmp_path / "registry.json"
    write_json(registry, sample_registry())
    out = tmp_path / "out"

    report = build_dirty_planner(
        artifact_registry=registry,
        changed_artifacts=["opensearch_adapter"],
        output_dir=out,
        thresholds=PlannerThresholds(min_planner_records=3, min_dirty_artifacts=3, require_registry_quality_pass=True),
        include_default_trace_net_rules=False,
        write_quality=True,
    )

    assert report["quality_status"] == "PASS"
    assert report["summary"]["dirty_artifact_count"] == 3
    assert report["dirty_artifacts"][:3] == ["hybrid_retrieval_v2", "dynamic_final_gate_execution", "retrieval_critic"]
    assert (out / "trace_net_artifact_dirty_planner_v1.json").exists()
    assert (out / "trace_net_artifact_dirty_planner_v1_quality.json").exists()


def test_changed_input_path_matches_artifact(tmp_path):
    registry = tmp_path / "registry.json"
    write_json(registry, sample_registry())

    report = build_dirty_planner(
        artifact_registry=registry,
        changed_inputs=["local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_adapter_v1.json"],
        output_dir=tmp_path / "out",
        include_default_trace_net_rules=False,
    )

    assert "opensearch_adapter" in report["seed_artifacts"]
    assert report["summary"]["dirty_artifact_count"] >= 1


def test_default_trace_net_rules_expand_new_modules(tmp_path):
    registry = tmp_path / "registry.json"
    write_json(registry, {"quality_status": "PASS", "artifacts": [], "dependency_edges": []})

    report = build_dirty_planner(
        artifact_registry=registry,
        changed_artifacts=["opensearch_adapter"],
        output_dir=tmp_path / "out",
        thresholds=PlannerThresholds(min_planner_records=5, min_dirty_artifacts=5, require_registry_quality_pass=True),
        include_default_trace_net_rules=True,
    )

    assert report["quality_status"] == "PASS"
    assert "hybrid_retrieval_v2" in report["dirty_artifacts"]
    assert "ask_api_final_return_policy_v21" in report["dirty_artifacts"]
    assert report["summary"]["default_rule_edge_count"] > 0


def test_cycle_detection_fails_quality_when_cycle_present(tmp_path):
    registry = tmp_path / "registry.json"
    write_json(
        registry,
        {
            "quality_status": "PASS",
            "artifacts": [{"artifact_id": "a"}, {"artifact_id": "b"}],
            "dependency_edges": [
                {"upstream_artifact_id": "a", "downstream_artifact_id": "b"},
                {"upstream_artifact_id": "b", "downstream_artifact_id": "a"},
            ],
        },
    )

    report = build_dirty_planner(
        artifact_registry=registry,
        changed_artifacts=["a"],
        output_dir=tmp_path / "out",
        thresholds=PlannerThresholds(max_dependency_cycle_count=0),
        include_default_trace_net_rules=False,
    )

    assert report["quality_status"] == "FAIL"
    assert report["summary"]["dependency_cycle_count"] >= 1


def test_quality_checker_writes_quality_json(tmp_path):
    registry = tmp_path / "registry.json"
    write_json(registry, sample_registry())
    out = tmp_path / "out"
    build_dirty_planner(
        artifact_registry=registry,
        changed_artifacts=["opensearch_adapter"],
        output_dir=out,
        include_default_trace_net_rules=False,
    )

    quality = check_dirty_planner_quality(
        out / "trace_net_artifact_dirty_planner_v1.json",
        thresholds=PlannerThresholds(min_planner_records=1, min_dirty_artifacts=1),
        write_json_report=True,
    )

    assert quality["quality_status"] == "PASS"
    assert (out / "trace_net_artifact_dirty_planner_v1_quality.json").exists()


def test_safety_contract_stays_read_only(tmp_path):
    registry = tmp_path / "registry.json"
    write_json(registry, sample_registry())
    report = build_dirty_planner(
        artifact_registry=registry,
        changed_artifacts=["opensearch_adapter"],
        output_dir=tmp_path / "out",
        include_default_trace_net_rules=False,
    )
    for key in [
        "postgres_write_attempt_count",
        "qdrant_write_attempt_count",
        "opensearch_write_attempt_count",
        "source_truth_mutation_allowed_count",
        "direct_answer_allowed_count",
        "claim_proof_allowed_count",
    ]:
        assert report["summary"][key] == 0
    assert report["safety_contract"] == {
        "postgres_writes": False,
        "qdrant_writes": False,
        "opensearch_writes": False,
        "source_truth_mutation": False,
        "answer_permission": False,
        "claim_proof_authority": False,
    }
