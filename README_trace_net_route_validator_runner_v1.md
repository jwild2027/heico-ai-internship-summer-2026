# TRACE-Net Route Validator Runner v1

This module validates the four operational TRACE-Net routes:

- `blank`
- `plain_text`
- `table`
- `image`

It reads the four-route operational resolver artifact, runs conservative route-specific validator checks, and decides which pages can safely leave `do_not_embed=true`.

## Safety contract

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission

## Scalable behavior

The runner does not require human review. Pages that fail validation stay graph/source-traceable, keep `final_do_not_embed=true`, and are queued for additional automated retry or multi-route probing.
