# TRACE-Net IT Operations Console v1

**Status:** FAIL
**Generated:** 2026-06-10T15:25:34+00:00

## Summary

- stage_record_count: 84
- present_stage_record_count: 84
- missing_expected_stage_count: 0
- stage_pass_count: 82
- stage_fail_count: 1
- critical_issue_count: 34
- warning_issue_count: 27
- review_issue_count: 7
- source_truth_mutation_issue_count: 1
- raw_feedback_direct_to_llm_issue_count: 1
- answer_permission_issue_count: 6

## Top Issues

- **CRITICAL** `safety_count_nonzero`: Stage 'issue_answer_boilerplate' has summary.boilerplate_leak_count = 1.
  - Action: Treat as a blocker for answer/search publication until the stage is repaired or the count is justified.
- **CRITICAL** `safety_count_nonzero`: Stage 'issue_answer_claim_without_citation' has summary.claim_without_citation_count = 1.
  - Action: Treat as a blocker for answer/search publication until the stage is repaired or the count is justified.
- **CRITICAL** `safety_count_nonzero`: Stage 'issue_answer_local_path_leak' has summary.local_path_leak_count = 1.
  - Action: Treat as a blocker for answer/search publication until the stage is repaired or the count is justified.
- **WARNING** `stage_quality_nonstandard`: Stage 'issue_answer_nonstandard_status' has non-standard status PARTIAL.
  - Action: Confirm whether this status is expected for the artifact type.
- **CRITICAL** `safety_count_nonzero`: Stage 'issue_answer_raw_bytes' has summary.raw_bytes_repr_count = 1.
  - Action: Treat as a blocker for answer/search publication until the stage is repaired or the count is justified.
- **CRITICAL** `safety_count_nonzero`: Stage 'issue_answer_uncited_claim' has summary.uncited_final_claim_count = 1.
  - Action: Treat as a blocker for answer/search publication until the stage is repaired or the count is justified.
- **REVIEW** `review_backlog`: Stage 'issue_callout_review' has summary.needs_human_review_callout_count = 5.
  - Action: Create or inspect human review tasks for this queue/backlog signal.
- **CRITICAL** `safety_count_nonzero`: Stage 'issue_community_as_proof' has summary.community_as_proof_count = 1.
  - Action: Treat as a blocker for answer/search publication until the stage is repaired or the count is justified.
- **WARNING** `operational_warning`: Stage 'issue_community_missing_membership' has summary.missing_community_membership_count = 5.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **REVIEW** `review_backlog`: Stage 'issue_consensus_review_needed' has summary.human_review_candidate_count = 4.
  - Action: Create or inspect human review tasks for this queue/backlog signal.
- **CRITICAL** `safety_count_nonzero`: Stage 'issue_consensus_unsafe_include' has summary.unsafe_rag_include_records_count = 1.
  - Action: Treat as a blocker for answer/search publication until the stage is repaired or the count is justified.
- **WARNING** `operational_warning`: Stage 'issue_embed_missing_page' has summary.missing_embedding_page_id_count = 4.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **CRITICAL** `safety_count_nonzero`: Stage 'issue_embed_unsafe_candidate' has summary.unsafe_embedding_candidate_count = 1.
  - Action: Treat as a blocker for answer/search publication until the stage is repaired or the count is justified.
- **CRITICAL** `safety_count_nonzero`: Stage 'issue_feedback_as_proof' has summary.feedback_as_proof_count = 1.
  - Action: Treat as a blocker for answer/search publication until the stage is repaired or the count is justified.
- **WARNING** `operational_warning`: Stage 'issue_feedback_missing_target' has summary.missing_feedback_target_count = 3.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **REVIEW** `review_backlog`: Stage 'issue_feedback_prompt_injection' has summary.prompt_injection_flagged_count = 2.
  - Action: Create or inspect human review tasks for this queue/backlog signal.
- **CRITICAL** `safety_count_nonzero`: Stage 'issue_feedback_raw_to_llm' has summary.raw_feedback_direct_to_llm_count = 1.
  - Action: Treat as a blocker for answer/search publication until the stage is repaired or the count is justified.
