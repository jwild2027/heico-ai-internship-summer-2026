from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_opensearch_loader_smoke_v1 import (
    LoaderSmokeThresholds,
    build_loader_smoke_report,
    build_query_plans,
    count_summary,
    find_documents,
    find_mapping,
)


def _adapter_payload() -> dict:
    return {
        "quality_status": "PASS",
        "index_name": "trace_net_safe_search_v1",
        "mapping": {"properties": {"search_text": {"type": "text"}, "page_id": {"type": "keyword"}}},
        "documents": [
            {
                "opensearch_document_id": "doc-part",
                "document_type": "source_text_evidence",
                "rag_bucket": "source_text",
                "page_id": "t_p_120_1176_p000003",
                "source_trace": {"page_id": "t_p_120_1176_p000003", "source_package_entry": "00000003.tif"},
                "search_text": "Part 120-46137-001 appears in the manual revision history sample.",
                "authority": "source_text_evidence",
            },
            {
                "opensearch_document_id": "doc-phrase",
                "document_type": "source_text_evidence",
                "rag_bucket": "source_text",
                "page_id": "t_p_120_1176_p000013",
                "source_trace": {"page_id": "t_p_120_1176_p000013"},
                "search_text": "Manual revision history is listed with source backed citation evidence.",
                "authority": "source_text_evidence",
            },
            {
                "opensearch_document_id": "doc-table",
                "document_type": "table_cell",
                "rag_bucket": "table_cell",
                "page_id": "t_p_120_1176_p000340",
                "source_trace": {"page_id": "t_p_120_1176_p000340"},
                "search_text": "Table cell includes part number 120-46137-001 and related nomenclature.",
                "authority": "source_text_evidence",
            },
        ],
    }


def test_find_documents_and_mapping_detect_expected_keys() -> None:
    payload = _adapter_payload()
    doc_key, docs = find_documents(payload)
    mapping_key, mapping = find_mapping(payload)

    assert doc_key == "documents"
    assert len(docs) == 3
    assert mapping_key == "mapping"
    assert mapping["properties"]["search_text"]["type"] == "text"


def test_count_summary_safe_lineage() -> None:
    payload = _adapter_payload()
    docs = payload["documents"]
    summary = count_summary(payload, docs)

    assert summary["opensearch_document_count"] == 3
    assert summary["page_scoped_document_count"] == 3
    assert summary["missing_page_id_count"] == 0
    assert summary["missing_source_trace_count"] == 0
    assert summary["unsafe_index_document_count"] == 0
    assert summary["retrieval_only_answer_allowed_count"] == 0


def test_build_query_plans_creates_required_smoke_queries() -> None:
    docs = _adapter_payload()["documents"]
    plans = build_query_plans(docs)
    kinds = [p["query_kind"] for p in plans]

    assert "part_number_exact" in kinds
    assert "ocr_phrase_exact" in kinds
    assert "table_cell_exact" in kinds
    assert any(p["query_text"] == "120-46137-001" for p in plans)
    assert all(p["can_answer_directly"] is False for p in plans)
    assert all(p["can_prove_claims"] is False for p in plans)


def test_build_loader_smoke_report_writes_expected_artifacts(tmp_path: Path) -> None:
    adapter = tmp_path / "adapter.json"
    adapter.write_text(json.dumps(_adapter_payload()), encoding="utf-8")
    output_dir = tmp_path / "out"

    report = build_loader_smoke_report(
        opensearch_adapter_path=adapter,
        output_dir=output_dir,
        index_name="trace_net_safe_search_v1",
        thresholds=LoaderSmokeThresholds(
            min_documents=3,
            min_page_scoped_documents=3,
            min_query_plans=3,
            require_mapping=True,
            require_adapter_quality_pass=True,
        ),
    )

    assert report["quality_status"] == "PASS"
    assert report["status"] == "LOADER_SMOKE_READY"
    assert report["summary"]["bulk_action_sample_count"] == 3
    assert report["summary"]["opensearch_write_attempt_count"] == 0
    assert report["summary"]["part_number_query_plan_count"] >= 1
    assert report["summary"]["ocr_phrase_query_plan_count"] >= 1
    assert report["summary"]["table_cell_query_plan_count"] >= 1
    assert (output_dir / "trace_net_opensearch_loader_smoke_v1.json").exists()
    assert (output_dir / "trace_net_opensearch_loader_smoke_v1_quality.json").exists()
    assert (output_dir / "trace_net_opensearch_loader_smoke_v1.md").exists()
