from pathlib import Path

from tiff.trace_net_e2e_dynamic_query_tunnels_v3 import (
    READY_STATUS,
    build_dynamic_query_tunnels_report,
    classify_query_intent,
    query_terms,
    render_markdown,
    write_report_files,
)


def _write_json(path: Path, data: dict) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _artifact(path: Path, **summary) -> Path:
    _write_json(path, {"quality_status": "PASS", "status": "BUILT", "summary": summary})
    return path


def test_classify_query_intent_and_terms():
    assert classify_query_intent("Find part number 120-36834-509") == "covered_part_number"
    assert classify_query_intent("Where is manual reference 25-21-00 used?") == "manual_page_reference"
    assert classify_query_intent("Search table text MAINTENANCE MANUAL WITH") == "table_text"
    assert "120-36834-509" in query_terms("Find part number 120-36834-509")


def test_build_report_with_required_artifacts(tmp_path: Path):
    endpoint = _artifact(tmp_path / "endpoint.json", exact_search_document_count=1497)
    exact = _artifact(tmp_path / "exact.json", table_exact_search_document_count=1497)
    bridge = _artifact(tmp_path / "bridge.json", table_hybrid_bridge_record_count=1497)
    page_profiles = _artifact(tmp_path / "profiles.json", page_retrieval_profile_count=509)
    graph = _artifact(tmp_path / "graph.json", community_navigation_record_count=25)

    report = build_dynamic_query_tunnels_report(
        queries=[
            "Find part number 120-36834-509",
            "Where is manual reference 25-21-00 used?",
        ],
        dynamic_query_endpoint=endpoint,
        table_exact_search_adapter=exact,
        table_hybrid_retrieval_bridge=bridge,
        page_retrieval_profiles=page_profiles,
        community_navigation_metadata_bridge=graph,
        thresholds={
            "min_query_tunnel_plans": 2,
            "min_ready_query_tunnel_plans": 2,
            "min_total_tunnels": 6,
            "min_unique_tunnel_types": 3,
            "min_plans_with_table_tunnels": 2,
            "min_plans_with_graph_or_summary_tunnels": 1,
            "min_available_artifacts": 5,
        },
        require_no_answer_permission=True,
    )
    assert report["quality_status"] == "PASS"
    assert report["e2e_dynamic_query_tunnels_status"] == READY_STATUS
    assert report["summary"]["plans_with_table_tunnel_count"] == 2
    assert report["summary"]["answer_permission_count"] == 0


def test_missing_required_artifact_fails(tmp_path: Path):
    exact = _artifact(tmp_path / "exact.json", table_exact_search_document_count=1497)
    report = build_dynamic_query_tunnels_report(
        queries=["Find part number 120-36834-509"],
        table_exact_search_adapter=exact,
        thresholds={"min_query_tunnel_plans": 1},
    )
    assert report["quality_status"] == "FAIL"
    assert report["summary"]["required_missing_artifact_count"] >= 1


def test_write_report_files_and_markdown(tmp_path: Path):
    endpoint = _artifact(tmp_path / "endpoint.json", exact_search_document_count=1497)
    exact = _artifact(tmp_path / "exact.json", table_exact_search_document_count=1497)
    bridge = _artifact(tmp_path / "bridge.json", table_hybrid_bridge_record_count=1497)
    report = build_dynamic_query_tunnels_report(
        queries=["Find part number 120-36834-509"],
        dynamic_query_endpoint=endpoint,
        table_exact_search_adapter=exact,
        table_hybrid_retrieval_bridge=bridge,
        thresholds={
            "min_query_tunnel_plans": 1,
            "min_ready_query_tunnel_plans": 1,
            "min_total_tunnels": 2,
            "min_unique_tunnel_types": 2,
            "min_plans_with_table_tunnels": 1,
            "min_available_artifacts": 3,
        },
    )
    paths = write_report_files(report, tmp_path / "out")
    assert Path(paths["report_path"]).exists()
    assert Path(paths["plans_jsonl_path"]).exists()
    assert "Dynamic Query Tunnels" in render_markdown(report)
