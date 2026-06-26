# TRACE-Net Engineering Context Pack Builder v1.2

Quality status: **PASS**

## Summary

- Context packs: 4
- Artifact corpus records: 23044
- Artifact record counts: `{'fishnet_route_dispatch_handoff': 1019, 'table_exact_search_adapter': 1515, 'page_context_v2': 510, 'leiden_communities': 20000, 'image_visual_observer': 0}`
- Missing optional artifact inputs: `[{'artifact_name': 'image_visual_observer', 'route': 'image_visual', 'path': 'local_data\\organization\\trace_net\\e2e_image_visual_observer_route\\trace_net_e2e_image_visual_observer_route_v34_3.json', 'optional': True, 'missing': True}]`
- Evidence capsules: 84
- High-signal capsules: 84
- Fallback capsules: 0
- Route capsule counts: `{'graph': 24, 'normal_text': 20, 'route_dispatch': 8, 'table': 32}`
- Missing evidence notes: 4

## Packs

### engineering_context_pack_0001 — engineering_change_candidate

- Question: `This model number 123-45 needs to be 4 inches shorter. Any part that looks like that?`
- Playbook: `dimensional_change_candidate_search`
- Evidence capsules: `22`
- High-signal capsules: `22`
- Filled route slots: `3/3`
- High-signal filled slots: `3/3`
- Missing evidence: `[{'missing_type': 'source_dimension_not_confirmed', 'route': 'table', 'reason': 'question requests a dimensional change but selected table evidence does not clearly prove a source dimension', 'crag_retry_recommended': True}]`

### engineering_context_pack_0002 — exact_part_lookup

- Question: `Find part number 120-29073-001 and nearby similar parts.`
- Playbook: `part_number_evidence_pack`
- Evidence capsules: `30`
- High-signal capsules: `30`
- Filled route slots: `4/4`
- High-signal filled slots: `4/4`
- Missing evidence: `[]`

### engineering_context_pack_0003 — repair_or_fault_context

- Question: `Can I clean this part with solvent?`
- Playbook: `fault_repair_procedure_reasoning`
- Evidence capsules: `16`
- High-signal capsules: `16`
- Filled route slots: `2/3`
- High-signal filled slots: `2/3`
- Missing evidence: `[{'missing_type': 'route_slot_unfilled', 'route': 'image_visual', 'reason': 'no available artifact evidence selected for route image_visual', 'crag_retry_recommended': True}, {'missing_type': 'warning_caution_not_confirmed', 'route': 'normal_text', 'reason': 'procedure question should check warnings/cautions; selected evidence did not clearly include them', 'crag_retry_recommended': True}]`

### engineering_context_pack_0004 — visual_or_callout_similarity

- Question: `Show visually similar callout parts in the same figure.`
- Playbook: `visual_similarity_candidate_search`
- Evidence capsules: `16`
- High-signal capsules: `16`
- Filled route slots: `2/3`
- High-signal filled slots: `2/3`
- Missing evidence: `[{'missing_type': 'route_slot_unfilled', 'route': 'image_visual', 'reason': 'no available artifact evidence selected for route image_visual', 'crag_retry_recommended': True}]`
