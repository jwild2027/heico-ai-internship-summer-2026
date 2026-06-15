# TRACE-Net Graph Query API v1.1

Status: `GRAPH_QUERY_API_V1_1_READY`
Quality status: `PASS`

This API keeps organization-graph lookups as the default and exposes an optional evidence-enriched view with `include_evidence=true`.
It is retrieval-only and cannot prove claims or return final answers.

## Key counts

- route_record_count: `7`
- query_record_count: `3`
- enriched_query_record_count: `3`
- evidence_enriched_page_count: `87`
- source_resolved_page_count: `87`
- opensearch_exact_channel_count: `58`
- hybrid_v2_channel_count: `16`
- leiden_navigation_channel_count: `90`
- claim_entailment_channel_count: `8`
- can_answer_directly_count: `0`
- can_prove_claims_count: `0`

## Routes

- `GET /health` - api_health_check
- `GET /graph/routes` - route_catalog
- `GET /graph/enrichment/summary` - evidence_enrichment_summary
- `GET /graph/part/{part_number}/sources` - part_to_pages_to_sources_optional_evidence
- `GET /graph/page/{page_id}` - page_to_source_ata_parts_optional_evidence
- `GET /graph/ata/{ata_code}/pages` - ata_to_pages_to_sources_optional_evidence
- `POST /graph/query` - generic_controlled_graph_query_optional_evidence
