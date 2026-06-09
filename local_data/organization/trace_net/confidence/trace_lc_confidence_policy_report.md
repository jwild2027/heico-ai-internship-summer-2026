# TRACE-Net Layer Confidence Stage 3 Policy

Status: **OK**
Version: `trace_lc_confidence_policy_v1`

## Stage 2 signal

- **agreement_rate**: 0.239382
- **within_one_tier_rate**: 0.986762
- **disagreement_records**: 1379
- **source_trace_confidence_below_A_records**: 509
- **rule_excludes_confidence_high_records**: 710
- **rule_includes_confidence_low_records**: 24
- **avg_usable_confidence**: 0.787436

## Policy summary

| Layer | Purpose | Routing authority | Max auto tier | Min RAG tier | Default RAG action |
|---|---|---|---|---|---|
| part_catalog | verified_part_evidence | rule_tier_controls_until_claim_level_calibration | A | A | include_as_verified_part_evidence |
| source_trace | source_truth | rule_tier_controls_routing_confidence_is_diagnostic | A | A | include_as_source_evidence |
| table_candidate | routing_signal | route_grouping_controls_operations | B | none | exclude_until_table_tiles_exist |
| table_tile_text_refined | derived_table_text_and_part_evidence | hybrid_rule_and_confidence_after_more_validation | A | B | include_as_derived_context |
| table_tiles | preprocessing_artifact | route_grouping_controls_operations | B | none | exclude_until_table_text_exists |
| visual_text | model_derived_visual_context | rule_tier_controls_until_claim_level_review | B | B | include_as_derived_context |

## Layer details

### part_catalog

- purpose: `verified_part_evidence`
- policy role: `promotes_catalog_supported_part_mentions`
- confidence use: `rank_part_evidence_strength_and_review_edge_cases`
- thresholds: `{'A': 0.82, 'B': 0.66, 'C': 0.42}`
- weights: `{'source_trace': 0.25, 'graph_support': 0.2, 'ocr_support': 0.1, 'part_catalog': 0.4, 'extraction_layer': 0.05}`
- hard blocks: `['catalog_conflict', 'invalid_part_pattern', 'source_untraceable']`
- hard promotions: `['catalog_verified and source_trace_verified', 'same_page_part_mention_present']`
- note: Catalog evidence is allowed to be A when source trace and catalog support agree.
- note: Generic confidence marked catalog records as B because it lacked layer-specific promotions.

### source_trace

- purpose: `source_truth`
- policy role: `proves_page_source_exists`
- confidence use: `calibrate_source_completeness_not_claim_truth`
- thresholds: `{'A': 0.75, 'B': 0.6, 'C': 0.4}`
- weights: `{'source_trace': 0.7, 'graph_support': 0.2, 'ocr_support': 0.05, 'part_catalog': 0.0, 'extraction_layer': 0.05}`
- hard blocks: `['missing_page', 'missing_tiff', 'missing_source_url', 'source_untraceable']`
- hard promotions: `['source_trace.status in source_verified,local_source_verified', 'page_exists and tiff_exists and source_url_present']`
- note: Stage 2 showed all source_trace records were below confidence A under the generic formula.
- note: This layer is not a claim extraction layer, so OCR/catalog absence must not demote source truth.

### table_candidate

- purpose: `routing_signal`
- policy role: `routes_pages_to_table_crop_tile_or_review`
- confidence use: `prioritize_table_candidate_review_not_rag_truth`
- thresholds: `{'A': 0.9, 'B': 0.66, 'C': 0.4}`
- weights: `{'source_trace': 0.2, 'graph_support': 0.35, 'ocr_support': 0.05, 'part_catalog': 0.05, 'extraction_layer': 0.35}`
- hard blocks: `['graph_gate_blocked', 'layout_gate_blocked', 'figure_without_table_trait']`
- hard promotions: `['passed_graph_gate and passed_layout_gate']`
- note: Table candidates are routing artifacts; they should not enter RAG directly.
- note: High confidence here means process priority, not factual confidence.

### table_tile_text_refined

- purpose: `derived_table_text_and_part_evidence`
- policy role: `gates_refined_tile_text_before_rag`
- confidence use: `decide_A_B_C_for_refined_table_text`
- thresholds: `{'A': 0.82, 'B': 0.64, 'C': 0.4}`
- weights: `{'source_trace': 0.25, 'graph_support': 0.2, 'ocr_support': 0.1, 'part_catalog': 0.35, 'extraction_layer': 0.1}`
- hard blocks: `['index_label_as_part', 'metadata_leakage', 'prompt_template_leakage', 'source_untraceable']`
- hard promotions: `['catalog_supported_part_numbers_found and source_trace_verified']`
- note: B tier is appropriate for derived table context even when not canonical source truth.
- note: A tier should require catalog support and source trace; C tier remains review/exclude.

### table_tiles

- purpose: `preprocessing_artifact`
- policy role: `proves_table_regions_were_cut_for_extraction`
- confidence use: `verify_tiles_exist_before_tile_text_ocr`
- thresholds: `{'A': 0.9, 'B': 0.65, 'C': 0.4}`
- weights: `{'source_trace': 0.25, 'graph_support': 0.25, 'ocr_support': 0.0, 'part_catalog': 0.0, 'extraction_layer': 0.5}`
- hard blocks: `['missing_tile_images', 'missing_preprocessed_image', 'source_untraceable']`
- hard promotions: `['tile_images_created and source_trace_verified']`
- note: Table tiles are not text evidence yet; they trigger the next OCR/extraction step.
- note: Stage 2 showed perfect agreement for table_tiles, so this policy preserves current behavior.

### visual_text

- purpose: `model_derived_visual_context`
- policy role: `keeps_vision_model_output_conservative`
- confidence use: `identify_safe_derived_context_and_high_risk_visual_claims`
- thresholds: `{'A': 0.92, 'B': 0.74, 'C': 0.45}`
- weights: `{'source_trace': 0.25, 'graph_support': 0.25, 'ocr_support': 0.15, 'part_catalog': 0.1, 'extraction_layer': 0.25}`
- hard blocks: `['metadata_leakage', 'prompt_template_leakage', 'refusal_like', 'section_bleed_unrepaired']`
- hard promotions: `['low_risk and graph_support_strong and source_trace_verified']`
- note: Visual text remains derived context, not canonical source truth.
- note: Stage 2 showed high risk and low average confidence for visual_text.

