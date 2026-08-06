from __future__ import annotations

import argparse
import json
from pathlib import Path

from tiff.trace_net_table_exact_search_adapter_v1 import (
    DEFAULT_INDEX_NAME,
    QUALITY_FAIL,
    QUALITY_PASS,
    build_table_exact_search_adapter,
    check_quality_report,
    load_evidence_documents,
    make_exact_search_document,
    make_opensearch_mapping,
)


def _args(**overrides):
    data = dict(
        min_source_evidence_documents=3,
        min_exact_search_documents=3,
        min_pages_with_exact_search_documents=1,
        min_field_count=3,
        min_covered_part_number_documents=1,
        min_manual_page_reference_documents=1,
        min_ipl_part_number_documents=1,
        max_unsafe_records=0,
        max_answer_permission_count=0,
        max_source_truth_mutation_allowed=0,
        require_source_evidence_package_quality_pass=True,
        require_no_answer_permission=True,
        index_name=DEFAULT_INDEX_NAME,
    )
    data.update(overrides)
    return argparse.Namespace(**data)


def _evidence_package(path: Path) -> Path:
    payload = {
        "quality_status": "PASS",
        "summary": {
            "table_route_evidence_document_count": 4,
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
        },
        "evidence_documents": [
            {
                "evidence_id": "ev-1",
                "page_id": "p001",
                "table_id": "t1",
                "field_name": "covered_part_number",
                "normalized_value": "123-456-7",
                "raw_value": "123-456-7",
                "template_name": "list_effective_pages",
            },
            {
                "evidence_id": "ev-2",
                "page_id": "p001",
                "table_id": "t1",
                "field_name": "manual_page_reference",
                "normalized_value": "25-21-00 Page 1",
                "raw_value": "25-21-00 Page 1",
            },
            {
                "evidence_id": "ev-3",
                "page_id": "p002",
                "table_id": "t2",
                "field_name": "ipl_part_number",
                "normalized_value": "ABC123",
                "raw_value": "ABC123",
            },
            {
                "evidence_id": "unsafe",
                "page_id": "p002",
                "table_id": "t2",
                "field_name": "ipl_part_number",
                "normalized_value": "BLOCKED",
                "answer_permission": True,
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_make_exact_search_document_is_retrieval_only():
    doc = make_exact_search_document(
        {
            "evidence_id": "ev-1",
            "page_id": "p001",
            "table_id": "t1",
            "field_name": "ipl_part_number",
            "normalized_value": "ABC123",
        },
        0,
    )
    assert doc is not None
    assert doc["retrieval_only"] is True
    assert doc["answer_permission"] is False
    assert doc["can_answer_directly"] is False
    assert doc["can_prove_claims"] is False
    assert doc["source_truth_mutation_allowed"] is False
    assert "ABC123" in doc["search_text"]


def test_make_exact_search_document_blocks_unsafe_or_authoritative_records():
    assert make_exact_search_document({"field_name": "x", "normalized_value": "y", "answer_permission": True}, 0) is None
    assert make_exact_search_document({"field_name": "x", "normalized_value": "y", "context_only": True}, 0) is None
    assert make_exact_search_document({"field_name": "x", "normalized_value": "y", "source_truth_mutation_allowed": True}, 0) is None


def test_build_table_exact_search_adapter_writes_artifacts(tmp_path: Path):
    package_path = _evidence_package(tmp_path / "packager.json")
    out = tmp_path / "out"
    report = build_table_exact_search_adapter(package_path, out, _args())
    assert report["quality_status"] == QUALITY_PASS
    assert report["summary"]["source_evidence_document_count"] == 4
    assert report["summary"]["table_exact_search_document_count"] == 3
    assert report["summary"]["field_count"] == 3
    assert report["summary"]["answer_permission_count"] == 0
    assert report["summary"]["opensearch_write_attempt_count"] == 0
    assert report["summary"]["opensearch_upload_attempt_count"] == 0
    assert (out / "trace_net_table_exact_search_documents_v1.jsonl").exists()
    assert (out / "trace_net_table_exact_search_bulk_v1.ndjson").exists()
    assert (out / "trace_net_table_exact_search_mapping_v1.json").exists()
    assert (out / "trace_net_table_exact_search_adapter_v1_inspect.md").exists()


def test_quality_fails_when_doc_threshold_is_not_met(tmp_path: Path):
    package_path = _evidence_package(tmp_path / "packager.json")
    report = build_table_exact_search_adapter(package_path, tmp_path / "out", _args(min_exact_search_documents=99))
    assert report["quality_status"] == QUALITY_FAIL
    quality = check_quality_report(report, _args(min_exact_search_documents=99))
    assert quality["quality_status"] == QUALITY_FAIL


def test_jsonl_fallback_loads_evidence_documents(tmp_path: Path):
    jsonl = tmp_path / "trace_net_table_route_evidence_documents_v1.jsonl"
    jsonl.write_text(json.dumps({"field_name": "ipl_part_number", "normalized_value": "ABC", "page_id": "p1"}) + "\n", encoding="utf-8")
    report = tmp_path / "trace_net_table_route_evidence_packager_v1.json"
    report.write_text(json.dumps({"quality_status": "PASS", "summary": {}}), encoding="utf-8")
    package, rows, source = load_evidence_documents(report)
    assert package["quality_status"] == "PASS"
    assert len(rows) == 1
    assert "jsonl" in source


def test_opensearch_mapping_is_strict_and_local_ready():
    mapping = make_opensearch_mapping()
    assert mapping["index_name"] == DEFAULT_INDEX_NAME
    assert mapping["mappings"]["dynamic"] == "strict"
    assert mapping["mappings"]["properties"]["answer_permission"]["type"] == "boolean"
    assert mapping["mappings"]["properties"]["search_text"]["type"] == "text"
