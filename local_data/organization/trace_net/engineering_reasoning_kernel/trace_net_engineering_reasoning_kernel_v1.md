# TRACE-Net Engineering Reasoning Kernel v1

Quality status: **PASS**

## Summary

- Playbooks: 5
- Example cards: 4
- Query plan templates: 1
- Route dispatch available: True

## Engineering playbooks

### similar_part_candidate_search

- Intent family: `similarity_or_substitution_candidate`
- Trust tier: `candidate_guidance_only`
- Retrieval plan: `['exact_seed_lookup', 'same_assembly_graph_search', 'same_ipl_table_search', 'same_figure_callout_search', 'nomenclature_similarity_search', 'vector_semantic_similarity_search', 'page_context_v2_supporting_text_search']`

### dimensional_change_candidate_search

- Intent family: `engineering_change_candidate`
- Trust tier: `candidate_guidance_only`
- Retrieval plan: `['exact_seed_lookup', 'dimension_table_search', 'dash_number_variant_search', 'same_assembly_graph_search', 'same_ipl_table_search', 'engineering_text_context_search']`

### fault_repair_procedure_reasoning

- Intent family: `repair_or_fault_context`
- Trust tier: `source_summary_required`
- Retrieval plan: `['normal_text_page_context_search', 'exact_part_lookup', 'procedure_section_search', 'warning_caution_note_search', 'associated_figure_callout_search', 'associated_table_search']`

### part_number_evidence_pack

- Intent family: `exact_part_lookup`
- Trust tier: `source_evidence_first`
- Retrieval plan: `['table_exact_search', 'promoted_table_value_evidence_search', 'page_context_v2_search', 'graph_neighbor_search', 'route_handoff_lookup']`

### visual_similarity_candidate_search

- Intent family: `visual_or_callout_similarity`
- Trust tier: `visual_candidate_only`
- Retrieval plan: `['image_visual_handoff_search', 'callout_candidate_search', 'same_figure_graph_search', 'table_exact_cross_check', 'visual_observer_review_search']`

## Global forbidden claims

- approved replacement without explicit source evidence
- guaranteed fit/form/function
- safe to install
- engineering approval
- uncited repair procedure
- uncited dimension or material claim