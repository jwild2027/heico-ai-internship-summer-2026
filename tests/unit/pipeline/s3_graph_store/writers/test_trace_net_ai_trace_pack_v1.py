from __future__ import annotations

from tiff.trace_net_ai_trace_pack_v1 import build_trace_packs, check_trace_pack_quality, TracePackThresholds


def _payloads():
    graph_api = {"quality_status": "PASS", "summary": {"route_record_count": 7}}
    enrichment = {
        "quality_status": "PASS",
        "enriched_query_records": [
            {
                "query_type": "part_lookup",
                "plan_id": "part_source_check_v1",
                "input": {"part_number": "120-46137-001"},
                "original_graph_page_count": 1,
                "enriched_page_count": 2,
                "source_resolved_page_count": 2,
                "pages": [
                    {
                        "page_id": "t_p_120_1176_p000340",
                        "channels": ["organization_graph", "opensearch_exact"],
                        "source_resolved": True,
                        "dublin_core_source_identity": {"page_id": "t_p_120_1176_p000340"},
                        "leiden_navigation_hints": [{"community_id": "c1", "retrieval_only": True}],
                        "evidence_records": [{"channel": "opensearch_exact", "document_type": "embedding_candidate"}],
                    },
                    {
                        "page_id": "t_p_120_1176_p000339",
                        "channels": ["opensearch_exact", "claim_evidence_entailment"],
                        "source_resolved": True,
                        "dublin_core_source_identity": {"page_id": "t_p_120_1176_p000339"},
                        "evidence_records": [
                            {
                                "channel": "claim_evidence_entailment",
                                "claim_id": "claim_0003",
                                "human_review_escalation_recommended": True,
                                "page_alignment_status": "PAGE_MISMATCH_REVIEW",
                            }
                        ],
                    },
                ],
            }
        ],
    }
    hybrid = {
        "quality_status": "PASS",
        "query_results": [
            {
                "query_id": "part_120_46137_001",
                "query": "120-46137-001",
                "ranked_groups": [
                    {"hybrid_v2_rank": 1, "page_id": "t_p_120_1176_p000340", "hybrid_v2_score": 0.4, "exact_hit_count": 2, "semantic_group_count": 0, "part_numbers": ["120-46137-001"]}
                ],
            }
        ],
    }
    dynamic = {"quality_status": "PASS", "summary": {"final_answer_allowed_count": 1, "dynamic_final_gate_approved_count": 1, "blocked_claim_count": 0}}
    retrieval = {"quality_status": "PASS", "critic_records": [{"query_id": "part_120_46137_001", "query": "120-46137-001", "critic_status": "final_gate_already_authorized"}]}
    suff = {"quality_status": "PASS", "sufficiency_records": [{"query_id": "part_120_46137_001", "status": "sufficient"}]}
    answer = {"quality_status": "PASS", "records": [{"query_id": "part_120_46137_001", "status": "claims_safe"}]}
    entail = {
        "quality_status": "PASS",
        "entailment_records": [
            {
                "query_id": "part_120_46137_001",
                "claim_id": "claim_0001",
                "claim_text": "Page 340 supports part 120-46137-001.",
                "page_ids": ["t_p_120_1176_p000340"],
                "entailment_status": "SUPPORTED_BY_CITATION_EVIDENCE",
                "best_evidence_span": {"page_ids": ["t_p_120_1176_p000340"], "citation_ids": ["c1"]},
            },
            {
                "query_id": "part_120_46137_001",
                "claim_id": "claim_0002",
                "claim_text": "Page 339 supports part 120-46137-001.",
                "page_ids": ["t_p_120_1176_p000339"],
                "entailment_status": "PARTIALLY_SUPPORTED_NEEDS_REVIEW",
                "human_review_escalation_recommended": True,
                "best_evidence_span": {"page_ids": ["t_p_120_1176_p000003"], "citation_ids": ["c2"]},
            },
        ],
    }
    dublin = {"quality_status": "PASS", "summary": {"pages_with_source_package_entry_count": 509}}
    leiden = {"quality_status": "PASS", "summary": {"retrieval_navigation_hint_count": 221, "page_navigation_hint_count": 506}}
    return graph_api, enrichment, hybrid, dynamic, retrieval, suff, answer, entail, dublin, leiden


def test_build_trace_packs_merges_graph_retrieval_critics_and_entailment():
    graph_api, enrichment, hybrid, dynamic, retrieval, suff, answer, entail, dublin, leiden = _payloads()
    report = build_trace_packs(
        graph_query_api_v1_1=graph_api,
        graph_query_evidence_enrichment=enrichment,
        hybrid_v2=hybrid,
        dynamic_final_gate=dynamic,
        retrieval_critic=retrieval,
        evidence_sufficiency_critic=suff,
        answer_claim_critic=answer,
        claim_evidence_entailment=entail,
        dublin_core_source_package_extension=dublin,
        leiden_navigation_metadata_bridge=leiden,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["trace_pack_count"] == 1
    pack = report["trace_pack_records"][0]
    assert pack["query_id"] == "part_120_46137_001"
    assert pack["graph_trace_summary"]["enriched_page_count"] == 2
    assert pack["retrieval_summary"]["exact_hit_group_count"] == 1
    assert pack["claim_evidence_summary"]["human_review_escalation_count"] == 1
    assert pack["can_answer_directly"] is False
    assert pack["can_prove_claims"] is False


def test_quality_checker_enforces_no_answer_permission():
    graph_api, enrichment, hybrid, dynamic, retrieval, suff, answer, entail, dublin, leiden = _payloads()
    report = build_trace_packs(
        graph_query_api_v1_1=graph_api,
        graph_query_evidence_enrichment=enrichment,
        hybrid_v2=hybrid,
        dynamic_final_gate=dynamic,
        retrieval_critic=retrieval,
        evidence_sufficiency_critic=suff,
        answer_claim_critic=answer,
        claim_evidence_entailment=entail,
        dublin_core_source_package_extension=dublin,
        leiden_navigation_metadata_bridge=leiden,
    )
    quality = check_trace_pack_quality(
        report,
        TracePackThresholds(
            min_trace_packs=1,
            min_trace_packs_with_graph_context=1,
            min_trace_packs_with_dublin_core_identity=1,
            min_trace_packs_with_claim_entailment=1,
            require_graph_api_quality_pass=True,
            require_enrichment_quality_pass=True,
            require_hybrid_v2_quality_pass=True,
            require_dynamic_final_gate_quality_pass=True,
            require_claim_entailment_quality_pass=True,
            require_no_answer_permission=True,
        ),
    )
    assert quality["quality_status"] == "PASS"
