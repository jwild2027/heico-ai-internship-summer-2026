# TRACE-Net Calibrated Cascade Route Brain v35.3

Quality status: **PASS**
Status: `E2E_CALIBRATED_CASCADE_ROUTE_BRAIN_READY`

## Summary
- source_page_count: 509
- route_decision_count: 509
- actual_diagram_page_count: 159
- primary_route_counts: {'blank_candidate': 14, 'image_visual': 185, 'normal_text': 283, 'table': 27}
- fishnet_action_counts: {'accept_route': 250, 'dual_route_text_and_visual': 197, 'review_required': 62}
- dispatch_visual_count: 185
- fishnet_visual_review_candidate_count: 61
- fishnet_review_queue_count: 259
- diagram_precision: 0.8378
- diagram_recall: 0.9748
- binary_accuracy: 0.9332
- false_negative_diagram_count: 4
- false_positive_non_diagram_count: 30
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Contract
- This stage creates an operational route manifest from v35.2 features.
- Manual labels are used for evaluation/calibration metrics only, not answer proof.
- No LLaVA/Gemma calls, database writes, source-truth mutation, or answer permission.
