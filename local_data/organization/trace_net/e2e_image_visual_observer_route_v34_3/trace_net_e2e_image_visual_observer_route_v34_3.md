# TRACE-Net E2E Image Visual Observer + OCR/OpenCV + Technical Drawing Geometry Route v34.3

Quality status: **PASS**
Status: `E2E_IMAGE_VISUAL_OBSERVER_ROUTE_READY`

## Summary
- sample_query_count: 5
- sample_success_count: 5
- visual_package_count: 5
- image_quality_card_count: 5
- ocr_text_card_count: 5
- ocr_text_candidate_count: 8
- opencv_layout_card_count: 5
- opencv_layout_region_count: 15
- technical_geometry_card_count: 5
- technical_drawing_candidate_count: 1
- technical_drawing_feature_card_count: 1
- technical_drawing_feature_count: 8
- dimension_text_candidate_count: 0
- circle_candidate_count: 6
- line_candidate_count: 18
- grounded_visual_package_count: 5
- unconfirmed_llava_text_claim_count: 0
- hallucinated_text_suppression_count: 0
- visual_observation_card_count: 5
- llava_observer_card_count: 5
- guidance_only_visual_card_count: 5
- source_truth_required_for_visual_claim_count: 5
- diagram_draft_card_count: 3
- diagram_draft_available_count: 3
- diagram_draft_guidance_only_count: 3
- visual_proof_authority_violation_count: 0
- unsupported_visual_claim_count: 0
- self_rag_sample_count: 5
- crag_sample_count: 5
- crag_retry_required_count: 0
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Contract
- LLaVA/image observations are guidance only, not proof authority.
- OCR text candidates, OpenCV layout regions, and technical drawing geometry cards are guidance, not proof authority.
- LLaVA visible-text claims must be confirmed by OCR or suppressed/downgraded; dimension/geometry candidates require source or human confirmation.
- Source truth is required before factual part/manual claims.
- Low-confidence visual observations require human review or source-truth confirmation.
- This stage does not write to Postgres, Qdrant, OpenSearch, or source truth.

## Sample records
### tracenet_visual_package_v34_3_06f08a6a9fbae844
- query: Inspect this uploaded manual page image and describe visible structure.
- intent: uploaded_image_visual_inspection
- mode: visual_observer_guidance
- final_gate_status: VISUAL_FINAL_GATE_PASS
- self_rag: SELF_RAG_VISUAL_GUIDANCE_READY_WITH_OCR_OPENCV_GROUNDING / visual_grounded_guidance_ready
- crag: CRAG_VISUAL_NO_RETRY_GUIDANCE_READY retry_required=False
- preview: TRACE-Net built an OCR/OpenCV + technical-geometry visual guidance package for 1 image(s). The primary visual type is diagram_candidate. Layout regions: Left visual region; Right visual region; Bottom text region. OCR text candidates: AIRCRAFT PARTS; POWERPLANT. LLaVA observations are retained as guidance only; OCR/OpenCV/geometry grounding is used before text/region/technical-drawing claims are surfaced. These visual observations do not prove fa

### tracenet_visual_package_v34_3_86f9e0d98fbee60c
- query: Does this image contain a diagram or callouts?
- intent: uploaded_image_diagram_draft
- mode: diagram_draft_guidance
- final_gate_status: VISUAL_FINAL_GATE_PASS
- self_rag: SELF_RAG_VISUAL_GUIDANCE_READY_WITH_OCR_OPENCV_GROUNDING / visual_grounded_guidance_ready
- crag: CRAG_VISUAL_NO_RETRY_GUIDANCE_READY retry_required=False
- preview: TRACE-Net built an OCR/OpenCV + technical-geometry visual guidance package for 1 image(s). The primary visual type is callout_diagram_candidate. Layout regions: Left visual region; Right visual region; Bottom text region. OCR text candidates: AIRCRAFT PARTS; POWERPLANT. LLaVA observations are retained as guidance only; OCR/OpenCV/geometry grounding is used before text/region/technical-drawing claims are surfaced. These visual observations do not 

