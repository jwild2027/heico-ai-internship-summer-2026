# TRACE-Net E2E Relationship Final Gate Hardener v30

Quality status: **PASS**
Status: `E2E_RELATIONSHIP_FINAL_GATE_HARDENER_READY`

## Summary
- relationship_final_gate_count: 11
- passed_relationship_final_gate_count: 11
- relationship_record_count: 5
- repaired_relationship_answer_count: 3
- graph_as_proof_violation_count: 1
- v2_summary_as_proof_violation_count: 1
- nomenclature_as_proof_violation_count: 1
- unsupported_relationship_claim_count: 3
- post_gate_issue_count: 0
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Contract
- Graph, Leiden, v2 summaries, and nomenclature metadata are guidance only.
- Relationship/synthesis answers may use guidance for navigation, but not as proof authority.
- Direct source-truth evidence is required for factual relationship claims.
- This gate validates and repairs relationship drafts; it does not call an LLM.

## Final gate records
### relationship_final_gate_v30_0001 — `RELATIONSHIP_FINAL_GATE_PASS`
- query: how many pages have a v2 summary
- relationship_record: False
- repaired_from_draft: False
- graph_as_proof_violation: False
- v2_summary_as_proof_violation: False
- nomenclature_as_proof_violation: False
- unsupported_relationship_claim: False
- final_answer_preview: TRACE-Net found v2 summary guidance for 509 page(s), page range t_p_120_1176_p000001 through t_p_120_1176_p000509. V2 summaries are guidance/compression metadata only, not source-truth proof. Graph metadata coverage observed separately: Has

### relationship_final_gate_v30_0002 — `RELATIONSHIP_FINAL_GATE_PASS`
- query: how many pages mention a nomenclature
- relationship_record: False
- repaired_from_draft: False
- graph_as_proof_violation: False
- v2_summary_as_proof_violation: False
- nomenclature_as_proof_violation: False
- unsupported_relationship_claim: False
- final_answer_preview: TRACE-Net found graph Has_nomenclature guidance for 11 page(s) across 385 part/entity seed(s). Graph nomenclature signals are navigation/count guidance and should be confirmed with source-truth records before factual part claims.

### relationship_final_gate_v30_0003 — `RELATIONSHIP_FINAL_GATE_PASS`
- query: find part number 120-36833-503
- relationship_record: False
- repaired_from_draft: False
- graph_as_proof_violation: False
- v2_summary_as_proof_violation: False
- nomenclature_as_proof_violation: False
- unsupported_relationship_claim: False
- final_answer_preview: TRACE-Net found part number 120-36833-503 on page t_p_120_1176_p000003 as covered_part_number [1]. The available direct source-truth evidence confirms the listing, but it does not provide enough information to describe the part physically.

### relationship_final_gate_v30_0004 — `RELATIONSHIP_FINAL_GATE_PASS`
- query: Find part number DOES-NOT-EXIST-999
- relationship_record: False
- repaired_from_draft: False
- graph_as_proof_violation: False
- v2_summary_as_proof_violation: False
- nomenclature_as_proof_violation: False
- unsupported_relationship_claim: False
- final_answer_preview: TRACE-Net did not find direct citation-ready source-truth evidence for this query. No source-truth claim is made. Try narrowing by part number, manual reference, page, table text, or a supported artifact-count field.

### relationship_final_gate_v30_0005 — `RELATIONSHIP_FINAL_GATE_PASS`
- query: What maintenance manual pages mention covered part numbers?
- relationship_record: False
- repaired_from_draft: False
- graph_as_proof_violation: False
- v2_summary_as_proof_violation: False
- nomenclature_as_proof_violation: False
- unsupported_relationship_claim: False
- final_answer_preview: TRACE-Net found covered part numbers on page(s) t_p_120_1176_p000003. Direct source-truth examples include 120-36833-001 [1]; 120-36833-003 [2]; 120-36833-005 [3]; 120-36833-501 [4]; 120-36833-503 [5]; 120-36833-507 [6]; 120-36833-509 [7]; 

