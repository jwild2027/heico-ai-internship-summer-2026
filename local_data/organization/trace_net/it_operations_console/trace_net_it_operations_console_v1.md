# TRACE-Net IT Operations Console v1

**Status:** PASS
**Generated:** 2026-06-10T15:44:04+00:00

## Summary

- stage_record_count: 91
- present_stage_record_count: 91
- missing_expected_stage_count: 0
- stage_pass_count: 91
- stage_fail_count: 0
- critical_issue_count: 0
- warning_issue_count: 18
- review_issue_count: 8
- source_truth_mutation_issue_count: 0
- raw_feedback_direct_to_llm_issue_count: 0
- answer_permission_issue_count: 0
- excluded_quality_file_count: 86

## Top Issues

- **WARNING** `operational_warning`: Stage 'page_element_registry' has summary.empty_or_missing_ocr_page_count = 14.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **WARNING** `operational_warning`: Stage 'table_understanding' has summary.missing_source_trace_count = 475.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **REVIEW** `review_backlog`: Stage 'figure_chart_understanding' has summary.records_needing_human_review_count = 474.
  - Action: Create or inspect human review tasks for this queue/backlog signal.
- **REVIEW** `review_backlog`: Stage 'visual_ink_layout_calibrator' has summary.figure_chart_summary.records_needing_human_review_count = 474.
  - Action: Create or inspect human review tasks for this queue/backlog signal.
- **REVIEW** `review_backlog`: Stage 'visual_ink_layout_calibrator' has summary.needs_human_review_count = 437.
  - Action: Create or inspect human review tasks for this queue/backlog signal.
- **WARNING** `operational_warning`: Stage 'visual_ink_layout_calibrator' has summary.needs_vision_model_count = 436.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **REVIEW** `review_backlog`: Stage 'feedback_memory' has summary.prompt_injection_flagged_count = 1.
  - Action: Create or inspect human review tasks for this queue/backlog signal.
- **REVIEW** `review_backlog`: Stage 'community_aware_retrieval' has summary.prompt_injection_flagged_count = 1.
  - Action: Create or inspect human review tasks for this queue/backlog signal.
- **WARNING** `operational_warning`: Stage 'incremental_manifest' has dirty_page_count = 509.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **WARNING** `operational_warning`: Stage 'incremental_manifest' has new_source_count = 1018.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **WARNING** `operational_warning`: Stage 'incremental_manifest' has summary.dirty_page_count = 509.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **WARNING** `operational_warning`: Stage 'incremental_manifest' has summary.needs_embedding_page_count = 509.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **WARNING** `operational_warning`: Stage 'incremental_manifest' has summary.needs_graph_update_page_count = 509.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **WARNING** `operational_warning`: Stage 'incremental_manifest' has summary.needs_leiden_refresh_page_count = 509.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **WARNING** `operational_warning`: Stage 'incremental_manifest' has summary.needs_ocr_page_count = 509.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **WARNING** `operational_warning`: Stage 'incremental_manifest' has summary.needs_opensearch_page_count = 509.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **WARNING** `operational_warning`: Stage 'incremental_manifest' has summary.needs_qdrant_page_count = 509.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **WARNING** `operational_warning`: Stage 'incremental_manifest' has summary.needs_table_page_count = 509.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **WARNING** `operational_warning`: Stage 'incremental_manifest' has summary.needs_visual_page_count = 509.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **WARNING** `operational_warning`: Stage 'incremental_manifest' has summary.new_source_count = 1018.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **WARNING** `operational_warning`: Stage 'incremental_orchestrator' has summary.unchanged_source_count = 1018.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **REVIEW** `review_backlog`: Stage 'callout_visual_part_verifier' has summary.diagrams_needing_human_review_count = 471.
  - Action: Create or inspect human review tasks for this queue/backlog signal.
- **WARNING** `operational_warning`: Stage 'incremental_corpus_manifest_next' has summary.unchanged_source_count = 1018.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.
- **REVIEW** `review_backlog`: Stage 'vision_model_pilot' has summary.source_calibrator_summary.figure_chart_summary.records_needing_human_review_count = 474.
  - Action: Create or inspect human review tasks for this queue/backlog signal.
- **REVIEW** `review_backlog`: Stage 'vision_model_pilot' has summary.source_calibrator_summary.needs_human_review_count = 437.
  - Action: Create or inspect human review tasks for this queue/backlog signal.
- **WARNING** `operational_warning`: Stage 'vision_model_pilot' has summary.source_calibrator_summary.needs_vision_model_count = 436.
  - Action: Inspect the operational count; it may indicate changed data, missing artifacts, or work pending.

## Stage Health

