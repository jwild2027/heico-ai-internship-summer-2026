# TRACE-Net E2E Self-RAG Context Critic v9

Quality status: **PASS**
Status: `E2E_SELF_RAG_CONTEXT_CRITIC_READY_FOR_CRAG_OR_PROMPT`

## Summary
- context_pack_count: 5
- self_rag_critique_count: 5
- ready_context_count: 5
- weak_context_count: 0
- needs_crag_retry_count: 0
- human_review_count: 0
- contexts_with_source_truth_evidence_count: 5
- contexts_with_guidance_separation_count: 5
- contexts_with_graph_or_summary_guidance_count: 5
- graph_summary_proof_violation_count: 0
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Critiques
- **SELF_RAG_CONTEXT_READY** `dynamic_context_pack_v8_0001` | intent=covered_part_number | evidence=5 | relevant=5 | warnings=0 | blockers=0
- **SELF_RAG_CONTEXT_READY** `dynamic_context_pack_v8_0002` | intent=covered_part_number | evidence=5 | relevant=5 | warnings=0 | blockers=0
- **SELF_RAG_CONTEXT_READY** `dynamic_context_pack_v8_0003` | intent=manual_page_reference | evidence=5 | relevant=5 | warnings=0 | blockers=0
- **SELF_RAG_CONTEXT_READY** `dynamic_context_pack_v8_0004` | intent=table_text | evidence=5 | relevant=5 | warnings=0 | blockers=0
- **SELF_RAG_CONTEXT_READY** `dynamic_context_pack_v8_0005` | intent=covered_part_number | evidence=5 | relevant=5 | warnings=0 | blockers=0

## Quality checks
- PASS context_pack_count: observed=5 expected=>= 5
- PASS self_rag_critique_count: observed=5 expected=>= 5
- PASS ready_context_count: observed=5 expected=>= 5
- PASS contexts_with_source_truth_evidence_count: observed=5 expected=>= 5
- PASS contexts_with_guidance_separation_count: observed=5 expected=>= 5
- PASS human_review_count: observed=0 expected=<= 0
- PASS graph_summary_proof_violation_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS contract_answer_permission: observed=0 expected=== 0
- PASS contract_can_answer_directly: observed=0 expected=== 0
- PASS contract_can_prove_claims: observed=0 expected=== 0
- PASS needs_crag_retry_count: observed=0 expected=<= 0
- PASS require_no_answer_permission: observed=0 expected=== 0
