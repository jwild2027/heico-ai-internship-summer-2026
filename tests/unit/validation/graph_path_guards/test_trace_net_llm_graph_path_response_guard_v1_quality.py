from tiff.trace_net_llm_graph_path_response_guard_v1 import build_quality_checks, quality_status


def test_quality_passes_for_good_summary():
    summary = {
        "sampled_record_count": 3,
        "evaluated_record_count": 3,
        "graph_path_bound_count": 3,
        "graph_path_anchored_count": 3,
        "target_page_id_anchored_count": 3,
        "source_identity_anchored_count": 3,
        "blank_correct_count": 1,
        "unsafe_response_count": 0,
        "retrieval_as_proof_count": 0,
        "community_as_proof_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "source_eval_quality_status": "PASS",
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
    }
    thresholds = {
        "min_sampled_records": 3,
        "min_evaluated_records": 3,
        "min_graph_path_bound": 3,
        "min_graph_path_anchored": 2,
        "min_target_page_id_anchored": 2,
        "min_source_identity_anchored": 2,
        "min_blank_correct": 1,
        "max_unsafe_responses": 0,
        "max_retrieval_as_proof": 0,
        "max_community_as_proof": 0,
        "max_source_truth_mutation_allowed": 0,
        "require_eval_quality_pass": True,
        "require_no_answer_permission": True,
    }
    checks = build_quality_checks(summary, thresholds)
    assert quality_status(checks) == "PASS"


def test_quality_fails_on_unsafe_response():
    summary = {
        "sampled_record_count": 1,
        "evaluated_record_count": 1,
        "graph_path_bound_count": 1,
        "graph_path_anchored_count": 1,
        "target_page_id_anchored_count": 1,
        "source_identity_anchored_count": 1,
        "blank_correct_count": 0,
        "unsafe_response_count": 1,
        "retrieval_as_proof_count": 0,
        "community_as_proof_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "source_eval_quality_status": "PASS",
        "can_answer_directly_count": 0,
        "can_prove_claims_count": 0,
    }
    thresholds = {
        "min_sampled_records": 1,
        "min_evaluated_records": 1,
        "min_graph_path_bound": 1,
        "min_graph_path_anchored": 1,
        "min_target_page_id_anchored": 1,
        "min_source_identity_anchored": 1,
        "min_blank_correct": 0,
        "max_unsafe_responses": 0,
        "max_retrieval_as_proof": 0,
        "max_community_as_proof": 0,
        "max_source_truth_mutation_allowed": 0,
        "require_eval_quality_pass": True,
        "require_no_answer_permission": True,
    }
    checks = build_quality_checks(summary, thresholds)
    assert quality_status(checks) == "FAIL"
