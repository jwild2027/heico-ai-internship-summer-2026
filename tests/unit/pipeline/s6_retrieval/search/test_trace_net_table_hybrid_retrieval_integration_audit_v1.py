from __future__ import annotations

import argparse
import json
from pathlib import Path

from tiff.trace_net_table_hybrid_retrieval_integration_audit_v1 import (
    QUALITY_FAIL,
    QUALITY_PASS,
    build_audit_records,
    build_table_hybrid_retrieval_integration_audit,
    check_quality_report,
)


def _args(**overrides):
    data = dict(
        min_source_bridge_records=3,
        min_source_query_bridge_groups=2,
        min_integration_audit_records=5,
        min_ranking_available_bridge_records=3,
        min_pages_with_ranking_signals=1,
        min_field_count=3,
        min_successful_query_bridge_groups=2,
        min_covered_part_number_ranking_signals=1,
        min_manual_page_reference_ranking_signals=1,
        min_ipl_part_number_ranking_signals=1,
        max_schema_missing_required_key_records=0,
        max_unsafe_records=0,
        max_answer_permission_count=0,
        max_source_truth_mutation_allowed=0,
        require_source_bridge_quality_pass=True,
        require_no_answer_permission=True,
    )
    data.update(overrides)
    return argparse.Namespace(**data)


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _bridge_record(page, field, value):
    return {
        "bridge_record_id": f"bridge::{page}::{field}::{value}",
        "page_id": page,
        "field_name": field,
        "normalized_value": value,
        "retrieval_channel": "table_exact_search",
        "hybrid_retrieval_role": "ranking_signal_only",
        "routing_boost": 1.25,
        "retrieval_only": True,
        "answer_permission": False,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
    }


def test_build_audit_records_marks_safe_ranking_records_available():
    records = [
        _bridge_record("p1", "covered_part_number", "120-1"),
        _bridge_record("p2", "manual_page_reference", "25-21-00"),
    ]
    groups = [
        {
            "query": "120-1",
            "match_count": 1,
            "hits": [{"page_id": "p1", "field_name": "covered_part_number", "normalized_value": "120-1", "answer_permission": False, "can_answer_directly": False, "can_prove_claims": False, "source_truth_mutation_allowed": False}],
            "retrieval_only": True,
            "answer_permission": False,
            "can_answer_directly": False,
            "can_prove_claims": False,
            "source_truth_mutation_allowed": False,
        }
    ]
    audit = build_audit_records(records, groups)
    assert len(audit) == 3
    assert audit[0]["ranking_signal_available"] is True
    assert audit[0]["answer_permission"] is False
    assert audit[-1]["audit_subject_type"] == "query_bridge_group"
    assert audit[-1]["ranking_signal_available"] is True


def test_build_audit_records_detects_missing_schema():
    bad = {"page_id": "p1", "field_name": "covered_part_number", "normalized_value": "120-1"}
    audit = build_audit_records([bad], [])
    assert audit[0]["schema_complete"] is False
    assert "bridge_record_id" in audit[0]["missing_required_keys"]
    assert audit[0]["ranking_signal_available"] is False


def test_build_table_hybrid_retrieval_integration_audit_pass(tmp_path: Path):
    bridge_path = tmp_path / "bridge" / "trace_net_table_hybrid_retrieval_bridge_v1.json"
    output_dir = tmp_path / "out"
    records = [
        _bridge_record("p1", "covered_part_number", "120-1"),
        _bridge_record("p2", "manual_page_reference", "25-21-00"),
        _bridge_record("p3", "ipl_part_number", "PN-3"),
        _bridge_record("p4", "ipl_text", "MAINT"),
    ]
    groups = [
        {"query": "120-1", "match_count": 1, "page_ids": ["p1"], "field_names": ["covered_part_number"], "hits": [{"page_id": "p1", "field_name": "covered_part_number", "normalized_value": "120-1", "answer_permission": False, "can_answer_directly": False, "can_prove_claims": False, "source_truth_mutation_allowed": False}], "retrieval_only": True, "answer_permission": False, "can_answer_directly": False, "can_prove_claims": False, "source_truth_mutation_allowed": False},
        {"query": "25-21-00", "match_count": 1, "page_ids": ["p2"], "field_names": ["manual_page_reference"], "hits": [{"page_id": "p2", "field_name": "manual_page_reference", "normalized_value": "25-21-00", "answer_permission": False, "can_answer_directly": False, "can_prove_claims": False, "source_truth_mutation_allowed": False}], "retrieval_only": True, "answer_permission": False, "can_answer_directly": False, "can_prove_claims": False, "source_truth_mutation_allowed": False},
    ]
    _write_json(
        bridge_path,
        {
            "quality_status": "PASS",
            "summary": {"table_hybrid_bridge_record_count": 4, "successful_query_bridge_group_count": 2},
            "bridge_records": records,
            "query_bridge_groups": groups,
        },
    )
    report = build_table_hybrid_retrieval_integration_audit(bridge_path, output_dir, _args(min_source_bridge_records=4, min_integration_audit_records=6, min_ranking_available_bridge_records=4, min_field_count=4))
    assert report["quality_status"] == QUALITY_PASS
    assert report["summary"]["ranking_available_bridge_record_count"] == 4
    assert report["summary"]["successful_query_bridge_group_count"] == 2
    assert (output_dir / "trace_net_table_hybrid_retrieval_integration_audit_records_v1.jsonl").exists()
    assert (output_dir / "trace_net_table_hybrid_retrieval_integration_audit_v1_inspect.md").exists()


def test_quality_report_fails_on_answer_permission():
    report = {
        "status": "TABLE_HYBRID_RETRIEVAL_INTEGRATION_AUDIT_BUILT",
        "summary": {
            "source_bridge_quality_pass": True,
            "source_bridge_record_count": 3,
            "source_query_bridge_group_count": 2,
            "integration_audit_record_count": 5,
            "ranking_available_bridge_record_count": 3,
            "page_with_ranking_signal_count": 1,
            "field_count": 3,
            "successful_query_bridge_group_count": 2,
            "field_counts": {"covered_part_number": 1, "manual_page_reference": 1, "ipl_part_number": 1},
            "schema_missing_required_key_record_count": 0,
            "unsafe_integration_audit_record_count": 0,
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
