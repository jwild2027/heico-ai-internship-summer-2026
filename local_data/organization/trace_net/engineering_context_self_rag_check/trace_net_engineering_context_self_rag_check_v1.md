# TRACE-Net Engineering Context Self-RAG Check v1

Quality status: **PASS**

## Summary

- Self-RAG records: 4
- Ready for Gemma draft: 1
- CRAG retry required: 3
- Status counts: `{'CRAG_RETRY_REQUIRED': 3, 'READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY': 1}`
- Source-truth strength counts: `{'partial_source_truth_context': 3, 'strong_exact_source_truth': 1}`
- Average evidence score: 51.75

## Records

### engineering_self_rag_0001 — CRAG_RETRY_REQUIRED

- Question: `This model number 123-45 needs to be 4 inches shorter. Any part that looks like that?`
- Intent: `engineering_change_candidate`
- Evidence strength score: `52`
- Source-truth strength: `partial_source_truth_context`
- Ready for Gemma draft: `False`
- CRAG retry required: `True`
- CRAG retry reasons: `['critical_missing:source_dimension_not_confirmed', 'missing_evidence:source_dimension_not_confirmed:table']`

### engineering_self_rag_0002 — READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY

- Question: `Find part number 120-29073-001 and nearby similar parts.`
- Intent: `exact_part_lookup`
- Evidence strength score: `90`
- Source-truth strength: `strong_exact_source_truth`
- Ready for Gemma draft: `True`
- CRAG retry required: `False`
- CRAG retry reasons: `[]`

### engineering_self_rag_0003 — CRAG_RETRY_REQUIRED

- Question: `Can I clean this part with solvent?`
- Intent: `repair_or_fault_context`
- Evidence strength score: `24`
- Source-truth strength: `partial_source_truth_context`
- Ready for Gemma draft: `False`
- CRAG retry required: `True`
- CRAG retry reasons: `['critical_missing:route_slot_unfilled', 'critical_missing:warning_caution_not_confirmed', 'evidence_strength_score_below_threshold', 'missing_evidence:route_slot_unfilled:image_visual', 'missing_evidence:warning_caution_not_confirmed:normal_text']`

### engineering_self_rag_0004 — CRAG_RETRY_REQUIRED

- Question: `Show visually similar callout parts in the same figure.`
- Intent: `visual_or_callout_similarity`
- Evidence strength score: `41`
- Source-truth strength: `partial_source_truth_context`
- Ready for Gemma draft: `False`
- CRAG retry required: `True`
- CRAG retry reasons: `['critical_missing:route_slot_unfilled', 'missing_evidence:route_slot_unfilled:image_visual']`
