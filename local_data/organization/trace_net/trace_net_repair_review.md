# TRACE-Net repair plan

Status: **OK**

## Summary

- records: 25
- auto_repair_candidate_records: 24
- human_review_records: 25
- rag_excluded_records: 25
- rag_included_records: 0
- table_repair_records: 17
- table_repair_high_records: 4
- table_repair_medium_records: 13
- table_candidate_review_records: 6
- cleanup_repair_records: 0
- ocr_graph_validation_records: 1
- rerun_model_records: 0
- unplanned_problem_records: 0

## trust_tier_counts
- C: 25

## repair_route_counts
- human_review_route: 1
- ocr_graph_validation_review_route: 1
- table_candidate_review_route: 6
- table_crop_tile_repair_route_high: 4
- table_crop_tile_repair_route_medium: 13

## repair_action_counts
- review_table_candidate_before_extraction: 6
- run_ocr_graph_validation: 1
- send_to_human_review: 1
- send_to_table_crop_tile_route: 17

## review_trait_counts
- hallucination_risk: 13
- needs_human_review: 25
- prompt_template_repaired: 16
- section_bleed_repaired: 15
- summary_heavy: 1
- suspicious_phrase: 3
- table_expected_but_not_extracted: 23

## priority_counts
- high: 23
- medium: 2

## Sample repairs

### t_p_120_1176_p000001

- trust tier: `C`
- current RAG trait: `exclude_visual_text`
- priority: `medium`
- primary route: `human_review_route`
- primary action: `send_to_human_review`
- review traits: needs_human_review, section_bleed_repaired
- action queue:
  - `send_to_human_review` via `human_review_route`: trust_tier_c_without_specific_auto_repair

### t_p_120_1176_p000003

- trust tier: `C`
- current RAG trait: `exclude_visual_text`
- priority: `high`
- primary route: `table_crop_tile_repair_route_medium`
- primary action: `send_to_table_crop_tile_route`
- review traits: hallucination_risk, needs_human_review, table_expected_but_not_extracted
- action queue:
  - `send_to_table_crop_tile_route` via `table_crop_tile_repair_route_medium`: table_expected_but_rows_missing
  - `run_ocr_graph_validation` via `ocr_graph_validation_review_route`: hallucination_or_suspicious_phrase_needs_grounding
  - `keep_in_human_review_queue` via `human_review_route`: derived_visual_text_not_yet_rag_safe

### t_p_120_1176_p000004

- trust tier: `C`
- current RAG trait: `exclude_visual_text`
- priority: `high`
- primary route: `table_candidate_review_route`
- primary action: `review_table_candidate_before_extraction`
- review traits: needs_human_review, prompt_template_repaired, table_expected_but_not_extracted
- action queue:
  - `review_table_candidate_before_extraction` via `table_candidate_review_route`: weak_table_signal_needs_route_review
  - `keep_in_human_review_queue` via `human_review_route`: derived_visual_text_not_yet_rag_safe

### t_p_120_1176_p000005

- trust tier: `C`
- current RAG trait: `exclude_visual_text`
- priority: `high`
- primary route: `table_crop_tile_repair_route_medium`
- primary action: `send_to_table_crop_tile_route`
- review traits: hallucination_risk, needs_human_review, section_bleed_repaired, table_expected_but_not_extracted
- action queue:
  - `send_to_table_crop_tile_route` via `table_crop_tile_repair_route_medium`: table_expected_but_rows_missing
  - `run_ocr_graph_validation` via `ocr_graph_validation_review_route`: hallucination_or_suspicious_phrase_needs_grounding
  - `keep_in_human_review_queue` via `human_review_route`: derived_visual_text_not_yet_rag_safe

### t_p_120_1176_p000006

- trust tier: `C`
- current RAG trait: `exclude_visual_text`
- priority: `high`
- primary route: `table_crop_tile_repair_route_medium`
- primary action: `send_to_table_crop_tile_route`
- review traits: hallucination_risk, needs_human_review, prompt_template_repaired, table_expected_but_not_extracted
- action queue:
  - `send_to_table_crop_tile_route` via `table_crop_tile_repair_route_medium`: table_expected_but_rows_missing
  - `run_ocr_graph_validation` via `ocr_graph_validation_review_route`: hallucination_or_suspicious_phrase_needs_grounding
  - `keep_in_human_review_queue` via `human_review_route`: derived_visual_text_not_yet_rag_safe

