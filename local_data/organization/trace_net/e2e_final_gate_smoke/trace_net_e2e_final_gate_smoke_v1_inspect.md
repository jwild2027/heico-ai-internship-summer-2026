# TRACE-Net E2E Final Gate Smoke v1 Inspect

Quality status: **PASS**

## Purpose
This artifact turns sufficiency-gated context packs into citation-backed response drafts or audit-only responses.
It is intentionally conservative: the smoke draft does not mutate source truth, prove claims, or grant direct answer authority.

## Final gate smoke contract
- purpose: Create citation-backed final-gate smoke response drafts or audit-only responses from sufficiency-gated context packs.
- response_permission: draft_for_review_or_audit_only
- answer_authority: blocked_in_smoke_draft
- safety_note: This smoke artifact demonstrates response shaping but does not grant direct answer/proof authority.
- can_answer_directly: False
- can_prove_claims: False
- source_truth_mutation_allowed: False
- writes_to_postgres: False
- writes_to_qdrant: False
- writes_to_opensearch: False
- uploads_to_opensearch: False
- ready_for_api_or_audit_response: True

## Main counters
- source_gate_record_count: 5
- final_gate_record_count: 5
- safe_response_draft_count: 5
- citation_backed_response_draft_count: 5
- audit_only_response_count: 0
- total_citation_count: 15
- page_with_citation_count: 6
- field_count: 5
- schema_missing_required_key_record_count: 0

## Field counts
- covered_part_number: 6
- ipl_figure_item_or_quantity: 3
- ipl_part_number: 2
- ipl_text: 3
- manual_page_reference: 1

## Safety/write counters
- unsafe_final_gate_smoke_record_count: 0
- answer_permission_count: 0
- can_answer_directly_count: 0
- can_prove_claims_count: 0
- source_truth_mutation_allowed_count: 0
- postgres_write_attempt_count: 0
- qdrant_write_attempt_count: 0
- opensearch_write_attempt_count: 0
- opensearch_upload_attempt_count: 0

## Final gate records
- e2e_query_v1_0001 | covered_part_number | FINAL_GATE_SAFE_CITATION_BACKED_RESPONSE_DRAFT | citations=3
  - draft: Final-gate smoke draft for query: 'Find part number 120-36833-001'. TRACE-Net found citation/source-trace-ready evidence: covered_part_number=120-36833-001 on t_p_120_1176_p000003; covered_part_number=120-36833-003 on t_p_120_1176_p000003; ...
  - cite_e2e_query_v1_0001_t_p_120_1176_p000003_covered_part_number_001 | t_p_120_1176_p000003 | covered_part_number | 120-36833-001
  - cite_e2e_query_v1_0001_t_p_120_1176_p000003_covered_part_number_002 | t_p_120_1176_p000003 | covered_part_number | 120-36833-003
  - cite_e2e_query_v1_0001_t_p_120_1176_p000003_covered_part_number_003 | t_p_120_1176_p000003 | covered_part_number | 120-36833-005
- e2e_query_v1_0002 | manual_page_reference | FINAL_GATE_SAFE_CITATION_BACKED_RESPONSE_DRAFT | citations=3
  - draft: Final-gate smoke draft for query: 'Where is manual reference 25-21-00 used?'. TRACE-Net found citation/source-trace-ready evidence: manual_page_reference=25-21-00 on t_p_120_1176_p000005; ipl_part_number=25-21-00 on t_p_120_1176_p000027; ip...
  - cite_e2e_query_v1_0002_t_p_120_1176_p000005_manual_page_reference_001 | t_p_120_1176_p000005 | manual_page_reference | 25-21-00
  - cite_e2e_query_v1_0002_t_p_120_1176_p000027_ipl_part_number_002 | t_p_120_1176_p000027 | ipl_part_number | 25-21-00
  - cite_e2e_query_v1_0002_t_p_120_1176_p000028_ipl_part_number_003 | t_p_120_1176_p000028 | ipl_part_number | 25-21-00
