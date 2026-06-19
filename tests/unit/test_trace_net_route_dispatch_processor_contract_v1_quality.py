from tiff.trace_net_route_dispatch_processor_contract_v1_quality import (
    RouteDispatchProcessorContractQualityThresholds,
    evaluate_route_dispatch_processor_contract_quality,
)


def test_quality_passes_for_clean_contract() -> None:
    quality = evaluate_route_dispatch_processor_contract_quality(
        {
            "schema_version": "trace_net_route_dispatch_processor_contract_v1",
            "summary": {
                "schema_version": "trace_net_route_dispatch_processor_contract_v1",
                "processor_contract_card_count": 10,
                "source_page_processor_contract_card_count": 10,
                "table_processor_allowed_page_count": 3,
                "image_visual_processor_allowed_page_count": 2,
                "coverage_violation_count": 0,
                "unsafe_contract_card_count": 0,
                "answer_permission_count": 0,
                "source_truth_mutation_allowed_count": 0,
                "route_dispatch_manifest_quality_status": "PASS",
                "route_dispatch_coverage_audit_quality_status": "PASS",
                "route_dispatch_warning_triage_quality_status": "PASS",
            },
        },
        RouteDispatchProcessorContractQualityThresholds(
            min_processor_contract_cards=1,
            min_source_page_processor_contract_cards=1,
            min_table_processor_pages=1,
            min_image_visual_processor_pages=1,
            require_route_dispatch_manifest_quality_pass=True,
            require_route_dispatch_coverage_audit_quality_pass=True,
            require_route_dispatch_warning_triage_quality_pass=True,
            require_no_answer_permission=True,
        ),
    )
    assert quality["quality_status"] == "PASS"


def test_quality_fails_on_coverage_violations() -> None:
    quality = evaluate_route_dispatch_processor_contract_quality(
        {
            "summary": {
                "schema_version": "trace_net_route_dispatch_processor_contract_v1",
                "processor_contract_card_count": 10,
                "source_page_processor_contract_card_count": 10,
                "coverage_violation_count": 1,
                "unsafe_contract_card_count": 0,
                "answer_permission_count": 0,
                "source_truth_mutation_allowed_count": 0,
            }
        },
        RouteDispatchProcessorContractQualityThresholds(max_coverage_violation_count=0),
    )
    assert quality["quality_status"] == "FAIL"
    assert "coverage_violation_count_within_limit" in quality["quality_fail_reasons"]
