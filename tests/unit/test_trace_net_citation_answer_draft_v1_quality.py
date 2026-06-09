from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tiff import trace_net_citation_answer_draft_v1 as mod


def base_summary() -> dict:
    return {
        "answer_status": "CITATION_DRAFT_ONLY",
        "final_answer_allowed": False,
        "llm_freeform_answer_allowed": False,
        "context_pack_quality_status": "PASS",
        "context_pack_answer_status": "CONTEXT_PACK_ONLY",
        "embedding_dim": 1024,
        "claim_count": 2,
        "cited_claim_count": 2,
        "uncited_claim_count": 0,
        "retrieval_only_claim_count": 0,
        "page_profile_claim_count": 0,
        "context_helper_claim_count": 0,
        "source_evidence_claim_count": 0,
        "claim_without_authority_count": 0,
        "claim_without_page_id_count": 0,
        "claim_without_citation_count": 0,
        "direct_answer_allowed_claim_count": 0,
        "claim_proof_direct_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "final_answer_allowed_count": 0,
        "llm_freeform_answer_allowed_count": 0,
        "missing_source_resolution_count": 0,
        "missing_authority_gate_count": 0,
        "missing_citation_requirement_count": 0,
    }


def test_evaluate_draft_quality_passes_clean_summary() -> None:
    quality = mod.evaluate_draft_quality(base_summary(), min_claims=1)
    assert quality.status == "PASS"
    assert all(check["passed"] for check in quality.checks)


def test_evaluate_draft_quality_fails_retrieval_only_claim() -> None:
    summary = base_summary()
    summary["retrieval_only_claim_count"] = 1
    quality = mod.evaluate_draft_quality(summary, min_claims=1)
    assert quality.status == "FAIL"
    failed = {check["name"] for check in quality.checks if not check["passed"]}
    assert "retrieval_only_claim_count" in failed


def test_evaluate_draft_quality_fails_when_final_answer_allowed() -> None:
    summary = base_summary()
    summary["final_answer_allowed"] = True
    quality = mod.evaluate_draft_quality(summary, min_claims=1)
    assert quality.status == "FAIL"


def test_evaluate_draft_quality_can_skip_embedding_dim() -> None:
    summary = base_summary()
    summary["embedding_dim"] = 0
    quality = mod.evaluate_draft_quality(summary, require_embedding_dim=None)
    assert quality.status == "PASS"