- **WARNING** `operational_warning`: Stage 'issue_graph_missing_lineage' has summary.missing_part_candidate_lineage_count = 8.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **CRITICAL** `safety_count_nonzero`: Stage 'issue_graph_orphan_edge' has summary.orphan_edge_count = 1.
  - Action: Treat as a blocker for answer/search publication until the stage is repaired or the count is justified.
- **CRITICAL** `safety_count_nonzero`: Stage 'issue_graph_postgres_write' has summary.postgres_write_attempt_count = 1.
  - Action: Treat as a blocker for answer/search publication until the stage is repaired or the count is justified.
- **REVIEW** `review_backlog`: Stage 'issue_graph_review_cluster' has summary.review_required_community_count = 3.
  - Action: Create or inspect human review tasks for this queue/backlog signal.
- **WARNING** `operational_warning`: Stage 'issue_incremental_dirty' has summary.dirty_page_count = 5.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **WARNING** `operational_warning`: Stage 'issue_incremental_needs_embedding' has summary.needs_embedding_page_count = 5.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **WARNING** `operational_warning`: Stage 'issue_incremental_needs_graph' has summary.needs_graph_update_page_count = 5.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **WARNING** `operational_warning`: Stage 'issue_incremental_needs_leiden' has summary.needs_leiden_refresh_page_count = 5.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **CRITICAL** `safety_count_nonzero`: Stage 'issue_llm_claim_proof' has summary.claim_proof_allowed_llm_count = 1.
  - Action: Treat as a blocker for answer/search publication until the stage is repaired or the count is justified.
- **CRITICAL** `safety_count_nonzero`: Stage 'issue_llm_freeform_allowed' has summary.direct_answer_allowed_llm_freeform_count = 1.
  - Action: Treat as a blocker for answer/search publication until the stage is repaired or the count is justified.
- **WARNING** `operational_warning`: Stage 'issue_llm_needs_model' has summary.needs_model_download_count = 1.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **WARNING** `operational_warning`: Stage 'issue_ocr_missing_clean_text' has summary.missing_clean_ocr_text_count = 5.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **WARNING** `operational_warning`: Stage 'issue_ocr_needs_retry' has summary.needs_ocr_page_count = 7.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **CRITICAL** `safety_count_nonzero`: Stage 'issue_ocr_raw_index_risk' has summary.unsafe_raw_ocr_index_document_count = 1.
  - Action: Treat as a blocker for answer/search publication until the stage is repaired or the count is justified.
- **CRITICAL** `safety_count_nonzero`: Stage 'issue_ocr_unsafe_text' has summary.unsafe_ocr_record_count = 1.
  - Action: Treat as a blocker for answer/search publication until the stage is repaired or the count is justified.
- **WARNING** `operational_warning`: Stage 'issue_opensearch_missing_page' has summary.missing_index_page_id_count = 4.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **WARNING** `operational_warning`: Stage 'issue_opensearch_needs_docs' has summary.needs_opensearch_page_count = 9.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **CRITICAL** `safety_count_nonzero`: Stage 'issue_opensearch_raw_visual' has summary.unsafe_raw_visual_output_indexed_count = 1.
  - Action: Treat as a blocker for answer/search publication until the stage is repaired or the count is justified.
- **CRITICAL** `safety_count_nonzero`: Stage 'issue_opensearch_unsafe_doc' has summary.unsafe_index_document_count = 1.
  - Action: Treat as a blocker for answer/search publication until the stage is repaired or the count is justified.
- **CRITICAL** `safety_count_nonzero`: Stage 'issue_orchestrator_unsafe_job' has summary.unsafe_job_count = 1.
  - Action: Treat as a blocker for answer/search publication until the stage is repaired or the count is justified.
- **CRITICAL** `stage_quality_failed`: Stage 'issue_page_registry_failed' quality status is FAIL.
  - Action: Open the quality artifact, inspect failing checks, and rerun/fix the stage before publishing.
- **WARNING** `operational_warning`: Stage 'issue_page_registry_missing_routes' has summary.missing_extraction_route_count = 9.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **WARNING** `operational_warning`: Stage 'issue_page_registry_needs_table' has summary.needs_table_page_count = 12.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **REVIEW** `review_backlog`: Stage 'issue_page_registry_review' has summary.needs_human_review_count = 6.
  - Action: Create or inspect human review tasks for this queue/backlog signal.
