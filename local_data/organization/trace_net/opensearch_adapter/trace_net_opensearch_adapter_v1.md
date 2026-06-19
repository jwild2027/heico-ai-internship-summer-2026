# TRACE-Net OpenSearch Adapter v1 — Lineage Guarded

**Status:** OPENSEARCH_DOCUMENTS_LINEAGE_GUARDED
**Quality:** PASS
**Index:** trace_net_safe_search_v1

## Summary

- opensearch_document_count: 7027
- page_scoped_document_count: 7027
- documents_with_search_text_count: 7027
- missing_page_id_count: 0
- missing_source_trace_count: 0
- lineage_guard_dropped_document_count: 0
- unsafe_index_document_count: 0
- raw_feedback_indexed_count: 0
- raw_visual_output_indexed_count: 0
- raw_ocr_unfiltered_indexed_count: 0
- retrieval_only_answer_allowed_count: 0
- source_truth_mutation_allowed_count: 0
- opensearch_write_attempt_count: 0

## Safety Contract

- Local artifact rewrite only.
- No Postgres, Qdrant, or OpenSearch writes.
- Documents without page/source lineage are removed before loader smoke or live indexing.
- Retrieval-only documents cannot answer directly or prove claims.
