from tiff.trace_net_artifact_dirty_planner_v1 import PlannerThresholds, quality_from_summary


def base_summary():
    return {
        "source_registry_quality_status": "PASS",
        "planner_record_count": 3,
        "dirty_artifact_count": 3,
        "dependency_cycle_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "source_truth_mutations_performed": 0,
        "direct_answer_allowed_count": 0,
        "claim_proof_allowed_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "feedback_as_proof_count": 0,
        "community_as_proof_count": 0,
        "category_as_proof_count": 0,
        "retrieval_only_answer_allowed_count": 0,
    }


def test_quality_passes_clean_summary():
    status, failures = quality_from_summary(
        base_summary(),
        PlannerThresholds(min_planner_records=1, min_dirty_artifacts=1, require_registry_quality_pass=True),
    )
    assert status == "PASS"
    assert failures == []


def test_quality_fails_on_low_records():
    summary = base_summary()
    summary["planner_record_count"] = 0
    status, failures = quality_from_summary(summary, PlannerThresholds(min_planner_records=1))
    assert status == "FAIL"
    assert any("planner_record_count" in f for f in failures)


def test_quality_fails_on_cycle():
    summary = base_summary()
    summary["dependency_cycle_count"] = 1
    status, failures = quality_from_summary(summary, PlannerThresholds(max_dependency_cycle_count=0))
    assert status == "FAIL"
    assert any("dependency_cycle_count" in f for f in failures)


def test_quality_fails_on_safety_counter():
    summary = base_summary()
    summary["opensearch_write_attempt_count"] = 1
    status, failures = quality_from_summary(summary, PlannerThresholds())
    assert status == "FAIL"
    assert any("opensearch_write_attempt_count" in f for f in failures)


def test_quality_fails_when_registry_required_but_not_pass():
    summary = base_summary()
    summary["source_registry_quality_status"] = "FAIL"
    status, failures = quality_from_summary(summary, PlannerThresholds(require_registry_quality_pass=True))
    assert status == "FAIL"
    assert "source_registry_quality_status is not PASS" in failures
