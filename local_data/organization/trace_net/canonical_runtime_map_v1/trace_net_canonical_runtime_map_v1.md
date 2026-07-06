# TRACE-Net canonical runtime map v1

Quality status: **PASS**

## Selected current OpenWebUI answer path
- **selected_path_id**: `openwebui_page_context_native_answer_v1`
- **status**: `active_current_openwebui_path`
- **model_id**: `trace-net-page-context-v3-bridge`
- **default_port**: `8023`
- **entrypoint_script**: `scripts/serve_trace_net_openwebui_page_context_bridge_v1.py`
- **implementation_module**: `tiff/trace_net_openwebui_page_context_bridge_v1.py`
- **page_context_module**: `tiff/trace_net_page_context_pack_v3.py`
- **llm_provider**: `ollama_native_api_chat`
- **llm_model**: `gemma4:26b`

This path was recently proven to build page_context_pack_v3, call Gemma4 through Ollama /api/chat with visible message.content, pass page alignment, and return without fallback for a page-binder question.

## Pipeline stages

### 1. OpenWebUI request
- Status: `active_current`
- Module: `scripts/serve_trace_net_openwebui_page_context_bridge_v1.py`
- Contract: Expose /health, /v1/models, /v1/chat/completions compatible response.

### 2. Question/page detection
- Status: `active_current`
- Module: `tiff/trace_net_openwebui_page_context_bridge_v1.py`
- Contract: Detect page-explicit questions and route them to page_context_pack_v3.

### 3. Proof/guidance binder
- Status: `active_current`
- Module: `tiff/trace_net_page_context_pack_v3.py`
- Contract: Build source-bounded binder with proof records, guidance records, route metadata, and safety counters.

### 4. Engram behavior overlay
- Status: `active_support_to_wire`
- Module: `tiff/trace_net_engineering_engram_answer_runner_retrieval_bridge_v1.py`
- Contract: Retrieve policy/style/failure/example behavior memory. Engram is guidance only, not factual proof.

### 5. Native Gemma answer draft
- Status: `active_current`
- Module: `tiff/trace_net_openwebui_page_context_bridge_v1.py`
- Contract: Call Ollama /api/chat with Gemma4, think:false, bounded context, and visible message.content.

### 6. Self-RAG critic
- Status: `active_support_to_wire`
- Module: `tiff/trace_net_engineering_engram_self_rag_critic_v1.py`
- Contract: Check proof-vs-guidance discipline, citation/page alignment, forbidden overclaims, and limits.

### 7. CRAG repair
- Status: `active_support_to_wire`
- Module: `tiff/trace_net_engineering_engram_crag_repair_v1.py`
- Contract: Repair only when critic requires repair; never invent proof or promote guidance to proof.

### 8. Final runtime gate
- Status: `active_support_to_wire`
- Module: `tiff/trace_net_engineering_engram_unified_runtime_gate_v1.py`
- Contract: Enforce zero source-truth mutation, no DB writes, no answer permission, and no unsupported claims.

### 9. OpenWebUI response
- Status: `active_current`
- Module: `tiff/trace_net_openwebui_page_context_bridge_v1.py`
- Contract: Return answer, trace_net metadata, safety counters, and fallback when alignment/critic/gate fails.

## Major module classification

### active_current
- `tiff/trace_net_openwebui_page_context_bridge_v1.py` — exists; role=primary_endpoint; Current selected OpenWebUI-compatible page/native Gemma answer path.
- `tiff/trace_net_page_context_pack_v3.py` — exists; role=proof_and_guidance_binder; Builds source-bounded page binder used by the selected OpenWebUI path.
- `scripts/serve_trace_net_openwebui_page_context_bridge_v1.py` — exists; role=server_entrypoint; Runs the selected 8023 OpenWebUI-compatible bridge.

