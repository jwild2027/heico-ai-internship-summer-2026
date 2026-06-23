# TRACE-Net E2E Live Eval + Latency Harness v26

Quality status: **PASS**
Status: `E2E_LIVE_EVAL_LATENCY_HARNESS_READY`

## Summary
- endpoint_base_url: http://127.0.0.1:8022
- model: trace-net-e2e-live-orchestrator-fastpath-gemma-v27
- eval_query_count: 6
- success_count: 6
- false_positive_count: 0
- false_negative_count: 0
- unsupported_claim_count: 0
- llm_call_error_count: 0
- audit_only_count: 3
- final_answer_count: 3
- cap_disclosure_required_count: 1
- cap_disclosure_detected_count: 1
- avg_latency_ms: 11.078
- max_latency_ms: 25.063
- total_latency_ms: 66.467
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Contract
- This harness evaluates the live v25 endpoint; it does not mutate source truth.
- Missing exact values must return audit-only rather than broad/noisy matches.
- Present exact values should return source-truth citations.
- Latency is measured for the complete endpoint call; v26 does not yet split retrieval vs Gemma timing unless the endpoint exposes those timings.

## Evaluation records
### eval_v26_0001 — PASS
- query: Find part number 120-36833-503
- expected_behavior: final_gated_answer
- final_gate_status: LIVE_ORCHESTRATOR_FINAL_GATE_PASS
- citation_like_count: 1
- total_match_count: 1
- returned_match_count: 1
- result_was_capped: False
- latency_ms: 10.636
- false_positive: False
- false_negative: False
- preview: TRACE-Net found part number 120-36833-503 on page t_p_120_1176_p000003 as covered_part_number [1]. The available direct source-truth evidence confirms the listing, but it does not provide enough information to describe the part physically.

### eval_v26_0002 — PASS
- query: Find part number DOES-NOT-EXIST-999
- expected_behavior: audit_only
- final_gate_status: LIVE_ORCHESTRATOR_AUDIT_ONLY
- citation_like_count: 0
- total_match_count: 0
- returned_match_count: 0
- result_was_capped: False
- latency_ms: 6.96
- false_positive: False
- false_negative: False
- preview: TRACE-Net did not find direct citation-ready source-truth evidence for this query. No source-truth claim is made. Try narrowing by part number, manual reference, page, or table text.

### eval_v26_0003 — PASS
- query: Where is manual reference 25-21-00 used?
- expected_behavior: final_gated_answer
- final_gate_status: LIVE_ORCHESTRATOR_FINAL_GATE_PASS
- citation_like_count: 1
- total_match_count: 50
- returned_match_count: 10
- result_was_capped: True
- latency_ms: 14.675
- false_positive: False
- false_negative: False
- preview: TRACE-Net found manual reference 25-21-00 on page t_p_120_1176_p000005 [1]. The same page/value was collapsed from 39 repeated source records. Results were capped: TRACE-Net returned 10 of 50 matching records. Available drill-downs include document, manual, revision, section, route, field_type.

### eval_v26_0004 — PASS
- query: Where is manual reference 99-99-99 used?
- expected_behavior: audit_only
- final_gate_status: LIVE_ORCHESTRATOR_AUDIT_ONLY
- citation_like_count: 0
- total_match_count: 0
- returned_match_count: 0
- result_was_capped: False
- latency_ms: 4.578
- false_positive: False
- false_negative: False
- preview: TRACE-Net did not find direct citation-ready source-truth evidence for this query. No source-truth claim is made. Try narrowing by part number, manual reference, page, or table text.

### eval_v26_0005 — PASS
- query: Search table text ILLUSTRATED PARTS LIST
- expected_behavior: final_gated_answer
- final_gate_status: LIVE_ORCHESTRATOR_FINAL_GATE_PASS
- citation_like_count: 1
- total_match_count: 10
- returned_match_count: 10
- result_was_capped: False
- latency_ms: 4.555
- false_positive: False
- false_negative: False
- preview: TRACE-Net found the exact table text "ILLUSTRATED PARTS LIST" on page t_p_120_1176_p000027 [1]. Nearby OCR/table records were returned as context only and are not treated as direct proof for this query.

### eval_v26_0006 — PASS
- query: Search table text THIS TEXT DOES NOT EXIST
- expected_behavior: audit_only
- final_gate_status: LIVE_ORCHESTRATOR_AUDIT_ONLY
- citation_like_count: 0
- total_match_count: 0
- returned_match_count: 0
- result_was_capped: False
- latency_ms: 25.063
- false_positive: False
- false_negative: False
- preview: TRACE-Net did not find direct citation-ready source-truth evidence for this query. No source-truth claim is made. Try narrowing by part number, manual reference, page, or table text.

## Quality checks
- PASS eval_query_count: observed=6 expected=>= 6
- PASS success_count: observed=6 expected=>= 6
- PASS latency_record_count: observed=6 expected=>= 6
- PASS false_positive_count: observed=0 expected=<= 0
- PASS false_negative_count: observed=0 expected=<= 0
- PASS unsupported_claim_count: observed=0 expected=<= 0
- PASS llm_call_error_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS require_no_answer_permission: observed=0 expected=== 0

report_path: `local_data\organization\trace_net\e2e_live_eval_latency_harness_v27_endpoint\trace_net_e2e_live_eval_latency_harness_v26.json`
records_jsonl_path: `local_data\organization\trace_net\e2e_live_eval_latency_harness_v27_endpoint\trace_net_e2e_live_eval_latency_harness_records_v26.jsonl`
