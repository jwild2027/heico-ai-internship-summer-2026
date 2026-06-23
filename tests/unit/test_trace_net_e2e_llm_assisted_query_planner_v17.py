from __future__ import annotations

from pathlib import Path


def test_detects_core_query_intents():
    from tiff.trace_net_e2e_llm_assisted_query_planner_v17 import detect_query_intent

    assert detect_query_intent("Find part number 120-36834-509")[0] == "part_number"
    assert detect_query_intent("What maintenance manual pages mention covered part numbers?")[0] == "covered_part_number"
    assert detect_query_intent("Where is manual reference 25-21-00 used?")[0] == "manual_page_reference"
    assert detect_query_intent("Search table text MAINTENANCE MANUAL WITH")[0] == "table_text"
    assert detect_query_intent("Find IPL item 130")[0] == "ipl_item"
    assert detect_query_intent("How does manual reference 25-21-00 connect to IPL table pages?")[0] == "relationship_or_synthesis"


def test_build_plan_uses_v2_summaries_and_leiden_as_guidance_only():
    from tiff.trace_net_e2e_llm_assisted_query_planner_v17 import build_query_plan

    artifact_summary = {
        "page_context_v2_available": True,
        "page_context_v2_record_count": 509,
        "leiden_communities_available": True,
        "leiden_community_record_count": 229,
        "community_navigation_available": True,
        "community_navigation_record_count": 229,
        "route_dispatch_manifest_available": True,
        "route_dispatch_record_count": 509,
    }
    plan = build_query_plan("query_plan_v17_test", "Find part number 120-36834-509", artifact_summary)
    assert plan["validation"]["validated"] is True
    assert "page_summary_tunnel" in plan["guidance_tunnels"]
    assert "graph_community_tunnel" in plan["guidance_tunnels"]
    assert plan["tunnel_policy"]["summary_authority"] == "guidance_only"
    assert plan["tunnel_policy"]["graph_authority"] == "guidance_only"
    assert plan["tunnel_policy"]["proof_authority"] == "source_truth_evidence_only"
    assert plan["safety_contract"]["answer_permission"] is False


def test_relationship_plan_has_graph_expansion_but_no_graph_proof():
    from tiff.trace_net_e2e_llm_assisted_query_planner_v17 import build_query_plan

    plan = build_query_plan("query_plan_v17_rel", "How are covered part numbers connected to IPL table pages?", {})
    assert plan["query_intent"] == "relationship_or_synthesis"
    assert any(s["subquery_type"] == "graph_guided_related_page_expansion" for s in plan["subqueries"])
    assert plan["tunnel_policy"]["leiden_communities_allowed"] is True
    assert plan["tunnel_policy"]["graph_authority"] == "guidance_only"
    assert plan["validation"]["validation_checks"]["graph_and_summary_guidance_only"] is True


def test_invalid_tunnel_is_rejected():
    from tiff.trace_net_e2e_llm_assisted_query_planner_v17 import validate_query_plan

    plan = {
        "primary_tunnels": ["made_up_tunnel"],
        "secondary_tunnels": [],
        "guidance_tunnels": ["page_summary_tunnel", "graph_community_tunnel"],
        "required_source_truth_fields": ["covered_part_number"],
        "tunnel_policy": {
            "proof_authority": "source_truth_evidence_only",
            "summary_authority": "guidance_only",
            "graph_authority": "guidance_only",
        },
        "safety_contract": {"answer_permission": False, "source_truth_mutation_allowed": False},
    }
    validation = validate_query_plan(plan)
    assert validation["validated"] is False
    assert validation["invalid_tunnel_count"] == 1


def test_report_quality_passes_with_sample_artifacts(tmp_path: Path):
    from tiff.trace_net_e2e_llm_assisted_query_planner_v17 import QualityThresholds, build_report, evaluate_quality, write_report_files

    live = {"probes": [{"user_query": "Find part number 120-36834-509"}]}
    page_context = {"pages": [{"page_id": "p1"}] * 5}
    leiden = {"communities": [{"community_id": "c1"}] * 3}
    nav = {"records": [{"community_id": "c1"}]}
    route = {"records": [{"page_id": "p1", "route": "table"}]}
    exact = {"exact_search_documents": [{"field_name": "covered_part_number", "normalized_value": "120-36834-509"}] * 10}
    report = build_report(
        live_dynamic_fallback=live,
        page_context_v2=page_context,
        leiden_communities=leiden,
        community_navigation_metadata_bridge=nav,
        route_dispatch_manifest=route,
        table_exact_search_adapter=exact,
        min_query_plans=5,
    )
    quality = evaluate_quality(report, QualityThresholds(require_no_answer_permission=True))
    assert quality["quality_status"] == "PASS"
    paths = write_report_files(report, tmp_path)
    assert Path(paths["report_path"]).exists()
    assert Path(paths["plans_jsonl_path"]).exists()
    assert Path(paths["inspect_md_path"]).exists()


def test_scalability_contract_prevents_raw_5tb_scans():
    from tiff.trace_net_e2e_llm_assisted_query_planner_v17 import build_query_plan

    plan = build_query_plan("query_plan_v17_scale", "Explain how these manual pages are related", {})
    assert plan["scalability_contract"]["raw_corpus_scan_at_query_time"] is False
    assert plan["scalability_contract"]["graph_built_offline"] is True
    assert plan["scalability_contract"]["llm_reads_entire_graph"] is False
    assert plan["scalability_contract"]["llm_reads_context_pack_only"] is True
