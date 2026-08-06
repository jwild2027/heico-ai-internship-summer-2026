from src.trace_net.validation.trace_net_coordinate_evidence_quality_v1 import (
    evaluate_coordinate_evidence_quality,
)


def _passing_summary():
    return {
        "selected_page_count": 20,
        "source_hash_present_count": 20,
        "route_preserved_count": 20,
        "route_mutation_count": 0,
        "nonblank_page_count": 18,
        "nonblank_page_with_word_boxes_count": 18,
        "blank_page_count": 2,
        "blank_page_with_word_boxes_count": 0,
        "invalid_coordinate_count": 0,
        "table_page_count": 8,
        "table_page_with_row_candidate_count": 8,
        "table_row_missing_coordinate_count": 0,
        "table_row_claim_proof_count": 0,
        "visual_page_count": 6,
        "visual_page_with_psm11_word_boxes_count": 6,
        "callout_on_nonvisual_route_count": 0,
        "callout_missing_bbox_count": 0,
        "callout_confirmed_count": 0,
        "callout_source_truth_count": 0,
        "normal_text_page_count": 4,
        "normal_text_page_with_block_count": 4,
        "answer_permission_count": 0,
        "can_prove_claims_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "qdrant_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }


def test_coordinate_quality_passes_only_complete_route_balanced_smoke():
    result = evaluate_coordinate_evidence_quality(
        {"summary": _passing_summary()},
        expected_pages=20,
        expected_nonblank_pages=18,
        expected_blank_pages=2,
    )
    assert result["quality_status"] == "PASS"
    assert result["checks"]["routing_frozen_all_pages"] is True
    assert result["checks"]["table_pages_have_coordinate_rows"] is True
    assert result["checks"]["callouts_only_on_visual_routes"] is True
    assert result["checks"]["all_coordinates_inside_page"] is True


def test_coordinate_quality_fails_on_route_mutation_or_unsafe_callout():
    summary = _passing_summary()
    summary["route_mutation_count"] = 1
    summary["callout_on_nonvisual_route_count"] = 2
    result = evaluate_coordinate_evidence_quality(
        {"summary": summary},
        expected_pages=20,
        expected_nonblank_pages=18,
        expected_blank_pages=2,
    )
    assert result["quality_status"] == "FAIL"
    assert "routing_frozen_all_pages" in result["failures"]
    assert "callouts_only_on_visual_routes" in result["failures"]


def test_coordinate_quality_fails_when_blank_page_invents_words():
    summary = _passing_summary()
    summary["blank_page_with_word_boxes_count"] = 1
    result = evaluate_coordinate_evidence_quality(
        {"summary": summary},
        expected_pages=20,
        expected_nonblank_pages=18,
        expected_blank_pages=2,
    )
    assert result["quality_status"] == "FAIL"
    assert "blank_pages_no_invented_words" in result["failures"]