| Stage | Exists | Status | Critical | Warning | Review |
|---|---:|---:|---:|---:|---:|
| page_element_registry | True | PASS | 0 | 1 | 0 |
| table_understanding | True | PASS | 0 | 1 | 0 |
| table_cell_normalizer | True | PASS | 0 | 0 | 0 |
| figure_chart_understanding | True | PASS | 0 | 0 | 1 |
| visual_ink_layout_calibrator | True | PASS | 0 | 1 | 2 |
| fishnet_retry_engine | True | PASS | 0 | 0 | 0 |
| fishnet_retry_refined | True | PASS | 0 | 0 | 0 |
| element_graph_attachment | True | PASS | 0 | 0 | 0 |
| graph_writeback_overlay | True | PASS | 0 | 0 | 0 |
| part_lineage | True | PASS | 0 | 0 | 0 |
| part_property_normalizer | True | PASS | 0 | 0 | 0 |
| leiden_communities | True | PASS | 0 | 0 | 0 |
| feedback_memory | True | PASS | 0 | 0 | 1 |
| community_aware_retrieval | True | PASS | 0 | 0 | 1 |
| incremental_manifest | True | PASS | 0 | 12 | 0 |
| incremental_orchestrator | True | PASS | 0 | 1 | 0 |
| answer_context_pack | True | PASS | 0 | 0 | 0 |
| answers | True | OK | 0 | 0 | 0 |
| ask | True | OK | 0 | 0 | 0 |
| ask_final_gate | True | PASS | 0 | 0 | 0 |
| ask_hybrid_flag | True | PASS | 0 | 0 | 0 |
| ask_hybrid_flag | True | PASS | 0 | 0 | 0 |
| baseline | True | OK | 0 | 0 | 0 |
| baselines | True | PASS | 0 | 0 | 0 |
| callout_visual_part_verifier | True | PASS | 0 | 0 | 1 |
| citation_answer_draft | True | PASS | 0 | 0 | 0 |
| citations | True | OK | 0 | 0 | 0 |
| cleanup_repair | True | OK | 0 | 0 | 0 |
| confidence | True | OK | 0 | 0 | 0 |
| confidence | True | OK | 0 | 0 | 0 |
| confidence | True | OK | 0 | 0 | 0 |
| confidence | True | OK | 0 | 0 | 0 |
| context_retrieval_helpers | True | PASS | 0 | 0 | 0 |
| embedding_candidates | True | PASS | 0 | 0 | 0 |
| evidence_consensus | True | OK | 0 | 0 | 0 |
| evidence_snippet_claims | True | PASS | 0 | 0 | 0 |
| evidence_snippet_cleaner | True | PASS | 0 | 0 | 0 |
| feedback | True | OK | 0 | 0 | 0 |
| feedback_ask_simulation | True | OK | 0 | 0 | 0 |
| feedback_search_simulation | True | OK | 0 | 0 | 0 |
| final_answer_gate | True | PASS | 0 | 0 | 0 |
| graph_audit | True | OK | 0 | 0 | 0 |
| graph_explorer | True | PASS | 0 | 0 | 0 |
| graph_ui_community_overlay | True | PASS | 0 | 0 | 0 |
| hybrid_retrieval_sim | True | PASS | 0 | 0 | 0 |
| incremental_corpus_manifest_next | True | PASS | 0 | 1 | 0 |
| it_issue_origin_test_matrix | True | PASS | 0 | 0 | 0 |
| page_context_overlay | True | OK | 0 | 0 | 0 |
| page_context_v2 | True | OK | 0 | 0 | 0 |
| page_retrieval_profiles | True | PASS | 0 | 0 | 0 |
| postgres | True | OK | 0 | 0 | 0 |
| qdrant_loader | True | PASS | 0 | 0 | 0 |
| qdrant_loader_ollama_bge_m3 | True | PASS | 0 | 0 | 0 |
| qdrant_page_retrieval_profiles | True | PASS | 0 | 0 | 0 |
| qdrant_page_retrieval_profiles_ollama_bge_m3 | True | PASS | 0 | 0 | 0 |
| rag_candidates | True | OK | 0 | 0 | 0 |
| rag_eligibility | True | OK | 0 | 0 | 0 |
| regression | True | OK | 0 | 0 | 0 |
| regression | True | OK | 0 | 0 | 0 |
| regression | True | OK | 0 | 0 | 0 |
| regression | True | OK | 0 | 0 | 0 |
| regression | True | OK | 0 | 0 | 0 |
| regression | True | OK | 0 | 0 | 0 |
| regression | True | OK | 0 | 0 | 0 |
| regression | True | OK | 0 | 0 | 0 |
| regression | True | OK | 0 | 0 | 0 |
| regression | True | OK | 0 | 0 | 0 |
| regression | True | OK | 0 | 0 | 0 |
| regression | True | OK | 0 | 0 | 0 |
| regression | True | OK | 0 | 0 | 0 |
| regression | True | OK | 0 | 0 | 0 |
| regression | True | OK | 0 | 0 | 0 |
| regression | True | OK | 0 | 0 | 0 |
| regression | True | OK | 0 | 0 | 0 |
| regression | True | OK | 0 | 0 | 0 |
| regression | True | OK | 0 | 0 | 0 |
| regression | True | OK | 0 | 0 | 0 |
| regression | True | OK | 0 | 0 | 0 |
| regression | True | OK | 0 | 0 | 0 |
| regression_eval | True | PASS | 0 | 0 | 0 |
| search | True | OK | 0 | 0 | 0 |
| search | True | OK | 0 | 0 | 0 |
| trace_net_quality | True | OK | 0 | 0 | 0 |
| trace_net_repair_quality | True | OK | 0 | 0 | 0 |
| trust_authority | True | OK | 0 | 0 | 0 |
| trust_overlay | True | OK | 0 | 0 | 0 |
| vector_search_smoke | True | PASS | 0 | 0 | 0 |
| vision_model_pilot | True | PASS | 0 | 1 | 2 |
| weighted_search | True | OK | 0 | 0 | 0 |
| weighted_search_calibration | True | OK | 0 | 0 | 0 |
| weights | True | OK | 0 | 0 | 0 |