### t_p_120_1176_p000007

- trust tier: `C`
- current RAG trait: `exclude_visual_text`
- priority: `high`
- primary route: `table_crop_tile_repair_route_medium`
- primary action: `send_to_table_crop_tile_route`
- review traits: needs_human_review, prompt_template_repaired, section_bleed_repaired, table_expected_but_not_extracted
- action queue:
  - `send_to_table_crop_tile_route` via `table_crop_tile_repair_route_medium`: table_expected_but_rows_missing
  - `keep_in_human_review_queue` via `human_review_route`: derived_visual_text_not_yet_rag_safe

### t_p_120_1176_p000008

- trust tier: `C`
- current RAG trait: `exclude_visual_text`
- priority: `high`
- primary route: `table_crop_tile_repair_route_medium`
- primary action: `send_to_table_crop_tile_route`
- review traits: hallucination_risk, needs_human_review, prompt_template_repaired, table_expected_but_not_extracted
- action queue:
  - `send_to_table_crop_tile_route` via `table_crop_tile_repair_route_medium`: table_expected_but_rows_missing
  - `run_ocr_graph_validation` via `ocr_graph_validation_review_route`: hallucination_or_suspicious_phrase_needs_grounding
  - `keep_in_human_review_queue` via `human_review_route`: derived_visual_text_not_yet_rag_safe

### t_p_120_1176_p000009

- trust tier: `C`
- current RAG trait: `exclude_visual_text`
- priority: `high`
- primary route: `table_crop_tile_repair_route_medium`
- primary action: `send_to_table_crop_tile_route`
- review traits: needs_human_review, prompt_template_repaired, table_expected_but_not_extracted
- action queue:
  - `send_to_table_crop_tile_route` via `table_crop_tile_repair_route_medium`: table_expected_but_rows_missing
  - `keep_in_human_review_queue` via `human_review_route`: derived_visual_text_not_yet_rag_safe

### t_p_120_1176_p000010

- trust tier: `C`
- current RAG trait: `exclude_visual_text`
- priority: `high`
- primary route: `table_crop_tile_repair_route_high`
- primary action: `send_to_table_crop_tile_route`
- review traits: hallucination_risk, needs_human_review, prompt_template_repaired, table_expected_but_not_extracted
- action queue:
  - `send_to_table_crop_tile_route` via `table_crop_tile_repair_route_high`: table_expected_but_rows_missing
  - `run_ocr_graph_validation` via `ocr_graph_validation_review_route`: hallucination_or_suspicious_phrase_needs_grounding
  - `keep_in_human_review_queue` via `human_review_route`: derived_visual_text_not_yet_rag_safe

### t_p_120_1176_p000011

- trust tier: `C`
- current RAG trait: `exclude_visual_text`
- priority: `high`
- primary route: `table_crop_tile_repair_route_high`
- primary action: `send_to_table_crop_tile_route`
- review traits: needs_human_review, prompt_template_repaired, table_expected_but_not_extracted
- action queue:
  - `send_to_table_crop_tile_route` via `table_crop_tile_repair_route_high`: table_expected_but_rows_missing
  - `keep_in_human_review_queue` via `human_review_route`: derived_visual_text_not_yet_rag_safe

### t_p_120_1176_p000013

- trust tier: `C`
- current RAG trait: `exclude_visual_text`
- priority: `high`
- primary route: `table_candidate_review_route`
- primary action: `review_table_candidate_before_extraction`
- review traits: needs_human_review, prompt_template_repaired, section_bleed_repaired, table_expected_but_not_extracted
- action queue:
  - `review_table_candidate_before_extraction` via `table_candidate_review_route`: weak_table_signal_needs_route_review
  - `keep_in_human_review_queue` via `human_review_route`: derived_visual_text_not_yet_rag_safe

### t_p_120_1176_p000014

- trust tier: `C`
- current RAG trait: `exclude_visual_text`
- priority: `high`
- primary route: `table_candidate_review_route`
- primary action: `review_table_candidate_before_extraction`
- review traits: hallucination_risk, needs_human_review, prompt_template_repaired, section_bleed_repaired, summary_heavy, table_expected_but_not_extracted
- action queue:
  - `review_table_candidate_before_extraction` via `table_candidate_review_route`: weak_table_signal_needs_route_review
  - `run_ocr_graph_validation` via `ocr_graph_validation_review_route`: hallucination_or_suspicious_phrase_needs_grounding
  - `rerun_or_rewrite_visual_summary` via `summary_rewrite_repair_route`: summary_heavy_output_needs_tighter_context
  - `keep_in_human_review_queue` via `human_review_route`: derived_visual_text_not_yet_rag_safe

