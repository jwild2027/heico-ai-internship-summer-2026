# TRACE-Net Engineering Query Planner v1

Quality status: **PASS**

## Summary

- Query plans: 4
- Intent families: `{'engineering_change_candidate': 1, 'exact_part_lookup': 1, 'repair_or_fault_context': 1, 'visual_or_callout_similarity': 1}`
- Route context needs: `{'graph': 3, 'image_visual': 2, 'normal_text': 3, 'route_dispatch': 1, 'table': 4}`

## Query plans

### engineering_q0001 — engineering_change_candidate

- Question: `This model number 123-45 needs to be 4 inches shorter. Any part that looks like that?`
- Playbook: `dimensional_change_candidate_search`
- Seed entities: `['123-45']`
- Requested change: `{'property': 'length', 'direction': 'decrease', 'delta_value': 4.0, 'delta_unit': 'inches', 'requires_source_dimension_before_computing_target': True}`
- Retrieval plan: `['exact_seed_lookup', 'dimension_table_search', 'dash_number_variant_search', 'same_assembly_graph_search', 'same_ipl_table_search', 'engineering_text_context_search']`
- Route context needed: `['graph', 'normal_text', 'table']`

### engineering_q0002 — exact_part_lookup

- Question: `Find part number 120-29073-001 and nearby similar parts.`
- Playbook: `part_number_evidence_pack`
- Seed entities: `['120-29073-001']`
- Requested change: `None`
- Retrieval plan: `['table_exact_search', 'promoted_table_value_evidence_search', 'page_context_v2_search', 'graph_neighbor_search', 'route_handoff_lookup']`
- Route context needed: `['graph', 'normal_text', 'route_dispatch', 'table']`

### engineering_q0003 — repair_or_fault_context

- Question: `Can I clean this part with solvent?`
- Playbook: `fault_repair_procedure_reasoning`
- Seed entities: `[]`
- Requested change: `None`
- Retrieval plan: `['normal_text_page_context_search', 'exact_part_lookup', 'procedure_section_search', 'warning_caution_note_search', 'associated_figure_callout_search', 'associated_table_search']`
- Route context needed: `['image_visual', 'normal_text', 'table']`

### engineering_q0004 — visual_or_callout_similarity

- Question: `Show visually similar callout parts in the same figure.`
- Playbook: `visual_similarity_candidate_search`
- Seed entities: `[]`
- Requested change: `None`
- Retrieval plan: `['image_visual_handoff_search', 'callout_candidate_search', 'same_figure_graph_search', 'table_exact_cross_check', 'visual_observer_review_search']`
- Route context needed: `['graph', 'image_visual', 'table']`
