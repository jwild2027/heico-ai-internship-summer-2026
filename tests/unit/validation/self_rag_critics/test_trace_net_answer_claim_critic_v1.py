from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_answer_claim_critic_v1 import (
    build_answer_claim_critic,
    build_report,
    evaluate_claim,
    quality_report,
)


def _dynamic_report() -> dict:
    return {
        "quality_status": "PASS",
        "query_results": [
            {
                "query_id": "q1",
                "query": "120-46137-001",
                "answer_status": "DYNAMIC_FINAL_GATE_APPROVED",
                "final_answer_allowed": True,
                "final_answer_text": "TRACE-Net dynamic final-gate answer. Page 3 is citation-backed. [cite:verified_part:t_p_120_1176_p000003:abc]",
                "final_claim_count": 1,
                "final_claims": [
                    {
                        "dynamic_final_claim_id": "c1",
                        "claim_text": "Page 3 is a citation-backed TRACE-Net evidence page matching part number 120-46137-001.",
                        "page_id": "t_p_120_1176_p000003",
                        "citation_ids": ["cite:verified_part:t_p_120_1176_p000003:abc"],
                        "retrieval_only": False,
                        "feedback_as_proof": False,
                        "community_as_proof": False,
                        "category_as_proof": False,
                        "source_truth_mutation_allowed": False,
                    }
                ],
                "blocked_claims": [],
                "uncited_final_claim_count": 0,
                "retrieval_only_final_claim_count": 0,
                "feedback_as_proof_count": 0,
                "community_as_proof_count": 0,
                "category_as_proof_count": 0,
                "source_truth_mutation_allowed_count": 0,
            },
            {
                "query_id": "q2",
                "query": "record of revisions",
                "answer_status": "DYNAMIC_FINAL_GATE_APPROVED",
                "final_answer_allowed": True,
                "final_answer_text": "TRACE-Net dynamic final-gate answer. Page 13 is citation-backed. [cite:source_text:t_p_120_1176_p000013:def]",
                "final_claim_count": 1,
                "final_claims": [
                    {
                        "dynamic_final_claim_id": "c2",
                        "claim_text": "Page 13 is a citation-backed TRACE-Net evidence page for the query.",
                        "page_id": "t_p_120_1176_p000013",
                        "citation_ids": ["cite:source_text:t_p_120_1176_p000013:def"],
                        "retrieval_only": False,
                    }
                ],
                "uncited_final_claim_count": 0,
                "retrieval_only_final_claim_count": 0,
                "feedback_as_proof_count": 0,
                "community_as_proof_count": 0,
                "category_as_proof_count": 0,
                "source_truth_mutation_allowed_count": 0,
            },
        ],
        "summary": {"status": "PASS"},
    }


def _suff_report() -> dict:
    return {
        "quality_status": "PASS",
        "sufficiency_records": [
            {
                "query": "120-46137-001",
                "evidence_sufficiency_status": "final_evidence_sufficient",
                "recommended_next_action": "return_final_answer_if_retrieval_critic_allows",
            },
            {
                "query": "record of revisions",
                "evidence_sufficiency_status": "final_evidence_sufficient_but_retrieval_audit_required",
                "recommended_next_action": "audit_retrieval_consistency_before_returning_answer",
            },
        ],
        "summary": {"status": "PASS"},
    }


def _retrieval_report() -> dict:
    return {
        "quality_status": "PASS",
        "critic_records": [
            {"query": "120-46137-001", "critic_status": "final_gate_already_authorized", "recommended_next_action": "return_final_gate_answer"},
            {"query": "record of revisions", "critic_status": "dynamic_final_gate_needs_audit", "recommended_next_action": "audit_dynamic_final_gate_before_returning_answer"},
        ],
        "summary": {"status": "PASS"},
    }


def test_evaluate_claim_blocks_retrieval_only_and_missing_citation() -> None:
    claim = {"claim_text": "Retrieval-only evidence proves this", "retrieval_only": True}
    record = evaluate_claim(claim, query="q", answer_status="DYNAMIC_FINAL_GATE_APPROVED")
    assert record["claim_status"] == "claim_blocked"
    assert "retrieval_only_claim" in record["reason_codes"]
    assert "missing_citation_ids" in record["reason_codes"]
    assert record["can_answer_directly"] is False


def test_build_report_marks_audit_required_when_retrieval_or_evidence_requires_audit() -> None:
    report = build_report(
        dynamic_final_gate_report=_dynamic_report(),
        evidence_sufficiency_report=_suff_report(),
        retrieval_critic_report=_retrieval_report(),
    )
    statuses = {r["query"]: r["answer_claim_critic_status"] for r in report["answer_critic_records"]}
    assert statuses["120-46137-001"] == "answer_claims_clear_for_return"
    assert statuses["record of revisions"] == "answer_claims_need_audit"
    assert report["summary"]["answer_claim_record_count"] == 2
    assert report["summary"]["claim_critic_record_count"] == 2
    assert report["summary"]["feedback_as_proof_count"] == 0


def test_quality_report_passes_clean_read_only_critic() -> None:
    report = build_report(
        dynamic_final_gate_report=_dynamic_report(),
        evidence_sufficiency_report=_suff_report(),
        retrieval_critic_report=_retrieval_report(),
    )
    q = quality_report(
        report,
        min_answer_records=2,
        min_queries=2,
        min_claim_records=2,
        require_dynamic_final_gate_quality_pass=True,
        require_evidence_sufficiency_quality_pass=True,
        require_retrieval_critic_quality_pass=True,
    )
    assert q["status"] == "PASS"
    assert q["checks"]["answer_critic_can_answer_directly_zero"] is True


def test_build_answer_claim_critic_writes_outputs(tmp_path: Path) -> None:
    dynamic_path = tmp_path / "dynamic.json"
    suff_path = tmp_path / "suff.json"
    retrieval_path = tmp_path / "retrieval.json"
    dynamic_path.write_text(json.dumps(_dynamic_report()), encoding="utf-8")
    suff_path.write_text(json.dumps(_suff_report()), encoding="utf-8")
    retrieval_path.write_text(json.dumps(_retrieval_report()), encoding="utf-8")
    out_dir = tmp_path / "out"
    report = build_answer_claim_critic(
        dynamic_final_gate_path=dynamic_path,
        evidence_sufficiency_critic_path=suff_path,
        retrieval_critic_path=retrieval_path,
        output_dir=out_dir,
        min_answer_records=2,
        min_queries=2,
        min_claim_records=2,
        require_dynamic_final_gate_quality_pass=True,
        require_evidence_sufficiency_quality_pass=True,
        require_retrieval_critic_quality_pass=True,
    )
    assert report["quality_status"] == "PASS"
    assert (out_dir / "trace_net_answer_claim_critic_v1.json").exists()
    assert (out_dir / "trace_net_answer_claim_critic_v1_claims.jsonl").exists()
