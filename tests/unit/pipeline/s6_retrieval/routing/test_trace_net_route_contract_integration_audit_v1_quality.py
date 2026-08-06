from tiff.trace_net_route_contract_integration_audit_v1 import AuditThresholds, build_quality


def test_route_contract_integration_audit_quality_passes_zero_violations() -> None:
    summary = {
        "audited_processor_count": 6,
        "audited_record_count": 10,
        "route_contract_violation_card_count": 0,
        "blocked_dispatch_leak_count": 0,
        "direct_answer_leak_count": 0,
        "source_truth_mutation_leak_count": 0,
        "unsafe_audit_card_count": 0,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "route_dispatch_processor_contract_quality_status": "PASS",
    }
    quality = build_quality(summary, AuditThresholds())
    assert quality["status"] == "PASS"


def test_route_contract_integration_audit_quality_fails_violations() -> None:
    summary = {
        "audited_processor_count": 6,
        "audited_record_count": 10,
        "route_contract_violation_card_count": 1,
        "blocked_dispatch_leak_count": 0,
        "direct_answer_leak_count": 0,
        "source_truth_mutation_leak_count": 0,
        "unsafe_audit_card_count": 1,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "route_dispatch_processor_contract_quality_status": "PASS",
    }
    quality = build_quality(summary, AuditThresholds())
    assert quality["status"] == "FAIL"
