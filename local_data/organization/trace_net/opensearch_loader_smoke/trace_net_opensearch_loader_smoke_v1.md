# TRACE-Net OpenSearch Loader Smoke v1

Quality status: PASS
Status: LOADER_SMOKE_READY

## Summary

- adapter_quality_status: PASS
- index_name: trace_net_safe_search_v1
- opensearch_document_count: 7027
- page_scoped_document_count: 7027
- missing_page_id_count: 0
- missing_source_trace_count: 0
- mapping_present: True
- query_plan_count: 3
- bulk_preview_document_count: 25
- unsafe_index_document_count: 0
- raw_feedback_indexed_count: 0
- raw_visual_output_indexed_count: 0
- raw_ocr_unfiltered_indexed_count: 0
- retrieval_only_answer_allowed_count: 0
- source_truth_mutation_allowed_count: 0
- opensearch_write_attempt_count: 0

## Safety contract

Dry-run only. No Postgres, Qdrant, OpenSearch, source-truth, or answer-permission writes.
