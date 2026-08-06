from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_e2e_query_planning_routing_v1 import (
    READY_STATUS,
    QualityThresholds,
    build_query_planning_routing,
    build_report,
    evaluate_quality,
)


def _query_input(tmp_path: Path) -> Path:
    data = {
        "quality_status": "PASS",
        "query_records": [
            {
                "query_id": "q1",
                "user_query": "Find part number 120-36833-001",
                "normalized_query": "find part number 120-36833-001",
                "query_intent": "covered_part_number",
                "requested_routes": ["table", "normal_text"],
                "retrieval_channels": ["table_exact_search", "table_hybrid_retrieval_bridge", "qdrant_page_profiles", "graph_source_trace"],
                "query_terms": [{"term": "120-36833-001", "term_type": "part_number"}],
                "safety_contract": {"answer_permission": False},
            },
            {
                "query_id": "q2",
                "user_query": "Find IPL item 130",
                "normalized_query": "find ipl item 130",
                "query_intent": "ipl_figure_item_or_quantity",
                "requested_routes": ["table", "image_visual"],
                "retrieval_channels": ["table_exact_search", "table_hybrid_retrieval_bridge", "graph_source_trace"],
                "query_terms": [{"term": "130", "term_type": "numeric_token"}],
                "safety_contract": {"answer_permission": False},
            },
        ],
    }
    p = tmp_path / "query_input.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _summary(tmp_path: Path) -> Path:
    data = {
        "quality_status": "PASS",
        "community_records": [
            {
                "community_id": "c1",
                "community_label": "covered part number table pages",
                "retrieval_hints": ["120-36833-001", "covered_part_number", "part number"],
                "page_ids": ["t_p_120_1176_p000003"],
                "summary": "Graph community that links covered part numbers to source table pages.",
            },
            {
                "community_id": "c2",
                "community_label": "IPL visual item pages",
                "retrieval_hints": ["130", "IPL", "figure item"],
                "page_ids": ["t_p_120_1176_p000027"],
                "summary": "Summary tunnel for IPL item and visual callout lookup.",
            },
        ],
    }
    p = tmp_path / "graph_summary.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_build_report_adds_graph_and_summary_tunnels(tmp_path: Path) -> None:
    query_path = _query_input(tmp_path)
    summary_path = _summary(tmp_path)
    report = build_query_planning_routing(
        e2e_query_input_path=query_path,
        output_dir=tmp_path / "out",
        summary_artifact_paths=[summary_path],
        thresholds=QualityThresholds(
            min_source_query_records=2,
            min_route_plans=2,
            min_routeable_plans=2,
            min_plans_with_graph_tunnels=2,
            min_plans_with_summary_tunnels=2,
            min_plans_with_table_tunnels=2,
            min_total_tunnels=6,
            min_unique_tunnel_types=3,
            min_planned_retrieval_steps=6,
            require_source_query_input_quality_pass=True,
            require_no_answer_permission=True,
        ),
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["e2e_query_planning_routing_status"] == READY_STATUS
    assert report["summary"]["plans_with_graph_tunnel_count"] == 2
    assert report["summary"]["plans_with_summary_tunnel_count"] == 2
    assert report["summary"]["plans_with_table_tunnel_count"] == 2
    assert report["summary"]["answer_permission_count"] == 0
    first_record = report["query_records"][0]
    assert "graph_summary_tunnels" in first_record["retrieval_channels"]
    assert "query_routing_plan" in first_record
    assert (tmp_path / "out" / "trace_net_e2e_query_planning_routing_v1.json").exists()


def test_report_still_builds_with_missing_optional_summary(tmp_path: Path) -> None:
    report = build_query_planning_routing(
        e2e_query_input_path=_query_input(tmp_path),
        output_dir=tmp_path / "out",
        summary_artifact_paths=[tmp_path / "missing.json"],
        allow_missing_summary_artifacts=True,
        thresholds=QualityThresholds(
            min_source_query_records=2,
            min_route_plans=2,
            min_routeable_plans=2,
            min_plans_with_graph_tunnels=2,
            min_plans_with_summary_tunnels=1,
            min_plans_with_table_tunnels=2,
            min_total_tunnels=5,
            min_unique_tunnel_types=3,
            min_planned_retrieval_steps=5,
            require_source_query_input_quality_pass=True,
            require_no_answer_permission=True,
        ),
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["loaded_summary_artifact_count"] == 0


def test_evaluate_quality_fails_thresholds(tmp_path: Path) -> None:
    query_path = _query_input(tmp_path)
    data = json.loads(query_path.read_text(encoding="utf-8"))
    report = build_report(e2e_query_input=data, e2e_query_input_path=query_path)
    status, checks = evaluate_quality(
        report,
        QualityThresholds(
            min_source_query_records=99,
            min_route_plans=99,
            min_routeable_plans=99,
            min_plans_with_graph_tunnels=99,
            min_plans_with_summary_tunnels=99,
            min_plans_with_table_tunnels=99,
            min_total_tunnels=99,
            min_unique_tunnel_types=99,
            min_planned_retrieval_steps=99,
        ),
    )
    assert status == "FAIL"
    assert any(not check["passed"] for check in checks)
