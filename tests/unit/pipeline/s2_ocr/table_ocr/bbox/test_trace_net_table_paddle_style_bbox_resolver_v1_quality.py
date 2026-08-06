from tiff.trace_net_table_paddle_style_bbox_resolver_v1 import Thresholds, build_quality


def test_paddle_style_bbox_resolver_quality_passes() -> None:
    summary = {
        "resolver_card_count": 2,
        "selected_bbox_card_count": 2,
        "route_blocked_card_count": 0,
        "unsafe_resolver_card_count": 0,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "route_dispatch_processor_contract_quality_status": "PASS",
    }
    assert build_quality(summary, Thresholds())["status"] == "PASS"


def test_paddle_style_bbox_resolver_quality_fails_unsafe() -> None:
    summary = {
        "resolver_card_count": 2,
        "selected_bbox_card_count": 2,
        "route_blocked_card_count": 0,
        "unsafe_resolver_card_count": 1,
        "answer_permission_count": 0,
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "route_dispatch_processor_contract_quality_status": "PASS",
    }
    assert build_quality(summary, Thresholds())["status"] == "FAIL"
