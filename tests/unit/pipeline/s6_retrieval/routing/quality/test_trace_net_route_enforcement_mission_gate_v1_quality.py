from tiff.trace_net_route_enforcement_mission_gate_v1 import MissionGateThresholds, build_quality


def test_route_enforcement_mission_gate_quality_passes() -> None:
    summary = {
        "required_artifact_count": 7,
        "failed_required_artifact_count": 0,
        "route_contract_violation_card_count": 0,
        "blocked_dispatch_leak_count": 0,
        "direct_answer_leak_count": 0,
        "source_truth_mutation_leak_count": 0,
        "unsafe_audit_card_count": 0,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
    }
    assert build_quality(summary, MissionGateThresholds())["status"] == "PASS"


def test_route_enforcement_mission_gate_quality_fails_route_violation() -> None:
    summary = {
        "required_artifact_count": 7,
        "failed_required_artifact_count": 0,
        "route_contract_violation_card_count": 1,
        "blocked_dispatch_leak_count": 0,
        "direct_answer_leak_count": 0,
        "source_truth_mutation_leak_count": 0,
        "unsafe_audit_card_count": 1,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
    }
    assert build_quality(summary, MissionGateThresholds())["status"] == "FAIL"
