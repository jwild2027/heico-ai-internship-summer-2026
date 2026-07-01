# TRACE-Net Four-Route Operational Resolver v1

This module collapses detailed route-confidence labels into the four operational processor families used at scale:

- `blank`
- `plain_text`
- `table`
- `image`

The previous detailed label is retained as `route_subtype`.  This keeps the operational router simple while preserving enough metadata for validators, auditing, and storage policy.

## Safety contract

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission

## Scalable behavior

Rows with high confidence can be auto-resolved into one of the four processor families.  Ambiguous rows carry secondary operational routes and stay validator-gated with `do_not_embed=true` until validators pass.  No human review is required by this module.
