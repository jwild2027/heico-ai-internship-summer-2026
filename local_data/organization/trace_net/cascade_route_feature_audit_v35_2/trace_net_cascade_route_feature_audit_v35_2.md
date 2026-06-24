# TRACE-Net Cascade Route Feature Audit v35.2

Quality status: **PASS**
Status: `E2E_CASCADE_ROUTE_FEATURE_AUDIT_READY`

## Summary
- source_page_count: 509
- actual_diagram_page_count: 159
- feature_record_count: 509
- feature_column_count: 16
- route_manifest_image_visual_candidate_count: 25
- diagram_precision: 0.8378
- diagram_recall: 0.9748
- binary_accuracy: 0.9332
- fishnet_uncertain_count: 209
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Confusion matrix
- true_positive_diagram_predicted_visual: 155
- false_positive_non_diagram_predicted_visual: 30
- true_negative_non_diagram_predicted_non_visual: 320
- false_negative_diagram_predicted_non_visual: 4
- total: 509

## Contract
- Feature audit only; it does not mutate source truth.
- No LLaVA/Gemma calls are made in this stage.
- Manual labels are used as route calibration/evaluation labels, not proof for answers.
