# TRACE-Net E2E Live Self-RAG + CRAG Evaluator v20

Quality status: **PASS**
Status: `E2E_LIVE_SELF_RAG_CRAG_EVALUATOR_READY_FOR_LIVE_LLM_PROMPT`

## Summary
- context_pack_count: 5
- self_rag_evaluation_count: 5
- crag_plan_count: 5
- ready_for_llm_count: 5
- ready_with_cap_disclosure_count: 3
- retry_required_count: 0
- audit_only_count: 0
- contexts_with_source_truth_evidence_count: 5
- contexts_with_graph_guidance_count: 5
- contexts_with_v2_summary_guidance_count: 5
- contexts_with_aggregation_or_cap_disclosure_count: 5
- graph_proof_authority_violation_count: 0
- summary_proof_authority_violation_count: 0
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Contract
- Self-RAG evaluates evidence sufficiency before the LLM sees a context pack.
- CRAG plans retries or drill-down handling only when needed.
- Graph/Leiden and v2 summaries remain guidance only, not proof authority.
- Capped/high-degree results require disclosure and drill-down options.
- Query time must not scan raw 5TB source data or rebuild the graph.

## Records
### self_rag_crag_v20_0001 — `CONTEXT_READY_FOR_LLM`
- query: Find part number 120-36834-509
- context_pack_id: `context_pack_v19_0001`
- ready_for_llm_prompt: True
- crag_status: `CRAG_NO_RETRY_NEEDED`
- source_truth_evidence_count: 1
- graph_guidance_count: 1
- v2_summary_guidance_count: 1
- cap_disclosure: False

### self_rag_crag_v20_0002 — `CONTEXT_READY_FOR_LLM`
- query: Find part number 120-36833-501
- context_pack_id: `context_pack_v19_0002`
- ready_for_llm_prompt: True
- crag_status: `CRAG_NO_RETRY_NEEDED`
- source_truth_evidence_count: 1
- graph_guidance_count: 1
- v2_summary_guidance_count: 1
- cap_disclosure: False

### self_rag_crag_v20_0003 — `CONTEXT_READY_WITH_CAP_DISCLOSURE`
- query: What maintenance manual pages mention covered part numbers?
- context_pack_id: `context_pack_v19_0003`
- ready_for_llm_prompt: True
- crag_status: `CRAG_NO_RETRY_NEEDED_PRESERVE_CAP_DISCLOSURE`
- source_truth_evidence_count: 10
- graph_guidance_count: 1
- v2_summary_guidance_count: 1
- cap_disclosure: True

### self_rag_crag_v20_0004 — `CONTEXT_READY_WITH_CAP_DISCLOSURE`
- query: Where is manual reference 25-21-00 used?
- context_pack_id: `context_pack_v19_0004`
- ready_for_llm_prompt: True
- crag_status: `CRAG_NO_RETRY_NEEDED_PRESERVE_CAP_DISCLOSURE`
- source_truth_evidence_count: 10
- graph_guidance_count: 1
- v2_summary_guidance_count: 1
- cap_disclosure: True

### self_rag_crag_v20_0005 — `CONTEXT_READY_WITH_CAP_DISCLOSURE`
- query: Search table text MAINTENANCE MANUAL WITH
- context_pack_id: `context_pack_v19_0005`
- ready_for_llm_prompt: True
- crag_status: `CRAG_NO_RETRY_NEEDED_PRESERVE_CAP_DISCLOSURE`
- source_truth_evidence_count: 10
- graph_guidance_count: 1
- v2_summary_guidance_count: 1
- cap_disclosure: True

## Quality checks
- PASS context_pack_count: observed=5 expected=>= 5
- PASS self_rag_evaluation_count: observed=5 expected=>= 5
- PASS crag_plan_count: observed=5 expected=>= 5
- PASS ready_for_llm_count: observed=5 expected=>= 5
- PASS contexts_with_source_truth_evidence_count: observed=5 expected=>= 5
- PASS contexts_with_graph_guidance_count: observed=5 expected=>= 5
- PASS contexts_with_v2_summary_guidance_count: observed=5 expected=>= 5
- PASS contexts_with_aggregation_or_cap_disclosure_count: observed=5 expected=>= 5
- PASS retry_required_count: observed=0 expected=<= 0
- PASS audit_only_count: observed=0 expected=<= 0
- PASS graph_proof_authority_violation_count: observed=0 expected=<= 0
- PASS summary_proof_authority_violation_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS contract_raw_5tb_scan_at_query_time: observed=False expected=is False False
- PASS contract_graph_rebuild_at_query_time: observed=False expected=is False False
- PASS require_no_answer_permission: observed=0 expected=== 0
