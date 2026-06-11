# TRACE-Net OpenSearch Adapter v1

**Status:** OPENSEARCH_DOCUMENTS_BUILT
**Quality:** PASS
**Index:** trace_net_safe_search_v1

## Summary

- opensearch_document_count: 7027
- page_scoped_document_count: 7027
- missing_page_id_count: 0
- missing_source_trace_count: 0
- unsafe_index_document_count: 0
- raw_feedback_indexed_count: 0
- raw_visual_output_indexed_count: 0
- raw_ocr_unfiltered_indexed_count: 0
- retrieval_only_answer_allowed_count: 0
- source_truth_mutation_allowed_count: 0
- opensearch_write_attempt_count: 0

## Document Types

- community_summary: 223
- context_retrieval_helper: 50
- embedding_candidate: 1476
- page_retrieval_profile: 509
- part_candidate_lineage: 301
- table_cell_normalized: 3054
- table_row_normalized: 1414

## Safety Contract

- This adapter builds local OpenSearch documents only.
- It does not write to OpenSearch/Postgres/Qdrant.
- Raw OCR, raw visual output, raw feedback, prompt/debug text, and unsafe records are blocked.
- Retrieval-only documents cannot prove claims or answer directly.
