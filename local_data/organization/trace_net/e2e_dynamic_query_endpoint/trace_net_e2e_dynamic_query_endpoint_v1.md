# TRACE-Net E2E Dynamic Query Endpoint v1

Quality status: **PASS**
Dynamic endpoint status: **E2E_DYNAMIC_QUERY_ENDPOINT_READY_FOR_OPEN_WEBUI_DYNAMIC_SMOKE**

## Reranker v2

Dynamic reranker v2 boosts exact intent-field matches, suppresses generic table tokens for identifier queries, and normalizes small OCR spacing issues before citation display.

## What dynamic means here

This endpoint runs query-time retrieval over prebuilt artifacts. It does not rerun OCR, page classification, embeddings, summaries, graph construction, or source ingest.

## Counters
- table_exact_search_document_count: 1497
- table_hybrid_bridge_record_count: 1497
- dynamic_search_document_count: 2994
- page_with_dynamic_search_document_count: 13
- field_count: 6

## Safety
- answer_permission_count: 0
- can_answer_directly_count: 0
- can_prove_claims_count: 0
- source_truth_mutation_allowed_count: 0
- service write attempts: 0
