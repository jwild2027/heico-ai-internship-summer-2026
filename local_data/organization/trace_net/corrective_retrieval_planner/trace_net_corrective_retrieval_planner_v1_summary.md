# TRACE-Net Corrective Retrieval Planner v1

Status: `CORRECTIVE_RETRIEVAL_PLAN_BUILT`
Quality status: `PASS`

## Summary

- correction_record_count: `45`
- safe_action_record_count: `45`
- review_routed_record_count: `42`
- unsafe_correction_record_count: `0`
- answer_permission_count: `0`
- source_truth_mutation_allowed_count: `0`
- postgres_write_attempt_count: `0`
- qdrant_write_attempt_count: `0`
- opensearch_write_attempt_count: `0`

## Recommended action counts

- apply_blank_page_exact_page_rerank: `5`
- apply_graph_anchor_rerank: `14`
- compare_semantic_vs_exact_channels: `2`
- expand_bounded_graph_path: `7`
- expand_graph_evidence_enrichment: `2`
- expand_graph_source_path: `2`
- mark_result_audit_required_until_corrected: `2`
- require_human_review_before_final_answer: `4`
- rerank_with_graph_page_anchor: `2`
- rerank_with_graph_source_anchors: `1`
- retain_top_k_for_review: `14`
- route_to_review_if_still_flagged: `7`
- route_to_tiff_content_review: `15`
- run_claim_evidence_alignment_review: `4`
- run_corrective_retrieval_expansion: `2`
- run_opensearch_exact_if_identifier_present: `2`
- run_or_expand_vision_audit_sample: `15`
- use_final_gate_authorized_answer_path: `1`
- use_opensearch_exact_for_identifiers: `1`
- use_opensearch_table_cell_for_part_cells: `1`
- use_qdrant_bge_m3_for_semantic_candidates: `1`
- verify_blank_page_with_image_metrics: `2`
- verify_dublin_core_source_identity: `7`

## Safety contract

This artifact is read-only and retrieval-only. It does not grant final answer permission, does not prove claims, and does not mutate source truth.
