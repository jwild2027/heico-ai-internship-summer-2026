# TRACE-Net WebUI Visual Context Bridge v1

Quality status: PASS

## Summary

- answer_permission_count: 0
- can_answer_directly_count: 0
- can_prove_claims_count: 0
- context_authority: vision_derived_retrieval_guidance_not_source_truth
- hallucination_risk_status_counts: {'LOW_SUPPORTED_BY_OCR': 1, 'MEDIUM_REVIEW_REQUIRED': 9, 'HIGH_REVIEW_REQUIRED': 2}
- included_canonical_page_numbers: [1, 22]
- included_page_count: 2
- included_pages: ['t_p_120_1176_p000001', 't_p_120_1176_p000022']
- opensearch_write_attempt_count: 0
- postgres_write_attempt_count: 0
- qdrant_write_attempt_count: 0
- review_only_visual_context_excluded_count: 10
- semantic_validation_status_counts: {'WEBUI_VISUAL_CONTEXT_ALLOWED': 2, 'REVIEW_ONLY_VISUAL_CONTEXT': 9, 'VISION_OBSERVATION_ERROR_REVIEW_ONLY': 1}
- source_image_visual_handoff_count: 12
- source_image_visual_summary_quality_status: PASS
- source_image_visual_summary_record_count: 12
- source_truth_mutation_allowed_count: 0
- source_webui_visual_context_allowed_count: 2
- unsafe_record_count: 0
- vision_model_counts: {'llava:13b': 2}
- visual_context_card_count: 2

## Included context cards

- t_p_120_1176_p000001 page=1 risk=LOW_SUPPORTED_BY_OCR supported_terms=['Passenger Seats', 'Component Maintenance Manual with Illustrated Parts List', 'component maintenance', 'parts list']
- t_p_120_1176_p000022 page=22 risk=MEDIUM_REVIEW_REQUIRED supported_terms=["Title: 'Airplane Maintenance Manual'", "Page number: '25'"]

Safety: visual context is retrieval guidance only, not source truth and not answer permission.
