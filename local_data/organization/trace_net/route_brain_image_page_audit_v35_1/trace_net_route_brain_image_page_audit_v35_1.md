# TRACE-Net Route Brain Image Page Audit v35.1

Quality status: **PASS**
Status: `E2E_ROUTE_BRAIN_IMAGE_PAGE_AUDIT_READY`

## Summary
- source_page_count: 509
- route_index_page_count: 122
- route_candidate_count: 509
- manual_screened_diagram_page_count: 159
- actual_diagram_page_count: 159
- route_manifest_image_visual_candidate_count: 122
- corrected_image_visual_count: 159
- overbroad_image_visual_candidate_count: 104
- missed_diagram_page_count: 141
- malformed_route_value_count: 0
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Corrected route counts
- image_visual: 159
- review: 350

## Repair action counts
- demote_overbroad_image_visual_to_review_non_diagram: 104
- keep_visual_route_confirmed_by_manual_screen: 18
- manual_screen_non_diagram_unclassified_review: 246
- promote_to_image_visual_from_manual_screen: 141

## Contract
- This audit does not mutate source truth.
- Manual-screened diagram labels are used to calibrate routing, not to prove manual/part claims.
