import json
from pathlib import Path

from tiff.trace_net_hybrid_retrieval_v3 import build_hybrid_retrieval_v3, build_from_paths


def _hybrid_v2_payload(*, unsafe=False):
    group = {
        "page_id": "t_p_120_1176_p000003",
        "source_page_ids": ["t_p_120_1176_p000003"],
        "citation_ids": ["cite:source_text:t_p_120_1176_p000003:abc"],
        "part_numbers": ["120-46137-001"],
        "hybrid_v2_score": 0.82,
        "exact_hits": [{"page_id": "t_p_120_1176_p000003", "score": 8.5}],
        "semantic_groups": [{"page_id": "t_p_120_1176_p000003", "score": 0.75}],
        "graph_path_resolved": True,
    }
    if unsafe:
        group["can_answer_directly"] = True
    return {
        "schema_version": "trace_net_hybrid_retrieval_v2",
        "quality_status": "PASS",
        "summary": {"quality_status": "PASS"},
        "query_results": [
            {
                "query_id": "part_120_46137_001",
                "query": "120-46137-001",
                "ranked_groups": [
                    group,
                    {
                        "page_id": "t_p_120_1176_p000340",
                        "source_page_ids": ["t_p_120_1176_p000340"],
                        "hybrid_v2_score": 0.55,
                        "semantic_groups": [{"page_id": "t_p_120_1176_p000340", "score": 0.5}],
                    },
                ],
            }
        ],
    }


def _planner_payload():
    return {
        "schema_version": "trace_net_corrective_retrieval_planner_v1",
        "quality_status": "PASS",
        "summary": {
            "quality_status": "PASS",
            "source_quality_statuses": {"qdrant_page_profile_quality": "PASS"},
        },
        "corrective_retrieval_records": [
            {
                "record_id": "corrective_retrieval::page_retrieval_large_eval_v2::t_p_120_1176_p000003::semantic_page_target_miss",
                "source_module": "page_retrieval_large_eval_v2",
                "issue_type": "semantic_page_target_miss",
                "severity": "HIGH",
                "recommended_actions": [
                    "rerank_with_graph_page_anchor",
                    "expand_graph_source_path",
                    "run_opensearch_exact_if_identifier_present",
                    "mark_result_audit_required_until_corrected",
                ],
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            },
            {
                "record_id": "corrective_retrieval::page_retrieval_large_eval_v2::t_p_120_1176_p000340::target_page_low_rank",
                "source_module": "page_retrieval_large_eval_v2",
                "issue_type": "target_page_low_rank",
                "severity": "MEDIUM",
                "recommended_actions": ["apply_graph_anchor_rerank", "retain_top_k_for_review"],
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            },
            {
                "record_id": "corrective_retrieval::opensearch_loader_smoke::exact_search_channel_available",
                "source_module": "opensearch_loader_smoke",
                "issue_type": "exact_search_channel_available",
                "severity": "INFO",
                "recommended_actions": ["use_opensearch_exact_for_identifiers"],
            },
            {
                "record_id": "corrective_retrieval::qdrant_page_profile_quality::semantic_search_channel_available",
                "source_module": "qdrant_page_profile_quality",
                "issue_type": "semantic_search_channel_available",
                "severity": "INFO",
                "recommended_actions": ["use_qdrant_bge_m3_for_semantic_candidates"],
            },
        ],
    }


def _graph_payload():
    return {
        "quality_status": "PASS",
        "summary": {"quality_status": "PASS"},
        "enriched_page_records": [{"page_id": "t_p_120_1176_p000003"}],
    }


