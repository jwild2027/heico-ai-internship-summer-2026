# TRACE-Net OpenSearch Live Loader v1

Quality status: PASS
Status: OPENSEARCH_LIVE_LOADER_READY

## Summary

- index_name: trace_net_safe_search_v1
- opensearch_url: http://localhost:9200
- opensearch_document_count: 7027
- loaded_document_count: 7027
- mapping_present: True
- create_index_performed: True
- bulk_load_performed: True
- refresh_performed: True
- live_read_check_ok: True
- smoke_query_count: 3
- smoke_query_success_count: 3
- missing_page_id_count: 0
- missing_source_trace_count: 0
- unsafe_index_document_count: 0
- source_truth_mutation_allowed_count: 0
- postgres_write_attempt_count: 0
- qdrant_write_attempt_count: 0
- opensearch_write_attempt_count: 18

## Safety contract

This module may write to OpenSearch only when explicitly allowed. It never writes to Postgres, Qdrant, source truth, graph state, or final-answer authority.
