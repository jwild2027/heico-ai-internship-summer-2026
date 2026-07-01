# TRACE-Net Route Confidence Resolver v1

This module replaces unscalable page-by-page human review with automatic confidence resolution, multi-route execution, and validator-gated storage.

## Purpose

Inputs are OCR route scan-pack records and the canonical route taxonomy. Outputs are per-page route-confidence records with:

- `primary_route`
- `secondary_routes`
- `route_confidence_score`
- `route_confidence_band`
- `auto_resolved`
- `multi_route_required`
- `validator_required`
- `do_not_embed`
- `storage_policy`

## Safety contract

This module does not write Postgres, Qdrant, or OpenSearch. It does not mutate source truth. It does not grant answer permission.

## Scaling policy

- High-confidence pages are auto-resolved.
- Medium-confidence pages are multi-routed and validator-gated.
- Low-confidence pages are not human-review blocked; they are processed conservatively and excluded from normal embedding/search until route validators pass.
