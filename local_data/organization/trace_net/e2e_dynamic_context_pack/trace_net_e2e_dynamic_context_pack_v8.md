# TRACE-Net E2E Dynamic Context Pack v8

Quality status: **PASS**
Status: `E2E_DYNAMIC_CONTEXT_PACK_READY_FOR_SELF_RAG`

## Context engineering assessment
Dynamic context pack v8 separates source-truth evidence, guidance-only graph/vector/summary/route signals, and answer rules so a downstream LLM can reason without treating guidance as proof.

## Summary
- context_pack_count: 5
- ready_context_pack_count: 5
- total_evidence_item_count: 25
- packs_with_evidence_box_count: 5
- packs_with_guidance_box_count: 5
- packs_with_rules_box_count: 5
- packs_with_graph_or_summary_guidance_count: 5
- guidance_item_count: 42
- answer_permission_count: 0
- can_answer_directly_count: 0
- can_prove_claims_count: 0
- source_truth_mutation_allowed_count: 0

## Artifact states
- **PASS** `dynamic_tunnel_ranker` purpose=dynamic_ranker_source quality=PASS records=5
- **PASS** `dynamic_query_tunnels` purpose=tunnel_plan_source quality=PASS records=5
- **PASS** `table_exact_search_adapter` purpose=source_truth_evidence quality=PASS records=1497
- **PASS** `table_hybrid_retrieval_bridge` purpose=ranking_guidance quality=PASS records=1497
- **PASS** `page_retrieval_profiles` purpose=semantic_profile_guidance quality=UNKNOWN records=509
- **PASS** `page_context_v2` purpose=page_summary_guidance quality=PASS records=509
- **PASS** `leiden_communities` purpose=graph_community_guidance quality=PASS records=229
- **PASS** `community_navigation_metadata_bridge` purpose=graph_navigation_guidance quality=PASS records=0
- **PASS** `route_dispatch_manifest` purpose=route_metadata_guidance quality=PASS records=0
- **PASS** `table_route_retrieval_handoff_summary` purpose=table_route_guidance quality=PASS records=0

## Context packs

### Find part number 120-36833-001
- intent: `covered_part_number`
- status: `DYNAMIC_CONTEXT_PACK_READY`
- evidence items: 5
- guidance items: 7
- graph/summary guidance: True
  - evidence: covered_part_number=120-36833-001 on t_p_120_1176_p000003 score=319
  - evidence: covered_part_number=120-36833-003 on t_p_120_1176_p000003 score=199
  - evidence: covered_part_number=120-36833-005 on t_p_120_1176_p000003 score=199

### Find part number 120-36834-509
- intent: `covered_part_number`
- status: `DYNAMIC_CONTEXT_PACK_READY`
- evidence items: 5
- guidance items: 7
- graph/summary guidance: True
  - evidence: covered_part_number=120-36834-509 on t_p_120_1176_p000003 score=319
  - evidence: covered_part_number=120-36833-001 on t_p_120_1176_p000003 score=199
  - evidence: covered_part_number=120-36833-003 on t_p_120_1176_p000003 score=199

### Where is manual reference 25-21-00 used?
- intent: `manual_page_reference`
- status: `DYNAMIC_CONTEXT_PACK_READY`
- evidence items: 5
- guidance items: 10
- graph/summary guidance: True
  - evidence: manual_page_reference=25-21-00 on t_p_120_1176_p000005 score=319
  - evidence: ipl_part_number=25-21-00 on t_p_120_1176_p000027 score=299
  - evidence: ipl_part_number=25-21-00 on t_p_120_1176_p000028 score=299

### Search table text MAINTENANCE MANUAL WITH
- intent: `table_text`
- status: `DYNAMIC_CONTEXT_PACK_READY`
- evidence items: 5
- guidance items: 11
- graph/summary guidance: True
  - evidence: ipl_text=MAINTENANCE MANUAL WITH on t_p_120_1176_p000027 score=319
  - evidence: ipl_text=MAINTENANCE MANUAL WITH on t_p_120_1176_p000028 score=319
  - evidence: ipl_text=MAINTENANCE MANUAL WITH on t_p_120_1176_p000029 score=319

### What maintenance manual pages mention covered part numbers?
- intent: `covered_part_number`
- status: `DYNAMIC_CONTEXT_PACK_READY`
- evidence items: 5
- guidance items: 7
- graph/summary guidance: True
  - evidence: covered_part_number=120-36833-001 on t_p_120_1176_p000003 score=199
  - evidence: covered_part_number=120-36833-003 on t_p_120_1176_p000003 score=199
  - evidence: covered_part_number=120-36833-005 on t_p_120_1176_p000003 score=199

## Quality checks
- PASS context_pack_count: observed=5 expected=>= 5
- PASS ready_context_pack_count: observed=5 expected=>= 5
- PASS total_evidence_item_count: observed=25 expected=>= 10
- PASS packs_with_evidence_box_count: observed=5 expected=>= 5
- PASS packs_with_guidance_box_count: observed=5 expected=>= 5
- PASS packs_with_rules_box_count: observed=5 expected=>= 5
- PASS packs_with_graph_or_summary_guidance_count: observed=5 expected=>= 5
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS contract_answer_permission: observed=0 expected=== 0
- PASS contract_can_answer_directly: observed=0 expected=== 0
- PASS contract_can_prove_claims: observed=0 expected=== 0
