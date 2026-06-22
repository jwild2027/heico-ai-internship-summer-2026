from __future__ import annotations

import argparse
import json
from pathlib import Path

from tiff.trace_net_table_hybrid_retrieval_bridge_v1 import (
    QUALITY_FAIL,
    QUALITY_PASS,
    build_bridge_records,
    build_query_groups,
    build_table_hybrid_retrieval_bridge,
    check_quality_report,
)


def _args(**overrides):
    data = dict(
        top_k=10,
        min_source_exact_search_documents=3,
        min_source_successful_smoke_queries=2,
        min_bridge_records=3,
        min_pages_with_bridge_records=1,
        min_field_count=3,
        min_query_bridge_groups=2,
        min_successful_query_bridge_groups=2,
        min_covered_part_number_bridge_records=1,
        min_manual_page_reference_bridge_records=1,
        min_ipl_part_number_bridge_records=1,
        max_unsafe_records=0,
        max_answer_permission_count=0,
        max_source_truth_mutation_allowed=0,
        require_source_exact_search_adapter_quality_pass=True,
        require_source_exact_search_smoke_quality_pass=True,
        require_no_answer_permission=True,
    )
    data.update(overrides)
    return argparse.Namespace(**data)


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_build_bridge_records_keeps_retrieval_only_and_filters_unsafe():
    docs = [
        {"document_id": "d1", "page_id": "p1", "table_id": "t1", "field_name": "covered_part_number", "normalized_value": "120-1", "retrieval_only": True},
        {"document_id": "d2", "page_id": "p2", "table_id": "t2", "field_name": "manual_page_reference", "normalized_value": "25-21-00", "retrieval_only": True},
        {"document_id": "d3", "page_id": "p3", "table_id": "t3", "field_name": "ipl_part_number", "normalized_value": "ABC", "answer_permission": True},
    ]
    records = build_bridge_records(docs)
    assert len(records) == 2
    assert all(row["retrieval_only"] is True for row in records)
    assert all(row["answer_permission"] is False for row in records)
    assert records[0]["hybrid_retrieval_role"] == "ranking_signal_only"
    assert records[0]["routing_boost"] > 1.0


def test_build_query_groups_links_smoke_hits_to_bridge_records():
    docs = [
        {"document_id": "d1", "page_id": "p1", "table_id": "t1", "field_name": "covered_part_number", "normalized_value": "120-1", "retrieval_only": True},
        {"document_id": "d2", "page_id": "p2", "table_id": "t2", "field_name": "manual_page_reference", "normalized_value": "25-21-00", "retrieval_only": True},
    ]
    records = build_bridge_records(docs)
    smoke = [
        {"query": "120-1", "hits": [{"page_id": "p1", "field_name": "covered_part_number", "normalized_value": "120-1", "score": 185}]},
        {"query": "25-21-00", "hits": [{"page_id": "p2", "field_name": "manual_page_reference", "normalized_value": "25-21-00", "score": 180}]},
    ]
    groups = build_query_groups(smoke, records)
    assert len(groups) == 2
    assert groups[0]["match_count"] == 1
    assert groups[0]["hits"][0]["answer_permission"] is False
    assert groups[1]["page_ids"] == ["p2"]


def test_build_table_hybrid_retrieval_bridge_pass(tmp_path: Path):
    adapter_path = tmp_path / "adapter" / "trace_net_table_exact_search_adapter_v1.json"
    smoke_path = tmp_path / "smoke" / "trace_net_table_exact_search_smoke_v1.json"
    output_dir = tmp_path / "out"
    docs = [
        {"document_id": "d1", "page_id": "p1", "table_id": "t1", "field_name": "covered_part_number", "normalized_value": "120-1", "retrieval_only": True},
        {"document_id": "d2", "page_id": "p2", "table_id": "t2", "field_name": "manual_page_reference", "normalized_value": "25-21-00", "retrieval_only": True},
        {"document_id": "d3", "page_id": "p3", "table_id": "t3", "field_name": "ipl_part_number", "normalized_value": "PN-3", "retrieval_only": True},
        {"document_id": "d4", "page_id": "p3", "table_id": "t3", "field_name": "ipl_text", "normalized_value": "MAINT", "retrieval_only": True},
    ]
    smoke_results = [
        {"query": "120-1", "match_count": 1, "hits": [{"page_id": "p1", "field_name": "covered_part_number", "normalized_value": "120-1", "score": 185}]},
        {"query": "25-21-00", "match_count": 1, "hits": [{"page_id": "p2", "field_name": "manual_page_reference", "normalized_value": "25-21-00", "score": 185}]},
        {"query": "PN-3", "match_count": 1, "hits": [{"page_id": "p3", "field_name": "ipl_part_number", "normalized_value": "PN-3", "score": 185}]},
    ]
    _write_json(adapter_path, {"quality_status": "PASS", "summary": {"table_exact_search_document_count": 4}, "exact_search_documents": docs})
    _write_json(smoke_path, {"quality_status": "PASS", "summary": {"successful_smoke_query_count": 3, "total_match_count": 3}, "smoke_results": smoke_results})
    report = build_table_hybrid_retrieval_bridge(adapter_path, smoke_path, output_dir, _args(min_bridge_records=4, min_field_count=4, min_query_bridge_groups=3, min_successful_query_bridge_groups=3))
    assert report["quality_status"] == QUALITY_PASS
    assert report["summary"]["table_hybrid_bridge_record_count"] == 4
    assert report["summary"]["query_bridge_group_count"] == 3
    assert (output_dir / "trace_net_table_hybrid_retrieval_bridge_records_v1.jsonl").exists()
    assert (output_dir / "trace_net_table_hybrid_retrieval_bridge_v1_inspect.md").exists()


def test_quality_report_fails_on_answer_permission():
    report = {
        "status": "TABLE_HYBRID_RETRIEVAL_BRIDGE_BUILT",
        "summary": {
            "source_exact_search_adapter_quality_pass": True,
            "source_exact_search_smoke_quality_pass": True,
            "source_exact_search_document_count": 3,
            "source_successful_smoke_query_count": 2,
            "table_hybrid_bridge_record_count": 3,
            "page_with_bridge_record_count": 1,
            "field_count": 3,
            "query_bridge_group_count": 2,
            "successful_query_bridge_group_count": 2,
            "field_counts": {"covered_part_number": 1, "manual_page_reference": 1, "ipl_part_number": 1},
            "unsafe_bridge_record_count": 0,
            "answer_permission_count": 1,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
            "opensearch_upload_attempt_count": 0,
        },
    }
    quality = check_quality_report(report, _args())
    assert quality["quality_status"] == QUALITY_FAIL
    assert any((not c["passed"]) and c["name"] == "answer_permission_count" for c in quality["quality_checks"])
