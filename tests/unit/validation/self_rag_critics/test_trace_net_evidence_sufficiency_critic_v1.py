from tiff.trace_net_evidence_sufficiency_critic_v1 import (
    build_report,
    build_sufficiency_record,
    evaluate_group_sufficiency,
    quality_report,
)


def group(**overrides):
    base = {
        "hybrid_v2_group_id": "g1",
        "page_id": "t_p_120_1176_p000003",
        "citation_ids": ["cite:source_text:t_p_120_1176_p000003:abc"],
        "rag_buckets": ["source_text_evidence"],
        "authorities": ["ocr_text_claim_with_citation"],
        "exact_hit_count": 1,
        "semantic_group_count": 0,
        "retrieval_only": False,
        "category_labels": ["Text / source evidence community"],
    }
    base.update(overrides)
    return base


def hybrid_row(query="120-46137-001", groups=None):
    groups = [group()] if groups is None else groups
    return {
        "query_id": "q1",
        "query": query,
        "ranked_group_count": len(groups),
        "exact_hit_group_count": sum(1 for g in groups if g.get("exact_hit_count", 0) > 0),
        "semantic_group_count": sum(1 for g in groups if g.get("semantic_group_count", 0) > 0),
        "ranked_groups": groups,
    }


def dynamic_result(query="120-46137-001", **overrides):
    base = {
        "query_id": "q1",
        "query": query,
        "answer_status": "DYNAMIC_FINAL_GATE_APPROVED",
        "final_answer_allowed": True,
        "final_answer_text": "A safe answer.",
        "final_claim_count": 1,
        "uncited_final_claim_count": 0,
        "retrieval_only_final_claim_count": 0,
        "feedback_as_proof_count": 0,
        "community_as_proof_count": 0,
        "category_as_proof_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "local_path_leak_count": 0,
        "raw_bytes_repr_count": 0,
        "final_claims": [
            {
                "dynamic_final_claim_id": "c1",
                "page_id": "t_p_120_1176_p000003",
                "citation_ids": ["cite:source_text:t_p_120_1176_p000003:abc"],
                "rag_buckets": ["source_text_evidence"],
                "authorities": ["ocr_text_claim_with_citation"],
                "claim_text": "Page 3 has source text evidence.",
                "retrieval_only": False,
                "source_truth_mutation_allowed": False,
            }
        ],
    }
    base.update(overrides)
    return base


def test_group_sufficiency_requires_lineage_citation_and_authority():
    good = evaluate_group_sufficiency(group())
    assert good["sufficient_for_final_gate"] is True
    bad = evaluate_group_sufficiency(group(citation_ids=[], rag_buckets=["source_evidence"], authorities=[]))
    assert bad["sufficient_for_final_gate"] is False
    assert "missing_citation" in bad["insufficiency_reason_codes"]
    assert "missing_answer_support_authority" in bad["insufficiency_reason_codes"]


def test_final_evidence_sufficient_when_dynamic_gate_and_critic_are_clean():
    rec = build_sufficiency_record(
        hybrid_row(),
        dynamic_result=dynamic_result(),
        retrieval_critic_result={"critic_status": "final_gate_already_authorized"},
    )
    assert rec["evidence_sufficiency_status"] == "final_evidence_sufficient"
    assert rec["dynamic_final_answer_safe_to_return"] is True
    assert rec["can_answer_directly"] is False
    assert rec["can_prove_claims"] is False


def test_final_evidence_requires_audit_when_retrieval_critic_audits():
    rec = build_sufficiency_record(
        hybrid_row(),
        dynamic_result=dynamic_result(),
        retrieval_critic_result={"critic_status": "dynamic_final_gate_needs_audit"},
    )
    assert rec["evidence_sufficiency_status"] == "final_evidence_sufficient_but_retrieval_audit_required"
    assert rec["dynamic_final_answer_safe_to_return"] is False


def test_final_gate_claims_need_audit_when_claim_missing_citation():
    dyn = dynamic_result(final_claims=[{"page_id": "p1", "rag_buckets": ["source_text_evidence"], "authorities": ["ocr_text_claim_with_citation"], "claim_text": "x"}])
    rec = build_sufficiency_record(hybrid_row(), dynamic_result=dyn, retrieval_critic_result={})
    assert rec["evidence_sufficiency_status"] == "final_gate_claims_need_audit"
    assert "insufficient_final_claim_records" in rec["reason_codes"]


def test_exact_query_without_exact_hits_is_insufficient_missing_exact_support():
    rec = build_sufficiency_record(
        hybrid_row(groups=[group(exact_hit_count=0, semantic_group_count=1)]),
        dynamic_result={"query": "120-46137-001", "final_answer_allowed": False, "answer_status": "DYNAMIC_FINAL_GATE_RETRIEVAL_ONLY"},
        retrieval_critic_result={},
    )
    assert rec["evidence_sufficiency_status"] == "insufficient_missing_exact_support"


def test_retrieval_only_groups_are_not_answer_ready():
    rec = build_sufficiency_record(
        hybrid_row(query="record of revisions", groups=[group(rag_buckets=["page_retrieval_profile"], authorities=[], citation_ids=[], retrieval_only=True, exact_hit_count=0, semantic_group_count=1)]),
        dynamic_result=None,
        retrieval_critic_result={},
    )
    assert rec["evidence_sufficiency_status"] in {"insufficient_retrieval_only_evidence", "insufficient_missing_citation"}
    assert rec["can_answer_directly"] is False


def test_build_report_summarizes_source_statuses_and_records():
    report = build_report(
        hybrid_v2_report={"quality_status": "PASS", "query_results": [hybrid_row()]},
        dynamic_final_gate_report={"quality_status": "PASS", "query_results": [dynamic_result()]},
        retrieval_critic_report={"quality_status": "PASS", "critic_records": [{"query": "120-46137-001", "critic_status": "final_gate_already_authorized"}]},
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["sufficiency_record_count"] == 1
    assert report["summary"]["hybrid_v2_quality_status"] == "PASS"
    qr = quality_report(report, min_sufficiency_records=1, min_queries=1, require_hybrid_v2_quality_pass=True)
    assert qr["status"] == "PASS"
