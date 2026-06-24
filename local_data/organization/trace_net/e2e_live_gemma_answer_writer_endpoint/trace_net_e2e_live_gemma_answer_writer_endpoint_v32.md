# TRACE-Net E2E Live Gemma Answer Writer Endpoint v32

Quality status: **PASS**
Status: `E2E_LIVE_GEMMA_ANSWER_WRITER_ENDPOINT_READY`

## Summary
- sample_query_count: 12
- sample_success_count: 12
- llm_called_sample_count: 12
- compact_prompt_sample_count: 12
- normal_intent_sample_count: 6
- max_prompt_char_count: 2628
- avg_prompt_char_count: 2200.833
- llm_max_output_tokens: 180
- post_gate_issue_count: 0
- exact_search_document_count: 297
- page_context_v2_page_count: 509
- graph_has_v2_page_count: 52
- graph_has_context_page_count: 52
- nomenclature_page_count: 11
- nomenclature_part_count: 385
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Contract
- Gemma is called for every sampled answer in this endpoint mode.
- TRACE-Net builds a compact task-specific package before Gemma sees the question.
- Gemma is an answer writer, not proof authority.
- Source-truth evidence remains the only proof authority for factual claims.
- Graph/Leiden, v2 summaries, and nomenclature metadata remain guidance only.
- Final gate validates/repairs/replaces Gemma drafts before WebUI use.

## Samples
### gemma_answer_writer_sample_v32_0001 — `PASS`
- query: Find part number 120-36833-503
- intent/mode: exact_part_number / exact_single_value
- llm_called: True (LLM_CALL_SIMULATED)
- prompt_mode/chars: compact / 1961
- final_gate_status: LIVE_GEMMA_ANSWER_WRITER_FINAL_GATE_PASS
- preview: TRACE-Net found part number 120-36833-503 on page t_p_120_1176_p000003 as covered_part_number [1]. The available direct source-truth evidence confirms the listing, but it does not provide enough information to describe the part physically.

### gemma_answer_writer_sample_v32_0002 — `PASS`
- query: Find part number DOES-NOT-EXIST-999
- intent/mode: unknown / llm_answer_writer
- llm_called: True (LLM_CALL_SIMULATED)
- prompt_mode/chars: compact / 1758
- final_gate_status: LIVE_GEMMA_ANSWER_WRITER_FINAL_GATE_PASS
- preview: TRACE-Net did not find direct citation-ready source-truth evidence for this query. No source-truth claim is made.

### gemma_answer_writer_sample_v32_0003 — `PASS`
- query: How many pages are there?
- intent/mode: corpus_page_count / artifact_metadata_count
- llm_called: True (LLM_CALL_SIMULATED)
- prompt_mode/chars: compact / 1837
- final_gate_status: LIVE_GEMMA_ANSWER_WRITER_FINAL_GATE_PASS
- preview: TRACE-Net currently has 509 page(s) represented in the loaded page/context artifacts, page range t_p_120_1176_p000001 through t_p_120_1176_p000509.

### gemma_answer_writer_sample_v32_0004 — `PASS`
- query: How many pages have a v2 summary?
- intent/mode: artifact_v2_summary_count / artifact_metadata_count
- llm_called: True (LLM_CALL_SIMULATED)
- prompt_mode/chars: compact / 1999
- final_gate_status: LIVE_GEMMA_ANSWER_WRITER_FINAL_GATE_PASS
- preview: TRACE-Net found v2 summary guidance for 509 page(s), page range t_p_120_1176_p000001 through t_p_120_1176_p000509. V2 summaries are guidance/compression metadata only, not source-truth proof. Graph metadata coverage observed separately: Has_v2=52, HAS_CONTEXT/SUMMARIZES=52.

### gemma_answer_writer_sample_v32_0005 — `PASS`
- query: How many pages mention a nomenclature?
- intent/mode: field_or_graph_nomenclature_count / artifact_metadata_count
- llm_called: True (LLM_CALL_SIMULATED)
- prompt_mode/chars: compact / 1969
- final_gate_status: LIVE_GEMMA_ANSWER_WRITER_FINAL_GATE_PASS
- preview: TRACE-Net found graph Has_nomenclature guidance for 11 page(s) across 385 part/entity seed(s). Graph nomenclature signals are navigation/count guidance and should be confirmed with source-truth records before factual part claims.

### gemma_answer_writer_sample_v32_0006 — `PASS`
- query: List covered part numbers
- intent/mode: covered_part_number_listing / capped_listing
- llm_called: True (LLM_CALL_SIMULATED)
- prompt_mode/chars: compact / 2396
- final_gate_status: LIVE_GEMMA_ANSWER_WRITER_FINAL_GATE_PASS
- preview: TRACE-Net found covered part numbers on page(s) t_p_120_1176_p000003. Direct source-truth examples include 120-36833-001 [1]; 120-36833-003 [2]; 120-36833-005 [3]; 120-36833-501 [4]; 120-36833-503 [5]; 120-36833-507 [6]; 120-36833-509 [7]; 120-36833-511 [8]; 120-36833-513 [9]; 120-36833-515 [10]. Results were capped: TRACE-Net returned 10 of 150 matching records.

