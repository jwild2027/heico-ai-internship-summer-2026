# TRACE-Net E2E Dynamic Plan Executor v18

Quality status: **PASS**
Status: `E2E_DYNAMIC_PLAN_EXECUTOR_READY_FOR_LIVE_CONTEXT_PACK`

## Summary
- query_plan_count: 5
- execution_count: 5
- ready_execution_count: 5
- source_truth_evidence_count: 32
- graph_guidance_count: 5
- summary_guidance_count: 5
- capped_result_count: 3
- high_degree_node_execution_count: 3
- graph_proof_authority_violation_count: 0
- summary_proof_authority_violation_count: 0
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Contract
- Query-time execution must not scan raw 5TB source data.
- Graph and Leiden outputs are guidance only and require source-truth confirmation.
- High-degree entities use aggregation plus a capped, ranked sample instead of silent truncation.
- Capped results disclose total and returned counts.
- v2 summaries are guidance only, not proof authority.

## Executions
### query_plan_v17_0001 — `part_number`
- query: Find part number 120-36834-509
- status: `DYNAMIC_PLAN_EXECUTION_READY`
- total_match_count: 1
- returned_match_count: 1
- result_was_capped: False
- high_degree_node_detected: False
- graph_guidance_count: 1

### query_plan_v17_0002 — `part_number`
- query: Find part number 120-36833-501
- status: `DYNAMIC_PLAN_EXECUTION_READY`
- total_match_count: 1
- returned_match_count: 1
- result_was_capped: False
- high_degree_node_detected: False
- graph_guidance_count: 1

### query_plan_v17_0003 — `covered_part_number`
- query: What maintenance manual pages mention covered part numbers?
- status: `DYNAMIC_PLAN_EXECUTION_READY`
- total_match_count: 150
- returned_match_count: 10
- result_was_capped: True
- high_degree_node_detected: True
- graph_guidance_count: 1

### query_plan_v17_0004 — `manual_page_reference`
- query: Where is manual reference 25-21-00 used?
- status: `DYNAMIC_PLAN_EXECUTION_READY`
- total_match_count: 50
- returned_match_count: 10
- result_was_capped: True
- high_degree_node_detected: True
- graph_guidance_count: 1

### query_plan_v17_0005 — `table_text`
- query: Search table text MAINTENANCE MANUAL WITH
- status: `DYNAMIC_PLAN_EXECUTION_READY`
- total_match_count: 188
- returned_match_count: 10
- result_was_capped: True
- high_degree_node_detected: True
- graph_guidance_count: 1

## Quality checks
- PASS query_plan_count: observed=5 expected=>= 5
- PASS ready_execution_count: observed=5 expected=>= 5
- PASS source_truth_evidence_count: observed=32 expected=>= 10
- PASS graph_guidance_count: observed=5 expected=>= 5
- PASS capped_result_count: observed=3 expected=>= 1
- PASS graph_proof_authority_violation_count: observed=0 expected=<= 0
- PASS summary_proof_authority_violation_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS require_no_answer_permission: observed=0 expected=== 0
