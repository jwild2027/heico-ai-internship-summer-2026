from tiff.trace_net_table_line_geometry_route_contract_audit_v1_quality import (
    TableLineGeometryRouteContractAuditQualityThresholds,
    evaluate_table_line_geometry_route_contract_audit_quality,
)


def test_quality_passes_for_clean_summary():
    summary = {
        "schema_version": "trace_net_table_line_geometry_route_contract_audit_v1",
        "table_geometry_card_count": 2,
        "route_contract_audit_card_count": 2,
        "table_route_blocked_geometry_card_count": 0,
        "unsafe_audit_card_count": 0,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "table_line_geometry_quality_status": "PASS",
        "route_dispatch_processor_contract_quality_status": "PASS",
    }
    result = evaluate_table_line_geometry_route_contract_audit_quality(
        summary,
        TableLineGeometryRouteContractAuditQualityThresholds(
            min_table_geometry_cards=1,
            min_route_contract_audit_cards=1,
            require_table_line_geometry_quality_pass=True,
            require_route_dispatch_processor_contract_quality_pass=True,
            require_no_answer_permission=True,
        ),
    )
    assert result["quality_status"] == "PASS"


def test_quality_fails_for_blocked_cards():
    summary = {
        "schema_version": "trace_net_table_line_geometry_route_contract_audit_v1",
        "table_geometry_card_count": 2,
        "route_contract_audit_card_count": 2,
        "table_route_blocked_geometry_card_count": 1,
        "unsafe_audit_card_count": 1,
        "answer_permission_count": 0,
        "source_truth_mutation_allowed_count": 0,
    }
    result = evaluate_table_line_geometry_route_contract_audit_quality(
        summary,
        TableLineGeometryRouteContractAuditQualityThresholds(max_table_route_blocked_geometry_cards=0, max_unsafe_audit_cards=0),
    )
    assert result["quality_status"] == "FAIL"
