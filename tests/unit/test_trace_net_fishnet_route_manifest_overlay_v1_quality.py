from tiff.trace_net_fishnet_route_manifest_overlay_v1 import evaluate_quality


def make_payload(summary):
    return {"summary": summary, "records": []}


def test_quality_passes_for_safe_overlay_summary():
    status, failures = evaluate_quality(
        make_payload(
            {
                "overlay_record_count": 14,
                "normal_text_overlay_proposal_count": 14,
                "unsafe_record_count": 0,
                "route_change_authorized_count": 0,
                "route_manifest_write_allowed_count": 0,
                "official_route_manifest_mutated_count": 0,
                "answer_permission_count": 0,
                "can_answer_directly_count": 0,
                "can_prove_claims_count": 0,
                "source_truth_mutation_allowed_count": 0,
                "source_policy_quality_status": "PASS",
                "current_route_match_missing_count": 0,
            }
        ),
        min_overlay_records=10,
        min_normal_text_overlay_proposals=10,
        require_source_policy_quality_pass=True,
        require_all_current_routes_matched=True,
        require_no_answer_permission=True,
        require_no_source_truth_mutation=True,
    )
    assert status == "PASS"
    assert failures == []


def test_quality_fails_on_route_authorization_or_manifest_write():
    status, failures = evaluate_quality(
        make_payload(
            {
                "overlay_record_count": 1,
                "normal_text_overlay_proposal_count": 1,
                "unsafe_record_count": 0,
                "route_change_authorized_count": 1,
                "route_manifest_write_allowed_count": 1,
                "official_route_manifest_mutated_count": 0,
            }
        ),
        max_route_change_authorized=0,
        max_route_manifest_write_allowed=0,
    )
    assert status == "FAIL"
    assert any("route_change_authorized_count" in f for f in failures)
    assert any("route_manifest_write_allowed_count" in f for f in failures)


def test_quality_fails_when_missing_current_routes_required():
    status, failures = evaluate_quality(
        make_payload(
            {
                "overlay_record_count": 1,
                "normal_text_overlay_proposal_count": 1,
                "unsafe_record_count": 0,
                "route_change_authorized_count": 0,
                "route_manifest_write_allowed_count": 0,
                "official_route_manifest_mutated_count": 0,
                "current_route_match_missing_count": 1,
            }
        ),
        require_all_current_routes_matched=True,
    )
    assert status == "FAIL"
    assert any("current_route_match_missing_count" in f for f in failures)
