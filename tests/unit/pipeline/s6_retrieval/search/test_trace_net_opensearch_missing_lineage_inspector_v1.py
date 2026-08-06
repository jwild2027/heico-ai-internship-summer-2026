from tiff.trace_net_opensearch_missing_lineage_inspector_v1 import (
    find_documents,
    has_page_lineage,
    has_source_trace_lineage,
    inspect_documents,
)


def test_find_documents_accepts_adapter_documents_key():
    payload = {"documents": [{"page_id": "p1"}, {"source_page_ids": ["p2"]}]}
    docs = find_documents(payload)
    assert len(docs) == 2


def test_lineage_detection_handles_page_and_source_page_ids():
    assert has_page_lineage({"page_id": "p1"})
    assert has_page_lineage({"source_page_ids": ["p2"]})
    assert has_source_trace_lineage({"page_id": "p1", "source_trace_present": False})
    assert has_source_trace_lineage({"source_trace": {"page_id": "p3"}})
    assert not has_page_lineage({"document_type": "part_candidate_lineage"})


def test_inspect_documents_reports_missing_lineage_records():
    docs = [
        {"opensearch_document_id": "good-page", "document_type": "page_retrieval_profile", "page_id": "p1", "source_trace_present": True, "safe_for_opensearch": True},
        {"opensearch_document_id": "good-community", "document_type": "community_summary", "source_page_ids": ["p2"], "safe_for_opensearch": True},
        {"opensearch_document_id": "bad-part", "document_type": "part_candidate_lineage", "rag_bucket": "part_candidate_lineage", "safe_for_opensearch": True},
    ]
    summary, records = inspect_documents(docs)
    assert summary["opensearch_document_count"] == 3
    assert summary["page_scoped_document_count"] == 2
    assert summary["missing_lineage_doc_count"] == 1
    assert summary["missing_page_id_count"] == 1
    assert summary["missing_source_trace_count"] == 1
    assert summary["missing_lineage_document_type_counts"] == {"part_candidate_lineage": 1}
    assert records[0]["opensearch_document_id"] == "bad-part"
