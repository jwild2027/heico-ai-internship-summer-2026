from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_opensearch_live_loader_v1 import (
    LiveLoaderThresholds,
    build_live_loader_report,
    filter_safe_documents,
    make_bulk_ndjson,
    smoke_query_body,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def safe_doc(i: int = 1) -> dict:
    return {
        "opensearch_document_id": f"doc::{i}",
        "document_type": "table_cell_normalized",
        "page_id": f"t_p_120_1176_p{i:06d}",
        "source_page_ids": [f"t_p_120_1176_p{i:06d}"],
        "search_text": f"120-50648-00{i} Table cell | t_p_120_1176_p{i:06d}",
        "retrieval_only": True,
        "can_answer_directly": False,
        "can_prove_claims": False,
        "source_truth_mutation_allowed": False,
        "safe_for_opensearch": True,
    }


def adapter_payload(docs: list[dict]) -> dict:
    return {
        "schema_version": "trace_net_opensearch_adapter_v1",
        "quality_status": "PASS",
        "mapping": {"properties": {"search_text": {"type": "text"}, "document_type": {"type": "keyword"}}},
        "documents": docs,
        "summary": {"quality_status": "PASS", "opensearch_document_count": len(docs)},
    }


def loader_smoke_payload() -> dict:
    return {
        "schema_version": "trace_net_opensearch_loader_smoke_v1",
        "quality_status": "PASS",
        "query_plans": [
            {"query_plan_id": "p", "query_kind": "part_number_exact", "query": "120-50648-001", "retrieval_only": True, "can_answer_directly": False, "can_prove_claims": False},
            {"query_plan_id": "o", "query_kind": "ocr_phrase_exact", "query": "Table cell", "retrieval_only": True, "can_answer_directly": False, "can_prove_claims": False},
            {"query_plan_id": "t", "query_kind": "table_cell_exact", "query": "120-50648-001", "retrieval_only": True, "can_answer_directly": False, "can_prove_claims": False},
        ],
        "summary": {"quality_status": "PASS"},
    }


def test_filter_safe_documents_drops_missing_lineage_and_answer_leaks() -> None:
    docs = [safe_doc(1), {**safe_doc(2), "page_id": None, "source_page_ids": []}, {**safe_doc(3), "can_answer_directly": True}]
    safe, dropped = filter_safe_documents(docs)
    assert len(safe) == 1
    assert dropped["missing_page_lineage"] == 1
    assert dropped["retrieval_only_answer_allowed"] == 1


def test_bulk_ndjson_uses_document_ids() -> None:
    ndjson = make_bulk_ndjson([safe_doc(1)], index_name="trace_net_safe_search_v1")
    lines = ndjson.strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["index"]["_id"] == "doc::1"
    assert json.loads(lines[1])["page_id"] == "t_p_120_1176_p000001"


def test_smoke_query_body_marks_exact_part_query() -> None:
    body = smoke_query_body("120-50648-001", "part_number_exact")
    assert body["query"]["bool"]["minimum_should_match"] == 1
    assert body["size"] == 5


def test_build_live_loader_dry_run_report_passes(tmp_path: Path) -> None:
    adapter_path = tmp_path / "adapter.json"
    smoke_path = tmp_path / "smoke.json"
    out = tmp_path / "out"
    docs = [safe_doc(i) for i in range(1, 4)]
    write_json(adapter_path, adapter_payload(docs))
    write_json(smoke_path, loader_smoke_payload())

    report = build_live_loader_report(
        opensearch_adapter_path=adapter_path,
        loader_smoke_path=smoke_path,
        output_dir=out,
        dry_run=True,
        thresholds=LiveLoaderThresholds(
            min_documents=3,
            min_page_scoped_documents=3,
            min_loaded_documents=3,
            min_smoke_queries=3,
            require_adapter_quality_pass=True,
            require_loader_smoke_quality_pass=True,
            require_mapping=True,
            allow_opensearch_writes=False,
        ),
    )
    assert report["quality_status"] == "PASS"
    summary = report["summary"]
    assert summary["opensearch_document_count"] == 3
    assert summary["loaded_document_count"] == 3
    assert summary["opensearch_write_attempt_count"] == 0
    assert summary["missing_page_id_count"] == 0
    assert (out / "trace_net_opensearch_live_loader_v1.json").exists()
