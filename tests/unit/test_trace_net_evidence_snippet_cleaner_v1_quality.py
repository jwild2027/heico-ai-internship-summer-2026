from __future__ import annotations

from tiff import trace_net_evidence_snippet_cleaner_v1 as mod


def passing_summary() -> dict:
    return {
        "answer_status": "CLEAN_SNIPPETS_ONLY",
        "final_answer_allowed": False,
        "llm_freeform_answer_allowed": False,
        "clean_snippet_claim_count": 2,
        "cited_clean_snippet_count": 2,
        "uncited_clean_snippet_count": 0,
        "missing_page_id_count": 0,
        "missing_citation_count": 0,
        "missing_clean_snippet_count": 0,
        "boilerplate_snippet_count": 0,
        "local_path_leak_count": 0,
        "raw_bytes_repr_count": 0,
        "forbidden_marker_count": 0,
        "retrieval_only_clean_claim_count": 0,
        "page_profile_clean_claim_count": 0,
        "context_helper_clean_claim_count": 0,
        "source_evidence_clean_claim_count": 0,
        "derived_context_clean_claim_count": 0,
        "claim_without_authority_count": 0,
        "direct_answer_allowed_claim_count": 0,
        "claim_proof_direct_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "final_answer_allowed_count": 0,
        "llm_freeform_answer_allowed_count": 0,
        "missing_source_resolution_count": 0,
        "missing_authority_gate_count": 0,
        "missing_citation_requirement_count": 0,
        "snippet_claims_quality_status": "PASS",
        "context_pack_quality_status": "PASS",
        "snippet_claims_answer_status": "SNIPPET_CLAIMS_ONLY",
        "context_pack_answer_status": "CONTEXT_PACK_ONLY",
        "embedding_dim": 1024,
    }


def test_quality_passes_for_safe_summary() -> None:
    result = mod.evaluate_clean_snippet_quality(passing_summary(), min_clean_snippets=1, require_embedding_dim=1024)
    assert result.status == "PASS"
    assert result.passed


def test_quality_fails_boilerplate_leak() -> None:
    summary = passing_summary()
    summary["boilerplate_snippet_count"] = 1
    result = mod.evaluate_clean_snippet_quality(summary, min_clean_snippets=1)
    assert result.status == "FAIL"
    assert any(check["name"] == "no_trace_net_boilerplate" and not check["passed"] for check in result.checks)


def test_quality_fails_local_path_leak() -> None:
    summary = passing_summary()
    summary["local_path_leak_count"] = 1
    result = mod.evaluate_clean_snippet_quality(summary, min_clean_snippets=1)
    assert result.status == "FAIL"
    assert any(check["name"] == "no_local_path_or_url_leaks" and not check["passed"] for check in result.checks)


def test_quality_fails_raw_bytes_repr() -> None:
    summary = passing_summary()
    summary["raw_bytes_repr_count"] = 1
    result = mod.evaluate_clean_snippet_quality(summary, min_clean_snippets=1)
    assert result.status == "FAIL"
    assert any(check["name"] == "no_raw_bytes_repr" and not check["passed"] for check in result.checks)


def test_quality_fails_retrieval_only_clean_claim() -> None:
    summary = passing_summary()
    summary["context_helper_clean_claim_count"] = 1
    result = mod.evaluate_clean_snippet_quality(summary, min_clean_snippets=1)
    assert result.status == "FAIL"
    assert any(check["name"] == "context_helper_clean_claim_count" and not check["passed"] for check in result.checks)


def test_quality_fails_wrong_embedding_dim() -> None:
    summary = passing_summary()
    summary["embedding_dim"] = 384
    result = mod.evaluate_clean_snippet_quality(summary, min_clean_snippets=1, require_embedding_dim=1024)
    assert result.status == "FAIL"
    assert any(check["name"] == "embedding_dim" and not check["passed"] for check in result.checks)
