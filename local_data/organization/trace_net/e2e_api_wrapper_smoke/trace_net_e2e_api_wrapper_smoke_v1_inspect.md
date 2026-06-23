# TRACE-Net E2E API Wrapper Smoke v1 Inspect

Quality status: **PASS**

## API wrapper status
- e2e_api_wrapper_smoke_status: E2E_API_WRAPPER_SMOKE_READY_FOR_LOCAL_ENDPOINT
- ready_for_local_api_endpoint: True
- ready_for_open_webui_adapter: True
- safe_responses_are_drafts_until_runtime_finalization: True

## Main counters
- source_e2e_demo_record_count: 5
- source_complete_demo_flow_count: 5
- api_wrapper_request_count: 5
- api_wrapper_response_count: 5
- citation_backed_api_response_count: 5
- total_api_citation_count: 15
- page_with_api_citation_count: 6
- field_count: 4

## Safety/write counters
- unsafe_api_wrapper_record_count: 0
- answer_permission_count: 0
- can_answer_directly_count: 0
- can_prove_claims_count: 0
- source_truth_mutation_allowed_count: 0
- postgres_write_attempt_count: 0
- qdrant_write_attempt_count: 0
- opensearch_write_attempt_count: 0
- opensearch_upload_attempt_count: 0

## API responses
- e2e_query_v1_0001 | covered_part_number | citation_backed_response_draft | citations=3
  - query: Find part number 120-36833-001
  - pages: t_p_120_1176_p000003
  - draft: Final-gate smoke draft for query: 'Find part number 120-36833-001'. TRACE-Net found citation/source-trace-ready evidence: covered_part_number=120-36833-001 on t_p_120_1176_p000003; covered_part_number=120-36833-003 on t_p_120_1176_p000003; covered_part_number=
- e2e_query_v1_0002 | manual_page_reference | citation_backed_response_draft | citations=3
  - query: Where is manual reference 25-21-00 used?
  - pages: t_p_120_1176_p000005, t_p_120_1176_p000027, t_p_120_1176_p000028
  - draft: Final-gate smoke draft for query: 'Where is manual reference 25-21-00 used?'. TRACE-Net found citation/source-trace-ready evidence: manual_page_reference=25-21-00 on t_p_120_1176_p000005; ipl_part_number=25-21-00 on t_p_120_1176_p000027; ipl_part_number=25-21-
- e2e_query_v1_0003 | ipl_figure_item_or_quantity | citation_backed_response_draft | citations=3
  - query: Find IPL item 130
  - pages: t_p_120_1176_p000027, t_p_120_1176_p000028, t_p_120_1176_p000036
  - draft: Final-gate smoke draft for query: 'Find IPL item 130'. TRACE-Net found citation/source-trace-ready evidence: ipl_figure_item_or_quantity=130 on t_p_120_1176_p000027; ipl_figure_item_or_quantity=130 on t_p_120_1176_p000028; ipl_figure_item_or_quantity=130 on t_
- e2e_query_v1_0004 | table_text | citation_backed_response_draft | citations=3
  - query: Search table text MAINTENANCE MANUAL WITH
  - pages: t_p_120_1176_p000027, t_p_120_1176_p000028, t_p_120_1176_p000029
  - draft: Final-gate smoke draft for query: 'Search table text MAINTENANCE MANUAL WITH'. TRACE-Net found citation/source-trace-ready evidence: ipl_text=MAINTENANCE MANUAL WITH on t_p_120_1176_p000027; ipl_text=MAINTENANCE MANUAL WITH on t_p_120_1176_p000028; ipl_text=MA
- e2e_query_v1_0005 | covered_part_number | citation_backed_response_draft | citations=3
  - query: What maintenance manual pages mention covered part numbers?
  - pages: t_p_120_1176_p000003
  - draft: Final-gate smoke draft for query: 'What maintenance manual pages mention covered part numbers?'. TRACE-Net found citation/source-trace-ready evidence: covered_part_number=120-36833-001 on t_p_120_1176_p000003; covered_part_number=120-36833-003 on t_p_120_1176_

## Quality checks
- PASS source_e2e_demo_record_count: observed=5 expected=>= 5
- PASS source_complete_demo_flow_count: observed=5 expected=>= 5
- PASS api_wrapper_request_count: observed=5 expected=>= 5
- PASS api_wrapper_response_count: observed=5 expected=>= 5
- PASS citation_backed_api_response_count: observed=5 expected=>= 4
- PASS total_api_citation_count: observed=15 expected=>= 10
- PASS page_with_api_citation_count: observed=6 expected=>= 2
- PASS field_count: observed=4 expected=>= 3
- PASS schema_missing_required_key_record_count: observed=0 expected=<= 0
- PASS unsafe_api_wrapper_record_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS can_answer_directly_count: observed=0 expected=== 0
- PASS can_prove_claims_count: observed=0 expected=== 0
- PASS postgres_write_attempt_count: observed=0 expected=== 0
- PASS qdrant_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_upload_attempt_count: observed=0 expected=== 0
- PASS source_demo_report_quality_pass: observed=True expected=is True
- PASS all_api_records_no_answer_authority: observed=0 expected=== 0
