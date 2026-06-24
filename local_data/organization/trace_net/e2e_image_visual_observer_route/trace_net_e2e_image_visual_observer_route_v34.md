# TRACE-Net E2E Image Visual Observer Route v34

Quality status: **PASS**
Status: `E2E_IMAGE_VISUAL_OBSERVER_ROUTE_READY`

## Summary
- sample_query_count: 4
- sample_success_count: 4
- visual_package_count: 4
- image_quality_card_count: 4
- visual_observation_card_count: 4
- llava_observer_card_count: 4
- guidance_only_visual_card_count: 4
- source_truth_required_for_visual_claim_count: 4
- visual_proof_authority_violation_count: 0
- unsupported_visual_claim_count: 0
- self_rag_sample_count: 4
- crag_sample_count: 4
- crag_retry_required_count: 0
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Contract
- LLaVA/image observations are guidance only, not proof authority.
- Source truth is required before factual part/manual claims.
- Low-confidence visual observations require human review or source-truth confirmation.
- This stage does not write to Postgres, Qdrant, OpenSearch, or source truth.

## Sample records
### tracenet_visual_package_v34_06f08a6a9fbae844
- query: Inspect this uploaded manual page image and describe visible structure.
- intent: uploaded_image_visual_inspection
- mode: visual_observer_guidance
- final_gate_status: VISUAL_FINAL_GATE_PASS
- self_rag: SELF_RAG_VISUAL_GUIDANCE_READY / visual_guidance_ready
- crag: CRAG_VISUAL_NO_RETRY_GUIDANCE_READY retry_required=False
- preview: TRACE-Net built a visual guidance package for 1 image(s). The primary visual type is diagram_candidate. Observations: image appears to be diagram_candidate; manual-style visual inspection required; possible callout labels; possible arrows or leader lines. These visual observations are guidance only and do not prove factual part/manual claims without source-truth confirmation. A diagram draft can be generated as guidance from the visual package.

### tracenet_visual_package_v34_86f9e0d98fbee60c
- query: Does this image contain a diagram or callouts?
- intent: uploaded_image_diagram_draft
- mode: diagram_draft_guidance
- final_gate_status: VISUAL_FINAL_GATE_PASS
- self_rag: SELF_RAG_VISUAL_GUIDANCE_READY / visual_guidance_ready
- crag: CRAG_VISUAL_NO_RETRY_GUIDANCE_READY retry_required=False
- preview: TRACE-Net built a visual guidance package for 1 image(s). The primary visual type is callout_diagram_candidate. Observations: image appears to be callout_diagram_candidate; manual-style visual inspection required; possible callout labels; possible arrows or leader lines. These visual observations are guidance only and do not prove factual part/manual claims without source-truth confirmation. A diagram draft can be generated as guidance from the v

### tracenet_visual_package_v34_efddfdabf97560b7
- query: Turn this image into a diagram draft.
- intent: uploaded_image_diagram_draft
- mode: diagram_draft_guidance
- final_gate_status: VISUAL_FINAL_GATE_PASS
- self_rag: SELF_RAG_VISUAL_GUIDANCE_READY / visual_guidance_ready
- crag: CRAG_VISUAL_NO_RETRY_GUIDANCE_READY retry_required=False
- preview: TRACE-Net built a visual guidance package for 1 image(s). The primary visual type is diagram_generation_draft. Observations: image appears to be diagram_generation_draft; manual-style visual inspection required; possible callout labels; possible arrows or leader lines. These visual observations are guidance only and do not prove factual part/manual claims without source-truth confirmation. A diagram draft can be generated as guidance from the vis

### tracenet_visual_package_v34_38e81bfd9204aff5
- query: What does this picture prove about the part?
- intent: uploaded_image_visual_inspection
- mode: visual_observer_guidance
- final_gate_status: VISUAL_FINAL_GATE_PASS
- self_rag: SELF_RAG_VISUAL_GUIDANCE_READY / visual_guidance_ready
- crag: CRAG_VISUAL_NO_RETRY_GUIDANCE_READY retry_required=False
- preview: TRACE-Net built a visual guidance package for 1 image(s). The primary visual type is unknown_visual_claim_risk. Observations: image appears to be unknown_visual_claim_risk; manual-style visual inspection required. These visual observations are guidance only and do not prove factual part/manual claims without source-truth confirmation.

## Quality checks
- PASS sample_query_count: observed=4 expected=>= 0
- PASS sample_success_count: observed=4 expected=>= 0
- PASS visual_package_count: observed=4 expected=>= 0
- PASS image_quality_card_count: observed=4 expected=>= 0
- PASS visual_observation_card_count: observed=4 expected=>= 0
- PASS llava_observer_card_count: observed=4 expected=>= 0
- PASS guidance_only_visual_card_count: observed=4 expected=>= 0
- PASS self_rag_sample_count: observed=4 expected=>= 0
- PASS crag_sample_count: observed=4 expected=>= 0
- PASS visual_proof_authority_violation_count: observed=0 expected=<= 0
- PASS unsupported_visual_claim_count: observed=0 expected=<= 0
- PASS post_gate_issue_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
