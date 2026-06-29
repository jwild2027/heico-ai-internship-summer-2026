# TRACE-Net Four-Route Operational Resolver v1

This artifact collapses detailed route labels into four operational processor families:
`blank`, `plain_text`, `table`, and `image`.

Detailed labels are preserved as `route_subtype` metadata.  Ambiguous rows remain
validator-gated and are not embedded/indexed until validators pass.

## Summary

- **answer_permission_count**: `0`
- **auto_resolved_operational_route_count**: `163`
- **can_answer_directly_count**: `0`
- **can_prove_claims_count**: `0`
- **do_not_embed_count**: `358`
- **human_review_required_count**: `0`
- **invalid_operational_route_count**: `0`
- **manual_review_required_count**: `0`
- **module**: `trace_net_four_route_operational_resolver_v1`
- **multi_route_required_count**: `222`
- **opensearch_index_allowed_count**: `143`
- **opensearch_write_attempt_count**: `0`
- **operational_record_count**: `509`
- **operational_resolution_status_counts**: `{'auto_resolved_four_route': 163, 'resolved_pending_storage_policy': 2, 'validator_gated_multi_route': 220, 'validator_gated_single_route': 124}`
- **operational_route_count**: `4`
- **operational_route_counts**: `{'blank': 14, 'image': 24, 'plain_text': 58, 'table': 413}`
- **operational_routes**: `['blank', 'plain_text', 'table', 'image']`
- **postgres_write_attempt_count**: `0`
- **qdrant_embedding_allowed_count**: `149`
- **qdrant_write_attempt_count**: `0`
- **ready_for_four_route_processing**: `True`
- **ready_for_validator_gated_storage**: `True`
- **route_subtype_counts**: `{'blank_candidate': 14, 'cover_or_title_page': 1, 'detailed_parts_list': 251, 'image_visual_diagram': 10, 'mixed_text_and_figure': 11, 'normal_text': 26, 'procedure_or_description': 26, 'review_required': 136, 'table_or_index': 34}`
- **source_record_count**: `509`
- **source_route_confidence_resolver**: `local_data\organization\trace_net\ocr_classifier_rerun_001\route_confidence_resolver_visual_diagram_clamped\trace_net_route_confidence_resolver_v1.json`
- **source_route_confidence_resolver_quality_status**: `PASS`
- **source_truth_mutation_allowed_count**: `0`
- **unknown_subtype_count**: `0`
- **unsafe_record_count**: `0`
- **validator_required_count**: `344`
- **version**: `v1`

## Safety contract

No Postgres writes, no Qdrant writes, no OpenSearch writes, no source-truth mutation, and no answer permission.
