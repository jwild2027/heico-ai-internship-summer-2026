from __future__ import annotations

from tiff.trace_net_retrieval_critic_v1 import (
    build_critic_record,
    build_report,
    detect_query_intent,
    quality_report,
)


def group(**updates):
    value = {
        "page_id": "t_p_120_1176_p000003",
        "hybrid_v2_rank": 1,
        "exact_hit_count": 2,
        "semantic_group_count": 0,
        "category_labels": ["Table + parts + diagram review community"],
        "part_numbers": ["120-46137-001"],
        "bucket_counts": {"table_cell_normalized": 2},
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }
    value.update(updates)
    return value


def hybrid_report():
    return {
        "quality_status": "PASS",
        "query_results": [
            {
                "query_id": "part_120_46137_001",
                "query": "120-46137-001",
                "exact_hit_count": 2,
                "exact_hit_group_count": 1,
                "semantic_group_count": 0,
                "ranked_group_count": 1,
                "ranked_groups": [group()],
            }
        ],
    }


def test_detect_query_intent_for_part_number_and_revision():
    assert detect_query_intent("120-46137-001") == "exact_part_number_lookup"
    assert detect_query_intent("Revision 4") == "revision_lookup"


def test_retrieval_only_part_query_recommends_final_gate_or_review():
    record = build_critic_record(hybrid_report()["query_results"][0])
    assert record["critic_status"] == "retrieval_only_not_answer_ready"
    assert "no_answer_support_groups" in record["reason_codes"]
    assert record["can_answer_directly"] is False
    assert record["can_prove_claims"] is False


def test_answer_support_group_recommends_final_gate_attempt():
    qr = hybrid_report()["query_results"][0]
    qr = dict(qr)
    qr["ranked_groups"] = [group(bucket_counts={"source_text_evidence": 1}, citation_ids=["cite:test"])]
    record = build_critic_record(qr)
    assert record["critic_status"] == "strong_enough_for_final_gate_attempt"
    assert record["answer_support_group_count"] == 1


def test_dynamic_final_gate_authorized_requires_safe_claims():
    qr = hybrid_report()["query_results"][0]
    record = build_critic_record(qr, {"final_answer_allowed": True, "answer_status": "DYNAMIC_FINAL_GATE_APPROVED"})
    assert record["critic_status"] == "dynamic_final_gate_needs_audit"
    assert record["recommended_next_action"].startswith("audit_dynamic_final_gate_before_returning_answer")
    assert "dynamic_final_gate_missing_final_claims" in record["reason_codes"]


def test_dynamic_final_gate_authorized_wins_when_claim_counters_are_safe():
    qr = dict(hybrid_report()["query_results"][0])
    qr["ranked_groups"] = [group(bucket_counts={"verified_part_evidence": 1}, citation_ids=["cite:test"])]
    record = build_critic_record(
        qr,
        {
            "final_answer_allowed": True,
            "answer_status": "DYNAMIC_FINAL_GATE_APPROVED",
            "final_claim_count": 1,
            "uncited_final_claim_count": 0,
            "retrieval_only_final_claim_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
    )
    assert record["critic_status"] == "final_gate_already_authorized"
    assert record["recommended_next_action"] == "return_final_gate_answer"
    assert "dynamic_final_gate_allowed_and_claim_safe" in record["reason_codes"]


def test_dynamic_final_gate_approved_exact_query_without_exact_hits_gets_audit():
    qr = {
        "query_id": "ata",
        "query": "ATA 25-21-00",
        "exact_hit_group_count": 0,
        "semantic_group_count": 2,
        "ranked_group_count": 1,
        "ranked_groups": [group(exact_hit_count=0, semantic_group_count=1, bucket_counts={"source_evidence": 1})],
    }
    record = build_critic_record(
        qr,
        {
            "final_answer_allowed": True,
            "answer_status": "DYNAMIC_FINAL_GATE_APPROVED",
            "final_claim_count": 1,
            "uncited_final_claim_count": 0,
            "retrieval_only_final_claim_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
    )
    assert record["critic_status"] == "dynamic_final_gate_needs_audit"
    assert "dynamic_final_gate_exact_query_missing_exact_hits" in record["reason_codes"]
    assert record["dynamic_final_answer_safe_to_return"] is True
    assert record["dynamic_final_gate_retrieval_consistency_reasons"]


def test_final_gate_artifact_answer_is_exempt_from_retrieval_pattern_audit():
    qr = {
        "query_id": "rev",
        "query": "Which pages discuss manual revision history?",
        "exact_hit_group_count": 0,
        "semantic_group_count": 0,
        "ranked_group_count": 1,
        "ranked_groups": [group(exact_hit_count=0, semantic_group_count=0, bucket_counts={"source_evidence": 1})],
    }
    record = build_critic_record(
        qr,
        {
            "final_answer_allowed": True,
            "answer_status": "FINAL_GATE_ARTIFACT_ANSWER",
            "final_answer_text": "Already gated answer.",
            "final_claim_count": 1,
            "uncited_final_claim_count": 0,
            "retrieval_only_final_claim_count": 0,
            "source_truth_mutation_allowed_count": 0,
        },
    )
    assert record["critic_status"] == "final_gate_already_authorized"
    assert record["dynamic_final_gate_retrieval_consistency_reasons"] == []


def test_no_groups_abstains():
    record = build_critic_record({"query_id": "q", "query": "missing part", "ranked_groups": [], "ranked_group_count": 0})
    assert record["critic_status"] == "abstain_no_evidence"


def test_unsafe_group_blocked():
    qr = dict(hybrid_report()["query_results"][0])
    qr["ranked_groups"] = [group(source_truth_mutation_allowed=True)]
    record = build_critic_record(qr)
    assert record["critic_status"] == "unsafe_retrieval_blocked"
    assert record["unsafe_group_count"] == 1


def test_build_report_and_quality_pass():
    report = build_report(hybrid_v2_report=hybrid_report())
    q = quality_report(report, min_critic_records=1, min_queries=1)
    assert q["status"] == "PASS"
    assert q["summary"]["critic_record_count"] == 1
    assert q["summary"]["feedback_as_proof_count"] == 0


def test_build_report_counts_dynamic_gate_needs_audit():
    hybrid = hybrid_report()
    dynamic_gate = {
        "quality_status": "PASS",
        "query_results": [
            {
                "query": "120-46137-001",
                "final_answer_allowed": True,
                "answer_status": "DYNAMIC_FINAL_GATE_APPROVED",
            }
        ],
    }
    report = build_report(hybrid_v2_report=hybrid, dynamic_final_gate_report=dynamic_gate)
    assert report["summary"]["dynamic_final_gate_needs_audit_count"] == 1
    assert report["critic_records"][0]["critic_status"] == "dynamic_final_gate_needs_audit"