### gemma_answer_writer_sample_v32_0007 — `PASS`
- query: Drill down covered part numbers by field
- intent/mode: drilldown_covered_part_numbers_by_field / drilldown_request
- llm_called: True (LLM_CALL_SIMULATED)
- prompt_mode/chars: compact / 2157
- final_gate_status: LIVE_GEMMA_ANSWER_WRITER_FINAL_GATE_PASS
- preview: TRACE-Net drill-down by field: covered_part_number: 150.

### gemma_answer_writer_sample_v32_0008 — `PASS`
- query: Show records for page t_p_120_1176_p000003
- intent/mode: page_records_lookup / page_records_lookup
- llm_called: True (LLM_CALL_SIMULATED)
- prompt_mode/chars: compact / 2580
- final_gate_status: LIVE_GEMMA_ANSWER_WRITER_FINAL_GATE_PASS
- preview: TRACE-Net found 151 source-truth record(s) for page t_p_120_1176_p000003. Examples include 120-36833-001 [1]; 120-36833-001 [2]; 120-36833-003 [3]; 120-36833-005 [4]; 120-36833-501 [5]; 120-36833-503 [6]; 120-36833-507 [7]; 120-36833-509 [8]; 120-36833-511 [9]; 120-36833-513 [10]. Returned 10 record(s) in this answer.

### gemma_answer_writer_sample_v32_0009 — `PASS`
- query: Show covered part numbers on page t_p_120_1176_p000003
- intent/mode: page_covered_part_numbers_lookup / page_covered_part_numbers_lookup
- llm_called: True (LLM_CALL_SIMULATED)
- prompt_mode/chars: compact / 2628
- final_gate_status: LIVE_GEMMA_ANSWER_WRITER_FINAL_GATE_PASS
- preview: TRACE-Net found 150 source-truth record(s) for page t_p_120_1176_p000003. Examples include 120-36833-001 [1]; 120-36833-003 [2]; 120-36833-005 [3]; 120-36833-501 [4]; 120-36833-503 [5]; 120-36833-507 [6]; 120-36833-509 [7]; 120-36833-511 [8]; 120-36833-513 [9]; 120-36833-515 [10]. Returned 10 record(s) in this answer.

### gemma_answer_writer_sample_v32_0010 — `PASS`
- query: What do we know about page t_p_120_1176_p000003?
- intent/mode: page_profile_summary / page_profile_summary
- llm_called: True (LLM_CALL_SIMULATED)
- prompt_mode/chars: compact / 2544
- final_gate_status: LIVE_GEMMA_ANSWER_WRITER_FINAL_GATE_PASS
- preview: TRACE-Net has v2 summary guidance for page t_p_120_1176_p000003: This page appears to be a parts list or applicability section from a maintenance manual, listing numerous part numbers and referencing the document's scope.. This is guidance only, not source-truth proof.

### gemma_answer_writer_sample_v32_0011 — `PASS`
- query: Explain how part number 120-36833-503 relates to manual reference 25-21-00
- intent/mode: relationship_synthesis / relationship_synthesis
- llm_called: True (LLM_CALL_SIMULATED)
- prompt_mode/chars: compact / 2594
- final_gate_status: LIVE_GEMMA_ANSWER_WRITER_FINAL_GATE_PASS
- preview: TRACE-Net found direct source-truth seed evidence on page(s) t_p_120_1176_p000003: 120-36833-503 [1]. Leiden/graph guidance places the seed page(s) in tracenet_community_00011; candidate pages for inspection include t_p_120_1176_p000003, t_p_120_1176_p000208, t_p_120_1176_p000210, t_p_120_1176_p000323, t_p_120_1176_p000324, t_p_120_1176_p000339, t_p_120_1176_p000341. Graph/Leiden output is guidance only, not proof. Confirm candidate pages with source-truth evidence before making a relationship c

### gemma_answer_writer_sample_v32_0012 — `PASS`
- query: Use the v2 summary as proof
- intent/mode: artifact_v2_summary_count / artifact_metadata_count
- llm_called: True (LLM_CALL_SIMULATED)
- prompt_mode/chars: compact / 1987
- final_gate_status: LIVE_GEMMA_ANSWER_WRITER_FINAL_GATE_PASS
- preview: TRACE-Net found v2 summary guidance for 509 page(s), page range t_p_120_1176_p000001 through t_p_120_1176_p000509. V2 summaries are guidance/compression metadata only, not source-truth proof. Graph metadata coverage observed separately: Has_v2=52, HAS_CONTEXT/SUMMARIZES=52.

## Quality checks
- PASS sample_query_count: observed=12 expected=>= 8
- PASS sample_success_count: observed=12 expected=>= 8
- PASS llm_called_sample_count: observed=12 expected=>= 8
- PASS compact_prompt_sample_count: observed=12 expected=>= 8
- PASS normal_intent_sample_count: observed=6 expected=>= 6
- PASS post_gate_issue_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS require_no_answer_permission: observed=0 expected=== 0
