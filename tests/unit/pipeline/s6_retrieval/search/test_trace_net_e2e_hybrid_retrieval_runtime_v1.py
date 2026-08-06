from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_e2e_hybrid_retrieval_runtime_v1 import (
    QualityThresholds,
    build_report,
    build_retrieval_group_for_query,
    build_from_paths,
    evaluate_quality,
)


def _query_input():
    return {
        "quality_status": "PASS",
        "query_records": [
            {
                "query_id": "q1",
                "user_query": "Find part number 120-36833-001",
                "query_intent": "covered_part_number",
                "requested_routes": ["table", "normal_text"],
                "retrieval_channels": ["table_exact_search", "table_hybrid_retrieval_bridge"],
                "query_terms": [{"term": "120-36833-001", "term_type": "part_number"}],
            },
            {
                "query_id": "q2",
                "user_query": "Where is manual reference 25-21-00 used?",
                "query_intent": "manual_page_reference",
                "requested_routes": ["table", "normal_text"],
                "retrieval_channels": ["table_exact_search", "table_hybrid_retrieval_bridge"],
                "query_terms": [{"term": "25-21-00", "term_type": "manual_page_reference"}],
            },
            {
                "query_id": "q3",
                "user_query": "What maintenance manual pages mention covered part numbers?",
                "query_intent": "covered_part_number",
                "requested_routes": ["table", "normal_text"],
                "retrieval_channels": ["table_hybrid_retrieval_bridge"],
                "query_terms": [{"term": "What maintenance manual pages mention covered part numbers?", "term_type": "free_text"}],
            },
        ],
    }


def _bridge():
    return {
        "quality_status": "PASS",
        "bridge_records": [
            {
                "bridge_record_id": "b1",
                "page_id": "t_p_120_1176_p000003",
                "field_name": "covered_part_number",
                "normalized_value": "120-36833-001",
                "routing_boost": 1.35,
            },
            {
                "bridge_record_id": "b2",
                "page_id": "t_p_120_1176_p000005",
                "field_name": "manual_page_reference",
                "normalized_value": "25-21-00",
                "routing_boost": 1.25,
            },
            {
                "bridge_record_id": "b3",
                "page_id": "t_p_120_1176_p000003",
                "field_name": "covered_part_number",
                "normalized_value": "120-36834-001",
                "routing_boost": 1.35,
            },
        ],
        "query_bridge_groups": [
            {
                "query": "120-36833-001",
                "match_count": 1,
                "hits": [
                    {
                        "page_id": "t_p_120_1176_p000003",
                        "field_name": "covered_part_number",
                        "normalized_value": "120-36833-001",
                        "routing_boost": 1.35,
                    }
                ],
            }
        ],
    }


def test_build_retrieval_group_scores_exact_part_number():
    group = build_retrieval_group_for_query(_query_input()["query_records"][0], _bridge()["bridge_records"], _bridge()["query_bridge_groups"], top_k=5)
    assert group["retrieval_status"] == "RETRIEVAL_MATCHED"
    assert group["hit_count"] >= 1
    assert group["hits"][0]["normalized_value"] == "120-36833-001"
    assert group["hits"][0]["answer_permission"] is False


def test_build_report_quality_passes():
    thresholds = QualityThresholds(
        min_source_query_records=3,
        min_source_bridge_records=3,
        min_retrieval_queries=3,
        min_successful_retrieval_queries=3,
        min_retrieval_groups=3,
        min_total_retrieval_hits=3,
        min_pages_with_retrieval_hits=2,
        min_field_count=2,
        require_source_query_input_quality_pass=True,
        require_source_bridge_quality_pass=True,
        require_no_answer_permission=True,
    )
    report = build_report(
        e2e_query_input=_query_input(),
        table_hybrid_retrieval_bridge=_bridge(),
        e2e_query_input_path="query.json",
        table_hybrid_retrieval_bridge_path="bridge.json",
        top_k=5,
        thresholds=thresholds,
    )
    assert report["quality_status"] == "PASS"
    assert report["summary"]["successful_retrieval_query_count"] == 3
    assert report["summary"]["answer_permission_count"] == 0
    assert report["runtime_contract"]["ready_for_context_pack"] is True


def test_free_text_intent_finds_field_records():
    group = build_retrieval_group_for_query(_query_input()["query_records"][2], _bridge()["bridge_records"], _bridge()["query_bridge_groups"], top_k=5)
    assert group["retrieval_status"] == "RETRIEVAL_MATCHED"
    assert any(hit["field_name"] == "covered_part_number" for hit in group["hits"])


def test_quality_fails_when_min_hits_too_high():
    thresholds = QualityThresholds(min_total_retrieval_hits=999)
    report = build_report(
        e2e_query_input=_query_input(),
        table_hybrid_retrieval_bridge=_bridge(),
        e2e_query_input_path="query.json",
        table_hybrid_retrieval_bridge_path="bridge.json",
        thresholds=thresholds,
    )
    status, checks = evaluate_quality(report, thresholds)
    assert status == "FAIL"
    assert any(c["name"] == "total_retrieval_hit_count" and not c["passed"] for c in checks)


def test_build_from_paths_writes_outputs(tmp_path: Path):
    qpath = tmp_path / "query.json"
    bpath = tmp_path / "bridge.json"
    out = tmp_path / "out"
    qpath.write_text(json.dumps(_query_input()), encoding="utf-8")
    bpath.write_text(json.dumps(_bridge()), encoding="utf-8")
    report = build_from_paths(
        e2e_query_input_path=qpath,
        table_hybrid_retrieval_bridge_path=bpath,
        output_dir=out,
        top_k=5,
        thresholds=QualityThresholds(min_successful_retrieval_queries=3, min_total_retrieval_hits=3),
    )
    assert report["quality_status"] == "PASS"
    assert (out / "trace_net_e2e_hybrid_retrieval_runtime_v1.json").exists()
    assert (out / "trace_net_e2e_hybrid_retrieval_groups_v1.jsonl").exists()
    assert (out / "trace_net_e2e_hybrid_retrieval_runtime_v1_inspect.md").exists()
