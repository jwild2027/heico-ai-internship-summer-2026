# TRACE-Net Route-Scoped Visual Context Builder v35

Quality status: **PASS**
Status: `E2E_ROUTE_SCOPED_VISUAL_CONTEXT_BUILDER_READY`

## Summary
- source_page_count: 509
- route_index_page_count: 509
- route_candidate_count: 509
- image_visual_candidate_count: 384
- visual_context_card_count: 25
- visual_prompt_context_count: 25
- technical_drawing_context_card_count: 0
- ocr_text_card_count: 25
- ocr_text_candidate_count: 0
- technical_geometry_card_count: 25
- line_candidate_count: 0
- circle_candidate_count: 0
- dimension_line_candidate_count: 0
- hatching_candidate_count: 0
- guidance_only_visual_context_count: 25
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Contract
- This stage consumes existing stored page files and route metadata; it does not create answer authority.
- Visual context cards are guidance only.
- LLaVA is not called by default in this offline builder; expensive visual models can enrich cards later.
- No Postgres/Qdrant/OpenSearch writes and no source-truth mutation are allowed.

## Sample visual context cards
### t_p_120_1176_p000001 — `{"allowed_dispatch_routes": ["table", "image_visual", "normal_text", "review"], "answer_permission": false, "blank_candidate_processing_allowed": false, "blank_score": 0.1, "can_answer_directly": false, "can_prove_claims": false, "dispatch_reasons": ["primary_route_image_visual", "route_manifest_review_required", "secondary_route_normal_text_with_review_required", "secondary_route_table_with_review_required"], "dispatch_routes": ["image_visual", "normal_text", "table", "review"], "evidence_summary": {"artifact_count": 58, "artifact_detector_path": "local_data\\organization\\trace_net\\artifact_detector\\trace_net_artifact_detector_v1.json", "artifact_keys": ["answer_claim_critic", "answer_context_pack", "ask_final_gate", "ask_hybrid_flag", "callout_visual_part_verifier", "category_aware_graph_ui_overlay", "category_aware_leiden_overlay", "citation_answer_draft", "community_aware_retrieval", "community_aware_retrieval_sim", "confidence", "context_retrieval_helper", "corrective_retrieval_planner", "dublin_core_crosswalk", "dublin_core_crosswalk_refinement", "dublin_core_source_package_extension", "dynamic_final_gate_execution", "element_category_taxonomy", "element_graph_attachment_plan", "embedding_candidates", "evidence_snippet_claims", "evidence_snippet_cleaner", "figure_chart_understanding", "final_answer_gate", "fishnet_retry_engine", "fishnet_retry_refinement", "graph_overlay_part_lineage", "graph_overlay_part_property_normalizer", "graph_query_evidence_enrichment", "graph_query_helper", "graph_ui_community_overlay", "graph_writeback_overlay", "human_review_workbench", "human_review_workbench_preview_wiring", "incremental_corpus_manifest", "leiden_graph_communities", "leiden_navigation_metadata_bridge", "llm_graph_path_compliance_judge", "llm_graph_path_response_guard", "numerical_index", "opensearch_adapter", "page_element_registry", "page_query_response_dataset", "page_query_response_source_cross_reference", "page_query_response_tiff_content_audit", "page_retrieval_large_eval", "page_retrieval_profiles", "stage5_control", "table_cell_normalizer", "table_understanding", "trace_net", "vector_search_smoke", "visual_ink_layout_calibrator"], "artifact_page_ids": ["t_p_120_1176_p000001"], "evidence_category_counts": {"general": 38, "human_review": 2, "image_visual": 3, "ocr_text": 4, "retrieval_answer": 9, "table": 2}, "human_review_evidence_artifact_count": 2, "image_visual_evidence_artifact_count": 3, "ocr_text_evidence_artifact_count": 4, "page_ink_route_evidence_path": "local_data\\organization\\trace_net\\page_ink_route_evidence\\trace_net_page_ink_route_evidence_v1.json", "safe_artifact_count": 57, "table_evidence_artifact_count": 2, "unsafe_artifact_count": 1}, "image_visual_processing_allowed": true, "image_visual_score": 0.8, "ink_primary_route": "normal_text", "ink_route_disagreement_review_reasons": [], "normal_text_processing_allowed": true, "opensearch_write_attempt_count": 0, "page_id": "t_p_120_1176_p000001", "page_ink_route_evidence_available": true, "page_number": 1, "postgres_write_attempt_count": 0, "primary_dispatch_route": "image_visual", "primary_route": "image_visual", "qdrant_write_attempt_count": 0, "review_processing_required": true, "review_required": true, "review_score": 1.0, "route_confidence": 0.8, "route_dispatch_card_id": "route_dispatch::d92ad38df6e30d7a", "route_policies": {"blank_candidate": {"allowed": false, "is_primary": false, "is_secondary": false, "reasons": [], "route": "blank_candidate", "score": 0.1, "status": "not_selected"}, "image_visual": {"allowed": true, "is_primary": true, "is_secondary": false, "reasons": ["primary_route_image_visual"], "route": "image_visual", "score": 0.8, "status": "primary_route_allowed"}, "normal_text": {"allowed": true, "is_primary": false, "is_secondary": true, "reasons": ["secondary_route_normal_text_with_review_required"], "route": "normal_text", "score": 0.79, "status": "secondary_review_candidate_allowed"}, "review": {"allowed": true, "is_primary": false, "is_secondary": false, "reasons": ["route_manifest_review_required"], "route": "review", "score": 1.0, "status": "review_required"}, "table": {"allowed": true, "is_primary": false, "is_secondary": true, "reasons": ["secondary_route_table_with_review_required"], "route": "table", "score": 0.68, "status": "secondary_review_candidate_allowed"}}, "routing_reasons": ["human_review_artifact_present", "image_or_ink_evidence_supports_table_route", "image_visual_evidence_artifact_present", "ink_primary_route_normal_text", "ink_text_density_supports_text_route", "ocr_text_evidence_artifact_present", "ocr_text_evidence_supports_table_route", "ocr_text_evidence_supports_visual_route", "page_ink_route_evidence_available", "route_scores_conflict", "source_or_ocr_artifact_present", "specialized_route_evidence_competes_with_text_route", "table_cell_or_normalizer_artifact_present", "table_evidence_artifact_present", "visual_diagram_or_callout_artifact_present"], "safe_for_routing": true, "schema_version": "trace_net_route_dispatch_manifest_v1", "secondary_routes": ["normal_text", "table"], "source_page_id": "metadata_page_000001", "source_truth_mutation_allowed": false, "source_truth_mutations_performed": 0, "table_processing_allowed": true, "table_score": 0.68, "text_score": 0.79, "unsafe_dispatch_card": false}`
- OCR: no confirmed candidates
### t_p_120_1176_p000002 — `image_visual`
- OCR: no confirmed candidates
### t_p_120_1176_p000012 — `image_visual`
- OCR: no confirmed candidates
### t_p_120_1176_p000025 — `image_visual`
- OCR: no confirmed candidates
### t_p_120_1176_p000047 — `image_visual`
- OCR: no confirmed candidates