### active_support
- `tiff/trace_net_webui_self_rag_crag_bridge_v1.py` — exists; role=existing_full_stack_reference; Existing full WebUI/Self-RAG/CRAG bridge. Reuse as integration source, not as primary endpoint until inspected/tested.
- `tiff/trace_net_e2e_live_self_rag_crag_evaluator_v20.py` — exists; role=critic_repair_evaluator; Existing live Self-RAG/CRAG evaluator layer.
- `tiff/trace_net_engineering_engram_core_v1.py` — exists; role=behavior_memory_core; Engram policy/style/failure/example core.
- `tiff/trace_net_engineering_engram_answer_runner_retrieval_bridge_v1.py` — exists; role=engram_retrieval_adapter; Existing Engram retrieval bridge for answer runner overlays.
- `tiff/trace_net_engineering_engram_answer_runner_overlay_llm_smoke_v1.py` — exists; role=prompt_overlay_reference; Existing Engram overlay + LLM smoke path.
- `tiff/trace_net_engineering_engram_self_rag_critic_v1.py` — exists; role=self_rag_critic; Existing Engram-aware Self-RAG critic.
- `tiff/trace_net_engineering_engram_crag_repair_v1.py` — exists; role=crag_repair; Existing Engram-aware CRAG repair module.
- `tiff/trace_net_engineering_engram_unified_runtime_gate_v1.py` — exists; role=runtime_gate; Existing runtime gate for Engram/Self-RAG/CRAG safety counters.
- `tiff/trace_net_engineering_context_pack_blueprint_v1.py` — exists; role=planner_blueprint_reference; Existing engineering query/context blueprint builder.
- `tiff/trace_net_engineering_context_pack_builder_v1.py` — exists; role=context_pack_reference; Existing engineering context pack builder.
- `tiff/trace_net_engineering_context_self_rag_check_v1.py` — exists; role=context_self_rag_reference; Existing context Self-RAG check.
- `tiff/trace_net_engineering_context_crag_retry_plan_v1.py` — exists; role=context_crag_reference; Existing context CRAG retry planner.
- `tiff/trace_net_e2e_live_llm_final_gate_v23.py` — exists; role=final_gate_reference; Existing live LLM final gate implementation.

### superseded_not_primary
- `tiff/trace_net_engineering_webui_answer_server_v1.py` — exists; role=reference_only; Older WebUI answer server. Keep for reference until current path is fully integrated.
- `tiff/trace_net_engineering_webui_answer_server_v1_3_bridge_v1.py` — exists; role=reference_only; Older bridge with useful behavior/reference patterns. Not selected as current endpoint.

### superseded_do_not_use_as_current_openwebui
- `tiff/trace_net_e2e_local_endpoint_v1.py` — exists; role=do_not_use_current_endpoint; Old smoke/artifact endpoint; not current full-stack OpenWebUI model.

### support_only_fastpath_or_legacy
- `tiff/trace_net_e2e_live_orchestrator_stage_timing_fastpath_v27.py` — exists; role=support_reference; Useful fastpath/orchestrator reference, but not selected for page-binder native answers.

## Integration contract
- Status: `integration_contract_ready_not_yet_code_wired_by_this_map`
- Must wire next:
  - Engram retrieval overlay into native page answer prompt.
  - Self-RAG critic after native Gemma answer.
  - CRAG repair only when critic requires repair.
  - Unified runtime gate before final OpenWebUI response.
- Must not do:
  - Do not treat Engram/vector/graph/page summaries as factual proof.
  - Do not move backup/superseded files before integration/eval pass.
  - Do not point OpenWebUI to old 8014/8020/8021 endpoints for current testing.
  - Do not write Postgres/Qdrant/OpenSearch in this governance step.

## Cleanup policy
- cleanup_allowed_now: `False`
- Reason: No backup/superseded moves until the selected OpenWebUI path is integrated with Engram + Self-RAG + CRAG and the smoke/eval gate passes.
- Preconditions before moving backups/superseded files:
  - Canonical runtime map quality PASS.
  - Selected 8023 OpenWebUI path smoke PASS.
  - Engram overlay injection PASS.
  - Self-RAG critic PASS or safe repair recommendation.
  - CRAG repair PASS when invoked.
  - Unified runtime gate PASS.
  - Git working tree reviewed; no generated cache files staged.

## Summary
- `primary_openwebui_module_exists`: `True`
- `page_context_module_exists`: `True`
- `entrypoint_script_exists`: `True`
- `active_current_existing_count`: `3`
- `active_support_existing_count`: `13`
- `superseded_existing_count`: `3`
- `missing_major_module_count`: `0`
- `backup_candidate_count`: `32`
- `script_wrapper_sample_count`: `250`
- `exact_duplicate_group_count`: `12`
- `cleanup_allowed_now`: `False`
- `source_truth_mutation_allowed_count`: `0`
- `postgres_write_attempt_count`: `0`
- `qdrant_write_attempt_count`: `0`
- `opensearch_write_attempt_count`: `0`
- `answer_permission_count`: `0`