### relationship_final_gate_v30_0006 — `RELATIONSHIP_FINAL_GATE_PASS`
- query: Drill down covered part numbers by page
- relationship_record: False
- repaired_from_draft: False
- graph_as_proof_violation: False
- v2_summary_as_proof_violation: False
- nomenclature_as_proof_violation: False
- unsupported_relationship_claim: False
- final_answer_preview: TRACE-Net drill-down by page: t_p_120_1176_p000003: 150. Direct source-truth examples include 120-36833-001 [1]; 120-36833-003 [2]; 120-36833-005 [3]; 120-36833-501 [4]; 120-36833-503 [5]; 120-36833-507 [6]; 120-36833-509 [7]; 120-36833-511

### relationship_final_gate_v30_0007 — `RELATIONSHIP_FINAL_GATE_PASS`
- query: What pages are related to part number 120-36833-503?
- relationship_record: True
- repaired_from_draft: False
- graph_as_proof_violation: False
- v2_summary_as_proof_violation: False
- nomenclature_as_proof_violation: False
- unsupported_relationship_claim: False
- final_answer_preview: TRACE-Net found direct source-truth seed evidence on page(s) t_p_120_1176_p000003: 120-36833-503 [1]. Leiden/graph guidance places the seed page(s) in tracenet_community_00011; candidate pages for inspection include t_p_120_1176_p000003, t_

### relationship_final_gate_v30_0008 — `RELATIONSHIP_FINAL_GATE_PASS`
- query: Which pages are in the same Leiden community as page t_p_120_1176_p000003?
- relationship_record: True
- repaired_from_draft: False
- graph_as_proof_violation: False
- v2_summary_as_proof_violation: False
- nomenclature_as_proof_violation: False
- unsupported_relationship_claim: False
- final_answer_preview: TRACE-Net is using the requested page ID as a graph-navigation seed. A page ID can seed navigation, but it is not by itself proof of a part/manual relationship. Leiden/graph guidance places the seed page(s) in tracenet_community_00011; cand

### relationship_final_gate_v30_0009 — `RELATIONSHIP_FINAL_GATE_PASS`
- query: Explain how part number 120-36833-503 relates to manual reference 25-21-00
- relationship_record: True
- repaired_from_draft: True
- graph_as_proof_violation: True
- v2_summary_as_proof_violation: False
- nomenclature_as_proof_violation: False
- unsupported_relationship_claim: True
- final_answer_preview: TRACE-Net found relationship/navigation guidance, but the available graph, Leiden, v2 summary, or nomenclature metadata is not proof authority. No factual relationship claim is made unless direct source-truth evidence supports it.

### relationship_final_gate_v30_0010 — `RELATIONSHIP_FINAL_GATE_PASS`
- query: What does the nomenclature mean for this part relationship?
- relationship_record: True
- repaired_from_draft: True
- graph_as_proof_violation: False
- v2_summary_as_proof_violation: False
- nomenclature_as_proof_violation: True
- unsupported_relationship_claim: True
- final_answer_preview: TRACE-Net found nomenclature metadata/navigation signals for this request.  Nomenclature graph signals are guidance only, not proof of a factual part/manual relationship. Direct source-truth evidence is required before making a relationship

### relationship_final_gate_v30_0011 — `RELATIONSHIP_FINAL_GATE_PASS`
- query: Does the v2 summary prove page t_p_120_1176_p000003 is related?
- relationship_record: True
- repaired_from_draft: True
- graph_as_proof_violation: False
- v2_summary_as_proof_violation: True
- nomenclature_as_proof_violation: False
- unsupported_relationship_claim: True
- final_answer_preview: TRACE-Net found relationship/navigation guidance, but the available graph, Leiden, v2 summary, or nomenclature metadata is not proof authority. No factual relationship claim is made unless direct source-truth evidence supports it.

## Quality checks
- PASS relationship_final_gate_count: observed=11 expected=>= 8
- PASS passed_relationship_final_gate_count: observed=11 expected=>= 8
- PASS relationship_record_count: observed=5 expected=>= 3
- PASS repaired_relationship_answer_count: observed=3 expected=>= 3
- PASS post_gate_issue_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS require_no_answer_permission: observed=0 expected=== 0