### t_p_120_1176_p000015

- trust tier: `C`
- current RAG trait: `exclude_visual_text`
- priority: `high`
- primary route: `table_crop_tile_repair_route_medium`
- primary action: `send_to_table_crop_tile_route`
- review traits: needs_human_review, prompt_template_repaired, section_bleed_repaired, table_expected_but_not_extracted
- action queue:
  - `send_to_table_crop_tile_route` via `table_crop_tile_repair_route_medium`: table_expected_but_rows_missing
  - `keep_in_human_review_queue` via `human_review_route`: derived_visual_text_not_yet_rag_safe

### t_p_120_1176_p000016

- trust tier: `C`
- current RAG trait: `exclude_visual_text`
- priority: `high`
- primary route: `table_candidate_review_route`
- primary action: `review_table_candidate_before_extraction`
- review traits: hallucination_risk, needs_human_review, prompt_template_repaired, section_bleed_repaired, table_expected_but_not_extracted
- action queue:
  - `review_table_candidate_before_extraction` via `table_candidate_review_route`: weak_table_signal_needs_route_review
  - `run_ocr_graph_validation` via `ocr_graph_validation_review_route`: hallucination_or_suspicious_phrase_needs_grounding
  - `keep_in_human_review_queue` via `human_review_route`: derived_visual_text_not_yet_rag_safe

### t_p_120_1176_p000017

- trust tier: `C`
- current RAG trait: `exclude_visual_text`
- priority: `high`
- primary route: `table_crop_tile_repair_route_medium`
- primary action: `send_to_table_crop_tile_route`
- review traits: needs_human_review, prompt_template_repaired, table_expected_but_not_extracted
- action queue:
  - `send_to_table_crop_tile_route` via `table_crop_tile_repair_route_medium`: table_expected_but_rows_missing
  - `keep_in_human_review_queue` via `human_review_route`: derived_visual_text_not_yet_rag_safe

### t_p_120_1176_p000018

- trust tier: `C`
- current RAG trait: `exclude_visual_text`
- priority: `high`
- primary route: `table_crop_tile_repair_route_medium`
- primary action: `send_to_table_crop_tile_route`
- review traits: needs_human_review, prompt_template_repaired, section_bleed_repaired, suspicious_phrase, table_expected_but_not_extracted
- action queue:
  - `send_to_table_crop_tile_route` via `table_crop_tile_repair_route_medium`: table_expected_but_rows_missing
  - `run_ocr_graph_validation` via `ocr_graph_validation_review_route`: hallucination_or_suspicious_phrase_needs_grounding
  - `keep_in_human_review_queue` via `human_review_route`: derived_visual_text_not_yet_rag_safe

### t_p_120_1176_p000019

- trust tier: `C`
- current RAG trait: `exclude_visual_text`
- priority: `medium`
- primary route: `ocr_graph_validation_review_route`
- primary action: `run_ocr_graph_validation`
- review traits: hallucination_risk, needs_human_review, section_bleed_repaired
- action queue:
  - `run_ocr_graph_validation` via `ocr_graph_validation_review_route`: hallucination_or_suspicious_phrase_needs_grounding
  - `keep_in_human_review_queue` via `human_review_route`: derived_visual_text_not_yet_rag_safe

### t_p_120_1176_p000020

- trust tier: `C`
- current RAG trait: `exclude_visual_text`
- priority: `high`
- primary route: `table_crop_tile_repair_route_high`
- primary action: `send_to_table_crop_tile_route`
- review traits: needs_human_review, section_bleed_repaired, table_expected_but_not_extracted
- action queue:
  - `send_to_table_crop_tile_route` via `table_crop_tile_repair_route_high`: table_expected_but_rows_missing
  - `keep_in_human_review_queue` via `human_review_route`: derived_visual_text_not_yet_rag_safe

### t_p_120_1176_p000021

- trust tier: `C`
- current RAG trait: `exclude_visual_text`
- priority: `high`
- primary route: `table_crop_tile_repair_route_medium`
- primary action: `send_to_table_crop_tile_route`
- review traits: hallucination_risk, needs_human_review, section_bleed_repaired, suspicious_phrase, table_expected_but_not_extracted
- action queue:
  - `send_to_table_crop_tile_route` via `table_crop_tile_repair_route_medium`: table_expected_but_rows_missing
  - `run_ocr_graph_validation` via `ocr_graph_validation_review_route`: hallucination_or_suspicious_phrase_needs_grounding
  - `keep_in_human_review_queue` via `human_review_route`: derived_visual_text_not_yet_rag_safe

