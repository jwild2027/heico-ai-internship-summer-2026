# TRACE-Net E2E Live LLM Draft Adapter v22

Quality status: **PASS**
Status: `E2E_LIVE_LLM_DRAFT_ADAPTER_READY_FOR_FINAL_GATE`

## Summary
- prompt_contract_count: 5
- ready_prompt_contract_count: 5
- llm_draft_count: 5
- drafts_ready_for_final_gate_count: 5
- drafts_with_nonempty_content_count: 5
- source_truth_supported_prompt_count: 5
- successful_llm_call_count: 5
- live_llm_call_count: 5
- simulated_llm_draft_count: 0
- llm_call_error_count: 0
- drafts_with_citation_like_tokens_count: 5
- drafts_needing_cap_disclosure_count: 3
- drafts_with_cap_disclosure_detected_count: 3
- llm_reasoning_omitted_count: 5
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Contract
- This stage may call the configured LLM, but the output is only a draft.
- The draft must pass a later TRACE-Net final gate before WebUI final answer use.
- The LLM receives compact v21 context packs, not the raw 5TB corpus or full graph.
- Source-truth evidence remains the only proof authority; graph/Leiden and v2 summaries remain guidance only.
- Any provider reasoning field is stored as metadata only and is not passed as answer text.

## Drafts
### llm_draft_v22_0001 — `LLM_DRAFT_READY_FOR_FINAL_GATE`
- query: Find part number 120-36834-509
- mode/model: ollama / gemma4:26b
- llm_call_status: LLM_CALL_SUCCEEDED
- ready_for_final_gate: True
- citation_like_count: 1
- draft_preview: Part number 120-36834-509 is identified as a covered part number on page t_p_120_1176_p000003 [1]. No further descriptions for this part are provided in the available evidence.

### llm_draft_v22_0002 — `LLM_DRAFT_READY_FOR_FINAL_GATE`
- query: Find part number 120-36833-501
- mode/model: ollama / gemma4:26b
- llm_call_status: LLM_CALL_SUCCEEDED
- ready_for_final_gate: True
- citation_like_count: 1
- draft_preview: Part number 120-36833-501 is identified as a covered part number on page t_p_120_1176_p000003 [1]. No further physical descriptions or details for this part are provided in the available evidence.

### llm_draft_v22_0003 — `LLM_DRAFT_READY_FOR_FINAL_GATE`
- query: What maintenance manual pages mention covered part numbers?
- mode/model: ollama / gemma4:26b
- llm_call_status: LLM_CALL_SUCCEEDED
- ready_for_final_gate: True
- citation_like_count: 10
- draft_preview: The maintenance manual page **t_p_120_1176_p000003** mentions the following covered part numbers:  *   120-36833-001 [1] *   120-36833-003 [2] *   120-36833-005 [3] *   120-36833-501 [4] *   120-36833-503 [5] *   120-36833-507 [6] *   120-36833-509 [7] *   120-36833-511 [8] *   1

### llm_draft_v22_0004 — `LLM_DRAFT_READY_FOR_FINAL_GATE`
- query: Where is manual reference 25-21-00 used?
- mode/model: ollama / gemma4:26b
- llm_call_status: LLM_CALL_SUCCEEDED
- ready_for_final_gate: True
- citation_like_count: 1
- draft_preview: Manual reference 25-21-00 is found on page `t_p_120_1176_p000005` [1]. This page appears to be a parts list and index from a maintenance manual [V2 Summary Guidance].  Please note that the provided results are capped, and additional matching evidence may exist.

### llm_draft_v22_0005 — `LLM_DRAFT_READY_FOR_FINAL_GATE`
- query: Search table text MAINTENANCE MANUAL WITH
- mode/model: ollama / gemma4:26b
- llm_call_status: LLM_CALL_SUCCEEDED
- ready_for_final_gate: True
- citation_like_count: 4
- draft_preview: The text "MAINTENANCE MANUAL WITH" is found on page `t_p_120_1176_p000027` [1].   Other text present on the same page includes: * "ILLUSTRATED PARTS LIST" [2] * "STOCK" [4] * "NUMBER en" [6]  Please note that the provided results are capped, and additional matching evidence may e

## Quality checks
- PASS prompt_contract_count: observed=5 expected=>= 5
- PASS llm_draft_count: observed=5 expected=>= 5
- PASS drafts_ready_for_final_gate_count: observed=5 expected=>= 5
- PASS drafts_with_nonempty_content_count: observed=5 expected=>= 5
- PASS source_truth_supported_prompt_count: observed=5 expected=>= 5
- PASS successful_llm_call_count: observed=5 expected=>= 5
- PASS live_llm_call_count: observed=5 expected=>= 5
- PASS simulated_llm_draft_count: observed=0 expected=>= 0
- PASS llm_call_error_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS require_no_answer_permission: observed=0 expected=== 0
