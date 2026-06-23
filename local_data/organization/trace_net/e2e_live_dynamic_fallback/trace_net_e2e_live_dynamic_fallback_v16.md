# TRACE-Net E2E Live Dynamic Fallback v16

Quality status: **PASS**
Status: `E2E_LIVE_DYNAMIC_FALLBACK_READY`

## Contract
This endpoint reuses v15 final-gated answers first, then dynamically searches prebuilt table exact-search evidence for new exact source-truth queries. It does not call an LLM, rerun OCR, rebuild embeddings, rebuild graph, rerun table extraction, mutate source truth, or write to services.

## Connection
- Windows/Git Bash test base URL: `http://127.0.0.1:8019/v1`
- Open WebUI Docker base URL: `http://host.docker.internal:8019/v1`
- Model: `trace-net-e2e-live-dynamic-fallback-v16`

## Summary
- existing_pipeline_query_count: 5
- exact_search_document_count: 1497
- dynamic_fallback_probe_count: 5
- ready_dynamic_fallback_probe_count: 5
- total_dynamic_fallback_citation_count: 21
- unsupported_claim_count: 0
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Dynamic fallback probes
- **LIVE_DYNAMIC_FALLBACK_FINAL_GATED_READY** `live_dynamic_fallback_v16_0001` | covered_part_number | Find part number 120-36833-003 | citations=5
- **LIVE_DYNAMIC_FALLBACK_FINAL_GATED_READY** `live_dynamic_fallback_v16_0002` | manual_page_reference | Where is manual reference 95-21-00 used? | citations=1
- **LIVE_DYNAMIC_FALLBACK_FINAL_GATED_READY** `live_dynamic_fallback_v16_0003` | table_text | Search table text ILLUSTRATED PARTS LIST | citations=5
- **LIVE_DYNAMIC_FALLBACK_FINAL_GATED_READY** `live_dynamic_fallback_v16_0004` | covered_part_number | Find part number 120-36833-005 | citations=5
- **LIVE_DYNAMIC_FALLBACK_FINAL_GATED_READY** `live_dynamic_fallback_v16_0005` | covered_part_number | Find part number 120-36833-501 | citations=5

## Quality checks
- PASS existing_pipeline_query_count: observed=5 expected=>= 5
- PASS exact_search_document_count: observed=1497 expected=>= 10
- PASS dynamic_fallback_probe_count: observed=5 expected=>= 3
- PASS ready_dynamic_fallback_probe_count: observed=5 expected=>= 3
- PASS total_dynamic_fallback_citation_count: observed=21 expected=>= 15
- PASS endpoint_route_count: observed=4 expected=>= 4
- PASS unsupported_claim_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS contract_can_answer_directly: observed=0 expected=== 0
- PASS contract_can_prove_claims: observed=0 expected=== 0
- PASS postgres_write_attempt_count: observed=0 expected=== 0
- PASS qdrant_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_write_attempt_count: observed=0 expected=== 0
- PASS require_no_answer_permission: observed=0 expected=== 0
