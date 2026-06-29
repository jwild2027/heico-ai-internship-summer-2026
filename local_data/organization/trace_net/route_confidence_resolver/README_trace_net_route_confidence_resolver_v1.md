# TRACE-Net Route Confidence Resolver v1

This artifact replaces page-by-page human review as the scaling gate.
It emits high-confidence automatic route decisions and sends uncertain pages
to multi-route/validator-gated processing instead of guessing.

## Summary

- **answer_permission_count**: `0`
- **auto_resolved_route_count**: `175`
- **can_answer_directly_count**: `0`
- **can_prove_claims_count**: `0`
- **canonical_route_label_count**: `9`
- **do_not_embed_count**: `348`
- **human_review_replaced_by_validator_gate**: `True`
- **human_review_required_count**: `0`
- **invalid_taxonomy_label_count**: `0`
- **invalid_taxonomy_labels**: `[]`
- **manual_review_required_count**: `0`
- **module**: `trace_net_route_confidence_resolver_v1`
- **multi_route_required_count**: `162`
- **opensearch_index_allowed_count**: `144`
- **opensearch_write_attempt_count**: `0`
- **postgres_write_attempt_count**: `0`
- **primary_route_counts**: `{'blank_candidate': 14, 'cover_or_title_page': 109, 'detailed_parts_list': 251, 'image_visual_diagram': 58, 'mixed_text_and_figure': 9, 'normal_text': 10, 'procedure_or_description': 22, 'review_required': 3, 'table_or_index': 33}`
- **qdrant_embedding_allowed_count**: `161`
- **qdrant_write_attempt_count**: `0`
- **ready_for_multi_route_processing**: `True`
- **ready_for_validator_gated_storage**: `True`
- **resolver_record_count**: `509`
- **route_confidence_band_counts**: `{'high': 175, 'low': 122, 'medium': 212}`
- **route_label_taxonomy**: `local_data/organization/trace_net/route_label_taxonomy/trace_net_route_label_taxonomy_v1.json`
- **source_record_count**: `509`
- **source_scan_pack**: `local_data\organization\trace_net\ocr_route_scan_pack_tesseract_full\trace_net_ocr_route_scan_pack_v1.json`
- **source_scan_pack_quality_status**: `PASS`
- **source_truth_mutation_allowed_count**: `0`
- **unsafe_record_count**: `0`
- **validator_required_count**: `334`
- **version**: `v1`

## Safety contract

No Postgres writes, no Qdrant writes, no OpenSearch writes, no source-truth mutation, and no answer permission.