def test_hybrid_v3_attaches_crag_actions_and_stays_retrieval_only():
    payload = build_hybrid_retrieval_v3(
        hybrid_v2=_hybrid_v2_payload(),
        corrective_planner=_planner_payload(),
        graph_enrichment=_graph_payload(),
        opensearch_loader_smoke={"quality_status": "PASS"},
        qdrant_page_profile_quality={"quality_status": "PASS"},
        min_queries=1,
        min_queries_with_results=1,
        min_groups=2,
        min_corrective_groups=2,
        min_review_routed_groups=2,
        require_hybrid_v2_quality_pass=True,
        require_corrective_planner_quality_pass=True,
        require_graph_enrichment_quality_pass=True,
        require_opensearch_loader_quality_pass=True,
        require_qdrant_quality_pass=True,
        require_no_answer_permission=True,
    )
    assert payload["quality_status"] == "PASS"
    assert payload["summary"]["corrective_group_count"] == 2
    assert payload["summary"]["review_routed_group_count"] == 2
    assert payload["summary"]["answer_permission_count"] == 0
    assert payload["summary"]["can_answer_directly_count"] == 0
    assert payload["summary"]["can_prove_claims_count"] == 0
    group = payload["query_results"][0]["ranked_groups"][0]
    assert group["retrieval_only"] is True
    assert group["can_answer_directly"] is False
    assert group["can_prove_claims"] is False
    assert "semantic_page_target_miss" in group["corrective_issue_types"]
    assert "run_opensearch_exact_if_identifier_present" in group["corrective_recommended_actions"]
    assert payload["channel_summary"]["exact_search_channel_available"] is True
    assert payload["channel_summary"]["semantic_search_channel_available"] is True


def test_hybrid_v3_fails_quality_for_unsafe_source_group():
    payload = build_hybrid_retrieval_v3(
        hybrid_v2=_hybrid_v2_payload(unsafe=True),
        corrective_planner=_planner_payload(),
        graph_enrichment=_graph_payload(),
        opensearch_loader_smoke={"quality_status": "PASS"},
        qdrant_page_profile_quality={"quality_status": "PASS"},
        max_unsafe_groups=0,
        require_no_answer_permission=True,
    )
    assert payload["quality_status"] == "FAIL"
    assert payload["summary"]["unsafe_group_count"] == 1
    # Output group remains safe even though the source group was flagged.
    group = payload["query_results"][0]["ranked_groups"][0]
    assert group["can_answer_directly"] is False
    assert group["source_group_unsafe_flag_count"] == 1


def test_hybrid_v3_build_from_paths_writes_artifacts(tmp_path):
    paths = {}
    for name, payload in {
        "hybrid_v2": _hybrid_v2_payload(),
        "planner": _planner_payload(),
        "graph": _graph_payload(),
        "opensearch": {"quality_status": "PASS"},
        "qdrant": {"quality_status": "PASS"},
    }.items():
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        paths[name] = path
    out_dir = tmp_path / "out"
    payload = build_from_paths(
        hybrid_v2_path=paths["hybrid_v2"],
        corrective_planner_path=paths["planner"],
        graph_enrichment_path=paths["graph"],
        opensearch_loader_smoke_path=paths["opensearch"],
        qdrant_page_profile_quality_path=paths["qdrant"],
        output_dir=out_dir,
        max_groups_per_query=12,
        min_queries=1,
        min_queries_with_results=1,
        min_groups=2,
        min_corrective_groups=2,
        min_review_routed_groups=2,
        max_unsafe_groups=0,
        require_hybrid_v2_quality_pass=True,
        require_corrective_planner_quality_pass=True,
        require_graph_enrichment_quality_pass=True,
        require_opensearch_loader_quality_pass=True,
        require_qdrant_quality_pass=True,
        require_no_answer_permission=True,
    )
    assert payload["quality_status"] == "PASS"
    assert (out_dir / "trace_net_hybrid_retrieval_v3.json").exists()
    assert (out_dir / "trace_net_hybrid_retrieval_v3_quality.json").exists()
    assert (out_dir / "trace_net_hybrid_retrieval_v3_results.jsonl").exists()
    assert (out_dir / "trace_net_hybrid_retrieval_v3_groups.jsonl").exists()