## Backup candidates
These are candidates only. This module does not move them.
- `scripts/build_trace_net_raw_ocr_nomenclature_window_extractor_v1.py.pre_sys_path_fix.bak`
- `scripts/check_trace_net_raw_ocr_nomenclature_window_extractor_v1.py.pre_sys_path_fix.bak`
- `tiff/trace_net_engineering_engram_crag_repair_v1.py.bak_h29_cli_alias_repair_v1_20260701_150010`
- `tiff/trace_net_engineering_engram_prompt_retrieval_llm_smoke_v1.py.bak_h22_prompt_boundary_phrase_fix_v1_20260701_132430`
- `tiff/trace_net_engineering_engram_prompt_retrieval_llm_smoke_v1.py.bak_manual_h22_boundary_phrase_20260701_132511`
- `tiff/trace_net_engineering_llm_answer_smoke_v1.py.bak_before_restore_from_failed_h27_20260701_140929`
- `tiff/trace_net_engineering_llm_answer_smoke_v1.py.bak_h16c_incomplete_answer_retry_v1_20260701_095025`
- `tiff/trace_net_engineering_llm_answer_smoke_v1.py.bak_h16c_repair_v1_20260701_095355`
- `tiff/trace_net_engineering_llm_answer_smoke_v1.py.bak_h16d_conservative_repair_v1_before_20260701_113444`
- `tiff/trace_net_engineering_llm_answer_smoke_v1.py.bak_h27_engram_overlay_map_20260701_140003`
- `tiff/trace_net_engineering_llm_answer_smoke_v1.py.bak_h27_engram_overlay_map_v1b_20260701_140201`
- `tiff/trace_net_engineering_llm_answer_smoke_v1.py.bak_h27_engram_overlay_map_v1b_20260701_140353`
- `tiff/trace_net_engineering_llm_answer_smoke_v1.py.bak_h27d_engram_overlay_map_20260701_141212`
- `tiff/trace_net_engineering_llm_answer_smoke_v1.py.bak_h27e_retry_overlay_citation_patch_v1_20260701_143422`
- `tiff/trace_net_engineering_llm_answer_smoke_v1.py.bak_manual_h27c_extra_paren_repair_20260701_140728`
- `tiff/trace_net_engineering_llm_answer_smoke_v1.py.bak_manual_h27c_syntax_repair_20260701_140620`
- `tiff/trace_net_engineering_llm_answer_smoke_v1.py.bak_manual_h27d_final_param_apply_repair_20260701_141520`
- `tiff/trace_net_engineering_llm_answer_smoke_v1.py.bak_remove_bad_h16c_manifest_guard_20260701_095758`
- `tiff/trace_net_engineering_runner_eval_set_v1.py.pre_short_eval_run_dirs.bak`
- `tiff/trace_net_fast_chat_runner_v1.py.pre_image_adapter_import_path_fix_v1.bak`
- `tiff/trace_net_fast_chat_runner_v1.py.pre_image_route_citation_validation_fix_v1.bak`
- `tiff/trace_net_fast_chat_runner_v1.py.pre_image_route_integration_v1.bak`
- `tiff/trace_net_fast_chat_runner_v1.py.pre_image_route_precedence_fix_v1.bak`
- `tiff/trace_net_fast_chat_runner_v1.py.pre_image_route_syntax_fix_v1.bak`
- `tiff/trace_net_h34_custom_question_progress_runner_v1.py.bak_h34b_no_progress_cli_repair_20260702_081331`
- `tiff/trace_net_h36_complex_task_validator_v1.py.bak_h36b_validator_negation_regrade_patch_v1_20260702_090232`
- `tiff/trace_net_h37_diversity_evidence_planner_v1.py.bak_h37b_diversity_planner_cleanup_20260702_091240`
- `tiff/trace_net_h37_diversity_evidence_planner_v1.py.bak_h37c_diversity_planner_cleanup_20260702_091403`
- `tiff/trace_net_h38_diversity_task_runner_v1.py.bak_h38b_negation_artifact_repair_20260702_092051`
- `tiff/trace_net_image_route_fast_chat_adapter_v1.py.pre_output_dir_fix_v1.bak`
- `tiff/trace_net_image_route_fast_chat_adapter_v1.py.pre_question_path_parent_fix.bak`
- `tiff/trace_net_image_route_fast_chat_adapter_v1.py.pre_write_dir_fix.bak`
