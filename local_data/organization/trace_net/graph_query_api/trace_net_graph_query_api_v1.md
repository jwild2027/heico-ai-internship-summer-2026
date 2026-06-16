# TRACE-Net Graph Query API v1

Read-only API wrapper for controlled graph query helper results.

## Summary

- Quality status: PASS
- Status: GRAPH_QUERY_API_READY
- Source helper quality: PASS
- Route records: 5
- Query records available: 3
- Can answer directly count: 0
- Can prove claims count: 0
- Source truth mutation allowed count: 0

## Routes

- `GET /health` - api_health_check
- `GET /graph/part/{part_number}/sources` - part_to_pages_to_sources
- `GET /graph/page/{page_id}` - page_to_source_ata_parts
- `GET /graph/ata/{ata_code}/pages` - ata_to_pages_to_sources
- `POST /graph/query` - generic_controlled_graph_query

## Safety

This API returns structured graph/source records. It does not grant answer permission or claim-proof authority.
