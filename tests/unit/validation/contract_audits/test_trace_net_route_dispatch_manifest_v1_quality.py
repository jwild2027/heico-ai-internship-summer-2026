from tiff.trace_net_route_dispatch_manifest_v1_quality import evaluate_quality, RouteDispatchQualityThresholds


def test_quality_passes_with_required_counts() -> None:
    report = {
        "schema_version": "trace_net_route_dispatch_manifest_v1",
        "summary": {
            "route_dispatch_card_count": 10,
            "source_page_dispatch_card_count": 10,
            "primary_route_dispatch_card_count": 10,
            "unsafe_dispatch_card_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "page_route_manifest_quality_status": "PASS",
        },
    }
    q = evaluate_quality(report, RouteDispatchQualityThresholds(
        min_dispatch_cards=10,
        min_source_page_dispatch_cards=10,
        require_page_route_manifest_quality_pass=True,
        require_no_answer_permission=True,
    ))
    assert q["quality_status"] == "PASS"


def test_quality_fails_when_upstream_quality_not_pass() -> None:
    report = {
        "schema_version": "trace_net_route_dispatch_manifest_v1",
        "summary": {
            "route_dispatch_card_count": 10,
            "source_page_dispatch_card_count": 10,
            "primary_route_dispatch_card_count": 10,
            "unsafe_dispatch_card_count": 0,
            "answer_permission_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "page_route_manifest_quality_status": "FAIL",
        },
    }
    q = evaluate_quality(report, RouteDispatchQualityThresholds(require_page_route_manifest_quality_pass=True))
    assert q["quality_status"] == "FAIL"
    assert "page_route_manifest_quality_pass" in q["quality_fail_reasons"]
