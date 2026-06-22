from __future__ import annotations

import argparse
import json
from pathlib import Path

from tiff.trace_net_table_exact_search_smoke_v1 import (
    QUALITY_FAIL,
    QUALITY_PASS,
    build_table_exact_search_smoke,
    check_quality_report,
    derive_auto_queries,
    load_exact_search_documents,
    score_document,
    search_documents,
)


def _args(**overrides):
    data = dict(
        min_source_exact_search_documents=3,
        min_smoke_query_count=3,
        min_successful_smoke_query_count=3,
        min_total_match_count=3,
        min_pages_with_smoke_matches=1,
        max_unsafe_records=0,
        max_answer_permission_count=0,
        max_source_truth_mutation_allowed=0,
        require_source_exact_search_adapter_quality_pass=True,
        require_no_answer_permission=True,
        query=[],
        auto_query_count=3,
        top_k=5,
    )
    data.update(overrides)
    return argparse.Namespace(**data)


def _adapter_report(path: Path, *, include_inline: bool = True) -> Path:
    docs = [
        {
            "document_id": "doc-1",
            "page_id": "p003",
            "table_id": "table-1",
            "field_name": "covered_part_number",
            "normalized_value": "120-36833-001",
            "raw_value": "120-36833-001",
            "search_text": "covered_part_number 120-36833-001",
            "retrieval_only": True,
        },
        {
            "document_id": "doc-2",
            "page_id": "p004",
            "table_id": "table-2",
            "field_name": "manual_page_reference",
            "normalized_value": "25-21-00 Page 101",
            "raw_value": "Page 101",
            "search_text": "manual_page_reference 25-21-00 Page 101",
            "retrieval_only": True,
        },
        {
            "document_id": "doc-3",
            "page_id": "p101",
            "table_id": "table-3",
            "field_name": "ipl_part_number",
            "normalized_value": "NAS1234",
            "raw_value": "NAS1234",
            "search_text": "ipl_part_number NAS1234",
            "retrieval_only": True,
        },
        {
            "document_id": "unsafe",
            "page_id": "p999",
            "table_id": "table-x",
            "field_name": "ipl_part_number",
            "normalized_value": "SHOULD-NOT-HIT",
            "search_text": "SHOULD-NOT-HIT",
            "answer_permission": True,
        },
    ]
    payload = {
        "quality_status": "PASS",
        "summary": {
            "table_exact_search_document_count": len(docs),
            "answer_permission_count": 0,
            "can_answer_directly_count": 0,
            "can_prove_claims_count": 0,
        },
    }
    if include_inline:
        payload["exact_search_documents"] = docs
    else:
        jsonl = path.parent / "trace_net_table_exact_search_documents_v1.jsonl"
        jsonl.write_text("".join(json.dumps(row) + "\n" for row in docs), encoding="utf-8")
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_score_document_prefers_exact_value_and_field():
    doc = {
        "field_name": "covered_part_number",
        "normalized_value": "120-36833-001",
        "search_text": "covered_part_number 120-36833-001",
    }
    assert score_document("120-36833-001", doc) >= 100
    assert score_document("covered_part_number", doc) >= 50
    assert score_document("missing", doc) == 0


def test_search_documents_filters_authoritative_or_unsafe_hits():
    docs = [
        {"document_id": "safe", "field_name": "ipl_part_number", "normalized_value": "ABC", "retrieval_only": True},
        {"document_id": "blocked", "field_name": "ipl_part_number", "normalized_value": "ABC", "answer_permission": True},
    ]
    hits = search_documents("ABC", docs, top_k=10)
    assert len(hits) == 1
    assert hits[0]["document_id"] == "safe"
    assert hits[0]["answer_permission"] is False
    assert hits[0]["can_prove_claims"] is False


def test_derive_auto_queries_uses_preferred_fields():
    docs = [
        {"field_name": "ipl_part_number", "normalized_value": "IPL-1"},
        {"field_name": "covered_part_number", "normalized_value": "COVERED-1"},
        {"field_name": "manual_page_reference", "normalized_value": "PAGE-1"},
    ]
    queries = derive_auto_queries(docs, limit=3)
    assert queries == ["COVERED-1", "PAGE-1", "IPL-1"]


def test_build_smoke_writes_passing_artifacts(tmp_path: Path):
    adapter_path = _adapter_report(tmp_path / "adapter.json")
    report = build_table_exact_search_smoke(adapter_path, tmp_path / "out", _args())
    assert report["quality_status"] == QUALITY_PASS
    assert report["summary"]["source_exact_search_document_count"] == 4
    assert report["summary"]["smoke_query_count"] == 3
    assert report["summary"]["successful_smoke_query_count"] == 3
    assert report["summary"]["answer_permission_count"] == 0
    assert report["summary"]["opensearch_upload_attempt_count"] == 0
    assert (tmp_path / "out" / "trace_net_table_exact_search_smoke_v1.json").exists()
    assert (tmp_path / "out" / "trace_net_table_exact_search_smoke_results_v1.jsonl").exists()
    assert (tmp_path / "out" / "trace_net_table_exact_search_smoke_v1_inspect.md").exists()


def test_build_smoke_with_explicit_queries(tmp_path: Path):
    adapter_path = _adapter_report(tmp_path / "adapter.json")
    report = build_table_exact_search_smoke(
        adapter_path,
        tmp_path / "out",
        _args(query=["120-36833-001", "25-21-00", "NAS1234"]),
    )
    assert report["quality_status"] == QUALITY_PASS
    assert report["summary"]["successful_smoke_query_count"] == 3


def test_quality_fails_when_smoke_threshold_is_not_met(tmp_path: Path):
    adapter_path = _adapter_report(tmp_path / "adapter.json")
    report = build_table_exact_search_smoke(adapter_path, tmp_path / "out", _args(min_total_match_count=999))
    assert report["quality_status"] == QUALITY_FAIL
    quality = check_quality_report(report, _args(min_total_match_count=999))
    assert quality["quality_status"] == QUALITY_FAIL


def test_jsonl_fallback_loads_exact_search_documents(tmp_path: Path):
    adapter_path = _adapter_report(tmp_path / "adapter.json", include_inline=False)
    adapter, rows, source = load_exact_search_documents(adapter_path)
    assert adapter["quality_status"] == "PASS"
    assert len(rows) == 4
    assert "jsonl" in source
