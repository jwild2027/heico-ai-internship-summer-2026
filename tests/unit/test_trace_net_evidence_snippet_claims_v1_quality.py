from __future__ import annotations

from tiff import trace_net_evidence_snippet_claims_v1 as mod


def passing_summary() -> dict:
    return {
        "answer_status": "SNIPPET_CLAIMS_ONLY",
        "final_answer_allowed": False,
        "llm_freeform_answer_allowed": False,
        "snippet_claim_count": 2,
        "cited_snippet_claim_count": 2,
        "uncited_snippet_claim_count": 0,
        "missing_page_id_count": 0,
        "missing_citation_count": 0,
        "missing_source_snippet_count": 0,
        "source_snippet_present_count": 2,
        "retrieval_only_snippet_claim_count": 0,
        "page_profile_snippet_claim_count": 0,
        "context_helper_snippet_claim_count": 0,
        "source_evidence_snippet_claim_count": 0,
        "derived_context_snippet_claim_count": 0,
        "claim_without_authority_count": 0,
        "claim_without_context_record_count": 0,
        "direct_answer_allowed_claim_count": 0,
        "claim_proof_direct_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "final_answer_allowed_count": 0,
        "llm_freeform_answer_allowed_count": 0,
        "missing_source_resolution_count": 0,
        "missing_authority_gate_count": 0,
        "missing_citation_requirement_count": 0,
        "draft_quality_status": "PASS",
        "context_pack_quality_status": "PASS",
        "draft_answer_status": "CITATION_DRAFT_ONLY",
        "context_pack_answer_status": "CONTEXT_PACK_ONLY",
        "embedding_dim": 1024,
    }


def test_quality_passes_for_safe_summary() -> None:
    result = mod.evaluate_snippet_claims_quality(passing_summary(), min_snippet_claims=1)
    assert result.status == "PASS"
    assert result.passed


def test_quality_fails_uncited_snippet_claim() -> None:
    summary = passing_summary()
    summary["uncited_snippet_claim_count"] = 1
    summary["cited_snippet_claim_count"] = 1
    result = mod.evaluate_snippet_claims_quality(summary, min_snippet_claims=1)
    assert result.status == "FAIL"
    assert any(check["name"] == "all_snippet_claims_cited" and not check["passed"] for check in result.checks)


def test_quality_fails_retrieval_only_claim() -> None:
    summary = passing_summary()
    summary["context_helper_snippet_claim_count"] = 1
    result = mod.evaluate_snippet_claims_quality(summary, min_snippet_claims=1)
    assert result.status == "FAIL"
    assert any(check["name"] == "context_helper_snippet_claim_count" and not check["passed"] for check in result.checks)


def test_quality_fails_missing_snippet() -> None:
    summary = passing_summary()
    summary["missing_source_snippet_count"] = 1
    summary["source_snippet_present_count"] = 1
    result = mod.evaluate_snippet_claims_quality(summary, min_snippet_claims=1)
    assert result.status == "FAIL"
    assert any(check["name"] == "all_snippet_claims_have_snippets" and not check["passed"] for check in result.checks)


def test_quality_fails_wrong_embedding_dim() -> None:
    summary = passing_summary()
    summary["embedding_dim"] = 384
    result = mod.evaluate_snippet_claims_quality(summary, min_snippet_claims=1, require_embedding_dim=1024)
    assert result.status == "FAIL"
    assert any(check["name"] == "embedding_dim" and not check["passed"] for check in result.checks)
