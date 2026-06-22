# TRACE-Net E2E Local Endpoint v1 Inspect

Quality status: **PASS**

## Endpoint contract
- purpose: Expose the artifact-backed E2E API wrapper smoke as local TRACE-Net endpoints for Open WebUI smoke testing.
- host: 127.0.0.1
- port: 8014
- base_url: http://127.0.0.1:8014
- native_endpoint: /api/trace-net/ask
- openai_chat_endpoint: /v1/chat/completions
- model_id: trace-net-e2e-local-endpoint-v1
- responses_are_smoke_drafts: True
- ready_for_open_webui_smoke: True
- answer_authority: blocked_in_local_endpoint_smoke
- can_answer_directly: False
- can_prove_claims: False
- source_truth_mutation_allowed: False
- writes_to_postgres: False
- writes_to_qdrant: False
- writes_to_opensearch: False
- uploads_to_opensearch: False

## Main counters
- api_response_count: 5
- citation_backed_response_count: 5
- total_citation_count: 15
- page_with_citation_count: 6
- field_count: 4
- endpoint_route_count: 4
- health_endpoint_ready: True
- native_ask_endpoint_ready: True
- openai_chat_completion_endpoint_ready: True
- ready_for_open_webui_smoke: True
- answer_permission_count: 0
- can_answer_directly_count: 0
- can_prove_claims_count: 0
- source_truth_mutation_allowed_count: 0
- postgres_write_attempt_count: 0
- qdrant_write_attempt_count: 0
- opensearch_write_attempt_count: 0
- opensearch_upload_attempt_count: 0

## Routes
- GET /health — endpoint health and source artifact status
- GET /v1/models — OpenAI-compatible model listing for Open WebUI
- POST /api/trace-net/ask — TRACE-Net native ask wrapper
- POST /v1/chat/completions — OpenAI-compatible chat completion wrapper

## Sample API responses
- e2e_query_v1_0001 | covered_part_number | citations=3
  - query: Find part number 120-36833-001
  - pages: t_p_120_1176_p000003
  - draft: Final-gate smoke draft for query: 'Find part number 120-36833-001'. TRACE-Net found citation/source-trace-ready evidence: covered_part_number=120-36833-001 on t_p_120_1176_p000003; covered_part_number=120-36833-003 on t_p_120_1176_p000003; covered_part_number=
- e2e_query_v1_0002 | manual_page_reference | citations=3
  - query: Where is manual reference 25-21-00 used?
  - pages: t_p_120_1176_p000005, t_p_120_1176_p000027, t_p_120_1176_p000028
  - draft: Final-gate smoke draft for query: 'Where is manual reference 25-21-00 used?'. TRACE-Net found citation/source-trace-ready evidence: manual_page_reference=25-21-00 on t_p_120_1176_p000005; ipl_part_number=25-21-00 on t_p_120_1176_p000027; ipl_part_number=25-21-
- e2e_query_v1_0003 | ipl_figure_item_or_quantity | citations=3
  - query: Find IPL item 130
  - pages: t_p_120_1176_p000027, t_p_120_1176_p000028, t_p_120_1176_p000036
  - draft: Final-gate smoke draft for query: 'Find IPL item 130'. TRACE-Net found citation/source-trace-ready evidence: ipl_figure_item_or_quantity=130 on t_p_120_1176_p000027; ipl_figure_item_or_quantity=130 on t_p_120_1176_p000028; ipl_figure_item_or_quantity=130 on t_
- e2e_query_v1_0004 | table_text | citations=3
  - query: Search table text MAINTENANCE MANUAL WITH
  - pages: t_p_120_1176_p000027, t_p_120_1176_p000028, t_p_120_1176_p000029
  - draft: Final-gate smoke draft for query: 'Search table text MAINTENANCE MANUAL WITH'. TRACE-Net found citation/source-trace-ready evidence: ipl_text=MAINTENANCE MANUAL WITH on t_p_120_1176_p000027; ipl_text=MAINTENANCE MANUAL WITH on t_p_120_1176_p000028; ipl_text=MA
- e2e_query_v1_0005 | covered_part_number | citations=3
  - query: What maintenance manual pages mention covered part numbers?
  - pages: t_p_120_1176_p000003
  - draft: Final-gate smoke draft for query: 'What maintenance manual pages mention covered part numbers?'. TRACE-Net found citation/source-trace-ready evidence: covered_part_number=120-36833-001 on t_p_120_1176_p000003; covered_part_number=120-36833-003 on t_p_120_1176_

## Quality checks
- PASS source_quality_pass: observed=True expected=is True
- PASS api_response_count: observed=5 expected=>= 5
- PASS citation_backed_response_count: observed=5 expected=>= 4
- PASS total_citation_count: observed=15 expected=>= 10
- PASS endpoint_route_count: observed=4 expected=>= 4
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS can_answer_directly_count: observed=0 expected=== 0
- PASS can_prove_claims_count: observed=0 expected=== 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS postgres_write_attempt_count: observed=0 expected=== 0
- PASS qdrant_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_upload_attempt_count: observed=0 expected=== 0
