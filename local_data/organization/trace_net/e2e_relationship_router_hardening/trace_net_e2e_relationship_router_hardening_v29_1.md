# TRACE-Net E2E Relationship Router Hardening v29.1

Quality status: **PASS**
Status: `E2E_RELATIONSHIP_ROUTER_HARDENING_READY`

## Summary
- exact_search_document_count: 574
- page_context_v2_page_count: 509
- graph_has_v2_page_count: 51
- graph_has_nomenclature_page_count: 0
- sample_query_count: 8
- sample_success_count: 8
- metadata_count_sample_count: 2
- bad_broad_fallback_count: 0
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Contract
- Metadata/count questions route before broad source-truth fallback.
- Graph Has_v2 and Has_nomenclature/Has_nomeclature signals are supported when available.
- V2 summaries and graph signals are guidance/metadata, not source-truth proof.
- Unknown metadata/field questions return audit-only instead of unrelated covered part records.

## Samples
### router_hardening_sample_0001 — PASS
- query: how many pages have a v2 summary
- query_intent: artifact_v2_summary_count
- response_mode: artifact_metadata_count
- final_gate_status: LIVE_ORCHESTRATOR_METADATA_COUNT_PASS
- metadata_count_router_used: True
- bad_broad_fallback_blocked: True
- preview: TRACE-Net found v2 summary guidance for 51 page(s), page range t_p_120_1176_p000001 through t_p_120_1176_p000051. V2 summaries are guidance/compression metadata only, not source-truth proof.

### router_hardening_sample_0002 — PASS
- query: how many pages mention a nomenclature
- query_intent: field_or_graph_nomenclature_count
- response_mode: audit_only
- final_gate_status: LIVE_ORCHESTRATOR_AUDIT_ONLY
- metadata_count_router_used: True
- bad_broad_fallback_blocked: True
- preview: TRACE-Net did not find direct citation-ready source-truth evidence for this query. No source-truth claim is made. Try narrowing by part number, manual reference, page, table text, or a supported artifact-count field.

### router_hardening_sample_0003 — PASS
- query: find part number 120-36833-503
- query_intent: exact_part_number
- response_mode: exact_single_value
- final_gate_status: LIVE_ORCHESTRATOR_FINAL_GATE_PASS
- metadata_count_router_used: False
- bad_broad_fallback_blocked: True
- preview: TRACE-Net found part number 120-36833-503 on page t_p_120_1176_p000003 as covered_part_number [1]. The available direct source-truth evidence confirms the listing, but it does not provide enough information to describe the part physically.

### router_hardening_sample_0004 — PASS
- query: Find part number DOES-NOT-EXIST-999
- query_intent: exact_part_number
- response_mode: audit_only
- final_gate_status: LIVE_ORCHESTRATOR_AUDIT_ONLY
- metadata_count_router_used: False
- bad_broad_fallback_blocked: True
- preview: TRACE-Net did not find direct citation-ready source-truth evidence for this query. No source-truth claim is made. Try narrowing by part number, manual reference, page, table text, or a supported artifact-count field.

### router_hardening_sample_0005 — PASS
- query: What maintenance manual pages mention covered part numbers?
- query_intent: field_listing_covered_part_number
- response_mode: capped_listing
- final_gate_status: LIVE_ORCHESTRATOR_FINAL_GATE_PASS
- metadata_count_router_used: False
- bad_broad_fallback_blocked: True
- preview: TRACE-Net found covered part numbers on page(s) t_p_120_1176_p000003. Direct source-truth examples include 120-36833-001 [1]; 120-36833-003 [2]; 120-36833-005 [3]; 120-36833-501 [4]; 120-36833-503 [5]; 120-36833-507 [6]; 120-36833-509 [7]; 120-36833-511 [8]; 1

### router_hardening_sample_0006 — PASS
- query: Drill down covered part numbers by page
- query_intent: drilldown_covered_part_numbers_by_page
- response_mode: drilldown_request
- final_gate_status: LIVE_ORCHESTRATOR_FINAL_GATE_PASS
- metadata_count_router_used: False
- bad_broad_fallback_blocked: True
- preview: TRACE-Net drill-down by page: t_p_120_1176_p000003: 150. Direct source-truth examples include 120-36833-001 [1]; 120-36833-003 [2]; 120-36833-005 [3]; 120-36833-501 [4]; 120-36833-503 [5]; 120-36833-507 [6]; 120-36833-509 [7]; 120-36833-511 [8]; 120-36833-513 

### router_hardening_sample_0007 — PASS
- query: What pages are related to part number 120-36833-503?
- query_intent: relationship_for_part
- response_mode: relationship_navigation
- final_gate_status: LIVE_ORCHESTRATOR_RELATIONSHIP_GUIDANCE_PASS
- metadata_count_router_used: False
- bad_broad_fallback_blocked: True
- preview: TRACE-Net found direct source-truth seed evidence on page(s) t_p_120_1176_p000003: 120-36833-503 [1]. Leiden/graph guidance places the seed page(s) in tracenet_community_00011; candidate pages for inspection include t_p_120_1176_p000003, t_p_120_1176_p000208, 

### router_hardening_sample_0008 — PASS
- query: Which pages are in the same Leiden community as page t_p_120_1176_p000003?
- query_intent: relationship_for_page
- response_mode: relationship_navigation
- final_gate_status: LIVE_ORCHESTRATOR_RELATIONSHIP_GUIDANCE_PASS
- metadata_count_router_used: False
- bad_broad_fallback_blocked: True
- preview: TRACE-Net is using the requested page ID as a graph-navigation seed. A page ID can seed navigation, but it is not by itself proof of a part/manual relationship. Leiden/graph guidance places the seed page(s) in tracenet_community_00011; candidate pages for insp

## Quality checks
- PASS exact_search_document_count: observed=574 expected=>= 10
- PASS endpoint_route_count: observed=4 expected=>= 4
- PASS sample_query_count: observed=8 expected=>= 8
- PASS sample_success_count: observed=8 expected=>= 8
- PASS metadata_count_sample_count: observed=2 expected=>= 2
- PASS bad_broad_fallback_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS contract_raw_5tb_scan_at_query_time: observed=False expected=is False
- PASS contract_metadata_count_router_before_source_truth_fallback: observed=True expected=is True
- PASS require_no_answer_permission: observed=0 expected=== 0
