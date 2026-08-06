from __future__ import annotations

import json
from pathlib import Path

from tiff.trace_net_opensearch_adapter_lineage_guard_v1 import apply_lineage_guard, quality_report


def _sample_report() -> dict:
    return {
        "schema_version": "trace_net_opensearch_adapter_v1",
        "status": "OPENSEARCH_DOCUMENTS_BUILT",
        "quality_status": "FAIL",
        "index_name": "trace_net_safe_search_v1",
        "mapping": {"mappings": {"properties": {"text": {"type": "text"}}}},
        "summary": {
            "opensearch_document_count": 4,
            "page_scoped_document_count": 2,
            "missing_page_id_count": 2,
            "missing_source_trace_count": 2,
            "unsafe_index_document_count": 1,
        },
        "documents": [
            {
                "opensearch_document_id": "doc-good-page",
                "document_type": "page_retrieval_profile",
                "text": "safe page text",
                "page_id": "t_p_120_1176_p000001",
                "source_page_ids": ["t_p_120_1176_p000001"],
                "source_trace_present": True,
                "safe_for_opensearch": True,
                "retrieval_only": True,
                "can_answer_directly": False,
                "can_prove_claims": False,
            },
            {
                "opensearch_document_id": "doc-good-community",
                "document_type": "community_summary",
                "text": "community with page lineage",
                "source_page_ids": ["t_p_120_1176_p000002", "t_p_120_1176_p000003"],
                "source_trace_present": True,
                "safe_for_opensearch": True,
                "retrieval_only": True,
                "can_answer_directly": False,
                "can_prove_claims": False,
            },
            {
                "opensearch_document_id": "doc-missing-lineage",
                "document_type": "community_summary",
                "text": "global community with no page lineage",
                "source_page_ids": [],
                "source_trace_present": False,
                "safe_for_opensearch": True,
                "retrieval_only": True,
            },
            {
                "opensearch_document_id": "doc-unsafe",
                "document_type": "debug",
                "text": "unsafe debug document",
                "page_id": "t_p_120_1176_p000004",
                "source_page_ids": ["t_p_120_1176_p000004"],
                "source_trace_present": True,
                "safe_for_opensearch": False,
                "retrieval_only": True,
            },
        ],
    }


def test_lineage_guard_drops_untraceable_and_unsafe_docs(tmp_path: Path) -> None:
    report_path = tmp_path / "trace_net_opensearch_adapter_v1.json"
    report_path.write_text(json.dumps(_sample_report()), encoding="utf-8")

    guarded = apply_lineage_guard(
        adapter_report_path=report_path,
        output_dir=tmp_path,
        min_documents=2,
        min_page_scoped_documents=2,
        require_mapping=True,
    )

    summary = guarded["summary"]
    assert guarded["quality_status"] == "PASS"
    assert summary["opensearch_document_count"] == 2
    assert summary["page_scoped_document_count"] == 2
    assert summary["missing_page_id_count"] == 0
    assert summary["missing_source_trace_count"] == 0
    assert summary["unsafe_index_document_count"] == 0
    assert summary["lineage_guard_dropped_document_count"] == 2
    assert all(d["source_trace_present"] for d in guarded["documents"])
    assert all(d["can_answer_directly"] is False for d in guarded["documents"])
    assert (tmp_path / "trace_net_opensearch_documents_v1.jsonl").exists()
    assert (tmp_path / "trace_net_opensearch_bulk_v1.ndjson").exists()


def test_lineage_guard_quality_fails_threshold_when_too_few_docs(tmp_path: Path) -> None:
    report_path = tmp_path / "trace_net_opensearch_adapter_v1.json"
    report_path.write_text(json.dumps(_sample_report()), encoding="utf-8")
    guarded = apply_lineage_guard(adapter_report_path=report_path, output_dir=tmp_path, min_documents=2, min_page_scoped_documents=2, require_mapping=True)
    quality = quality_report(guarded, min_documents=5, min_page_scoped_documents=5, require_mapping=True)
    assert quality["status"] == "FAIL"
    assert quality["summary"]["failed_check_count"] >= 1
