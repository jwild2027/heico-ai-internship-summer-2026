from __future__ import annotations

from tiff.trace_net_artifact_dependency_registry_v1 import quality_report


def test_quality_report_passes_clean_summary() -> None:
    report = {
        "summary": {
            "artifact_record_count": 5,
            "dependency_edge_count": 2,
            "dependency_cycle_count": 0,
            "missing_artifact_path_count": 0,
            "duplicate_artifact_id_count": 0,
            "self_dependency_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "source_truth_mutations_performed": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "direct_answer_allowed_count": 0,
            "claim_proof_allowed_count": 0,
            "can_mutate_source_truth_count": 0,
            "read_only_registry": True,
        }
    }
    q = quality_report(report, min_artifacts=5, min_dependency_edges=1)
    assert q["status"] == "PASS"


def test_quality_report_fails_on_cycle() -> None:
    report = {
        "summary": {
            "artifact_record_count": 5,
            "dependency_edge_count": 2,
            "dependency_cycle_count": 1,
            "missing_artifact_path_count": 0,
            "duplicate_artifact_id_count": 0,
            "self_dependency_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "source_truth_mutations_performed": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "direct_answer_allowed_count": 0,
            "claim_proof_allowed_count": 0,
            "can_mutate_source_truth_count": 0,
            "read_only_registry": True,
        }
    }
    q = quality_report(report)
    assert q["status"] == "FAIL"
    assert any("cycle" in issue for issue in q["issues"])


def test_quality_report_fails_on_source_truth_mutation() -> None:
    report = {
        "summary": {
            "artifact_record_count": 5,
            "dependency_edge_count": 2,
            "dependency_cycle_count": 0,
            "missing_artifact_path_count": 0,
            "duplicate_artifact_id_count": 0,
            "self_dependency_count": 0,
            "source_truth_mutation_allowed_count": 1,
            "source_truth_mutations_performed": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "direct_answer_allowed_count": 0,
            "claim_proof_allowed_count": 0,
            "can_mutate_source_truth_count": 0,
            "read_only_registry": True,
        }
    }
    q = quality_report(report)
    assert q["status"] == "FAIL"
