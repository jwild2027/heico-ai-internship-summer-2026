from __future__ import annotations

from tiff.trace_net_answer_context_pack_v1 import evaluate_context_pack_quality


def passing_summary(**updates):
    summary = {
        "context_pack_group_count": 1,
        "context_record_count": 2,
        "answer_support_record_count": 1,
        "retrieval_only_record_count": 1,
        "ask_quality_status": "PASS",
        "hybrid_quality_status": "PASS",
        "regression_quality_status": "PASS",
        "embedding_dim": 1024,
        "missing_page_id_count": 0,
        "missing_source_candidate_id_count": 0,
        "missing_citation_required_count": 0,
        "retrieval_only_answer_allowed_count": 0,
        "page_profile_answer_allowed_count": 0,
        "context_helper_answer_allowed_count": 0,
        "source_evidence_answer_allowed_count": 0,
        "direct_answer_allowed_record_count": 0,
        "claim_proof_without_authority_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "answer_composition_allowed_count": 0,
        "llm_answer_allowed_count": 0,
        "unsafe_group_count": 0,
        "unsafe_record_count": 0,
    }
    summary.update(updates)
    return summary


def test_quality_passes_clean_summary() -> None:
    quality = evaluate_context_pack_quality(passing_summary())
    assert quality.status == "PASS"
    assert all(check["passed"] for check in quality.checks)


def test_quality_fails_missing_answer_support() -> None:
    quality = evaluate_context_pack_quality(passing_summary(answer_support_record_count=0))
    assert quality.status == "FAIL"
    assert any(check["name"] == "min_answer_support_records" and not check["passed"] for check in quality.checks)


def test_quality_fails_bad_embedding_dim() -> None:
    quality = evaluate_context_pack_quality(passing_summary(embedding_dim=384))
    assert quality.status == "FAIL"
    assert any(check["name"] == "embedding_dim" and not check["passed"] for check in quality.checks)


def test_quality_can_disable_answer_support_minimum_for_route_only_debug() -> None:
    quality = evaluate_context_pack_quality(passing_summary(answer_support_record_count=0), min_answer_support_records=0)
    assert quality.status == "PASS"
