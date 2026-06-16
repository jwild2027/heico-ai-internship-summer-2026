# TRACE-Net OpenSearch Missing Lineage Inspector v1

**Status:** NO_MISSING_LINEAGE
**Quality:** PASS
**Adapter quality:** PASS

## Summary

- opensearch_document_count: 7027
- page_scoped_document_count: 7027
- missing_lineage_doc_count: 0
- missing_page_id_count: 0
- missing_source_trace_count: 0
- unsafe_index_document_count: 0
- raw_feedback_indexed_count: 0
- raw_visual_output_indexed_count: 0
- raw_ocr_unfiltered_indexed_count: 0
- retrieval_only_answer_allowed_count: 0
- source_truth_mutation_allowed_count: 0
- postgres_write_attempt_count: 0
- qdrant_write_attempt_count: 0
- opensearch_write_attempt_count: 0

## Missing lineage by document type

- none

## Safety Contract

- Diagnostic artifact only; no Postgres writes.
- Diagnostic artifact only; no Qdrant writes.
- Diagnostic artifact only; no OpenSearch writes.
- Does not mutate source truth.
- Does not grant answer permission or proof authority.
