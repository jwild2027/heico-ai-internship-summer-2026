from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_e2e_dynamic_context_pack_v8 import (
    QualityThresholds,
    build_context_pack_report,
    normalize_text,
    write_report_files,
)


def sample_ranker():
    return {
        "quality_status": "PASS",
        "rank_plans": [
            {
                "rank_plan_id": "p1",
                "user_query": "Find part number 120-36834-509",
                "query_intent": "covered_part_number",
                "query_terms": ["120-36834-509"],
                "available_tunnels": [
                    "table_exact_search_tunnel",
                    "table_hybrid_bridge_tunnel",
                    "qdrant_page_profile_tunnel",
                    "page_summary_tunnel",
                    "graph_community_tunnel",
                    "graph_navigation_tunnel",
                    "route_metadata_tunnel",
                    "table_route_summary_tunnel",
                ],
                "ranked_evidence": [
                    {
                        "rank": 1,
                        "field_name": "covered_part_number",
                        "normalized_value": "120-36834-509",
                        "page_id": "t_p_120_1176_p000003",
                        "source_name": "table_exact_search_adapter",
                        "source_tunnel": "table_exact_search_tunnel",
                        "citation_ready": True,
                        "source_trace_ready": True,
                        "total_tunnel_score": 319,
                        "tunnel_contributions": {
                            "table_exact_search_tunnel": 240,
                            "table_hybrid_bridge_tunnel": 20,
                            "page_summary_tunnel": 10,
                            "graph_community_tunnel": 7,
                            "route_metadata_tunnel": 15,
                        },
                    }
                ],
                "answer_permission": False,
                "can_answer_directly": False,
                "can_prove_claims": False,
                "source_truth_mutation_allowed": False,
            }
        ],
        "summary": {"available_tunnels": ["table_exact_search_tunnel", "page_summary_tunnel"]},
    }


def test_normalize_text_repairs_known_spacing():
    assert normalize_text("MAINTENANCEMANUAL WITH") == "MAINTENANCE MANUAL WITH"


def test_build_context_pack_separates_evidence_guidance_and_rules():
    report = build_context_pack_report(
        dynamic_tunnel_ranker=sample_ranker(),
        page_context_v2={
            "quality_status": "PASS",
            "pages": [{"page_id": "t_p_120_1176_p000003", "summary": "Page summary guidance."}],
        },
        route_dispatch_manifest={
            "quality_status": "PASS",
            "route_records": [{"page_id": "t_p_120_1176_p000003", "primary_route": "table"}],
        },
        leiden_communities={
            "quality_status": "PASS",
            "communities": [
                {"community_id": "c1", "page_ids": ["t_p_120_1176_p000003"], "summary": "Graph community guidance."}
            ],
        },
        thresholds=QualityThresholds(
            min_context_packs=1,
            min_ready_context_packs=1,
            min_total_evidence_items=1,
            min_packs_with_evidence_box=1,
            min_packs_with_guidance_box=1,
            min_packs_with_rules_box=1,
            min_packs_with_graph_or_summary_guidance=1,
            require_no_answer_permission=True,
        ),
    )
    assert report["quality_status"] == "PASS"
    pack = report["context_packs"][0]
    assert pack["evidence_box"]["authority"] == "source_truth_evidence_only"
    assert pack["evidence_box"]["items"][0]["normalized_value"] == "120-36834-509"
    assert pack["guidance_box"]["authority"] == "guidance_only_not_source_truth"
    assert pack["guidance_box"]["contains_graph_or_summary_guidance"] is True
    assert pack["rules_box"]["graph_is_not_proof_authority"] is True
    assert pack["rules_box"]["summaries_are_not_source_truth"] is True
    assert pack["source_truth_mutation_allowed"] is False


def test_write_report_files(tmp_path: Path):
    report = build_context_pack_report(dynamic_tunnel_ranker=sample_ranker())
    paths = write_report_files(report, tmp_path)
    for path in paths.values():
        assert Path(path).exists()
    loaded = json.loads(Path(paths["report_path"]).read_text(encoding="utf-8"))
    assert loaded["schema_version"] == "v8"


def test_quality_fails_when_missing_evidence():
    report = build_context_pack_report(
        dynamic_tunnel_ranker={"quality_status": "PASS", "rank_plans": []},
        thresholds=QualityThresholds(min_context_packs=1, min_total_evidence_items=1),
    )
    assert report["quality_status"] == "FAIL"
