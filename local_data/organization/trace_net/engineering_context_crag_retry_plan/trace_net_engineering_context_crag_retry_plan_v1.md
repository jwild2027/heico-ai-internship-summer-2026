# TRACE-Net Engineering Context CRAG Retry Plan v1.1

Quality status: **PASS**

## Summary

- CRAG retry plans: 3
- Ready for CRAG execution: 3
- Retry priority counts: `{'high': 2, 'medium': 1}`
- Target route counts: `{'image_visual': 2, 'normal_text': 1, 'table': 1}`
- Unknown target route count: `0`
- Missing evidence type counts: `{'route_slot_unfilled': 2, 'source_dimension_not_confirmed': 1, 'warning_caution_not_confirmed': 1}`

## Retry plans

### engineering_crag_retry_plan_0001 — medium

- Question: `This model number 123-45 needs to be 4 inches shorter. Any part that looks like that?`
- Intent: `engineering_change_candidate`
- Source Self-RAG status: `CRAG_RETRY_REQUIRED`
- Target routes: `['table']`
- Target artifacts: `['promoted_table_value_evidence', 'source_normalized_table_value_records', 'table_exact_search_adapter', 'table_route_evidence_package']`
- Query hints: `['This model number 123-45 needs to be 4 inches shorter. Any part that looks like that?', '123-45 shorter part dimension length inch inches mm cm', 'same part family dash number variant dimension length', 'IPL table dimensions repair material part number']`

### engineering_crag_retry_plan_0002 — high

- Question: `Can I clean this part with solvent?`
- Intent: `repair_or_fault_context`
- Source Self-RAG status: `CRAG_RETRY_REQUIRED`
- Target routes: `['image_visual', 'normal_text']`
- Target artifacts: `['callout_candidates', 'fishnet OCR text', 'image_visual_handoff', 'image_visual_observer_route', 'normal_text_handoff', 'page_context_v2', 'visual_part_verification_records']`
- Query hints: `['Can I clean this part with solvent?', 'clean solvent part figure callout visual diagram', 'same figure callout neighboring parts visual similarity', 'clean solvent part WARNING CAUTION NOTE', 'cleaning solvent warning caution procedure', 'cleaners toxic ingredients gloves skin eyes']`

### engineering_crag_retry_plan_0003 — high

- Question: `Show visually similar callout parts in the same figure.`
- Intent: `visual_or_callout_similarity`
- Source Self-RAG status: `CRAG_RETRY_REQUIRED`
- Target routes: `['image_visual']`
- Target artifacts: `['callout_candidates', 'image_visual_handoff', 'image_visual_observer_route', 'visual_part_verification_records']`
- Query hints: `['Show visually similar callout parts in the same figure.', 'callout figure visual part figure callout visual diagram', 'same figure callout neighboring parts visual similarity']`
