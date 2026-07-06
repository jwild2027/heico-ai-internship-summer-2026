# TRACE-Net Graph Query API v1

Read-only API wrapper for TRACE-Net Graph Query Helper v1.

## Purpose

The existing graph contains deterministic document organization relationships such as part to page, page to source, and ATA to pages. Graph Query API v1 exposes those controlled helper results through simple HTTP endpoints without granting answer permission.

## Endpoints

- `GET /health`
- `GET /graph/routes`
- `GET /graph/part/{part_number}/sources`
- `GET /graph/page/{page_id}`
- `GET /graph/ata/{ata_code}/pages`
- `POST /graph/query`

## Safety contract

- No Postgres writes.
- No Qdrant writes.
- No OpenSearch writes.
- No source-truth mutation.
- No answer permission.
- No claim-proof authority.

This API returns structured graph/source context. Final answer generation still belongs behind TRACE-Net final-gate APIs.
