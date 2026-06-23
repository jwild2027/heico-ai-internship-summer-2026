from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_e2e_dynamic_plan_executor_v18 import build_report, execute_plan, quality_check_report


def sample_plan(value="120-36833-501"):
    return {
        "query_plan_id": "query_plan_v17_0001",
        "user_query": f"Find part number {value}",
        "query_intent": "part_number",
        "required_source_truth_fields": ["covered_part_number", "ipl_part_number"],
        "subqueries": [{"target_value": value}],
    }


def sample_docs():
    return [
        {"page_id": "p1", "document_id": "d1", "field_name": "covered_part_number", "value": "120-36833-501"},
        {"page_id": "p2", "document_id": "d1", "field_name": "covered_part_number", "value": "120-36833-501"},
        {"page_id": "p3", "document_id": "d2", "field_name": "ipl_part_number", "value": "120-36833-501"},
        {"page_id": "p4", "document_id": "d2", "field_name": "ipl_text", "value": "MAINTENANCE MANUAL WITH"},
    ]


def test_execute_plan_returns_source_truth_and_graph_guidance():
    plan = sample_plan()
    page_to_comm = {"p1": "c1", "p2": "c1", "p3": "c2"}
    comm_to_pages = {"c1": ["p1", "p2"], "c2": ["p3"]}
    report = execute_plan(plan, sample_docs(), {}, page_to_comm, comm_to_pages, {}, top_k=2, high_degree_threshold=2)
    assert report["ready_for_live_context_pack"] is True
    assert report["source_truth_evidence_count"] == 2
    assert report["result_was_capped"] is True
    assert report["high_degree_node_detected"] is True
    assert report["graph_guidance_count"] >= 1
    assert all(g["authority"] == "guidance_only" for g in report["graph_guidance"])
    assert report["authority_contract"]["source_truth_evidence_required_for_final_claims"] is True


def test_build_report_and_quality(tmp_path: Path):
    planner = tmp_path / "planner.json"
    exact = tmp_path / "exact.json"
    leiden = tmp_path / "leiden.json"
    planner.write_text(json.dumps({"query_plans": [sample_plan(), sample_plan("120-36833-999")]}), encoding="utf-8")
    exact.write_text(json.dumps({"exact_search_documents": sample_docs()}), encoding="utf-8")
    leiden.write_text(json.dumps({"communities": [{"community_id": "c1", "page_ids": ["p1", "p2"]}, {"community_id": "c2", "page_ids": ["p3"]}]}), encoding="utf-8")
    report = build_report(query_planner=planner, table_exact_search_adapter=exact, leiden_communities=leiden, top_k=2, high_degree_threshold=2)
    assert report["query_plan_count"] == 2
    assert report["ready_execution_count"] == 1
    status, checks = quality_check_report(report, min_query_plans=2, min_ready_executions=1, min_source_truth_evidence=2, min_graph_guidance_records=1, min_capped_result_disclosures=1, require_no_answer_permission=True)
    assert status == "PASS", checks


def test_graph_and_summary_never_have_proof_authority(tmp_path: Path):
    planner = tmp_path / "planner.json"
    exact = tmp_path / "exact.json"
    summaries = tmp_path / "summaries.json"
    leiden = tmp_path / "leiden.json"
    planner.write_text(json.dumps({"query_plans": [sample_plan()]}), encoding="utf-8")
    exact.write_text(json.dumps({"exact_search_documents": sample_docs()}), encoding="utf-8")
    summaries.write_text(json.dumps({"records": [{"page_id": "p1", "summary": "Covered parts page."}]}), encoding="utf-8")
    leiden.write_text(json.dumps({"communities": [{"community_id": "c1", "page_ids": ["p1", "p2"]}]}), encoding="utf-8")
    report = build_report(query_planner=planner, table_exact_search_adapter=exact, page_context_v2=summaries, leiden_communities=leiden, top_k=1)
    execution = report["executions"][0]
    assert execution["summary_guidance_count"] == 1
    assert execution["summary_guidance"][0]["proof_authority"] is False
    assert execution["graph_guidance"][0]["proof_authority"] is False
    assert report["graph_proof_authority_violation_count"] == 0
    assert report["summary_proof_authority_violation_count"] == 0
