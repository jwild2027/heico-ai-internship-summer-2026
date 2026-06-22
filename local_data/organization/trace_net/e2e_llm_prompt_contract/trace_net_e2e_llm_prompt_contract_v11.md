# TRACE-Net E2E LLM Prompt Contract v11

Quality status: **PASS**
Status: `E2E_LLM_PROMPT_CONTRACT_READY_FOR_REASONED_DRAFT`

## Contract
This prompt-contract stage creates LLM-ready messages only. It does not call an LLM, rerun retrieval, rerun OCR, rebuild embeddings, rebuild graph, rerun table extraction, mutate source truth, or write to services.

## Summary
- context_pack_count: 5
- prompt_contract_count: 5
- ready_prompt_contract_count: 5
- total_prompt_message_count: 15
- contracts_with_source_truth_evidence_count: 5
- contracts_with_guidance_box_count: 5
- contracts_with_self_rag_ready_count: 5
- contracts_with_crag_no_retry_count: 5
- contracts_with_graph_or_summary_guidance_count: 5
- graph_summary_proof_violation_count: 0
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Prompt contracts
- **LLM_PROMPT_CONTRACT_READY** `llm_prompt_contract_v11_0001` | covered_part_number | Find part number 120-36833-001 | messages=3 evidence=5 guidance=7
- **LLM_PROMPT_CONTRACT_READY** `llm_prompt_contract_v11_0002` | covered_part_number | Find part number 120-36834-509 | messages=3 evidence=5 guidance=7
- **LLM_PROMPT_CONTRACT_READY** `llm_prompt_contract_v11_0003` | manual_page_reference | Where is manual reference 25-21-00 used? | messages=3 evidence=5 guidance=10
- **LLM_PROMPT_CONTRACT_READY** `llm_prompt_contract_v11_0004` | table_text | Search table text MAINTENANCE MANUAL WITH | messages=3 evidence=5 guidance=11
- **LLM_PROMPT_CONTRACT_READY** `llm_prompt_contract_v11_0005` | covered_part_number | What maintenance manual pages mention covered part numbers? | messages=3 evidence=5 guidance=7

## Quality checks
- PASS quality_status: observed=PASS expected=== PASS
- PASS context_pack_count: observed=5 expected=>= 5
- PASS prompt_contract_count: observed=5 expected=>= 5
- PASS ready_prompt_contract_count: observed=5 expected=>= 5
- PASS total_prompt_message_count: observed=15 expected=>= 15
- PASS contracts_with_source_truth_evidence_count: observed=5 expected=>= 5
- PASS contracts_with_guidance_box_count: observed=5 expected=>= 5
- PASS contracts_with_self_rag_ready_count: observed=5 expected=>= 5
- PASS contracts_with_crag_no_retry_count: observed=5 expected=>= 5
- PASS contracts_with_graph_or_summary_guidance_count: observed=5 expected=>= 5
- PASS graph_summary_proof_violation_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS contract_can_answer_directly: observed=0 expected=== 0
- PASS contract_can_prove_claims: observed=0 expected=== 0
- PASS postgres_write_attempt_count: observed=0 expected=== 0
- PASS qdrant_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_write_attempt_count: observed=0 expected=== 0
- PASS require_no_answer_permission: observed=0 expected=== 0