- **CRITICAL** `safety_count_nonzero`: Stage 'issue_qdrant_direct_answer' has summary.direct_answer_allowed_payload_count = 1.
  - Action: Treat as a blocker for answer/search publication until the stage is repaired or the count is justified.
- **WARNING** `operational_warning`: Stage 'issue_qdrant_needs_upsert' has summary.needs_qdrant_page_count = 12.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **WARNING** `operational_warning`: Stage 'issue_retrieval_missing_citation' has summary.missing_citation_count = 6.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **CRITICAL** `safety_count_nonzero`: Stage 'issue_retrieval_only_answer' has summary.retrieval_only_answer_allowed_count = 1.
  - Action: Treat as a blocker for answer/search publication until the stage is repaired or the count is justified.
- **CRITICAL** `safety_count_nonzero`: Stage 'issue_retrieval_unsafe' has summary.unsafe_result_count = 1.
  - Action: Treat as a blocker for answer/search publication until the stage is repaired or the count is justified.
- **CRITICAL** `safety_count_nonzero`: Stage 'issue_security_debug_leak' has summary.unsafe_debug_record_count = 1.
  - Action: Treat as a blocker for answer/search publication until the stage is repaired or the count is justified.
- **WARNING** `operational_warning`: Stage 'issue_security_missing_redaction' has summary.missing_redaction_count = 3.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **CRITICAL** `safety_count_nonzero`: Stage 'issue_security_prompt_leak' has summary.unsafe_prompt_leak_count = 1.
  - Action: Treat as a blocker for answer/search publication until the stage is repaired or the count is justified.
- **WARNING** `operational_warning`: Stage 'issue_source_ingest_changed_sources' has summary.changed_source_count = 2.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.

## Stage Health