### t_p_120_1176_p000022

- trust tier: `C`
- current RAG trait: `exclude_visual_text`
- priority: `high`
- primary route: `table_candidate_review_route`
- primary action: `review_table_candidate_before_extraction`
- review traits: hallucination_risk, needs_human_review, section_bleed_repaired, suspicious_phrase, table_expected_but_not_extracted
- action queue:
  - `review_table_candidate_before_extraction` via `table_candidate_review_route`: weak_table_signal_needs_route_review
  - `run_ocr_graph_validation` via `ocr_graph_validation_review_route`: hallucination_or_suspicious_phrase_needs_grounding
  - `keep_in_human_review_queue` via `human_review_route`: derived_visual_text_not_yet_rag_safe

### t_p_120_1176_p000023

- trust tier: `C`
- current RAG trait: `exclude_visual_text`
- priority: `high`
- primary route: `table_crop_tile_repair_route_high`
- primary action: `send_to_table_crop_tile_route`
- review traits: needs_human_review, prompt_template_repaired, section_bleed_repaired, table_expected_but_not_extracted
- action queue:
  - `send_to_table_crop_tile_route` via `table_crop_tile_repair_route_high`: table_expected_but_rows_missing
  - `keep_in_human_review_queue` via `human_review_route`: derived_visual_text_not_yet_rag_safe

### t_p_120_1176_p000024

- trust tier: `C`
- current RAG trait: `exclude_visual_text`
- priority: `high`
- primary route: `table_crop_tile_repair_route_medium`
- primary action: `send_to_table_crop_tile_route`
- review traits: hallucination_risk, needs_human_review, section_bleed_repaired, table_expected_but_not_extracted
- action queue:
  - `send_to_table_crop_tile_route` via `table_crop_tile_repair_route_medium`: table_expected_but_rows_missing
  - `run_ocr_graph_validation` via `ocr_graph_validation_review_route`: hallucination_or_suspicious_phrase_needs_grounding
  - `keep_in_human_review_queue` via `human_review_route`: derived_visual_text_not_yet_rag_safe

### t_p_120_1176_p000026

- trust tier: `C`
- current RAG trait: `exclude_visual_text`
- priority: `high`
- primary route: `table_candidate_review_route`
- primary action: `review_table_candidate_before_extraction`
- review traits: needs_human_review, prompt_template_repaired, table_expected_but_not_extracted
- action queue:
  - `review_table_candidate_before_extraction` via `table_candidate_review_route`: weak_table_signal_needs_route_review
  - `keep_in_human_review_queue` via `human_review_route`: derived_visual_text_not_yet_rag_safe

### t_p_120_1176_p000027

- trust tier: `C`
- current RAG trait: `exclude_visual_text`
- priority: `high`
- primary route: `table_crop_tile_repair_route_medium`
- primary action: `send_to_table_crop_tile_route`
- review traits: hallucination_risk, needs_human_review, prompt_template_repaired, table_expected_but_not_extracted
- action queue:
  - `send_to_table_crop_tile_route` via `table_crop_tile_repair_route_medium`: table_expected_but_rows_missing
  - `run_ocr_graph_validation` via `ocr_graph_validation_review_route`: hallucination_or_suspicious_phrase_needs_grounding
  - `keep_in_human_review_queue` via `human_review_route`: derived_visual_text_not_yet_rag_safe

### t_p_120_1176_p000028

- trust tier: `C`
- current RAG trait: `exclude_visual_text`
- priority: `high`
- primary route: `table_crop_tile_repair_route_medium`
- primary action: `send_to_table_crop_tile_route`
- review traits: hallucination_risk, needs_human_review, section_bleed_repaired, table_expected_but_not_extracted
- action queue:
  - `send_to_table_crop_tile_route` via `table_crop_tile_repair_route_medium`: table_expected_but_rows_missing
  - `run_ocr_graph_validation` via `ocr_graph_validation_review_route`: hallucination_or_suspicious_phrase_needs_grounding
  - `keep_in_human_review_queue` via `human_review_route`: derived_visual_text_not_yet_rag_safe
