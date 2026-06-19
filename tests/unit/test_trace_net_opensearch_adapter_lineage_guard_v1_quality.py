from __future__ import annotations

from tiff.trace_net_opensearch_adapter_lineage_guard_v1 import quality_report


def test_quality_report_requires_zero_lineage_and_safety_counts() -> None:
    report = {
        "mapping": {"mappings": {}},
        "summary": {
            "opensearch_document_count": 10,
            "page_scoped_document_count": 10,
            "missing_page_id_count": 0,
            "missing_source_trace_count": 0,
            "unsafe_index_document_count": 0,
            "raw_feedback_indexed_count": 0,
            "raw_visual_output_indexed_count": 0,
            "raw_ocr_unfiltered_indexed_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
    }
    quality = quality_report(report, min_documents=5, min_page_scoped_documents=5, require_mapping=True)
    assert quality["status"] == "PASS"


def test_quality_report_fails_nonzero_missing_source_trace() -> None:
    report = {
        "mapping": {"mappings": {}},
        "summary": {
            "opensearch_document_count": 10,
            "page_scoped_document_count": 9,
            "missing_page_id_count": 0,
            "missing_source_trace_count": 1,
            "unsafe_index_document_count": 0,
            "raw_feedback_indexed_count": 0,
            "raw_visual_output_indexed_count": 0,
            "raw_ocr_unfiltered_indexed_count": 0,
            "retrieval_only_answer_allowed_count": 0,
            "source_truth_mutation_allowed_count": 0,
            "postgres_write_attempt_count": 0,
            "qdrant_write_attempt_count": 0,
            "opensearch_write_attempt_count": 0,
        },
    }
    quality = quality_report(report, min_documents=5, min_page_scoped_documents=5, require_mapping=True)
    assert quality["status"] == "FAIL"
