from tiff.trace_net_page_query_response_tiff_content_audit_v1 import Thresholds, check_quality


def test_quality_counts_thresholds_pass():
    payload = {
        "status": "PAGE_QUERY_RESPONSE_TIFF_CONTENT_AUDIT_BUILT",
        "summary": {
            "source_dataset_quality_status": "PASS",
            "record_count": 200,
            "image_opened_count": 200,
            "blank_image_response_match_count": 11,
            "response_page_anchor_count": 200,
            "response_source_entry_anchor_count": 200,
            "vision_evaluated_count": 0,
            "missing_zip_entry_count": 0,
            "image_open_failure_count": 0,
            "blank_mismatch_count": 0,
            "vision_support_fail_count": 0,
            "vision_call_failed_count": 0,
            "unsafe_response_count": 0,
            "answer_capable_response_count": 0,
            "claim_proof_response_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
        },
    }
    thresholds = Thresholds(
        min_records=200,
        min_image_opened=200,
        min_blank_image_matches=1,
        min_response_page_anchors=200,
        min_response_source_entry_anchors=200,
        require_dataset_quality_pass=True,
        require_no_answer_permission=True,
    )
    assert check_quality(payload, thresholds)["quality_status"] == "PASS"


def test_quality_fails_on_unsafe_response():
    payload = {
        "status": "PAGE_QUERY_RESPONSE_TIFF_CONTENT_AUDIT_BUILT",
        "summary": {
            "record_count": 1,
            "image_opened_count": 1,
            "blank_image_response_match_count": 0,
            "response_page_anchor_count": 1,
            "response_source_entry_anchor_count": 1,
            "vision_evaluated_count": 0,
            "missing_zip_entry_count": 0,
            "image_open_failure_count": 0,
            "blank_mismatch_count": 0,
            "vision_support_fail_count": 0,
            "vision_call_failed_count": 0,
            "unsafe_response_count": 0,
            "answer_capable_response_count": 1,
            "claim_proof_response_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
    }
    assert check_quality(payload, Thresholds(max_answer_capable_responses=0))["quality_status"] == "FAIL"