| Stage | Exists | Status | Critical | Warning | Review |
|---|---:|---:|---:|---:|---:|
| page_element_registry | True | PASS | 0 | 0 | 0 |
| table_understanding | True | PASS | 0 | 0 | 0 |
| table_cell_normalizer | True | PASS | 0 | 0 | 0 |
| figure_chart_understanding | True | PASS | 0 | 0 | 0 |
| visual_ink_layout_calibrator | True | PASS | 0 | 0 | 0 |
| fishnet_retry_engine | True | PASS | 0 | 0 | 0 |
| fishnet_retry_refined | True | PASS | 0 | 0 | 0 |
| element_graph_attachment | True | PASS | 0 | 0 | 0 |
| graph_writeback_overlay | True | PASS | 0 | 0 | 0 |
| part_lineage | True | PASS | 0 | 0 | 0 |
| part_property_normalizer | True | PASS | 0 | 0 | 0 |
| leiden_communities | True | PASS | 0 | 0 | 0 |
| feedback_memory | True | PASS | 0 | 0 | 0 |
| community_aware_retrieval | True | PASS | 0 | 0 | 0 |
| incremental_manifest | True | PASS | 0 | 0 | 0 |
| incremental_orchestrator | True | PASS | 0 | 0 | 0 |
| issue_answer_boilerplate | True | PASS | 1 | 0 | 0 |
| issue_answer_claim_without_citation | True | PASS | 1 | 0 | 0 |
| issue_answer_local_path_leak | True | PASS | 1 | 0 | 0 |
| issue_answer_nonstandard_status | True | PARTIAL | 0 | 1 | 0 |
| issue_answer_raw_bytes | True | PASS | 1 | 0 | 0 |
| issue_answer_uncited_claim | True | PASS | 1 | 0 | 0 |
| issue_callout_review | True | PASS | 0 | 0 | 1 |
| issue_community_as_proof | True | PASS | 1 | 0 | 0 |
| issue_community_missing_membership | True | PASS | 0 | 1 | 0 |
| issue_consensus_review_needed | True | PASS | 0 | 0 | 1 |
| issue_consensus_unsafe_include | True | PASS | 1 | 0 | 0 |
| issue_embed_missing_page | True | PASS | 0 | 1 | 0 |
| issue_embed_unsafe_candidate | True | PASS | 1 | 0 | 0 |
| issue_feedback_as_proof | True | PASS | 1 | 0 | 0 |
| issue_feedback_missing_target | True | PASS | 0 | 1 | 0 |
| issue_feedback_prompt_injection | True | PASS | 0 | 0 | 1 |
| issue_feedback_raw_to_llm | True | PASS | 1 | 0 | 0 |
| issue_graph_missing_lineage | True | PASS | 0 | 1 | 0 |
| issue_graph_orphan_edge | True | PASS | 1 | 0 | 0 |
| issue_graph_postgres_write | True | PASS | 1 | 0 | 0 |
| issue_graph_review_cluster | True | PASS | 0 | 0 | 1 |
| issue_incremental_dirty | True | PASS | 0 | 1 | 0 |
| issue_incremental_needs_embedding | True | PASS | 0 | 1 | 0 |
| issue_incremental_needs_graph | True | PASS | 0 | 1 | 0 |
| issue_incremental_needs_leiden | True | PASS | 0 | 1 | 0 |
| issue_llm_claim_proof | True | PASS | 1 | 0 | 0 |
| issue_llm_freeform_allowed | True | PASS | 1 | 0 | 0 |
| issue_llm_needs_model | True | PASS | 0 | 1 | 0 |
| issue_ocr_missing_clean_text | True | PASS | 0 | 1 | 0 |
| issue_ocr_needs_retry | True | PASS | 0 | 1 | 0 |
| issue_ocr_raw_index_risk | True | PASS | 1 | 0 | 0 |
| issue_ocr_unsafe_text | True | PASS | 1 | 0 | 0 |
| issue_opensearch_missing_page | True | PASS | 0 | 1 | 0 |
| issue_opensearch_needs_docs | True | PASS | 0 | 1 | 0 |
| issue_opensearch_raw_visual | True | PASS | 1 | 0 | 0 |
| issue_opensearch_unsafe_doc | True | PASS | 1 | 0 | 0 |
| issue_orchestrator_unsafe_job | True | PASS | 1 | 0 | 0 |
| issue_page_registry_failed | True | FAIL | 1 | 0 | 0 |
| issue_page_registry_missing_routes | True | PASS | 0 | 1 | 0 |
| issue_page_registry_needs_table | True | PASS | 0 | 1 | 0 |
| issue_page_registry_review | True | PASS | 0 | 0 | 1 |
| issue_qdrant_direct_answer | True | PASS | 1 | 0 | 0 |
| issue_qdrant_needs_upsert | True | PASS | 0 | 1 | 0 |
| issue_retrieval_missing_citation | True | PASS | 0 | 1 | 0 |
| issue_retrieval_only_answer | True | PASS | 1 | 0 | 0 |
| issue_retrieval_unsafe | True | PASS | 1 | 0 | 0 |
| issue_security_debug_leak | True | PASS | 1 | 0 | 0 |
| issue_security_missing_redaction | True | PASS | 0 | 1 | 0 |
| issue_security_prompt_leak | True | PASS | 1 | 0 | 0 |
| issue_source_ingest_changed_sources | True | PASS | 0 | 1 | 0 |
| issue_source_ingest_missing_trace | True | PASS | 0 | 1 | 0 |
| issue_source_ingest_mutation | True | PASS | 1 | 0 | 0 |
| issue_source_ingest_new_sources | True | PASS | 0 | 1 | 0 |
| issue_source_ingest_unsafe_package | True | PASS | 1 | 0 | 0 |
| issue_table_missing_source | True | PASS | 0 | 1 | 0 |
| issue_table_repair_review | True | PASS | 0 | 0 | 1 |
| issue_table_uncited_answer | True | PASS | 1 | 0 | 0 |
| issue_table_unsafe | True | PASS | 1 | 0 | 0 |
| issue_table_unverified_rows | True | PASS | 0 | 1 | 0 |
| issue_trust_claim_proof | True | PASS | 1 | 0 | 0 |
| issue_trust_claim_without_authority | True | PASS | 1 | 0 | 0 |
| issue_trust_direct_answer | True | PASS | 1 | 0 | 0 |
| issue_trust_missing_authority | True | PASS | 0 | 1 | 0 |
| issue_visual_direct_answer | True | PASS | 1 | 0 | 0 |
| issue_visual_human_review | True | PASS | 0 | 0 | 1 |
| issue_visual_needs_model | True | PASS | 0 | 1 | 0 |
| issue_visual_unsafe | True | PASS | 1 | 0 | 0 |
| issue_visual_unverified_claim | True | PASS | 0 | 1 | 0 |
