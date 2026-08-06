from tiff.trace_net_opensearch_adapter_v1 import quality_report


def base_summary():
    return {
        "opensearch_document_count": 5,
        "page_scoped_document_count": 5,
        "missing_page_id_count": 0,
        "missing_source_trace_count": 0,
        "unsafe_index_document_count": 0,
        "raw_feedback_indexed_count": 0,
        "raw_visual_output_indexed_count": 0,
        "raw_ocr_unfiltered_indexed_count": 0,
        "retrieval_only_answer_allowed_count": 0,
        "source_truth_mutation_allowed_count": 0,
        "postgres_write_attempt_count": 0,
        "opensearch_write_attempt_count": 0,
    }


def test_quality_passes_clean_report():
    quality = quality_report({"summary": base_summary(), "mapping": {"mappings": {}}}, min_documents=1, min_page_scoped_documents=1, require_mapping=True)
    assert quality["status"] == "PASS"


def test_quality_fails_missing_lineage():
    summary = base_summary()
    summary["missing_page_id_count"] = 1
    quality = quality_report({"summary": summary, "mapping": {"mappings": {}}}, min_documents=1, min_page_scoped_documents=1, require_mapping=True)
    assert quality["status"] == "FAIL"


def test_quality_fails_write_attempt():
    summary = base_summary()
    summary["opensearch_write_attempt_count"] = 1
    quality = quality_report({"summary": summary, "mapping": {"mappings": {}}}, min_documents=1, min_page_scoped_documents=1, require_mapping=True)
    assert quality["status"] == "FAIL"