- e2e_query_v1_0003 | ipl_figure_item_or_quantity | FINAL_GATE_SAFE_CITATION_BACKED_RESPONSE_DRAFT | citations=3
  - draft: Final-gate smoke draft for query: 'Find IPL item 130'. TRACE-Net found citation/source-trace-ready evidence: ipl_figure_item_or_quantity=130 on t_p_120_1176_p000027; ipl_figure_item_or_quantity=130 on t_p_120_1176_p000028; ipl_figure_item_o...
  - cite_e2e_query_v1_0003_t_p_120_1176_p000027_ipl_figure_item_or_quantity_001 | t_p_120_1176_p000027 | ipl_figure_item_or_quantity | 130
  - cite_e2e_query_v1_0003_t_p_120_1176_p000028_ipl_figure_item_or_quantity_002 | t_p_120_1176_p000028 | ipl_figure_item_or_quantity | 130
  - cite_e2e_query_v1_0003_t_p_120_1176_p000036_ipl_figure_item_or_quantity_003 | t_p_120_1176_p000036 | ipl_figure_item_or_quantity | 130
- e2e_query_v1_0004 | table_text | FINAL_GATE_SAFE_CITATION_BACKED_RESPONSE_DRAFT | citations=3
  - draft: Final-gate smoke draft for query: 'Search table text MAINTENANCE MANUAL WITH'. TRACE-Net found citation/source-trace-ready evidence: ipl_text=MAINTENANCE MANUAL WITH on t_p_120_1176_p000027; ipl_text=MAINTENANCE MANUAL WITH on t_p_120_1176_...
  - cite_e2e_query_v1_0004_t_p_120_1176_p000027_ipl_text_001 | t_p_120_1176_p000027 | ipl_text | MAINTENANCE MANUAL WITH
  - cite_e2e_query_v1_0004_t_p_120_1176_p000028_ipl_text_002 | t_p_120_1176_p000028 | ipl_text | MAINTENANCE MANUAL WITH
  - cite_e2e_query_v1_0004_t_p_120_1176_p000029_ipl_text_003 | t_p_120_1176_p000029 | ipl_text | MAINTENANCE MANUAL WITH
- e2e_query_v1_0005 | covered_part_number | FINAL_GATE_SAFE_CITATION_BACKED_RESPONSE_DRAFT | citations=3
  - draft: Final-gate smoke draft for query: 'What maintenance manual pages mention covered part numbers?'. TRACE-Net found citation/source-trace-ready evidence: covered_part_number=120-36833-001 on t_p_120_1176_p000003; covered_part_number=120-36833-...
  - cite_e2e_query_v1_0005_t_p_120_1176_p000003_covered_part_number_001 | t_p_120_1176_p000003 | covered_part_number | 120-36833-001
  - cite_e2e_query_v1_0005_t_p_120_1176_p000003_covered_part_number_002 | t_p_120_1176_p000003 | covered_part_number | 120-36833-003
  - cite_e2e_query_v1_0005_t_p_120_1176_p000003_covered_part_number_003 | t_p_120_1176_p000003 | covered_part_number | 120-36833-005

## Quality checks
- PASS source_sufficiency_quality_pass: observed=True expected=is True
- PASS source_sufficiency_ready_for_final_gate_smoke: observed=True expected=is True
- PASS source_gate_record_count: observed=5 expected=>= 5
- PASS final_gate_record_count: observed=5 expected=>= 5
- PASS safe_response_draft_count: observed=5 expected=>= 4
- PASS citation_backed_response_draft_count: observed=5 expected=>= 4
- PASS audit_or_safe_response_count: observed=5 expected=>= 5
- PASS total_citation_count: observed=15 expected=>= 10
- PASS page_with_citation_count: observed=6 expected=>= 2
- PASS field_count: observed=5 expected=>= 3
- PASS schema_missing_required_key_record_count: observed=0 expected=== 0
- PASS unsafe_final_gate_smoke_record_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS can_answer_directly_count: observed=0 expected=== 0
- PASS can_prove_claims_count: observed=0 expected=== 0
- PASS postgres_write_attempt_count: observed=0 expected=== 0
- PASS qdrant_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_upload_attempt_count: observed=0 expected=== 0
- PASS all_final_gate_smoke_records_no_answer_authority: observed=True expected=is True
