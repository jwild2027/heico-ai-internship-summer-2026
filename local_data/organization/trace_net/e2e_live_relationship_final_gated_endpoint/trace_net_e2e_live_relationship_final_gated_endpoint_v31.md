# TRACE-Net E2E Live Relationship Final-Gated Endpoint v31

Quality status: **PASS**
Status: `E2E_LIVE_RELATIONSHIP_FINAL_GATED_ENDPOINT_READY`

## Summary
- sample_query_count: 10
- sample_success_count: 10
- relationship_final_gate_applied_count: 10
- relationship_record_count: 4
- repaired_relationship_sample_count: 1
- post_gate_issue_count: 0
- exact_search_document_count: 574
- page_context_v2_page_count: 509
- graph_has_v2_page_count: 52
- graph_has_nomenclature_page_count: 11
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Contract
- v29.2 metadata/count and relationship router runs first.
- v30 relationship final gate is applied before WebUI receives the answer.
- Graph, Leiden, v2 summaries, and nomenclature metadata remain guidance only.
- Source-truth evidence is required for factual relationship claims.
- The endpoint does not scan raw 5TB data, rebuild graph, mutate source truth, or write to services.

## Samples
### sample_v31_0001 — PASS
- query: how many pages have a v2 summary
- response_mode: artifact_metadata_count
- source_final_gate_status: LIVE_ORCHESTRATOR_METADATA_COUNT_PASS
- relationship_final_gate_status: RELATIONSHIP_FINAL_GATE_PASS
- relationship_final_gate_repaired: False
- post_gate_issue_count: 0
- preview: TRACE-Net found v2 summary guidance for 509 page(s), page range t_p_120_1176_p000001 through t_p_120_1176_p000509. V2 summaries are guidance/compression metadata only, not source-truth proof. Graph metadata coverage observed separately: Has_v2=52, HAS_CONTEXT/

### sample_v31_0002 — PASS
- query: how many pages mention a nomenclature
- response_mode: artifact_metadata_count
- source_final_gate_status: LIVE_ORCHESTRATOR_METADATA_COUNT_PASS
- relationship_final_gate_status: RELATIONSHIP_FINAL_GATE_PASS
- relationship_final_gate_repaired: False
- post_gate_issue_count: 0
- preview: TRACE-Net found graph Has_nomenclature guidance for 11 page(s) across 385 part/entity seed(s). Graph nomenclature signals are navigation/count guidance and should be confirmed with source-truth records before factual part claims.

### sample_v31_0003 — PASS
- query: find part number 120-36833-503
- response_mode: exact_single_value
- source_final_gate_status: LIVE_ORCHESTRATOR_FINAL_GATE_PASS
- relationship_final_gate_status: RELATIONSHIP_FINAL_GATE_PASS
- relationship_final_gate_repaired: False
- post_gate_issue_count: 0
- preview: TRACE-Net found part number 120-36833-503 on page t_p_120_1176_p000003 as covered_part_number [1]. The available direct source-truth evidence confirms the listing, but it does not provide enough information to describe the part physically.

### sample_v31_0004 — PASS
- query: Find part number DOES-NOT-EXIST-999
- response_mode: audit_only
- source_final_gate_status: LIVE_ORCHESTRATOR_AUDIT_ONLY
- relationship_final_gate_status: RELATIONSHIP_FINAL_GATE_PASS
- relationship_final_gate_repaired: False
- post_gate_issue_count: 0
- preview: TRACE-Net did not find direct citation-ready source-truth evidence for this query. No source-truth claim is made. Try narrowing by part number, manual reference, page, table text, or a supported artifact-count field.

### sample_v31_0005 — PASS
- query: What maintenance manual pages mention covered part numbers?
- response_mode: capped_listing
- source_final_gate_status: LIVE_ORCHESTRATOR_FINAL_GATE_PASS
- relationship_final_gate_status: RELATIONSHIP_FINAL_GATE_PASS
- relationship_final_gate_repaired: False
- post_gate_issue_count: 0
- preview: TRACE-Net found covered part numbers on page(s) t_p_120_1176_p000003. Direct source-truth examples include 120-36833-001 [1]; 120-36833-003 [2]; 120-36833-005 [3]; 120-36833-501 [4]; 120-36833-503 [5]; 120-36833-507 [6]; 120-36833-509 [7]; 120-36833-511 [8]; 1

