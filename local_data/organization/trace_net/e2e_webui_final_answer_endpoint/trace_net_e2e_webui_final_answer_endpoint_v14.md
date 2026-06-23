# TRACE-Net E2E WebUI Final Answer Endpoint v14

Quality status: **PASS**
Status: `E2E_WEBUI_FINAL_ANSWER_ENDPOINT_READY`

## Contract
This endpoint serves final-gated answer artifacts to Open WebUI. It does not call an LLM, rerun retrieval, rerun OCR, rebuild embeddings, rebuild graph, rerun table extraction, mutate source truth, or write to services.

## Connection
- Windows/Git Bash test base URL: `http://127.0.0.1:8017/v1`
- Open WebUI Docker base URL: `http://host.docker.internal:8017/v1`
- Model: `trace-net-e2e-webui-final-answer-endpoint-v14`

## Summary
- final_answer_count: 5
- ready_final_answer_count: 5
- total_citation_count: 25
- final_answers_ready_for_webui_count: 5
- unsupported_claim_count: 0
- graph_summary_proof_violation_count: 0
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Ready final answers
- **WEBUI_FINAL_ANSWER_READY** `final_answer_gate_v13_0001` | covered_part_number | Find part number 120-36833-001 | citations=5
- **WEBUI_FINAL_ANSWER_READY** `final_answer_gate_v13_0002` | covered_part_number | Find part number 120-36834-509 | citations=5
- **WEBUI_FINAL_ANSWER_READY** `final_answer_gate_v13_0003` | manual_page_reference | Where is manual reference 25-21-00 used? | citations=5
- **WEBUI_FINAL_ANSWER_READY** `final_answer_gate_v13_0004` | table_text | Search table text MAINTENANCE MANUAL WITH | citations=5
- **WEBUI_FINAL_ANSWER_READY** `final_answer_gate_v13_0005` | covered_part_number | What maintenance manual pages mention covered part numbers? | citations=5

## Quality checks
- PASS final_answer_count: observed=5 expected=>= 5
- PASS ready_final_answer_count: observed=5 expected=>= 5
- PASS total_citation_count: observed=25 expected=>= 15
- PASS endpoint_route_count: observed=4 expected=>= 4
- PASS unsupported_claim_count: observed=0 expected=<= 0
- PASS graph_summary_proof_violation_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS contract_can_answer_directly: observed=0 expected=== 0
- PASS contract_can_prove_claims: observed=0 expected=== 0
- PASS postgres_write_attempt_count: observed=0 expected=== 0
- PASS qdrant_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_write_attempt_count: observed=0 expected=== 0
- PASS require_no_answer_permission: observed=0 expected=== 0
