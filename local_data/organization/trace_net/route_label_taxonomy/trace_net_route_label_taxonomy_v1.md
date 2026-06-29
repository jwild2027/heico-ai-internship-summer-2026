# TRACE-Net Route Label Taxonomy v1

This artifact locks the canonical page route labels used by OCR/router accuracy work.

## Summary

- **answer_permission_count**: 0
- **can_answer_directly_count**: 0
- **can_prove_claims_count**: 0
- **canonical_route_label_count**: 9
- **legacy_route_alias_count**: 5
- **module**: trace_net_route_label_taxonomy_v1
- **opensearch_write_attempt_count**: 0
- **postgres_write_attempt_count**: 0
- **qdrant_write_attempt_count**: 0
- **ready_for_gold_label_review_workbook**: True
- **route_family_counts**: {'blank_or_sparse': 1, 'front_matter': 1, 'text': 2, 'structured_text': 2, 'visual': 1, 'mixed': 1, 'review': 1}
- **source_truth_mutation_allowed_count**: 0
- **unsafe_record_count**: 0
- **version**: v1

## Labels

### blank_candidate

A page with empty or near-empty OCR and low visual/ink signal. It is not source-truth blank until confirmed.

- family: `blank_or_sparse`
- processor: `blank_candidate_confirmation_scan`
- qdrant policy: `do_not_embed_blank_candidates`
- review policy: `human_confirm_blank_before_source_truth_blank`

### cover_or_title_page

A cover, title, revision title, or publication identity page. Usually dense text but not a table/evidence table.

- family: `front_matter`
- processor: `front_matter_identity_scan`
- qdrant policy: `embed_short_publication_identity_summary_only`
- review policy: `review_if_confused_with_table_or_revision_record`

### normal_text

Narrative, explanatory, introductory, service, maintenance, or ordinary manual prose without dominant procedure or table structure.

- family: `text`
- processor: `normal_text_page_context_scan`
- qdrant policy: `embed_ocr_chunks_and_page_context_summary`
- review policy: `review_if_table_or_figure_signals_tie_with_text_signals`

### procedure_or_description

Description, operation, removal, installation, cleaning, inspection, repair, or other procedural/prose page.

- family: `text`
- processor: `procedure_description_context_scan`
- qdrant policy: `embed_procedure_chunks_with_strong_page_trace`
- review policy: `review_if_safety_warning_or_table_like_layout_is_uncertain`

### table_or_index

Structured list, index, LEP, contents, vendor list, numerical index, or repeated row/column table that is not specifically a detailed parts list.

- family: `structured_text`
- processor: `table_ocr_table_candidate_scan`
- qdrant policy: `embed_table_summary_or_evidence_cards_only_not_raw_table_blob`
- review policy: `review_if_header_only_or_prose_dominant`

### detailed_parts_list

Illustrated/detailed parts list page with item numbers, part numbers, nomenclature, units-per-assembly, figure-item references, or equivalent IPL structure.

- family: `structured_text`
- processor: `detailed_parts_list_extraction_scan`
- qdrant policy: `embed_extracted_part_evidence_cards_and_summaries`
- review policy: `review_if_part_numbers_missing_or_column_boundaries_uncertain`

### image_visual_diagram

Diagram, figure, callout illustration, exploded view, or labeled technical drawing requiring image/vision handling plus OCR support.

- family: `visual`
- processor: `image_visual_ocr_and_vision_queue_scan`
- qdrant policy: `embed_only_ocr_supported_visual_context_cards`
- review policy: `review_raw_vision_output_before_webui_use_unless_ocr_supported`

### mixed_text_and_figure

Page containing both meaningful prose/procedure content and a figure/diagram or visual region where both routes may be useful.

- family: `mixed`
- processor: `mixed_text_visual_split_scan`
- qdrant policy: `embed_text_summary_and_ocr_supported_visual_context_separately`
- review policy: `review_region_split_if_downstream_evidence_depends_on_visual_claims`

### review_required

Fallback for low-confidence, conflicting, corrupted, OCR-failed, route-tied, or safety-sensitive pages.

- family: `review`
- processor: `human_review_route_resolution_scan`
- qdrant policy: `do_not_embed_as_normal_context_until_reviewed`
- review policy: `human_or_policy_review_required_before_downstream_route_commit`
