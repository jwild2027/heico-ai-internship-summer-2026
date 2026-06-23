# TRACE-Net E2E Live Query Pipeline v15

Quality status: **PASS**
Status: `E2E_LIVE_QUERY_PIPELINE_READY`

## Contract
This endpoint orchestrates the live query-time TRACE-Net control path using prebuilt final-gated answers. It does not call an LLM, rerun retrieval, rerun OCR, rebuild embeddings, rebuild graph, rerun table extraction, mutate source truth, or write to services.

## Connection
- Windows/Git Bash test base URL: `http://127.0.0.1:8018/v1`
- Open WebUI Docker base URL: `http://host.docker.internal:8018/v1`
- Model: `trace-net-e2e-live-query-pipeline-v15`

## Summary
- final_answer_count: 5
- ready_pipeline_query_count: 5
- total_pipeline_stage_count: 45
- total_citation_count: 25
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Ready live query pipelines
- **LIVE_QUERY_PIPELINE_FINAL_GATED_READY** `live_query_pipeline_v15_0001` | covered_part_number | Find part number 120-36833-001 | stages=9 citations=5
- **LIVE_QUERY_PIPELINE_FINAL_GATED_READY** `live_query_pipeline_v15_0002` | covered_part_number | Find part number 120-36834-509 | stages=9 citations=5
- **LIVE_QUERY_PIPELINE_FINAL_GATED_READY** `live_query_pipeline_v15_0003` | manual_page_reference | Where is manual reference 25-21-00 used? | stages=9 citations=5
- **LIVE_QUERY_PIPELINE_FINAL_GATED_READY** `live_query_pipeline_v15_0004` | table_text | Search table text MAINTENANCE MANUAL WITH | stages=9 citations=5
- **LIVE_QUERY_PIPELINE_FINAL_GATED_READY** `live_query_pipeline_v15_0005` | covered_part_number | What maintenance manual pages mention covered part numbers? | stages=9 citations=5

## Quality checks
- PASS final_answer_count: observed=5 expected=>= 5
- PASS ready_pipeline_query_count: observed=5 expected=>= 5
- PASS min_pipeline_stages_per_query: observed=9 expected=>= 8
- PASS total_pipeline_stage_count: observed=45 expected=>= 40
- PASS total_citation_count: observed=25 expected=>= 15
- PASS endpoint_route_count: observed=4 expected=>= 4
- PASS unknown_query_final_answer_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS contract_can_answer_directly: observed=0 expected=== 0
- PASS contract_can_prove_claims: observed=0 expected=== 0
- PASS postgres_write_attempt_count: observed=0 expected=== 0
- PASS qdrant_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_write_attempt_count: observed=0 expected=== 0
- PASS require_no_answer_permission: observed=0 expected=== 0
