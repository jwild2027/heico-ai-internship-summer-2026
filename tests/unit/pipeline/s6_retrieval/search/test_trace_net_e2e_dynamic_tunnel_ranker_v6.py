import json
from pathlib import Path


def sample_exact_rows():
    return [
        {"page_id": "t_p_120_1176_p000003", "field_name": "covered_part_number", "normalized_value": "120-36834-509"},
        {"page_id": "t_p_120_1176_p000003", "field_name": "covered_part_number", "normalized_value": "120-36833-001"},
        {"page_id": "t_p_120_1176_p000027", "field_name": "ipl_text", "normalized_value": "MAINTENANCEMANUAL WITH"},
    ]


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_ranker_boosts_exact_part_and_uses_graph_summary_contributions():
    from tiff.trace_net_e2e_dynamic_tunnel_ranker_v6 import rank_hits_for_query

    plan, hits = rank_hits_for_query(
        "Find part number 120-36834-509",
        sample_exact_rows(),
        [],
        [
            "table_exact_search_tunnel",
            "table_hybrid_bridge_tunnel",
            "route_metadata_tunnel",
            "qdrant_page_profile_tunnel",
            "page_summary_tunnel",
            "graph_community_tunnel",
            "graph_navigation_tunnel",
            "table_route_summary_tunnel",
        ],
        page_profile_rows=[{"page_id": "t_p_120_1176_p000003"}],
        page_context_rows=[{"page_id": "t_p_120_1176_p000003"}],
        graph_rows=[{"page_id": "t_p_120_1176_p000003"}],
    )
    assert plan["ranker_status"] == "DYNAMIC_TUNNEL_RANKING_READY"
    assert hits[0].normalized_value == "120-36834-509"
    assert "page_summary_tunnel" in hits[0].tunnel_contributions
    assert "graph_community_tunnel" in hits[0].tunnel_contributions
    assert "table_exact_search_tunnel" in hits[0].tunnel_contributions


def test_ranker_normalizes_table_text_spacing():
    from tiff.trace_net_e2e_dynamic_tunnel_ranker_v6 import clean_value

    assert clean_value("MAINTENANCEMANUAL WITH") == "MAINTENANCE MANUAL WITH"


def test_build_ranker_report_passes(tmp_path):
    from tiff.trace_net_e2e_dynamic_tunnel_ranker_v6 import build_ranker_report

    exact = tmp_path / "exact.json"
    bridge = tmp_path / "bridge.json"
    endpoint = tmp_path / "endpoint.json"
    tunnels = tmp_path / "tunnels.json"
    profiles = tmp_path / "profiles.json"
    page_context = tmp_path / "context.json"
    graph = tmp_path / "graph.json"
    nav = tmp_path / "nav.json"
    route = tmp_path / "route.json"
    table_summary = tmp_path / "table_summary.json"

    write_json(exact, {"quality_status": "PASS", "exact_search_documents": sample_exact_rows()})
    write_json(bridge, {"quality_status": "PASS", "table_hybrid_bridge_records": []})
    write_json(endpoint, {"quality_status": "PASS", "status": "READY"})
    write_json(tunnels, {"quality_status": "PASS", "summary": {"unique_tunnel_types": ["table_exact_search_tunnel", "table_hybrid_bridge_tunnel", "page_summary_tunnel", "graph_community_tunnel", "route_metadata_tunnel"]}})
    write_json(profiles, {"records": [{"page_id": "t_p_120_1176_p000003"}]})
    write_json(page_context, {"records": [{"page_id": "t_p_120_1176_p000003"}]})
    write_json(graph, {"records": [{"page_id": "t_p_120_1176_p000003"}]})
    write_json(nav, {"records": [{"page_id": "t_p_120_1176_p000003"}]})
    write_json(route, {"records": [{"page_id": "t_p_120_1176_p000003"}]})
    write_json(table_summary, {"records": [{"page_id": "t_p_120_1176_p000003"}]})

    report = build_ranker_report(
        dynamic_query_endpoint=endpoint,
        dynamic_query_tunnels=tunnels,
        table_exact_search_adapter=exact,
        table_hybrid_retrieval_bridge=bridge,
        page_retrieval_profiles=profiles,
        page_context_v2=page_context,
        leiden_communities=graph,
        community_navigation_metadata_bridge=nav,
        route_dispatch_manifest=route,
        table_route_retrieval_handoff_summary=table_summary,
        queries=["Find part number 120-36834-509"],
        min_rank_plans=1,
        min_ready_rank_plans=1,
        min_total_ranked_evidence=1,
        min_unique_contribution_tunnels=4,
        min_plans_with_graph_or_summary_contribution=1,
        min_plans_with_table_contribution=1,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["plans_with_graph_or_summary_contribution_count"] == 1


def test_write_report_files(tmp_path):
    from tiff.trace_net_e2e_dynamic_tunnel_ranker_v6 import write_report_files

    report = {"quality_status": "PASS", "summary": {}, "rank_records": [], "rank_plans": [], "quality_checks": []}
    paths = write_report_files(report, tmp_path)
    assert paths["report_path"].exists()
    assert paths["records_jsonl_path"].exists()
    assert paths["inspect_md_path"].exists()