### tracenet_visual_package_v34_3_efddfdabf97560b7
- query: Turn this image into a diagram draft.
- intent: uploaded_image_diagram_draft
- mode: diagram_draft_guidance
- final_gate_status: VISUAL_FINAL_GATE_PASS
- self_rag: SELF_RAG_VISUAL_GUIDANCE_READY_WITH_OCR_OPENCV_GROUNDING / visual_grounded_guidance_ready
- crag: CRAG_VISUAL_NO_RETRY_GUIDANCE_READY retry_required=False
- preview: TRACE-Net built an OCR/OpenCV + technical-geometry visual guidance package for 1 image(s). The primary visual type is diagram_generation_draft. Layout regions: Left visual region; Right visual region; Bottom text region. OCR text candidates: AIRCRAFT PARTS; POWERPLANT. LLaVA observations are retained as guidance only; OCR/OpenCV/geometry grounding is used before text/region/technical-drawing claims are surfaced. These visual observations do not p

### tracenet_visual_package_v34_3_9e12604b78fedb13
- query: Turn this engineering drawing into a technical diagram draft.
- intent: uploaded_image_diagram_draft
- mode: technical_drawing_draft_guidance
- final_gate_status: VISUAL_FINAL_GATE_PASS
- self_rag: SELF_RAG_VISUAL_GUIDANCE_READY_WITH_OCR_OPENCV_GROUNDING / visual_grounded_guidance_ready
- crag: CRAG_VISUAL_NO_RETRY_GUIDANCE_READY retry_required=False
- preview: TRACE-Net built an OCR/OpenCV + technical-geometry visual guidance package for 1 image(s). The primary visual type is technical_drawing_candidate. Layout regions: Left visual region; Right visual region; Bottom text region. OCR text candidates: AIRCRAFT PARTS; POWERPLANT. Technical drawing features detected as guidance: left sectional/profile view; right front/flange view; dimension lines; cross-section hatching; central bore; bolt-hole circle pa

### tracenet_visual_package_v34_3_8c40fef4a6eb08fd
- query: What does this picture prove about the part?
- intent: uploaded_image_visual_inspection
- mode: visual_observer_guidance
- final_gate_status: VISUAL_FINAL_GATE_PASS
- self_rag: SELF_RAG_VISUAL_GUIDANCE_READY_WITH_OCR_OPENCV_GROUNDING / visual_grounded_guidance_ready
- crag: CRAG_VISUAL_NO_RETRY_GUIDANCE_READY retry_required=False
- preview: TRACE-Net built an OCR/OpenCV + technical-geometry visual guidance package for 1 image(s). The primary visual type is unknown_visual_claim_risk. Layout regions: Left visual region; Right visual region; Bottom text region. OCR did not confirm readable text candidates in this package. LLaVA observations are retained as guidance only; OCR/OpenCV/geometry grounding is used before text/region/technical-drawing claims are surfaced. These visual observa

## Quality checks
- PASS sample_query_count: observed=5 expected=>= 0
- PASS sample_success_count: observed=5 expected=>= 0
- PASS visual_package_count: observed=5 expected=>= 0
- PASS image_quality_card_count: observed=5 expected=>= 0
- PASS ocr_text_card_count: observed=5 expected=>= 0
- PASS opencv_layout_card_count: observed=5 expected=>= 0
- PASS technical_geometry_card_count: observed=5 expected=>= 0
- PASS technical_drawing_candidate_count: observed=1 expected=>= 0
- PASS technical_drawing_feature_card_count: observed=1 expected=>= 0
- PASS grounded_visual_package_count: observed=5 expected=>= 0
- PASS visual_observation_card_count: observed=5 expected=>= 0
- PASS llava_observer_card_count: observed=5 expected=>= 0
- PASS guidance_only_visual_card_count: observed=5 expected=>= 0
- PASS self_rag_sample_count: observed=5 expected=>= 0
- PASS crag_sample_count: observed=5 expected=>= 0
- PASS diagram_draft_card_count: observed=3 expected=>= 0
- PASS diagram_draft_guidance_only_count: observed=3 expected=>= 0
- PASS visual_proof_authority_violation_count: observed=0 expected=<= 0
- PASS unsupported_visual_claim_count: observed=0 expected=<= 0
- PASS post_gate_issue_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
