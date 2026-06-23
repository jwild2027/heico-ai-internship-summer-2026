# TRACE-Net E2E Live LLM Prompt Contract v21

Quality status: **PASS**
Status: `E2E_LIVE_LLM_PROMPT_CONTRACT_READY_FOR_LLM_DRAFT`

## Summary
- context_pack_count: 5
- prompt_contract_count: 5
- ready_prompt_contract_count: 5
- total_prompt_message_count: 15
- contracts_with_source_truth_evidence_count: 5
- contracts_with_graph_guidance_count: 5
- contracts_with_v2_summary_guidance_count: 5
- contracts_with_aggregation_or_cap_disclosure_count: 5
- contracts_with_self_rag_ready_count: 5
- contracts_with_crag_no_retry_count: 5
- graph_proof_authority_violation_count: 0
- summary_proof_authority_violation_count: 0
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Contract
- This stage builds LLM-ready prompt messages but does not call an LLM.
- Source-truth evidence is the only proof authority.
- Graph/Leiden and v2 summaries are guidance only.
- Capped/high-degree results must be disclosed to the LLM.
- The LLM reads compact context packs, not raw 5TB corpus data or the full graph.

## Prompt contracts
### llm_prompt_contract_v21_0001 — `PROMPT_CONTRACT_READY_FOR_LLM_DRAFT`
- query: Find part number 120-36834-509
- evidence_item_count: 1
- has_graph_guidance: True
- has_v2_summary_guidance: True
- has_aggregation_or_cap_disclosure: True

### llm_prompt_contract_v21_0002 — `PROMPT_CONTRACT_READY_FOR_LLM_DRAFT`
- query: Find part number 120-36833-501
- evidence_item_count: 1
- has_graph_guidance: True
- has_v2_summary_guidance: True
- has_aggregation_or_cap_disclosure: True

### llm_prompt_contract_v21_0003 — `PROMPT_CONTRACT_READY_FOR_LLM_DRAFT`
- query: What maintenance manual pages mention covered part numbers?
- evidence_item_count: 10
- has_graph_guidance: True
- has_v2_summary_guidance: True
- has_aggregation_or_cap_disclosure: True

### llm_prompt_contract_v21_0004 — `PROMPT_CONTRACT_READY_FOR_LLM_DRAFT`
- query: Where is manual reference 25-21-00 used?
- evidence_item_count: 1
- has_graph_guidance: True
- has_v2_summary_guidance: True
- has_aggregation_or_cap_disclosure: True

### llm_prompt_contract_v21_0005 — `PROMPT_CONTRACT_READY_FOR_LLM_DRAFT`
- query: Search table text MAINTENANCE MANUAL WITH
- evidence_item_count: 9
- has_graph_guidance: True
- has_v2_summary_guidance: True
- has_aggregation_or_cap_disclosure: True

## Quality checks
- PASS context_pack_count: observed=5 expected=>= 5
- PASS prompt_contract_count: observed=5 expected=>= 5
- PASS ready_prompt_contract_count: observed=5 expected=>= 5
- PASS total_prompt_message_count: observed=15 expected=>= 15
- PASS contracts_with_source_truth_evidence_count: observed=5 expected=>= 5
- PASS contracts_with_graph_guidance_count: observed=5 expected=>= 5
- PASS contracts_with_v2_summary_guidance_count: observed=5 expected=>= 5
- PASS contracts_with_aggregation_or_cap_disclosure_count: observed=5 expected=>= 5
- PASS contracts_with_self_rag_ready_count: observed=5 expected=>= 5
- PASS contracts_with_crag_no_retry_count: observed=5 expected=>= 5
- PASS contracts_with_answer_rules_count: observed=5 expected=>= 5
- PASS graph_proof_authority_violation_count: observed=0 expected=<= 0
- PASS summary_proof_authority_violation_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS require_no_answer_permission: observed=0 expected=== 0