### sample_v31_0006 — PASS
- query: Drill down covered part numbers by page
- response_mode: drilldown_request
- source_final_gate_status: LIVE_ORCHESTRATOR_FINAL_GATE_PASS
- relationship_final_gate_status: RELATIONSHIP_FINAL_GATE_PASS
- relationship_final_gate_repaired: False
- post_gate_issue_count: 0
- preview: TRACE-Net drill-down by page: t_p_120_1176_p000003: 150. Direct source-truth examples include 120-36833-001 [1]; 120-36833-003 [2]; 120-36833-005 [3]; 120-36833-501 [4]; 120-36833-503 [5]; 120-36833-507 [6]; 120-36833-509 [7]; 120-36833-511 [8]; 120-36833-513 

### sample_v31_0007 — PASS
- query: What pages are related to part number 120-36833-503?
- response_mode: relationship_navigation
- source_final_gate_status: LIVE_ORCHESTRATOR_RELATIONSHIP_GUIDANCE_PASS
- relationship_final_gate_status: RELATIONSHIP_FINAL_GATE_PASS
- relationship_final_gate_repaired: False
- post_gate_issue_count: 0
- preview: TRACE-Net found direct source-truth seed evidence on page(s) t_p_120_1176_p000003: 120-36833-503 [1]. Leiden/graph guidance places the seed page(s) in tracenet_community_00011; candidate pages for inspection include t_p_120_1176_p000003, t_p_120_1176_p000208, 

### sample_v31_0008 — PASS
- query: Which pages are in the same Leiden community as page t_p_120_1176_p000003?
- response_mode: relationship_navigation
- source_final_gate_status: LIVE_ORCHESTRATOR_RELATIONSHIP_GUIDANCE_PASS
- relationship_final_gate_status: RELATIONSHIP_FINAL_GATE_PASS
- relationship_final_gate_repaired: False
- post_gate_issue_count: 0
- preview: TRACE-Net is using the requested page ID as a graph-navigation seed. A page ID can seed navigation, but it is not by itself proof of a part/manual relationship. Leiden/graph guidance places the seed page(s) in tracenet_community_00011; candidate pages for insp

### sample_v31_0009 — PASS
- query: Explain how part number 120-36833-503 relates to manual reference 25-21-00
- response_mode: relationship_synthesis
- source_final_gate_status: LIVE_ORCHESTRATOR_RELATIONSHIP_GUIDANCE_PASS
- relationship_final_gate_status: RELATIONSHIP_FINAL_GATE_PASS
- relationship_final_gate_repaired: False
- post_gate_issue_count: 0
- preview: TRACE-Net found direct source-truth seed evidence on page(s) t_p_120_1176_p000003: 120-36833-503 [1]. Leiden/graph guidance places the seed page(s) in tracenet_community_00011; candidate pages for inspection include t_p_120_1176_p000003, t_p_120_1176_p000208, 

### sample_v31_0010 — PASS
- query: Synthetic unsafe relationship draft smoke
- response_mode: relationship_synthesis
- source_final_gate_status: None
- relationship_final_gate_status: RELATIONSHIP_FINAL_GATE_PASS
- relationship_final_gate_repaired: True
- post_gate_issue_count: 0
- preview: TRACE-Net found relationship/navigation guidance, but the available graph, Leiden, v2 summary, or nomenclature metadata is not proof authority. No factual relationship claim is made unless direct source-truth evidence supports it.

## Quality checks
- PASS sample_query_count: observed=10 expected=>= 8
- PASS sample_success_count: observed=10 expected=>= 8
- PASS relationship_final_gate_applied_count: observed=10 expected=>= 8
- PASS relationship_record_count: observed=4 expected=>= 2
- PASS post_gate_issue_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS contract_relationship_final_gate_live_endpoint: observed=True expected=is True
- PASS contract_raw_5tb_scan_at_query_time: observed=False expected=is False
- PASS require_no_answer_permission: observed=0 expected=== 0
